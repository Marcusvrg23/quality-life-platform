from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.urls import get_resolver


class ProjectSmokeTests(SimpleTestCase):
    def test_django_system_checks_pass(self):
        output = StringIO()
        call_command("check", stdout=output)
        self.assertIn("System check identified no issues", output.getvalue())

    def test_root_url_configuration_loads_without_domain_routes(self):
        self.assertEqual(get_resolver().url_patterns, [])

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


class PostgreSQLConnectionSmokeTests(TestCase):
    def test_postgresql_connection_executes_select_one(self):
        self.assertEqual(connection.vendor, "postgresql")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone(), (1,))
