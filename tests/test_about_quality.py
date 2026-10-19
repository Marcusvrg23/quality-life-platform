"""'Conheça a Quality' (docs/specs/16-conheca-a-quality.md, aceite 1 a 5)."""

import re

from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization, User

PASSWORD = "about-quality-password-16"
URL = "/app/conheca-a-quality/"
NAV_LINK = re.compile(
    r'<a href="/app/conheca-a-quality/"\s*(aria-current="page")?\s*>'
    r'<span aria-hidden="true">✦</span>Conheça a Quality</a>'
)
FORBIDDEN = (
    re.compile(r"pr[ée]via", re.IGNORECASE),
    re.compile(r"\bpreview\b", re.IGNORECASE),
    re.compile(r"\bIA\b"),
    re.compile(r"inteligência artificial", re.IGNORECASE),
    re.compile(r"aguardando", re.IGNORECASE),
    re.compile(r"MINUTA"),
    re.compile(r"Exemplo de", re.IGNORECASE),
    re.compile(r"em definição", re.IGNORECASE),
    re.compile(r"\[EMAIL-COMERCIAL\]"),
)
SERVICES = (
    "Ginástica laboral",
    "Massoterapia",
    "Palestras lúdicas",
    "Aulas de dança laboral",
    "Eventos",
    "Ergonomia",
    "SIPAT / Semana da saúde",
    "Meditação / relaxamento",
    "Gestão emocional",
    "Nutrição online",
)
STEPS = (
    "Contato",
    "Visita de diagnóstico",
    "Entrega da proposta",
    "Implementação",
    "Acompanhamento e avaliação",
)
BENEFITS = (
    "Rotina profissional agradável",
    "Atividades saudáveis",
    "Colaboradores confiantes",
    "Melhor produtividade individual",
    "Resultados coletivos",
)


class AboutQualityTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Empresa", slug="empresa-16"
        )
        self.user = User.objects.create_user("pessoa@empresa.test", PASSWORD)
        Membership.objects.create(
            user=self.user,
            organization=self.organization,
            role=Membership.Role.COLLABORATOR,
        )

    def html(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_route_name(self):
        self.assertEqual(reverse("about_quality"), URL)

    def test_requires_login(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_rejects_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(URL).status_code, 405)

    def test_every_role_opens_it_and_the_menu_marks_it(self):
        manager = User.objects.create_user("gestor@empresa.test", PASSWORD)
        Membership.objects.create(
            user=manager,
            organization=self.organization,
            role=Membership.Role.CORPORATE_MANAGER,
        )
        operator = User.objects.create_superuser("ql@quality.test", PASSWORD)
        for user in (self.user, manager, operator):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                links = NAV_LINK.findall(self.html())
                self.assertEqual(links, ['aria-current="page"'])

    def test_other_pages_show_the_link_without_current(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("wellbeing_gym")).content.decode()
        self.assertEqual(NAV_LINK.findall(html), [""])

    def test_forged_tenant_is_forbidden(self):
        other = Organization.objects.create(name="Outra", slug="outra-16")
        self.client.force_login(self.user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = other.pk
        session.save()
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_shows_the_presentation_content(self):
        self.client.force_login(self.user)
        html = self.html()
        for text in (
            "Qualidade de vida &amp; ",
            "para os colaboradores",
            "Educação Física",
            "Programas personalizados para a sua empresa",
            "Prática de exercícios físicos para a melhoria da qualidade de vida",
            "Assessoria e consultoria com exclusividade",
            "Soluções online para os colaboradores",
            "Integração entre equipes",
            "Gerenciamento do estresse",
            "Adaptação e adequação da atuação em home office",
            "Promoção da cultura de saúde aos colaboradores",
            "Propostas personalizadas de acordo com a necessidade dos colaboradores",
            "www.qualitylife.online",
            *SERVICES,
            *STEPS,
            *BENEFITS,
        ):
            with self.subTest(text=text):
                self.assertIn(text, html)

    def test_no_preview_or_internal_notes(self):
        self.client.force_login(self.user)
        html = self.html()
        self.assertEqual([p.pattern for p in FORBIDDEN if p.search(html)], [])
        self.assertNotIn("{#", html)

    @override_settings(QL_SALES_EMAIL="[EMAIL-COMERCIAL]")
    def test_contact_falls_back_to_the_presentation_email(self):
        self.client.force_login(self.user)
        self.assertIn(
            '<strong id="qlc-mail">ceo.qualitylife.online@gmail.com</strong>',
            self.html(),
        )

    @override_settings(QL_SALES_EMAIL="vendas@quality.test")
    def test_contact_uses_the_configured_sales_email(self):
        self.client.force_login(self.user)
        self.assertIn('<strong id="qlc-mail">vendas@quality.test</strong>', self.html())

    def test_assets_are_served_by_the_app(self):
        self.client.force_login(self.user)
        html = self.html()
        self.assertNotIn("cdnjs", html)
        self.assertNotIn("cdn.jsdelivr", html)
        self.assertNotIn("fonts.googleapis", html)
        for path in (
            "quality_life/conheca.css",
            "quality_life/conheca.js",
            "quality_life/vendor/three-0.128.0.min.js",
            "quality_life/vendor/ScrollTrigger-3.13.0.min.js",
            "quality_life/images/brand/quality-life-logo-ring-512.png",
        ):
            with self.subTest(path=path):
                self.assertIn(path, html)
                self.assertIsNotNone(finders.find(path))
