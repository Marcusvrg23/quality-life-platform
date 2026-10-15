"""Browser QA for the wellbeing pages (spec 11, aceite 8) at 390x844 and 1280x800.

Every new page: no horizontal scroll, no console error, AA contrast, GSAP idle
except tweens tagged data: 'loop', and no video src or AudioContext before a
click. Reduced motion runs no loop and keeps the poster while the timer runs.
A finished session is recorded once and shows up in Meu Progresso.
Screenshots go to QA_ARTIFACT_DIR/bem-estar/.
"""

import os
from pathlib import Path
from unittest import skipIf

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from identity.models import Membership, Organization
from tests.test_app_dark_browser import CONTRAST
from wellbeing.models import ActivitySession

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

PASSWORD = "browser-test-password"
VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
PAGES = (
    ("hoje", "/app/"),
    ("ginastica", "/app/ginastica/"),
    ("meditacao", "/app/meditacao/"),
    ("relaxamento", "/app/relaxamento/"),
    ("progresso", "/app/progresso/"),
)
# Idle = every top-level animation finished, except endless ones tagged 'loop'.
GSAP_IDLE = (
    "!window.gsap || gsap.globalTimeline.getChildren(false, true, true)"
    ".filter(t => t.data !== 'loop').every(t => t.totalProgress() === 1)"
)
LOOPS = (
    "window.gsap ? gsap.globalTimeline.getChildren(false, true, true)"
    ".filter(t => t.data === 'loop').length : 0"
)
ALL_GSAP = "window.gsap ? gsap.globalTimeline.getChildren(true, true, true).length : 0"
# Counts AudioContext creations; nothing may sound before a click.
COUNT_AUDIO = """(() => {
    window.__audioContexts = 0;
    const Original = window.AudioContext;
    if (!Original) return;
    window.AudioContext = class extends Original {
        constructor(...args) { super(...args); window.__audioContexts += 1; }
    };
})();"""
MEDIA_IDLE = (
    "[...document.querySelectorAll('video')].every(v => !v.getAttribute('src') && v.paused)"
    " && window.__audioContexts === 0"
)


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class WellbeingBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        org = Organization.objects.create(name="QA Bem-estar", slug="qa-bem-estar")
        self.user = get_user_model().objects.create_user(
            email="bemestar@example.test", password=PASSWORD
        )
        Membership.objects.create(
            user=self.user, organization=org, role=Membership.Role.COLLABORATOR
        )

    # Helpers -----------------------------------------------------------------

    def open(self, browser, width, height, reduced_motion="no-preference"):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            reduced_motion=reduced_motion,
        )
        context.add_init_script(COUNT_AUDIO)
        page = context.new_page()
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
        page.wait_for_function(GSAP_IDLE)

    def screenshot(self, page, name):
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir) / "bem-estar"
            path.mkdir(parents=True, exist_ok=True)
            # A modal player is captured as the person sees it (viewport only).
            modal = page.evaluate("Boolean(document.querySelector('dialog[open]'))")
            page.screenshot(path=str(path / f"{name}.png"), full_page=not modal)

    def assert_fits(self, page, label):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow: {label}"
        assert page.errors == [], (label, page.errors)

    # Tests -------------------------------------------------------------------

    def test_pages_fit_have_contrast_and_stay_silent_until_click(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                for slug, path in PAGES:
                    self.visit(page, path)
                    label = f"{name}-{slug}"
                    self.assert_fits(page, label)
                    assert page.evaluate(MEDIA_IDLE), label
                    contrast = page.evaluate(CONTRAST)
                    assert contrast["failures"] == [], (label, contrast["failures"][:6])
                    self.screenshot(page, label)
                page.context.close()
            browser.close()

    def test_gym_player_starts_video_and_timer_only_after_click(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                self.visit(page, "/app/ginastica/")
                page.locator('[data-open-session="pausa-coluna-3min"]').click()
                position = page.locator("[data-player-position]")
                assert position.inner_text() == "Exercício 1 de 6"
                timer = page.locator("[data-player-step-time]")
                assert timer.inner_text() == "00:30"
                video = page.locator("[data-player-video]")
                assert video.get_attribute("src") is None
                assert video.get_attribute("poster").endswith(
                    "ex-inclinacao-frente.webp"
                )
                # No material image yet for this exercise: no toggle.
                assert page.locator("[data-player-toggle-image]").is_hidden()
                page.wait_for_function(GSAP_IDLE)
                self.screenshot(page, f"{name}-ginastica-player")
                page.locator("[data-player-toggle]").click()
                assert video.get_attribute("src").endswith("ex-inclinacao-frente.mp4")
                page.wait_for_function(
                    "document.querySelector('[data-player-step-time]').textContent !== '00:30'"
                )
                page.locator("[data-player-next]").click()
                assert position.inner_text() == "Exercício 2 de 6"
                assert video.get_attribute("src").endswith("ex-lateral.mp4")
                page.locator("[data-player-toggle-image]").click()
                assert (
                    page.locator("[data-player-image]")
                    .get_attribute("src")
                    .endswith("exercises/lateral.webp")
                )
                page.locator("[data-player-toggle]").click()
                page.wait_for_function(GSAP_IDLE)
                assert page.locator(
                    ".wb-player__controls [data-player-next]"
                ).is_visible()
                self.assert_fits(page, f"{name}-ginastica-player")
                self.screenshot(page, f"{name}-ginastica-player-imagem")
                page.keyboard.press("Escape")
                assert not page.locator("dialog").is_visible()
                page.context.close()
            browser.close()
        # Under 60 s nothing is recorded. The ORM runs outside sync_playwright,
        # whose event loop makes Django refuse synchronous queries.
        assert not ActivitySession.objects.exists()

    def test_meditation_breathing_loop_and_noise_after_click(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                self.visit(page, "/app/meditacao/")
                page.locator('[data-open-session="respiracao-foco"]').click()
                page.locator("[data-player-noise]").select_option("pink")
                assert page.evaluate(MEDIA_IDLE)
                page.locator("[data-player-toggle]").click()
                page.wait_for_function("window.__audioContexts === 1")
                assert page.evaluate(LOOPS) == 1
                page.wait_for_function(GSAP_IDLE)
                assert page.locator("[data-breath-label]").inner_text() in (
                    "Inspire",
                    "Expire",
                )
                self.assert_fits(page, f"{name}-meditacao-player")
                self.screenshot(page, f"{name}-meditacao-player")
                page.get_by_role("button", name="← Voltar").click()
                assert page.evaluate(LOOPS) == 0
                assert page.evaluate("!window.QLNoise.playing")
                page.context.close()
            browser.close()

    def test_relax_plays_generated_noise_only_after_click(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                self.visit(page, "/app/relaxamento/")
                assert page.locator("[data-sound-play]").count() == 7
                page.locator('input[name="wb-timer"][value="5"]').check(force=True)
                page.locator('[data-slug="ruido-rosa"]').click()
                page.wait_for_function("window.__audioContexts === 1")
                status = page.locator("[data-relax-status]")
                assert status.inner_text().startswith("Tocando: Ruído rosa")
                page.locator("[data-backdrop-toggle]").check()
                assert (
                    page.locator("[data-backdrop-video]")
                    .get_attribute("src")
                    .endswith("med-relaxamento.mp4")
                )
                page.wait_for_function(GSAP_IDLE)
                self.assert_fits(page, f"{name}-relaxamento-tocando")
                self.screenshot(page, f"{name}-relaxamento-tocando")
                page.get_by_role("button", name="Parar").click()
                assert status.inner_text() == "Nenhum som tocando."
                assert page.evaluate("!window.QLNoise.playing")
                page.context.close()
            browser.close()

    def test_default_sound_and_video_sound_start_on_click_and_stop_on_back(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser, 390, 844)
            for path, slug, default in (
                ("/app/meditacao/", "respiracao-foco", "forest"),
                ("/app/ginastica/", "pausa-coluna-3min", "music"),
            ):
                self.visit(page, path)
                page.locator(f'[data-open-session="{slug}"]').click()
                noise = page.locator("[data-player-noise]")
                assert noise.input_value() == default, path
                sound = page.locator("[data-player-video-sound]")
                assert sound.is_checked()
                assert page.evaluate(MEDIA_IDLE), path
                assert page.evaluate(
                    "!document.querySelector('[data-player-video]').muted"
                )
                page.locator("[data-player-toggle]").click()
                page.wait_for_function("window.QLNoise.playing")
                assert page.evaluate("window.__audioContexts") == 1, path
                sound.uncheck()
                assert page.evaluate(
                    "document.querySelector('[data-player-video]').muted"
                )
                self.assert_fits(page, f"390-{slug}-som")
                page.get_by_role("button", name="← Voltar").click()
                assert page.evaluate("!window.QLNoise.playing"), path
            page.context.close()
            browser.close()

    def test_each_generated_sound_plays_and_stops(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser, 390, 844)
            self.visit(page, "/app/relaxamento/")
            buttons = page.locator("[data-sound-play]")
            noises = [
                buttons.nth(i).get_attribute("data-noise")
                for i in range(buttons.count())
            ]
            assert noises == [
                "forest",
                "ocean",
                "rain",
                "music",
                "white",
                "pink",
                "brown",
            ]
            for index, noise in enumerate(noises):
                buttons.nth(index).click()
                assert page.evaluate("window.QLNoise.playing"), noise
                page.wait_for_timeout(1000)
                assert page.evaluate("window.QLNoise.playing"), noise
                page.get_by_role("button", name="Parar").click()
                assert page.evaluate("!window.QLNoise.playing"), noise
                assert page.errors == [], (noise, page.errors)
            assert page.evaluate("window.__audioContexts") == 1
            self.assert_fits(page, "390-relaxamento-sete-sons")
            page.context.close()
            browser.close()

    def test_reduced_motion_keeps_poster_and_runs_no_loop(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height, reduced_motion="reduce")
                for _, path in PAGES:
                    self.visit(page, path)
                    assert page.evaluate(ALL_GSAP) == 0, path
                self.visit(page, "/app/meditacao/")
                page.locator('[data-open-session="reduzir-ansiedade"]').click()
                page.locator("[data-player-toggle]").click()
                page.wait_for_function(
                    "document.querySelector('[data-player-step-time]').textContent !== '05:00'"
                )
                assert page.locator("[data-player-video]").get_attribute("src") is None
                assert page.evaluate(ALL_GSAP) == 0
                assert page.locator("[data-breath-label]").inner_text() == "Inspire"
                self.assert_fits(page, f"{name}-reduced-meditacao")
                self.screenshot(page, f"{name}-reduced-meditacao")
                page.keyboard.press("Escape")
                page.context.close()
            browser.close()

    def test_completed_session_is_recorded_once_and_shown_in_progress(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            # Reduced motion: no GSAP frames to wait for while the clock is fake.
            page = self.open(browser, 390, 844, reduced_motion="reduce")
            page.clock.install()
            page.goto(f"{self.live_server_url}/app/meditacao/")
            page.wait_for_load_state("load")
            page.locator('[data-open-session="respiracao-foco"]').click()
            # No background sound: the fake clock would fire every audio
            # scheduler tick and run slower than real time.
            page.locator("[data-player-noise]").select_option("")
            page.locator("[data-player-toggle]").click()
            with page.expect_response(lambda r: "pratica/registrar" in r.url) as info:
                page.clock.run_for(125_000)
            assert info.value.status == 201
            assert page.locator("[data-player-done]").is_visible()
            page.keyboard.press("Escape")  # closing after completion records nothing
            page.goto(f"{self.live_server_url}/app/progresso/")
            page.wait_for_load_state("load")
            assert "Conquistado" in page.locator(".wb-trophy.is-earned").inner_text()
            self.assert_fits(page, "390-progresso-com-pratica")
            self.screenshot(page, "390-progresso-com-pratica")
            browser.close()
        # ORM outside sync_playwright (its event loop blocks synchronous queries).
        session = ActivitySession.objects.get()
        assert (session.user, session.kind, session.slug) == (
            self.user,
            "meditacao",
            "respiracao-foco",
        )
        assert session.completed
        assert session.duration_seconds == 120
