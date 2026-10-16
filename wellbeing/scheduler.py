"""In-process scheduler for break reminders (docs/specs/13-pwa-lembretes.md).

Started only by ``config/wsgi.py`` (``start_in_background``), so it lives in
the gunicorn workers and never in ``manage.py`` commands, migrations or
tests. Slots are computed in ``settings.TIME_ZONE`` with the same rules as
``reminders.js`` (start + k × interval strictly between start and end; a
shift that crosses midnight belongs to the day it starts).

The production database (Neon Free) suspends after 5 idle minutes and has a
monthly compute quota, so the scheduler only touches it when there is work:
on start and every ``REFRESH`` it loads the active reminders once and keeps
their upcoming slots in memory (``Plan``); it sleeps until the earliest of
the next slot and the next refresh; at a slot it reloads only that slot's
reminders, checks them again with ``due_slot`` and sends. Between those
moments it runs no query at all.

Saving or deactivating reminders and adding or removing a device call
``wake()``: that worker reloads its plan at once. The other worker keeps its
old plan until its next refresh; that is safe because every send is checked
against the database first, and the worker that took the change covers the
new slots.

Two workers reach the same slot: ``ReminderDispatch`` is unique per
(setting, slot), so the second insert fails and that worker skips it. A slot
more than five minutes old is never sent.
"""

import logging
import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, close_old_connections, connection, transaction
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
# After a failed step (database unreachable, quota exhausted) try again soon
# enough that a slot still fits in LATE.
RETRY_SECONDS = 120
# Wake a second after the slot so it is already in the past.
SLACK_SECONDS = 1

_lock = threading.Lock()
_thread = None
_stop = threading.Event()
# Set by wake() (and by stop) to cut the current sleep short.
_wake = threading.Event()


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


def refresh_interval():
    return timedelta(minutes=settings.WEB_PUSH_SCHEDULER_REFRESH_MINUTES)


def upcoming_slots(setting, after, until):
    """Slots of ``setting`` in ``[after, until]``, oldest first."""
    first = after.astimezone(_local_zone()).date() - timedelta(days=1)
    last = until.astimezone(_local_zone()).date()
    slots = []
    day = first
    while day <= last:
        slots.extend(slot for slot in slots_on(setting, day) if after <= slot <= until)
        day += timedelta(days=1)
    return slots


def _candidates():
    return ReminderSetting.objects.filter(
        active=True,
        membership__is_active=True,
        membership__organization__is_active=True,
        membership__push_subscriptions__isnull=False,
    ).distinct()


def _claim(setting, slot):
    try:
        with transaction.atomic():
            ReminderDispatch.objects.create(setting=setting, slot_at=slot)
    except IntegrityError:
        return False
    return True


class Plan:
    """The upcoming slots of one worker, kept in memory between refreshes."""

    def __init__(self, refresh=None):
        self.refresh = refresh or refresh_interval()
        self.refresh_at = None  # None: load on the next step
        self.slots = {}  # slot -> ids of the settings due at it
        self.handled = None  # latest slot already handled by this plan

    def invalidate(self):
        self.refresh_at = None

    def wake_at(self, now):
        """When the next step has something to do."""
        if self.refresh_at is None:
            return now
        return min([self.refresh_at, *self.slots])

    def step(self, now):
        """Do what is due at ``now``; returns how many reminders were sent."""
        if self.refresh_at is None or now >= self.refresh_at:
            self._load(now)
        dispatched = 0
        for slot in sorted(slot for slot in self.slots if slot <= now):
            ids = self.slots.pop(slot)
            # Too late to send: skip without touching the database.
            if now - slot <= LATE:
                dispatched += _dispatch(slot, ids, now)
            self.handled = slot if self.handled is None else max(self.handled, slot)
        return dispatched

    def _load(self, now):
        after = now - LATE
        until = now + self.refresh
        slots = {}
        for setting in _candidates().only(
            "id", "interval_minutes", "workday_start", "workday_end", "weekdays"
        ):
            for slot in upcoming_slots(setting, after, until):
                if self.handled is None or slot > self.handled:
                    slots.setdefault(slot, set()).add(setting.pk)
        ReminderDispatch.objects.filter(slot_at__lt=now - KEEP_DISPATCHES).delete()
        self.slots = slots
        self.refresh_at = until


def _dispatch(slot, ids, now):
    """Send ``slot`` to the settings in ``ids`` that still have it due."""
    candidates = _candidates().filter(pk__in=ids)
    dispatched = devices = 0
    url = reverse("wellbeing_gym")
    for setting in candidates.select_related(
        "membership__organization", "membership__user"
    ):
        # Changed or deactivated since the plan was loaded: not sent.
        if due_slot(setting, now) != slot or not _claim(setting, slot):
            continue
        dispatched += 1
        devices += notify(
            setting.membership, NotificationCategory.BREAKS, TITLE, BODY, url, now=now
        )
    if dispatched:
        logger.info("reminder slot dispatched=%s devices=%s", dispatched, devices)
    return dispatched


def run_once(now=None):
    """Send every reminder due at ``now`` once. Returns how many were sent."""
    return Plan().step(now or timezone.now())


def wake():
    """Make this process's scheduler reload its plan now (spec 13)."""
    _wake.set()


def tick(plan, now):
    """One iteration of the loop; returns the seconds to sleep afterwards."""
    if _wake.is_set():
        _wake.clear()
        plan.invalidate()
    try:
        plan.step(now)
    except Exception:
        logger.exception("reminder scheduler step failed")
        plan.invalidate()
        return RETRY_SECONDS
    seconds = (plan.wake_at(now) - now).total_seconds()
    return max(seconds, 0) + SLACK_SECONDS


def _loop(plan):
    while not _stop.is_set():
        try:
            close_old_connections()
            seconds = tick(plan, timezone.now())
        finally:
            # Never keep a connection open while sleeping, so nothing here
            # keeps the Neon compute awake.
            connection.close()
        _wake.wait(seconds)


def start_in_background(refresh=None):
    """Start the daemon thread once per process; None when push is off."""
    global _thread
    if not (push_configured() and settings.WEB_PUSH_SCHEDULER):
        return None
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        _stop.clear()
        _wake.clear()
        _thread = threading.Thread(
            target=_loop,
            args=(Plan(refresh),),
            name="ql-reminder-scheduler",
            daemon=True,
        )
        _thread.start()
        logger.info("reminder scheduler started")
        return _thread


def stop_in_background():
    global _thread
    _stop.set()
    _wake.set()
    with _lock:
        thread, _thread = _thread, None
    if thread is not None:
        thread.join(5)


def running_thread():
    return _thread if _thread is not None and _thread.is_alive() else None
