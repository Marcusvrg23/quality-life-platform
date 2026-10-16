"""Browser QA for spec 14 at 390x844 and 1280x800: login with "Continuar com o
Google", the operator wizard and per-company list, the team page with
"Liberar e-mails" and the report header. No horizontal scroll and no console
error on any of them. Screenshots go to QA_ARTIFACT_DIR/google/.
"""

import os
from pathlib import Path
from unittest import skipIf

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from identity.models import AllowedEmail, Membership, Organization, User
from tests.test_google_login import GOOGLE_PROVIDERS
from tests.test_wellbeing_browser import GSAP_IDLE

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None

PASSWORD = "browser-test-password"
VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
NO_OVERFLOW = "document.documentElement.scrollWidth <= window.innerWidth"
PASTE = (
    "ana@qa-google.test, bruno@qa-google.test;carla@qa-google.test\n"
    "colaborador-com-email-bem-comprido-para-testar-quebra@empresa-exemplo.test\n"
    "invalido\nana@qa-google.test"
)


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class GoogleBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="QA Google", slug="qa-google")
        User.objects.create_superuser("ql-google@example.test", PASSWORD)
        manager = User.objects.create_user("gestora-google@example.test", PASSWORD)
        Membership.objects.create(
            user=manager, organization=self.org, role=Membership.Role.CORPORATE_MANAGER
        )
        for index in range(3):
            AllowedEmail.objects.create(
                organization=self.org, email=f"liberado{index}@qa-google.test"
            )
        AllowedEmail.objects.create(
            organization=self.org,
            email="gestora-google@example.test",
            role=Membership.Role.CORPORATE_MANAGER,
        )

    def open(self, browser, width, height):
        page = browser.new_context(
            viewport={"width": width, "height": height}
        ).new_page()
        page.errors = []
        page.on(
            "console",
            lambda message: (
                message.type == "error" and page.errors.append(message.text)
            ),
        )
        page.on("pageerror", lambda error: page.errors.append(str(error)))
        return page

    def settle(self, page):
        page.wait_for_load_state("load")
        page.wait_for_function(GSAP_IDLE)

    def check(self, page, name, label):
        assert page.evaluate(NO_OVERFLOW), f"Horizontal overflow at {name}: {label}"
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir) / "google"
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / f"{name}-{label}.png"), full_page=True)
        assert page.errors == [], (name, label, page.errors)

    def login(self, page, email):
        page.goto(f"{self.live_server_url}/login/")
        self.settle(page)
        page.get_by_text("Entrar com e-mail e senha").click()
        page.locator("#id_username").fill(email)
        page.locator("#id_password").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_load_state("load")

    def test_login_panel_team_and_report_fit_both_viewports(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for index, (name, width, height) in enumerate(VIEWPORTS):
                # The first viewport adds 4 e-mails on the team page; the second
                # pastes the same list and adds none (no ORM inside this block).
                team_before, team_after = (4, 8) if index == 0 else (8, 8)
                page = self.open(browser, width, height)
                page.goto(f"{self.live_server_url}/login/")
                self.settle(page)
                google = page.get_by_role("button", name="Continuar com o Google")
                expect(google).to_be_visible()
                expect(page.locator("#id_username")).to_be_hidden()
                self.check(page, name, "login")
                page.get_by_text("Entrar com e-mail e senha").click()
                expect(page.locator("#id_username")).to_be_visible()
                self.check(page, name, "login-senha")
                page.context.close()

                page = self.open(browser, width, height)
                self.login(page, "ql-google@example.test")
                assert page.url.endswith("/app/painel/"), page.url
                self.settle(page)
                self.check(page, name, "painel")
                page.locator("#id_name").fill(f"Nova {name}")
                page.locator("#id_collaborators").fill(PASTE)
                page.locator("#id_managers").fill("chefe@qa-google.test")
                page.get_by_role("button", name="Concluir").click()
                page.wait_for_url("**/emails/")
                self.settle(page)
                expect(page.get_by_text("Lista (5)")).to_be_visible()
                expect(
                    page.get_by_text("Ignorados por serem inválidos: invalido.")
                ).to_be_visible()
                self.check(page, name, "painel-nova-empresa")
                page.get_by_role("button", name="Tornar gestor").first.click()
                page.wait_for_load_state("load")
                self.settle(page)
                expect(
                    page.get_by_role("button", name="Voltar a colaborador")
                ).to_have_count(2)
                self.check(page, name, "painel-emails")
                page.context.close()

                page = self.open(browser, width, height)
                self.login(page, "gestora-google@example.test")
                page.goto(f"{self.live_server_url}/app/equipe/")
                self.settle(page)
                expect(
                    page.get_by_text(f"E-mails liberados ({team_before})")
                ).to_be_visible()
                self.check(page, name, "equipe")
                page.locator("#id_emails").fill(PASTE)
                page.get_by_role("button", name="Liberar").click()
                page.wait_for_load_state("load")
                self.settle(page)
                expect(
                    page.get_by_text(f"E-mails liberados ({team_after})")
                ).to_be_visible()
                self.check(page, name, "equipe-liberados")
                page.goto(f"{self.live_server_url}/app/report/")
                self.settle(page)
                expect(
                    page.get_by_text("E-mails liberados", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_text("Pessoas cadastradas", exact=True)
                ).to_be_visible()
                self.check(page, name, "relatorio")
                page.context.close()
            browser.close()
        self.assertEqual(
            Organization.objects.filter(name__startswith="Nova ").count(), 2
        )
        self.assertEqual(AllowedEmail.objects.filter(organization=self.org).count(), 8)
