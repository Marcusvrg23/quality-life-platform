"""Square Cloud production: the HTTPS redirect can be turned off by environment."""

import os
import subprocess
import sys
from typing import ClassVar

from django.conf import settings
from django.test import SimpleTestCase

SSL_REDIRECT_VARIABLE = "DJANGO_SECURE_SSL_REDIRECT"


class SquareCloudSslRedirectTests(SimpleTestCase):
    """Run production settings in a child process; no database is touched."""

    environment: ClassVar[dict[str, str]] = {
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "square-cloud-test-key-not-used-outside-this-process",
        "DJANGO_DEBUG": "false",
        "DJANGO_ALLOWED_HOSTS": "quality-life-mvrg23.squareweb.app",
        "POSTGRES_DB": "quality_life_square_test",
        "POSTGRES_USER": "quality_life_square_test",
        "POSTGRES_PASSWORD": "square-cloud-test-password",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5432",
        "POSTGRES_SSLMODE": "require",
    }

    def status_over_http(self, extra_environment):
        child_environment = os.environ.copy()
        child_environment.pop(SSL_REDIRECT_VARIABLE, None)
        child_environment.update(self.environment)
        child_environment.update(extra_environment)
        # The manifest needs collectstatic (covered by ProductionStaticSmokeTests);
        # only the static storage is swapped, the SSL settings stay production.
        script = (
            "import django\n"
            "django.setup()\n"
            "from django.conf import settings\n"
            "from django.test import Client, override_settings\n"
            "storages = {**settings.STORAGES, 'staticfiles': {'BACKEND': (\n"
            "    'django.contrib.staticfiles.storage.StaticFilesStorage')}}\n"
            "with override_settings(STORAGES=storages):\n"
            "    response = Client().get(\n"
            "        '/privacidade/', HTTP_HOST='quality-life-mvrg23.squareweb.app'\n"
            "    )\n"
            "print('STATUS', response.status_code)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=settings.BASE_DIR,
            env=child_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_redirect_disabled_serves_common_route_over_http(self):
        stdout = self.status_over_http({SSL_REDIRECT_VARIABLE: "false"})

        self.assertIn("STATUS 200", stdout)

    def test_redirect_stays_on_by_default(self):
        stdout = self.status_over_http({})

        self.assertIn("STATUS 301", stdout)
