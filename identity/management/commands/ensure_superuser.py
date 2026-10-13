"""Create the first superuser from the environment; never touch an existing one."""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

EMAIL_VARIABLE = "DJANGO_SUPERUSER_EMAIL"
PASSWORD_VARIABLE = "DJANGO_SUPERUSER_PASSWORD"


class Command(BaseCommand):
    help = (
        f"Create a superuser from {EMAIL_VARIABLE} and {PASSWORD_VARIABLE} "
        "if that e-mail does not exist yet. The password is never printed."
    )

    def handle(self, *args, **options):
        User = get_user_model()
        email = User.objects.normalize_email(os.environ.get(EMAIL_VARIABLE, ""))
        password = os.environ.get(PASSWORD_VARIABLE, "")
        if not email or not password.strip():
            self.stdout.write(
                self.style.WARNING(
                    f"{EMAIL_VARIABLE} ou {PASSWORD_VARIABLE} ausente; "
                    "nenhum superusuário criado."
                )
            )
            return
        with transaction.atomic():
            if User.objects.filter(email__iexact=email).exists():
                self.stdout.write(
                    self.style.WARNING(f"Usuário {email} já existe; nada foi alterado.")
                )
                return
            try:
                validate_password(password, user=User(email=email))
            except ValidationError as exc:
                raise CommandError(
                    f"Senha de {PASSWORD_VARIABLE} recusada: " + " ".join(exc.messages)
                ) from None
            User.objects.create_superuser(email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superusuário {email} criado."))
