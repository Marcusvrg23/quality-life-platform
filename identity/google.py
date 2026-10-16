"""Google sign-in through django-allauth, limited to the allowed e-mail list.

Only the two OAuth routes below are exposed (config/urls.py). Every refusal
renders the Quality Life login page with a notice; no allauth page, sign-up
form or English message is ever shown, and a refused e-mail is not stored.
"""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.google import views as google_views
from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from config.forms import EmailAuthenticationForm

from .eligibility import is_eligible, memberships_for_email, normalize_email
from .models import User

logger = logging.getLogger("quality_life.google")

NOT_ALLOWED_MESSAGE = (
    "Seu e-mail ainda não foi liberado. Peça ao RH da sua empresa para incluir {email}."
)
UNVERIFIED_MESSAGE = (
    "O Google não confirmou este e-mail. Use uma conta Google com e-mail verificado."
)
INACTIVE_MESSAGE = "Esta conta está desativada. Fale com o RH da sua empresa."
ERROR_MESSAGE = (
    "Não foi possível entrar com o Google. Tente de novo ou use e-mail e senha."
)


def enabled():
    """True when GOOGLE_CLIENT_ID/SECRET reached settings (see base.py)."""
    return bool(settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APPS"))


def login_page(request, message, status=200):
    """The regular login page with a Google notice; nothing is persisted."""
    return render(
        request,
        "identity/login.html",
        {
            "form": EmailAuthenticationForm(request),
            "next": "",
            "google_enabled": enabled(),
            "google_message": message,
        },
        status=status,
    )


def _refuse(request, message, status):
    raise ImmediateHttpResponse(login_page(request, message, status))


def _verified_email(sociallogin):
    """(normalized e-mail, verified) from the id_token claims; ('', False) if none."""
    for address in sociallogin.email_addresses:
        if address.email:
            return normalize_email(address.email), bool(address.verified)
    return "", False


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # There is no public sign-up form; accounts are born only through
        # SocialAccountAdapter below, after the allowed list says so.
        return False

    def add_message(self, *args, **kwargs):
        # allauth's own notices ("Successfully signed in as ...") never show.
        return None


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            # Linked before by the Google account id (SocialAccount.uid = sub).
            user = sociallogin.user
            if not user.is_active:
                _refuse(request, INACTIVE_MESSAGE, 403)
            memberships_for_email(user.email)
            return
        email, verified = _verified_email(sociallogin)
        if not email or not verified:
            _refuse(request, UNVERIFIED_MESSAGE, 403)
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            if not user.is_active:
                _refuse(request, INACTIVE_MESSAGE, 403)
            # Same verified e-mail: link the Google account and sign in. The
            # password, if any, stays valid.
            sociallogin.connect(request, user)
            memberships_for_email(user.email)
            logger.info("google_account_linked user=%s", user.pk)
            return
        if not is_eligible(email):
            _refuse(request, NOT_ALLOWED_MESSAGE.format(email=email), 403)

    def is_open_for_signup(self, request, sociallogin):
        email, verified = _verified_email(sociallogin)
        return bool(email) and verified and is_eligible(email)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        granted = memberships_for_email(user.email)
        logger.info(
            "google_account_created user=%s organizations=%s",
            user.pk,
            sorted(membership.organization_id for membership in granted),
        )
        return user

    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ):
        logger.warning(
            "google_authentication_error error=%s exception=%s",
            error,
            type(exception).__name__ if exception else None,
        )
        raise ImmediateHttpResponse(login_page(request, ERROR_MESSAGE))


def google_login(request):
    if not enabled():
        raise Http404("Google sign-in is not configured.")
    return google_views.oauth2_login(request)


def google_callback(request):
    if not enabled():
        raise Http404("Google sign-in is not configured.")
    return google_views.oauth2_callback(request)
