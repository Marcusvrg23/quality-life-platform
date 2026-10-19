"""In-process reminder scheduler (docs/specs/13-pwa-lembretes.md, aceite 13 e 14):
slots in America/Sao_Paulo with a UTC clock, nothing outside the shift, on
unmarked days or for inactive reminders; night shifts; no duplicates across
workers; late slots skipped. pywebpush is simulated."""

import json
import threading
import time as time_module
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from identity.models import Membership, Organization, User
from wellbeing import notifications, scheduler
from wellbeing.models import PushSubscription, ReminderDispatch, ReminderSetting

PASSWORD = "scheduler-test-password"
VAPID = {
    "VAPID_PUBLIC_KEY": "public-key-for-the-test",
    "VAPID_PRIVATE_KEY": "private-key-for-the-test",
    "VAPID_SUBJECT": "mailto:contato@example.test",
}
NO_VAPID = {"VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": "", "VAPID_SUBJECT": ""}
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
# Monday 19/10/2026 (launch day); São Paulo is UTC-3 all year.
MONDAY = datetime(2026, 10, 19, tzinfo=SAO_PAULO)


def wait_for(condition, seconds=2):
    deadline = time_module.monotonic() + seconds
    while time_module.monotonic() < deadline:
        if condition():
            return True
        time_module.sleep(0.01)
    return condition()


def utc(local):
    """The same instant as the production clock sees it (UTC)."""
    return local.astimezone(dt_timezone.utc)


def make_member(email, organization, **setting):
    user = User.objects.create_user(email, PASSWORD)
    membership = Membership.objects.create(
        user=user, organization=organization, role=Membership.Role.COLLABORATOR
    )
    reminder = ReminderSetting.objects.create(
        membership=membership, active=True, **setting
    )
    PushSubscription.objects.create(
        membership=membership,
        endpoint=f"https://push.example.test/{membership.pk}",
        p256dh="p256dh",
        auth="auth",
    )
    return reminder


@override_settings(**VAPID)
class SchedulerTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.setting = make_member("dono@empresa.test", self.organization)

    def run_once(self, local, **kwargs):
        with mock.patch.object(notifications, "webpush") as webpush:
            webpush.side_effect = kwargs.pop("side_effect", None)
            dispatched = scheduler.run_once(now=utc(local))
        return dispatched, webpush

    def at(self, day_offset=0, hour=0, minute=0, second=5):
        return MONDAY + timedelta(
            days=day_offset, hours=hour, minutes=minute, seconds=second
        )

    # Right time, local zone, UTC clock -------------------------------------------

    def test_sends_at_the_local_slot_with_a_utc_clock(self):
        # 09:00 in São Paulo is 12:00 UTC: the first slot of 08:00-18:00 / 60 min.
        dispatched, webpush = self.run_once(self.at(hour=9))
        self.assertEqual(dispatched, 1)
        webpush.assert_called_once()
        call = webpush.call_args
        self.assertEqual(
            call.kwargs["subscription_info"]["endpoint"],
            f"https://push.example.test/{self.setting.membership_id}",
        )
        payload = json.loads(call.kwargs["data"])
        self.assertEqual(payload["title"], "Hora da pausa")
        self.assertEqual(
            payload["body"], "Que tal alguns minutos de Ginástica Laboral?"
        )
        self.assertEqual(payload["url"], "/app/ginastica/")
        dispatch = ReminderDispatch.objects.get()
        self.assertEqual(dispatch.setting, self.setting)
        self.assertEqual(dispatch.slot_at, MONDAY + timedelta(hours=9))
        # 17:00 is the last slot; 08:00 (start) and 18:00 (end) are not slots.
        self.assertEqual(self.run_once(self.at(hour=17))[0], 1)
        self.assertEqual(self.run_once(self.at(hour=8))[0], 0)
        self.assertEqual(self.run_once(self.at(hour=18))[0], 0)
        # Between slots nothing happens either.
        self.assertEqual(self.run_once(self.at(hour=9, minute=30))[0], 0)

    def test_interval_defines_the_slots(self):
        ReminderSetting.objects.filter(pk=self.setting.pk).update(interval_minutes=90)
        for hour, minute, expected in ((9, 0, 0), (9, 30, 1), (11, 0, 1), (17, 0, 1)):
            with self.subTest(hour=hour, minute=minute):
                ReminderDispatch.objects.all().delete()
                self.assertEqual(
                    self.run_once(self.at(hour=hour, minute=minute))[0], expected
                )

    def test_nothing_outside_the_shift_on_unmarked_days_or_inactive(self):
        saturday = self.at(day_offset=5, hour=9)
        self.assertEqual(self.run_once(saturday)[0], 0)
        ReminderSetting.objects.filter(pk=self.setting.pk).update(active=False)
        self.assertEqual(self.run_once(self.at(hour=9))[0], 0)
        ReminderSetting.objects.filter(pk=self.setting.pk).update(active=True)
        Membership.objects.filter(pk=self.setting.membership_id).update(is_active=False)
        self.assertEqual(self.run_once(self.at(hour=9))[0], 0)
        Membership.objects.filter(pk=self.setting.membership_id).update(is_active=True)
        Organization.objects.filter(pk=self.organization.pk).update(is_active=False)
        self.assertEqual(self.run_once(self.at(hour=9))[0], 0)
        Organization.objects.filter(pk=self.organization.pk).update(is_active=True)
        PushSubscription.objects.all().delete()
        # No device: nothing to send and no dispatch row either.
        self.assertEqual(self.run_once(self.at(hour=9))[0], 0)
        self.assertFalse(ReminderDispatch.objects.exists())

    def test_night_shift_belongs_to_the_day_it_starts(self):
        ReminderSetting.objects.filter(pk=self.setting.pk).update(
            workday_start=time(22), workday_end=time(6), weekdays="1"
        )
        for day_offset, hour, expected in (
            (0, 0, 0),  # Monday 00:00 is Sunday's shift: not marked.
            (0, 22, 0),  # the start itself is not a slot
            (0, 23, 1),  # Monday 23:00
            (1, 0, 1),  # Tuesday 00:00 (03:00 UTC)
            (1, 5, 1),  # Tuesday 05:00, the last slot
            (1, 6, 0),  # the end is not a slot
            (1, 23, 0),  # Tuesday night: not marked
        ):
            with self.subTest(day_offset=day_offset, hour=hour):
                ReminderDispatch.objects.all().delete()
                dispatched, _ = self.run_once(self.at(day_offset, hour))
                self.assertEqual(dispatched, expected)

    # Duplicates and lateness -----------------------------------------------------

    def test_same_slot_is_sent_once_even_when_run_twice(self):
        first, webpush = self.run_once(self.at(hour=9))
        second, webpush_again = self.run_once(self.at(hour=9, second=40))
        self.assertEqual((first, second), (1, 0))
        webpush.assert_called_once()
        webpush_again.assert_not_called()
        with self.assertRaises(IntegrityError):
            ReminderDispatch.objects.create(
                setting=self.setting, slot_at=MONDAY + timedelta(hours=9)
            )

    def test_slot_later_than_five_minutes_is_skipped(self):
        self.assertEqual(self.run_once(self.at(hour=9, minute=5, second=1))[0], 0)
        self.assertEqual(self.run_once(self.at(hour=9, minute=4, second=59))[0], 1)
        self.assertFalse(
            ReminderDispatch.objects.filter(
                slot_at__gt=MONDAY + timedelta(hours=9)
            ).exists()
        )

    def test_expired_device_is_forgotten(self):
        response = mock.Mock(status_code=410, text="", headers={})
        dispatched, _ = self.run_once(
            self.at(hour=9),
            side_effect=notifications.WebPushException("gone", response=response),
        )
        self.assertEqual(dispatched, 1)
        self.assertFalse(PushSubscription.objects.exists())

    def test_old_dispatch_rows_are_pruned(self):
        old = ReminderDispatch.objects.create(
            setting=self.setting, slot_at=MONDAY - timedelta(days=10)
        )
        self.run_once(self.at(hour=9))
        self.assertFalse(ReminderDispatch.objects.filter(pk=old.pk).exists())
        self.assertEqual(ReminderDispatch.objects.count(), 1)

    def test_each_active_member_gets_their_own_reminder(self):
        other = make_member(
            "outra@empresa.test", self.organization, interval_minutes=120
        )
        dispatched, webpush = self.run_once(self.at(hour=10))
        self.assertEqual(dispatched, 2)
        self.assertEqual(webpush.call_count, 2)
        self.assertEqual(
            set(ReminderDispatch.objects.values_list("setting", flat=True)),
            {self.setting.pk, other.pk},
        )

    def test_logs_only_ids_and_counts(self):
        with self.assertLogs("wellbeing.scheduler", level="INFO") as logs:
            self.run_once(self.at(hour=9))
        output = "\n".join(logs.output)
        self.assertIn("dispatched=1", output)
        self.assertNotIn("@", output)
        self.assertNotIn("dono", output)

    # Background thread -----------------------------------------------------------

    def test_background_thread_needs_keys_and_switch(self):
        self.addCleanup(scheduler.stop_in_background)
        with override_settings(**NO_VAPID):
            self.assertIsNone(scheduler.start_in_background())
        with override_settings(WEB_PUSH_SCHEDULER=False):
            self.assertIsNone(scheduler.start_in_background())
        with (
            mock.patch.object(scheduler.Plan, "step", return_value=0) as step,
            mock.patch.object(scheduler.Plan, "wake_at", side_effect=lambda now: now),
            mock.patch.object(scheduler, "SLACK_SECONDS", 60),
        ):
            thread = scheduler.start_in_background()
            self.assertTrue(thread.daemon)
            # Starting again reuses the running thread.
            self.assertIs(scheduler.start_in_background(), thread)
            # It steps once on start, then sleeps (60 s here) until woken.
            self.assertTrue(wait_for(lambda: step.call_count == 1))
            scheduler.wake()
            self.assertTrue(wait_for(lambda: step.call_count == 2))
            scheduler.stop_in_background()
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_only_the_wsgi_entry_point_starts_the_thread(self):
        from pathlib import Path

        from django.conf import settings

        wsgi = (Path(settings.BASE_DIR) / "config" / "wsgi.py").read_text()
        apps = (Path(settings.BASE_DIR) / "wellbeing" / "apps.py").read_text()
        self.assertIn("start_in_background", wsgi)
        self.assertNotIn("start_in_background", apps)
        # Nothing in the test process (a manage.py command) started it.
        self.assertIsNone(scheduler.running_thread())


@override_settings(**VAPID, WEB_PUSH_SCHEDULER_REFRESH_MINUTES=180)
class PlanTests(TestCase):
    """The worker's plan with a simulated clock: the database is touched only
    on refresh and at a due slot, so Neon Free can suspend in between."""

    def setUp(self):
        scheduler._wake.clear()
        self.addCleanup(scheduler._wake.clear)
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.setting = make_member("dono@empresa.test", self.organization)
        self.webpush = mock.patch.object(notifications, "webpush").start()
        self.addCleanup(mock.patch.stopall)

    def at(self, day_offset=0, hour=0, minute=0, second=0):
        return utc(
            MONDAY
            + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)
        )

    def drive(self, plan, start, end):
        """Run the worker loop from ``start`` to ``end``, waking exactly when
        the plan asks; returns the sent slots and the queries per wake."""
        sent, queries, now = [], [], start
        while now <= end:
            before = ReminderDispatch.objects.count()
            with CaptureQueriesContext(connection) as captured:
                seconds = scheduler.tick(plan, now)
            queries.append((now, len(captured)))
            sent.extend(
                ReminderDispatch.objects.order_by("slot_at").values_list(
                    "slot_at", flat=True
                )[before:]
            )
            now += timedelta(seconds=seconds)
        return sent, queries

    def test_no_query_between_refreshes_without_a_due_slot(self):
        plan = scheduler.Plan()
        saturday = self.at(day_offset=5, hour=0, second=5)
        with CaptureQueriesContext(connection) as loading:
            plan.step(saturday)
        self.assertEqual(len(loading), 2)  # the reminders, the old dispatches
        self.assertEqual(plan.wake_at(saturday), saturday + timedelta(hours=3))
        # Even waking every minute, nothing reaches the database.
        with CaptureQueriesContext(connection) as idle:
            for minute in range(1, 180):
                self.assertEqual(plan.step(saturday + timedelta(minutes=minute)), 0)
        self.assertEqual(len(idle), 0)
        with CaptureQueriesContext(connection) as refreshed:
            plan.step(saturday + timedelta(hours=3))
        self.assertEqual(len(refreshed), 2)

    def test_weekend_wakes_only_to_refresh(self):
        plan = scheduler.Plan()
        sent, queries = self.drive(
            plan, self.at(day_offset=5, second=5), self.at(day_offset=6, hour=23)
        )
        self.assertEqual(sent, [])
        # 48 hours, one refresh every 3 hours, nothing else.
        self.assertEqual(len(queries), 16)
        self.assertEqual({count for _, count in queries}, {2})

    def test_sleeps_until_the_slot_and_sends_it_once(self):
        plan = scheduler.Plan()
        plan.step(self.at(hour=8))
        self.assertEqual(plan.wake_at(self.at(hour=8)), self.at(hour=9))
        self.assertEqual(scheduler.tick(plan, self.at(hour=8)), 3600 + 1)
        with CaptureQueriesContext(connection) as idle:
            self.assertEqual(plan.step(self.at(hour=8, minute=59, second=59)), 0)
        self.assertEqual(len(idle), 0)
        self.assertEqual(plan.step(self.at(hour=9, second=1)), 1)
        self.webpush.assert_called_once()
        self.assertEqual(plan.step(self.at(hour=9, second=30)), 0)
        self.webpush.assert_called_once()

    def test_a_working_day_wakes_only_at_slots_and_refreshes(self):
        plan = scheduler.Plan()
        sent, queries = self.drive(plan, self.at(second=5), self.at(hour=23))
        self.assertEqual(
            sent, [MONDAY + timedelta(hours=hour) for hour in range(9, 18)]
        )
        # 9 slots (each a second after the hour) and 8 refreshes in 23 hours;
        # nothing else wakes the database.
        slots = [(now, count) for now, count in queries if now.second == 1]
        self.assertEqual(
            [now for now, _ in slots],
            [self.at(hour=hour, second=1) for hour in range(9, 18)],
        )
        refreshes = [count for _, count in queries if (_, count) not in slots]
        self.assertEqual(refreshes, [2] * 8)

    def test_two_workers_send_once(self):
        first, second = scheduler.Plan(), scheduler.Plan()
        first.step(self.at(hour=8))
        second.step(self.at(hour=8, minute=1))
        results = [
            first.step(self.at(hour=9, second=1)),
            second.step(self.at(hour=9, second=2)),
        ]
        self.assertEqual(results, [1, 0])
        self.webpush.assert_called_once()
        self.assertEqual(ReminderDispatch.objects.count(), 1)

    def test_changed_or_deactivated_after_refresh_is_not_sent_at_the_old_slot(self):
        for change in (
            {"interval_minutes": 90},
            {"weekdays": "2345"},
            {"workday_start": time(8, 30)},
            {"active": False},
        ):
            with self.subTest(change=change):
                ReminderDispatch.objects.all().delete()
                ReminderSetting.objects.filter(pk=self.setting.pk).update(
                    active=True,
                    interval_minutes=60,
                    weekdays="12345",
                    workday_start=time(8),
                )
                plan = scheduler.Plan()
                plan.step(self.at(hour=8))
                ReminderSetting.objects.filter(pk=self.setting.pk).update(**change)
                self.assertEqual(plan.step(self.at(hour=9, second=1)), 0)
                self.assertFalse(ReminderDispatch.objects.exists())
        self.webpush.assert_not_called()

    def test_removed_device_is_not_sent_at_the_old_slot(self):
        plan = scheduler.Plan()
        plan.step(self.at(hour=8))
        PushSubscription.objects.all().delete()
        self.assertEqual(plan.step(self.at(hour=9, second=1)), 0)
        self.webpush.assert_not_called()

    def test_saving_reminders_wakes_the_scheduler_for_the_new_slot(self):
        user = self.setting.membership.user
        self.client.force_login(user)
        plan = scheduler.Plan()
        scheduler.tick(plan, self.at(hour=8))
        # The other worker loaded its plan before the change and is not woken.
        other_worker = scheduler.Plan()
        other_worker.step(self.at(hour=8))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("wellbeing_reminders"),
                {
                    "action": "save",
                    "interval_minutes": "90",
                    "workday_start": "08:00",
                    "workday_end": "18:00",
                    "weekdays": ["1", "2", "3", "4", "5"],
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(scheduler._wake.is_set())
        # The loop wakes now, reloads, and sleeps until the new 09:30 slot.
        self.assertEqual(scheduler.tick(plan, self.at(hour=8, minute=10)), 80 * 60 + 1)
        self.assertFalse(scheduler._wake.is_set())
        self.assertEqual(other_worker.step(self.at(hour=9, second=1)), 0)
        self.assertEqual(plan.step(self.at(hour=9, minute=30, second=1)), 1)
        self.assertEqual(other_worker.step(self.at(hour=9, minute=30, second=2)), 0)
        self.webpush.assert_called_once()

    def test_deactivating_and_devices_wake_the_scheduler(self):
        user = self.setting.membership.user
        self.client.force_login(user)
        device = {
            "endpoint": "https://push.example.test/novo",
            "keys": {"p256dh": "p256dh", "auth": "auth"},
        }
        for name, data, kwargs in (
            ("wellbeing_reminders", {"action": "deactivate"}, {}),
            (
                "wellbeing_push_subscribe",
                json.dumps(device),
                {"content_type": "application/json"},
            ),
            (
                "wellbeing_push_unsubscribe",
                json.dumps({"endpoint": device["endpoint"]}),
                {"content_type": "application/json"},
            ),
        ):
            with self.subTest(name=name):
                scheduler._wake.clear()
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse(name), data, **kwargs)
                self.assertLess(response.status_code, 400)
                self.assertTrue(scheduler._wake.is_set())

    def test_rejected_save_does_not_wake(self):
        self.client.force_login(self.setting.membership.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("wellbeing_reminders"),
                {"action": "save", "interval_minutes": "45"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(scheduler._wake.is_set())

    def test_night_shift_through_the_plan(self):
        ReminderSetting.objects.filter(pk=self.setting.pk).update(
            workday_start=time(22), workday_end=time(6), weekdays="1"
        )
        plan = scheduler.Plan()
        sent, _ = self.drive(plan, self.at(hour=0, second=5), self.at(day_offset=2))
        self.assertEqual(
            sent,
            [MONDAY + timedelta(hours=23)]
            + [MONDAY + timedelta(days=1, hours=hour) for hour in range(6)],
        )

    def test_late_slot_is_skipped_without_a_query(self):
        plan = scheduler.Plan()
        plan.step(self.at(hour=8))
        # The process stalled past 09:05: the 09:00 slot is dropped.
        with CaptureQueriesContext(connection) as late:
            self.assertEqual(plan.step(self.at(hour=9, minute=5, second=1)), 0)
        self.assertEqual(len(late), 0)
        self.assertFalse(ReminderDispatch.objects.exists())
        other = scheduler.Plan()
        other.step(self.at(hour=8))
        self.assertEqual(other.step(self.at(hour=9, minute=4, second=59)), 1)

    def test_restart_within_five_minutes_still_sends(self):
        plan = scheduler.Plan()
        self.assertEqual(plan.step(self.at(hour=9, minute=3)), 1)
        self.assertEqual(plan.wake_at(self.at(hour=9, minute=3)), self.at(hour=10))

    def test_failed_step_retries_soon(self):
        plan = scheduler.Plan()
        with (
            mock.patch.object(scheduler, "_candidates", side_effect=RuntimeError),
            self.assertLogs("wellbeing.scheduler", level="ERROR"),
        ):
            self.assertEqual(
                scheduler.tick(plan, self.at(hour=8)), scheduler.RETRY_SECONDS
            )
        self.assertIsNone(plan.refresh_at)
        self.assertEqual(plan.step(self.at(hour=9, second=1)), 1)

    def test_refresh_interval_comes_from_settings(self):
        with override_settings(WEB_PUSH_SCHEDULER_REFRESH_MINUTES=60):
            plan = scheduler.Plan()
        plan.step(self.at(day_offset=5))
        self.assertEqual(
            plan.wake_at(self.at(day_offset=5)), self.at(day_offset=5, hour=1)
        )

    def test_old_dispatch_rows_are_pruned_only_on_refresh(self):
        plan = scheduler.Plan()
        plan.step(self.at(hour=8))
        old = ReminderDispatch.objects.create(
            setting=self.setting, slot_at=MONDAY - timedelta(days=10)
        )
        plan.step(self.at(hour=9, second=1))
        self.assertTrue(ReminderDispatch.objects.filter(pk=old.pk).exists())
        plan.step(self.at(hour=11))
        self.assertFalse(ReminderDispatch.objects.filter(pk=old.pk).exists())


@override_settings(**VAPID)
class TwoWorkersTests(TransactionTestCase):
    """Two gunicorn workers waking up in the same minute, as separate DB
    connections: the unique dispatch row lets only one send."""

    def test_concurrent_workers_send_once(self):
        organization = Organization.objects.create(name="Empresa", slug="empresa")
        make_member("dono@empresa.test", organization)
        now = utc(MONDAY + timedelta(hours=9, seconds=5))
        barrier = threading.Barrier(2)
        results = []

        def worker():
            try:
                barrier.wait()
                results.append(scheduler.run_once(now=now))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        with mock.patch.object(notifications, "webpush") as webpush:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
        self.assertEqual(sorted(results), [0, 1])
        webpush.assert_called_once()
        self.assertEqual(ReminderDispatch.objects.count(), 1)
