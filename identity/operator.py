"""Quality Life operator actions: companies and the operator's own admin access."""

import logging

from django.db import IntegrityError, transaction
from django.utils.text import slugify

from .models import Membership, Organization

logger = logging.getLogger("quality_life.operator")

SLUG_MAX_LENGTH = Organization._meta.get_field("slug").max_length
# Room for a "-<n>" suffix inside the slug column.
SLUG_BASE_LENGTH = SLUG_MAX_LENGTH - 8
FALLBACK_SLUG = "empresa"
CREATE_ATTEMPTS = 5


def unique_slug(name):
    base = slugify(name)[:SLUG_BASE_LENGTH].strip("-") or FALLBACK_SLUG
    candidate, suffix = base, 2
    while Organization.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def create_organization(name, operator):
    """Create an active company; retries if a concurrent request took the slug."""
    for attempt in range(1, CREATE_ATTEMPTS + 1):
        try:
            with transaction.atomic():
                organization = Organization.objects.create(
                    name=name, slug=unique_slug(name)
                )
            break
        except IntegrityError:
            if attempt == CREATE_ATTEMPTS:
                raise
    logger.info(
        "operator_organization_created operator=%s organization=%s",
        operator.pk,
        organization.pk,
    )
    return organization


def set_organization_active(organization, active, operator):
    """Deactivation only blocks access; memberships and data stay untouched."""
    Organization.objects.filter(pk=organization.pk).update(is_active=active)
    logger.info(
        "operator_organization_status operator=%s organization=%s active=%s",
        operator.pk,
        organization.pk,
        active,
    )


def enter_as_admin(operator, organization):
    """Create or reactivate the operator's own ADMIN membership; nobody else's."""
    with transaction.atomic():
        membership, created = Membership.objects.select_for_update().get_or_create(
            user=operator,
            organization=organization,
            defaults={"role": Membership.Role.ADMIN},
        )
        if not created and (
            membership.role != Membership.Role.ADMIN or not membership.is_active
        ):
            membership.role = Membership.Role.ADMIN
            membership.is_active = True
            membership.save(update_fields=["role", "is_active", "updated_at"])
    logger.info(
        "operator_entered_as_admin operator=%s organization=%s",
        operator.pk,
        organization.pk,
    )
    return membership
