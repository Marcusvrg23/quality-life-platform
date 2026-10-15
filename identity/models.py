from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=254, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # noqa: RUF012 - Django requires a mutable list here.

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.UniqueConstraint(
                Lower("email"), name="identity_user_email_ci_unique"
            ),
        ]

    def clean(self):
        super().clean()
        self.email = type(self).objects.normalize_email(self.email)

    def save(self, *args, **kwargs):
        self.email = type(self).objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class Organization(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class MembershipRole(models.TextChoices):
    COLLABORATOR = "COLLABORATOR", "Collaborator"
    CORPORATE_MANAGER = "CORPORATE_MANAGER", "Corporate manager"
    PROFESSIONAL = "PROFESSIONAL", "Professional"
    ADMIN = "ADMIN", "Admin"


class Membership(models.Model):
    Role = MembershipRole

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=MembershipRole.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="identity_membership_user_organization_unique",
            ),
            models.CheckConstraint(
                condition=Q(role__in=MembershipRole.values),
                name="identity_membership_valid_role",
            ),
        ]

    def __str__(self):
        return f"{self.user} in {self.organization} ({self.role})"


INVITATION_ROLES = (MembershipRole.COLLABORATOR, MembershipRole.CORPORATE_MANAGER)


class Invitation(models.Model):
    """Single-use invite; only the SHA-256 of the link token is kept.

    Managers invite collaborators; only a superuser invites a corporate manager
    (enforced in identity.invitations.issue_invitations).
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_invitations",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_invitations",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    role = models.CharField(
        max_length=20,
        choices=[(role.value, role.label) for role in INVITATION_ROLES],
        default=MembershipRole.COLLABORATOR,
    )

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.CheckConstraint(
                condition=Q(role__in=[role.value for role in INVITATION_ROLES]),
                name="identity_invitation_valid_role",
            ),
        ]

    def is_usable(self, now):
        return (
            self.used_at is None
            and self.revoked_at is None
            and self.expires_at > now
            and self.organization.is_active
        )

    def __str__(self):
        return f"Invitation {self.pk} to {self.organization}"


class ConsentRecordQuerySet(models.QuerySet):
    """Append-only ledger: bulk updates and deletes are refused."""

    def update(self, **kwargs):
        raise ValidationError("Consent records are append-only.")

    def delete(self):
        raise ValidationError("Consent records are append-only.")


class ConsentRecord(models.Model):
    """Per-company consent; the only allowed change is filling revoked_at once."""

    class Purpose(models.TextChoices):
        ASSESSMENT_HEALTH_DATA = (
            "ASSESSMENT_HEALTH_DATA",
            "Avaliação de qualidade de vida (dado de saúde)",
        )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consent_records",
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="consent_records"
    )
    purpose = models.CharField(max_length=40, choices=Purpose.choices)
    version = models.CharField(max_length=40)
    accepted_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = ConsentRecordQuerySet.as_manager()

    class Meta:
        constraints = [  # noqa: RUF012 - Django model metadata convention.
            models.UniqueConstraint(
                fields=["user", "organization", "purpose", "version"],
                condition=Q(revoked_at__isnull=True),
                name="identity_consent_one_active_per_version",
            ),
            models.CheckConstraint(
                condition=Q(purpose__in=["ASSESSMENT_HEALTH_DATA"]),
                name="identity_consent_valid_purpose",
            ),
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True)
                | Q(revoked_at__gte=models.F("accepted_at")),
                name="identity_consent_revoked_after_accepted",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            stored = type(self).objects.get(pk=self.pk)
            unchanged = all(
                getattr(stored, field) == getattr(self, field)
                for field in (
                    "user_id",
                    "organization_id",
                    "purpose",
                    "version",
                    "accepted_at",
                )
            )
            if not unchanged or stored.revoked_at is not None or not self.revoked_at:
                raise ValidationError("Only revoked_at can be filled, once.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Consent records are append-only.")

    def revoke(self, now=None):
        self.revoked_at = now or timezone.now()
        self.save(update_fields=["revoked_at"])

    def __str__(self):
        return f"Consent {self.purpose} v{self.version} of {self.user} in {self.organization}"
