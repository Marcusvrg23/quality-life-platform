"""Invitation tokens: generated once, shown once, stored only as SHA-256."""

import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .models import INVITATION_ROLES, Invitation, MembershipRole

INVITATION_TTL = timedelta(days=7)
MAX_INVITATIONS_PER_BATCH = 50


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_invitations(
    organization, created_by, count, role=MembershipRole.COLLABORATOR
):
    """Create `count` invitations and return their plain tokens (never persisted).

    Only a superuser (the Quality Life operator) may invite a corporate manager.
    """
    if not 1 <= count <= MAX_INVITATIONS_PER_BATCH:
        raise ValueError("Invitation count out of range.")
    if role not in INVITATION_ROLES:
        raise ValueError("Role cannot be invited.")
    if role != MembershipRole.COLLABORATOR and not created_by.is_superuser:
        raise PermissionDenied("Only the Quality Life operator invites managers.")
    now = timezone.now()
    tokens = [secrets.token_urlsafe(32) for _ in range(count)]
    with transaction.atomic():
        Invitation.objects.bulk_create(
            Invitation(
                organization=organization,
                created_by=created_by,
                token_hash=hash_token(token),
                created_at=now,
                expires_at=now + INVITATION_TTL,
                role=role,
            )
            for token in tokens
        )
    return tokens


def pending_invitations(organization, role=MembershipRole.COLLABORATOR):
    return Invitation.objects.filter(
        organization=organization,
        role=role,
        used_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at", "-pk")


def find_invitation(token, *, lock=False):
    """Return the invitation for `token` if it can still be accepted, else None."""
    queryset = Invitation.objects.select_related("organization")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    invitation = queryset.filter(token_hash=hash_token(token)).first()
    if invitation is None or not invitation.is_usable(timezone.now()):
        return None
    return invitation
