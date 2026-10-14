"""Wellbeing pages and the owner-only practice record."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from config import wellbeing_catalog as catalog
from config.tenant import resolve_tenant_context
from identity.models import Membership

from .models import MIN_RECORD_SECONDS, ActivitySession

# Two records of the same person may not overlap in time (a resent or
# duplicated request would otherwise count the same minutes twice).
OVERLAP_TOLERANCE = timedelta(seconds=5)


def _tenant(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        raise PermissionDenied("Organization unavailable.")
    return tenant


@login_required
@require_POST
def record(request):
    """Store one finished (or 60 s+) practice for the caller and active tenant.

    Only kind, slug, duration and completion come from the client; user,
    organization and start time come from the server.
    """
    tenant = _tenant(request)
    item = catalog.find_available(
        request.POST.get("kind", ""), request.POST.get("slug", "")
    )
    if item is None:
        raise Http404("Practice unavailable.")
    try:
        seconds = int(request.POST.get("duration_seconds", ""))
    except ValueError:
        return JsonResponse({"error": "duration"}, status=400)
    if seconds < MIN_RECORD_SECONDS:
        return JsonResponse({"error": "duration"}, status=400)
    seconds = min(seconds, catalog.max_seconds(item))
    now = timezone.now()
    started_at = now - timedelta(seconds=seconds)
    with transaction.atomic():
        # Serialize records of this person in this organization.
        Membership.objects.select_for_update().get(pk=tenant.membership.pk)
        last = (
            ActivitySession.objects.filter(
                user=request.user, organization=tenant.organization
            )
            .order_by("-started_at")
            .first()
        )
        if last and (
            last.started_at + timedelta(seconds=last.duration_seconds)
            > started_at + OVERLAP_TOLERANCE
        ):
            return JsonResponse({"error": "overlap"}, status=409)
        ActivitySession.objects.create(
            user=request.user,
            organization=tenant.organization,
            kind=item["kind"],
            slug=item["slug"],
            started_at=started_at,
            duration_seconds=seconds,
            completed=request.POST.get("completed") == "1",
        )
    return JsonResponse({"ok": True}, status=201)
