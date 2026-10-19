"""Assistente Quality (docs/specs/18-assistente.md).

A short chat about workplace wellbeing and the app, answered by an
OpenAI-compatible chat API (Groq by default). Privacy by design:

- The conversation lives only in the person's browser tab; the server keeps
  no text, only a per-day message count for the limit.
- The API receives the messages alone: never the person's name, e-mail,
  company or questionnaire. E-mails, phone numbers, CPF-like and other long
  digit sequences, and the person's own name/e-mail words are removed first.
- Messages about self-harm get a fixed answer with the CVV, without calling
  the API.
- Nothing about the text is logged; logs carry ids, status codes and counts.
"""

import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from config import tips_calendar

from .models import AssistantUsage
from .services import first_name

logger = logging.getLogger("wellbeing.assistant")

MAX_TURNS = 12  # messages of history sent to the API (user + assistant)
MAX_CHARS = 1000  # per message
TIMEOUT_SECONDS = 30
REMOVED = "[removido]"

CRISIS_ANSWER = (
    "Sinto muito que você esteja passando por isso. Você não precisa enfrentar "
    "sozinho. Converse agora com o CVV: ligue 188, 24 horas, gratuito, ou acesse "
    "cvv.org.br. Se houver risco imediato, ligue 192 (SAMU) ou procure o pronto-"
    "socorro mais próximo. Se puder, chame também alguém de confiança."
)
# Compared in casefold with accents stripped.
CRISIS_PATTERNS = (
    r"\bsuicid",
    r"\bme matar\b",
    r"\bmatar me\b",
    r"\btirar (a )?minha (propria )?vida\b",
    r"\bnao quero (mais )?viver\b",
    r"\bquero morrer\b",
    r"\bme (machucar|ferir)\b",
    r"\bautolesao\b",
    r"\bacabar com (a minha vida|tudo)\b",
)
ACCENTS = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# Phone numbers, CPF/CNPJ and any other run of 8+ digits (with separators).
LONG_NUMBER = re.compile(r"\+?\d[\d .()/-]{6,}\d")

SYSTEM_PROMPT = """Você é o Assistente Quality, da plataforma Quality Life de qualidade de vida no trabalho.
Responda em português do Brasil, em até 120 palavras, com tom acolhedor e prático.
Escreva em texto simples, sem Markdown: nada de asteriscos, cerquilhas ou tabelas. Se precisar de lista, comece cada item com "• ".
Ajude com: pausas, hidratação, postura, ergonomia, alongamentos leves, respiração, organização da rotina, convivência no trabalho e uso do app (Ginástica Laboral, Meditação, Relaxamento, Lembretes, Meu Progresso, Exercícios e Aulas).
Não faça diagnóstico, não indique remédio, dose, dieta ou tratamento e não interprete exames. Para dor, sintoma ou dúvida de saúde, oriente procurar um profissional de saúde.
Se a pessoa falar em se machucar, em suicídio ou em crise, indique o CVV (ligue 188, 24 horas, gratuito) e, em emergência, o SAMU 192.
Não peça nem repita dados pessoais (nome, documento, e-mail, telefone, empresa). Você não tem acesso aos dados da pessoa nem às respostas do questionário.
Se perguntarem algo fora desses temas, diga com gentileza que você ajuda só com bem-estar no trabalho e com o app."""


class AssistantError(Exception):
    """The API could not answer; the view shows a generic message."""


def enabled_for(organization):
    return bool(
        settings.GROQ_API_KEY
        and organization is not None
        and organization.slug in settings.ASSISTANT_ORGANIZATIONS
    )


def _normalize(text):
    return text.casefold().translate(ACCENTS)


def is_crisis(text):
    normalized = re.sub(r"[^\w\s]", " ", _normalize(text))
    return any(re.search(pattern, normalized) for pattern in CRISIS_PATTERNS)


def personal_words(membership):
    """Words that would identify this person: name and e-mail parts (≥ 3 letters)."""
    words = set()
    email = membership.user.email
    for token in re.split(r"[@._+-]", email.split("@")[0]):
        if len(token) >= 3:
            words.add(token)
    name = first_name(membership.user, membership.organization)
    if len(name) >= 3:
        words.add(name)
    return words


def scrub(text, words=()):
    """Remove e-mails, long numbers and the person's own name/e-mail words."""
    text = EMAIL.sub(REMOVED, text)
    text = LONG_NUMBER.sub(REMOVED, text)
    for word in sorted(words, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(word)}\b", REMOVED, text, flags=re.IGNORECASE)
    return text


def clean_history(raw):
    """Validated [{role, content}] (last message from the user), or None."""
    if not isinstance(raw, list) or not raw:
        return None
    history = []
    for item in raw[-MAX_TURNS:]:
        if not isinstance(item, dict):
            return None
        role, content = item.get("role"), item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            return None
        content = content.strip()
        if not content or len(content) > MAX_CHARS:
            return None
        history.append({"role": role, "content": content})
    if history[-1]["role"] != "user":
        return None
    return history


def take_slot(membership, today):
    """Count one message for today; False when the daily limit is reached."""
    with transaction.atomic():
        usage, _ = AssistantUsage.objects.select_for_update().get_or_create(
            membership=membership, day=today
        )
        if usage.messages >= settings.ASSISTANT_DAILY_LIMIT:
            return False
        AssistantUsage.objects.filter(pk=usage.pk).update(messages=F("messages") + 1)
    return True


def _context_line(today):
    tip = tips_calendar.tip_to_show(today)
    line = f"Data de hoje: {today:%d/%m/%Y}."
    if tip is not None:
        line += f" {tip.label} na plataforma: {tip.title}. {tip.text}"
    return line


def ask(history, membership, *, today=None):
    """The assistant's answer to ``history`` (already cleaned)."""
    today = today or timezone.localdate()
    words = personal_words(membership)
    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n{_context_line(today)}"},
        *(
            {"role": item["role"], "content": scrub(item["content"], words)}
            for item in history
        ),
    ]
    body = json.dumps(
        {
            "model": settings.ASSISTANT_MODEL,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 1200,
        }
    ).encode()
    request = urllib.request.Request(
        settings.ASSISTANT_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Some API front doors refuse the default "Python-urllib" agent.
            "User-Agent": "QualityLife/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        logger.warning(
            "assistant api status=%s membership=%s", error.code, membership.pk
        )
        raise AssistantError from error
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        logger.warning("assistant api unreachable membership=%s", membership.pk)
        raise AssistantError from error
    try:
        answer = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        logger.warning("assistant api malformed membership=%s", membership.pk)
        raise AssistantError from error
    if not answer:
        raise AssistantError
    logger.info("assistant answered membership=%s", membership.pk)
    return answer
