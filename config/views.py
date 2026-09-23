"""Minimal HTTP surface for the Quality Life V2 foundation."""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def foundation(request: HttpRequest) -> HttpResponse:
    """Render the foundation smoke page without product functionality."""
    return render(request, "foundation.html")


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Report process availability without querying dependencies."""
    return JsonResponse({"status": "ok"})
