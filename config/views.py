"""Public HTTP surface: landing page and health check."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from assessments.models import Pillar

SALES_EMAIL_PLACEHOLDER = "[EMAIL-COMERCIAL]"


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    """Render the public landing page; pillar names come from the database."""
    pillars = Pillar.objects.filter(is_active=True).order_by("display_order")
    sales_email = getattr(settings, "QL_SALES_EMAIL", "") or SALES_EMAIL_PLACEHOLDER
    return render(
        request, "home.html", {"pillars": pillars, "sales_email": sales_email}
    )


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Report process availability without querying dependencies."""
    return JsonResponse({"status": "ok"})
