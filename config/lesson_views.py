"""Lesson videos under the existing tenant authorization."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .lessons import LESSONS
from .tenant import resolve_tenant_context


@login_required
@require_GET
def lessons(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        raise PermissionDenied("Organization unavailable.")
    return render(
        request, "lessons/lessons.html", {"tenant": tenant, "lessons": LESSONS}
    )
