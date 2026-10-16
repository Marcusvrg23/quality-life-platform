"""In-process scheduler for break reminders (docs/specs/13-pwa-lembretes.md).

Started only by ``config/wsgi.py`` (``start_in_background``), so it lives in
the gunicorn workers and never in ``manage.py`` commands, migrations or
tests. Every minute each worker computes, in ``settings.TIME_ZONE``, the slots
of every active reminder with the same rules as ``reminders.js`` (start +
k × interval strictly between start and end; a shift that crosses midnight
belongs to the day it starts) and hands the due ones to ``notify()``.

Two workers wake up in the same minute: ``ReminderDispatch`` is unique per
(setting, slot), so the second insert fails and that worker skips the slot.
A slot more than five minutes old is never sent.
"""

import logging
import threading
import time as time_module
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.urls import reverse
from django.utils import timezone

from .models import NotificationCategory, ReminderDispatch, ReminderSetting
from .notifications import notify, push_configured

logger = logging.getLogger("wellbeing.scheduler")

TITLE = "Hora da pausa"
BODY = "Que tal alguns minutos de Ginástica Laboral?"
# Same tolerance as reminders.js: later than this the reminder is noise.
LATE = timedelta(minutes=5)
KEEP_DISPATCHES = timedelta(days=2)
TICK_SECONDS = 60

_lock = threading.Lock()
_thread = None
_stop = threading.Event()


def _local_zone():
    return ZoneInfo(settings.TIME_ZONE)


def _minutes(value):
    return value.hour * 60 + value.minute


def slots_on(setting, day):
    """Wall-clock slots of the shift that starts on ``day`` (a local date)."""
    if str(day.isoweekday()) not in setting.weekdays:
        return []
    start = _minutes(setting.workday_start)
    end = _minutes(setting.workday_end)
    if end <= start:
        end += 24 * 60
    midnight = datetime.combine(day, time.min)
    return [
        (midnight + timedelta(minutes=at)).replace(tzinfo=_local_zone())
        for at in range(start + setting.interval_minutes, end, setting.interval_minutes)
    ]


def due_slot(setting, now):
    """The slot due at ``now`` (started at most ``LATE`` ago), or None.

    Yesterday's shift may still be running past midnight, so both days are
    checked.
    """
    today = now.astimezone(_local_zone()).date()
    for day in (today - timedelta(days=1), today):
        for slot in slots_on(setting, day):
            if timedelta(0) <= now - slot <= LATE:
                return slot
    return None


def _claim(setting, slot):
    try:
        with transaction.atomic():
            ReminderDispatch.objects.create(setting=setting, slot_at=slot)
    except IntegrityError:
        return False
    return True


def run_once(now=None):
    """One tick: send every due reminder once. Returns how many were sent."""
    now = now or timezone.now()
    candidates = (
        ReminderSetting.objects.filter(
            active=True,
            membership__is_active=True,
            membership__organization__is_active=True,
            membership__push_subscriptions__isnull=False,
        )
        .select_related("membership__organization", "membership__user")
        .distinct()
    )
    dispatched = devices = 0
    url = reverse("wellbeing_gym")
    for setting in candidates:
        slot = due_slot(setting, now)
        if slot is None or not _claim(setting, slot):
            continue
        dispatched += 1
        devices += notify(
            setting.membership, NotificationCategory.BREAKS, TITLE, BODY, url, now=now
        )
    ReminderDispatch.objects.filter(slot_at__lt=now - KEEP_DISPATCHES).delete()
    if dispatched:
        logger.info("reminder tick dispatched=%s devices=%s", dispatched, devices)
    return dispatched


def _seconds_to_next_tick(tick_seconds):
    if tick_seconds < TICK_SECONDS:
        return tick_seconds
    # Wake a few seconds into the minute so the slot is already in the past.
    return tick_seconds - (time_module.time() % tick_seconds) + 2


def _loop(tick_seconds):
    while not _stop.wait(_seconds_to_next_tick(tick_seconds)):
        try:
            close_old_connections()
            run_once()
        except Exception:
            logger.exception("reminder tick failed")
        finally:
            close_old_connections()


def start_in_background(tick_seconds=TICK_SECONDS):
    """Start the daemon thread once per process; None when push is off."""
    global _thread
    if not (push_configured() and settings.WEB_PUSH_SCHEDULER):
        return None
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        _stop.clear()
        _thread = threading.Thread(
            target=_loop,
            args=(tick_seconds,),
            name="ql-reminder-scheduler",
            daemon=True,
        )
        _thread.start()
        logger.info("reminder scheduler started")
        return _thread


def stop_in_background():
    global _thread
    _stop.set()
    with _lock:
        thread, _thread = _thread, None
    if thread is not None:
        thread.join(5)


def running_thread():
    return _thread if _thread is not None and _thread.is_alive() else None
