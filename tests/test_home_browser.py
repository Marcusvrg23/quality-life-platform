"""Browser QA for the public landing page: overflow, reduced motion, console."""

import os
from pathlib import Path
from unittest import skipIf

from django.contrib.staticfiles.testing import StaticLiveServerTestCase

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
VISIBLE_SELECTORS = ("h1", ".ql-feature")
# Scroll-scrubbed parallax tweens follow the scroll position and never "finish";
# ScrollTrigger also keeps a paused delayedCall (resize debounce) with no element.
OWN_PENDING = (
    "gsap.globalTimeline.getChildren(true, true, false)"
    ".filter(t => t.targets()[0] instanceof Element && t.data !== 'parallax'"
    " && t.totalProgress() !== 1)"
)
GSAP_IDLE = f"!window.gsap || {OWN_PENDING}.length === 0"
PENDING_TWEENS = (
    f"{OWN_PENDING}.map(t => ({{progress: t.totalProgress(), paused: t.paused(),"
    " target: String(t.targets()[0].className),"
    " start: t.scrollTrigger ? t.scrollTrigger.start : null, scrollY}))"
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


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class HomeBrowserTests(StaticLiveServerTestCase):
    # Keep the nine pillars seeded by migration 0002 (live server tests flush).
    serialized_rollback = True

    def open_home(self, browser, width, height, reduced_motion):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            reduced_motion=reduced_motion,
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

    def assert_fully_visible(self, page, label):
        opacities = page.evaluate(
            "selectors => selectors.flatMap(s => [...document.querySelectorAll(s)])"
            ".map(el => getComputedStyle(el).opacity)",
            list(VISIBLE_SELECTORS),
        )
        self.assertEqual(len(opacities), 5, label)
        self.assertEqual(set(opacities), {"1"}, label)
        pills = page.evaluate(
            "[...document.querySelectorAll('.ql-pill')]"
            ".map(el => getComputedStyle(el).opacity)"
        )
        self.assertEqual(pills, ["1"] * 9, label)

    def test_reduced_motion_shows_everything_without_overflow(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                with self.subTest(viewport=name):
                    context, page, errors = self.open_home(
                        browser, width, height, "reduce"
                    )
                    self.assertTrue(
                        page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        ),
                        f"Horizontal overflow at {name}",
                    )
                    self.assert_fully_visible(page, name)
                    self.assertEqual(errors, [])
                    artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
                    if artifact_dir:
                        path = Path(artifact_dir)
                        path.mkdir(parents=True, exist_ok=True)
                        page.screenshot(
                            path=str(path / f"landing-{name}.png"), full_page=True
                        )
                    context.close()
            browser.close()

    def test_motion_enabled_settles_visible_without_overflow(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                with self.subTest(viewport=name):
                    context, page, errors = self.open_home(
                        browser, width, height, "no-preference"
                    )
                    self.assertTrue(page.evaluate("Boolean(window.ScrollTrigger)"))
                    # Scroll through the page so every once-only reveal fires.
                    page.evaluate(SCROLL_THROUGH)
                    try:
                        page.wait_for_function(GSAP_IDLE, timeout=10_000)
                    except PlaywrightTimeoutError:
                        self.fail(
                            f"GSAP did not settle: {page.evaluate(PENDING_TWEENS)}"
                        )
                    self.assertTrue(
                        page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        ),
                        f"Horizontal overflow with motion at {name}",
                    )
                    self.assert_fully_visible(page, name)
                    self.assertEqual(errors, [])
                    context.close()
            browser.close()
