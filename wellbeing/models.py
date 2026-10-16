"""Practice records (docs/specs/11-bem-estar.md) and break reminders
(docs/specs/13-pwa-lembretes.md) for the wellbeing pages."""

from datetime import time

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from identity.models import Membership, Organization

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


REMINDER_INTERVALS = (60, 90, 120)
# ISO weekdays (1 = Monday), stored as ordered unique digits: "12345".
WEEKDAYS_PATTERN = r"^1?2?3?4?5?6?7?$"


class ReminderSetting(models.Model):
    """Break reminders of one person in one organization (spec 13).

    Read and written only by its owner through ``wellbeing.views.reminders``;
    no screen or endpoint lists the reminders of other people.
    """

    membership = models.OneToOneField(
        Membership, on_delete=models.CASCADE, related_name="reminder_setting"
    )
    active = models.BooleanField(default=False)
    interval_minutes = models.PositiveSmallIntegerField(
        choices=[(minutes, f"{minutes} min") for minutes in REMINDER_INTERVALS],
        default=60,
    )
    workday_start = models.TimeField(default=time(8, 0))
    workday_end = models.TimeField(default=time(18, 0))
    weekdays = models.CharField(max_length=7, default="12345")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.CheckConstraint(
                condition=Q(interval_minutes__in=REMINDER_INTERVALS),
                name="wellbeing_reminder_valid_interval",
            ),
            models.CheckConstraint(
                condition=Q(weekdays__regex=WEEKDAYS_PATTERN) & ~Q(weekdays=""),
                name="wellbeing_reminder_valid_weekdays",
            ),
            models.CheckConstraint(
                condition=Q(workday_start__lt=F("workday_end")),
                name="wellbeing_reminder_workday_order",
            ),
        ]

    def __str__(self):
        return f"lembrete {self.membership_id} ({self.interval_minutes} min)"
