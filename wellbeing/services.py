"""Progress from practice records, always in the product time zone.

Rules (docs/specs/11-bem-estar.md):
- A practice belongs to the local day (America/Sao_Paulo) in which it started.
- Streak ("dias seguidos"): consecutive local days with at least one practice,
  ending today; while today has no practice yet, yesterday's streak still
  counts. It drops to 0 when a whole local day passes without practice.
- Week = Monday to Sunday; month = calendar month; both local.
- Minutes are the summed seconds divided by 60, rounded down.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from assessments.models import Assessment
from assessments.services import collaborator_name

from .models import ActivitySession

LOCAL_TZ = ZoneInfo(settings.TIME_ZONE)

# Trophy rules. "best_streak" uses the longest streak ever, so a trophy is not
# lost when a streak breaks; "total_minutes" counts every recorded practice.
TROPHIES = (
    {
        "slug": "primeira-pratica",
        "title": "Primeira prática",
        "rule": "Registrar a primeira prática.",
        "metric": "sessions",
        "target": 1,
    },
    {
        "slug": "sequencia-3",
        "title": "3 dias seguidos",
        "rule": "Praticar em 3 dias seguidos.",
        "metric": "best_streak",
        "target": 3,
    },
    {
        "slug": "sequencia-7",
        "title": "7 dias seguidos",
        "rule": "Praticar em 7 dias seguidos.",
        "metric": "best_streak",
        "target": 7,
    },
    {
        "slug": "sequencia-30",
        "title": "30 dias seguidos",
        "rule": "Praticar em 30 dias seguidos.",
        "metric": "best_streak",
        "target": 30,
    },
    {
        "slug": "60-minutos",
        "title": "60 minutos acumulados",
        "rule": "Somar 60 minutos de prática.",
        "metric": "total_minutes",
        "target": 60,
    },
)


def local_date(moment):
    return timezone.localtime(moment, LOCAL_TZ).date()


def _streak_ending(days, last_day):
    count = 0
    while last_day in days:
        count += 1
        last_day -= timedelta(days=1)
    return count


def _best_streak(days):
    best = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue  # not the first day of a run
        length = 0
        while day + timedelta(days=length) in days:
            length += 1
        best = max(best, length)
    return best


def personal_progress(user, organization, *, now=None):
    """Own progress of ``user`` inside ``organization`` only."""
    today = local_date(now or timezone.now())
    rows = [
        (local_date(started_at), seconds, kind)
        for started_at, seconds, kind in ActivitySession.objects.filter(
            user=user, organization=organization
        ).values_list("started_at", "duration_seconds", "kind")
    ]
    days = {day for day, _, _ in rows if day <= today}
    streak = _streak_ending(days, today) or _streak_ending(
        days, today - timedelta(days=1)
    )
    week_start = today - timedelta(days=today.weekday())
    week_seconds = sum(s for day, s, _ in rows if week_start <= day <= today)
    month_seconds = sum(
        s for day, s, _ in rows if (day.year, day.month) == (today.year, today.month)
    )
    total_seconds = sum(s for _, s, _ in rows)
    by_kind = [
        {
            "kind": kind,
            "label": label,
            "count": sum(1 for _, _, k in rows if k == kind),
            "minutes": sum(s for _, s, k in rows if k == kind) // 60,
        }
        for kind, label in ActivitySession.Kind.choices
    ]
    metrics = {
        "sessions": len(rows),
        "best_streak": _best_streak(days),
        "total_minutes": total_seconds // 60,
    }
    trophies = [
        {**trophy, "earned": metrics[trophy["metric"]] >= trophy["target"]}
        for trophy in TROPHIES
    ]
    return {
        "today": today,
        "streak": streak,
        "best_streak": metrics["best_streak"],
        "week_minutes": week_seconds // 60,
        "month_minutes": month_seconds // 60,
        "total_minutes": metrics["total_minutes"],
        "sessions": metrics["sessions"],
        "by_kind": by_kind,
        "trophies": trophies,
    }


def greeting(now=None):
    """Bom dia (5h-11h59), Boa tarde (12h-17h59) or Boa noite, local time."""
    hour = timezone.localtime(now or timezone.now(), LOCAL_TZ).hour
    if 5 <= hour < 12:
        return "Bom dia"
    if 12 <= hour < 18:
        return "Boa tarde"
    return "Boa noite"


def first_name(user, organization):
    """First word of the name typed in the user's own latest completed
    assessment in this organization; "" when there is none."""
    latest = (
        Assessment.objects.filter(
            user=user,
            organization=organization,
            status=Assessment.Status.COMPLETED,
        )
        .order_by("-completed_at", "-pk")
        .first()
    )
    if latest is None:
        return ""
    words = collaborator_name(latest).split()
    return words[0] if words else ""
