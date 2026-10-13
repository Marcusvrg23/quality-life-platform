"""Railway pre-deploy step: migrate, load the official questionnaire, superuser.

Runs without a shell, so every step lives here instead of a chained "&&".
Any failure propagates and the process exits with a non-zero code. The demo
seed is never called in production.

The official questionnaire is v2 (the text in docs/questionario/). Loading it
retires any other published version (v1); completed assessments and their
results stay untouched. A second run finds v2 loaded and changes nothing.
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

OFFICIAL_QUESTIONNAIRE = (
    settings.BASE_DIR
    / "assessments"
    / "questionnaires"
    / "quality_life_oficial_v2.json"
)


class Command(BaseCommand):
    help = "Production release: migrate, load_official_questionnaire, ensure_superuser."

    def handle(self, *args, **options):
        streams = {"stdout": self.stdout, "stderr": self.stderr}
        call_command("migrate", interactive=False, **streams)
        call_command(
            "load_official_questionnaire",
            file=str(OFFICIAL_QUESTIONNAIRE),
            retire_other_published=True,
            **streams,
        )
        call_command("ensure_superuser", **streams)
