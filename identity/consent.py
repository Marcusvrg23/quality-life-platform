"""LGPD consent for the assessment (health data), always scoped to one company."""

from django.db import transaction
from django.utils import timezone

from config.legal import CONSENT_VERSION

from .models import ConsentRecord

PURPOSE = ConsentRecord.Purpose.ASSESSMENT_HEALTH_DATA


def _own(user, organization):
    return ConsentRecord.objects.filter(
        user=user, organization=organization, purpose=PURPOSE
    )


def active_consents(user, organization):
    return _own(user, organization).filter(revoked_at__isnull=True)


def has_active_consent(user, organization):
    """Active means not revoked and accepted on the current text version."""
    return active_consents(user, organization).filter(version=CONSENT_VERSION).exists()


def grant_consent(user, organization):
    """Record consent once per version; callers serialize per user."""
    existing = active_consents(user, organization).filter(version=CONSENT_VERSION)
    record = existing.first()
    if record is None:
        record = ConsentRecord.objects.create(
            user=user,
            organization=organization,
            purpose=PURPOSE,
            version=CONSENT_VERSION,
            accepted_at=timezone.now(),
        )
    return record


def revoke_consent(user, organization):
    """Fill revoked_at on every active record of this user in this company."""
    now = timezone.now()
    with transaction.atomic():
        records = list(active_consents(user, organization).select_for_update())
        for record in records:
            record.revoke(now)
    return len(records)


def revoked_user_ids(organization):
    """Users whose most recent consent in this company is revoked."""
    latest = (
        ConsentRecord.objects.filter(organization=organization, purpose=PURPOSE)
        .order_by("user_id", "-accepted_at", "-pk")
        .distinct("user_id")
        .values_list("user_id", "revoked_at")
    )
    return {user_id for user_id, revoked_at in latest if revoked_at is not None}
