"""Public landing and dependency-free health endpoint."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from assessments.models import Pillar


@require_GET
def foundation(request: HttpRequest) -> HttpResponse:
    """Present the platform with approved pillar names from the database."""
    return render(
        request,
        "home.html",
        {
            "pillars": Pillar.objects.order_by("display_order"),
            "sales_email": getattr(settings, "QL_SALES_EMAIL", "[EMAIL-COMERCIAL]"),
        },
    )


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Report process availability without querying dependencies."""
    return JsonResponse({"status": "ok"})
