"""Railway production readiness: health check, logging, release, static files."""

import os
import shutil
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import ClassVar
from unittest.mock import call, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from assessments.management.commands.seed_quality_life_demo import DEMO_CODE
from assessments.models import QuestionnaireVersion
from config.legal import CONSENT_VERSION
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import ConsentRecord, Membership, Organization

User = get_user_model()
OFFICIAL_FILE = (
    Path(settings.BASE_DIR)
    / "assessments"
    / "questionnaires"
    / "quality_life_oficial_v1.json"
)
STRONG_PASSWORD = "Railway-admin-passphrase-9137"


class ProductionSettingsProcessTests(SimpleTestCase):
    """Run production settings in a child process; no database is touched."""

    environment: ClassVar[dict[str, str]] = {
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "railway-test-key-not-used-outside-this-process",
        "DJANGO_DEBUG": "false",
        "DJANGO_ALLOWED_HOSTS": "app.example.test,healthcheck.railway.app",
        "POSTGRES_DB": "quality_life_railway_test",
        "POSTGRES_USER": "quality_life_railway_test",
        "POSTGRES_PASSWORD": "railway-test-password",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5432",
        "POSTGRES_SSLMODE": "require",
    }

    def run_production(self, code):
        child_environment = os.environ.copy()
        child_environment.update(self.environment)
        script = "import django\ndjango.setup()\n" + code
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=settings.BASE_DIR,
            env=child_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_health_answers_200_over_http_for_railway_healthcheck_host(self):
        result = self.run_production(
            "from django.test import Client\n"
            "response = Client().get('/health/', HTTP_HOST='healthcheck.railway.app')\n"
            "print('STATUS', response.status_code)\n"
        )

        self.assertIn("STATUS 200", result.stdout)

    def test_other_routes_still_redirect_http_to_https(self):
        result = self.run_production(
            "from django.test import Client\n"
            "response = Client().get('/privacidade/', HTTP_HOST='app.example.test')\n"
            "print('STATUS', response.status_code)\n"
            "print('LOCATION', response['Location'])\n"
        )

        self.assertIn("STATUS 301", result.stdout)
        self.assertIn("LOCATION https://app.example.test/privacidade/", result.stdout)

    def test_request_errors_are_logged_to_stdout_with_traceback(self):
        result = self.run_production(
            "import logging\n"
            "try:\n"
            "    raise RuntimeError('railway-logging-probe')\n"
            "except RuntimeError:\n"
            "    logging.getLogger('django.request').error(\n"
            "        'Internal Server Error: /probe/', exc_info=True\n"
            "    )\n"
        )

        self.assertIn("Internal Server Error: /probe/", result.stdout)
        self.assertIn("Traceback", result.stdout)
        self.assertIn("railway-logging-probe", result.stdout)

    def test_logging_config_targets_stdout_at_error_level(self):
        result = self.run_production(
            "from django.conf import settings\n"
            "config = settings.LOGGING\n"
            "print('STREAM', config['handlers']['console']['stream'])\n"
            "for name in ('django', 'django.request'):\n"
            "    print(name, config['loggers'][name]['level'],\n"
            "          config['loggers'][name]['handlers'])\n"
        )

        self.assertIn("STREAM ext://sys.stdout", result.stdout)
        self.assertIn("django ERROR ['console']", result.stdout)
        self.assertIn("django.request ERROR ['console']", result.stdout)


class EnsureSuperuserTests(TestCase):
    def run_command(self, environment):
        stdout, stderr = StringIO(), StringIO()
        with patch.dict(os.environ, environment, clear=False):
            for name in ("DJANGO_SUPERUSER_EMAIL", "DJANGO_SUPERUSER_PASSWORD"):
                if name not in environment:
                    os.environ.pop(name, None)
            call_command("ensure_superuser", stdout=stdout, stderr=stderr)
        return stdout.getvalue() + stderr.getvalue()

    def test_creates_superuser_without_printing_password(self):
        output = self.run_command(
            {
                "DJANGO_SUPERUSER_EMAIL": "Admin@Example.test",
                "DJANGO_SUPERUSER_PASSWORD": STRONG_PASSWORD,
            }
        )

        user = User.objects.get()
        self.assertEqual(user.email, "admin@example.test")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertNotIn(STRONG_PASSWORD, output)

    def test_is_idempotent(self):
        environment = {
            "DJANGO_SUPERUSER_EMAIL": "admin@example.test",
            "DJANGO_SUPERUSER_PASSWORD": STRONG_PASSWORD,
        }
        self.run_command(environment)
        output = self.run_command(environment)

        self.assertEqual(User.objects.count(), 1)
        self.assertIn("já existe", output)
        self.assertNotIn(STRONG_PASSWORD, output)

    def test_never_changes_existing_password_case_insensitively(self):
        existing = User.objects.create_user(
            email="admin@example.test", password="Original-passphrase-5521"
        )

        output = self.run_command(
            {
                "DJANGO_SUPERUSER_EMAIL": "ADMIN@example.test",
                "DJANGO_SUPERUSER_PASSWORD": STRONG_PASSWORD,
            }
        )

        existing.refresh_from_db()
        self.assertEqual(User.objects.count(), 1)
        self.assertTrue(existing.check_password("Original-passphrase-5521"))
        self.assertFalse(existing.is_superuser)
        self.assertIn("já existe", output)

    def test_skips_when_variables_are_missing(self):
        for environment in (
            {},
            {"DJANGO_SUPERUSER_EMAIL": "admin@example.test"},
            {"DJANGO_SUPERUSER_PASSWORD": STRONG_PASSWORD},
            {"DJANGO_SUPERUSER_EMAIL": " ", "DJANGO_SUPERUSER_PASSWORD": " "},
        ):
            with self.subTest(environment=sorted(environment)):
                output = self.run_command(environment)

                self.assertFalse(User.objects.exists())
                self.assertIn("DJANGO_SUPERUSER_EMAIL", output)
                self.assertNotIn(STRONG_PASSWORD, output)

    def test_rejects_weak_password_without_creating_or_echoing(self):
        with self.assertRaises(CommandError) as raised:
            self.run_command(
                {
                    "DJANGO_SUPERUSER_EMAIL": "admin@example.test",
                    "DJANGO_SUPERUSER_PASSWORD": "12345678",
                }
            )

        self.assertFalse(User.objects.exists())
        self.assertNotIn("12345678", str(raised.exception))


class ReleaseCommandTests(TestCase):
    superuser_environment: ClassVar[dict[str, str]] = {
        "DJANGO_SUPERUSER_EMAIL": "admin@example.test",
        "DJANGO_SUPERUSER_PASSWORD": STRONG_PASSWORD,
    }

    def release(self):
        stdout = StringIO()
        with patch.dict(os.environ, self.superuser_environment):
            call_command("release", stdout=stdout, stderr=StringIO())
        return stdout.getvalue()

    def test_calls_steps_in_order_and_never_the_demo_seed(self):
        with patch(
            "assessments.management.commands.release.call_command"
        ) as mocked_call:
            call_command("release", stdout=StringIO())

        names = [entry.args[0] for entry in mocked_call.call_args_list]
        self.assertEqual(
            names, ["migrate", "load_official_questionnaire", "ensure_superuser"]
        )
        self.assertNotIn("seed_quality_life_demo", names)
        self.assertEqual(
            mocked_call.call_args_list[1],
            call(
                "load_official_questionnaire",
                file=str(OFFICIAL_FILE),
                stdout=mocked_call.call_args_list[1].kwargs["stdout"],
                stderr=mocked_call.call_args_list[1].kwargs["stderr"],
            ),
        )
        self.assertFalse(mocked_call.call_args_list[0].kwargs["interactive"])

    def test_runs_twice_without_error(self):
        first = self.release()
        second = self.release()

        self.assertIn("publicado", first)
        self.assertIn("já carregado", second)
        self.assertEqual(
            QuestionnaireVersion.objects.filter(
                status=QuestionnaireVersion.Status.PUBLISHED
            ).count(),
            1,
        )
        self.assertFalse(QuestionnaireVersion.objects.filter(code=DEMO_CODE).exists())
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)

    def test_failure_propagates_as_command_error(self):
        # Another published questionnaire makes the official load refuse.
        with patch.dict(
            os.environ,
            {
                "QUALITY_LIFE_DEMO_SEED_ENABLED": "true",
                "QUALITY_LIFE_DEMO_PASSWORD": "Long-demo-passphrase-8274",
            },
        ):
            call_command("seed_quality_life_demo", stdout=StringIO())

        with self.assertRaisesMessage(CommandError, "--retire-other-published"):
            self.release()

        self.assertFalse(User.objects.filter(is_superuser=True).exists())


class ProductionStaticSmokeTests(TestCase):
    """collectstatic with the production manifest storage, then render key pages."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.static_root = tempfile.mkdtemp(prefix="ql-static-")
        cls.static_override = override_settings(
            DEBUG=False,
            STATIC_ROOT=cls.static_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": (
                        "whitenoise.storage.CompressedManifestStaticFilesStorage"
                    )
                },
            },
        )
        cls.static_override.enable()
        call_command("collectstatic", interactive=False, verbosity=0)

    @classmethod
    def tearDownClass(cls):
        cls.static_override.disable()
        shutil.rmtree(cls.static_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        call_command(
            "load_official_questionnaire", file=str(OFFICIAL_FILE), stdout=StringIO()
        )
        self.organization = Organization.objects.create(
            name="Empresa Smoke", slug="empresa-smoke"
        )
        self.collaborator = self.member(
            "colaborador@example.test", Membership.Role.COLLABORATOR
        )
        ConsentRecord.objects.create(
            user=self.collaborator,
            organization=self.organization,
            purpose=ConsentRecord.Purpose.ASSESSMENT_HEALTH_DATA,
            version=CONSENT_VERSION,
            accepted_at=timezone.now(),
        )
        self.manager = self.member(
            "gestor@example.test", Membership.Role.CORPORATE_MANAGER
        )

    def member(self, email, role):
        user = User.objects.create_user(email=email, password="test-password")
        Membership.objects.create(user=user, organization=self.organization, role=role)
        return user

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.organization.pk
        session.save()

    def assert_pages_ok(self, names):
        for name in names:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_manifest_contains_entries(self):
        self.assertTrue((Path(self.static_root) / "staticfiles.json").exists())

    def test_public_pages_render(self):
        self.assert_pages_ok(["login", "privacy", "terms"])

    def test_collaborator_pages_render(self):
        self.login(self.collaborator)
        self.assert_pages_ok(
            [
                "app",
                "exercises",
                "lessons",
                "assessment_hub",
                "privacy_settings",
                "password_change",
            ]
        )

    def test_manager_pages_render(self):
        self.login(self.manager)
        self.assert_pages_ok(["executive_report", "team"])
