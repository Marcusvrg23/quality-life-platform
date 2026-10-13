"""Public HTTP surface: landing page and health check."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from assessments.models import Pillar

SALES_EMAIL_PLACEHOLDER = "[EMAIL-COMERCIAL]"

# Landing icon per pillar code (symbols live in templates/home.html).
PILLAR_ICONS = {
    "physical_health": "heart-pulse",
    "preventive_behavior": "shield",
    "physical_activity": "activity",
    "nutrition_hydration": "droplet",
    "relationships": "users",
    "mental_emotional_health": "brain",
    "ergonomics_workplace": "monitor",
    "sleep_recovery": "moon",
    "work_life_balance": "balance",
}
DEFAULT_PILLAR_ICON = "leaf"


def pillar_icon(code: str) -> str:
    return PILLAR_ICONS.get(code, DEFAULT_PILLAR_ICON)


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    """Render the public landing page; pillar names come from the database."""
    pillars = list(Pillar.objects.filter(is_active=True).order_by("display_order"))
    for pillar in pillars:
        pillar.icon = pillar_icon(pillar.code)
    sales_email = getattr(settings, "QL_SALES_EMAIL", "") or SALES_EMAIL_PLACEHOLDER
    return render(
        request, "home.html", {"pillars": pillars, "sales_email": sales_email}
    )


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Report process availability without querying dependencies."""
    return JsonResponse({"status": "ok"})
