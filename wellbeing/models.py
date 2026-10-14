"""Practice records for the wellbeing pages (docs/specs/11-bem-estar.md)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from identity.models import Organization

MIN_RECORD_SECONDS = 60
MAX_RECORD_SECONDS = 60 * 60


class ActivitySession(models.Model):
    """One practice of one person in one organization.

    Written only by its owner through ``wellbeing.views.record``; the company
    sees it only inside aggregates (``wellbeing.services.company_usage``).
    """

    class Kind(models.TextChoices):
        GYM = "ginastica", "Ginástica laboral"
        MEDITATION = "meditacao", "Meditação"
        RELAXATION = "relaxamento", "Relaxamento"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_sessions",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="activity_sessions",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    slug = models.SlugField(max_length=80)
    started_at = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [  # noqa: RUF012 - Django model metadata convention.
            models.Index(
                fields=["organization", "started_at"],
                name="wellbeing_session_org_start",
            ),
            models.Index(
                fields=["user", "organization", "started_at"],
                name="wellbeing_session_user_start",
            ),
        ]
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.CheckConstraint(
                condition=Q(kind__in=["ginastica", "meditacao", "relaxamento"]),
                name="wellbeing_session_valid_kind",
            ),
            models.CheckConstraint(
                condition=Q(duration_seconds__gte=MIN_RECORD_SECONDS)
                & Q(duration_seconds__lte=MAX_RECORD_SECONDS),
                name="wellbeing_session_duration_range",
            ),
        ]

    def __str__(self):
        return f"{self.kind}/{self.slug} ({self.duration_seconds}s)"
