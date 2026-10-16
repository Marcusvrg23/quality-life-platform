"""Dark neon/glass theme wiring for the app shell and auth pages (spec 09)."""

import re
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from config.exercises import EXERCISES, SOURCE
from config.forms import EmailAuthenticationForm

STATIC = Path(settings.BASE_DIR) / "static" / "quality_life"
RING_LOGO = "quality_life/images/brand/quality-life-logo-ring-"
AMBIENT = 'id="ql-ambient"'


class AppDarkTemplateTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get(reverse("app"))
        self.request.user = get_user_model()(email="dark.member@example.test")
        self.request.resolver_match = resolve(reverse("app"))
        self.tenant = SimpleNamespace(
            organization=SimpleNamespace(name="Dark Company"), role="COLLABORATOR"
        )

    def render(self, template, url_name="app", **context):
        self.request.resolver_match = resolve(reverse(url_name))
        return render_to_string(
            template, {"tenant": self.tenant, **context}, request=self.request
        )

    def assert_dark_assets(self, html):
        self.assertIn("quality_life/brand.css", html)
        self.assertIn("quality_life/app-dark.css", html)
        self.assertIn(RING_LOGO, html)
        self.assertNotIn("quality_life/images/quality-life-logo.png", html)
        self.assertNotRegex(html, r'(href|src)="(https?:)?//')

    def test_shell_loads_dark_theme_last_and_motion_once(self):
        html = self.render("identity/app.html")
        self.assert_dark_assets(html)
        self.assertLess(
            html.index("quality_life/app-shell.css"),
            html.index("quality_life/app-dark.css"),
        )
        self.assertLess(
            html.index("quality_life/dashboard.css"),
            html.index("quality_life/app-dark.css"),
        )
        self.assertEqual(html.count("gsap-3.13.0.min.js"), 1)
        self.assertEqual(html.count("quality_life/app-motion.js"), 1)
        # The image cap stays the very first style rule.
        rule = "<style>img { max-width: 100%; height: auto; }</style>"
        self.assertLess(html.index(rule), html.index('rel="stylesheet"'))

    def test_activity_pages_get_the_light_ambient_canvas(self):
        for template, url_name, context in (
            ("identity/app.html", "app", {}),
            (
                "exercises/library.html",
                "exercises",
                {"exercises": EXERCISES, "source": SOURCE},
            ),
            ("lessons/lessons.html", "lessons", {"lessons": []}),
        ):
            with self.subTest(template=template):
                html = self.render(template, url_name, **context)
                self.assertIn(AMBIENT, html)
                self.assertIn('data-ambient="lite"', html)
                self.assertIn("quality_life/ambient.js", html)
                self.assertEqual(html.count("gsap-3.13.0.min.js"), 1)

    def test_long_reading_pages_have_no_animated_canvas(self):
        self.tenant.role = "CORPORATE_MANAGER"
        report = SimpleNamespace(insufficient_data=True)
        html = self.render("reports/executive.html", "executive_report", report=report)
        self.assertNotIn(AMBIENT, html)
        self.assertNotIn("quality_life/ambient.js", html)
        self.tenant.role = "COLLABORATOR"
        for template, url_name, context in (
            ("assessments/hub.html", "assessment_hub", {"available": True}),
            ("legal/settings.html", "privacy_settings", {"consents": []}),
        ):
            with self.subTest(template=template):
                html = self.render(template, url_name, **context)
                self.assert_dark_assets(html)
                self.assertNotIn(AMBIENT, html)
                self.assertNotIn("quality_life/ambient.js", html)

    def test_public_legal_pages_are_dark_without_canvas(self):
        for url_name in ("privacy", "terms"):
            with self.subTest(url_name=url_name):
                html = self.client.get(reverse(url_name)).content.decode()
                self.assert_dark_assets(html)
                self.assertIn("MINUTA — pendente de revisão jurídica", html)
                self.assertNotIn(AMBIENT, html)

    def test_auth_pages_are_dark_and_keep_their_forms(self):
        login = self.render(
            "identity/login.html",
            form=EmailAuthenticationForm(),
            next=reverse("app"),
        )
        self.assert_dark_assets(login)
        # One visible logo; the apple-touch-icon link is the home screen icon.
        self.assertEqual(login.count(f'src="/static/{RING_LOGO}'), 1)
        self.assertIn('name="username"', login)
        self.assertIn('name="password"', login)
        self.assertIn(f'method="post" action="{reverse("login")}"', login)
        self.assertIn(AMBIENT, login)
        for template, context in (
            ("identity/no_access.html", {}),
            ("identity/select_organization.html", {"memberships": []}),
            ("identity/invitation_invalid.html", {"message": "Expirado."}),
        ):
            with self.subTest(template=template):
                html = self.render(template, **context)
                self.assert_dark_assets(html)
        select = self.render("identity/select_organization.html", memberships=[])
        # identity.css has local edits on Marcus's PC: still linked, never edited.
        self.assertLess(
            select.index("quality_life/identity.css"),
            select.index("quality_life/app-dark.css"),
        )
        self.assertIn(f'action="{reverse("logout")}"', select)

    def test_quality_map_keeps_its_own_script_and_svg_hook(self):
        source = (
            Path(settings.BASE_DIR) / "templates" / "assessments" / "completed.html"
        ).read_text(encoding="utf-8")
        self.assertIn("quality_life/quality-map.js", source)
        self.assertIn('class="quality-heart"', source)
        # GSAP comes from the shell once; the map page must not load it again.
        self.assertNotIn("gsap-3.13.0.min.js", source)


class AppDarkStylesheetTests(SimpleTestCase):
    def setUp(self):
        self.css = (STATIC / "app-dark.css").read_text(encoding="utf-8")

    def test_no_remote_resources(self):
        self.assertNotRegex(self.css, r"url\(\s*['\"]?(https?:)?//")
        self.assertNotIn("@import", self.css)

    def test_reduced_motion_disables_transitions_and_animations(self):
        block = re.search(
            r"@media \(prefers-reduced-motion: reduce\) \{(.+?)\n\}",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        self.assertIn("transition: none", block.group(1))
        self.assertIn("animation: none", block.group(1))

    def test_band_seals_cover_the_four_bands(self):
        for band in ("EXCELENTE", "BOM", "ATENÇÃO", "PRIORIDADE"):
            self.assertIn(f'[data-band="{band}"]', self.css)

    def test_print_restores_light_tokens(self):
        self.assertIn("@media print", self.css)

    def test_identity_css_is_untouched_by_the_theme(self):
        # The theme overrides identity.css rules from app-dark.css only.
        self.assertIn(".organizations button", self.css)
