"""Browser QA for the installable app and break reminders
(docs/specs/13-pwa-lembretes.md, aceite 2, 4, 6 e 7) at 390x844 and 1280x800.

No horizontal scroll, no console error and AA contrast on the new pages; no
notification permission is requested before the "Ativar lembretes" click; the
service worker stores no /app/ page; with a simulated clock the in-page notice
shows up at the configured time. Screenshots go to QA_ARTIFACT_DIR/pwa/.
"""

import os
from datetime import datetime
from pathlib import Path
from unittest import skipIf
from zoneinfo import ZoneInfo

from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from identity.models import Membership, Organization, User
from tests.test_app_dark_browser import CONTRAST
from wellbeing.models import ReminderSetting

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None

PASSWORD = "browser-test-password"
VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
PAGES = (("instalar", "/app/instalar/"), ("lembretes", "/app/lembretes/"))
MESSAGE = "Hora da pausa. Que tal alguns minutos de Ginástica Laboral?"
TIMEZONE = "America/Sao_Paulo"
# Counts permission requests across navigations of the tab and keeps the
# permission at "default" (headless browsers may answer on their own).
COUNT_PERMISSION = """(() => {
    if (!('Notification' in window)) return;
    const key = '__qlPermissionRequests';
    Object.defineProperty(Notification, 'permission', {
        configurable: true, get: () => 'default',
    });
    Notification.requestPermission = () => {
        sessionStorage.setItem(key, String(Number(sessionStorage.getItem(key) || 0) + 1));
        return Promise.resolve('default');
    };
})();"""
PERMISSION_REQUESTS = "Number(sessionStorage.getItem('__qlPermissionRequests') || 0)"
STANDALONE = """(() => {
    const original = window.matchMedia.bind(window);
    window.matchMedia = query => query.includes('display-mode: standalone')
        ? { matches: true, media: query, onchange: null, addListener() {}, removeListener() {},
            addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; } }
        : original(query);
})();"""
CACHED_REQUESTS = """async () => {
    const entries = [];
    for (const key of await caches.keys()) {
        const cache = await caches.open(key);
        for (const request of await cache.keys()) {
            entries.push(request.method + ' ' + new URL(request.url).pathname);
        }
    }
    return entries;
}"""
INSTALL_OFFER = """() => {
    const offer = new Event('beforeinstallprompt', { cancelable: true });
    offer.prompt = () => Promise.resolve();
    offer.userChoice = Promise.resolve({ outcome: 'accepted' });
    window.dispatchEvent(offer);
}"""


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class PwaBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        organization = Organization.objects.create(name="QA PWA", slug="qa-pwa")
        self.user = User.objects.create_user("pwa@example.test", PASSWORD)
        self.membership = Membership.objects.create(
            user=self.user,
            organization=organization,
            role=Membership.Role.COLLABORATOR,
        )

    # Helpers -----------------------------------------------------------------

    def open(self, browser, width=390, height=844, clock=None, init=()):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            timezone_id=TIMEZONE,
            locale="pt-BR",
        )
        context.add_init_script(COUNT_PERMISSION)
        for script in init:
            context.add_init_script(script)
        page = context.new_page()
        if clock is not None:
            page.clock.install(time=clock)
        page.errors = []
        page.on(
            "console",
            lambda message: (
                message.type == "error" and page.errors.append(message.text)
            ),
        )
        page.on("pageerror", lambda error: page.errors.append(str(error)))
        page.goto(f"{self.live_server_url}/login/")
        page.locator("#id_username").fill(self.user.email)
        page.locator("#id_password").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_load_state("load")
        return page

    def visit(self, page, path):
        page.goto(f"{self.live_server_url}{path}")
        page.wait_for_load_state("load")
        # The reminder scheduler finished reading the owner's agenda.
        page.wait_for_function(
            "document.querySelector('script[data-schedule]')?.dataset.state === 'loaded'"
        )

    def screenshot(self, page, name):
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir) / "pwa"
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / f"{name}.png"), full_page=True)

    def assert_fits(self, page, label):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow: {label}"
        assert page.errors == [], (label, page.errors)

    # Tests -------------------------------------------------------------------

    def test_pages_fit_have_contrast_and_ask_no_permission(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                for slug, path in PAGES:
                    self.visit(page, path)
                    label = f"{name}-{slug}"
                    self.assert_fits(page, label)
                    assert page.evaluate(PERMISSION_REQUESTS) == 0, label
                    contrast = page.evaluate(CONTRAST)
                    assert contrast["failures"] == [], (label, contrast["failures"][:6])
                    self.screenshot(page, label)
                page.context.close()
            browser.close()

    def test_install_button_only_with_browser_offer(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser)
            self.visit(page, "/app/instalar/")
            button = page.get_by_role("button", name="Adicionar à tela inicial")
            expect(button).to_be_hidden()
            expect(page.get_by_text("Adicionar à Tela de Início")).to_be_visible()
            expect(
                page.get_by_text("Apps na App Store e no Google Play: em breve.")
            ).to_be_visible()
            installed = page.get_by_text("O app já está na sua tela inicial.")
            expect(installed).to_be_hidden()
            page.evaluate(INSTALL_OFFER)
            expect(button).to_be_visible()
            self.assert_fits(page, "instalar-oferta")
            button.click()
            expect(installed).to_be_visible()
            expect(button).to_be_hidden()
            assert page.evaluate(PERMISSION_REQUESTS) == 0
            browser.close()

    def test_installed_app_says_so(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser, init=[STANDALONE])
            self.visit(page, "/app/instalar/")
            expect(
                page.get_by_text("O app já está na sua tela inicial.")
            ).to_be_visible()
            expect(page.get_by_text("Adicionar à Tela de Início")).to_be_hidden()
            self.assert_fits(page, "instalar-standalone")
            browser.close()

    def test_permission_only_on_activate_click(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser)
            self.visit(page, "/app/lembretes/")
            assert page.evaluate(PERMISSION_REQUESTS) == 0
            page.get_by_role("button", name="Ativar lembretes").click()
            expect(
                page.get_by_role("button", name="Desativar lembretes")
            ).to_be_visible()
            assert page.evaluate(PERMISSION_REQUESTS) == 1
            setting = ReminderSetting.objects.get(membership=self.membership)
            assert setting.active
            # Saving again does not ask again.
            page.get_by_role("button", name="Salvar alterações").click()
            expect(
                page.get_by_role("button", name="Desativar lembretes")
            ).to_be_visible()
            assert page.evaluate(PERMISSION_REQUESTS) == 1
            self.assert_fits(page, "lembretes-ativos")
            browser.close()

    def test_notice_appears_at_configured_time(self):
        ReminderSetting.objects.create(membership=self.membership, active=True)
        zone = ZoneInfo(TIMEZONE)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                # Monday 19/10/2026; 08:00-18:00 every 60 min -> next at 10:00.
                page = self.open(
                    browser,
                    width,
                    height,
                    clock=datetime(2026, 10, 19, 9, 57, tzinfo=zone),
                )
                self.visit(page, "/app/")
                page.clock.pause_at(datetime(2026, 10, 19, 9, 59, 30, tzinfo=zone))
                notice = page.locator("[data-reminder-notice]")
                expect(notice).to_have_count(0)
                page.clock.fast_forward("01:00")
                expect(notice).to_be_visible()
                expect(notice).to_contain_text(MESSAGE)
                start = notice.get_by_role("link", name="Começar a pausa")
                assert start.get_attribute("href") == "/app/ginastica/"
                self.assert_fits(page, f"{name}-aviso")
                assert page.evaluate(PERMISSION_REQUESTS) == 0
                self.screenshot(page, f"{name}-aviso")
                notice.get_by_role("button", name="Agora não").click()
                expect(notice).to_be_hidden()
                page.context.close()
            browser.close()

    def test_service_worker_stores_no_app_page_and_serves_offline_page(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser)
            self.visit(page, "/app/")
            page.evaluate("navigator.serviceWorker.ready.then(() => true)")
            for path in ("/app/lembretes/", "/app/progresso/", "/app/"):
                self.visit(page, path)
            assert page.evaluate("Boolean(navigator.serviceWorker.controller)")
            entries = page.evaluate(CACHED_REQUESTS)
            assert "GET /offline/" in entries, entries
            assert all(
                entry.startswith("GET /static/") or entry == "GET /offline/"
                for entry in entries
            ), entries
            page.context.set_offline(True)
            page.goto(f"{self.live_server_url}/app/progresso/")
            expect(page.get_by_text("Sem conexão. Tente de novo.")).to_be_visible()
            page.context.set_offline(False)
            assert page.evaluate(CACHED_REQUESTS) == entries
            browser.close()
