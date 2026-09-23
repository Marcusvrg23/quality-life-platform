from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

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
