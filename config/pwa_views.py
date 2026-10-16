"""Installable app files and the install screen (docs/specs/13-pwa-lembretes.md).

The service worker only ever caches the public offline page, the icon and
hashed static files: app HTML, authenticated responses and non-GET requests
carry health data and never reach the cache.
"""

import hashlib
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from .tenant import resolve_tenant_context

ICON_192 = "quality_life/images/brand/quality-life-logo-ring-192.png"
ICON_512 = "quality_life/images/brand/quality-life-logo-ring-512.png"
# --ql-purple and --ql-bg in static/quality_life/brand.css.
THEME_COLOR = "#84267d"
BACKGROUND_COLOR = "#fbf8f4"
# Bump to force every installed worker to drop its cache.
WORKER_REVISION = "1"


@require_GET
def manifest(request):
    return JsonResponse(
        {
            "id": "/app/",
            "name": "Quality Life",
            "short_name": "Quality Life",
            "description": "Ginástica laboral e bem-estar no trabalho.",
            "lang": "pt-BR",
            "start_url": "/app/",
            "scope": "/",
            "display": "standalone",
            "theme_color": THEME_COLOR,
            "background_color": BACKGROUND_COLOR,
            "icons": [
                {"src": static(ICON_192), "sizes": "192x192", "type": "image/png"},
                {"src": static(ICON_512), "sizes": "512x512", "type": "image/png"},
            ],
        },
        content_type="application/manifest+json",
        json_dumps_params={"ensure_ascii": False},
    )


@require_GET
@cache_control(no_cache=True)
def service_worker(request):
    precache = [reverse("offline"), static(ICON_192)]
    # A deploy that changes any static file (new manifest hash in production)
    # starts a new cache, so old hashed files do not pile up on the device.
    manifest_hash = getattr(staticfiles_storage, "manifest_hash", "")
    digest = hashlib.sha256(
        json.dumps([WORKER_REVISION, manifest_hash, *precache]).encode()
    ).hexdigest()
    return render(
        request,
        "pwa/sw.js",
        {
            "cache_name": f"ql-static-{digest[:12]}",
            "precache": json.dumps(precache),
            "static_url": settings.STATIC_URL,
        },
        content_type="text/javascript; charset=utf-8",
    )


@require_GET
def offline(request):
    return render(request, "pwa/offline.html", {"icon": static(ICON_192)})


@login_required
@require_GET
def install_app(request):
    # Install works without a company (operator panel); a forged one is 403.
    tenant = resolve_tenant_context(request)
    return render(request, "pwa/install.html", {"tenant": tenant})
