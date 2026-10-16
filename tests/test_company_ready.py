"""App for companies, not a prototype (spec 15): no internal notes on screen,
new practice items in the catalog and the "Hoje" card on the home."""

import datetime
import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from config import wellbeing_catalog as catalog
from config.legal import CONSENT_VERSION
from config.lessons import LESSONS
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization
from wellbeing.models import ActivitySession

PASSWORD = "company-ready-password-15"
# Noon in São Paulo: practices a few minutes before are on the same local day.
NOON = datetime.datetime(2026, 10, 14, 15, 0, tzinfo=datetime.UTC)
TODAY = "config.calendar_highlights.timezone.localdate"
FORBIDDEN = (
    re.compile(r"\bIA\b"),
    re.compile(r"inteligência artificial", re.IGNORECASE),
    re.compile(r"proposta", re.IGNORECASE),
    re.compile(r"aguardando", re.IGNORECASE),
    re.compile(r"MINUTA"),
    re.compile(r"Exemplo de", re.IGNORECASE),
    re.compile(r"em definição", re.IGNORECASE),
)
APP_PAGES = (
    "app",
    "wellbeing_gym",
    "wellbeing_meditation",
    "wellbeing_relax",
    "exercises",
    "lessons",
    "wellbeing_progress",
    "wellbeing_reminders",
    "install_app",
    "privacy",
    "terms",
)


def forbidden_in(html):
    return [pattern.pattern for pattern in FORBIDDEN if pattern.search(html)]


class TenantCase(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.user = users.create_user(email="empresa@example.test", password=PASSWORD)
        self.org = Organization.objects.create(name="Empresa A", slug="empresa-a15")
        self.other_org = Organization.objects.create(
            name="Empresa B", slug="empresa-b15"
        )
        Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.COLLABORATOR
        )

    def login(self, org=None):
        self.client.force_login(self.user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = (org or self.org).pk
        session.save()


class NoInternalNotesOnScreenTests(TenantCase):
    def test_no_page_mentions_ai_proposals_drafts_or_placeholders(self):
        self.login()
        # September: the commemorative notice is on screen too.
        with mock.patch(TODAY, return_value=datetime.date(2026, 9, 15)):
            for name in APP_PAGES:
                with self.subTest(page=name):
                    response = self.client.get(reverse(name))
                    self.assertEqual(response.status_code, 200)
                    html = response.content.decode()
                    self.assertEqual(forbidden_in(html), [])
                    # A multi-line {# #} is not a comment: it shows as text.
                    self.assertNotIn("{#", html)

    def test_patterns_catch_the_old_texts_and_spare_words_like_inicial(self):
        for text in (
            "Vídeo ilustrativo gerado por IA",
            catalog.__dict__.get("PROPOSAL_NOTE", "Tempos em proposta"),
            "MINUTA — pendente de revisão jurídica",
            "Exemplo de atividade curta",
            "Conteúdo em definição pela Quality Life",
        ):
            with self.subTest(text=text):
                self.assertTrue(forbidden_in(text))
        self.assertEqual(forbidden_in("AVALIAÇÃO INICIAL · IAGO · média"), [])

    def test_notes_are_gone_from_the_catalog(self):
        self.assertFalse(hasattr(catalog, "PROPOSAL_NOTE"))
        self.assertFalse(hasattr(catalog, "AI_VIDEO_NOTE"))

    def test_commemorative_notice_shows_title_and_support_text_only(self):
        self.login()
        with mock.patch(TODAY, return_value=datetime.date(2026, 9, 15)):
            html = self.client.get(reverse("app")).content.decode()
        self.assertIn("Setembro Amarelo", html)
        self.assertIn("CVV — ligue 188", html)

    def test_lesson_descriptions_are_final_texts(self):
        self.assertEqual(
            [lesson["description"] for lesson in LESSONS],
            [
                (
                    "Atividade curta para ativar o corpo antes de começar a"
                    " jornada de trabalho."
                ),
                (
                    "Pausa guiada para recuperar a mobilidade e aliviar a tensão"
                    " do expediente."
                ),
                (
                    "Sequência leve para desacelerar e encerrar a jornada com uma"
                    " rotina de recuperação."
                ),
            ],
        )

    def test_privacy_shows_readable_text_version_and_keeps_consent_version(self):
        self.assertEqual(CONSENT_VERSION, "2026-10-minuta-1")
        html = self.client.get(reverse("privacy")).content.decode()
        self.assertIn("Versão do texto: outubro de 2026", html)
        self.assertNotIn(CONSENT_VERSION, html)
        self.assertNotIn("legal-draft", html)

    def test_player_video_label_names_the_exercise_and_relax_background(self):
        self.login()
        player = self.client.get(reverse("wellbeing_gym")).content.decode()
        self.assertNotIn('wb-note">', player.split("data-player", 1)[1])
        relax = self.client.get(reverse("wellbeing_relax")).content.decode()
        self.assertIn('aria-label="Fundo visual"', relax)
        self.assertNotIn("wb-footnote", relax)
        library = self.client.get(reverse("exercises")).content.decode()
        self.assertNotIn("quadro do vídeo", library)


class NewCatalogItemsTests(TenantCase):
    def post(self, **data):
        return self.client.post(reverse("wellbeing_record"), data)

    def test_sequence_and_lessons_are_available_gym_items(self):
        sequence = catalog.find_available(catalog.KIND_GYM, "sequencia-exercicios")
        self.assertIsNotNone(sequence)
        self.assertIsNone(sequence["duration_seconds"])
        for lesson in LESSONS:
            with self.subTest(lesson=lesson["slug"]):
                item = catalog.find_available(
                    catalog.KIND_GYM, f"aula-{lesson['slug']}"
                )
                self.assertIsNotNone(item)
                self.assertEqual(
                    item["file"], f"quality_life/videos/{lesson['slug']}.mp4"
                )
        # Only under their own kind.
        self.assertIsNone(
            catalog.find_available(catalog.KIND_MEDITATION, "sequencia-exercicios")
        )

    def test_record_needs_60_seconds_and_goes_to_the_active_company(self):
        Membership.objects.create(
            user=self.user,
            organization=self.other_org,
            role=Membership.Role.COLLABORATOR,
        )
        self.login()
        for slug in ("sequencia-exercicios", "aula-inicio-trabalho"):
            with self.subTest(slug=slug):
                ActivitySession.objects.all().delete()
                short = self.post(kind="ginastica", slug=slug, duration_seconds="59")
                self.assertEqual(short.status_code, 400)
                self.assertFalse(ActivitySession.objects.exists())
                response = self.post(
                    kind="ginastica", slug=slug, duration_seconds="90", completed="1"
                )
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["minutes"], 1)
                session = ActivitySession.objects.get()
                self.assertEqual(
                    (session.organization, session.kind, session.slug),
                    (self.org, "ginastica", slug),
                )

    def test_forged_tenant_is_denied(self):
        self.login(self.other_org)
        response = self.post(
            kind="ginastica", slug="sequencia-exercicios", duration_seconds="90"
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ActivitySession.objects.exists())


class TodayCardTests(TenantCase):
    def practice(self, org, minutes_ago, seconds, slug="respiracao-foco"):
        ActivitySession.objects.create(
            user=self.user,
            organization=org,
            kind="meditacao",
            slug=slug,
            started_at=NOON - timedelta(minutes=minutes_ago),
            duration_seconds=seconds,
            completed=True,
        )

    def card(self):
        with mock.patch("wellbeing.services.timezone.now", return_value=NOON):
            html = self.client.get(reverse("app")).content.decode()
        start = html.index('aria-labelledby="today-card-title"')
        return html[start : html.index("</section>", start)]

    def test_without_practice_today_invites_to_the_gym(self):
        self.login()
        card = self.card()
        self.assertIn("Você ainda não praticou hoje.", card)
        self.assertIn(f'href="{reverse("wellbeing_gym")}"', card)

    def test_shows_own_numbers_of_the_active_company_only(self):
        Membership.objects.create(
            user=self.user,
            organization=self.other_org,
            role=Membership.Role.COLLABORATOR,
        )
        self.practice(self.org, 30, 180)
        self.practice(self.org, 5, 125)
        self.practice(self.other_org, 60, 600)
        other = get_user_model().objects.create_user(
            email="colega@example.test", password=PASSWORD
        )
        Membership.objects.create(
            user=other, organization=self.org, role=Membership.Role.COLLABORATOR
        )
        ActivitySession.objects.create(
            user=other,
            organization=self.org,
            kind="ginastica",
            slug="sequencia-exercicios",
            started_at=NOON - timedelta(minutes=50),
            duration_seconds=900,
        )
        self.login()
        card = self.card()
        self.assertIn('data-today-sessions="2"', card)
        self.assertIn('data-today-minutes="5"', card)
        self.assertIn('data-today-streak="1"', card)
        self.assertIn(f'href="{reverse("wellbeing_progress")}"', card)
        self.assertNotIn("Você ainda não praticou hoje.", card)
        self.login(self.other_org)
        card = self.card()
        self.assertIn('data-today-sessions="1"', card)
        self.assertIn('data-today-minutes="10"', card)
