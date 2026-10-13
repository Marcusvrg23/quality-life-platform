"""Browser QA for the public landing page: overflow, motion, menu, console."""

import os
from importlib import import_module
from pathlib import Path
from unittest import skipIf

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from assessments.models import Pillar

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

NINE_PILLARS = import_module("assessments.migrations.0002_nine_pillars")
VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
LANDING_IMAGES = (
    "hero-bg",
    "hero-pessoa",
    "hero-mobile-bg",
    "hero-mobile-pessoa",
    "cta-bg",
    "cta-pessoa",
    "hero",
    "hero-mobile",
    "cta",
    "momento-comecar",
    "momento-durante",
    "momento-encerrar",
    "jornada",
)
# Scroll-scrubbed parallax tweens follow the scroll position and endless 'loop'
# tweens (aurora, breathing, glow) never "finish"; ScrollTrigger also keeps a
# paused delayedCall (resize debounce) with no element.
OWN_PENDING = (
    "gsap.globalTimeline.getChildren(true, true, false)"
    ".filter(t => t.targets()[0] instanceof Element && t.data !== 'parallax'"
    " && t.data !== 'loop' && t.totalProgress() !== 1)"
)
GSAP_IDLE = f"!window.gsap || {OWN_PENDING}.length === 0"
# Before scrolling, reveals further down wait (paused) for their trigger.
VIEW_IDLE = (
    f"!window.gsap || {OWN_PENDING}"
    ".filter(t => !(t.scrollTrigger && scrollY < t.scrollTrigger.start))"
    ".length === 0"
)
PENDING_TWEENS = (
    f"{OWN_PENDING}.map(t => ({{progress: t.totalProgress(), paused: t.paused(),"
    " target: String(t.targets()[0].className),"
    " start: t.scrollTrigger ? t.scrollTrigger.start : null, scrollY}))"
)
LOOP_TWEENS = (
    "window.gsap ? gsap.globalTimeline.getChildren(true, true, false)"
    ".filter(t => t.data === 'loop' && !t.paused()).length : 0"
)
SCROLL_THROUGH = """async () => {
    const pause = ms => new Promise(r => setTimeout(r, ms));
    const bottom = document.documentElement.scrollHeight;
    for (let y = 0; y <= bottom; y += 200) {
        window.scrollTo(0, y);
        await pause(50);
    }
    window.scrollTo(0, bottom);
    await pause(100);
}"""
FRAMES = "name => window.QLAmbient ? window.QLAmbient.frames(name) : 0"
LAYER_ORDER = """scene => [...document.querySelectorAll(
    `.ql-scene--${scene} .ql-scene__rig > .ql-layer`)].map(el => ({
        kind: el.className.match(/ql-layer--(\\w+)/)[1],
        z: Number(getComputedStyle(el).zIndex),
        visible: el.getBoundingClientRect().width > 0,
    }))"""
# The element at the centre of a control must be the control itself.
CLICKABLE = """el => {
    const box = el.getBoundingClientRect();
    if (!box.width || !box.height) return false;
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false;
    const hit = document.elementFromPoint(x, y);
    return Boolean(hit) && (hit === el || el.contains(hit));
}"""
NO_OVERFLOW = "document.documentElement.scrollWidth <= window.innerWidth"


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class HomeBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        # Live-server tests flush the database; restore migration 0002's pillars.
        for order, (code, name) in enumerate(NINE_PILLARS.PILLARS, start=1):
            Pillar.objects.get_or_create(
                code=code, defaults={"name": name, "display_order": order}
            )

    def open_home(self, browser, width, height, reduced_motion):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            reduced_motion=reduced_motion,
            has_touch=width < 600,
        )
        page = context.new_page()
        errors = []
        page.on(
            "console",
            lambda message: (
                errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{self.live_server_url}/")
        page.wait_for_load_state("load")
        return context, page, errors

    def wait_idle(self, page, condition=GSAP_IDLE):
        try:
            page.wait_for_function(condition, timeout=10_000)
        except PlaywrightTimeoutError:
            self.fail(f"GSAP did not settle: {page.evaluate(PENDING_TWEENS)}")

    def assert_fully_visible(self, page, label):
        for selector, count in (
            ("h1", 1),
            (".ql-moment", 3),
            (".ql-pillar", 9),
            (".ql-step", 4),
        ):
            opacities = page.eval_on_selector_all(
                selector, "els => els.map(el => getComputedStyle(el).opacity)"
            )
            self.assertEqual(opacities, ["1"] * count, f"{label} {selector}")

    def assert_clickable(self, page, selector, label):
        locator = page.locator(selector).first
        locator.scroll_into_view_if_needed()
        self.wait_idle(page)
        self.assertTrue(locator.evaluate(CLICKABLE), f"{selector} covered at {label}")

    def screenshot(self, page, name):
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir)
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / f"landing-{name}.png"))

    def test_reduced_motion_shows_static_scene_without_loops(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                with self.subTest(viewport=name):
                    context, page, errors = self.open_home(
                        browser, width, height, "reduce"
                    )
                    page.wait_for_timeout(400)
                    self.assertTrue(page.evaluate(NO_OVERFLOW), name)
                    self.assert_fully_visible(page, name)
                    self.assertEqual(page.evaluate(LOOP_TWEENS), 0)
                    self.assertEqual(
                        page.evaluate(
                            "document.getAnimations()"
                            ".filter(a => a.playState === 'running').length"
                        ),
                        0,
                    )
                    first = page.evaluate(FRAMES, "ambient")
                    page.wait_for_timeout(300)
                    self.assertEqual(page.evaluate(FRAMES, "ambient"), first)
                    self.assertEqual(first, 0)
                    for scene in ("hero", "cta"):
                        self.assertFalse(
                            page.is_visible(f".ql-scene--{scene} .ql-scene__layers")
                        )
                        self.assertTrue(
                            page.is_visible(f".ql-scene--{scene} .ql-scene__static img")
                        )
                    static = page.eval_on_selector(
                        ".ql-scene--hero .ql-scene__static img", "img => img.currentSrc"
                    )
                    expected = "hero-mobile.webp" if width < 600 else "hero.webp"
                    self.assertTrue(static.endswith(expected), static)
                    self.assertEqual(errors, [])
                    context.close()
            browser.close()

    def test_motion_runs_canvases_and_settles_visible_without_overflow(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                with self.subTest(viewport=name):
                    context, page, errors = self.open_home(
                        browser, width, height, "no-preference"
                    )
                    self.assertTrue(page.evaluate("Boolean(window.ScrollTrigger)"))
                    for scene in ("hero", "cta"):
                        layers = page.evaluate(LAYER_ORDER, scene)
                        self.assertEqual(
                            [layer["kind"] for layer in layers],
                            ["bg", "back", "person", "front"],
                        )
                        z_order = [layer["z"] for layer in layers]
                        self.assertEqual(z_order, sorted(set(z_order)), scene)
                    self.assertTrue(
                        page.is_visible(".ql-scene--hero .ql-scene__layers")
                    )
                    self.assertFalse(
                        page.is_visible(".ql-scene--hero .ql-scene__static")
                    )

                    for canvas in ("ambient", "hero"):
                        first = page.evaluate(FRAMES, canvas)
                        page.wait_for_timeout(500)
                        self.assertGreater(page.evaluate(FRAMES, canvas), first, canvas)
                    self.assertGreater(page.evaluate(LOOP_TWEENS), 0)

                    # Scroll through the page so every once-only reveal fires.
                    page.evaluate(SCROLL_THROUGH)
                    self.wait_idle(page)
                    self.assertTrue(page.evaluate(NO_OVERFLOW), name)
                    self.assert_fully_visible(page, name)

                    page.locator(".ql-scene--cta").scroll_into_view_if_needed()
                    self.wait_idle(page)
                    page.wait_for_timeout(300)
                    self.screenshot(page, f"{name}-cta")
                    first = page.evaluate(FRAMES, "cta")
                    page.wait_for_timeout(500)
                    self.assertGreater(page.evaluate(FRAMES, "cta"), first)

                    page.evaluate("window.scrollTo(0, 0)")
                    self.wait_idle(page)
                    page.wait_for_timeout(300)
                    self.screenshot(page, f"{name}-top")
                    self.assertEqual(errors, [])
                    context.close()
            browser.close()

    def test_login_is_visible_and_clickable_without_opening_menu(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                for motion in ("no-preference", "reduce"):
                    with self.subTest(viewport=name, motion=motion):
                        context, page, errors = self.open_home(
                            browser, width, height, motion
                        )
                        self.wait_idle(page, VIEW_IDLE)
                        login = page.locator(".ql-header__cta")
                        self.assertTrue(login.is_visible())
                        self.assertEqual(login.inner_text().strip(), "Entrar")
                        self.assertTrue(login.evaluate(CLICKABLE), name)
                        self.assertEqual(
                            page.get_attribute(".ql-menu-toggle", "aria-expanded"),
                            "false",
                        )
                        # Still reachable after scrolling, while the header is glass.
                        page.evaluate("window.scrollTo(0, 1600)")
                        self.wait_idle(page, VIEW_IDLE)
                        self.assertTrue(login.evaluate(CLICKABLE), f"{name} scrolled")
                        login.click()
                        page.wait_for_url(f"**{reverse('login')}")
                        self.assertEqual(errors, [])
                        context.close()
            browser.close()

    def test_mobile_menu_is_accessible_and_desktop_shows_links(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context, page, errors = self.open_home(browser, 390, 844, "no-preference")
            toggle = page.locator(".ql-menu-toggle")
            menu = page.locator("#ql-menu")
            self.assertTrue(toggle.is_visible())
            self.assertFalse(menu.locator("a").first.is_visible())

            toggle.click()
            self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
            for label in ("Experiências", "Como funciona", "Para empresas"):
                link = menu.get_by_role("link", name=label)
                self.assertTrue(link.is_visible(), label)
            self.assertTrue(page.evaluate(NO_OVERFLOW))

            page.keyboard.press("Escape")
            self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
            self.assertFalse(menu.locator("a").first.is_visible())
            self.assertTrue(
                page.evaluate(
                    "document.activeElement === document.querySelector('.ql-menu-toggle')"
                )
            )

            toggle.click()
            menu.get_by_role("link", name="Como funciona").click()
            self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
            page.wait_for_function("location.hash === '#como-funciona'")
            self.assertEqual(errors, [])
            context.close()

            context, page, errors = self.open_home(browser, 1280, 800, "no-preference")
            self.assertFalse(page.is_visible(".ql-menu-toggle"))
            for label in ("Experiências", "Como funciona", "Para empresas"):
                link = page.locator("#ql-menu").get_by_role("link", name=label)
                self.assertTrue(link.is_visible(), label)
            self.assertEqual(errors, [])
            context.close()
            browser.close()

    def test_calls_to_action_are_clickable(self):
        selectors = (
            ".ql-hero .ql-btn--primary",
            ".ql-hero .ql-btn--ghost",
            ".ql-moment",
            "#empresas .ql-btn--primary",
            "#empresas .ql-btn--ghost",
            ".ql-scene--cta ~ .ql-cta__copy .ql-btn--primary",
            ".ql-footer a[href^='mailto:']",
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                with self.subTest(viewport=name):
                    context, page, errors = self.open_home(
                        browser, width, height, "no-preference"
                    )
                    page.evaluate(SCROLL_THROUGH)
                    for selector in selectors:
                        self.assert_clickable(page, selector, name)
                    self.assertEqual(errors, [])
                    context.close()
            browser.close()

    def test_landing_images_are_served(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            for image in LANDING_IMAGES:
                with self.subTest(image=image):
                    response = context.request.get(
                        f"{self.live_server_url}/static/quality_life/images/landing/"
                        f"{image}.webp"
                    )
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["content-type"], "image/webp")
            context.close()
            browser.close()
