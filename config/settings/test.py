"""Automated test settings; PostgreSQL remains mandatory."""

import os
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

_BASE_DIR = Path(__file__).resolve().parents[2]
environ.Env.read_env(_BASE_DIR / ".env", overwrite=False)

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1", "[::1]"]
_database_name = str(DATABASES["default"]["NAME"]).strip()
_test_database_name = os.environ.get(
    "POSTGRES_TEST_DB", f"test_{_database_name}"
).strip()

if not _test_database_name:
    raise ImproperlyConfigured("POSTGRES_TEST_DB must not be empty.")
if _test_database_name.casefold() == _database_name.casefold():
    raise ImproperlyConfigured("POSTGRES_TEST_DB must differ from POSTGRES_DB.")

DATABASES["default"]["TEST"] = {"NAME": _test_database_name}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
