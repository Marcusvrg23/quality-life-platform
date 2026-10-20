"""Browser QA for the Assistente Quality (docs/specs/18-assistente.md, aceite 9)
at 390x844 and 1280x800: a question gets an answer shown as plain text, the
conversation is gone after a reload, no horizontal scroll, no console error.
The chat API is simulated in-process."""

import io
import json
import os
from pathlib import Path
from unittest import mock, skipIf

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings

from identity.models import Membership, Organization, User

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None

PASSWORD = "browser-test-password"
ANSWER = "Levante, alongue os ombros e beba água. <b>sem html</b>"


def reply(*args):
    body = {"choices": [{"message": {"role": "assistant", "content": ANSWER}}]}
    return io.BytesIO(json.dumps(body).encode())


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
@override_settings(
    GROQ_API_KEY="key-for-the-test", ASSISTANT_ORGANIZATIONS=["piloto-b"]
)
class AssistantBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Piloto", slug="piloto-b")
        self.user = User.objects.create_user("assistente@example.test", PASSWORD)
        Membership.objects.create(
            user=self.user, organization=organization, role=Membership.Role.COLLABORATOR
        )
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = mock.patch("urllib.request.urlopen")
        urlopen = patcher.start()
        self.addCleanup(patcher.stop)
        urlopen.return_value.__enter__.side_effect = reply

    def test_chat_fits_and_forgets_on_reload(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for width, height in ((390, 844), (1280, 800)):
                context = browser.new_context(
                    viewport={"width": width, "height": height}, locale="pt-BR"
                )
                page = context.new_page()
                errors = []
                page.on(
                    "console",
                    lambda m, errors=errors: (
                        m.type == "error" and errors.append(m.text)
                    ),
                )
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(f"{self.live_server_url}/login/")
                page.locator("#id_username").fill(self.user.email)
                page.locator("#id_password").fill(PASSWORD)
                page.get_by_role("button", name="Entrar").click()
                page.wait_for_url(lambda url: "/login/" not in url)
                page.goto(f"{self.live_server_url}/app/assistente/")
                page.locator("#assistant-input").fill("Como cuidar da postura?")
                page.get_by_role("button", name="Enviar").click()
                answers = page.locator(".wb-assistant__msg--assistant p")
                # The greeting (suggestion) arrives on its own, then the answer.
                expect(answers).to_have_count(2)
                expect(answers.first).to_have_text(ANSWER)
                expect(answers.last).to_have_text(ANSWER)
                assert page.locator(".wb-assistant__msg--assistant b").count() == 0
                assert page.locator(".wb-dot").count() == 0
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), width
                artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
                if artifact_dir:
                    path = Path(artifact_dir) / "assistente"
                    path.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(path / f"{width}.png"), full_page=True)
                page.reload()
                # Only the new greeting: the conversation was not kept.
                expect(page.locator(".wb-assistant__msg--assistant")).to_have_count(1)
                assert page.locator(".wb-assistant__msg--user").count() == 0
                # Hoje shows the same suggestion in its card.
                page.goto(f"{self.live_server_url}/app/")
                expect(page.locator("[data-assistant-suggestion-text]")).to_have_text(
                    ANSWER
                )
                assert errors == [], errors
                context.close()
            browser.close()
