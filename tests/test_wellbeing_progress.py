"""Meu Progresso: streak, minutes and trophies in America/Sao_Paulo (aceite 4 e 5)."""

from datetime import UTC, datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization
from wellbeing.models import ActivitySession
from wellbeing.services import TROPHIES, personal_progress

# Brazil has no DST: local = UTC-3. 2026-10-12 is a Monday.
NOW = datetime(2026, 10, 13, 15, 0, tzinfo=UTC)  # Tue 13/10 12:00 local


def utc(day, hour, minute=0, month=10):
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


class ProgressTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.user = users.create_user(email="progresso@example.test", password="x-pw-1")
        self.colleague = users.create_user(
            email="colega@example.test", password="x-pw-2"
        )
        self.org = Organization.objects.create(name="Progresso", slug="progresso")
        self.other_org = Organization.objects.create(name="Outra", slug="outra-prog")
        for user, org in (
            (self.user, self.org),
            (self.colleague, self.org),
            (self.user, self.other_org),
        ):
            Membership.objects.create(
                user=user, organization=org, role=Membership.Role.COLLABORATOR
            )

    def practice(self, started_at, seconds=300, kind="meditacao", user=None, org=None):
        return ActivitySession.objects.create(
            user=user or self.user,
            organization=org or self.org,
            kind=kind,
            slug="x",
            started_at=started_at,
            duration_seconds=seconds,
            completed=True,
        )

    def progress(self, now=NOW):
        return personal_progress(self.user, self.org, now=now)

    def test_empty_progress(self):
        data = self.progress()
        self.assertEqual(
            (data["streak"], data["week_minutes"], data["month_minutes"]), (0, 0, 0)
        )
        self.assertFalse(any(t["earned"] for t in data["trophies"]))

    def test_day_turns_at_local_midnight_not_utc(self):
        # 12/10 23:30 local and 13/10 00:30 local: same UTC day, two local days.
        self.practice(utc(13, 2, 30))
        self.practice(utc(13, 3, 30))
        self.assertEqual(self.progress()["streak"], 2)

    def test_streak_survives_until_today_ends_and_breaks_after_a_gap(self):
        for day in (10, 11, 12):  # 10, 11, 12/10 at noon local
            self.practice(utc(day, 15))
        self.assertEqual(self.progress()["streak"], 3)  # nothing yet today
        self.assertEqual(self.progress(now=utc(14, 2, 59))["streak"], 3)  # 13/10 23:59
        self.assertEqual(self.progress(now=utc(14, 3, 0))["streak"], 0)  # 14/10 00:00

    def test_week_and_month_minutes_use_local_calendar(self):
        self.practice(utc(12, 2, 30), seconds=600)  # Sun 11/10 23:30 local: last week
        self.practice(utc(12, 3, 30), seconds=300)  # Mon 12/10 00:30 local: this week
        self.practice(utc(1, 2, 30), seconds=900)  # 30/09 23:30 local: September
        self.practice(utc(1, 3, 30), seconds=120)  # 01/10 00:30 local: October
        data = self.progress()
        self.assertEqual(data["week_minutes"], 5)
        self.assertEqual(data["month_minutes"], 17)  # 600 + 300 + 120 seconds
        self.assertEqual(data["total_minutes"], 32)

    def test_totals_by_kind(self):
        self.practice(utc(13, 12), seconds=180, kind="ginastica")
        self.practice(utc(12, 12), seconds=600, kind="relaxamento")
        self.practice(utc(11, 12), seconds=120, kind="ginastica")
        kinds = {item["kind"]: item for item in self.progress()["by_kind"]}
        self.assertEqual(
            (kinds["ginastica"]["count"], kinds["ginastica"]["minutes"]), (2, 5)
        )
        self.assertEqual(kinds["meditacao"]["count"], 0)
        self.assertEqual(kinds["relaxamento"]["minutes"], 10)

    def test_trophies_by_milestone(self):
        def earned():
            return {t["slug"] for t in self.progress()["trophies"] if t["earned"]}

        self.assertEqual(
            [t["slug"] for t in TROPHIES],
            [
                "primeira-pratica",
                "sequencia-3",
                "sequencia-7",
                "sequencia-30",
                "60-minutos",
            ],
        )
        self.practice(utc(13, 12), seconds=60)
        self.assertEqual(earned(), {"primeira-pratica"})
        self.practice(utc(12, 12), seconds=60)
        self.practice(utc(11, 12), seconds=60)
        self.assertEqual(earned(), {"primeira-pratica", "sequencia-3"})
        for day in range(4, 11):  # 4..10/10: 10 days in a row up to today
            self.practice(utc(day, 12), seconds=60)
        self.assertEqual(earned(), {"primeira-pratica", "sequencia-3", "sequencia-7"})
        # A broken streak keeps the trophies already earned.
        later = NOW + timedelta(days=5)
        progress = personal_progress(self.user, self.org, now=later)
        self.assertEqual(progress["streak"], 0)
        self.assertEqual(progress["best_streak"], 10)
        self.assertIn(
            "sequencia-7", {t["slug"] for t in progress["trophies"] if t["earned"]}
        )
        self.practice(utc(13, 13), seconds=3600 - 600)  # total now 60 min
        self.assertIn("60-minutos", earned())
        self.assertNotIn("sequencia-30", earned())
        for offset in range(10, 30):
            self.practice(NOW - timedelta(days=offset), seconds=60)
        self.assertIn("sequencia-30", earned())

    def test_only_own_practices_in_the_active_organization_count(self):
        self.practice(utc(13, 12), user=self.colleague)
        self.practice(utc(13, 12), org=self.other_org)
        self.assertEqual(self.progress()["total_minutes"], 0)

    def test_page_shows_only_the_owner_progress(self):
        self.practice(utc(13, 12), seconds=600, user=self.colleague)
        self.practice(utc(13, 12), seconds=600, org=self.other_org)
        self.client.force_login(self.user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.org.pk
        session.save()
        response = self.client.get(reverse("wellbeing_progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meu Progresso")
        self.assertNotContains(response, "colega@example.test")
        self.assertEqual(response.context["progress"]["total_minutes"], 0)
        self.assertEqual(
            self.client.post(reverse("wellbeing_progress")).status_code, 405
        )
        self.client.logout()
        url = reverse("wellbeing_progress")
        self.assertRedirects(self.client.get(url), f"/login/?next={url}")
