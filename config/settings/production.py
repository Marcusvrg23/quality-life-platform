"""Production settings for the isolated Render deployment."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import _boolean, _integer

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required in production.")
if SECRET_KEY.startswith("replace-with-"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY still contains a placeholder.")
if str(DATABASES["default"]["PASSWORD"]).startswith("replace-with-"):
    raise ImproperlyConfigured("POSTGRES_PASSWORD still contains a placeholder.")

_postgres_sslmode = os.environ.get("POSTGRES_SSLMODE", "require").strip()
if _postgres_sslmode not in {"require", "verify-ca", "verify-full"}:
    raise ImproperlyConfigured(
        "Production POSTGRES_SSLMODE must be require, verify-ca, or verify-full."
    )
DATABASES["default"]["OPTIONS"]["sslmode"] = _postgres_sslmode

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = _integer("DJANGO_SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _boolean(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False
)
SECURE_HSTS_PRELOAD = _boolean("DJANGO_SECURE_HSTS_PRELOAD", default=False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
