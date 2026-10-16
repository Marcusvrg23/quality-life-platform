"""Forms for the team page, the operator panel and invitation sign-up."""

from django import forms
from django.contrib.auth.password_validation import (
    password_validators_help_text_html,
    validate_password,
)
from django.core.exceptions import ValidationError

from .invitations import MAX_INVITATIONS_PER_BATCH
from .models import ALLOWED_EMAIL_ROLES, User

EMAILS_LABEL = (
    "Cole os e-mails dos colaboradores (um por linha ou separados por "
    "vírgula/ponto e vírgula; dá para colar a coluna do Excel)"
)
ROLE_LABELS = {"COLLABORATOR": "Colaborador", "CORPORATE_MANAGER": "Gestor"}


def _emails_widget(rows):
    return forms.Textarea(
        attrs={"rows": rows, "autocomplete": "off", "spellcheck": "false"}
    )


class InvitationQuantityForm(forms.Form):
    quantidade = forms.IntegerField(
        label="Quantidade de convites",
        min_value=1,
        max_value=MAX_INVITATIONS_PER_BATCH,
        initial=1,
    )


class OrganizationCreateForm(forms.Form):
    """One-screen company wizard: name, collaborator e-mails, manager e-mails."""

    name = forms.CharField(label="Nome da empresa", max_length=255)
    collaborators = forms.CharField(
        label=EMAILS_LABEL, required=False, widget=_emails_widget(8)
    )
    managers = forms.CharField(
        label="E-mail(s) do chefe/gestor", required=False, widget=_emails_widget(2)
    )


class AllowedEmailsForm(forms.Form):
    """Pasted e-mails for the team page (always collaborators)."""

    emails = forms.CharField(label=EMAILS_LABEL, widget=_emails_widget(6))


class OperatorAllowedEmailsForm(AllowedEmailsForm):
    """Same box for the operator, who also picks the role."""

    papel = forms.ChoiceField(
        label="Papel",
        choices=[(role.value, ROLE_LABELS[role.value]) for role in ALLOWED_EMAIL_ROLES],
        initial="COLLABORATOR",
    )


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
