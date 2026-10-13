"""Invitation links, acceptance and support password reset without email."""

import hashlib
import os
import re
from datetime import timedelta
from pathlib import Path
from unittest import skipIf
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.admin import UserAdmin
from identity.invitations import hash_token, issue_invitations
from identity.models import Invitation, Membership, Organization, User
from identity.views import (
    EXISTING_ACCOUNT_MESSAGE,
    INACTIVE_MEMBERSHIP_MESSAGE,
    INVALID_INVITATION_MESSAGE,
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

Role = Membership.Role
PASSWORD = "invite-test-password-81"
NEW_PASSWORD = "brand-new-password-37"
TOKEN_IN_LINK = re.compile(r"/convite/([A-Za-z0-9_-]{20,})/")
FORGOT_PASSWORD = (
    "Esqueceu a senha? Fale com o RH da sua empresa ou com o suporte Quality Life."
)


class InvitationTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Empresa A", slug="empresa-a")
        self.other_org = Organization.objects.create(name="Empresa B", slug="empresa-b")
        self.manager = self.member(self.org, "gestor@a.test", Role.CORPORATE_MANAGER)
        self.collaborator = self.member(self.org, "colab@a.test", Role.COLLABORATOR)
        self.other_manager = self.member(
            self.other_org, "gestor@b.test", Role.CORPORATE_MANAGER
        )

    def member(self, organization, email, role):
        user = get_user_model().objects.create_user(email, PASSWORD)
        Membership.objects.create(user=user, organization=organization, role=role)
        return user

    def login(self, user, organization=None):
        self.client.force_login(user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = (organization or self.org).pk
        session.save()

    def invite(self, organization=None, created_by=None):
        (token,) = issue_invitations(
            organization or self.org, created_by or self.manager, 1
        )
        return token, Invitation.objects.get(token_hash=hash_token(token))

    def accept_url(self, token):
        return reverse("accept_invitation", args=[token])

    def signup(self, token, email="novo@a.test", password=NEW_PASSWORD, confirm=None):
        return self.client.post(
            self.accept_url(token),
            {"email": email, "password1": password, "password2": confirm or password},
        )


class InvitationGenerationTests(InvitationTestCase):
    def create(self, quantity):
        return self.client.post(
            reverse("team_invitations_create"), {"quantidade": quantity}
        )

    def test_quantity_bounds_are_enforced(self):
        self.login(self.manager)
        for quantity in ("0", "51", "-1", "abc", ""):
            with self.subTest(quantity=quantity):
                response = self.create(quantity)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(self.create("50").status_code, 200)
        self.assertEqual(Invitation.objects.count(), 50)

    def test_links_are_shown_once_with_copy_and_whatsapp(self):
        self.login(self.manager)
        response = self.create("3")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        tokens = list(dict.fromkeys(TOKEN_IN_LINK.findall(html)))
        self.assertEqual(len(tokens), 3)
        self.assertEqual(html.count("Copiar"), 3)
        for token in tokens:
            link = f"http://testserver{self.accept_url(token)}"
            self.assertIn(f'value="{link}"', html)
            self.assertIn("https://wa.me/?text=", html)
            self.assertIn(quote(link, safe=""), html)
        invitations = Invitation.objects.filter(organization=self.org)
        self.assertEqual(invitations.count(), 3)
        for invitation in invitations:
            self.assertEqual(invitation.created_by, self.manager)
            self.assertEqual(
                invitation.expires_at - invitation.created_at, timedelta(days=7)
            )
        self.assertIn("no-store", response.get("Cache-Control", ""))
        later = self.client.get(reverse("team")).content.decode()
        for token in tokens:
            self.assertNotIn(token, later)
        self.assertIn("Convites pendentes", later)
        self.assertEqual(later.count("Revogar"), 3)

    def test_plain_token_is_never_stored(self):
        self.login(self.manager)
        html = self.create("2").content.decode()
        tokens = set(TOKEN_IN_LINK.findall(html))
        self.assertEqual(len(tokens), 2)
        stored = [
            str(value)
            for row in Invitation.objects.values_list()
            for value in row
            if value is not None
        ]
        stored += [
            session.session_data + str(session.get_decoded())
            for session in Session.objects.all()
        ]
        for token in tokens:
            self.assertTrue(
                Invitation.objects.filter(
                    token_hash=hashlib.sha256(token.encode()).hexdigest()
                ).exists()
            )
            for value in stored:
                self.assertNotIn(token, value)

    def test_collaborator_cannot_create_or_revoke(self):
        _, invitation = self.invite()
        self.login(self.collaborator)
        self.assertEqual(self.create("1").status_code, 403)
        response = self.client.post(
            reverse("team_invitation_revoke", args=[invitation.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Invitation.objects.count(), 1)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.revoked_at)


class InvitationRevokeTests(InvitationTestCase):
    def revoke(self, invitation):
        return self.client.post(reverse("team_invitation_revoke", args=[invitation.pk]))

    def test_revoke_disables_the_link(self):
        token, invitation = self.invite()
        self.login(self.manager)
        self.assertRedirects(self.revoke(invitation), reverse("team"))
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.revoked_at)
        self.assertNotContains(self.client.get(reverse("team")), "Revogar")
        self.client.logout()
        self.assertEqual(self.client.get(self.accept_url(token)).status_code, 404)

    def test_other_company_invitation_returns_404(self):
        _, invitation = self.invite(self.other_org, self.other_manager)
        self.login(self.manager)
        self.assertEqual(self.revoke(invitation).status_code, 404)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.revoked_at)

    def test_used_invitation_cannot_be_revoked(self):
        token, invitation = self.invite()
        self.signup(token)
        self.client.logout()
        self.login(self.manager)
        self.assertEqual(self.revoke(invitation).status_code, 404)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.revoked_at)


class InvitationAcceptTests(InvitationTestCase):
    def assert_joined(self, user, invitation):
        membership = Membership.objects.get(user=user, organization=self.org)
        self.assertEqual(membership.role, Role.COLLABORATOR)
        self.assertTrue(membership.is_active)
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.used_at)
        self.assertEqual(invitation.used_by, user)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(self.client.session[SESSION_ORGANIZATION_KEY], self.org.pk)

    def test_new_user_creates_account_and_joins(self):
        token, invitation = self.invite()
        page = self.client.get(self.accept_url(token))
        self.assertContains(page, "Empresa A")
        self.assertContains(page, 'name="password2"')
        response = self.signup(token, email=" Novo@A.test ")
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        user = User.objects.get(email="novo@a.test")
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assert_joined(user, invitation)
        self.assertEqual(self.client.get(reverse("app")).status_code, 200)

    def test_new_user_password_is_validated(self):
        token, invitation = self.invite()
        cases = (
            {"password": "123"},
            {"password": NEW_PASSWORD, "confirm": NEW_PASSWORD + "x"},
            {"email": "nao-e-email"},
        )
        for case in cases:
            with self.subTest(case=case):
                response = self.signup(token, **case)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertFalse(User.objects.filter(email="novo@a.test").exists())
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)

    def test_existing_email_without_login_is_sent_to_login(self):
        token, invitation = self.invite()
        outsider = self.member(self.other_org, "pessoa@b.test", Role.COLLABORATOR)
        response = self.signup(token, email="PESSOA@b.test")
        self.assertContains(response, EXISTING_ACCOUNT_MESSAGE)
        login_link = f"{reverse('login')}?next={quote(self.accept_url(token))}"
        self.assertContains(response, f'href="{login_link}"')
        self.assertFalse(
            Membership.objects.filter(organization=self.org, user=outsider).exists()
        )
        outsider.refresh_from_db()
        self.assertTrue(outsider.check_password(PASSWORD))
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)

    def test_logged_in_existing_user_joins(self):
        token, invitation = self.invite()
        outsider = self.member(self.other_org, "pessoa@b.test", Role.COLLABORATOR)
        self.client.force_login(outsider)
        page = self.client.get(self.accept_url(token))
        self.assertContains(page, "Entrar na empresa Empresa A")
        self.assertNotContains(page, 'name="password1"')
        response = self.client.post(self.accept_url(token))
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        self.assert_joined(outsider, invitation)
        other = Membership.objects.get(user=outsider, organization=self.other_org)
        self.assertTrue(other.is_active)

    def test_login_then_accept_through_next(self):
        token, invitation = self.invite()
        outsider = self.member(self.other_org, "pessoa@b.test", Role.COLLABORATOR)
        response = self.client.post(
            reverse("login"),
            {
                "username": "pessoa@b.test",
                "password": PASSWORD,
                "next": self.accept_url(token),
            },
        )
        self.assertRedirects(
            response, self.accept_url(token), fetch_redirect_response=False
        )
        self.client.post(self.accept_url(token))
        self.assert_joined(outsider, invitation)

    def test_inactive_membership_is_not_reactivated(self):
        token, invitation = self.invite()
        Membership.objects.filter(user=self.collaborator).update(is_active=False)
        self.client.force_login(self.collaborator)
        response = self.client.post(self.accept_url(token))
        self.assertContains(response, INACTIVE_MEMBERSHIP_MESSAGE, status_code=403)
        membership = Membership.objects.get(user=self.collaborator)
        self.assertFalse(membership.is_active)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)

    def test_active_membership_only_redirects(self):
        token, invitation = self.invite()
        self.client.force_login(self.collaborator)
        response = self.client.post(self.accept_url(token))
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        membership = Membership.objects.get(user=self.collaborator)
        self.assertEqual(membership.role, Role.COLLABORATOR)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)

    def test_manager_accepting_keeps_role(self):
        token, invitation = self.invite()
        self.client.force_login(self.manager)
        self.client.post(self.accept_url(token))
        membership = Membership.objects.get(user=self.manager, organization=self.org)
        self.assertEqual(membership.role, Role.CORPORATE_MANAGER)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)

    def test_second_acceptance_fails(self):
        token, invitation = self.invite()
        self.signup(token, email="primeiro@a.test")
        self.client.logout()
        response = self.signup(token, email="segundo@a.test")
        self.assertContains(response, INVALID_INVITATION_MESSAGE, status_code=404)
        self.assertFalse(User.objects.filter(email="segundo@a.test").exists())
        self.client.force_login(self.other_manager)
        self.assertEqual(self.client.post(self.accept_url(token)).status_code, 404)
        self.assertFalse(
            Membership.objects.filter(
                user=self.other_manager, organization=self.org
            ).exists()
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.used_by.email, "primeiro@a.test")

    def test_unusable_invitations_share_one_generic_404(self):
        expired_token, expired = self.invite()
        Invitation.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        used_token, used = self.invite()
        Invitation.objects.filter(pk=used.pk).update(
            used_at=timezone.now(), used_by=self.collaborator
        )
        revoked_token, revoked = self.invite()
        Invitation.objects.filter(pk=revoked.pk).update(revoked_at=timezone.now())
        inactive_org_token, _ = self.invite(self.other_org, self.other_manager)
        Organization.objects.filter(pk=self.other_org.pk).update(is_active=False)
        bodies = set()
        for token in (
            expired_token,
            used_token,
            revoked_token,
            inactive_org_token,
            "nao-existe-" + "x" * 32,
        ):
            with self.subTest(token=token[:8]):
                for method in (self.client.get, self.client.post):
                    response = method(self.accept_url(token))
                    self.assertEqual(response.status_code, 404)
                    self.assertContains(
                        response, INVALID_INVITATION_MESSAGE, status_code=404
                    )
                    bodies.add(response.content)
        self.assertEqual(len(bodies), 1)
        self.assertFalse(Membership.objects.filter(user__email="novo@a.test").exists())


class PasswordChangeTests(InvitationTestCase):
    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_change_password_inside_app_shell(self):
        self.login(self.collaborator)
        page = self.client.get(reverse("password_change"))
        self.assertContains(page, 'id="app-navigation"')
        self.assertContains(page, 'name="old_password"')
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
            follow=True,
        )
        self.assertContains(response, "Senha alterada")
        self.collaborator.refresh_from_db()
        self.assertTrue(self.collaborator.check_password(NEW_PASSWORD))
        self.assertEqual(self.client.get(reverse("app")).status_code, 200)

    def test_wrong_old_password_is_rejected(self):
        self.login(self.collaborator)
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "errada",
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.collaborator.refresh_from_db()
        self.assertTrue(self.collaborator.check_password(PASSWORD))


class SupportPasswordResetTests(InvitationTestCase):
    action = "generate_password_reset_link"

    def setUp(self):
        super().setUp()
        self.superuser = get_user_model().objects.create_superuser(
            "suporte@ql.test", PASSWORD
        )
        self.changelist = reverse("admin:identity_user_changelist")

    def run_action(self, *users):
        return self.client.post(
            self.changelist,
            {"action": self.action, "_selected_action": [user.pk for user in users]},
            follow=True,
        )

    def messages(self, response):
        return [str(message) for message in response.context["messages"]]

    def test_link_resets_password(self):
        self.client.force_login(self.superuser)
        response = self.run_action(self.collaborator)
        (message,) = self.messages(response)
        match = re.search(
            r"http://testserver(/senha/redefinir/[^/\s]+/[^/\s]+/)", message
        )
        self.assertIsNotNone(match, message)
        visitor = Client()
        page = visitor.get(match.group(1), follow=True)
        self.assertContains(page, 'name="new_password1"')
        set_password_url = page.redirect_chain[-1][0]
        done = visitor.post(
            set_password_url,
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertRedirects(done, reverse("password_reset_complete"))
        self.assertContains(visitor.get(reverse("password_reset_complete")), "login")
        self.collaborator.refresh_from_db()
        self.assertTrue(self.collaborator.check_password(NEW_PASSWORD))
        reused = visitor.get(match.group(1), follow=True)
        self.assertNotContains(reused, 'name="new_password1"')
        self.assertContains(reused, "Link inválido")

    def test_requires_exactly_one_user(self):
        self.client.force_login(self.superuser)
        response = self.run_action(self.collaborator, self.manager)
        messages = self.messages(response)
        self.assertEqual(messages, ["Selecione exatamente 1 usuário."])

    def test_requires_superuser(self):
        staff = get_user_model().objects.create_user(
            "staff@ql.test", PASSWORD, is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.post(
            self.changelist,
            {"action": self.action, "_selected_action": [self.collaborator.pk]},
        )
        self.assertEqual(response.status_code, 403)
        request = RequestFactory().post(self.changelist)
        request.user = staff
        model_admin = UserAdmin(User, None)
        with self.assertRaises(PermissionDenied):
            model_admin.generate_password_reset_link(
                request, User.objects.filter(pk=self.collaborator.pk)
            )

    def test_invalid_reset_link_shows_message(self):
        response = self.client.get(
            reverse("password_reset_confirm", args=["MQ", "token-invalido"])
        )
        self.assertContains(response, "Link inválido")


class LoginHelpTests(TestCase):
    def test_login_page_explains_password_recovery(self):
        self.assertContains(self.client.get(reverse("login")), FORGOT_PASSWORD)


@skipIf(sync_playwright is None, "Install requirements-browser.txt for browser QA")
class TeamInvitationBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="QA Equipe", slug="qa-equipe")
        manager = get_user_model().objects.create_user("gestor-qa@a.test", PASSWORD)
        Membership.objects.create(
            user=manager, organization=self.org, role=Role.CORPORATE_MANAGER
        )
        for index in range(3):
            user = get_user_model().objects.create_user(
                f"colaborador-com-email-bem-comprido-{index}@empresa-exemplo.test",
                PASSWORD,
            )
            Membership.objects.create(
                user=user, organization=self.org, role=Role.COLLABORATOR
            )

    def _check(self, page, viewport, stage):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), f"Horizontal overflow at {viewport}: {stage}"
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir)
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(path / f"team-{viewport}-{stage}.png"), full_page=True
            )

    def _flow(self, browser, width, height, new_email):
        viewport = f"{width}x{height}"
        size = {"width": width, "height": height}
        manager_context = browser.new_context(viewport=size)
        manager_context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=self.live_server_url
        )
        page = manager_context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{self.live_server_url}/login/")
        page.locator("#id_username").fill("gestor-qa@a.test")
        page.locator("#id_password").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_url("**/app/")
        page.goto(f"{self.live_server_url}{reverse('team')}")
        self._check(page, viewport, "team")
        page.locator("#id_quantidade").fill("2")
        page.get_by_role("button", name="Gerar convites").click()
        page.get_by_role("heading", name="Links gerados").wait_for()
        self._check(page, viewport, "links")
        links = page.locator("[data-invite-link]")
        assert links.count() == 2
        link = links.first.input_value()
        page.get_by_role("button", name="Copiar").first.click()
        page.get_by_role("button", name="Copiado").first.wait_for()
        assert page.evaluate("navigator.clipboard.readText()") == link
        whatsapp = page.get_by_role("link", name="Enviar por WhatsApp").first
        assert whatsapp.get_attribute("href").startswith("https://wa.me/?text=")
        page.goto(f"{self.live_server_url}{reverse('password_change')}")
        self._check(page, viewport, "password")
        assert errors == [], errors
        manager_context.close()

        guest_context = browser.new_context(viewport=size)
        guest = guest_context.new_page()
        guest.goto(link)
        self._check(guest, viewport, "accept")
        guest.locator("#id_email").fill(new_email)
        guest.locator("#id_password1").fill(NEW_PASSWORD)
        guest.locator("#id_password2").fill(NEW_PASSWORD)
        guest.get_by_role("button", name="Criar acesso").click()
        guest.get_by_role("heading", name="Escolha sua atividade").wait_for()
        guest.goto(link)
        self._check(guest, viewport, "invalid")
        guest_context.close()

    def test_team_and_invitation_flow(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            self._flow(browser, 390, 844, "novo-390@a.test")
            self._flow(browser, 1366, 768, "novo-desktop@a.test")
            browser.close()
        self.assertEqual(
            Membership.objects.filter(
                organization=self.org, role=Role.COLLABORATOR, is_active=True
            ).count(),
            5,
        )
