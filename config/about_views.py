"""'Conheça a Quality' (docs/specs/16-conheca-a-quality.md): the company
presentation inside the app, for every signed-in role."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .tenant import resolve_tenant_context
from .views import SALES_EMAIL_PLACEHOLDER

# Contact printed in the Quality Life business presentation.
PRESENTATION_EMAIL = "ceo.qualitylife.online@gmail.com"


def contact_email():
    configured = getattr(settings, "QL_SALES_EMAIL", "") or ""
    if configured and configured != SALES_EMAIL_PLACEHOLDER:
        return configured
    return PRESENTATION_EMAIL


@login_required
@require_GET
def about_quality(request):
    # Like "Instalar o app": opens without a company (operator panel), and a
    # forged company in the session is refused by resolve_tenant_context.
    tenant = resolve_tenant_context(request)
    return render(
        request,
        "about/conheca.html",
        {"tenant": tenant, "sales_email": contact_email()},
    )
