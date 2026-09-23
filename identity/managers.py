from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """Store the entire address in lowercase for consistent email login."""
        return email.strip().lower() if email else ""

    def get_by_natural_key(self, username):
        return self.get(email__iexact=self.normalize_email(username))

    def create_user(self, email, password=None, **extra_fields):
        normalized_email = self.normalize_email(email)
        if not normalized_email:
            raise ValueError("An email address is required.")
        user = self.model(email=normalized_email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields["is_staff"] is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        if extra_fields["is_active"] is not True:
            raise ValueError("A superuser must have is_active=True.")
        return self.create_user(email, password, **extra_fields)
