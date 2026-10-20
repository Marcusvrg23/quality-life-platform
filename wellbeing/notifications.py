"""General notification channel (docs/specs/13-pwa-lembretes.md).

``notify()`` is the only door to Web Push: break reminders use it today and
the future assistant's tips and special dates will use ``category="dicas"``.
Nothing else in the code base calls ``pywebpush``.

Every text may show up on a locked screen, so it must stay generic: never a
name, a score, a pillar, an answer or any other health data. Logs carry ids
and counts only.
"""

import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import (
    NotificationCategory,
    NotificationDelivery,
    NotificationPreference,
    PushSubscription,
)
from .services import first_name

logger = logging.getLogger("wellbeing.notifications")

# Sends per person per local day; a category absent here has no daily cap.
# Break reminders and tips are both paced by the person's own interval.
DAILY_LIMITS = {}
# The push service drops a message not delivered within this time: a reminder
# that arrives an hour late is noise, not a reminder.
TTL_SECONDS = 10 * 60
# The subscription no longer exists at the push service.
EXPIRED_STATUSES = {404, 410}
# Words that only appear next to someone's result; a generic text never needs
# them (compared in casefold, accents stripped).
RESULT_WORDS = (
    "nota",
    "pontuacao",
    "score",
    "pilar",
    "pilares",
    "resposta",
    "respostas",
    "diagnostico",
    "avaliacao",
    "resultado",
    "resultados",
)
ACCENTS = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")


class NotGeneric(ValueError):
    """The text names the person or talks about a result."""


def push_configured():
    return bool(
        settings.VAPID_PUBLIC_KEY
        and settings.VAPID_PRIVATE_KEY
        and settings.VAPID_SUBJECT
    )


def _normalize(text):
    return text.casefold().translate(ACCENTS)


def _words(text):
    return {
        word.strip(".,;:!?()\"'") for word in _normalize(text).replace("-", " ").split()
    }


def ensure_generic(text, membership):
    """Refuse a text that could identify the person or describe a result."""
    normalized = _normalize(text)
    words = _words(text)
    email = _normalize(membership.user.email)
    if email in normalized:
        raise NotGeneric("The notification text contains the person's e-mail.")
    local_part = email.split("@")[0]
    for token in local_part.replace("_", ".").replace("-", ".").split("."):
        if len(token) >= 3 and token in words:
            raise NotGeneric("The notification text names the person.")
    name = _normalize(first_name(membership.user, membership.organization))
    if len(name) >= 3 and name in words:
        raise NotGeneric("The notification text names the person.")
    if words & set(RESULT_WORDS):
        raise NotGeneric("The notification text talks about a result.")


def preference_for(membership):
    return NotificationPreference.objects.filter(
        membership=membership
    ).first() or NotificationPreference(membership=membership)


def _local_day_start(moment):
    zone = ZoneInfo(settings.TIME_ZONE)
    local = moment.astimezone(zone)
    return datetime.combine(local.date(), time.min, tzinfo=zone)


def _over_daily_limit(membership, category, now):
    limit = DAILY_LIMITS.get(category)
    if limit is None:
        return False
    sent_today = NotificationDelivery.objects.filter(
        membership=membership,
        category=category,
        sent_at__gte=_local_day_start(now),
        sent_at__lt=_local_day_start(now) + timedelta(days=1),
    ).count()
    return sent_today >= limit


def _send(subscription, payload, now):
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=TTL_SECONDS,
            timeout=10,
        )
    except WebPushException as error:
        status = error.status_code
        if status in EXPIRED_STATUSES:
            subscription.delete()
            logger.info(
                "push subscription expired id=%s status=%s", subscription.pk, status
            )
        else:
            logger.warning("push failed id=%s status=%s", subscription.pk, status)
        return False
    except OSError:
        # requests' network errors are OSError subclasses.
        logger.warning("push unreachable id=%s", subscription.pk)
        return False
    PushSubscription.objects.filter(pk=subscription.pk).update(last_success_at=now)
    return True


def notify(membership, category, title, body, url, *, now=None):
    """Send one generic notification to every device of ``membership``.

    Returns how many devices received it. Sends nothing without the VAPID
    keys, for an inactive Membership or organization, for a category the
    person turned off, or past the category's daily limit.
    """
    if category not in NotificationCategory.values:
        raise ValueError(f"Unknown notification category: {category!r}")
    if not url.startswith("/") or url.startswith("//"):
        raise ValueError("The notification URL must be a same-origin path.")
    ensure_generic(title, membership)
    ensure_generic(body, membership)
    if not push_configured():
        return 0
    if not (membership.is_active and membership.organization.is_active):
        logger.info("notify skipped inactive membership=%s", membership.pk)
        return 0
    if not preference_for(membership).allows(category):
        return 0
    now = now or timezone.now()
    if _over_daily_limit(membership, category, now):
        logger.info(
            "notify over daily limit category=%s membership=%s",
            category,
            membership.pk,
        )
        return 0
    payload = json.dumps(
        {"title": title, "body": body, "url": url, "tag": f"ql-{category}"},
        ensure_ascii=False,
    )
    sent = 0
    for subscription in PushSubscription.objects.filter(membership=membership):
        if _send(subscription, payload, now):
            sent += 1
    if sent:
        NotificationDelivery.objects.create(
            membership=membership, category=category, devices=sent, sent_at=now
        )
    logger.info(
        "notify category=%s membership=%s devices=%s", category, membership.pk, sent
    )
    return sent
