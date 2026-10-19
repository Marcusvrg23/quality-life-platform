"""Practice records (docs/specs/11-bem-estar.md), break reminders and the
push notification channel (docs/specs/13-pwa-lembretes.md)."""

from datetime import time

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

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


def shift_minutes(start, end):
    """Length of the shift in minutes; an end at or before the start is on the
    next day (night shift), so the result is between 1 and 1440."""
    span = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return span if span > 0 else span + 24 * 60


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
            # end <= start is a night shift ending on the next day.
            models.CheckConstraint(
                condition=~Q(workday_start=F("workday_end")),
                name="wellbeing_reminder_workday_distinct",
            ),
        ]

    @property
    def overnight(self):
        return self.workday_end <= self.workday_start

    def __str__(self):
        return f"lembrete {self.membership_id} ({self.interval_minutes} min)"


class PushSubscription(models.Model):
    """One device of one person in one organization, subscribed to Web Push.

    Created and removed only by its owner (``wellbeing.views.push_subscribe``
    and ``push_unsubscribe``); the endpoint identifies the device, so a device
    that signs in as someone else moves to the new Membership. It holds the
    push service address and the browser's encryption keys, never health data.
    """

    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.CharField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"aparelho {self.pk} da membership {self.membership_id}"


class NotificationCategory(models.TextChoices):
    BREAKS = "pausas", "Lembretes de pausa"
    TIPS = "dicas", "Dicas e datas especiais"


class NotificationPreference(models.Model):
    """Which categories a person accepts; only the owner changes it.

    Both are on by default, so activating the notifications is enough.
    """

    membership = models.OneToOneField(
        Membership, on_delete=models.CASCADE, related_name="notification_preference"
    )
    pausas = models.BooleanField(default=True)
    dicas = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def allows(self, category):
        return bool(getattr(self, category))

    def __str__(self):
        return f"preferências da membership {self.membership_id}"


class NotificationDelivery(models.Model):
    """One ``notify()`` call that reached at least one device.

    Only ids, category, time and device count are kept, never the text: it
    exists for the per-category daily limits.
    """

    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="notification_deliveries"
    )
    category = models.CharField(max_length=10, choices=NotificationCategory.choices)
    devices = models.PositiveSmallIntegerField()
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [  # noqa: RUF012 - Django model metadata convention.
            models.Index(
                fields=["membership", "category", "sent_at"],
                name="wellbeing_delivery_member_sent",
            ),
        ]
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.CheckConstraint(
                condition=Q(category__in=NotificationCategory.values),
                name="wellbeing_delivery_valid_category",
            ),
        ]

    def __str__(self):
        return f"{self.category} para membership {self.membership_id}"


class ReminderDispatch(models.Model):
    """One reminder slot handed to the notification channel by the scheduler.

    Unique per (setting, slot), so two gunicorn workers that wake up in the
    same minute never send the same reminder twice: the second insert fails
    and that worker skips the slot.
    """

    setting = models.ForeignKey(
        ReminderSetting, on_delete=models.CASCADE, related_name="dispatches"
    )
    slot_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.UniqueConstraint(
                fields=["setting", "slot_at"],
                name="wellbeing_dispatch_setting_slot_unique",
            ),
        ]

    def __str__(self):
        return f"lembrete {self.setting_id} às {self.slot_at:%Y-%m-%d %H:%M}"


class TipDispatch(models.Model):
    """One day's tip handed to a person by the scheduler (spec 17).

    Unique per (membership, day), so two gunicorn workers that wake up at the
    same send time never deliver the same tip twice. Only ids and the date are
    kept, never the text.
    """

    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="tip_dispatches"
    )
    day = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.UniqueConstraint(
                fields=["membership", "day"],
                name="wellbeing_tip_dispatch_once_a_day",
            ),
        ]

    def __str__(self):
        return f"dica de {self.day:%Y-%m-%d} para membership {self.membership_id}"


class AssistantUsage(models.Model):
    """How many messages a person sent to the assistant on a local day (spec 18).

    Only the count is kept, never the text: the conversation lives in the
    person's browser tab and is gone when the page closes.
    """

    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="assistant_usage"
    )
    day = models.DateField()
    messages = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.UniqueConstraint(
                fields=["membership", "day"],
                name="wellbeing_assistant_usage_once_a_day",
            ),
        ]

    def __str__(self):
        return f"{self.messages} mensagens em {self.day:%Y-%m-%d} (membership {self.membership_id})"
