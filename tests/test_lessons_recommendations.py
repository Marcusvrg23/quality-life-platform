"""Lessons page, deterministic home recommendation and commemorative dates."""

import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from assessments.models import (
    Assessment,
    AssessmentResult,
    Pillar,
    PillarResult,
    QuestionnaireVersion,
)
from config.calendar_highlights import active_highlight
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization

PASSWORD = "lessons-test-password-81"
CVV = "Precisa conversar? CVV — ligue 188, 24 horas, gratuito."
TODAY = "config.calendar_highlights.timezone.localdate"
# Removed from the screen in spec 15; it must never come back.
PLACEHOLDER_TEXT = "Conteúdo em definição pela Quality Life"
QUIET_DAY = datetime.date(2026, 10, 12)
EXERCISE_CODES = ("physical_activity", "ergonomics_workplace", "physical_health")


def main_content(response):
    return response.content.decode().split("<main", 1)[1].split("</main>", 1)[0]


class HighlightRuleTests(SimpleTestCase):
    def test_fixed_dates_and_whole_month(self):
        for day, title in (
            (datetime.date(2026, 3, 8), "Dia Internacional da Mulher"),
            (datetime.date(2026, 5, 1), "Dia do Trabalhador"),
            (datetime.date(2026, 9, 1), "Setembro Amarelo"),
            (datetime.date(2026, 9, 15), "Setembro Amarelo"),
            (datetime.date(2026, 9, 30), "Setembro Amarelo"),
        ):
            with self.subTest(day=day):
                self.assertIn(title, active_highlight(day).title)

    def test_other_days_have_no_highlight(self):
        for day in (
            datetime.date(2026, 5, 2),
            datetime.date(2026, 3, 9),
            datetime.date(2026, 8, 31),
            datetime.date(2026, 10, 1),
        ):
            with self.subTest(day=day):
                self.assertIsNone(active_highlight(day))

    def test_default_date_comes_from_timezone_localdate(self):
        with mock.patch(TODAY, return_value=datetime.date(2026, 5, 1)):
            self.assertEqual(active_highlight().title, "Dia do Trabalhador")


class HomeTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Empresa A", slug="empresa-a")
        self.other_org = Organization.objects.create(name="Empresa B", slug="empresa-b")
        self.user = self.member(self.org, "colab@a.test", Membership.Role.COLLABORATOR)
        self.version = QuestionnaireVersion.objects.create(
            code="rec-test", version=1, title="TEST", scoring_version="rec-test"
        )
        self.pillars = list(Pillar.objects.order_by("display_order"))

    def member(self, org, email, role):
        user = get_user_model().objects.create_user(email, PASSWORD)
        Membership.objects.create(user=user, organization=org, role=role)
        return user

    def login(self, user, org=None):
        self.client.force_login(user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = (org or self.org).pk
        session.save()

    def complete(self, user, org, scores, completed_at=None):
        """scores: {pillar code: score}; the other pillars get 90."""
        assessment = Assessment.objects.create(
            user=user, organization=org, questionnaire_version=self.version
        )
        result = AssessmentResult.objects.create(
            assessment=assessment,
            overall_score=Decimal("70.00"),
            overall_band="BOM",
            scoring_version="rec-test",
        )
        for pillar in self.pillars:
            PillarResult.objects.create(
                assessment_result=result,
                pillar=pillar,
                score=Decimal(scores.get(pillar.code, 90)),
                band="ATENÇÃO",
            )
        assessment.status = Assessment.Status.COMPLETED
        assessment.completed_at = completed_at or timezone.now()
        assessment.save()
        return assessment

    def home(self, today=QUIET_DAY):
        with mock.patch(TODAY, return_value=today):
            return self.client.get(reverse("app"))


class LessonsPageTests(HomeTestCase):
    def test_requires_login(self):
        response = self.client.get(reverse("lessons"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_requires_active_organization(self):
        self.client.force_login(self.user)
        Membership.objects.update(is_active=False)
        self.assertEqual(self.client.get(reverse("lessons")).status_code, 403)

    def test_lists_three_videos_with_static_sources_and_final_texts(self):
        self.login(self.user)
        response = self.client.get(reverse("lessons"))
        self.assertEqual(response.status_code, 200)
        html = main_content(response)
        self.assertEqual(html.count("<video"), 3)
        self.assertEqual(html.count(" controls"), 3)
        self.assertEqual(html.count(" playsinline"), 3)
        self.assertEqual(html.count('preload="none"'), 3)
        for slug in ("inicio-trabalho", "durante-trabalho", "final-trabalho"):
            self.assertIn(f'src="/static/quality_life/videos/{slug}.mp4"', html)
            self.assertIn(
                f'poster="/static/quality_life/images/posters/{slug}.jpg"', html
            )
        for text in (
            "Início do trabalho",
            "PREPARAÇÃO",
            "Atividade curta para ativar o corpo antes de começar a jornada de trabalho.",
            "Durante o trabalho",
            "PAUSA ATIVA",
            "Pausa guiada para recuperar a mobilidade e aliviar a tensão do expediente.",
            "Final do trabalho",
            "RECUPERAÇÃO",
            "Sequência leve para desacelerar e encerrar a jornada com uma rotina de recuperação.",
        ):
            self.assertIn(text, html)

    def test_static_files_exist(self):
        from django.contrib.staticfiles import finders

        for slug in ("inicio-trabalho", "durante-trabalho", "final-trabalho"):
            self.assertIsNotNone(finders.find(f"quality_life/videos/{slug}.mp4"))
            self.assertIsNotNone(
                finders.find(f"quality_life/images/posters/{slug}.jpg")
            )

    def test_menu_has_lessons_for_every_role_and_keeps_other_links(self):
        for role in Membership.Role.values:
            user = self.member(self.org, f"{role}@a.test", role)
            self.login(user)
            html = self.client.get(reverse("app")).content.decode()
            self.assertIn(f'href="{reverse("lessons")}"', html)
            self.assertIn(f'href="{reverse("password_change")}"', html)
            managerial = role in (
                Membership.Role.CORPORATE_MANAGER,
                Membership.Role.ADMIN,
            )
            for name in ("executive_report", "team"):
                self.assertEqual(
                    f'href="{reverse(name)}"' in html, managerial, (role, name)
                )

    def test_manager_links_still_work(self):
        manager = self.member(
            self.org, "gestor@a.test", Membership.Role.CORPORATE_MANAGER
        )
        self.login(manager)
        for name in ("executive_report", "team", "password_change"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class RecommendationTests(HomeTestCase):
    def test_picks_lowest_pillar_and_links_exercises_for_physical_ones(self):
        self.complete(self.user, self.org, {"ergonomics_workplace": 20, "sleep": 40})
        self.login(self.user)
        html = main_content(self.home())
        self.assertIn("Sua prioridade agora: Ergonomia e Ambiente de Trabalho", html)
        self.assertIn(
            f'class="recommendation-link" href="{reverse("exercises")}"', html
        )
        self.assertNotIn(PLACEHOLDER_TEXT, html)

    def test_other_pillar_links_assessment_without_placeholder(self):
        other = next(p for p in self.pillars if p.code not in EXERCISE_CODES)
        self.complete(self.user, self.org, {other.code: 10})
        self.login(self.user)
        html = main_content(self.home())
        self.assertIn(f"Sua prioridade agora: {other.name}", html)
        self.assertNotIn(PLACEHOLDER_TEXT, html)
        self.assertIn(
            f'class="recommendation-link" href="{reverse("assessment_hub")}"', html
        )

    def test_tie_is_decided_by_display_order(self):
        first, second = self.pillars[3], self.pillars[6]
        self.complete(self.user, self.org, {first.code: 30, second.code: 30})
        self.login(self.user)
        html = main_content(self.home())
        self.assertIn(f"Sua prioridade agora: {first.name}", html)
        self.assertNotIn(second.name, html)

    def test_uses_latest_completed_assessment(self):
        old = timezone.now() - datetime.timedelta(days=30)
        self.complete(self.user, self.org, {self.pillars[0].code: 5}, completed_at=old)
        self.complete(self.user, self.org, {self.pillars[1].code: 5})
        self.login(self.user)
        self.assertIn(
            f"Sua prioridade agora: {self.pillars[1].name}", main_content(self.home())
        )

    def test_without_completed_assessment_invites_to_assess(self):
        Assessment.objects.create(
            user=self.user, organization=self.org, questionnaire_version=self.version
        )
        self.login(self.user)
        html = main_content(self.home())
        self.assertNotIn("Sua prioridade agora", html)
        self.assertIn("Faça sua avaliação", html)
        self.assertIn(f'href="{reverse("assessment_hub")}"', html)

    def test_never_uses_another_user_or_another_company(self):
        mate = self.member(self.org, "mate@a.test", Membership.Role.COLLABORATOR)
        self.complete(mate, self.org, {self.pillars[2].code: 1})
        Membership.objects.create(
            user=self.user,
            organization=self.other_org,
            role=Membership.Role.COLLABORATOR,
        )
        self.complete(self.user, self.other_org, {self.pillars[4].code: 1})
        self.login(self.user)
        html = main_content(self.home())
        self.assertIn("Faça sua avaliação", html)
        self.assertNotIn("Sua prioridade agora", html)
        self.login(self.user, self.other_org)
        self.assertIn(
            f"Sua prioridade agora: {self.pillars[4].name}", main_content(self.home())
        )


class CommemorativeNoticeTests(HomeTestCase):
    def test_notice_on_fixed_days_and_whole_september(self):
        self.login(self.user)
        for day, title in (
            (datetime.date(2026, 3, 8), "Dia Internacional da Mulher"),
            (datetime.date(2026, 5, 1), "Dia do Trabalhador"),
            (datetime.date(2026, 9, 15), "Setembro Amarelo"),
        ):
            with self.subTest(day=day):
                html = main_content(self.home(day))
                self.assertIn(title, html)
                self.assertNotIn(PLACEHOLDER_TEXT, html)

    def test_no_notice_on_ordinary_day(self):
        self.login(self.user)
        html = main_content(self.home(datetime.date(2026, 5, 2)))
        self.assertNotIn("Dia do Trabalhador", html)
        self.assertNotIn(PLACEHOLDER_TEXT, html)

    def test_cvv_only_in_september(self):
        self.login(self.user)
        self.assertIn(CVV, main_content(self.home(datetime.date(2026, 9, 15))))
        for day in (datetime.date(2026, 3, 8), datetime.date(2026, 5, 1), QUIET_DAY):
            with self.subTest(day=day):
                self.assertNotIn("CVV", main_content(self.home(day)))
