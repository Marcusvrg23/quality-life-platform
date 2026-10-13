"""Public landing contracts, using the approved pillars from the database."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from assessments.models import Pillar


class HomeTests(TestCase):
    def test_home_template_and_public_links(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        for name in ("login", "privacy", "terms"):
            self.assertContains(response, f'href="{reverse(name)}"')
        self.assertContains(response, "Sua pausa também faz parte do")

    def test_nine_pillars_are_read_from_database_in_display_order(self):
        pillars = list(Pillar.objects.order_by("display_order"))
        self.assertEqual(len(pillars), 9)
        # QuerySet.update intentionally bypasses the immutable model's save guard:
        # a distinct name proves that the landing is not a hard-coded copy.
        Pillar.objects.filter(pk=pillars[0].pk).update(name="Pilar vindo do banco")
        response = self.client.get("/")
        names = list(
            Pillar.objects.order_by("display_order").values_list("name", flat=True)
        )
        self.assertQuerySetEqual(
            response.context["pillars"], names, transform=lambda p: p.name
        )
        body = response.content.decode()
        positions = []
        for name in names:
            self.assertContains(response, name)
            positions.append(body.index(name))
        self.assertEqual(positions, sorted(positions))

    def test_authenticated_user_can_open_app(self):
        user = get_user_model().objects.create_user(
            email="landing@example.test", password="test-password"
        )
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertContains(response, "Abrir o app")
        self.assertContains(response, f'href="{reverse("app")}"')

    @override_settings(
        QL_SALES_EMAIL="comercial@example.test", LEGAL_DPO_EMAIL="dpo@example.test"
    )
    def test_sales_contact_is_separate_from_privacy_contact(self):
        response = self.client.get("/")
        self.assertContains(response, 'href="mailto:comercial@example.test"')
        self.assertNotContains(response, "dpo@example.test")

    def test_missing_sales_setting_uses_placeholder(self):
        with override_settings():
            if hasattr(settings, "QL_SALES_EMAIL"):
                del settings.QL_SALES_EMAIL
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mailto:[EMAIL-COMERCIAL]")

    def test_animation_assets_are_deferred_and_local(self):
        response = self.client.get("/")
        for asset in (
            "vendor/gsap-3.13.0.min.js",
            "vendor/ScrollTrigger-3.13.0.min.js",
            "home.js",
        ):
            self.assertContains(
                response, f'<script defer src="/static/quality_life/{asset}"></script>'
            )
        self.assertNotContains(response, "fonts.googleapis.com")
