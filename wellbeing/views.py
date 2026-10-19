"""Wellbeing pages, the owner-only practice record, break reminders and the
push subscriptions of the caller's own devices."""

import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from config import tips_calendar
from config import wellbeing_catalog as catalog
from config.exercises import EXERCISES, SOURCE, image_path, poster_path
from config.tenant import resolve_tenant_context
from identity.models import Membership

from . import scheduler
from .forms import WEEKDAYS, ReminderForm
from .models import (
    MIN_RECORD_SECONDS,
    REMINDER_INTERVALS,
    ActivitySession,
    NotificationCategory,
    NotificationPreference,
    PushSubscription,
    ReminderSetting,
)
from .notifications import notify, preference_for, push_configured
from .services import personal_progress

# Two records of the same person may not overlap in time (a resent or
# duplicated request would otherwise count the same minutes twice).
OVERLAP_TOLERANCE = timedelta(seconds=5)


def _tenant(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        raise PermissionDenied("Organization unavailable.")
    return tenant


def _static(path):
    return static(path) if path else None


def _step(exercise, seconds):
    return {
        "slug": exercise["slug"],
        "seconds": seconds,
        "title": exercise["title"],
        "category": exercise["category"],
        "text": exercise["instruction"],
        "video": _static(exercise.get("video")),
        "poster": _static(poster_path(exercise)),
        "image": _static(image_path(exercise)),
    }


def _noises():
    return [
        item
        for item in catalog.SOUNDS
        if item["type"] == "noise" and item["status"] == catalog.AVAILABLE
    ]


@login_required
@require_GET
def gym(request):
    tenant = _tenant(request)
    exercises = {item["slug"]: item for item in EXERCISES}
    sessions = [
        {
            "kind": session["kind"],
            "slug": session["slug"],
            "title": session["title"],
            "label": f"{session['minutes']} min",
            "duration": session["duration_seconds"],
            "breathing": None,
            "steps": [
                _step(exercises[slug], catalog.SECONDS_PER_EXERCISE)
                for slug in session["steps"]
            ],
        }
        for session in catalog.GYM_SESSIONS
    ]
    categories = [
        {
            **category,
            "exercises": [exercises[slug] for slug in category["exercises"]],
            "chair_exercise": (
                exercises[next(iter(category["chair"].values()))]
                if category["chair"]
                else None
            ),
            "sessions": [
                session
                for session in catalog.GYM_SESSIONS
                if session["category_slug"] == category["slug"]
            ],
        }
        for category in catalog.GYM_CATEGORIES
    ]
    return render(
        request,
        "wellbeing/gym.html",
        {
            "tenant": tenant,
            "categories": categories,
            "sessions": sessions,
            "noises": _noises(),
            "default_noise": "music",
            "catalog": catalog,
            "source": SOURCE,
        },
    )


@login_required
@require_GET
def meditation(request):
    tenant = _tenant(request)
    breathing = {
        "inhale": catalog.BREATH_IN_SECONDS,
        "exhale": catalog.BREATH_OUT_SECONDS,
    }
    sessions = [
        {
            "kind": item["kind"],
            "slug": item["slug"],
            "title": item["title"],
            "label": f"{item['duration_seconds'] // 60} min",
            "duration": item["duration_seconds"],
            "breathing": breathing,
            "steps": [
                {
                    "slug": item["slug"],
                    "seconds": item["duration_seconds"],
                    "title": item["title"],
                    "category": item["category"],
                    "text": "",
                    "video": _static(item["file"]),
                    "poster": _static(item["file"].removesuffix(".mp4") + ".webp"),
                    "image": None,
                }
            ],
        }
        for item in catalog.MEDITATIONS
        if item["status"] == catalog.AVAILABLE
    ]
    return render(
        request,
        "wellbeing/meditation.html",
        {
            "tenant": tenant,
            "meditations": sessions,
            "sessions": sessions,
            "noises": _noises(),
            "default_noise": "forest",
            "catalog": catalog,
        },
    )


@login_required
@require_GET
def relax(request):
    tenant = _tenant(request)
    return render(
        request,
        "wellbeing/relax.html",
        {
            "tenant": tenant,
            "sounds": catalog.SOUNDS,
            "timers": catalog.RELAX_TIMER_MINUTES,
            "default_timer": 15,
            "background": catalog.RELAX_BACKGROUND,
            "background_poster": catalog.RELAX_BACKGROUND.removesuffix(".mp4")
            + ".webp",
            "catalog": catalog,
        },
    )


@login_required
@require_GET
def progress(request):
    tenant = _tenant(request)
    return render(
        request,
        "wellbeing/progress.html",
        {
            "tenant": tenant,
            "progress": personal_progress(request.user, tenant.organization),
        },
    )


@login_required
@require_POST
def record(request):
    """Store one finished (or 60 s+) practice for the caller and active tenant.

    Only kind, slug, duration and completion come from the client; user,
    organization and start time come from the server.
    """
    tenant = _tenant(request)
    item = catalog.find_available(
        request.POST.get("kind", ""), request.POST.get("slug", "")
    )
    if item is None:
        raise Http404("Practice unavailable.")
    try:
        seconds = int(request.POST.get("duration_seconds", ""))
    except ValueError:
        return JsonResponse({"error": "duration"}, status=400)
    if seconds < MIN_RECORD_SECONDS:
        return JsonResponse({"error": "duration"}, status=400)
    seconds = min(seconds, catalog.max_seconds(item))
    now = timezone.now()
    started_at = now - timedelta(seconds=seconds)
    with transaction.atomic():
        # Serialize records of this person in this organization.
        Membership.objects.select_for_update().get(pk=tenant.membership.pk)
        last = (
            ActivitySession.objects.filter(
                user=request.user, organization=tenant.organization
            )
            .order_by("-started_at")
            .first()
        )
        if last and (
            last.started_at + timedelta(seconds=last.duration_seconds)
            > started_at + OVERLAP_TOLERANCE
        ):
            return JsonResponse({"error": "overlap"}, status=409)
        ActivitySession.objects.create(
            user=request.user,
            organization=tenant.organization,
            kind=item["kind"],
            slug=item["slug"],
            started_at=started_at,
            duration_seconds=seconds,
            completed=request.POST.get("completed") == "1",
        )
    # Minutes as counted in "Meu Progresso", for the "Prática registrada" notice.
    return JsonResponse({"ok": True, "minutes": seconds // 60}, status=201)


def _reminder_setting(membership):
    return ReminderSetting.objects.filter(membership=membership).first() or (
        ReminderSetting(membership=membership)
    )


@login_required
@require_http_methods(["GET", "POST"])
def reminders(request):
    """The caller's own break reminders in the active tenant (spec 13).

    The Membership always comes from ``resolve_tenant_context``; nothing in
    the request can point to someone else's reminders.
    """
    tenant = _tenant(request)
    if request.method == "POST" and request.POST.get("action") == "deactivate":
        # Its own form: never blocked by whatever the time fields hold.
        ReminderSetting.objects.filter(membership=tenant.membership).update(
            active=False, updated_at=timezone.now()
        )
        transaction.on_commit(scheduler.wake)
        messages.success(request, "Lembretes desativados.")
        return redirect("wellbeing_reminders")
    setting = _reminder_setting(tenant.membership)
    form = ReminderForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                Membership.objects.select_for_update().get(pk=tenant.membership.pk)
                setting, _ = ReminderSetting.objects.get_or_create(
                    membership=tenant.membership
                )
                if data["action"] == "activate":
                    setting.active = True
                setting.interval_minutes = data["interval_minutes"]
                setting.workday_start = data["workday_start"]
                setting.workday_end = data["workday_end"]
                setting.weekdays = form.weekday_digits()
                setting.save()
                # This worker's scheduler reloads at once (spec 13).
                transaction.on_commit(scheduler.wake)
            messages.success(
                request,
                "Lembretes ativados."
                if data["action"] == "activate"
                else "Alterações salvas.",
            )
            return redirect("wellbeing_reminders")
        current = {
            "interval": request.POST.get("interval_minutes", ""),
            "start": request.POST.get("workday_start", ""),
            "end": request.POST.get("workday_end", ""),
            "days": request.POST.getlist("weekdays"),
        }
    else:
        current = {
            "interval": str(setting.interval_minutes),
            "start": setting.workday_start.strftime("%H:%M"),
            "end": setting.workday_end.strftime("%H:%M"),
            "days": list(setting.weekdays),
        }
    return render(
        request,
        "wellbeing/reminders.html",
        {
            "tenant": tenant,
            "setting": setting,
            "form": form,
            "error": form.first_error() if form.errors else "",
            "current": current,
            "intervals": [str(minutes) for minutes in REMINDER_INTERVALS],
            "weekdays": WEEKDAYS,
            "preference": preference_for(tenant.membership),
            "categories": NotificationCategory.choices,
            "tips_published": tips_calendar.PUBLISHED,
        },
        status=400 if form.is_bound else 200,
    )


@login_required
@require_POST
def notification_preferences(request):
    """The caller's own category switches; a missing checkbox means off."""
    tenant = _tenant(request)
    with transaction.atomic():
        Membership.objects.select_for_update().get(pk=tenant.membership.pk)
        NotificationPreference.objects.update_or_create(
            membership=tenant.membership,
            defaults={
                category: category in request.POST
                for category in NotificationCategory.values
            },
        )
    messages.success(request, "Preferências salvas.")
    return redirect("wellbeing_reminders")


@login_required
@require_GET
def reminder_schedule(request):
    """The caller's own agenda, read by reminders.js on every app page."""
    tenant = _tenant(request)
    setting = _reminder_setting(tenant.membership)
    response = JsonResponse(
        {
            "active": setting.active,
            "interval": setting.interval_minutes,
            "start": setting.workday_start.strftime("%H:%M"),
            "end": setting.workday_end.strftime("%H:%M"),
            "days": [int(day) for day in setting.weekdays],
            # The VAPID public key is what PushManager.subscribe needs; null
            # means the server cannot push and the in-page notice stays.
            "push_key": settings.VAPID_PUBLIC_KEY or None,
        }
    )
    response["Cache-Control"] = "no-store, private"
    return response


# Push subscriptions ----------------------------------------------------------

ENDPOINT_MAX = PushSubscription._meta.get_field("endpoint").max_length
P256DH_MAX = PushSubscription._meta.get_field("p256dh").max_length
AUTH_MAX = PushSubscription._meta.get_field("auth").max_length
USER_AGENT_MAX = PushSubscription._meta.get_field("user_agent").max_length
_https_only = URLValidator(schemes=["https"])


def _json_body(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _endpoint(body):
    endpoint = body.get("endpoint") if body else None
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > ENDPOINT_MAX:
        return None
    try:
        _https_only(endpoint)
    except ValidationError:
        return None
    return endpoint


def _key(keys, name, limit):
    value = keys.get(name) if isinstance(keys, dict) else None
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    return value


def _json(payload, status=200):
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store, private"
    return response


@login_required
@require_POST
def push_subscribe(request):
    """Save this device's push subscription on the caller's own Membership.

    The endpoint identifies the device: a device that signs in as someone
    else (or in another company) moves to that Membership. The client never
    chooses the Membership.
    """
    tenant = _tenant(request)
    body = _json_body(request)
    endpoint = _endpoint(body)
    keys = body.get("keys") if body else None
    p256dh = _key(keys, "p256dh", P256DH_MAX)
    auth = _key(keys, "auth", AUTH_MAX)
    if not (endpoint and p256dh and auth):
        return HttpResponseBadRequest("Invalid push subscription.")
    _, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "membership": tenant.membership,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_MAX],
        },
    )
    transaction.on_commit(scheduler.wake)
    return _json({"status": "subscribed"}, status=201 if created else 200)


@login_required
@require_POST
def push_unsubscribe(request):
    """Forget this device; only a subscription of the caller's own Membership."""
    tenant = _tenant(request)
    body = _json_body(request)
    endpoint = body.get("endpoint") if body else None
    if not isinstance(endpoint, str) or not endpoint:
        return HttpResponseBadRequest("Invalid push subscription.")
    removed, _ = PushSubscription.objects.filter(
        membership=tenant.membership, endpoint=endpoint
    ).delete()
    if not removed:
        raise Http404("No such subscription for this account.")
    transaction.on_commit(scheduler.wake)
    return _json({"status": "unsubscribed"})


PUSH_TEST_TITLE = "Teste da Quality Life"
PUSH_TEST_BODY = "Se você está vendo isto, as notificações estão funcionando."
# One test per person per minute (per worker): enough to try again, not to spam.
PUSH_TEST_COOLDOWN_SECONDS = 60


@login_required
@require_POST
def push_test(request):
    """Send one test notification now to the caller's own devices (spec 13)."""
    tenant = _tenant(request)
    membership = tenant.membership
    if not push_configured():
        messages.info(
            request,
            "Este servidor ainda não envia notificações com o app fechado. "
            "O aviso aparece só com o app aberto.",
        )
        return redirect("wellbeing_reminders")
    if not PushSubscription.objects.filter(membership=membership).exists():
        messages.info(
            request,
            "Nenhum aparelho recebendo notificações nesta conta. Toque em "
            "Ativar lembretes (ou em Permitir notificações neste aparelho) e "
            "aceite as notificações; depois envie o teste. Cada aparelho recebe "
            "as notificações de uma conta só: a última que ativou nele.",
        )
        return redirect("wellbeing_reminders")
    if not cache.add(f"ql:push-test:{membership.pk}", True, PUSH_TEST_COOLDOWN_SECONDS):
        messages.info(request, "Teste enviado há pouco. Aguarde um minuto.")
        return redirect("wellbeing_reminders")
    sent = notify(
        membership,
        NotificationCategory.BREAKS,
        PUSH_TEST_TITLE,
        PUSH_TEST_BODY,
        reverse("wellbeing_reminders"),
    )
    if sent:
        aparelhos = "aparelho" if sent == 1 else "aparelhos"
        messages.success(
            request,
            f"Notificação de teste enviada para {sent} {aparelhos}. "
            "Pode levar alguns segundos para chegar.",
        )
    else:
        messages.info(
            request,
            "A notificação não foi entregue. Confira se Lembretes de pausa está "
            "marcado e ative os lembretes de novo neste aparelho.",
        )
    return redirect("wellbeing_reminders")
