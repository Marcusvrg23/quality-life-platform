"""TEST ONLY — Browser QA of the individual map (spec 10) at 390 and 1280 + print.

No horizontal scroll, no console error, GSAP idle with every segment visible,
heart on top at full width on the phone, and an A4 landscape print that fits
on one page without cutting the heart. Screenshots and the PDF go to
QA_ARTIFACT_DIR/mapa/.
"""

import os
import re
from importlib import import_module
from pathlib import Path
from unittest import skipIf

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from assessments import quality_map
from assessments.models import Assessment, Pillar, QuestionnaireVersion
from identity.models import Membership, Organization

from .test_assessment_result import answer_identification, completed_result

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

NINE_PILLARS = import_module("assessments.migrations.0002_nine_pillars")
PASSWORD = "browser-map-password"
GSAP_IDLE = (
    "!window.gsap || gsap.globalTimeline.getChildren(true, true, false)"
    ".every(t => t.totalProgress() === 1)"
)
CURRENT = {
    "physical_health": "78.40",
    "preventive_behavior": "88.00",
    "physical_activity": "56.10",
    "nutrition_hydration": "48.00",
    "mental_emotional_health": "42.90",
    "sleep_recovery": "34.67",
    "ergonomics_workplace": "59.00",
    "relationships": "72.00",
    "work_life_balance": "63.50",
}
PREVIOUS = dict.fromkeys(CURRENT, "50.00")
# A4 landscape minus the 6 mm @page margins, in CSS pixels.
PAGE_WIDTH, PAGE_HEIGHT = 1077, 748


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class QualityMapBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        # Live-server tests flush the database; restore migration 0002's pillars.
        for order, (code, name) in enumerate(NINE_PILLARS.PILLARS, start=1):
            Pillar.objects.get_or_create(
                code=code, defaults={"name": name, "display_order": order}
            )
        self.user = get_user_model().objects.create_user(
            email="mapa-browser@example.test", password=PASSWORD
        )
        organization = Organization.objects.create(name="Mapa QA", slug="mapa-qa")
        Membership.objects.create(
            user=self.user,
            organization=organization,
            role=Membership.Role.COLLABORATOR,
        )
        version = QuestionnaireVersion.objects.create(
            code="map-browser-test-only",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-result",
        )
        completed_result(self.user, organization, version, "50.00", PREVIOUS, 60)
        current = Assessment.objects.create(
            user=self.user, organization=organization, questionnaire_version=version
        )
        answer_identification(version, current, "12548", "Laboratório")
        completed_result(
            self.user, organization, version, "67.40", CURRENT, start=current
        )
        self.path = reverse("assessment_completed", args=[current.pk])

    def artifact(self, name):
        directory = os.environ.get("QA_ARTIFACT_DIR")
        if not directory:
            return None
        path = Path(directory) / "mapa"
        path.mkdir(parents=True, exist_ok=True)
        return path / name

    def open(self, browser, width, height):
        context = browser.new_context(
            viewport={"width": width, "height": height}, has_touch=width < 900
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
        page.wait_for_load_state("load")
        page.goto(f"{self.live_server_url}{self.path}")
        page.wait_for_load_state("load")
        page.wait_for_function(GSAP_IDLE)
        return page

    def check_screen(self, page, width):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow at {width}"
        codes = page.locator(".heart-segment").evaluate_all(
            "els => els.map(el => el.dataset.pillarCode)"
        )
        assert codes == [s["pillar_code"] for s in quality_map.SPEC["segments"]]
        assert page.evaluate(
            "[...document.querySelectorAll('.heart-segment, .heart-label')]"
            ".every(el => getComputedStyle(el).opacity === '1')"
        )
        assert page.locator(".heart-center-score").text_content() == "67"
        sleep = page.locator('.heart-segment[data-pillar-code="sleep_recovery"]')
        assert sleep.get_attribute("data-score") == "34"
        assert sleep.get_attribute("data-band") == "PRIORIDADE"
        assert page.get_by_text("Carla Souza Oliveira").is_visible()
        assert page.locator(".evolution-chart").is_visible()
        heart = page.locator(".quality-heart").bounding_box()
        identity = page.locator(".map-identity").bounding_box()
        if width < 640:
            # Phone: heart first, at the card's full width; panels stacked.
            card = page.locator(".quality-map").bounding_box()
            assert heart["width"] >= card["width"] - 24, (heart, card)
            assert heart["y"] + heart["height"] <= identity["y"], (heart, identity)
            assert page.locator(".pillar-list").is_visible()
        target = self.artifact(f"mapa-{width}.png")
        if target:
            page.screenshot(path=str(target), full_page=True)

    def check_print(self, page):
        page.emulate_media(media="print")
        page.set_viewport_size({"width": PAGE_WIDTH, "height": PAGE_HEIGHT})
        assert not page.locator(".ql-sidebar").is_visible()
        assert not page.locator(".ql-topbar").is_visible()
        assert not page.get_by_role("button", name="Salvar em PDF").is_visible()
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") in (
            "rgb(255, 255, 255)",
            "rgba(0, 0, 0, 0)",
        )
        # No shell transition may run while printing (margin of the menu).
        assert page.evaluate(
            "getComputedStyle(document.querySelector('.ql-workspace'))"
            ".transitionDuration"
        ) in ("0s", "0s, 0s")
        heart = page.locator(".quality-heart").bounding_box()
        # As large as in the client's model (about half the page width).
        assert heart["width"] >= 440, heart
        assert heart["y"] >= 0, heart
        assert heart["y"] + heart["height"] <= PAGE_HEIGHT, heart
        assert heart["x"] >= 0 and heart["x"] + heart["width"] <= PAGE_WIDTH, heart
        assert page.evaluate("document.documentElement.scrollHeight") <= PAGE_HEIGHT
        target = self.artifact("mapa-print.png")
        if target:
            page.screenshot(path=str(target))
        pdf = page.pdf(prefer_css_page_size=True, print_background=True)
        pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
        assert pages == 1, f"Print spans {pages} pages"
        target = self.artifact("mapa-print.pdf")
        if target:
            target.write_bytes(pdf)
        page.emulate_media(media="screen")

    def test_map_on_phone_desktop_and_print(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for width, height in ((390, 844), (1280, 800)):
                page = self.open(browser, width, height)
                self.check_screen(page, width)
                if width == 1280:
                    self.check_print(page)
                assert page.errors == [], (width, page.errors)
                page.context.close()
            browser.close()
