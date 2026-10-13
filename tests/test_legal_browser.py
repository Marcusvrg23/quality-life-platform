"""Browser QA: no horizontal scroll at 390x844 on consent and legal pages."""

from decimal import Decimal
from unittest import skipIf

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from assessments.models import (
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


def no_horizontal_scroll(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class LegalBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        organization = Organization.objects.create(
            name="QA Privacidade Empresa Com Nome Longo", slug="qa-privacidade"
        )
        user = get_user_model().objects.create_user(
            email="privacidade-390@example.test", password="browser-test-password"
        )
        Membership.objects.create(
            user=user, organization=organization, role=Membership.Role.COLLABORATOR
        )
        version = QuestionnaireVersion.objects.create(
            code="test-only-legal-browser",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-legal-browser",
        )
        configured = QuestionnairePillar.objects.create(
            questionnaire=version,
            # Earlier live-server tests flush the migration-seeded pillars.
            pillar=Pillar.objects.get_or_create(
                code="physical_health",
                defaults={"name": "Saúde Física", "display_order": 1},
            )[0],
            display_order=1,
            weight=Decimal(1),
        )
        question = Question.objects.create(
            questionnaire_pillar=configured,
            code="only",
            text="TEST ONLY — question?",
            weight=Decimal(1),
            display_order=1,
        )
        for order, score in enumerate((0, 100), 1):
            QuestionOption.objects.create(
                question=question,
                code=f"test-{score}",
                label=f"TEST ONLY choice {order}",
                score_value=Decimal(score),
                display_order=order,
            )
        publish_questionnaire(version.pk)

    def test_no_horizontal_scroll_at_390(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            for stage, url in (
                ("privacidade", "/privacidade/"),
                ("termos", "/termos/"),
            ):
                page.goto(f"{self.live_server_url}{url}")
                page.wait_for_load_state("load")
                page.get_by_text("MINUTA — pendente de revisão jurídica").wait_for()
                assert no_horizontal_scroll(page), f"Horizontal overflow: {stage}"

            page.goto(f"{self.live_server_url}/login/")
            assert no_horizontal_scroll(page), "Horizontal overflow: login"
            page.locator("#id_username").fill("privacidade-390@example.test")
            page.locator("#id_password").fill("browser-test-password")
            page.get_by_role("button", name="Entrar").click()
            page.get_by_role("heading", name="Escolha sua atividade").wait_for()

            page.goto(f"{self.live_server_url}/app/assessment/")
            consent = page.locator('input[name="consent"]')
            assert not consent.is_checked()
            assert no_horizontal_scroll(page), "Horizontal overflow: hub consent"
            consent.check()
            page.get_by_role("button", name="Iniciar avaliação").click()
            page.get_by_role("heading", name="Pergunta 1 de 1").wait_for()

            page.goto(f"{self.live_server_url}/app/privacidade/")
            page.get_by_role("button", name="Revogar").wait_for()
            assert no_horizontal_scroll(page), "Horizontal overflow: privacy settings"
            page.locator('input[name="confirm"]').check()
            page.get_by_role("button", name="Revogar").click()
            page.get_by_text("Autorização revogada").wait_for()
            assert no_horizontal_scroll(page), "Horizontal overflow: after revoke"
            browser.close()
