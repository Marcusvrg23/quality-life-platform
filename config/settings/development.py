"""Local development settings."""

from pathlib import Path

import environ

_BASE_DIR = Path(__file__).resolve().parents[2]
environ.Env.read_env(_BASE_DIR / ".env", overwrite=False)

from .base import *

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
