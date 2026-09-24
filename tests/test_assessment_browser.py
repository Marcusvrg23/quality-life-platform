"""TEST ONLY — NOT PRODUCTION CONTENT. Ephemeral PostgreSQL browser QA."""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
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
    @staticmethod
    def _stored_result(email):
        assessment = Assessment.objects.get(user__email=email)
        result = assessment.result
        pillars = list(
            result.pillars.select_related("pillar").order_by("pillar__display_order")
        )
        return (
            result.overall_score,
            result.overall_band,
            [
                (pillar.pillar.display_order, pillar.score, pillar.band)
                for pillar in pillars
            ],
        )

    def setUp(self):
        primary = Organization.objects.create(name="QA Principal", slug="qa-principal")
        secondary = Organization.objects.create(
            name="QA Secundária", slug="qa-secondary"
        )
        for email in (
            "browser-390@example.test",
            "browser-430@example.test",
            "browser-desktop@example.test",
            "browser-large@example.test",
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
        page.wait_for_function(
            "!window.gsap || gsap.globalTimeline.getChildren(true, true, false).every(t => t.totalProgress() === 1)"
        )
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow at {viewport}: {stage}"
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir)
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(path / f"{viewport}-{stage}.png"),
                full_page=stage != "exercise-open",
            )

    def _agent_checkpoint(self, viewport, stage):
        """Inspect the same live Django page through the required agent-browser CLI."""
        if os.environ.get("QA_AGENT_BROWSER") != "1":
            return
        path = Path(os.environ.get("QA_ARTIFACT_DIR", "qa-artifacts"))
        path.mkdir(parents=True, exist_ok=True)
        base = ["agent-browser", "--session", f"ql-{viewport}", "--cdp", "9222"]
        for command, suffix in (
            (["snapshot", "-i"], "snapshot"),
            (["errors"], "errors"),
        ):
            result = subprocess.run(
                base + command, capture_output=True, text=True, timeout=45, check=True
            )
            (path / f"{viewport}-{stage}-{suffix}.txt").write_text(
                result.stdout, encoding="utf-8"
            )
            if suffix == "snapshot":
                assert "ref=" in result.stdout or "@e" in result.stdout, result.stdout
        subprocess.run(
            base + ["screenshot", str(path / f"{viewport}-{stage}-agent-browser.png")],
            capture_output=True,
            timeout=45,
            check=True,
        )

    def _flow(self, width, height, email):
        viewport = f"{width}x{height}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--remote-debugging-port=9222"])
            page = browser.new_page(
                viewport={"width": width, "height": height}, has_touch=width < 900
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{self.live_server_url}/login/")
            self._capture(page, viewport, "login")
            page.locator("#id_username").fill(email)
            page.locator("#id_password").fill("browser-test-password")
            page.get_by_role("button", name="Entrar").click()
            page.get_by_role("button", name="QA Principal").click()
            page.get_by_role("heading", name="Escolha sua atividade").wait_for()
            self._capture(page, viewport, "dashboard")
            toggle = page.locator(".ql-menu-toggle")
            if width < 900:
                assert toggle.get_attribute("aria-expanded") == "false"
                toggle.click()
                assert toggle.get_attribute("aria-expanded") == "true"
                page.keyboard.press("Escape")
                assert toggle.evaluate("el => el === document.activeElement")
                toggle.click()
                page.locator(".ql-backdrop").click(position={"x": width - 5, "y": 300})
                assert toggle.get_attribute("aria-expanded") == "false"
            else:
                assert toggle.get_attribute("aria-expanded") == "true"
                toggle.click()
                assert toggle.get_attribute("aria-expanded") == "false"
                toggle.click()
            self._agent_checkpoint(viewport, "checkpoint-1")
            page.locator("main").get_by_role("link", name="Explorar exercícios").click()
            page.get_by_role("heading", name="Exercícios", exact=True).wait_for()
            assert page.locator(".exercise-card").count() == 8
            self._capture(page, viewport, "exercises")
            page.get_by_role("button", name="Começar sequência").click()
            assert (
                page.locator("[data-sequence-position]").inner_text()
                == "Exercício 1 de 8"
            )
            page.get_by_role("button", name="Próximo").click()
            assert (
                page.locator("[data-sequence-position]").inner_text()
                == "Exercício 2 de 8"
            )
            page.get_by_role("button", name="Anterior").click()
            self._capture(page, viewport, "exercise-open")
            assert page.get_by_role("button", name="Próximo").evaluate(
                "el => { const r=el.getBoundingClientRect(); return r.bottom <= innerHeight && r.top >= 0; }"
            )
            assert page.get_by_role("button", name="Anterior").is_disabled()
            for index in range(1, 8):
                page.get_by_role("button", name="Próximo").click()
                assert (
                    page.locator("[data-sequence-position]").inner_text()
                    == f"Exercício {index + 1} de 8"
                )
            assert page.get_by_role("button", name="Próximo").is_disabled()
            page.keyboard.press("Escape")
            assert not page.locator("dialog").is_visible()
            page.get_by_role("button", name="Alongamentos sentados", exact=True).click()
            assert page.locator(".exercise-card:visible").count() == 1
            page.get_by_role("button", name="Todos").click()
            self._agent_checkpoint(viewport, "checkpoint-1-5")
            if width < 900:
                toggle.click()
            page.locator(".ql-nav").get_by_role("link", name="Minha avaliação").click()
            page.get_by_role("heading", name="Minha avaliação").wait_for()
            assert page.locator(".ql-topbar").is_visible()
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
            page.locator("#result-title").wait_for()
            with ThreadPoolExecutor(max_workers=1) as pool:
                overall_score, overall_band, pillars = pool.submit(
                    self._stored_result, email
                ).result()
            assert len(pillars) == 9
            assert len({score for _, score, _ in pillars}) == 9
            assert page.locator(".overall-score strong").inner_text() == localize(
                overall_score
            )
            assert page.locator(".overall-band").inner_text() == overall_band
            assert page.locator(".heart-segment").count() == 9
            assert page.locator(".pillar-row").count() == 9
            for order, score, band in pillars:
                row = page.locator(f'.pillar-row[data-pillar="{order}"]')
                assert row.locator(".pillar-score strong").inner_text() == localize(
                    score
                )
                assert row.locator(".pillar-band").inner_text() == band
                assert (
                    page.locator(
                        f'.heart-segment[data-pillar="{order}"]'
                    ).get_attribute("data-band")
                    == band
                )
            self._capture(page, viewport, "result")
            segment = page.locator(".heart-segment").first
            segment.focus()
            assert page.locator(".heart-center-score").inner_text() == localize(
                pillars[0][1]
            )
            page.keyboard.press("Escape")
            assert page.locator(".heart-center-score").inner_text() == localize(
                overall_score
            )
            if width < 900:
                segment.tap()
            else:
                segment.hover()
            assert page.locator(".heart-center-score").inner_text() == localize(
                pillars[0][1]
            )
            page.locator(".quality-map-reset").click()
            assert page.locator(".heart-center-score").inner_text() == localize(
                overall_score
            )
            self._agent_checkpoint(viewport, "checkpoint-2")
            page.reload()
            page.locator("#result-title").wait_for()
            page.emulate_media(reduced_motion="reduce")
            page.reload()
            assert page.locator(".heart-segment").count() == 9
            self._capture(page, viewport, "reduced-motion")
            assert page.evaluate(
                "[...document.images].every(i => i.complete && i.naturalWidth > 0)"
            )
            self._agent_checkpoint(viewport, "final")
            page.route("**/gsap-3.13.0.min.js", lambda route: route.abort())
            page.reload()
            page.locator(".heart-segment").first.focus()
            assert page.locator(".heart-center-score").inner_text() == localize(
                pillars[0][1]
            )
            page.locator(".quality-map-reset").click()
            assert page.locator(".heart-center-score").inner_text() == localize(
                overall_score
            )
            assert errors == [], errors
            if width < 900:
                page.locator(".ql-menu-toggle").click()
            page.get_by_role("button", name="Sair", exact=False).click()
            page.wait_for_url("**/login/")
            browser.close()

    def test_flow_both_viewports(self):
        self._flow(390, 844, "browser-390@example.test")
        self._flow(430, 932, "browser-430@example.test")
        self._flow(1366, 768, "browser-desktop@example.test")
        self._flow(1440, 900, "browser-large@example.test")
