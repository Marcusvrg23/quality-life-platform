"""Versioned assessment configuration and immutable completed records."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class Pillar(models.Model):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    display_order = models.PositiveSmallIntegerField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order"]  # noqa: RUF012

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if any(
                getattr(old, field) != getattr(self, field)
                for field in ("code", "name", "display_order", "is_active")
            ):
                raise ValidationError("Approved pillar is immutable.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class QuestionnaireVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        RETIRED = "RETIRED", "Retired"

    code = models.SlugField(max_length=64)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    scoring_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["code", "version"],
                name="assessment_questionnaire_code_version_unique",
            ),
            models.CheckConstraint(
                condition=Q(version__gt=0),
                name="assessment_questionnaire_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["DRAFT", "PUBLISHED", "RETIRED"]),
                name="assessment_questionnaire_valid_status",
            ),
        ]

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.select_for_update().get(pk=self.pk)
            if old.status != self.Status.DRAFT:
                if (
                    old.status != self.Status.PUBLISHED
                    or self.status != self.Status.RETIRED
                ):
                    raise ValidationError("Published questionnaire is immutable.")
                for field in ("code", "version", "title", "scoring_version"):
                    if getattr(old, field) != getattr(self, field):
                        raise ValidationError("Published questionnaire is immutable.")
            elif self.status == self.Status.PUBLISHED:
                from .services import validate_questionnaire

                validate_questionnaire(self)
        elif self.status != self.Status.DRAFT:
            raise ValidationError("New questionnaire must be a draft.")
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        old = type(self).objects.select_for_update().get(pk=self.pk)
        if old.status != self.Status.DRAFT:
            raise ValidationError("Published questionnaire cannot be deleted.")
        return super().delete(*args, **kwargs)


class PublishedConfigurationGuard(models.Model):
    """Block ordinary model edits to configuration used by published assessments."""

    class Meta:
        abstract = True

    @property
    def questionnaire_version(self):
        raise NotImplementedError

    def _lock_draft_versions(self):
        version_ids = {self.questionnaire_version.pk}
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            version_ids.add(old.questionnaire_version.pk)
        versions = QuestionnaireVersion.objects.select_for_update().filter(
            pk__in=sorted(version_ids)
        )
        if versions.count() != len(version_ids) or any(
            version.status != QuestionnaireVersion.Status.DRAFT for version in versions
        ):
            raise ValidationError("Published questionnaire configuration is immutable.")

    @transaction.atomic
    def save(self, *args, **kwargs):
        self._lock_draft_versions()
        self.full_clean()
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        self._lock_draft_versions()
        return super().delete(*args, **kwargs)


class QuestionnairePillar(PublishedConfigurationGuard):
    questionnaire = models.ForeignKey(
        QuestionnaireVersion, on_delete=models.PROTECT, related_name="pillars"
    )
    pillar = models.ForeignKey(Pillar, on_delete=models.PROTECT)
    display_order = models.PositiveSmallIntegerField()
    weight = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)

    @property
    def questionnaire_version(self):
        return self.questionnaire

    class Meta:
        ordering = ["display_order"]  # noqa: RUF012
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["questionnaire", "pillar"],
                name="assessment_version_pillar_unique",
            ),
            models.UniqueConstraint(
                fields=["questionnaire", "display_order"],
                name="assessment_version_pillar_order_unique",
            ),
            models.CheckConstraint(
                condition=Q(weight__gt=0), name="assessment_pillar_weight_positive"
            ),
        ]


class Question(PublishedConfigurationGuard):
    class Direction(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        REVERSE = "REVERSE", "Reverse"

    questionnaire_pillar = models.ForeignKey(
        QuestionnairePillar, on_delete=models.CASCADE, related_name="questions"
    )
    code = models.SlugField(max_length=64)
    text = models.TextField()
    required = models.BooleanField(default=True)
    scorable = models.BooleanField(default=True)
    score_direction = models.CharField(
        max_length=7, choices=Direction.choices, default=Direction.NORMAL
    )
    weight = models.DecimalField(max_digits=8, decimal_places=2)
    display_order = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)

    @property
    def questionnaire_version(self):
        return self.questionnaire_pillar.questionnaire

    class Meta:
        ordering = ["display_order"]  # noqa: RUF012
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["questionnaire_pillar", "code"],
                name="assessment_question_pillar_code_unique",
            ),
            models.UniqueConstraint(
                fields=["questionnaire_pillar", "display_order"],
                name="assessment_question_pillar_order_unique",
            ),
            models.CheckConstraint(
                condition=Q(weight__gt=0), name="assessment_question_weight_positive"
            ),
            models.CheckConstraint(
                condition=Q(score_direction__in=["NORMAL", "REVERSE"]),
                name="assessment_question_valid_direction",
            ),
        ]


class QuestionOption(PublishedConfigurationGuard):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )
    code = models.SlugField(max_length=64)
    label = models.CharField(max_length=255)
    score_value = models.DecimalField(max_digits=5, decimal_places=2)
    display_order = models.PositiveSmallIntegerField()

    @property
    def questionnaire_version(self):
        return self.question.questionnaire_version

    class Meta:
        ordering = ["display_order"]  # noqa: RUF012
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["question", "code"],
                name="assessment_option_question_code_unique",
            ),
            models.UniqueConstraint(
                fields=["question", "display_order"],
                name="assessment_option_question_order_unique",
            ),
            models.CheckConstraint(
                condition=Q(score_value__gte=0, score_value__lte=100),
                name="assessment_option_score_range",
            ),
        ]


class Assessment(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT)
    questionnaire_version = models.ForeignKey(
        QuestionnaireVersion, on_delete=models.PROTECT
    )
    status = models.CharField(
        max_length=11, choices=Status.choices, default=Status.IN_PROGRESS
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=Q(status__in=["IN_PROGRESS", "COMPLETED"]),
                name="assessment_valid_status",
            ),
            models.CheckConstraint(
                condition=Q(status="IN_PROGRESS", completed_at__isnull=True)
                | Q(status="COMPLETED", completed_at__isnull=False),
                name="assessment_completion_timestamp_consistent",
            ),
        ]

    def save(self, *args, **kwargs):
        if (
            self.pk
            and type(self).objects.get(pk=self.pk).status == self.Status.COMPLETED
        ):
            raise ValidationError("Completed assessment is immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.COMPLETED:
            raise ValidationError("Completed assessment is immutable.")
        return super().delete(*args, **kwargs)


class Answer(models.Model):
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    selected_option = models.ForeignKey(QuestionOption, on_delete=models.PROTECT)
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["assessment", "question"],
                name="assessment_one_answer_per_question",
            ),
        ]

    def clean(self):
        if (
            self.assessment_id
            and self.question_id
            and self.question.questionnaire_version.pk
            != self.assessment.questionnaire_version_id
        ):
            raise ValidationError("Question belongs to another questionnaire version.")
        if (
            self.question_id
            and self.selected_option_id
            and self.selected_option.question_id != self.question_id
        ):
            raise ValidationError("Option belongs to another question.")

    def save(self, *args, **kwargs):
        if (
            self.pk
            and type(self).objects.get(pk=self.pk).assessment.status
            == Assessment.Status.COMPLETED
        ):
            raise ValidationError("Completed assessment answers are immutable.")
        if self.assessment.status != Assessment.Status.IN_PROGRESS:
            raise ValidationError("Completed assessment answers are immutable.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.assessment.status != Assessment.Status.IN_PROGRESS:
            raise ValidationError("Completed assessment answers are immutable.")
        return super().delete(*args, **kwargs)


class AssessmentResult(models.Model):
    assessment = models.OneToOneField(
        Assessment, on_delete=models.PROTECT, related_name="result"
    )
    overall_score = models.DecimalField(max_digits=5, decimal_places=2)
    overall_band = models.CharField(max_length=12)
    scoring_version = models.CharField(max_length=32)
    calculated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=Q(overall_score__gte=0, overall_score__lte=100),
                name="assessment_overall_score_range",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk or self.assessment.status == Assessment.Status.COMPLETED:
            raise ValidationError("Persisted result is immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Persisted result is immutable.")


class PillarResult(models.Model):
    assessment_result = models.ForeignKey(
        AssessmentResult, on_delete=models.PROTECT, related_name="pillars"
    )
    pillar = models.ForeignKey(Pillar, on_delete=models.PROTECT)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    band = models.CharField(max_length=12)

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["assessment_result", "pillar"],
                name="assessment_result_pillar_unique",
            ),
            models.CheckConstraint(
                condition=Q(score__gte=0, score__lte=100),
                name="assessment_pillar_score_range",
            ),
        ]

    def save(self, *args, **kwargs):
        if (
            self.pk
            or self.assessment_result.assessment.status == Assessment.Status.COMPLETED
        ):
            raise ValidationError("Persisted result is immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Persisted result is immutable.")
