"""Executive report for corporate managers: aggregated data only."""

import re
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from config.tenant import resolve_tenant_context
from identity.models import Membership

from .services import MIN_GROUP, build_executive_report

REPORT_ROLES = (Membership.Role.CORPORATE_MANAGER, Membership.Role.ADMIN)
DEFAULT_PERIOD_DAYS = 90
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _parse_date(value):
    if not value or not ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def report_period(query):
    """Invalid or inverted dates fall back to the last 90 days, today included."""
    end_default = timezone.localdate()
    start_default = end_default - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    start = _parse_date(query.get("inicio")) or start_default
    end = _parse_date(query.get("fim")) or end_default
    if start > end:
        return start_default, end_default
    return start, end


@login_required
@require_GET
def executive_report(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        return redirect("app")
    if tenant.role not in REPORT_ROLES:
        raise PermissionDenied("Report unavailable.")
    start, end = report_period(request.GET)
    report = build_executive_report(tenant.organization, start, end)
    return render(
        request,
        "reports/executive.html",
        {
            "tenant": tenant,
            "report": report,
            "generated_at": timezone.now(),
            "min_group": MIN_GROUP,
        },
    )
