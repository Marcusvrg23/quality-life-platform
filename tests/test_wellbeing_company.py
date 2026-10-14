"""Company usage of wellbeing practices: aggregates only, MIN_GROUP (aceite 6)."""

from datetime import UTC, datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from identity.models import Membership, Organization
from reports.services import MIN_GROUP
from wellbeing.models import ActivitySession
from wellbeing.services import company_usage

# Tue 13/10/2026 12:00 in São Paulo (UTC-3); the week starts Mon 12/10.
NOW = datetime(2026, 10, 13, 15, 0, tzinfo=UTC)


class CompanyUsageTests(TestCase):
    def setUp(self):
        self.users = get_user_model().objects
        self.org = Organization.objects.create(name="Uso", slug="uso-be")
        self.other_org = Organization.objects.create(name="Outra", slug="outra-uso")
        self.manager = self.users.create_user(
            email="gestor-uso@example.test", password="x-pw-1"
        )
        Membership.objects.create(
            user=self.manager,
            organization=self.org,
            role=Membership.Role.CORPORATE_MANAGER,
        )
        self.people = []

    def person(self, org=None):
        index = len(self.people)
        user = self.users.create_user(
            email=f"pessoa{index}@example.test", password="x-pw-2"
        )
        Membership.objects.create(
            user=user, organization=org or self.org, role=Membership.Role.COLLABORATOR
        )
        self.people.append(user)
        return user

    def practice(self, user, kind="ginastica", seconds=300, started_at=NOW, org=None):
        ActivitySession.objects.create(
            user=user,
            organization=org or self.org,
            kind=kind,
            slug="x",
            started_at=started_at,
            duration_seconds=seconds,
            completed=True,
        )

    def week(self):
        return company_usage(self.org, now=NOW)["periods"][0]

    def test_min_group_is_the_report_rule(self):
        self.assertEqual(MIN_GROUP, 5)

    def test_four_people_show_no_numbers(self):
        for _ in range(4):
            self.practice(self.person(), seconds=600)
        week = self.week()
        self.assertFalse(week["visible"])
        self.assertEqual(set(week), {"label", "start", "end", "visible"})

    def test_five_people_show_aggregates_only(self):
        monday = datetime(2026, 10, 12, 12, tzinfo=UTC)  # Mon 12/10 09:00 local
        for _ in range(5):
            user = self.person()
            self.practice(user, kind="meditacao")
            self.practice(user, kind="ginastica", seconds=120, started_at=monday)
        week = self.week()
        self.assertTrue(week["visible"])
        self.assertEqual(week["people"], 5)
        self.assertEqual(week["minutes"], (5 * 300 + 5 * 120) // 60)
        self.assertEqual(week["practices"], 10)
        kinds = {item["kind"]: item for item in week["by_kind"]}
        self.assertEqual(
            (kinds["ginastica"]["count"], kinds["ginastica"]["minutes"]), (5, 10)
        )
        self.assertEqual(
            (kinds["meditacao"]["count"], kinds["meditacao"]["minutes"]), (5, 25)
        )
        self.assertEqual(kinds["relaxamento"]["count"], 0)  # nobody: nothing to infer
        self.assertNotIn("user", repr(week))

    def test_split_by_type_hidden_when_any_type_has_a_small_group(self):
        for index in range(5):
            self.practice(
                self.person(), kind="relaxamento" if index < 2 else "ginastica"
            )
        week = self.week()
        self.assertTrue(week["visible"])
        self.assertEqual(week["people"], 5)
        # Showing ginástica (3 people would already be hidden) or anything
        # else would let total minus visible types reveal the small group.
        self.assertIsNone(week["by_kind"])

    def test_week_and_month_use_local_calendar_and_own_company(self):
        sunday_night = datetime(
            2026, 10, 12, 2, 30, tzinfo=UTC
        )  # Sun 11/10 23:30 local
        for _ in range(5):
            self.practice(self.person(), started_at=sunday_night)
        for _ in range(5):
            outsider = self.person(org=self.other_org)
            self.practice(outsider, org=self.other_org)
        week, month = company_usage(self.org, now=NOW)["periods"]
        self.assertFalse(week["visible"])  # last week locally, not this week
        self.assertTrue(month["visible"])
        self.assertEqual(month["people"], 5)  # the other company never counts

    def test_report_page_for_manager_has_no_individual_data(self):
        for _ in range(5):
            self.practice(self.person())
        self.client.force_login(self.manager)
        with mock.patch("django.utils.timezone.now", return_value=NOW):
            response = self.client.get(reverse("executive_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uso das práticas de bem-estar")
        html = response.content.decode()
        for user in self.people:
            self.assertNotIn(user.email, html)
        self.assertNotIn("ranking", html.lower())
        usage = response.context["usage"]
        self.assertNotIn("user", repr(usage))
        self.assertNotIn("email", repr(usage))

    def test_report_page_below_min_group_shows_the_rule_not_numbers(self):
        for _ in range(4):
            self.practice(self.person(), seconds=600)
        self.client.force_login(self.manager)
        with mock.patch("django.utils.timezone.now", return_value=NOW):
            response = self.client.get(reverse("executive_report"))
        self.assertContains(response, "menos de 5 pessoas", count=2)
        self.assertNotContains(response, "pessoas ativas")

    def test_collaborator_and_professional_cannot_see_usage(self):
        user = self.person()
        for role in (Membership.Role.COLLABORATOR, Membership.Role.PROFESSIONAL):
            Membership.objects.filter(user=user).update(role=role)
            self.client.force_login(user)
            with self.subTest(role=role):
                response = self.client.get(reverse("executive_report"))
                self.assertEqual(response.status_code, 403)
