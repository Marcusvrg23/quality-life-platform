"""Assistente Quality pages (docs/specs/18-assistente.md)."""

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from config.tenant import resolve_tenant_context

from . import assistant

BUSY = "O assistente não conseguiu responder agora. Tente de novo em instantes."
LIMIT = "Você chegou ao limite de mensagens de hoje. Amanhã o assistente volta."
INVALID = "Mensagem inválida. Escreva um texto de até 1000 caracteres."


def _tenant(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        raise PermissionDenied("Organization unavailable.")
    if not assistant.enabled_for(tenant.organization):
        raise Http404("Assistant unavailable for this company.")
    return tenant


def _answer(text, status=200, **extra):
    response = JsonResponse({"answer": text, **extra}, status=status)
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_GET
def assistant_page(request):
    tenant = _tenant(request)
    return render(
        request,
        "wellbeing/assistant.html",
        {
            "tenant": tenant,
            "daily_limit": settings.ASSISTANT_DAILY_LIMIT,
            "max_chars": assistant.MAX_CHARS,
        },
    )


@login_required
@require_POST
def assistant_message(request):
    tenant = _tenant(request)
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        body = None
    history = assistant.clean_history(
        body.get("messages") if isinstance(body, dict) else None
    )
    if history is None:
        return _answer(INVALID, status=400, error="invalid")
    if assistant.is_crisis(history[-1]["content"]):
        # Fixed answer with the CVV; nothing goes to the API.
        return _answer(assistant.CRISIS_ANSWER, crisis=True)
    if not assistant.take_slot(tenant.membership, timezone.localdate()):
        return _answer(LIMIT, status=429, error="limit")
    try:
        text = assistant.ask(history, tenant.membership)
    except assistant.AssistantError:
        return _answer(BUSY, status=502, error="unavailable")
    return _answer(text)
