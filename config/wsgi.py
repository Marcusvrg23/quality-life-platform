"""WSGI config for Quality Life V2.

Only the WSGI server (gunicorn) loads this module, so the reminder scheduler
started here never runs inside ``manage.py`` commands, migrations or tests.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()

from wellbeing.scheduler import (
    start_in_background,
)

start_in_background()
