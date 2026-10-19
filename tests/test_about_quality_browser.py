"""Browser QA for "Conheça a Quality" (docs/specs/16-conheca-a-quality.md,
aceite 6) at 390x844 and 1280x800.

No horizontal scroll and no console error before and after scrolling the whole
page; the logo is 3D with WebGL or stays an image without it; after scrolling,
every section's text is visible; with prefers-reduced-motion everything is
visible at once and GSAP runs nothing. Screenshots go to
QA_ARTIFACT_DIR/conheca/.
"""

import os
from pathlib import Path
from unittest import skipIf

from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from identity.models import Membership, Organization, User

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

PASSWORD = "browser-test-password"
PATH = "/app/conheca-a-quality/"
VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
FITS = "document.documentElement.scrollWidth <= window.innerWidth"
# Software WebGL so the 3D path runs headless.
SOFTWARE_GL = [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
]
LOGO_STATE = "document.getElementById('qlc-logo3d').dataset.state"
# Texts that must end fully visible (opacity 1 up the tree) once scrolled to.
HIDDEN_TEXTS = """() => {
    const shown = element => {
        for (let node = element; node; node = node.parentElement) {
            if (Number(getComputedStyle(node).opacity) < 0.99) return false;
        }
        return true;
    };
    // The hero copy fades out on purpose while scrolling past it on desktop;
    // its lead is checked before scrolling.
    const selector = '.qlc-head h2, .qlc-head p, .qlc-card h3, .qlc-tile strong,'
        + ' .qlc-step strong, .qlc-benefits li, .qlc-cline strong';
    return [...document.querySelectorAll(selector)]
        .filter(element => !shown(element))
        .map(element => element.textContent.trim().slice(0, 40));
}"""
SCROLL_THROUGH = """async () => {
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    for (let y = 0; y <= document.documentElement.scrollHeight; y += 250) {
        window.scrollTo(0, y);
        await pause(60);
    }
    await pause(1600);
}"""


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class AboutQualityBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        organization = Organization.objects.create(name="QA Conheça", slug="qa-conheca")
        self.user = User.objects.create_user("conheca@example.test", PASSWORD)
        Membership.objects.create(
            user=self.user,
            organization=organization,
            role=Membership.Role.COLLABORATOR,
        )

    def open(self, browser, width, height, reduced=False):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            locale="pt-BR",
            reduced_motion="reduce" if reduced else "no-preference",
        )
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
        page.wait_for_url(lambda url: "/login/" not in url)
        page.wait_for_load_state("load")
        page.goto(f"{self.live_server_url}{PATH}")
        page.wait_for_load_state("load")
        return page

    def screenshot(self, page, name):
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir) / "conheca"
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / f"{name}.png"), full_page=True)

    def check_page(self, page, label):
        nav = page.locator('.ql-nav a[aria-current="page"]')
        # At 390 the menu is a closed drawer: read the text, not the rendering.
        assert nav.text_content().strip().endswith("Conheça a Quality"), label
        # The intro ends (lead text fully shown) before measuring.
        page.wait_for_function(
            "Number(getComputedStyle(document.querySelector('.qlc-lead')).opacity) > 0.99"
        )
        assert page.evaluate(LOGO_STATE) in ("3d", "image"), label
        if page.evaluate(LOGO_STATE) == "image":
            assert page.locator("#qlc-fallback").is_visible(), label
        else:
            # Only one logo on screen: the flat image leaves when the 3D coin shows.
            assert not page.locator("#qlc-fallback").is_visible(), label
        assert page.evaluate(FITS), f"Horizontal overflow: {label}"
        page.evaluate(SCROLL_THROUGH)
        assert page.evaluate(FITS), f"Horizontal overflow after scroll: {label}"
        # Reveals run on the animation clock; slow software GL can delay them.
        try:
            page.wait_for_function(f"({HIDDEN_TEXTS})().length === 0", timeout=10000)
        except PlaywrightError:
            pass
        assert page.evaluate(HIDDEN_TEXTS) == [], (label, page.evaluate(HIDDEN_TEXTS))
        assert page.errors == [], (label, page.errors)

    def test_fits_animates_and_shows_every_section(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                self.check_page(page, f"chromium-{name}")
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(600)
                self.screenshot(page, f"chromium-{name}")
                page.context.close()
            browser.close()

    def test_3d_logo_replaces_the_image(self):
        """With WebGL (software GL in CI) only the 3D coin shows, never both."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=SOFTWARE_GL)
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                try:
                    page.wait_for_function(f"{LOGO_STATE} === '3d'", timeout=8000)
                except PlaywrightError:
                    self.skipTest("No WebGL in this browser build")
                self.check_page(page, f"webgl-{name}")
                page.context.close()
            browser.close()

    def test_iphone_webkit_fits(self):
        with sync_playwright() as playwright:
            try:
                browser = playwright.webkit.launch()
            except PlaywrightError:
                if os.environ.get("QA_WEBKIT") == "1":
                    raise
                self.skipTest(
                    "WebKit is not installed (python -m playwright install webkit)"
                )
            page = self.open(browser, 390, 844)
            self.check_page(page, "webkit-390")
            self.screenshot(page, "webkit-390")
            page.context.close()
            browser.close()

    def test_reduced_motion_shows_everything_without_gsap(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser, 390, 844, reduced=True)
            assert page.evaluate(HIDDEN_TEXTS) == []
            assert (
                page.evaluate(
                    "Number(getComputedStyle(document.querySelector('.qlc-lead')).opacity)"
                )
                == 1
            )
            assert (
                page.evaluate(
                    "window.gsap ? gsap.globalTimeline.getChildren(true, true, true)"
                    ".filter(t => (t.targets?.() || []).some(el => el.closest?.('.qlc'))).length : 0"
                )
                == 0
            )
            assert page.evaluate(FITS)
            assert page.errors == [], page.errors
            page.context.close()
            browser.close()
