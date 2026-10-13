"""Public landing page at "/": content, pillars from the database, auth state."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from assessments.models import Pillar

PILLAR_NAMES = [
    "Saúde Física",
    "Comportamento Preventivo",
    "Atividade Física",
    "Alimentação e Hidratação",
    "Relacionamentos",
    "Saúde Mental e Emocional",
    "Ergonomia e Ambiente de Trabalho",
    "Sono e Recuperação",
    "Equilíbrio Vida × Trabalho",
]


class HomePageTests(TestCase):
    def test_home_returns_ok_with_new_template(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertContains(response, "Sua pausa também faz parte do trabalho.")

    def test_home_links_to_login_privacy_and_terms(self):
        response = self.client.get("/")

        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertContains(response, f'href="{reverse("terms")}"')
        self.assertContains(response, ">Entrar<")
        self.assertNotContains(response, "Abrir o app")

    def test_home_loads_brand_assets_and_deferred_scripts(self):
        response = self.client.get("/")

        for path in (
            "quality_life/brand.css",
            "quality_life/home.css",
            "quality_life/home.js",
            "quality_life/vendor/gsap-3.13.0.min.js",
            "quality_life/vendor/ScrollTrigger-3.13.0.min.js",
            "quality_life/images/brand/quality-life-logo-ring-192.png",
            "quality_life/fonts/quicksand-latin-700.woff2",
            "quality_life/fonts/figtree-latin-400.woff2",
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path))
        for script in ("gsap-3.13.0.min.js", "ScrollTrigger-3.13.0.min.js", "home.js"):
            with self.subTest(script=script):
                self.assertRegex(
                    response.content.decode(), rf'<script defer src="[^"]*{script}">'
                )
        self.assertNotContains(response, "fonts.googleapis.com")

    def test_pillars_come_from_database_in_display_order(self):
        response = self.client.get("/")
        body = response.content.decode()

        # rindex: the hero preview also mentions "Sono e Recuperação".
        positions = [body.rindex(name) for name in PILLAR_NAMES]
        self.assertEqual(positions, sorted(positions))
        for name in PILLAR_NAMES:
            with self.subTest(pillar=name):
                self.assertContains(response, name)

    def test_pillar_list_is_not_hardcoded_in_template(self):
        # Pillar.save() forbids renames; queryset update simulates new data.
        Pillar.objects.filter(display_order=2).update(name="Pilar Vindo Do Banco")

        response = self.client.get("/")

        self.assertContains(response, "Pilar Vindo Do Banco")
        self.assertNotContains(response, "Comportamento Preventivo")
        self.assertEqual(Pillar.objects.count(), 9)

    def test_authenticated_user_sees_open_app_button(self):
        user = get_user_model().objects.create_user(
            email="landing@example.test", password="test-password"
        )
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, "Abrir o app")
        self.assertContains(response, f'href="{reverse("app")}"')

    @override_settings()
    def test_renders_without_sales_email_setting(self):
        del settings.QL_SALES_EMAIL

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="mailto:[EMAIL-COMERCIAL]"')

    @override_settings(QL_SALES_EMAIL="vendas@example.test")
    def test_sales_button_uses_configured_email(self):
        response = self.client.get("/")

        self.assertContains(response, 'href="mailto:vendas@example.test"')
        self.assertContains(response, "Fale com a Quality Life")

    def test_home_does_not_expose_dpo_email_as_sales_contact(self):
        with override_settings(LEGAL_DPO_EMAIL="dpo@example.test"):
            response = self.client.get("/")

        self.assertNotContains(response, "dpo@example.test")
