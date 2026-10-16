"""Browser QA for spec 15 at 390x844 and 1280x800: the completion screen fits
without scrolling, the 60 s notices, "Sequência concluída" in Exercícios,
"Aula concluída" in Aulas and the Relaxamento progress link. Always: no
console error and no horizontal scroll. The fake clock runs with reduced
motion (no GSAP frames to wait for). Screenshots: QA_ARTIFACT_DIR/app-empresas/.
"""

import os
from pathlib import Path
from unittest import skipIf

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from config.exercises import EXERCISES
from identity.models import Membership, Organization
from wellbeing.models import ActivitySession

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

PASSWORD = "browser-test-password"
VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
SHORT = "Práticas com menos de 1 minuto não entram no seu progresso."
ALL_GSAP = "window.gsap ? gsap.globalTimeline.getChildren(true, true, true).length : 0"
# The element is fully inside the viewport (no scrolling needed to see it).
IN_VIEW = """element => {
    const box = element.getBoundingClientRect();
    return box.top >= 0 && box.left >= 0
        && box.bottom <= window.innerHeight && box.right <= window.innerWidth;
}"""
# Sounds are not under test here: the fake clock would run every audio tick.
SILENT_NOISE = """window.QLNoise && Object.assign(window.QLNoise, {
    play() {}, stop() {}, pause() {}, resume() {}, fadeOut() {}, setVolume() {},
})"""


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class CompanyReadyBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        # One person per recorded practice: the fake clock moves only in the
        # browser, so the server would see back-to-back records as overlapping.
        org = Organization.objects.create(name="QA Empresas", slug="qa-empresas")
        self.users = []
        for index in range(4):
            user = get_user_model().objects.create_user(
                email=f"empresas{index}@example.test", password=PASSWORD
            )
            Membership.objects.create(
                user=user, organization=org, role=Membership.Role.COLLABORATOR
            )
            self.users.append(user)

    def open(self, browser, width, height, person=0):
        context = browser.new_context(
            viewport={"width": width, "height": height}, reduced_motion="reduce"
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
        page.locator("#id_username").fill(self.users[person].email)
        page.locator("#id_password").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_load_state("load")
        page.clock.install()
        return page

    def visit(self, page, path):
        page.goto(f"{self.live_server_url}{path}")
        page.wait_for_load_state("load")

    def screenshot(self, page, name):
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir) / "app-empresas"
            path.mkdir(parents=True, exist_ok=True)
            modal = page.evaluate("Boolean(document.querySelector('dialog[open]'))")
            page.screenshot(path=str(path / f"{name}.png"), full_page=not modal)

    def assert_fits(self, page, label):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow: {label}"
        assert page.errors == [], (label, page.errors)

    def notice(self, page, text):
        notice = page.locator("[data-practice-notice]")
        page.wait_for_function(
            "text => document.querySelector('[data-practice-notice]').textContent === text",
            arg=text,
        )
        assert notice.get_attribute("role") == "status"
        assert notice.evaluate(IN_VIEW)

    def start_session(self, page, path, slug):
        self.visit(page, path)
        page.locator(f'[data-open-session="{slug}"]').click()
        page.locator("[data-player-noise]").select_option("")
        page.locator("[data-player-toggle]").click()

    def test_completion_screen_fits_without_scrolling_and_takes_focus(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            person = 0
            for name, width, height in VIEWPORTS:
                for path, slug, run_ms in (
                    ("/app/meditacao/", "respiracao-foco", 125_000),
                    ("/app/ginastica/", "pescoco-ombros-3min", 185_000),
                ):
                    page = self.open(browser, width, height, person)
                    person += 1
                    self.start_session(page, path, slug)
                    with page.expect_response(
                        lambda r: "pratica/registrar" in r.url
                    ) as info:
                        page.clock.run_for(run_ms)
                    assert info.value.status == 201
                    done = page.locator("[data-player-done]")
                    assert done.is_visible()
                    title = page.get_by_role("heading", name="Sessão concluída")
                    assert title.evaluate(
                        "element => element === document.activeElement"
                    )
                    minutes = 2 if slug == "respiracao-foco" else 3
                    summary = page.locator("[data-player-done-summary]").inner_text()
                    assert f"Você praticou {minutes} min." in summary, summary
                    progress = page.get_by_role("link", name="Ver meu progresso")
                    again = page.get_by_role("button", name="Fazer outra sessão")
                    for element in (title, progress, again):
                        assert element.evaluate(IN_VIEW), (name, slug)
                    # Reduced motion: the screen appears without any animation.
                    assert page.evaluate(ALL_GSAP) == 0
                    self.assert_fits(page, f"{name}-{slug}-concluida")
                    self.screenshot(page, f"{name}-{slug}-concluida")
                    again.click()
                    assert not page.locator("dialog[open]").count()
                    # Already recorded at the end: leaving adds no notice.
                    assert page.locator("[data-practice-notice]").inner_text() == ""
                    page.context.close()
            browser.close()
        assert ActivitySession.objects.count() == 4
        assert ActivitySession.objects.filter(completed=True).count() == 4

    def test_leaving_the_player_tells_what_entered_the_progress(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for person, (name, width, height) in enumerate(VIEWPORTS):
                page = self.open(browser, width, height, person)
                self.start_session(page, "/app/ginastica/", "pausa-coluna-5min")
                page.clock.run_for(20_000)
                page.get_by_role("button", name="← Voltar").click()
                self.notice(page, SHORT)
                self.assert_fits(page, f"{name}-aviso-curto")
                self.screenshot(page, f"{name}-aviso-curto")
                page.clock.run_for(7_000)  # the notice clears itself
                assert page.locator("[data-practice-notice]").inner_text() == ""
                self.start_session(page, "/app/meditacao/", "reduzir-ansiedade")
                page.clock.run_for(65_000)
                page.keyboard.press("Escape")
                self.notice(page, "Prática registrada: 1 min.")
                self.assert_fits(page, f"{name}-aviso-registrada")
                self.screenshot(page, f"{name}-aviso-registrada")
                page.context.close()
            browser.close()
        sessions = list(ActivitySession.objects.values_list("slug", "completed"))
        assert sessions == [("reduzir-ansiedade", False)] * 2, sessions

    def test_relax_timer_end_links_progress_and_early_stop_notices(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for person, (name, width, height) in enumerate(VIEWPORTS):
                page = self.open(browser, width, height, person)
                self.visit(page, "/app/relaxamento/")
                page.evaluate(SILENT_NOISE)
                progress = page.locator("[data-relax-progress]")
                assert progress.is_hidden()
                page.locator('[data-slug="chuva"]').click()
                page.get_by_role("button", name="Parar").click()
                self.notice(page, SHORT)
                page.locator('input[name="wb-timer"][value="5"]').check(force=True)
                page.locator('[data-slug="mar"]').click()
                with page.expect_response(lambda r: "pratica/registrar" in r.url):
                    page.clock.run_for(301_000)
                status = page.locator("[data-relax-status]")
                assert status.inner_text() == "Tempo concluído. O som foi desligado."
                assert progress.is_visible()
                self.assert_fits(page, f"{name}-relaxamento-concluido")
                self.screenshot(page, f"{name}-relaxamento-concluido")
                page.context.close()
            browser.close()
        assert (
            ActivitySession.objects.filter(
                kind="relaxamento", slug="mar", completed=True, duration_seconds=300
            ).count()
            == 2
        )

    def test_exercise_sequence_ends_in_sequencia_concluida(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for person, (name, width, height) in enumerate(VIEWPORTS):
                page = self.open(browser, width, height, person)
                self.visit(page, "/app/exercises/")
                # A quick look at one exercise does not count.
                page.locator("[data-open-exercise]").first.click()
                page.get_by_role("button", name="← Voltar aos exercícios").click()
                self.notice(page, SHORT)
                page.locator("[data-start-sequence]").click()
                next_button = page.locator("[data-next]")
                for _ in range(len(EXERCISES) - 1):
                    assert next_button.inner_text() == "Próximo →"
                    next_button.click()
                assert next_button.inner_text() == "Concluir sequência"
                page.clock.run_for(61_000)
                with page.expect_response(
                    lambda r: "pratica/registrar" in r.url
                ) as info:
                    next_button.click()
                assert info.value.status == 201
                done = page.locator("[data-sequence-done]")
                page.wait_for_function(
                    "document.querySelector('[data-sequence-done]').textContent"
                    ".includes('Prática registrada: 1 min.')"
                )
                assert "Sequência concluída" in done.inner_text()
                assert done.evaluate(IN_VIEW)
                assert next_button.is_disabled()
                self.assert_fits(page, f"{name}-sequencia-concluida")
                self.screenshot(page, f"{name}-sequencia-concluida")
                page.keyboard.press("Escape")
                assert page.locator("[data-practice-notice]").inner_text() == ""
                self.assert_fits(page, f"{name}-exercicios")
                page.context.close()
            browser.close()
        assert (
            list(ActivitySession.objects.values_list("kind", "slug", "completed"))
            == [("ginastica", "sequencia-exercicios", True)] * 2
        )

    def test_lesson_end_shows_aula_concluida_and_short_videos_do_not_record(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for person, (name, width, height) in enumerate(VIEWPORTS):
                page = self.open(browser, width, height, person)
                self.visit(page, "/app/aulas/")
                card = page.locator('[data-lesson="aula-inicio-trabalho"]')
                # A 10 s viewing, then the end of the video.
                card.locator("video").evaluate(
                    """video => {
                        video.dispatchEvent(new Event('playing'));
                        for (let t = 0; t <= 10; t += 0.25) {
                            Object.defineProperty(video, 'currentTime', { value: t, configurable: true });
                            Object.defineProperty(video, 'paused', { value: false, configurable: true });
                            video.dispatchEvent(new Event('timeupdate'));
                        }
                        video.dispatchEvent(new Event('ended'));
                    }"""
                )
                assert (
                    card.locator("[data-lesson-done]").inner_text() == "Aula concluída"
                )
                self.notice(page, SHORT)
                self.assert_fits(page, f"{name}-aula-concluida")
                self.screenshot(page, f"{name}-aula-concluida")
                page.context.close()
            browser.close()
        assert not ActivitySession.objects.exists()

    def test_today_card_fits(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for person, (name, width, height) in enumerate(VIEWPORTS):
                page = self.open(browser, width, height, person)
                self.visit(page, "/app/")
                card = page.locator(".wb-today")
                assert "Você ainda não praticou hoje." in card.inner_text()
                self.assert_fits(page, f"{name}-hoje")
                self.screenshot(page, f"{name}-hoje")
                page.context.close()
            browser.close()
