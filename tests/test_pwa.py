"""Installable app: manifest, service worker, offline page and install screen
(docs/specs/13-pwa-lembretes.md, aceite 1-4)."""

import json
import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization, User

PASSWORD = "pwa-test-password"
BRAND = "/static/quality_life/images/brand/quality-life-logo-ring-"


class PublicPwaFilesTests(SimpleTestCase):
    def test_manifest_is_served_with_brand_and_official_icons(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        manifest = json.loads(response.content)
        self.assertEqual(manifest["name"], "Quality Life")
        self.assertEqual(manifest["start_url"], "/app/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        # --ql-purple and --ql-bg in static/quality_life/brand.css.
        self.assertEqual(manifest["theme_color"], "#84267d")
        self.assertEqual(manifest["background_color"], "#fbf8f4")
        icons = {icon["sizes"]: icon["src"] for icon in manifest["icons"]}
        self.assertEqual(icons["192x192"], f"{BRAND}192.png")
        self.assertEqual(icons["512x512"], f"{BRAND}512.png")
        self.assertTrue(all(i["type"] == "image/png" for i in manifest["icons"]))

    def test_service_worker_is_served_at_root_without_http_cache(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/javascript; charset=utf-8")
        self.assertIn("no-cache", response["Cache-Control"])

    def test_service_worker_caches_only_offline_page_icon_and_hashed_static(self):
        body = self.client.get("/sw.js").content.decode()
        # No app URL anywhere: the notification target travels in its data.
        self.assertNotIn("/app/", body)
        precache = json.loads(re.search(r"const PRECACHE = (\[.*?\]);", body)[1])
        self.assertEqual(precache, [reverse("offline"), f"{BRAND}192.png"])
        self.assertIn("/static/", body)
        # Only GET is ever handled; navigations fall back to the offline page
        # but are never written to the cache.
        self.assertIn("request.method !== 'GET'", body)
        self.assertEqual(body.count("cache.put("), 1)
        self.assertIn("HASHED_STATIC.test(url.pathname)", body)

    def test_service_worker_cache_name_changes_with_precache(self):
        body = self.client.get("/sw.js").content.decode()
        self.assertRegex(body, r"const CACHE = 'ql-static-[0-9a-f]{12}';")

    def test_offline_page_is_public_and_simple(self):
        response = self.client.get(reverse("offline"))
        self.assertContains(response, "Sem conexão. Tente de novo.")
        self.assertNotContains(response, "<script")

    def test_login_links_manifest_and_registers_worker(self):
        response = self.client.get(reverse("login"))
        self.assertContains(
            response, '<link rel="manifest" href="/manifest.webmanifest">'
        )
        self.assertContains(response, 'data-sw="/sw.js"')
        self.assertContains(response, "quality_life/pwa.js")

    def test_auth_base_pages_link_manifest(self):
        response = self.client.get(reverse("password_reset_complete"))
        self.assertContains(
            response, '<link rel="manifest" href="/manifest.webmanifest">'
        )
        self.assertContains(response, "quality_life/pwa.js")


class ShellPwaTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.user = User.objects.create_user("pessoa@empresa.test", PASSWORD)
        Membership.objects.create(user=self.user, organization=self.organization)

    def test_app_shell_links_manifest_menu_and_reminder_scheduler(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("wellbeing_gym"))
        self.assertContains(
            response, '<link rel="manifest" href="/manifest.webmanifest">'
        )
        self.assertContains(response, 'data-sw="/sw.js"')
        self.assertContains(response, f'href="{reverse("install_app")}"')
        self.assertContains(response, f'href="{reverse("wellbeing_reminders")}"')
        self.assertContains(
            response, f'data-schedule="{reverse("wellbeing_reminder_schedule")}"'
        )

    def test_operator_panel_without_tenant_still_opens_without_reminders(self):
        root = User.objects.create_superuser("ql@quality.test", PASSWORD)
        self.client.force_login(root)
        response = self.client.get(reverse("operator_panel"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("install_app")}"')
        self.assertNotContains(response, reverse("wellbeing_reminders"))
        self.assertNotContains(response, "data-schedule=")
        self.assertContains(response, 'data-sw="/sw.js"')


class InstallPageTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.user = User.objects.create_user("pessoa@empresa.test", PASSWORD)
        Membership.objects.create(user=self.user, organization=self.organization)

    def test_requires_login(self):
        response = self.client.get(reverse("install_app"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_explains_android_iphone_installed_and_stores_soon(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("install_app"))
        self.assertContains(response, "Instalar o app")
        # The install button exists only for beforeinstallprompt to reveal.
        self.assertContains(
            response,
            '<button type="button" class="button" data-install-button hidden>'
            "Adicionar à tela inicial</button>",
            html=True,
        )
        self.assertContains(response, "Compartilhar")
        self.assertContains(response, "Adicionar à Tela de Início")
        self.assertContains(response, "O app já está na sua tela inicial.")
        self.assertContains(response, "Apps na App Store e no Google Play: em breve.")

    def test_never_suggests_store_availability(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("install_app")).content.decode().lower()
        for forbidden in (
            "baixe na",
            "disponível na app store",
            "disponível no google play",
            "play.google.com",
            "apps.apple.com",
            "badge",
            "selo",
        ):
            self.assertNotIn(forbidden, html)

    def test_operator_without_tenant_can_open(self):
        root = User.objects.create_superuser("ql@quality.test", PASSWORD)
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse("install_app")).status_code, 200)

    def test_forged_tenant_is_forbidden(self):
        other = Organization.objects.create(name="Outra", slug="outra")
        self.client.force_login(self.user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = other.pk
        session.save()
        self.assertEqual(self.client.get(reverse("install_app")).status_code, 403)
