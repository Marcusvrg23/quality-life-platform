from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.urls import get_resolver
from django.urls.resolvers import URLPattern


class ProjectSmokeTests(SimpleTestCase):
    def test_django_system_checks_pass(self):
        output = StringIO()
        call_command("check", stdout=output)
        self.assertIn("System check identified no issues", output.getvalue())

    def test_security_middleware_is_enabled(self):
        self.assertEqual(
            settings.MIDDLEWARE[0], "django.middleware.security.SecurityMiddleware"
        )
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

    def test_database_backend_is_postgresql(self):
        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"],
            "django.db.backends.postgresql",
        )


class FoundationSurfaceTests(SimpleTestCase):
    def test_health_returns_ok(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)

    def test_health_returns_stable_payload(self):
        response = self.client.get("/health/")

        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_does_not_expose_sensitive_configuration(self):
        response = self.client.get("/health/")
        body = response.content.lower()

        for sensitive_value in (
            b"database_url",
            b"postgres",
            b"secret",
            b"settings",
            b"traceback",
        ):
            self.assertNotIn(sensitive_value, body)

    def test_unknown_url_returns_not_found(self):
        response = self.client.get("/rota-inexistente/")

        self.assertEqual(response.status_code, 404)

    def test_foundation_and_identity_routes_are_registered(self):
        route_names = {
            pattern.name
            for pattern in get_resolver().url_patterns
            if isinstance(pattern, URLPattern)
        }

        self.assertEqual(
            route_names,
            {
                "home",
                "health",
                "login",
                "logout",
                "google_login",
                "google_callback",
                "app",
                "exercises",
                "lessons",
                "select_organization",
                "organization_home",
                "team",
                "team_member_status",
                "team_emails_add",
                "team_email_remove",
                "team_invitations_create",
                "team_invitation_revoke",
                "operator_panel",
                "operator_organization_create",
                "operator_organization_status",
                "operator_organization_emails",
                "operator_email_add",
                "operator_email_remove",
                "operator_email_role",
                "operator_manager_invitation",
                "operator_enter",
                "password_change",
                "privacy_settings",
                "privacy_revoke",
                "privacy",
                "terms",
                "accept_invitation",
                "password_reset_confirm",
                "password_reset_complete",
                "install_app",
                "about_quality",
                "manifest",
                "service_worker",
                "offline",
            },
        )

    def test_public_routes_reject_non_get_methods(self):
        for route in ("/", "/health/"):
            with self.subTest(route=route):
                response = self.client.post(route)

                self.assertEqual(response.status_code, 405)


class PostgreSQLConnectionSmokeTests(TestCase):
    def test_postgresql_connection_executes_select_one(self):
        self.assertEqual(connection.vendor, "postgresql")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone(), (1,))
