"""Browser QA for the installable app and break reminders
(docs/specs/13-pwa-lembretes.md, aceite 2, 4, 6 e 7) at 390x844 and 1280x800.

No horizontal scroll, no console error and AA contrast on the new pages; no
notification permission is requested before the "Ativar lembretes" click; the
service worker stores no /app/ page; with a simulated clock the in-page notice
shows up at the configured time. Screenshots go to QA_ARTIFACT_DIR/pwa/.
"""

import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest import skipIf
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import override_settings
from py_vapid import Vapid, b64urlencode

from identity.models import Membership, Organization, User
from tests.test_app_dark_browser import CONTRAST
from tests.test_wellbeing_browser import GSAP_IDLE
from wellbeing.models import PushSubscription, ReminderSetting

try:
    from playwright.sync_api import Error as PlaywrightError
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
# Notification permission granted and a PushManager that never talks to a push
# service: subscriptions live in sessionStorage so they survive navigations.
FAKE_ENDPOINT = "https://push.example.test/device-1"
FAKE_PUSH = """(() => {
    if (!('Notification' in window)) return;
    Object.defineProperty(Notification, 'permission', {
        configurable: true, get: () => 'granted',
    });
    const KEY = '__qlFakePush';
    const read = () => JSON.parse(sessionStorage.getItem(KEY) || 'null');
    const write = value => sessionStorage.setItem(KEY, JSON.stringify(value));
    const wrap = stored => stored && ({
        endpoint: stored.endpoint,
        options: { applicationServerKey: Uint8Array.from(stored.key).buffer },
        toJSON() {
            return { endpoint: stored.endpoint,
                     keys: { p256dh: 'BFakeP256dhKeyForTheTest', auth: 'fakeAuthForTheTest' } };
        },
        unsubscribe() { write(null); return Promise.resolve(true); },
    });
    const manager = {
        getSubscription: () => Promise.resolve(wrap(read())),
        subscribe: options => {
            const stored = { endpoint: 'ENDPOINT_PLACEHOLDER',
                             key: Array.from(new Uint8Array(options.applicationServerKey)) };
            write(stored);
            return Promise.resolve(wrap(stored));
        },
    };
    Object.defineProperty(ServiceWorkerRegistration.prototype, 'pushManager', {
        configurable: true, get: () => manager,
    });
    if (!('PushManager' in window)) window.PushManager = function PushManager() {};
})();""".replace("ENDPOINT_PLACEHOLDER", FAKE_ENDPOINT)
PUSH_ACTIVE = "Notificações ativas neste aparelho, mesmo com o app fechado."
PUSH_INACTIVE = (
    "Notificações permitidas neste aparelho. Ative os lembretes para recebê-las "
    "mesmo com o app fechado."
)
INSTALL_OFFER = """() => {
    const offer = new Event('beforeinstallprompt', { cancelable: true });
    offer.prompt = () => Promise.resolve();
    offer.userChoice = Promise.resolve({ outcome: 'accepted' });
    window.dispatchEvent(offer);
}"""


def vapid_public_key():
    """A fresh, valid application server key; the private half is never used."""
    vapid = Vapid()
    vapid.generate_keys()
    return b64urlencode(
        vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )


def presubscribed(key):
    """The device already holds a subscription for ``key`` (another visit)."""
    raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
    stored = json.dumps({"endpoint": FAKE_ENDPOINT, "key": list(raw)})
    return f"sessionStorage.setItem('__qlFakePush', {json.dumps(stored)});"


def in_thread(function):
    """Run an ORM query outside Playwright's event loop (committed data)."""

    def query():
        try:
            return function()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(query).result()


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

    def open(self, browser, width=390, height=844, clock=None, init=(), device=None):
        context = browser.new_context(
            **(device or {}),
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
        # The login POST must finish before the next goto, or WebKit cancels it.
        page.wait_for_url(lambda url: "/login/" not in url)
        page.wait_for_load_state("load")
        return page

    def visit(self, page, path):
        page.goto(f"{self.live_server_url}{path}")
        page.wait_for_load_state("load")
        # The reminder scheduler finished reading the owner's agenda.
        try:
            page.wait_for_function(
                "document.querySelector('script[data-schedule]')?.dataset.state"
                " === 'loaded'"
            )
        except PlaywrightError as error:
            raise AssertionError(
                f"Agenda not loaded on {page.url}: {page.errors}"
            ) from error
        # Cards rise in with GSAP; screenshots and contrast need the final state.
        page.wait_for_function(GSAP_IDLE)

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
            # Saving again does not ask again.
            page.get_by_role("button", name="Salvar alterações").click()
            expect(
                page.get_by_role("button", name="Desativar lembretes")
            ).to_be_visible()
            assert page.evaluate(PERMISSION_REQUESTS) == 1
            self.assert_fits(page, "lembretes-ativos")
            browser.close()
        # The ORM is not usable inside sync_playwright (async context).
        assert ReminderSetting.objects.get(membership=self.membership).active

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

    def subscriptions(self):
        return in_thread(
            lambda: list(
                PushSubscription.objects.filter(membership=self.membership).values_list(
                    "endpoint", flat=True
                )
            )
        )

    @override_settings(
        VAPID_PRIVATE_KEY="private-key-for-the-test",
        VAPID_SUBJECT="mailto:contato@example.test",
    )
    def test_activating_subscribes_the_device_and_deactivating_cancels(self):
        key = vapid_public_key()
        with override_settings(VAPID_PUBLIC_KEY=key), sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser, init=(FAKE_PUSH,))
            self.visit(page, "/app/lembretes/")
            status = page.locator("[data-reminder-status]")
            expect(status).to_have_text(PUSH_INACTIVE)
            assert self.subscriptions() == []
            page.get_by_role("button", name="Ativar lembretes").click()
            expect(
                page.get_by_role("button", name="Desativar lembretes")
            ).to_be_visible()
            expect(status).to_have_text(PUSH_ACTIVE)
            assert status.get_attribute("data-push") == "active"
            # Permission was already granted: nothing asked again.
            assert page.evaluate(PERMISSION_REQUESTS) == 0
            assert self.subscriptions() == [FAKE_ENDPOINT]
            self.assert_fits(page, "lembretes-push-ativo")
            self.screenshot(page, "390-push-ativo")
            # Another page keeps the subscription and shows no in-page notice.
            self.visit(page, "/app/")
            assert self.subscriptions() == [FAKE_ENDPOINT]
            self.visit(page, "/app/lembretes/")
            page.get_by_role("button", name="Desativar lembretes").click()
            expect(
                page.get_by_role("status").filter(has_text="Lembretes desativados.")
            ).to_be_visible()
            expect(status).to_have_text(PUSH_INACTIVE)
            assert self.subscriptions() == []
            assert (
                page.evaluate(
                    "JSON.parse(sessionStorage.getItem('__qlFakePush') || 'null')"
                )
                is None
            )
            self.assert_fits(page, "lembretes-push-cancelado")
            browser.close()

    @override_settings(
        VAPID_PRIVATE_KEY="private-key-for-the-test",
        VAPID_SUBJECT="mailto:contato@example.test",
    )
    def test_signing_out_cancels_the_device_subscription(self):
        key = vapid_public_key()
        with override_settings(VAPID_PUBLIC_KEY=key), sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            # Desktop: the menu with "Sair" is always visible.
            page = self.open(browser, 1280, 800, init=(FAKE_PUSH,))
            self.visit(page, "/app/lembretes/")
            page.get_by_role("button", name="Ativar lembretes").click()
            expect(page.locator("[data-reminder-status]")).to_have_text(PUSH_ACTIVE)
            assert self.subscriptions() == [FAKE_ENDPOINT]
            page.get_by_role("button", name="Sair").click()
            page.wait_for_url(lambda url: "/login/" in url)
            assert self.subscriptions() == []
            assert page.errors == [], page.errors
            browser.close()

    @override_settings(
        VAPID_PRIVATE_KEY="private-key-for-the-test",
        VAPID_SUBJECT="mailto:contato@example.test",
    )
    def test_no_in_page_notice_when_the_device_receives_push(self):
        ReminderSetting.objects.create(membership=self.membership, active=True)
        key = vapid_public_key()
        zone = ZoneInfo(TIMEZONE)
        with override_settings(VAPID_PUBLIC_KEY=key), sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(
                browser,
                clock=datetime(2026, 10, 19, 9, 57, tzinfo=zone),
                init=(FAKE_PUSH, presubscribed(key)),
            )
            self.visit(page, "/app/")
            # The existing device subscription was sent to the server.
            assert self.subscriptions() == [FAKE_ENDPOINT]
            page.clock.pause_at(datetime(2026, 10, 19, 9, 59, 30, tzinfo=zone))
            page.clock.fast_forward("01:00")
            page.wait_for_timeout(500)
            expect(page.locator("[data-reminder-notice]")).to_have_count(0)
            assert page.errors == [], page.errors
            browser.close()

    def iphone(self, playwright):
        device = dict(playwright.devices["iPhone 13"])
        for key in ("viewport", "screen", "default_browser_type"):
            device.pop(key, None)
        return device

    def change_times_and_save(self, page, start, end, button, message):
        page.locator("input[name=workday_start]").fill(start)
        page.locator("input[name=workday_end]").fill(end)
        page.get_by_role("button", name=button).click()
        expect(page.get_by_role("status").filter(has_text=message)).to_be_visible()
        expect(page.locator("input[name=workday_start]")).to_have_value(start)
        expect(page.locator("input[name=workday_end]")).to_have_value(end)
        expect(page.locator("[role=alert]")).to_have_count(0)

    def assert_times_inside_card(self, page, label):
        card = page.locator("form.ql-pwa-form").bounding_box()
        for name in ("workday_start", "workday_end"):
            box = page.locator(f"input[name={name}]").bounding_box()
            assert box["x"] >= card["x"], (label, name, box, card)
            assert box["x"] + box["width"] <= card["x"] + card["width"], (
                label,
                name,
                box,
                card,
            )
        self.assert_fits(page, label)

    def run_iphone_flow(self, playwright, browser, engine):
        page = self.open(browser, device=self.iphone(playwright))
        self.visit(page, "/app/lembretes/")
        self.assert_times_inside_card(page, f"{engine}-lembretes")
        self.change_times_and_save(
            page, "07:15", "16:45", "Ativar lembretes", "Lembretes ativados."
        )
        self.change_times_and_save(
            page, "09:00", "17:30", "Salvar alterações", "Alterações salvas."
        )
        self.change_times_and_save(
            page, "22:00", "06:00", "Salvar alterações", "Alterações salvas."
        )
        expect(page.get_by_role("status").first).to_be_visible()
        expect(page.locator(".ql-pwa-state").last).to_contain_text(
            "das 22:00 às 06:00 (dia seguinte)."
        )
        self.assert_times_inside_card(page, f"{engine}-lembretes-ativos")
        self.screenshot(page, f"{engine}-iphone-lembretes")
        # Whatever is left in the fields, deactivating always works.
        page.locator("input[name=workday_start]").evaluate("input => input.value = ''")
        page.locator("input[name=weekdays]").evaluate_all(
            "days => days.forEach(day => { day.checked = false; })"
        )
        page.get_by_role("button", name="Desativar lembretes").click()
        expect(
            page.get_by_role("status").filter(has_text="Lembretes desativados.")
        ).to_be_visible()
        expect(page.get_by_role("button", name="Ativar lembretes")).to_be_visible()
        expect(page.locator("input[name=workday_start]")).to_have_value("22:00")
        self.assert_fits(page, f"{engine}-lembretes-desativados")
        page.context.close()

    def assert_saved_night_shift(self):
        setting = ReminderSetting.objects.get(membership=self.membership)
        assert not setting.active
        assert (setting.workday_start, setting.workday_end) == (time(22), time(6))

    def test_iphone_changes_times_saves_and_deactivates_chromium(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            self.run_iphone_flow(playwright, browser, "chromium")
            browser.close()
        self.assert_saved_night_shift()

    def test_iphone_changes_times_saves_and_deactivates_webkit(self):
        with sync_playwright() as playwright:
            try:
                browser = playwright.webkit.launch()
            except PlaywrightError:
                if os.environ.get("QA_WEBKIT") == "1":
                    raise
                self.skipTest(
                    "WebKit is not installed (python -m playwright install webkit)"
                )
            self.run_iphone_flow(playwright, browser, "webkit")
            browser.close()
        self.assert_saved_night_shift()

    def test_night_shift_reminders_belong_to_the_start_day(self):
        # 22:00-06:00 every 60 min, Mondays only: Monday 19/10/2026 at 23:00
        # and Tuesday 00:00 ... 05:00; never Monday early morning (Sunday's
        # shift) nor Tuesday night.
        ReminderSetting.objects.create(
            membership=self.membership,
            active=True,
            workday_start=time(22),
            workday_end=time(6),
            weekdays="1",
        )
        zone = ZoneInfo(TIMEZONE)
        monday = datetime(2026, 10, 19, tzinfo=zone)
        expected = [monday + timedelta(hours=hour) for hour in range(23, 30)]
        missing = [monday + timedelta(hours=1), monday + timedelta(hours=30)]

        def check(page, slot, shown):
            notice = page.locator("[data-reminder-notice]")
            page.clock.pause_at(slot - timedelta(seconds=30))
            expect(notice).to_be_hidden()
            page.clock.fast_forward("01:00")
            if shown:
                expect(notice).to_be_visible()
                notice.get_by_role("button", name="Agora não").click()
            else:
                page.wait_for_timeout(200)
                expect(notice).to_be_hidden()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            # Sunday's night shift was not chosen: nothing on Monday at 01:00.
            page = self.open(browser, clock=monday + timedelta(minutes=50))
            self.visit(page, "/app/")
            check(page, missing[0], shown=False)
            page.context.close()
            page = self.open(browser, clock=monday + timedelta(hours=22, minutes=50))
            self.visit(page, "/app/")
            for slot in expected:
                check(page, slot, shown=True)
            check(page, monday + timedelta(hours=30), shown=False)  # 06:00 = end
            check(page, monday + timedelta(hours=47), shown=False)  # Tuesday 23:00
            page.context.close()
            # Opened after midnight, Monday's shift is still running.
            page = self.open(browser, clock=monday + timedelta(hours=26, minutes=50))
            self.visit(page, "/app/")
            check(page, monday + timedelta(hours=27), shown=True)
            assert page.evaluate(PERMISSION_REQUESTS) == 0
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
