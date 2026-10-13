"""Questionnaire v2 end to end in a real browser at 390x844 (Playwright)."""

import os
from importlib import import_module
from io import StringIO
from pathlib import Path
from unittest import skipIf

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command

from assessments.models import Assessment, Pillar
from identity.models import Membership, Organization

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

NINE_PILLARS = import_module("assessments.migrations.0002_nine_pillars")
V2_FILE = (
    Path(settings.BASE_DIR)
    / "assessments"
    / "questionnaires"
    / "quality_life_oficial_v2.json"
)
EMAIL = "browser-v2@example.test"
PASSWORD = "browser-test-password"
NAME = "Ana Souza Teste"
TOTAL = 101


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class QuestionnaireV2BrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        # Live-server tests flush the database; restore migration 0002's pillars.
        for order, (code, name) in enumerate(NINE_PILLARS.PILLARS, start=1):
            Pillar.objects.get_or_create(
                code=code, defaults={"name": name, "display_order": order}
            )
        call_command(
            "load_official_questionnaire", file=str(V2_FILE), stdout=StringIO()
        )
        user = get_user_model().objects.create_user(email=EMAIL, password=PASSWORD)
        for name, slug in (("QA v2", "qa-v2"), ("QA v2 Outra", "qa-v2-outra")):
            organization = Organization.objects.create(name=name, slug=slug)
            Membership.objects.create(
                user=user, organization=organization, role=Membership.Role.COLLABORATOR
            )

    def check_layout(self, page, stage, screenshot=False):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow at 390x844: {stage}"
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if screenshot and artifact_dir:
            path = Path(artifact_dir)
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / f"v2-390x844-{stage}.png"), full_page=True)

    def answer(self, page, position):
        text = page.locator("#answer-text")
        boxes = page.locator('input[name="options"]')
        if text.count():
            label = page.locator(".question-label").inner_text()
            if "(opcional)" in label:
                return "skipped"
            value = NAME if position == 1 else f"Resposta {position}"
            text.fill(value)
            counter = page.locator("#answer-count").inner_text()
            assert (
                counter == f"{len(value)}/{text.get_attribute('maxlength')} caracteres"
            )
            return "text"
        if boxes.count():
            exclusive = page.locator('input[name="options"][data-exclusive]')
            exclusive.check()
            boxes.first.check()
            assert not exclusive.is_checked(), "exclusive option stayed checked"
            return "multiple"
        if page.locator('input[name="other_text"]').count():
            page.locator("label.option", has_text="Outro:").locator("input").check()
            page.locator('input[name="other_text"]').fill("Logística")
            return "other"
        if "(opcional)" in page.locator("legend").inner_text():
            return "skipped"
        page.locator('input[name="option"]').first.check()
        return "choice"

    def test_full_flow_at_390x844(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(
                viewport={"width": 390, "height": 844}, has_touch=True
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{self.live_server_url}/login/")
            page.locator("#id_username").fill(EMAIL)
            page.locator("#id_password").fill(PASSWORD)
            page.get_by_role("button", name="Entrar").click()
            page.get_by_role("button", name="QA v2", exact=True).click()
            page.goto(f"{self.live_server_url}/app/assessment/")
            page.get_by_role("heading", name="Minha avaliação").wait_for()
            self.check_layout(page, "hub", screenshot=True)

            # Consent stays mandatory: the browser refuses to start without it.
            page.get_by_role("button", name="Iniciar avaliação").click()
            page.get_by_role("heading", name="Minha avaliação").wait_for()
            page.locator('input[name="consent"]').check()
            page.get_by_role("button", name="Iniciar avaliação").click()

            kinds = {}
            sections = []
            for position in range(1, TOTAL + 1):
                page.get_by_role(
                    "heading", name=f"Pergunta {position} de {TOTAL}"
                ).wait_for()
                section = page.locator(".card .eyebrow").first.inner_text()
                if not sections or sections[-1] != section:
                    sections.append(section)
                kind = self.answer(page, position)
                kinds[kind] = kinds.get(kind, 0) + 1
                self.check_layout(
                    page,
                    f"question-{position}",
                    screenshot=position in (1, 3, 12, 81, 101),
                )
                last = position == TOTAL
                page.get_by_role(
                    "button", name="Salvar e revisar" if last else "Salvar e próxima"
                ).click()

            page.get_by_role("heading", name="Revisar respostas").wait_for()
            assert page.get_by_text(f"{TOTAL - 2} de {TOTAL} perguntas").count()
            self.check_layout(page, "review", screenshot=True)
            page.get_by_role("button", name="Concluir avaliação").click()
            page.locator("#result-title").wait_for()
            page.wait_for_function(
                "!window.gsap || gsap.globalTimeline.getChildren(true, true, false)"
                ".every(t => t.totalProgress() === 1)"
            )
            assert page.get_by_text("Nome do colaborador").is_visible()
            assert page.get_by_text(NAME).is_visible()
            assert page.get_by_text("Data da avaliação").is_visible()
            self.check_layout(page, "result", screenshot=True)
            browser.close()

        self.assertEqual(errors, [])
        self.assertEqual(len(sections), 12)
        self.assertTrue(sections[0].startswith("1. IDENTIFICA"))
        self.assertTrue(sections[-1].startswith("12. SUA PRINCIPAL"))
        self.assertEqual(
            kinds,
            {"text": 3, "other": 1, "multiple": 2, "skipped": 2, "choice": 93},
        )
        self.assertEqual(
            Assessment.objects.get(user__email=EMAIL).status,
            Assessment.Status.COMPLETED,
        )
