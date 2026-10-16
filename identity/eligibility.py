"""Who may enter which company, and as what: the only place that decides it.

Membership creation at sign-in (Google or password), reactivation, role
alignment and the removal side effects all go through here. ADMIN memberships
and superusers are never touched: they are managed by the operator panel.
"""

import logging
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from .models import ALLOWED_EMAIL_ROLES, AllowedEmail, Membership, User

logger = logging.getLogger("quality_life.eligibility")

EMAIL_SEPARATORS = re.compile(r"[\s,;]+")
LIST_ROLES = frozenset(role.value for role in ALLOWED_EMAIL_ROLES)


def normalize_email(email):
    return User.objects.normalize_email(email or "")


def parse_emails(text):
    """Split pasted text into (valid unique e-mails, invalid tokens, repeated).

    Accepts one per line, commas, semicolons, tabs or spaces (an Excel column
    pastes as lines). Order is kept; comparison is case-insensitive.
    """
    valid, invalid, repeated, seen = [], [], [], set()
    for token in EMAIL_SEPARATORS.split(text or ""):
        if not token:
            continue
        email = normalize_email(token)
        try:
            validate_email(email)
        except ValidationError:
            invalid.append(token)
            continue
        if email in seen:
            repeated.append(email)
            continue
        seen.add(email)
        valid.append(email)
    return valid, invalid, repeated


def eligible_entries(email):
    """Allowed-list rows for this e-mail in ACTIVE companies only."""
    return AllowedEmail.objects.filter(
        email=normalize_email(email), organization__is_active=True
    ).select_related("organization")


def is_eligible(email):
    return eligible_entries(email).exists()


def _protected(membership):
    return membership.role == Membership.Role.ADMIN or membership.user.is_superuser


def memberships_for_email(email):
    """Create or reactivate the memberships the allowed list grants this e-mail.

    Returns the memberships that now back the list, for the user who owns the
    e-mail; an unknown e-mail yields []. Only active companies count. An
    existing COLLABORATOR/CORPORATE_MANAGER membership is reactivated and its
    role aligned with the list; ADMIN memberships and superusers keep theirs.
    """
    user = User.objects.filter(email__iexact=normalize_email(email)).first()
    if user is None:
        return []
    granted = []
    for entry in eligible_entries(email):
        with transaction.atomic():
            membership, created = Membership.objects.select_for_update().get_or_create(
                user=user,
                organization=entry.organization,
                defaults={"role": entry.role},
            )
            if not created and not _protected(membership):
                changes = []
                if not membership.is_active:
                    membership.is_active = True
                    changes.append("is_active")
                if membership.role != entry.role:
                    membership.role = entry.role
                    changes.append("role")
                if changes:
                    membership.save(update_fields=[*changes, "updated_at"])
        if created:
            logger.info(
                "eligibility_membership_created user=%s organization=%s entry=%s",
                user.pk,
                entry.organization_id,
                entry.pk,
            )
        granted.append(membership)
    return granted


def add_allowed_emails(organization, emails, role, added_by):
    """Add e-mails to a company's list; returns (added rows, already listed).

    `role` must be COLLABORATOR or CORPORATE_MANAGER. An e-mail already on the
    company's list is reported as repeated and left unchanged.
    """
    if role not in LIST_ROLES:
        raise ValueError("Role cannot be allowed.")
    added, repeated = [], []
    for email in emails:
        email = normalize_email(email)
        try:
            with transaction.atomic():
                entry = AllowedEmail.objects.create(
                    organization=organization,
                    email=email,
                    role=role,
                    added_by=added_by,
                )
        except IntegrityError:
            repeated.append(email)
            continue
        added.append(entry)
    if added:
        logger.info(
            "eligibility_emails_added organization=%s count=%s role=%s by=%s",
            organization.pk,
            len(added),
            role,
            getattr(added_by, "pk", None),
        )
    return added, repeated


def remove_allowed_email(entry, removed_by):
    """Delete the list row and deactivate the matching membership right away."""
    with transaction.atomic():
        membership = (
            Membership.objects.select_for_update()
            .select_related("user")
            .filter(
                organization=entry.organization,
                user__email__iexact=entry.email,
                is_active=True,
            )
            .first()
        )
        if membership is not None and not _protected(membership):
            membership.is_active = False
            membership.save(update_fields=["is_active", "updated_at"])
        entry_pk, organization_pk = entry.pk, entry.organization_id
        entry.delete()
    logger.info(
        "eligibility_email_removed organization=%s entry=%s by=%s",
        organization_pk,
        entry_pk,
        getattr(removed_by, "pk", None),
    )


def set_allowed_email_role(entry, role, changed_by):
    """Change the role on the list and on the existing membership, if any."""
    if role not in LIST_ROLES:
        raise ValueError("Role cannot be allowed.")
    with transaction.atomic():
        AllowedEmail.objects.filter(pk=entry.pk).update(role=role)
        entry.role = role
        membership = (
            Membership.objects.select_for_update()
            .select_related("user")
            .filter(organization=entry.organization, user__email__iexact=entry.email)
            .first()
        )
        if membership is not None and not _protected(membership):
            membership.role = role
            membership.save(update_fields=["role", "updated_at"])
    logger.info(
        "eligibility_role_changed organization=%s entry=%s role=%s by=%s",
        entry.organization_id,
        entry.pk,
        role,
        getattr(changed_by, "pk", None),
    )
    return entry
