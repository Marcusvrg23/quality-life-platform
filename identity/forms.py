"""Forms for the team page, the operator panel and invitation sign-up."""

from django import forms
from django.contrib.auth.password_validation import (
    password_validators_help_text_html,
    validate_password,
)
from django.core.exceptions import ValidationError

from .invitations import MAX_INVITATIONS_PER_BATCH
from .models import User


class InvitationQuantityForm(forms.Form):
    quantidade = forms.IntegerField(
        label="Quantidade de convites",
        min_value=1,
        max_value=MAX_INVITATIONS_PER_BATCH,
        initial=1,
    )


class OrganizationCreateForm(forms.Form):
    name = forms.CharField(label="Nome da empresa", max_length=255)


class InvitationSignupForm(forms.Form):
    email = forms.EmailField(
        label="E-mail", widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )
    password1 = forms.CharField(
        label="Senha",
        strip=False,
        help_text=password_validators_help_text_html(),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirme a senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self):
        return User.objects.normalize_email(self.cleaned_data["email"])

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "As senhas não conferem.")
        elif password2:
            try:
                validate_password(password2, User(email=cleaned.get("email", "")))
            except ValidationError as error:
                self.add_error("password2", error)
        return cleaned
