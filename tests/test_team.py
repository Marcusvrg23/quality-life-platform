"""Team page: tenant-scoped member management for corporate managers."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assessments.models import Assessment, AssessmentResult, QuestionnaireVersion
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import AllowedEmail, Membership, Organization

Role = Membership.Role
PASSWORD = "team-test-password-81"


def main_content(response):
    html = response.content.decode()
    return html.split("<main", 1)[1].split("</main>", 1)[0]


class TeamTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Empresa A", slug="empresa-a")
        self.other_org = Organization.objects.create(name="Empresa B", slug="empresa-b")
        self.manager = self.member(self.org, "gestor@a.test", Role.CORPORATE_MANAGER)
        self.collaborator = self.member(self.org, "colab@a.test", Role.COLLABORATOR)
        self.outsider = self.member(self.other_org, "colab@b.test", Role.COLLABORATOR)

    def member(self, organization, email, role):
        user = get_user_model().objects.create_user(email, PASSWORD)
        Membership.objects.create(user=user, organization=organization, role=role)
        return user

    def membership(self, user, organization=None):
        return Membership.objects.get(user=user, organization=organization or self.org)

    def login(self, user, organization=None, client=None):
        client = client or self.client
        client.force_login(user)
        session = client.session
        session[SESSION_ORGANIZATION_KEY] = (organization or self.org).pk
        session.save()
        return client

    def set_status(self, membership, active):
        return self.client.post(
            reverse("team_member_status", args=[membership.pk]),
            {"ativo": "1" if active else "0"},
        )


class TeamAccessTests(TeamTestCase):
    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("team"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_collaborator_and_professional_get_403(self):
        professional = self.member(self.org, "pro@a.test", Role.PROFESSIONAL)
        for user in (self.collaborator, professional):
            with self.subTest(user=user.email):
                self.login(user)
                self.assertEqual(self.client.get(reverse("team")).status_code, 403)

    def test_manager_and_admin_get_200(self):
        admin = self.member(self.org, "admin@a.test", Role.ADMIN)
        for user in (self.manager, admin):
            with self.subTest(user=user.email):
                self.login(user)
                self.assertEqual(self.client.get(reverse("team")).status_code, 200)

    def test_manager_role_in_another_company_does_not_grant_access(self):
        # Manager in B, collaborator in A: the active tenant (A) decides.
        Membership.objects.create(
            user=self.collaborator,
            organization=self.other_org,
            role=Role.CORPORATE_MANAGER,
        )
        self.login(self.collaborator, self.org)
        self.assertEqual(self.client.get(reverse("team")).status_code, 403)


class TeamListTests(TeamTestCase):
    def test_lists_only_members_of_the_active_company(self):
        inactive = self.member(self.org, "saiu@a.test", Role.COLLABORATOR)
        Membership.objects.filter(user=inactive).update(is_active=False)
        self.login(self.manager)
        response = self.client.get(reverse("team"))
        content = main_content(response)
        for email in ("gestor@a.test", "colab@a.test", "saiu@a.test"):
            self.assertIn(email, content)
        self.assertNotIn("colab@b.test", response.content.decode())
        self.assertIn("Colaborador", content)
        self.assertIn("Gestor", content)
        self.assertIn("Inativo", content)
        self.assertIn(
            timezone.localtime(self.membership(self.collaborator).created_at).strftime(
                "%d/%m/%Y"
            ),
            content,
        )

    def test_html_has_no_assessment_data(self):
        version = QuestionnaireVersion.objects.create(
            code="team-test-only",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="team-test",
        )
        assessment = Assessment.objects.create(
            user=self.collaborator,
            organization=self.org,
            questionnaire_version=version,
        )
        AssessmentResult.objects.create(
            assessment=assessment,
            overall_score=Decimal("47.13"),
            overall_band="PRIORIDADE",
            scoring_version="team-test",
        )
        assessment.status = Assessment.Status.COMPLETED
        assessment.completed_at = timezone.now()
        assessment.save()
        self.login(self.manager)
        content = main_content(self.client.get(reverse("team"))).lower()
        for marker in (
            "47,13",
            "47.13",
            "prioridade",
            "avalia",
            "respond",
            "nota",
            "score",
            "pontua",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, content)


class MemberStatusTests(TeamTestCase):
    def test_deactivate_and_reactivate_collaborator(self):
        self.login(self.manager)
        membership = self.membership(self.collaborator)
        response = self.set_status(membership, active=False)
        self.assertRedirects(response, reverse("team"))
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)
        self.set_status(membership, active=True)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_own_membership_is_blocked(self):
        self.login(self.manager)
        membership = self.membership(self.manager)
        self.assertEqual(self.set_status(membership, active=False).status_code, 403)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_admin_and_manager_memberships_are_blocked(self):
        admin = self.member(self.org, "admin@a.test", Role.ADMIN)
        other_manager = self.member(self.org, "gestor2@a.test", Role.CORPORATE_MANAGER)
        self.login(self.manager)
        for user in (admin, other_manager):
            with self.subTest(user=user.email):
                membership = self.membership(user)
                response = self.set_status(membership, active=False)
                self.assertEqual(response.status_code, 403)
                membership.refresh_from_db()
                self.assertTrue(membership.is_active)

    def test_other_company_membership_returns_404(self):
        self.login(self.manager)
        membership = self.membership(self.outsider, self.other_org)
        self.assertEqual(self.set_status(membership, active=False).status_code, 404)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_collaborator_cannot_change_status(self):
        peer = self.member(self.org, "par@a.test", Role.COLLABORATOR)
        self.login(self.collaborator)
        membership = self.membership(peer)
        self.assertEqual(self.set_status(membership, active=False).status_code, 403)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_invalid_value_and_get_are_rejected(self):
        self.login(self.manager)
        membership = self.membership(self.collaborator)
        url = reverse("team_member_status", args=[membership.pk])
        self.assertEqual(self.client.post(url, {"ativo": "talvez"}).status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_status_change_requires_csrf(self):
        client = self.login(self.manager, client=Client(enforce_csrf_checks=True))
        membership = self.membership(self.collaborator)
        response = client.post(
            reverse("team_member_status", args=[membership.pk]), {"ativo": "0"}
        )
        self.assertEqual(response.status_code, 403)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_deactivated_member_loses_access(self):
        member_client = self.login(self.collaborator, client=Client())
        self.assertEqual(member_client.get(reverse("app")).status_code, 200)
        self.login(self.manager)
        self.set_status(self.membership(self.collaborator), active=False)
        self.assertEqual(member_client.get(reverse("app")).status_code, 403)
        self.assertEqual(member_client.get(reverse("exercises")).status_code, 403)


class TeamMenuTests(TeamTestCase):
    def test_team_link_shows_for_manager_only(self):
        team_href = f'href="{reverse("team")}"'
        self.login(self.manager)
        self.assertContains(self.client.get(reverse("app")), team_href)
        self.login(self.collaborator)
        self.assertNotContains(self.client.get(reverse("app")), team_href)

    def test_password_link_shows_for_everyone(self):
        for user in (self.manager, self.collaborator):
            with self.subTest(user=user.email):
                self.login(user)
                self.assertContains(
                    self.client.get(reverse("app")),
                    f'href="{reverse("password_change")}"',
                )


class TeamAllowedEmailsTests(TeamTestCase):
    def add(self, text, client=None):
        return (client or self.client).post(
            reverse("team_emails_add"), {"emails": text}
        )

    def test_manager_clears_collaborators_only_whatever_the_form_says(self):
        self.login(self.manager)
        response = self.client.post(
            reverse("team_emails_add"),
            {
                "emails": "nova@a.test, Outra@A.test\nnova@a.test\ninvalido",
                "papel": Role.CORPORATE_MANAGER,
                "role": Role.ADMIN,
            },
            follow=True,
        )
        self.assertRedirects(response, reverse("team"))
        self.assertEqual(
            dict(AllowedEmail.objects.values_list("email", "role")),
            {"nova@a.test": Role.COLLABORATOR, "outra@a.test": Role.COLLABORATOR},
        )
        self.assertEqual(
            AllowedEmail.objects.get(email="nova@a.test").added_by, self.manager
        )
        self.assertContains(response, "2 e-mails liberados.")
        self.assertContains(response, "Ignorados por serem inválidos: invalido.")
        self.assertContains(response, "Ignorados por estarem repetidos: nova@a.test.")
        self.assertContains(response, "E-mails liberados (2)")
        self.assertContains(response, "Continuar com o Google")

    def test_team_page_has_no_invitation_ui(self):
        self.login(self.manager)
        html = main_content(self.client.get(reverse("team")))
        for text in (
            "Convidar colaboradores",
            "Convites pendentes",
            "Gerar convites",
            "convites/",
        ):
            self.assertNotIn(text, html)
        self.assertIn("Liberar e-mails", html)
        self.assertIn("Membros (2)", html)

    def test_remove_collaborator_entry_deactivates_access(self):
        entry = AllowedEmail.objects.create(organization=self.org, email="colab@a.test")
        self.login(self.manager)
        response = self.client.post(reverse("team_email_remove", args=[entry.pk]))
        self.assertRedirects(response, reverse("team"))
        self.assertFalse(AllowedEmail.objects.filter(pk=entry.pk).exists())
        self.assertFalse(self.membership(self.collaborator).is_active)

    def test_manager_cannot_remove_a_manager_entry(self):
        entry = AllowedEmail.objects.create(
            organization=self.org, email="gestor2@a.test", role=Role.CORPORATE_MANAGER
        )
        self.login(self.manager)
        page = main_content(self.client.get(reverse("team")))
        self.assertIn("gestor2@a.test", page)
        self.assertNotIn(reverse("team_email_remove", args=[entry.pk]), page)
        response = self.client.post(reverse("team_email_remove", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(AllowedEmail.objects.filter(pk=entry.pk).exists())

    def test_other_company_entry_is_404_and_lists_are_isolated(self):
        b_entry = AllowedEmail.objects.create(
            organization=self.other_org, email="so-b@b.test"
        )
        self.login(self.manager)
        self.assertNotIn("so-b@b.test", main_content(self.client.get(reverse("team"))))
        response = self.client.post(reverse("team_email_remove", args=[b_entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(AllowedEmail.objects.filter(pk=b_entry.pk).exists())

    def test_collaborator_and_anonymous_cannot_use_the_actions(self):
        entry = AllowedEmail.objects.create(organization=self.org, email="x@a.test")
        self.assertEqual(self.add("y@a.test").status_code, 302)
        self.assertIn(reverse("login"), self.add("y@a.test")["Location"])
        self.login(self.collaborator)
        self.assertEqual(self.add("y@a.test").status_code, 403)
        self.assertEqual(
            self.client.post(reverse("team_email_remove", args=[entry.pk])).status_code,
            403,
        )
        self.assertEqual(AllowedEmail.objects.count(), 1)

    def test_actions_are_post_only_and_need_csrf(self):
        entry = AllowedEmail.objects.create(organization=self.org, email="x@a.test")
        self.login(self.manager)
        for url in (
            reverse("team_emails_add"),
            reverse("team_email_remove", args=[entry.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
        client = self.login(self.manager, client=Client(enforce_csrf_checks=True))
        self.assertEqual(self.add("z@a.test", client=client).status_code, 403)
        self.assertEqual(
            client.post(reverse("team_email_remove", args=[entry.pk])).status_code, 403
        )
        self.assertEqual(AllowedEmail.objects.count(), 1)

    def test_empty_box_is_refused_without_error_page(self):
        self.login(self.manager)
        response = self.add("   ")
        self.assertRedirects(response, reverse("team"))
        self.assertEqual(AllowedEmail.objects.count(), 0)
