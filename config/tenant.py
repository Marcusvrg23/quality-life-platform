"""Server-side tenant authorization shared by product views."""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from identity.models import Membership, Organization

SESSION_ORGANIZATION_KEY = "active_organization_id"


@dataclass(frozen=True)
class TenantContext:
    organization: Organization
    membership: Membership
    role: str


def active_memberships(user):
    """Return only operational memberships; superusers get no implicit bypass."""
    if not user.is_authenticated or not user.is_active:
        return Membership.objects.none()
    return Membership.objects.select_related("organization").filter(
        user=user, is_active=True, organization__is_active=True
    )


def get_user_organizations(user):
    if not user.is_authenticated or not user.is_active:
        return Organization.objects.none()
    return Organization.objects.filter(
        memberships__user=user,
        memberships__is_active=True,
        is_active=True,
    ).distinct()


def get_active_membership(user, organization):
    organization_id = getattr(organization, "pk", organization)
    return active_memberships(user).filter(organization_id=organization_id).first()


def require_active_membership(user, organization):
    membership = get_active_membership(user, organization)
    if membership is None:
        raise PermissionDenied("No active membership for this organization.")
    return membership


def require_membership_for_slug(user, slug):
    """Resolve a tenant only inside the caller's authorized set."""
    membership = active_memberships(user).filter(organization__slug=slug).first()
    if membership is None:
        raise PermissionDenied("Organization unavailable.")
    return membership


def user_has_role(user, organization, *roles):
    membership = get_active_membership(user, organization)
    return membership is not None and membership.role in roles


def context_for_membership(membership):
    return TenantContext(
        organization=membership.organization,
        membership=membership,
        role=membership.role,
    )


def resolve_tenant_context(request):
    """Revalidate the selected tenant on every request, including stale sessions."""
    memberships = active_memberships(request.user)
    selected_id = request.session.get(SESSION_ORGANIZATION_KEY)
    if selected_id is not None:
        membership = memberships.filter(organization_id=selected_id).first()
        if membership is None:
            request.session.pop(SESSION_ORGANIZATION_KEY, None)
            raise PermissionDenied("Selected organization is unavailable.")
        return context_for_membership(membership)

    available = list(memberships[:2])
    if len(available) == 1:
        request.session[SESSION_ORGANIZATION_KEY] = available[0].organization_id
        return context_for_membership(available[0])
    return None
