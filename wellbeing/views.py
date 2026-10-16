"""Wellbeing pages and the owner-only practice record."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from config import wellbeing_catalog as catalog
from config.exercises import EXERCISES, SOURCE, image_path, poster_path
from config.tenant import resolve_tenant_context
from identity.models import Membership

from .forms import WEEKDAYS, ReminderForm
from .models import (
    MIN_RECORD_SECONDS,
    REMINDER_INTERVALS,
    ActivitySession,
    ReminderSetting,
)
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
    return JsonResponse({"ok": True}, status=201)


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
                if data["action"] != "save":
                    setting.active = data["action"] == "activate"
                setting.interval_minutes = data["interval_minutes"]
                setting.workday_start = data["workday_start"]
                setting.workday_end = data["workday_end"]
                setting.weekdays = form.weekday_digits()
                setting.save()
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
            "current": current,
            "intervals": [str(minutes) for minutes in REMINDER_INTERVALS],
            "weekdays": WEEKDAYS,
        },
        status=400 if form.is_bound else 200,
    )


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
        }
    )
    response["Cache-Control"] = "no-store, private"
    return response
