"""Public legal drafts, their links, and role-aware navigation without 403 links."""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization

DRAFT = "MINUTA — pendente de revisão jurídica"  # off the screen since spec 15


class PublicLegalPagesTests(TestCase):
    def test_pages_answer_without_login_and_hide_draft_banner(self):
        for name in ("privacy", "terms"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, DRAFT)
                self.assertContains(response, "[RAZÃO SOCIAL]")
                self.assertContains(response, "[CNPJ]")
                self.assertContains(response, "[E-MAIL DO ENCARREGADO]")
                self.assertEqual(self.client.post(reverse(name)).status_code, 405)

    @override_settings(
        LEGAL_COMPANY_NAME="Quality Life Teste Ltda",
        LEGAL_CNPJ="00.000.000/0000-00",
        LEGAL_DPO_EMAIL="dpo@example.test",
    )
    def test_company_data_comes_from_settings(self):
        for name in ("privacy", "terms"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, "Quality Life Teste Ltda")
                self.assertContains(response, "00.000.000/0000-00")
                self.assertContains(response, "dpo@example.test")
                self.assertNotContains(response, "[RAZÃO SOCIAL]")

    def test_privacy_policy_covers_required_topics(self):
        response = self.client.get(reverse("privacy"))
        for text in (
            "Controladora",
            "Operadora",
            "A definir pelo jurídico",
            "Cadastro:</strong> e-mail, empresa e papel",
            "dados pessoais sensíveis referentes à saúde",
            "art. 11, I",
            "A confirmar pelo jurídico",
            "5 pessoas ou mais",
            "[PRAZO A DEFINIR]",
            "Portabilidade dos dados",
            "Revogação do consentimento",
            reverse("privacy_settings"),
            "Encarregado de dados",
        ):
            with self.subTest(text=text):
                self.assertContains(response, text)
        # The User model stores only the e-mail; the policy must not claim a name.
        self.assertNotContains(response, "nome, e-mail")

    def test_terms_state_it_is_not_a_diagnosis_and_list_emergency_numbers(self):
        response = self.client.get(reverse("terms"))
        self.assertContains(response, "não é avaliação clínica nem diagnóstico")
        self.assertContains(response, "não substitui profissional de saúde")
        self.assertContains(response, "CVV — ligue 188")
        self.assertContains(response, "SAMU — ligue 192")

    def test_login_links_to_both_pages(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertContains(response, f'href="{reverse("terms")}"')


class RoleNavigationTests(TestCase):
    """Every internal link on the menu and home answers without 403."""

    HREF = re.compile(r'href="(/[^"]*)"')

    def setUp(self):
        self.org = Organization.objects.create(name="Nav Org", slug="nav-org")

    def login_as(self, role):
        user = get_user_model().objects.create_user(
            email=f"{role.lower()}@example.test", password="test-pass"
        )
        Membership.objects.create(user=user, organization=self.org, role=role)
        self.client.force_login(user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.org.pk
        session.save()

    def test_no_link_leads_to_403_for_any_role(self):
        for role in Membership.Role.values:
            with self.subTest(role=role):
                self.login_as(role)
                html = self.client.get(reverse("app")).content.decode()
                links = {
                    link
                    for link in self.HREF.findall(html)
                    if not link.startswith("/static/")
                }
                self.assertIn(reverse("privacy"), links)
                self.assertIn(reverse("terms"), links)
                self.assertIn(reverse("privacy_settings"), links)
                for link in sorted(links):
                    self.assertNotEqual(
                        self.client.get(link).status_code, 403, f"{role}: {link}"
                    )
                self.client.logout()

    def test_only_collaborator_sees_assessment_entry_points(self):
        hub = f'href="{reverse("assessment_hub")}"'
        for role in Membership.Role.values:
            with self.subTest(role=role):
                self.login_as(role)
                response = self.client.get(reverse("app"))
                if role == Membership.Role.COLLABORATOR:
                    self.assertContains(response, hub)
                    self.assertContains(response, "Faça sua avaliação")
                    self.assertContains(response, "Minha avaliação")
                else:
                    self.assertNotContains(response, hub)
                    self.assertNotContains(response, "Faça sua avaliação")
                    self.assertNotContains(response, "Sua prioridade agora")
                    self.assertNotContains(response, "Minha avaliação")
                self.client.logout()
