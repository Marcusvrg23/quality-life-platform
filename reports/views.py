"""Executive report for corporate managers: aggregated data only."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from config.tenant import resolve_tenant_context
from identity.models import Membership
from wellbeing.services import company_usage

from .services import MIN_GROUP, build_executive_report

REPORT_ROLES = (Membership.Role.CORPORATE_MANAGER, Membership.Role.ADMIN)
DEFAULT_PERIOD_DAYS = 90


def report_period():
    """Always the last 90 days, today included.

    Free periods let two near-identical windows be diffed to isolate one
    person's answers, so the period is not taken from the request.
    """
    end = timezone.localdate()
    return end - timedelta(days=DEFAULT_PERIOD_DAYS - 1), end


@login_required
@require_GET
def executive_report(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        return redirect("app")
    if tenant.role not in REPORT_ROLES:
        raise PermissionDenied("Report unavailable.")
    start, end = report_period()
    report = build_executive_report(tenant.organization, start, end)
    return render(
        request,
        "reports/executive.html",
        {
            "tenant": tenant,
            "report": report,
            "generated_at": timezone.now(),
            "min_group": MIN_GROUP,
            "period_days": DEFAULT_PERIOD_DAYS,
            "usage": company_usage(tenant.organization),
        },
    )
