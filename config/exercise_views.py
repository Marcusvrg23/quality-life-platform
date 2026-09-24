"""Read-only exercise presentation under the existing tenant authorization."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .exercises import EXERCISES, SOURCE
from .tenant import resolve_tenant_context


@login_required
@require_GET
def exercises(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        raise PermissionDenied("Organization unavailable.")
    return render(
        request,
        "exercises/library.html",
        {
            "tenant": tenant,
            "exercises": EXERCISES,
            "categories": tuple(dict.fromkeys(item["category"] for item in EXERCISES)),
            "source": SOURCE,
        },
    )
