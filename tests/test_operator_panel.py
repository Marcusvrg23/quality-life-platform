"""Quality Life operator panel (spec 12): companies, manager invites, no dead end."""

import hashlib
import re
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.invitations import INVITATION_TTL, hash_token, issue_invitations
from identity.models import (
    AllowedEmail,
    Invitation,
    Membership,
    Organization,
    User,
)

Role = Membership.Role
PASSWORD = "operator-test-password-63"
NO_ACCESS_TEXT = (
    "Sua conta ainda não está ligada a uma empresa. "
    "Peça um novo convite ao RH da sua empresa."
)
TOKEN_IN_LINK = re.compile(r"/convite/([A-Za-z0-9_-]{20,})/")


class OperatorTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Empresa A", slug="empresa-a")
        self.other_org = Organization.objects.create(name="Empresa B", slug="empresa-b")
        self.root = User.objects.create_superuser("ql@quality.test", PASSWORD)
        self.manager = self.member(self.org, "gestor@a.test", Role.CORPORATE_MANAGER)
        self.admin = self.member(self.org, "admin@a.test", Role.ADMIN)
        self.collaborator = self.member(self.org, "colab@a.test", Role.COLLABORATOR)
        self.other_manager = self.member(
            self.other_org, "gestor@b.test", Role.CORPORATE_MANAGER
        )
        self.other_collaborator = self.member(
            self.other_org, "colab@b.test", Role.COLLABORATOR
        )
        self.entry = AllowedEmail.objects.create(
            organization=self.org, email="liberado@a.test"
        )

    def member(self, organization, email, role):
        user = User.objects.create_user(email, PASSWORD)
        Membership.objects.create(user=user, organization=organization, role=role)
        return user

    def login(self, user, organization=None):
        self.client.force_login(user)
        if organization is not None:
            session = self.client.session
            session[SESSION_ORGANIZATION_KEY] = organization.pk
            session.save()

    def action_urls(self, organization=None):
        pk = (organization or self.org).pk
        return {
            "operator_organization_create": reverse("operator_organization_create"),
            "operator_organization_status": reverse(
                "operator_organization_status", args=[pk]
            ),
            "operator_manager_invitation": reverse(
                "operator_manager_invitation", args=[pk]
            ),
            "operator_enter": reverse("operator_enter", args=[pk]),
            "operator_email_add": reverse("operator_email_add", args=[pk]),
            "operator_email_remove": reverse(
                "operator_email_remove", args=[pk, self.entry.pk]
            ),
            "operator_email_role": reverse(
                "operator_email_role", args=[pk, self.entry.pk]
            ),
        }

    def manager_link(self, organization=None):
        response = self.client.post(
            reverse("operator_manager_invitation", args=[(organization or self.org).pk])
        )
        self.assertEqual(response.status_code, 200)
        match = TOKEN_IN_LINK.search(response.content.decode())
        self.assertIsNotNone(match)
        return match.group(1)


class AppHomeEntryTests(OperatorTestCase):
    def test_superuser_without_membership_is_sent_to_panel(self):
        self.login(self.root)
        response = self.client.get(reverse("app"))
        self.assertRedirects(response, reverse("operator_panel"))

    def test_superuser_still_has_no_implicit_tenant_access(self):
        self.login(self.root)
        response = self.client.get(reverse("organization_home", args=["empresa-a"]))
        self.assertEqual(response.status_code, 403)

    def test_superuser_with_membership_keeps_home_and_gets_panel_link(self):
        Membership.objects.create(
            user=self.root, organization=self.org, role=Role.ADMIN
        )
        self.login(self.root)
        response = self.client.get(reverse("app"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresa A")
        self.assertContains(response, "Painel da Quality Life")
        self.assertContains(response, f'href="{reverse("operator_panel")}"')

    def test_regular_user_has_no_panel_link(self):
        self.login(self.manager)
        response = self.client.get(reverse("app"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Painel da Quality Life")
        self.assertNotContains(response, reverse("operator_panel"))

    @override_settings(QL_SALES_EMAIL="vendas@quality.test")
    def test_regular_user_without_membership_sees_way_out_with_403(self):
        lost = User.objects.create_user("semvinculo@x.test", PASSWORD)
        self.login(lost)
        response = self.client.get(reverse("app"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, NO_ACCESS_TEXT, status_code=403)
        self.assertContains(
            response, 'href="mailto:vendas@quality.test"', status_code=403
        )
        self.assertContains(
            response, f'method="post" action="{reverse("logout")}"', status_code=403
        )
        self.assertContains(response, ">Sair<", status_code=403)
        self.assertContains(response, "csrfmiddlewaretoken", status_code=403)
        self.assertNotContains(response, "Painel da Quality Life", status_code=403)

    def test_login_next_still_goes_to_requested_page(self):
        response = self.client.post(
            f"{reverse('login')}?next=/app/aulas/",
            {"username": "colab@a.test", "password": PASSWORD},
        )
        self.assertRedirects(response, "/app/aulas/", fetch_redirect_response=False)

    def test_superuser_login_without_next_reaches_panel(self):
        response = self.client.post(
            reverse("login"),
            {"username": "ql@quality.test", "password": PASSWORD},
            follow=True,
        )
        self.assertEqual(
            [url for url, _ in response.redirect_chain],
            [reverse("app"), reverse("operator_panel")],
        )
        self.assertContains(response, "Painel da Quality Life")


class OperatorAccessTests(OperatorTestCase):
    def outsiders(self):
        staff = User.objects.create_user("staff@ql.test", PASSWORD, is_staff=True)
        lost = User.objects.create_user("semvinculo@x.test", PASSWORD)
        return (self.collaborator, self.manager, self.admin, staff, lost)

    def test_non_superusers_get_404_on_panel_and_every_action(self):
        organizations = Organization.objects.count()
        memberships = list(Membership.objects.values_list("pk", "role", "is_active"))
        for user in self.outsiders():
            self.login(user, self.org if user.memberships.exists() else None)
            with self.subTest(user=user.email):
                self.assertEqual(
                    self.client.get(reverse("operator_panel")).status_code, 404
                )
                self.assertEqual(
                    self.client.get(
                        reverse("operator_organization_emails", args=[self.org.pk])
                    ).status_code,
                    404,
                )
                for name, url in self.action_urls().items():
                    data = {
                        "name": "Invasora",
                        "ativo": "0",
                        "confirmar": "1",
                        "emails": "invasor@x.test",
                        "papel": "CORPORATE_MANAGER",
                    }
                    with self.subTest(action=name):
                        self.assertEqual(self.client.post(url, data).status_code, 404)
        self.assertEqual(Organization.objects.count(), organizations)
        self.assertTrue(Organization.objects.get(pk=self.org.pk).is_active)
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(
            list(AllowedEmail.objects.values_list("email", "role")),
            [("liberado@a.test", Role.COLLABORATOR)],
        )
        self.assertEqual(
            list(Membership.objects.values_list("pk", "role", "is_active")),
            memberships,
        )

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("operator_panel"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('operator_panel')}",
            fetch_redirect_response=False,
        )

    def test_actions_are_post_only(self):
        self.login(self.root)
        for name, url in self.action_urls().items():
            with self.subTest(action=name):
                self.assertEqual(self.client.get(url).status_code, 405)

    def test_actions_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.root)
        for name, url in self.action_urls().items():
            with self.subTest(action=name):
                response = client.post(
                    url,
                    {
                        "name": "X",
                        "ativo": "0",
                        "confirmar": "1",
                        "emails": "csrf@x.test",
                        "papel": "CORPORATE_MANAGER",
                    },
                )
                self.assertEqual(response.status_code, 403)
        self.assertFalse(Organization.objects.filter(name="X").exists())
        self.assertTrue(Organization.objects.get(pk=self.org.pk).is_active)
        self.assertEqual(AllowedEmail.objects.count(), 1)
        self.assertEqual(AllowedEmail.objects.get().role, Role.COLLABORATOR)


class OperatorPanelListTests(OperatorTestCase):
    def test_lists_companies_with_active_counts(self):
        self.member(self.org, "colab2@a.test", Role.COLLABORATOR)
        gone = self.member(self.org, "saiu@a.test", Role.COLLABORATOR)
        Membership.objects.filter(user=gone).update(is_active=False)
        self.member(self.org, "prof@a.test", Role.PROFESSIONAL)
        self.other_org.is_active = False
        self.other_org.save()
        self.login(self.root)
        response = self.client.get(reverse("operator_panel"))
        self.assertEqual(response.status_code, 200)
        rows = {company.pk: company for company in response.context["companies"]}
        self.assertEqual(rows[self.org.pk].collaborators, 2)
        self.assertEqual(rows[self.org.pk].managers, 1)
        self.assertEqual(rows[self.other_org.pk].collaborators, 1)
        self.assertEqual(rows[self.other_org.pk].managers, 1)
        self.assertContains(response, "Empresa A")
        self.assertContains(response, "Empresa B")
        self.assertContains(response, "Inativa")
        # Company counts only: no member e-mail reaches the panel.
        self.assertNotContains(response, "colab@a.test")
        self.assertNotContains(response, "gestor@b.test")


class OrganizationCreateTests(OperatorTestCase):
    def create(self, name):
        return self.client.post(reverse("operator_organization_create"), {"name": name})

    def test_creates_company_with_unique_slug_for_repeated_names(self):
        self.login(self.root)
        for _ in range(3):
            response = self.create("Padaria São João")
            newest = Organization.objects.latest("pk")
            self.assertRedirects(
                response, reverse("operator_organization_emails", args=[newest.pk])
            )
        self.assertEqual(
            sorted(
                Organization.objects.filter(name="Padaria São João").values_list(
                    "slug", flat=True
                )
            ),
            ["padaria-sao-joao", "padaria-sao-joao-2", "padaria-sao-joao-3"],
        )
        self.assertTrue(Organization.objects.get(slug="padaria-sao-joao").is_active)

    def test_slug_avoids_existing_company(self):
        self.login(self.root)
        self.create("Empresa A")
        self.assertTrue(
            Organization.objects.filter(name="Empresa A", slug="empresa-a-2").exists()
        )

    def test_name_without_letters_gets_fallback_slug(self):
        self.login(self.root)
        self.create("!!!")
        self.assertTrue(Organization.objects.filter(slug="empresa").exists())

    def test_blank_or_long_name_is_refused(self):
        self.login(self.root)
        count = Organization.objects.count()
        for name in ("", "   ", "x" * 256):
            with self.subTest(name=name[:5]):
                self.assertEqual(self.create(name).status_code, 400)
        self.assertEqual(Organization.objects.count(), count)


class OrganizationStatusTests(OperatorTestCase):
    def set_status(self, value, organization=None):
        return self.client.post(
            reverse(
                "operator_organization_status", args=[(organization or self.org).pk]
            ),
            {"ativo": value},
        )

    def test_deactivate_keeps_data_and_blocks_members(self):
        memberships = Membership.objects.filter(organization=self.org).count()
        self.login(self.root)
        self.assertRedirects(self.set_status("0"), reverse("operator_panel"))
        self.org.refresh_from_db()
        self.assertFalse(self.org.is_active)
        self.assertEqual(
            Membership.objects.filter(organization=self.org).count(), memberships
        )
        self.login(self.collaborator)
        self.assertEqual(self.client.get(reverse("app")).status_code, 403)

        self.login(self.root)
        self.set_status("1")
        self.org.refresh_from_db()
        self.assertTrue(self.org.is_active)
        self.login(self.collaborator)
        self.assertEqual(self.client.get(reverse("app")).status_code, 200)

    def test_invalid_value_is_refused(self):
        self.login(self.root)
        self.assertEqual(self.set_status("talvez").status_code, 400)
        self.org.refresh_from_db()
        self.assertTrue(self.org.is_active)

    def test_unknown_company_is_404(self):
        self.login(self.root)
        response = self.client.post(
            reverse("operator_organization_status", args=[999999]), {"ativo": "0"}
        )
        self.assertEqual(response.status_code, 404)


class ManagerInvitationTests(OperatorTestCase):
    def test_link_is_shown_once_and_only_its_hash_is_stored(self):
        self.login(self.root)
        before = timezone.now()
        token = self.manager_link()
        invitation = Invitation.objects.get()
        self.assertEqual(invitation.role, Role.CORPORATE_MANAGER)
        self.assertEqual(invitation.organization, self.org)
        self.assertEqual(invitation.created_by, self.root)
        self.assertEqual(
            invitation.token_hash, hashlib.sha256(token.encode()).hexdigest()
        )
        self.assertNotIn(token, str(Invitation.objects.values().get()))
        self.assertEqual(invitation.expires_at - invitation.created_at, INVITATION_TTL)
        self.assertGreaterEqual(invitation.created_at, before)
        self.assertNotIn(
            token, self.client.get(reverse("operator_panel")).content.decode()
        )

    def test_signup_creates_manager_membership_once(self):
        self.login(self.root)
        token = self.manager_link()
        self.client.logout()
        response = self.client.post(
            reverse("accept_invitation", args=[token]),
            {
                "email": "rh@a.test",
                "password1": "manager-new-password-91",
                "password2": "manager-new-password-91",
            },
        )
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        membership = Membership.objects.get(user__email="rh@a.test")
        self.assertEqual(membership.organization, self.org)
        self.assertEqual(membership.role, Role.CORPORATE_MANAGER)
        self.assertTrue(membership.is_active)
        invitation = Invitation.objects.get()
        self.assertIsNotNone(invitation.used_at)
        self.assertEqual(invitation.used_by, membership.user)
        # The new manager manages the team right away.
        self.assertEqual(self.client.get(reverse("team")).status_code, 200)

        self.client.logout()
        second = self.client.post(
            reverse("accept_invitation", args=[token]),
            {
                "email": "outro@a.test",
                "password1": "manager-new-password-91",
                "password2": "manager-new-password-91",
            },
        )
        self.assertEqual(second.status_code, 404)
        self.assertFalse(User.objects.filter(email="outro@a.test").exists())

    def test_logged_in_user_accepts_as_manager(self):
        newcomer = User.objects.create_user("novo@a.test", PASSWORD)
        self.login(self.root)
        token = self.manager_link()
        self.login(newcomer)
        page = self.client.get(reverse("accept_invitation", args=[token]))
        self.assertContains(page, "como gestor")
        self.client.post(reverse("accept_invitation", args=[token]))
        self.assertEqual(
            Membership.objects.get(user=newcomer).role, Role.CORPORATE_MANAGER
        )

    def test_expired_manager_link_is_unavailable(self):
        self.login(self.root)
        token = self.manager_link()
        Invitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.client.logout()
        response = self.client.get(reverse("accept_invitation", args=[token]))
        self.assertEqual(response.status_code, 404)

    def test_inactive_company_gets_no_manager_link(self):
        self.other_org.is_active = False
        self.other_org.save()
        self.login(self.root)
        response = self.client.post(
            reverse("operator_manager_invitation", args=[self.other_org.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Invitation.objects.exists())


class InvitationRoleRulesTests(OperatorTestCase):
    def test_service_refuses_manager_invite_from_non_superuser(self):
        for user in (self.manager, self.admin):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                issue_invitations(self.org, user, 1, role=Role.CORPORATE_MANAGER)
        self.assertFalse(Invitation.objects.exists())

    def test_service_refuses_other_roles_even_for_superuser(self):
        for role in (Role.ADMIN, Role.PROFESSIONAL):
            with self.subTest(role=role), self.assertRaises(ValueError):
                issue_invitations(self.org, self.root, 1, role=role)
        self.assertFalse(Invitation.objects.exists())

    def test_default_role_is_collaborator(self):
        (token,) = issue_invitations(self.org, self.manager, 1)
        self.assertEqual(
            Invitation.objects.get(token_hash=hash_token(token)).role,
            Role.COLLABORATOR,
        )

    def test_database_refuses_other_roles(self):
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Invitation.objects.create(
                organization=self.org,
                created_by=self.root,
                token_hash="0" * 64,
                created_at=now,
                expires_at=now + INVITATION_TTL,
                role=Role.ADMIN,
            )

    def test_team_page_only_generates_collaborator_invites(self):
        for user in (self.manager, self.admin):
            self.login(user, self.org)
            with self.subTest(user=user.email):
                response = self.client.post(
                    reverse("team_invitations_create"),
                    {"quantidade": 2, "role": Role.CORPORATE_MANAGER},
                )
                self.assertEqual(response.status_code, 200)
        self.assertEqual(Invitation.objects.count(), 4)
        self.assertEqual(
            set(Invitation.objects.values_list("role", flat=True)), {Role.COLLABORATOR}
        )

    def test_team_page_does_not_list_or_revoke_manager_invites(self):
        self.login(self.root)
        self.manager_link()
        manager_invite = Invitation.objects.get()
        self.login(self.manager, self.org)
        response = self.client.get(reverse("team"))
        self.assertNotContains(response, f"Convite nº {manager_invite.pk}")
        revoke = self.client.post(
            reverse("team_invitation_revoke", args=[manager_invite.pk])
        )
        self.assertEqual(revoke.status_code, 404)
        manager_invite.refresh_from_db()
        self.assertIsNone(manager_invite.revoked_at)


class EnterAsAdminTests(OperatorTestCase):
    def enter(self, organization=None, confirm=True):
        data = {"confirmar": "1"} if confirm else {}
        return self.client.post(
            reverse("operator_enter", args=[(organization or self.org).pk]), data
        )

    def test_requires_explicit_confirmation(self):
        self.login(self.root)
        self.assertEqual(self.enter(confirm=False).status_code, 400)
        self.assertFalse(Membership.objects.filter(user=self.root).exists())

    def test_creates_admin_membership_only_for_the_superuser(self):
        others = list(
            Membership.objects.order_by("pk").values_list(
                "pk", "user_id", "role", "is_active"
            )
        )
        self.login(self.root)
        response = self.enter()
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        membership = Membership.objects.get(user=self.root)
        self.assertEqual(membership.organization, self.org)
        self.assertEqual(membership.role, Role.ADMIN)
        self.assertTrue(membership.is_active)
        self.assertEqual(
            list(
                Membership.objects.exclude(user=self.root)
                .order_by("pk")
                .values_list("pk", "user_id", "role", "is_active")
            ),
            others,
        )
        self.assertEqual(self.client.session[SESSION_ORGANIZATION_KEY], self.org.pk)
        home = self.client.get(reverse("app"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Empresa A")

    def test_reactivates_existing_membership_as_admin(self):
        Membership.objects.create(
            user=self.root,
            organization=self.org,
            role=Role.COLLABORATOR,
            is_active=False,
        )
        self.login(self.root)
        self.enter()
        membership = Membership.objects.get(user=self.root)
        self.assertEqual(membership.role, Role.ADMIN)
        self.assertTrue(membership.is_active)

    def test_switches_between_companies(self):
        self.login(self.root)
        self.enter(self.org)
        self.enter(self.other_org)
        self.assertEqual(Membership.objects.filter(user=self.root).count(), 2)
        self.assertContains(self.client.get(reverse("app")), "Empresa B")

    def test_inactive_company_cannot_be_entered(self):
        self.other_org.is_active = False
        self.other_org.save()
        self.login(self.root)
        self.assertEqual(self.enter(self.other_org).status_code, 404)
        self.assertFalse(Membership.objects.filter(user=self.root).exists())


class ManagerIsolationTests(OperatorTestCase):
    def test_invited_manager_of_a_sees_nothing_of_b(self):
        Invitation.objects.all().delete()
        (b_invite,) = issue_invitations(self.other_org, self.other_manager, 1)
        b_invitation = Invitation.objects.get(token_hash=hash_token(b_invite))
        self.login(self.root)
        token = self.manager_link(self.org)
        newcomer = User.objects.create_user("rh@a.test", PASSWORD)
        self.login(newcomer)
        self.client.post(reverse("accept_invitation", args=[token]))
        self.assertEqual(
            list(
                Membership.objects.filter(user=newcomer).values_list(
                    "organization", "role"
                )
            ),
            [(self.org.pk, Role.CORPORATE_MANAGER)],
        )

        team = self.client.get(reverse("team"))
        self.assertContains(team, "colab@a.test")
        self.assertNotContains(team, "colab@b.test")
        self.assertNotContains(team, "gestor@b.test")
        self.assertNotContains(team, f"Convite nº {b_invitation.pk}")
        self.assertEqual(
            self.client.get(
                reverse("organization_home", args=[self.other_org.slug])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("select_organization"), {"organization": self.other_org.slug}
            ).status_code,
            403,
        )
        b_member = Membership.objects.get(user=self.other_collaborator)
        self.assertEqual(
            self.client.post(
                reverse("team_member_status", args=[b_member.pk]), {"ativo": "0"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("team_invitation_revoke", args=[b_invitation.pk])
            ).status_code,
            404,
        )
        b_member.refresh_from_db()
        b_invitation.refresh_from_db()
        self.assertTrue(b_member.is_active)
        self.assertIsNone(b_invitation.revoked_at)
        self.assertEqual(self.client.get(reverse("operator_panel")).status_code, 404)


class CompanyWizardTests(OperatorTestCase):
    def test_wizard_adds_lists_and_reports_ignored(self):
        self.login(self.root)
        response = self.client.post(
            reverse("operator_organization_create"),
            {
                "name": "Clínica Viva",
                "collaborators": (
                    "Ana@viva.test, bruno@viva.test;carla@viva.test\n"
                    "dado@viva.test \t ana@viva.test\nsem-arroba\nchefe@viva.test\n"
                ),
                "managers": "Chefe@viva.test\nchefe@viva.test, @quebrado",
            },
            follow=True,
        )
        organization = Organization.objects.get(name="Clínica Viva")
        self.assertRedirects(
            response, reverse("operator_organization_emails", args=[organization.pk])
        )
        rows = dict(
            AllowedEmail.objects.filter(organization=organization).values_list(
                "email", "role"
            )
        )
        self.assertEqual(
            rows,
            {
                "ana@viva.test": Role.COLLABORATOR,
                "bruno@viva.test": Role.COLLABORATOR,
                "carla@viva.test": Role.COLLABORATOR,
                "dado@viva.test": Role.COLLABORATOR,
                "chefe@viva.test": Role.CORPORATE_MANAGER,
            },
        )
        self.assertTrue(
            all(
                entry.added_by == self.root
                for entry in AllowedEmail.objects.filter(organization=organization)
            )
        )
        self.assertContains(
            response, "Clínica Viva criada com 4 colaboradores e 1 gestor."
        )
        self.assertContains(response, "5 e-mails liberados.")
        self.assertContains(
            response, "Ignorados por serem inválidos: sem-arroba, @quebrado."
        )
        self.assertContains(
            response, "Ignorados por estarem repetidos: ana@viva.test, chefe@viva.test."
        )
        self.assertContains(
            response,
            "Acesse http://testserver/ e clique em Continuar com o Google usando o "
            "e-mail que você passou ao RH.",
        )
        self.assertContains(response, 'data-copy="whatsapp-message"')
        self.assertContains(
            response, "https://wa.me/?text=Acesse%20http%3A%2F%2Ftestserver%2F"
        )
        self.assertContains(response, "Tornar gestor")
        self.assertContains(response, "Voltar a colaborador")
        self.assertNotContains(response, "Gerar convite de gestor")
        self.assertFalse(Invitation.objects.exists())

    def test_wizard_without_emails_still_creates_the_company(self):
        self.login(self.root)
        self.client.post(reverse("operator_organization_create"), {"name": "Só nome"})
        organization = Organization.objects.get(name="Só nome")
        self.assertFalse(organization.allowed_emails.exists())

    def test_panel_shows_allowed_count_and_link_not_emails(self):
        self.login(self.root)
        response = self.client.get(reverse("operator_panel"))
        self.assertContains(response, "E-mails liberados (1)")
        self.assertContains(
            response, reverse("operator_organization_emails", args=[self.org.pk])
        )
        self.assertNotContains(response, "liberado@a.test")
        self.assertNotContains(response, "Gerar convite de gestor")
        self.assertContains(response, ">Concluir<")
        self.assertContains(response, "Cole os e-mails dos colaboradores")
        self.assertContains(response, "E-mail(s) do chefe/gestor")
        rows = {company.pk: company for company in response.context["companies"]}
        self.assertEqual(rows[self.org.pk].collaborators, 1)
        self.assertEqual(rows[self.org.pk].managers, 1)
        self.assertEqual(rows[self.org.pk].allowed, 1)


class CompanyEmailsPageTests(OperatorTestCase):
    def emails_url(self, organization=None):
        return reverse(
            "operator_organization_emails", args=[(organization or self.org).pk]
        )

    def test_add_with_role_and_list(self):
        self.login(self.root)
        response = self.client.post(
            reverse("operator_email_add", args=[self.org.pk]),
            {"emails": "nova@a.test; liberado@a.test", "papel": Role.CORPORATE_MANAGER},
            follow=True,
        )
        self.assertRedirects(response, self.emails_url())
        self.assertEqual(
            AllowedEmail.objects.get(email="nova@a.test").role, Role.CORPORATE_MANAGER
        )
        self.assertContains(response, "1 e-mail liberado.")
        self.assertContains(
            response, "Ignorados por estarem repetidos: liberado@a.test."
        )
        self.assertContains(response, "Lista (2)")

    def test_invalid_role_or_empty_box_is_refused(self):
        self.login(self.root)
        count = AllowedEmail.objects.count()
        response = self.client.post(
            reverse("operator_email_add", args=[self.org.pk]),
            {"emails": "x@a.test", "papel": Role.ADMIN},
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            reverse("operator_email_add", args=[self.org.pk]), {"emails": "   "}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AllowedEmail.objects.count(), count)
        response = self.client.post(
            reverse("operator_email_role", args=[self.org.pk, self.entry.pk]),
            {"papel": Role.ADMIN},
        )
        self.assertEqual(response.status_code, 400)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.role, Role.COLLABORATOR)

    def test_role_toggle_changes_list_and_membership(self):
        person = self.member(self.org, "liberado@a.test", Role.COLLABORATOR)
        self.login(self.root)
        self.client.post(
            reverse("operator_email_role", args=[self.org.pk, self.entry.pk]),
            {"papel": Role.CORPORATE_MANAGER},
        )
        self.assertEqual(
            Membership.objects.get(user=person).role, Role.CORPORATE_MANAGER
        )
        self.client.post(
            reverse("operator_email_role", args=[self.org.pk, self.entry.pk]),
            {"papel": Role.COLLABORATOR},
        )
        self.assertEqual(Membership.objects.get(user=person).role, Role.COLLABORATOR)

    def test_remove_deactivates_membership_now(self):
        person = self.member(self.org, "liberado@a.test", Role.COLLABORATOR)
        self.login(self.root)
        response = self.client.post(
            reverse("operator_email_remove", args=[self.org.pk, self.entry.pk])
        )
        self.assertRedirects(response, self.emails_url())
        self.assertFalse(AllowedEmail.objects.filter(pk=self.entry.pk).exists())
        self.assertFalse(Membership.objects.get(user=person).is_active)

    def test_entry_of_another_company_is_404_even_for_the_operator(self):
        self.login(self.root)
        for name in ("operator_email_remove", "operator_email_role"):
            with self.subTest(action=name):
                response = self.client.post(
                    reverse(name, args=[self.other_org.pk, self.entry.pk]),
                    {"papel": Role.CORPORATE_MANAGER},
                )
                self.assertEqual(response.status_code, 404)
        self.assertTrue(AllowedEmail.objects.filter(pk=self.entry.pk).exists())
        self.assertEqual(
            self.client.get(self.emails_url(Organization(pk=10**6))).status_code, 404
        )

    def test_emails_page_lists_only_this_company(self):
        AllowedEmail.objects.create(organization=self.other_org, email="segredo@b.test")
        self.login(self.root)
        response = self.client.get(self.emails_url())
        self.assertContains(response, "liberado@a.test")
        self.assertNotContains(response, "segredo@b.test")
        self.assertContains(response, "Empresa A")
