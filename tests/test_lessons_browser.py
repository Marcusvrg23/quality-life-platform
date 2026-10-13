"""Browser QA: no horizontal scroll at 390x844 on home and Aulas."""

from unittest import skipIf

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from identity.models import Membership, Organization

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class LessonsBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        organization = Organization.objects.create(name="QA Aulas", slug="qa-aulas")
        user = get_user_model().objects.create_user(
            email="aulas-390@example.test", password="browser-test-password"
        )
        Membership.objects.create(
            user=user, organization=organization, role=Membership.Role.COLLABORATOR
        )

    def test_no_horizontal_scroll_at_390(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"{self.live_server_url}/login/")
            page.locator("#id_username").fill("aulas-390@example.test")
            page.locator("#id_password").fill("browser-test-password")
            page.get_by_role("button", name="Entrar").click()
            page.get_by_role("heading", name="Escolha sua atividade").wait_for()
            for stage, url in (
                ("home", "/app/"),
                ("aulas", "/app/aulas/"),
            ):
                page.goto(f"{self.live_server_url}{url}")
                page.wait_for_load_state("load")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), f"Horizontal overflow at 390x844: {stage}"
            assert page.locator("video").count() == 3
            browser.close()
