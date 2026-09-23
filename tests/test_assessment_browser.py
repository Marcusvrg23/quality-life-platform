"""TEST ONLY — NOT PRODUCTION CONTENT. Ephemeral PostgreSQL browser QA."""

import os
from decimal import Decimal
from pathlib import Path
from unittest import skipIf

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils.formats import localize

from assessments.models import (
    Assessment,
    Pillar,
    Question,
    QuestionnairePillar,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import publish_questionnaire
from identity.models import Membership, Organization

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class AssessmentBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        primary = Organization.objects.create(name="QA Principal", slug="qa-principal")
        secondary = Organization.objects.create(
            name="QA Secundária", slug="qa-secondary"
        )
        for email in (
            "browser-390@example.test",
            "browser-430@example.test",
            "browser-desktop@example.test",
        ):
            user = get_user_model().objects.create_user(
                email=email, password="browser-test-password"
            )
            for organization in (primary, secondary):
                Membership.objects.create(
                    user=user,
                    organization=organization,
                    role=Membership.Role.COLLABORATOR,
                )
        version = QuestionnaireVersion.objects.create(
            code="browser-test-only",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="browser-test",
        )
        for order, pillar in enumerate(Pillar.objects.order_by("display_order"), 1):
            configured = QuestionnairePillar.objects.create(
                questionnaire=version,
                pillar=pillar,
                weight=Decimal(1),
                display_order=order,
            )
            question = Question.objects.create(
                questionnaire_pillar=configured,
                code=f"qa-{order}",
                text=f"TEST ONLY — pergunta {order}?",
                weight=Decimal(1),
                display_order=1,
            )
            for option_order, score in enumerate(range(0, 101, 10), 1):
                QuestionOption.objects.create(
                    question=question,
                    code=f"qa-{option_order}",
                    label=f"TEST ONLY alternativa {option_order}",
                    score_value=Decimal(score),
                    display_order=option_order,
                )
        publish_questionnaire(version.pk)

    def _capture(self, page, viewport, stage):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow at {viewport}: {stage}"
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir)
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / f"{viewport}-{stage}.png"), full_page=True)

    def _flow(self, width, height, email):
        viewport = f"{width}x{height}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"{self.live_server_url}/login/")
            page.locator("#id_username").fill(email)
            page.locator("#id_password").fill("browser-test-password")
            page.get_by_role("button", name="Entrar").click()
            page.get_by_role("button", name="QA Principal").click()
            page.get_by_role("link", name="Minha avaliação").click()
            page.get_by_role("heading", name="Minha avaliação").wait_for()
            assert (
                page.locator(".site-header").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(22, 77, 73)"
            )
            self._capture(page, viewport, "hub")
            page.get_by_role("button", name="Iniciar avaliação").click()
            page.get_by_role("heading", name="Pergunta 1 de 9").wait_for()
            self._capture(page, viewport, "question")
            first = page.locator('input[name="option"]').first
            first.focus()
            assert first.evaluate("element => element === document.activeElement")
            page.keyboard.press("Space")
            assert first.is_checked()
            page.get_by_role("button", name="Salvar e próxima").click()
            page.get_by_role("heading", name="Pergunta 2 de 9").wait_for()
            page.get_by_role("link", name="Pergunta anterior").click()
            page.reload()
            assert page.locator('input[name="option"]').first.is_checked()
            page.get_by_role("link", name="Próxima pergunta sem salvar").click()
            for question_number in range(2, 10):
                page.locator('input[name="option"]').nth(question_number - 1).check()
                if question_number == 9:
                    page.get_by_role("button", name="Salvar e revisar").click()
                else:
                    page.get_by_role("button", name="Salvar e próxima").click()
            page.get_by_role("heading", name="Revisar respostas").wait_for()
            self._capture(page, viewport, "review")
            page.get_by_role("button", name="Concluir avaliação").click()
            page.get_by_role("heading", name="Mapa de Qualidade de Vida").wait_for()
            assessment = Assessment.objects.get(user__email=email)
            result = assessment.result
            pillars = list(
                result.pillars.select_related("pillar").order_by(
                    "pillar__display_order"
                )
            )
            assert len(pillars) == 9
            assert len({pillar.score for pillar in pillars}) == 9
            assert page.locator(".overall-score strong").inner_text() == localize(
                result.overall_score
            )
            assert page.locator(".overall-band").inner_text() == result.overall_band
            assert page.locator(".heart-segment").count() == 9
            assert page.locator(".pillar-row").count() == 9
            for pillar in pillars:
                row = page.locator(
                    f'.pillar-row[data-pillar="{pillar.pillar.display_order}"]'
                )
                assert row.locator(".pillar-score strong").inner_text() == localize(
                    pillar.score
                )
                assert row.locator(".pillar-band").inner_text() == pillar.band
                assert (
                    page.locator(
                        f'.heart-segment[data-pillar="{pillar.pillar.display_order}"]'
                    ).get_attribute("data-band")
                    == pillar.band
                )
            self._capture(page, viewport, "result")
            page.reload()
            page.get_by_role("heading", name="Mapa de Qualidade de Vida").wait_for()
            browser.close()

    def test_flow_both_viewports(self):
        self._flow(390, 844, "browser-390@example.test")
        self._flow(430, 932, "browser-430@example.test")
        self._flow(1280, 800, "browser-desktop@example.test")
