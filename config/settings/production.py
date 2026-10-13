"""Production settings for the Railway deployment (see docs/DEPLOY_RAILWAY.md)."""

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
# Square Cloud does not document X-Forwarded-Proto; without it the redirect
# loops, so the host can turn it off while its proxy still serves HTTPS.
SECURE_SSL_REDIRECT = _boolean("DJANGO_SECURE_SSL_REDIRECT", default=True)
# Railway health checks hit the container over plain HTTP and need a 2xx.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
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

# With DEBUG=False Django sends nothing from django.request to the console, so
# 500s would be invisible in the Railway logs. Tracebacks go to stdout.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "plain",
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "ERROR"},
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
