"""Public legal drafts and the signed-in consent/revocation page."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from identity.consent import active_consents, revoke_consent

from .legal import CONSENT_TEXT_LABEL
from .tenant import resolve_tenant_context


def _legal_context():
    return {
        "company_name": settings.LEGAL_COMPANY_NAME,
        "cnpj": settings.LEGAL_CNPJ,
        "dpo_email": settings.LEGAL_DPO_EMAIL,
        "consent_text_label": CONSENT_TEXT_LABEL,
    }


@require_GET
def privacy(request):
    return render(request, "legal/privacy.html", _legal_context())


@require_GET
def terms(request):
    return render(request, "legal/terms.html", _legal_context())


@login_required
@require_GET
def privacy_settings(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        return redirect("app")
    return render(
        request,
        "legal/settings.html",
        {
            **_legal_context(),
            "tenant": tenant,
            "consents": active_consents(request.user, tenant.organization).order_by(
                "-accepted_at"
            ),
        },
    )


@login_required
@require_POST
def privacy_revoke(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        return redirect("app")
    if request.POST.get("confirm") != "on":
        messages.error(request, "Confirme a revogação marcando a caixa.")
    elif revoke_consent(request.user, tenant.organization):
        messages.success(
            request,
            "Autorização revogada. Suas respostas não entram mais no relatório "
            "da empresa e novas respostas estão bloqueadas.",
        )
    return redirect("privacy_settings")
