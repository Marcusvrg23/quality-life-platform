"""Landing layout and progressive enhancement in a real browser."""

import os
from pathlib import Path
from unittest import skipIf

from django.contrib.staticfiles.testing import StaticLiveServerTestCase

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class HomeBrowserTests(StaticLiveServerTestCase):
    def check_landing(
        self, width, height, *, reduced_motion="no-preference", java_script_enabled=True
    ):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(
                viewport={"width": width, "height": height},
                reduced_motion=reduced_motion,
                java_script_enabled=java_script_enabled,
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: (
                    errors.append(message.text) if message.type == "error" else None
                ),
            )
            page.goto(self.live_server_url + "/")
            page.evaluate("document.fonts.ready")
            expect(page.locator("h1")).to_be_visible()
            cards = page.locator(".feature-card")
            expect(cards).to_have_count(4)
            static = reduced_motion == "reduce" or not java_script_enabled
            if static:
                expect(page.locator("h1")).to_have_css("opacity", "1")
            for card in cards.all():
                card.scroll_into_view_if_needed()
                expect(card).to_be_visible()
                expect(card).to_have_css("opacity", "1")
            # Check at multiple scroll positions, including active parallax.
            for selector in ("header", "#como-funciona", "#empresas", "footer"):
                page.locator(selector).scroll_into_view_if_needed()
                self.assertTrue(
                    page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                )
            if static and java_script_enabled:
                self.assertEqual(page.evaluate("ScrollTrigger.getAll().length"), 0)
            artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
            if artifact_dir and reduced_motion == "reduce" and java_script_enabled:
                target = Path(artifact_dir)
                target.mkdir(parents=True, exist_ok=True)
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(target / f"home-{width}.png"), full_page=True)
            self.assertEqual(errors, [])
            browser.close()

    def test_mobile_and_desktop_motion(self):
        for width, height in ((390, 844), (1280, 800)):
            with self.subTest(width=width):
                self.check_landing(width, height)

    def test_reduced_motion_is_complete_and_static(self):
        for width, height in ((390, 844), (1280, 800)):
            with self.subTest(width=width):
                self.check_landing(width, height, reduced_motion="reduce")

    def test_without_javascript_is_complete(self):
        self.check_landing(390, 844, java_script_enabled=False)
