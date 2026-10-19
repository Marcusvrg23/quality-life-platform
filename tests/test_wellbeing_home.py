"""Home: greeting, own first name, shortcuts and tip; menu entries (aceite 7)."""

from datetime import UTC, datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from assessments.models import Assessment, Pillar, QuestionnaireVersion
from config import tips_calendar, wellbeing_catalog
from identity.models import Membership, Organization
from tests.test_assessment_result import answer_identification, completed_result
from wellbeing.services import greeting

SHORTCUTS = (
    "wellbeing_gym",
    "wellbeing_meditation",
    "wellbeing_relax",
    "wellbeing_progress",
)


def local(hour, minute=0):
    """A moment at the given São Paulo local time (UTC-3, no DST)."""
    return datetime(2026, 10, 14, (hour + 3) % 24, minute, tzinfo=UTC)


class GreetingTests(TestCase):
    def test_greeting_by_local_hour(self):
        for (hour, minute), expected in (
            ((5, 0), "Bom dia"),
            ((11, 59), "Bom dia"),
            ((12, 0), "Boa tarde"),
            ((17, 59), "Boa tarde"),
            ((18, 0), "Boa noite"),
            ((20, 59), "Boa noite"),  # 23:59 UTC is still evening locally
            ((4, 59), "Boa noite"),
        ):
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(greeting(local(hour, minute)), expected)


class HomeTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.user = users.create_user(email="home@example.test", password="x-pw-1")
        self.colleague = users.create_user(
            email="colega-home@example.test", password="x-pw-2"
        )
        self.org = Organization.objects.create(name="Home", slug="home-be")
        for user in (self.user, self.colleague):
            Membership.objects.create(
                user=user, organization=self.org, role=Membership.Role.COLLABORATOR
            )
        self.scores = {pillar.code: "70" for pillar in Pillar.objects.all()}

    def complete_with_name(self, user, name):
        # One TEST ONLY version per assessment: the helper creates section 1.
        version = QuestionnaireVersion.objects.create(
            code=f"home-test-{user.pk}",
            version=1,
            title="TEST ONLY",
            scoring_version="t",
        )
        assessment = Assessment.objects.create(
            user=user, organization=self.org, questionnaire_version=version
        )
        answer_identification(version, assessment)
        assessment.answers.filter(question__code="q1-1").update(text_value=name)
        return completed_result(
            user, self.org, version, "70", self.scores, start=assessment
        )

    def home(self, moment):
        self.client.force_login(self.user)
        with mock.patch("django.utils.timezone.now", return_value=moment):
            return self.client.get(reverse("app"))

    def test_greeting_without_assessment_has_no_name(self):
        response = self.home(local(9))
        self.assertContains(
            response, '<p class="dashboard-greeting">Bom dia</p>', html=True
        )

    def test_first_name_comes_from_own_completed_assessment(self):
        self.complete_with_name(self.colleague, "Bruno Colega")
        self.complete_with_name(self.user, "  Ana Paula Souza ")
        response = self.home(local(14))
        self.assertContains(
            response, '<p class="dashboard-greeting">Boa tarde, Ana</p>', html=True
        )
        self.assertNotContains(response, "Bruno")
        self.assertNotContains(response, "Souza")

    def test_name_is_escaped(self):
        self.complete_with_name(self.user, "<b>Ana</b>")
        response = self.home(local(20))
        self.assertNotContains(response, "<b>Ana</b>")
        self.assertContains(response, "Boa noite, &lt;b&gt;Ana&lt;/b&gt;")

    @mock.patch.object(tips_calendar, "PUBLISHED", False)
    def test_four_shortcuts_and_no_tip_while_catalog_is_empty(self):
        # The daily catalog tip shows only while the weekly tips are off.
        response = self.home(local(9))
        for name in SHORTCUTS:
            self.assertContains(
                response, f'class="dashboard-link" href="{reverse(name)}"'
            )
        self.assertNotContains(response, "Dica do dia")
        tip = {"slug": "agua", "text": "TEST ONLY tip text.", "source": "teste"}
        with mock.patch.object(wellbeing_catalog, "TIPS", (tip,)):
            response = self.home(local(9))
        self.assertContains(response, "Dica do dia")
        self.assertContains(response, "TEST ONLY tip text.")

    def test_menu_lists_wellbeing_pages_for_every_role(self):
        membership = Membership.objects.get(user=self.user)
        for role in Membership.Role.values:
            membership.role = role
            membership.save()
            response = self.home(local(9))
            nav = (
                response.content.decode().split('class="ql-nav"')[1].split("</nav>")[0]
            )
            with self.subTest(role=role):
                for name, label in zip(
                    SHORTCUTS,
                    ("Ginástica Laboral", "Meditação", "Relaxamento", "Meu Progresso"),
                    strict=True,
                ):
                    self.assertIn(f'href="{reverse(name)}"', nav)
                    self.assertIn(label, nav)
