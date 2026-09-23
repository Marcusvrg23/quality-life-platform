import os
import subprocess
import sys
from typing import ClassVar

from django.conf import settings
from django.test import SimpleTestCase


class EnvironmentConfigurationTests(SimpleTestCase):
    valid_environment: ClassVar[dict[str, str]] = {
        "DJANGO_SECRET_KEY": "configuration-test-key-not-used-outside-this-process",
        "DJANGO_DEBUG": "false",
        "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "POSTGRES_DB": "quality_life_test",
        "POSTGRES_USER": "quality_life_test",
        "POSTGRES_PASSWORD": "configuration-test-password",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5432",
    }

    def import_settings(self, module="base", *, overrides=None, missing=()):
        child_environment = os.environ.copy()
        child_environment.update(self.valid_environment)
        child_environment.update(overrides or {})
        for name in missing:
            child_environment.pop(name, None)
        return subprocess.run(
            [sys.executable, "-c", f"import config.settings.{module}"],
            cwd=settings.BASE_DIR,
            env=child_environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_secret_key_is_required(self):
        result = self.import_settings(missing=("DJANGO_SECRET_KEY",))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DJANGO_SECRET_KEY environment variable is required", result.stderr
        )

    def test_database_credentials_are_required(self):
        result = self.import_settings(missing=("POSTGRES_PASSWORD",))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "POSTGRES_PASSWORD environment variable is required", result.stderr
        )

    def test_debug_rejects_ambiguous_boolean_values(self):
        result = self.import_settings(overrides={"DJANGO_DEBUG": "maybe"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DJANGO_DEBUG environment variable must be a boolean", result.stderr
        )

    def test_allowed_hosts_rejects_wildcard(self):
        result = self.import_settings(overrides={"DJANGO_ALLOWED_HOSTS": "*"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS must not contain a wildcard", result.stderr)

    def test_test_database_must_differ_from_application_database(self):
        result = self.import_settings(
            "test", overrides={"POSTGRES_TEST_DB": "quality_life_test"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("POSTGRES_TEST_DB must differ from POSTGRES_DB", result.stderr)

    def test_test_database_name_must_not_be_empty(self):
        result = self.import_settings("test", overrides={"POSTGRES_TEST_DB": ""})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("POSTGRES_TEST_DB must not be empty", result.stderr)

    def test_production_requires_encrypted_database_transport(self):
        result = self.import_settings(
            "production", overrides={"POSTGRES_SSLMODE": "prefer"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production POSTGRES_SSLMODE must be", result.stderr)

    def test_production_rejects_example_secret_placeholder(self):
        result = self.import_settings(
            "production",
            overrides={
                "DJANGO_SECRET_KEY": "replace-with-a-long-random-local-development-key",
                "POSTGRES_SSLMODE": "require",
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY still contains a placeholder", result.stderr)

    def test_production_settings_accept_secure_configuration(self):
        result = self.import_settings(
            "production", overrides={"POSTGRES_SSLMODE": "require"}
        )

        self.assertEqual(result.returncode, 0, result.stderr)
