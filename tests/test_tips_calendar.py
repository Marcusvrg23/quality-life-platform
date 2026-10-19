"""Weekly tips and special dates (docs/specs/17-dicas-da-semana.md, aceite 1 a 7).

The texts are a draft waiting for the Quality Life's approval: with
``PUBLISHED`` False nothing shows on Hoje and nothing is sent. Every test that
needs them on patches ``PUBLISHED``. pywebpush is simulated.
"""

import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from config import tips_calendar
from identity.models import Membership, Organization, User
from wellbeing import notifications, scheduler
from wellbeing.models import (
    NotificationDelivery,
    NotificationPreference,
    PushSubscription,
    TipDispatch,
)

PASSWORD = "tips-calendar-password-17"
VAPID = {
    "VAPID_PUBLIC_KEY": "public-key-for-the-test",
    "VAPID_PRIVATE_KEY": "private-key-for-the-test",
    "VAPID_SUBJECT": "mailto:contato@example.test",
}
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
MONDAY = date(2026, 10, 19)
TUESDAY = date(2026, 10, 20)
published = mock.patch.object(tips_calendar, "PUBLISHED", True)


def at_local(day, hour, minute=0, second=5):
    local = datetime(
        day.year, day.month, day.day, hour, minute, second, tzinfo=SAO_PAULO
    )
    return local.astimezone(dt_timezone.utc)


class CalendarTests(TestCase):
    def test_draft_has_26_weekly_tips_and_14_special_dates(self):
        self.assertEqual(len(tips_calendar.WEEKLY_TIPS), 26)
        self.assertEqual(len(tips_calendar.SPECIAL_DATES), 14)

    def test_texts_are_short_generic_and_open_app_pages(self):
        tips = [
            *tips_calendar.WEEKLY_TIPS,
            *(tip for _, tip in tips_calendar.SPECIAL_DATES),
        ]
        for tip in tips:
            with self.subTest(title=tip.title):
                self.assertLessEqual(len(tip.title), 40)
                self.assertLessEqual(len(tip.text), 120)
                words = notifications._words(f"{tip.title} {tip.text}")
                self.assertEqual(words & set(notifications.RESULT_WORDS), set())
                self.assertTrue(reverse(tip.route).startswith("/app/"))

    def test_unpublished_shows_and_sends_nothing(self):
        self.assertFalse(tips_calendar.PUBLISHED)
        for day in (MONDAY, TUESDAY, date(2026, 9, 10)):
            self.assertIsNone(tips_calendar.tip_to_send(day))
            self.assertIsNone(tips_calendar.tip_to_show(day))

    def test_send_day_rules(self):
        send_day = tips_calendar.send_day
        # 08/03/2026 is a Sunday: the Friday before.
        self.assertEqual(send_day(("date", 3, 8), 2026), date(2026, 3, 6))
        self.assertEqual(send_day(("date", 9, 10), 2026), date(2026, 9, 10))
        # 01/11/2026 is a Sunday: the first business day is Monday the 2nd.
        self.assertEqual(send_day(("first_business_day", 11), 2026), date(2026, 11, 2))
        # 28/02/2026 is a Saturday; 2028 is a leap year (29/02, a Tuesday).
        self.assertEqual(send_day(("last_day", 2), 2026), date(2026, 2, 27))
        self.assertEqual(send_day(("last_day", 2), 2028), date(2028, 2, 29))
        self.assertEqual(send_day(("last_day", 12), 2026), date(2026, 12, 31))
        # 01/05/2026 is a Friday: Thursday the 30th; 01/05/2028 is a Monday: Friday.
        self.assertEqual(
            send_day(("business_day_before", 5, 1), 2026), date(2026, 4, 30)
        )
        self.assertEqual(
            send_day(("business_day_before", 5, 1), 2028), date(2028, 4, 28)
        )
        with self.assertRaises(ValueError):
            send_day(("weekly", 1), 2026)

    def test_every_special_date_goes_out_on_a_business_day(self):
        for year in range(2026, 2036):
            for rule, tip in tips_calendar.SPECIAL_DATES:
                with self.subTest(year=year, title=tip.title):
                    self.assertLess(tips_calendar.send_day(rule, year).weekday(), 5)

    def test_first_listed_special_date_wins_a_shared_day(self):
        # 07/04/2029 is a Saturday and moves to Friday 06/04, the day of the
        # previous entry: that one goes out.
        tip = tips_calendar.special_tip_on(date(2029, 4, 6))
        self.assertEqual(tip.title, "Dia da Atividade Física")

    def test_weekly_tip_follows_the_iso_week_and_repeats_twice_a_year(self):
        tips = tips_calendar.WEEKLY_TIPS
        self.assertEqual(tips_calendar.weekly_tip(MONDAY), tips[(43 - 1) % 26])
        self.assertEqual(
            tips_calendar.weekly_tip(MONDAY),
            tips_calendar.weekly_tip(MONDAY + timedelta(days=6)),
        )
        self.assertEqual(tips_calendar.weekly_tip(date(2026, 1, 1)), tips[0])
        self.assertEqual(
            tips_calendar.weekly_tip(date(2026, 7, 6)), tips[(28 - 1) % 26]
        )

    @published
    def test_published_sends_on_mondays_and_special_dates_only(self):
        self.assertEqual(
            tips_calendar.tip_to_send(MONDAY), tips_calendar.weekly_tip(MONDAY)
        )
        self.assertIsNone(tips_calendar.tip_to_send(TUESDAY))
        setembro = tips_calendar.tip_to_send(date(2026, 9, 10))  # a Thursday
        self.assertEqual(setembro.title, "Setembro Amarelo")
        self.assertIn("CVV, ligue 188", setembro.text)
        # Hoje shows the week's tip on any day and the special one on its day.
        self.assertEqual(
            tips_calendar.tip_to_show(TUESDAY), tips_calendar.weekly_tip(TUESDAY)
        )
        self.assertEqual(
            tips_calendar.tip_to_show(date(2026, 9, 10)).label, "Data especial"
        )


class ScreenTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Empresa", slug="empresa-17"
        )
        self.user = User.objects.create_user("pessoa@empresa.test", PASSWORD)
        Membership.objects.create(
            user=self.user,
            organization=self.organization,
            role=Membership.Role.COLLABORATOR,
        )
        self.client.force_login(self.user)

    def home(self, day):
        with mock.patch("django.utils.timezone.localdate", return_value=day):
            return self.client.get(reverse("app"))

    def test_unpublished_home_has_no_weekly_tip(self):
        response = self.home(MONDAY)
        self.assertNotContains(response, "Dica da semana")
        self.assertNotContains(response, tips_calendar.weekly_tip(MONDAY).text)

    @published
    def test_published_home_shows_the_tip_of_the_week(self):
        tip = tips_calendar.weekly_tip(TUESDAY)
        response = self.home(TUESDAY)
        self.assertContains(response, "Dica da semana")
        self.assertContains(
            response, f'<p class="wb-tip__title">{tip.title}</p>', html=True
        )
        self.assertContains(response, tip.text)

    @published
    def test_published_home_shows_the_special_date_with_its_link(self):
        response = self.home(date(2026, 9, 1))  # Dia da Educação Física
        self.assertContains(response, "Data especial")
        self.assertContains(response, "Dia da Educação Física")
        self.assertContains(response, f'href="{reverse("wellbeing_gym")}">Abrir')

    def test_reminders_explain_whether_tips_are_sent(self):
        unpublished = self.client.get(reverse("wellbeing_reminders"))
        self.assertContains(
            unpublished, "As dicas e datas especiais ainda não são enviadas"
        )
        with published:
            on = self.client.get(reverse("wellbeing_reminders"))
        self.assertContains(
            on, "As dicas chegam às segundas, às 10h, e nas datas especiais."
        )
        self.assertNotContains(on, "ainda não são enviadas")


def make_member(email, organization, *, device=True):
    user = User.objects.create_user(email, PASSWORD)
    membership = Membership.objects.create(
        user=user, organization=organization, role=Membership.Role.COLLABORATOR
    )
    if device:
        PushSubscription.objects.create(
            membership=membership,
            endpoint=f"https://push.example.test/{membership.pk}",
            p256dh="p256dh",
            auth="auth",
        )
    return membership


@override_settings(**VAPID)
class TipSchedulerTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Empresa", slug="empresa-17b"
        )
        self.member = make_member("dono@empresa.test", self.organization)
        patcher = mock.patch.object(notifications, "webpush")
        self.webpush = patcher.start()
        self.addCleanup(patcher.stop)

    def payloads(self):
        return [json.loads(call.kwargs["data"]) for call in self.webpush.call_args_list]

    def test_unpublished_plan_never_holds_a_tip_and_adds_no_query(self):
        plan = scheduler.Plan()
        with CaptureQueriesContext(connection) as loading:
            plan.step(at_local(MONDAY, 8))
        self.assertIsNone(plan.tip_slot)
        self.assertEqual(len(loading), 2)  # the reminders, the old dispatches
        self.assertEqual(plan.step(at_local(MONDAY, 10)), 0)
        self.webpush.assert_not_called()

    @published
    def test_monday_tip_goes_out_at_ten_once_to_each_person(self):
        other = make_member("outra@empresa.test", self.organization)
        make_member("semaparelho@empresa.test", self.organization, device=False)
        plan = scheduler.Plan()
        plan.step(at_local(MONDAY, 8))
        self.assertEqual(plan.tip_slot, at_local(MONDAY, 10, second=0))
        self.assertEqual(
            plan.wake_at(at_local(MONDAY, 8)), at_local(MONDAY, 10, second=0)
        )
        with CaptureQueriesContext(connection) as idle:
            self.assertEqual(plan.step(at_local(MONDAY, 9, 59)), 0)
        self.assertEqual(len(idle), 0)
        self.assertEqual(plan.step(at_local(MONDAY, 10, second=1)), 2)
        tip = tips_calendar.weekly_tip(MONDAY)
        self.assertEqual(
            [(p["title"], p["body"], p["url"], p["tag"]) for p in self.payloads()],
            [(tip.title, tip.text, reverse(tip.route), "ql-dicas")] * 2,
        )
        self.assertEqual(
            set(TipDispatch.objects.values_list("membership", flat=True)),
            {self.member.pk, other.pk},
        )
        # The same worker, a second worker and a restart all send nothing more.
        self.assertEqual(plan.step(at_local(MONDAY, 10, 1)), 0)
        self.assertEqual(scheduler.run_once(now=at_local(MONDAY, 10, 2)), 0)
        self.assertEqual(self.webpush.call_count, 2)

    @published
    def test_tuesday_has_no_tip_and_late_tip_is_skipped(self):
        self.assertEqual(scheduler.run_once(now=at_local(TUESDAY, 10)), 0)
        self.assertEqual(scheduler.run_once(now=at_local(MONDAY, 10, 6)), 0)
        self.webpush.assert_not_called()
        self.assertFalse(TipDispatch.objects.exists())

    @published
    def test_special_date_goes_out_on_its_weekday(self):
        self.assertEqual(scheduler.run_once(now=at_local(date(2026, 9, 10), 10)), 1)
        self.assertEqual(self.payloads()[0]["title"], "Setembro Amarelo")

    @published
    def test_turned_off_inactive_or_over_the_daily_limit_get_nothing(self):
        off = make_member("desligou@empresa.test", self.organization)
        NotificationPreference.objects.create(membership=off, dicas=False)
        inactive = make_member("saiu@empresa.test", self.organization)
        Membership.objects.filter(pk=inactive.pk).update(is_active=False)
        NotificationDelivery.objects.create(
            membership=self.member,
            category="dicas",
            devices=1,
            sent_at=at_local(MONDAY, 8),
        )
        scheduler.run_once(now=at_local(MONDAY, 10))
        self.webpush.assert_not_called()

    @published
    def test_a_name_inside_the_tip_skips_only_that_person(self):
        # "Outubro Rosa": rosa@… would see her own name on the lock screen.
        rosa = make_member("rosa@empresa.test", self.organization)
        october = date(2026, 10, 1)  # a Thursday, first business day
        self.assertEqual(scheduler.run_once(now=at_local(october, 10)), 1)
        endpoints = [
            c.kwargs["subscription_info"]["endpoint"]
            for c in self.webpush.call_args_list
        ]
        self.assertEqual(endpoints, [f"https://push.example.test/{self.member.pk}"])
        self.assertTrue(TipDispatch.objects.filter(membership=rosa).exists())

    @published
    def test_old_tip_rows_are_pruned_when_a_tip_is_planned(self):
        TipDispatch.objects.create(
            membership=self.member, day=MONDAY - timedelta(days=7)
        )
        scheduler.Plan().step(at_local(MONDAY, 8))
        self.assertFalse(TipDispatch.objects.filter(day__lt=MONDAY).exists())
