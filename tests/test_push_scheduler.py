"""In-process reminder scheduler (docs/specs/13-pwa-lembretes.md, aceite 13 e 14):
slots in America/Sao_Paulo with a UTC clock, nothing outside the shift, on
unmarked days or for inactive reminders; night shifts; no duplicates across
workers; late slots skipped. pywebpush is simulated."""

import json
import threading
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase, override_settings

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
        with mock.patch.object(scheduler, "run_once") as run_once:
            thread = scheduler.start_in_background(tick_seconds=0.01)
            self.assertTrue(thread.daemon)
            # Starting again reuses the running thread.
            self.assertIs(scheduler.start_in_background(), thread)
            for _ in range(200):
                if run_once.called:
                    break
                thread.join(0.01)
            scheduler.stop_in_background()
            thread.join(2)
        self.assertTrue(run_once.called)
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
