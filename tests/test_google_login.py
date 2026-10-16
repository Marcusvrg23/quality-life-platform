"""'Continuar com o Google' (spec 14) with a simulated Google: no network.

The OAuth handshake is driven through the real allauth views; only the token
exchange is replaced by a fake response carrying an id_token we sign here.
"""

import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialToken
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.google import (
    ERROR_MESSAGE,
    INACTIVE_MESSAGE,
    NOT_ALLOWED_MESSAGE,
    UNVERIFIED_MESSAGE,
)
from identity.models import AllowedEmail, Membership, Organization, User

Role = Membership.Role
PASSWORD = "google-test-password-44"
CLIENT_ID = "test-client-id.apps.googleusercontent.com"
# Test-only configuration; the "secret" is a placeholder, not a credential.
GOOGLE_PROVIDERS = {
    "google": {
        "SCOPE": ["openid", "email", "profile"],
        "AUTH_PARAMS": {"prompt": "select_account"},
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [
            {"client_id": CLIENT_ID, "secret": "test-only-placeholder", "key": ""}
        ],
    }
}
TOKEN_EXCHANGE = (
    "allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token"
)


def id_token(email, sub, verified=True, **claims):
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": sub,
        "email": email,
        "email_verified": verified,
        "iat": now,
        "exp": now + 600,
        **claims,
    }
    return jwt.encode(
        payload, "test-only-signing-key-long-enough-for-hs256", algorithm="HS256"
    )


class GoogleTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Empresa A", slug="empresa-a")
        self.other_org = Organization.objects.create(name="Empresa B", slug="empresa-b")

    def allow(self, email, organization=None, role=Role.COLLABORATOR):
        return AllowedEmail.objects.create(
            organization=organization or self.org, email=email, role=role
        )

    def start(self, next_url=None, client=None):
        client = client or self.client
        data = {"process": "login"}
        if next_url:
            data["next"] = next_url
        response = client.post(reverse("google_login"), data)
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(
            location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        )
        return parse_qs(urlparse(location).query)

    def sign_in(self, email, sub="1001", verified=True, next_url=None, client=None):
        """Run the whole handshake; returns the callback response."""
        client = client or self.client
        query = self.start(next_url, client=client)
        token_response = {
            "access_token": "test-access-token",
            "expires_in": 3599,
            "id_token": id_token(email, sub, verified),
            "token_type": "Bearer",
        }
        with patch(TOKEN_EXCHANGE, return_value=token_response):
            return client.get(
                reverse("google_callback"),
                {"code": "test-code", "state": query["state"][0]},
            )

    def assert_nothing_created(self, email):
        self.assertFalse(User.objects.filter(email__iexact=email).exists())
        self.assertEqual(SocialAccount.objects.count(), 0)
        self.assertEqual(EmailAddress.objects.count(), 0)
        for session in Session.objects.all():
            self.assertNotIn(email, str(session.get_decoded()))


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class GoogleLoginPageTests(GoogleTestCase):
    def test_button_first_and_password_form_collapsed(self):
        response = self.client.get(reverse("login"))
        html = response.content.decode()
        self.assertContains(response, "Continuar com o Google")
        self.assertContains(response, f'action="{reverse("google_login")}"')
        self.assertContains(response, 'fill="#4285F4"')  # official "G" mark
        self.assertContains(response, "Ao continuar, você concorda com os")
        self.assertContains(response, f'href="{reverse("terms")}"')
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertContains(response, "<summary>Entrar com e-mail e senha</summary>")
        self.assertIn('<details class="login-password">', html)
        self.assertLess(html.index("Continuar com o Google"), html.index("id_username"))

    def test_failed_password_attempt_reopens_the_form(self):
        response = self.client.post(
            reverse("login"), {"username": "x@a.test", "password": "errada"}
        )
        self.assertContains(response, '<details class="login-password" open>')
        self.assertContains(response, "Email ou senha inválidos.")

    def test_redirect_to_google_asks_account_choice_and_minimal_scopes(self):
        query = self.start(next_url="/app/equipe/")
        self.assertEqual(query["prompt"], ["select_account"])
        self.assertEqual(set(query["scope"][0].split()), {"openid", "email", "profile"})
        self.assertEqual(query["client_id"], [CLIENT_ID])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(
            query["redirect_uri"], ["http://testserver/accounts/google/login/callback/"]
        )
        self.assertIn("code_challenge", query)

    def test_get_on_login_route_shows_dark_confirmation_not_allauth_page(self):
        response = self.client.get(reverse("google_login") + "?next=/app/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Continuar com o Google")
        self.assertContains(response, 'name="next" value="/app/"')
        self.assertContains(response, "login-form-wrap")
        self.assertNotContains(response, "Sign In Via")

    def test_no_public_signup_or_allauth_pages(self):
        for path in (
            "/signup/",
            "/accounts/",
            "/accounts/signup/",
            "/accounts/login/",
            "/accounts/password/reset/",
            "/accounts/3rdparty/signup/",
            "/accounts/3rdparty/login/cancelled/",
            "/accounts/google/login/token/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class GoogleSignInRulesTests(GoogleTestCase):
    def test_unverified_email_is_refused_and_nothing_is_created(self):
        self.allow("nova@a.test")
        response = self.sign_in("nova@a.test", verified=False)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, UNVERIFIED_MESSAGE, status_code=403)
        self.assert_nothing_created("nova@a.test")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unlisted_email_creates_no_account_and_is_not_stored(self):
        response = self.sign_in("ninguem@fora.test")
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            NOT_ALLOWED_MESSAGE.format(email="ninguem@fora.test"),
            status_code=403,
        )
        self.assertContains(response, "Continuar com o Google", status_code=403)
        self.assert_nothing_created("ninguem@fora.test")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_collaborator_and_manager_land_in_their_company_with_their_role(self):
        self.allow("colab@a.test")
        self.allow("gestora@a.test", role=Role.CORPORATE_MANAGER)
        for email, sub, role in (
            ("Colab@A.test", "sub-colab", Role.COLLABORATOR),
            ("gestora@a.test", "sub-gestora", Role.CORPORATE_MANAGER),
        ):
            with self.subTest(email=email):
                self.client.logout()
                response = self.sign_in(email, sub=sub)
                self.assertRedirects(
                    response, reverse("app"), fetch_redirect_response=False
                )
                user = User.objects.get(email=email.lower())
                self.assertFalse(user.has_usable_password())
                membership = Membership.objects.get(user=user)
                self.assertEqual(membership.organization, self.org)
                self.assertEqual(membership.role, role)
                self.assertTrue(membership.is_active)
                account = SocialAccount.objects.get(user=user)
                self.assertEqual((account.provider, account.uid), ("google", sub))
                self.assertEqual(SocialToken.objects.count(), 0)
                home = self.client.get(reverse("app"))
                self.assertEqual(home.status_code, 200)
                self.assertContains(home, "Empresa A")

    def test_two_companies_give_two_memberships_and_a_choice(self):
        self.allow("multi@a.test")
        self.allow(
            "multi@a.test", organization=self.other_org, role=Role.CORPORATE_MANAGER
        )
        self.sign_in("multi@a.test")
        user = User.objects.get(email="multi@a.test")
        self.assertEqual(
            Membership.objects.filter(user=user, is_active=True).count(), 2
        )
        response = self.client.get(reverse("app"))
        self.assertContains(response, "Selecione sua organização")
        self.assertContains(response, "Empresa A")
        self.assertContains(response, "Empresa B")

    def test_inactive_company_gives_no_access(self):
        self.other_org.is_active = False
        self.other_org.save()
        self.allow("so-b@a.test", organization=self.other_org)
        response = self.sign_in("so-b@a.test")
        self.assertEqual(response.status_code, 403)
        self.assert_nothing_created("so-b@a.test")
        # Listed in A (active) and B (inactive): only A opens.
        self.allow("a-e-b@a.test")
        self.allow("a-e-b@a.test", organization=self.other_org)
        self.client.logout()
        self.sign_in("a-e-b@a.test", sub="sub-ab")
        user = User.objects.get(email="a-e-b@a.test")
        self.assertEqual(
            list(
                Membership.objects.filter(user=user).values_list(
                    "organization_id", flat=True
                )
            ),
            [self.org.pk],
        )

    def test_existing_account_links_google_keeps_password_and_gets_memberships(self):
        user = User.objects.create_user("antiga@a.test", PASSWORD)
        self.allow("antiga@a.test", role=Role.CORPORATE_MANAGER)
        response = self.sign_in("ANTIGA@a.test", sub="sub-antiga")
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(User.objects.filter(email__iexact="antiga@a.test").count(), 1)
        account = SocialAccount.objects.get(user=user)
        self.assertEqual(account.uid, "sub-antiga")
        self.assertEqual(Membership.objects.get(user=user).role, Role.CORPORATE_MANAGER)

    def test_superuser_links_and_reaches_the_panel(self):
        root = User.objects.create_superuser("ql@quality.test", PASSWORD)
        response = self.sign_in("ql@quality.test", sub="sub-root")
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), root.pk)
        self.assertRedirects(self.client.get(reverse("app")), reverse("operator_panel"))
        root.refresh_from_db()
        self.assertTrue(root.is_superuser)
        self.assertTrue(root.check_password(PASSWORD))
        self.assertEqual(SocialAccount.objects.get(user=root).uid, "sub-root")

    def test_second_login_is_by_google_account_id_not_email(self):
        self.allow("colab@a.test")
        self.sign_in("colab@a.test", sub="sub-fixo")
        user = User.objects.get(email="colab@a.test")
        self.client.logout()
        # Same Google account, e-mail changed at Google: still the same user,
        # no second account.
        response = self.sign_in("outro-nome@a.test", sub="sub-fixo")
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(User.objects.count(), 1)

    def test_removed_from_list_loses_access_on_next_visit(self):
        entry = self.allow("sai@a.test")
        self.sign_in("sai@a.test")
        from identity.eligibility import remove_allowed_email

        remove_allowed_email(entry, None)
        response = self.client.get(reverse("app"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Sem acesso a uma empresa", status_code=403)

    def test_inactive_user_is_refused(self):
        user = User.objects.create_user("parada@a.test", PASSWORD, is_active=False)
        self.allow("parada@a.test")
        response = self.sign_in("parada@a.test")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, INACTIVE_MESSAGE, status_code=403)
        self.assertFalse(SocialAccount.objects.filter(user=user).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_next_is_honoured(self):
        self.allow("gestora@a.test", role=Role.CORPORATE_MANAGER)
        response = self.sign_in("gestora@a.test", next_url=reverse("team"))
        self.assertRedirects(response, reverse("team"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("team")).status_code, 200)

    def test_unsafe_next_is_dropped(self):
        self.allow("colab@a.test")
        response = self.sign_in("colab@a.test", next_url="https://evil.test/")
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)

    def test_cancel_or_error_returns_to_login_in_portuguese(self):
        query = self.start()
        for params in (
            {"error": "access_denied", "state": query["state"][0]},
            {"error": "server_error", "state": self.start()["state"][0]},
            {"code": "x", "state": "state-desconhecido"},
        ):
            with self.subTest(params=params):
                response = self.client.get(reverse("google_callback"), params)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, ERROR_MESSAGE)
                self.assertContains(response, "Continuar com o Google")
                self.assertNotContains(response, "Third-Party Login Failure")
        self.assertEqual(User.objects.count(), 0)

    def test_callback_without_handshake_logs_nobody_in(self):
        for method in (self.client.get, self.client.post):
            response = method(reverse("google_callback"), {"code": "x"})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, ERROR_MESSAGE)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(User.objects.count(), 0)

    def test_logged_in_user_signing_in_as_someone_else_is_switched(self):
        first = User.objects.create_user("um@a.test", PASSWORD)
        self.allow("um@a.test")
        self.allow("dois@a.test")
        self.client.force_login(first)
        self.sign_in("dois@a.test", sub="sub-dois")
        self.assertNotEqual(int(self.client.session["_auth_user_id"]), first.pk)


class GoogleDisabledTests(GoogleTestCase):
    """Default test settings carry no Google credentials."""

    def test_button_hidden_and_routes_404(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "Continuar com o Google")
        self.assertNotContains(response, reverse("google_login"))
        self.assertNotContains(response, "<details")
        self.assertContains(response, 'id="id_username"')
        for method in (self.client.get, self.client.post):
            self.assertEqual(method(reverse("google_login")).status_code, 404)
        self.assertEqual(self.client.get(reverse("google_callback")).status_code, 404)

    def test_password_login_works_and_applies_the_allowed_list(self):
        user = User.objects.create_user("senha@a.test", PASSWORD)
        self.allow("senha@a.test", role=Role.CORPORATE_MANAGER)
        self.allow("senha@a.test", organization=self.other_org)
        response = self.client.post(
            reverse("login"),
            {"username": "SENHA@a.test", "password": PASSWORD, "next": reverse("team")},
        )
        self.assertRedirects(response, reverse("team"), fetch_redirect_response=False)
        self.assertEqual(
            Membership.objects.filter(user=user, is_active=True).count(), 2
        )
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.org.pk
        session.save()
        self.assertEqual(self.client.get(reverse("team")).status_code, 200)

    def test_password_login_without_list_entry_changes_nothing(self):
        user = User.objects.create_user("semlista@a.test", PASSWORD)
        self.client.post(
            reverse("login"), {"username": user.email, "password": PASSWORD}
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertFalse(Membership.objects.filter(user=user).exists())
