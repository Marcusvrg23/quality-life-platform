"""Browser QA for the dark app and auth pages (spec 09) at 390x844 and 1280x800.

Every listed page: no horizontal scroll, no console error, dark background,
Figtree/Cormorant, AA contrast on the main texts, visible keyboard focus and a
screenshot in QA_ARTIFACT_DIR/app-dark/. Also: light ambient canvas runs and
pauses with the tab hidden, reduced motion runs nothing and hides nothing,
the individual map stays on a light card, the exercise player and the
hamburger menu still work.
"""

import os
import re
from decimal import Decimal
from importlib import import_module
from io import StringIO
from pathlib import Path
from unittest import skipIf

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from assessments.models import (
    Assessment,
    AssessmentResult,
    Pillar,
    PillarResult,
    QuestionnaireVersion,
)
from assessments.services import classify_score
from identity.consent import grant_consent
from identity.invitations import issue_invitations
from identity.models import Membership, Organization

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

NINE_PILLARS = import_module("assessments.migrations.0002_nine_pillars")
V2_FILE = (
    Path(settings.BASE_DIR)
    / "assessments"
    / "questionnaires"
    / "quality_life_oficial_v2.json"
)
PASSWORD = "browser-test-password"
VIEWPORTS = (("390", 390, 844), ("1280", 1280, 800))
SCORES = (
    ("91.00", "88", "76", "64", "52", "45", "38", "71", "86", "90"),
    ("82.50", "80", "72", "61", "55", "48", "35", "75", "84", "88"),
    ("67.00", "66", "70", "58", "41", "39", "62", "73", "77", "69"),
    ("58.25", "52", "60", "44", "37", "30", "65", "70", "72", "71"),
    ("74.00", "78", "81", "62", "58", "40", "52", "77", "90", "79"),
)

# Composite background colors up the ancestor chain (gradients fall back to
# their background-color) and check WCAG AA on elements that own text.
CONTRAST = r"""() => {
    const parse = value => {
        const m = value.match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
        return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const over = (top, bottom) => {
        const a = top[3] + bottom[3] * (1 - top[3]);
        if (!a) return [0, 0, 0, 0];
        return [0, 1, 2].map(i => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / a).concat(a);
    };
    const background = element => {
        const layers = [];
        for (let node = element; node; node = node.parentElement) {
            const color = parse(getComputedStyle(node).backgroundColor);
            if (color && color[3] > 0) layers.push(color);
            if (color && color[3] >= 1) break;
        }
        let result = parse(getComputedStyle(document.documentElement).backgroundColor) || [255, 255, 255, 1];
        if (result[3] < 1) result = over(result, [255, 255, 255, 1]);
        for (let i = layers.length - 1; i >= 0; i -= 1) result = over(layers[i], result);
        return result;
    };
    const lum = c => {
        const ch = c.slice(0, 3).map(v => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
    };
    const ratio = (a, b) => {
        const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
        return (hi + 0.05) / (lo + 0.05);
    };
    const selector = 'h1,h2,h3,p,li,a,button,label,td,th,dt,dd,summary,legend,small,strong,b,span,div';
    const failures = [];
    let checked = 0;
    for (const element of document.querySelectorAll(selector)) {
        if (element.closest('svg, [aria-hidden="true"], dialog:not([open]), [hidden], .ql-skip')) continue;
        if (element.disabled) continue;
        const own = [...element.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
        if (!own) continue;
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        if (!box.width || !box.height || style.visibility === 'hidden') continue;
        const bg = background(element);
        let fg = parse(style.color);
        if (!fg) continue;
        if (fg[3] < 1) fg = over(fg, bg);
        const size = parseFloat(style.fontSize);
        const weight = Number(style.fontWeight) || 400;
        const large = size >= 24 || (size >= 18.66 && weight >= 700);
        const value = ratio(fg, bg);
        checked += 1;
        if (value < (large ? 3 : 4.5)) {
            failures.push({
                text: element.textContent.trim().slice(0, 40),
                cls: String(element.className).slice(0, 40),
                tag: element.tagName,
                ratio: Math.round(value * 100) / 100,
                fg: style.color,
                bg: 'rgb(' + bg.slice(0, 3).map(Math.round).join(',') + ')',
            });
        }
    }
    return {checked, failures};
}"""
BODY_LUMINANCE = """() => {
    const c = getComputedStyle(document.body).backgroundColor.match(/\\d+(\\.\\d+)?/g).map(Number);
    const ch = c.slice(0, 3).map(v => (v /= 255) <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}"""
FONTS = """async () => {
    await document.fonts.ready;
    const heading = document.querySelector('h1');
    return {
        body: getComputedStyle(document.body).fontFamily,
        heading: heading ? getComputedStyle(heading).fontFamily : null,
        figtree: document.fonts.check('400 16px "Figtree"'),
        cormorant: document.fonts.check('600 32px "Cormorant Garamond"'),
    };
}"""
FOCUS_STYLE = """() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const s = getComputedStyle(el);
    return {
        tag: el.tagName,
        text: (el.textContent || el.name || '').trim().slice(0, 30),
        outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0,
        ring: s.boxShadow !== 'none',
    };
}"""
GSAP_IDLE = (
    "!window.gsap || gsap.globalTimeline.getChildren(true, true, false)"
    ".every(t => t.totalProgress() === 1)"
)
FRAMES = "() => window.QLAmbient ? window.QLAmbient.frames('ambient') : 0"
HIDE_TAB = """() => {
    Object.defineProperty(document, 'hidden', {value: true, configurable: true});
    document.dispatchEvent(new Event('visibilitychange'));
}"""
CARDS = (
    ".card, .dashboard-hero, .dashboard-link, .dashboard-recommendation, "
    ".exercise-card, .lesson-card, .team-row, .legal-settings, .legal-doc, "
    ".quality-map, .login-form-wrap, .foundation"
)


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class AppDarkBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        # Live-server tests flush the database; restore migration 0002's pillars.
        for order, (code, name) in enumerate(NINE_PILLARS.PILLARS, start=1):
            Pillar.objects.get_or_create(
                code=code, defaults={"name": name, "display_order": order}
            )
        call_command(
            "load_official_questionnaire", file=str(V2_FILE), stdout=StringIO()
        )
        users = get_user_model().objects
        self.org = Organization.objects.create(name="QA Escuro", slug="qa-escuro")
        other = Organization.objects.create(name="QA Escuro Dois", slug="qa-escuro-2")
        self.flow = users.create_user(email="fluxo@example.test", password=PASSWORD)
        manager = users.create_user(email="gestor@example.test", password=PASSWORD)
        multi = users.create_user(email="multi@example.test", password=PASSWORD)
        users.create_user(email="semacesso@example.test", password=PASSWORD)
        users.create_superuser(email="ql@example.test", password=PASSWORD)
        self.reset_user = users.create_user(
            email="reset@example.test", password=PASSWORD
        )
        for user, org, role in (
            (self.flow, self.org, Membership.Role.COLLABORATOR),
            (manager, self.org, Membership.Role.CORPORATE_MANAGER),
            (multi, self.org, Membership.Role.COLLABORATOR),
            (multi, other, Membership.Role.COLLABORATOR),
        ):
            Membership.objects.create(user=user, organization=org, role=role)
        version = QuestionnaireVersion.objects.create(
            code="dark-test-only",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-dark",
        )
        pillars = list(Pillar.objects.order_by("display_order"))
        self.map_assessment = None
        for index, (overall, *scores) in enumerate(SCORES):
            user = users.create_user(
                email=f"mapa{index}@example.test", password=PASSWORD
            )
            Membership.objects.create(
                user=user, organization=self.org, role=Membership.Role.COLLABORATOR
            )
            grant_consent(user, self.org)
            # Result first, then complete, as the immutability rules expect.
            assessment = Assessment.objects.create(
                user=user, organization=self.org, questionnaire_version=version
            )
            result = AssessmentResult.objects.create(
                assessment=assessment,
                overall_score=Decimal(overall),
                overall_band=classify_score(Decimal(overall)),
                scoring_version="test-dark",
            )
            for pillar, score in zip(pillars, scores, strict=True):
                PillarResult.objects.create(
                    assessment_result=result,
                    pillar=pillar,
                    score=Decimal(score),
                    band=classify_score(Decimal(score)),
                )
            assessment.status = Assessment.Status.COMPLETED
            assessment.completed_at = timezone.now()
            assessment.save()
            self.map_assessment = self.map_assessment or assessment
        self.invite = issue_invitations(self.org, manager, 1)[0]
        uid = urlsafe_base64_encode(force_bytes(self.reset_user.pk))
        token = default_token_generator.make_token(self.reset_user)
        self.reset_path = f"/senha/redefinir/{uid}/{token}/"

    # Helpers -----------------------------------------------------------------

    def open(self, browser, width, height, reduced_motion="no-preference"):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            reduced_motion=reduced_motion,
        )
        page = context.new_page()
        page.errors = []
        page.on(
            "console",
            lambda message: (
                message.type == "error"
                and "status of 403" not in message.text
                and page.errors.append(message.text)
            ),
        )
        page.on("pageerror", lambda error: page.errors.append(str(error)))
        return page

    def login(self, page, email):
        page.goto(f"{self.live_server_url}/login/")
        page.locator("#id_username").fill(email)
        page.locator("#id_password").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_load_state("load")

    def visit(self, page, path):
        page.goto(f"{self.live_server_url}{path}")
        page.wait_for_load_state("load")
        page.wait_for_function(GSAP_IDLE)

    def screenshot(self, page, name):
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir) / "app-dark"
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / f"{name}.png"), full_page=True)

    def check_page(self, page, label):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow: {label}"
        assert page.evaluate(BODY_LUMINANCE) < 0.03, f"Background not dark: {label}"
        fonts = page.evaluate(FONTS)
        assert "Figtree" in fonts["body"], (label, fonts)
        assert fonts["figtree"], (label, fonts)
        if fonts["heading"] is not None:
            assert "Cormorant Garamond" in fonts["heading"], (label, fonts)
            assert fonts["cormorant"], (label, fonts)
        contrast = page.evaluate(CONTRAST)
        assert contrast["checked"] >= 3, (label, contrast)
        assert contrast["failures"] == [], (label, contrast["failures"][:6])
        self.screenshot(page, label)
        page.locator("body").click(position={"x": 1, "y": 1})
        seen = 0
        for _ in range(8):
            page.keyboard.press("Tab")
            focus = page.evaluate(FOCUS_STYLE)
            if focus is None:
                continue
            seen += 1
            assert focus["outline"] or focus["ring"], (label, focus)
        # Any page with a link, button or field must take keyboard focus.
        focusable = page.evaluate(
            "document.querySelectorAll('a[href], button, input:not([type=hidden]),"
            " textarea, select, summary').length"
        )
        assert seen or not focusable, f"Nothing focusable by keyboard: {label}"
        page.keyboard.press("Escape")
        assert page.errors == [], (label, page.errors)

    def collaborator_pages(self, page):
        """Pages of the collaborator flow, starting the questionnaire for real."""
        yield "hoje", "/app/"
        yield "exercicios", "/app/exercises/"
        yield "aulas", "/app/aulas/"
        yield "avaliacao-hub", "/app/assessment/"
        # The second viewport finds the assessment already started.
        if page.locator('input[name="consent"]').count():
            page.locator('input[name="consent"]').check()
            page.get_by_role("button", name="Iniciar avaliação").click()
        else:
            page.get_by_role("link", name="Retomar avaliação").click()
        page.wait_for_url(re.compile(r".*/question/\d+/$"))
        assessment = re.search(r"/assessment/(\d+)/", page.url).group(1)
        yield "pergunta", page.url.replace(self.live_server_url, "")
        yield "revisao", f"/app/assessment/{assessment}/review/"
        yield "privacidade-app", "/app/privacidade/"
        yield "senha", "/app/senha/"

    # Tests -------------------------------------------------------------------

    def test_every_page_is_dark_readable_and_focusable(self):
        map_path = f"/app/assessment/{self.map_assessment.pk}/completed/"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                for label, path in (
                    ("login", "/login/"),
                    ("convite", f"/convite/{self.invite}/"),
                    ("redefinir-senha", self.reset_path),
                    ("privacidade", "/privacidade/"),
                    ("termos", "/termos/"),
                ):
                    self.visit(page, path)
                    self.check_page(page, f"{name}-{label}")
                page.context.close()

                page = self.open(browser, width, height)
                self.login(page, "semacesso@example.test")
                page.get_by_role("button", name="Sair").wait_for()
                self.check_page(page, f"{name}-sem-acesso")
                page.context.close()

                # Spec 12: a superuser without a company lands on the panel.
                page = self.open(browser, width, height)
                self.login(page, "ql@example.test")
                assert page.url.endswith("/app/painel/"), page.url
                page.wait_for_function(GSAP_IDLE)
                self.check_page(page, f"{name}-painel")
                page.locator(
                    "summary", has_text="Entrar como administrador"
                ).first.click()
                page.get_by_role("button", name="Confirmar e entrar").first.wait_for()
                self.check_page(page, f"{name}-painel-entrar")
                # Spec 14: the per-company allowed e-mail list.
                self.visit(page, f"/app/painel/empresas/{self.org.pk}/emails/")
                self.check_page(page, f"{name}-painel-emails")
                page.context.close()

                page = self.open(browser, width, height)
                self.login(page, "multi@example.test")
                page.get_by_role("heading", name="Selecione sua organização").wait_for()
                self.check_page(page, f"{name}-escolher-empresa")
                page.context.close()

                page = self.open(browser, width, height)
                self.login(page, "fluxo@example.test")
                for label, path in self.collaborator_pages(page):
                    if path:
                        self.visit(page, path)
                    self.check_page(page, f"{name}-{label}")
                page.context.close()

                page = self.open(browser, width, height)
                self.login(page, "mapa0@example.test")
                self.visit(page, map_path)
                self.check_page(page, f"{name}-mapa")
                # Light "document" card inside the dark app.
                light = page.evaluate(
                    "() => getComputedStyle(document.querySelector('.quality-map'))"
                    ".backgroundColor"
                )
                channels = [int(v) for v in re.findall(r"\d+", light)[:3]]
                assert min(channels) > 235, light
                assert page.locator(".heart-segment").count() == 9
                page.context.close()

                page = self.open(browser, width, height)
                self.login(page, "gestor@example.test")
                for label, path in (
                    ("relatorio", "/app/report/"),
                    ("equipe", "/app/equipe/"),
                ):
                    self.visit(page, path)
                    self.check_page(page, f"{name}-{label}")
                    if label == "relatorio":
                        assert page.locator(".report-table tbody tr").count() == 9
                page.context.close()
            browser.close()

    def test_light_ambient_runs_pauses_hidden_and_skips_reading_pages(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser, 1280, 800)
            self.login(page, "fluxo@example.test")
            self.visit(page, "/app/")
            assert page.locator("#ql-ambient").get_attribute("data-ambient") == "lite"
            page.wait_for_function(f"({FRAMES})() > 10")
            page.evaluate(HIDE_TAB)
            page.wait_for_timeout(100)
            paused = page.evaluate(FRAMES)
            page.wait_for_timeout(500)
            assert page.evaluate(FRAMES) == paused
            for path in ("/app/assessment/", "/app/privacidade/", "/termos/"):
                self.visit(page, path)
                assert page.locator("#ql-ambient").count() == 0, path
            assert page.errors == [], page.errors
            browser.close()

    def test_reduced_motion_runs_no_loop_and_hides_nothing(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height, reduced_motion="reduce")
                self.visit(page, "/login/")
                self.login(page, "fluxo@example.test")
                for path in ("/app/", "/app/exercises/", "/app/aulas/"):
                    self.visit(page, path)
                    page.wait_for_timeout(300)
                    assert page.evaluate(FRAMES) == 0, path
                    assert page.evaluate(
                        "!window.gsap || gsap.globalTimeline.getChildren(true, true,"
                        " false).length === 0"
                    ), path
                    hidden = page.evaluate(
                        f"[...document.querySelectorAll('{CARDS}')]"
                        ".filter(el => getComputedStyle(el).opacity !== '1')"
                        ".map(el => el.className)"
                    )
                    assert hidden == [], (path, hidden)
                    slug = path.strip("/").replace("/", "-")
                    self.screenshot(page, f"{name}-reduced-{slug}")
                assert page.errors == [], page.errors
                page.context.close()
            browser.close()

    def test_mobile_menu_is_glass_and_accessible(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = self.open(browser, 390, 844)
            self.login(page, "gestor@example.test")
            self.visit(page, "/app/")
            toggle = page.locator(".ql-menu-toggle")
            assert toggle.is_visible()
            assert toggle.get_attribute("aria-expanded") == "false"
            toggle.click()
            assert toggle.get_attribute("aria-expanded") == "true"
            nav = page.locator("#app-navigation")
            nav.get_by_role("link", name="Relatório da empresa").wait_for()
            assert nav.get_by_role("link", name="Equipe").is_visible()
            assert page.evaluate(
                "getComputedStyle(document.getElementById('app-navigation'))"
                ".backdropFilter.includes('blur')"
            )
            current = nav.locator('[aria-current="page"]')
            assert "gradient" in current.evaluate(
                "el => getComputedStyle(el).backgroundImage"
            )
            self.screenshot(page, "390-menu-aberto")
            page.keyboard.press("Escape")
            assert toggle.get_attribute("aria-expanded") == "false"
            assert page.evaluate(
                "document.activeElement === document.querySelector('.ql-menu-toggle')"
            )
            assert page.errors == [], page.errors
            browser.close()

    def test_exercise_player_frames_white_images_and_advances(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, width, height in VIEWPORTS:
                page = self.open(browser, width, height)
                self.login(page, "fluxo@example.test")
                self.visit(page, "/app/exercises/")
                frame = page.evaluate(
                    "getComputedStyle(document.querySelector('.exercise-card-visual'))"
                    ".backgroundColor"
                )
                assert min(int(v) for v in re.findall(r"\d+", frame)[:3]) > 235, frame
                page.get_by_role("button", name="Começar sequência").click()
                position = page.locator("[data-sequence-position]")
                assert position.inner_text() == "Exercício 1 de 9"
                page.get_by_role("button", name="Próximo →").click()
                assert position.inner_text() == "Exercício 2 de 9"
                page.wait_for_function(GSAP_IDLE)
                image = page.evaluate(
                    "(() => { const s = getComputedStyle("
                    "document.querySelector('.exercise-detail-image'));"
                    " return [s.backgroundColor, s.borderRadius]; })()"
                )
                assert min(int(v) for v in re.findall(r"\d+", image[0])[:3]) > 235
                assert float(image[1].rstrip("px")) >= 12, image
                assert page.locator(".exercise-sequence button[data-next]").is_visible()
                self.screenshot(page, f"{name}-player")
                page.keyboard.press("Escape")
                assert page.errors == [], page.errors
                page.context.close()
            browser.close()
