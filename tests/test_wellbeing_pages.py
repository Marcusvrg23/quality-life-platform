"""Wellbeing pages: tenant access and content honesty (spec 11, aceite 1 e 2)."""

import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from config import wellbeing_catalog as catalog
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization

PAGES = ("wellbeing_gym", "wellbeing_meditation", "wellbeing_relax")


class WellbeingPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="paginas@example.test", password="test-only-password"
        )
        self.org = Organization.objects.create(name="Páginas", slug="paginas-be")
        self.membership = Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.COLLABORATOR
        )

    def sessions(self, response):
        match = re.search(
            r'<script id="wb-sessions" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        return json.loads(match.group(1))

    def test_every_role_with_exercises_sees_the_pages(self):
        for role in Membership.Role.values:
            self.membership.role = role
            self.membership.save()
            self.client.force_login(self.user)
            for name in PAGES:
                with self.subTest(role=role, page=name):
                    response = self.client.get(reverse(name))
                    self.assertEqual(response.status_code, 200)
                    # Media never starts by itself: no autoplay, no src yet.
                    html = response.content.decode()
                    self.assertNotIn("autoplay", html)
                    self.assertNotRegex(html, r"<video[^>]*\ssrc=")
                    self.assertEqual(self.client.post(reverse(name)).status_code, 405)

    def test_anonymous_and_forged_tenant_are_denied(self):
        for name in PAGES:
            url = reverse(name)
            self.assertRedirects(self.client.get(url), f"/login/?next={url}")
        self.client.force_login(self.user)
        other = Organization.objects.create(name="Outra", slug="outra-paginas")
        for name in (*PAGES, "wellbeing_progress"):
            # The first 403 drops the forged key, so forge it again each time.
            session = self.client.session
            session[SESSION_ORGANIZATION_KEY] = other.pk
            session.save()
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_gym_sessions_payload_lists_steps_with_videos_or_photos(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("wellbeing_gym"))
        self.assertContains(response, catalog.PROPOSAL_NOTE)
        for category in (
            "Alongamento para pescoço e ombros",
            "Pausa ativa para coluna",
        ):
            self.assertContains(response, category)
        self.assertContains(response, "Na cadeira")
        sessions = {item["slug"]: item for item in self.sessions(response)}
        self.assertEqual(set(sessions), {s["slug"] for s in catalog.GYM_SESSIONS})
        session = sessions["pescoco-ombros-3min"]
        self.assertEqual(sum(step["seconds"] for step in session["steps"]), 180)
        steps = {step["slug"]: step for step in session["steps"]}
        self.assertTrue(steps["pescoco"]["video"].endswith("ex-pescoco.mp4"))
        self.assertTrue(steps["pescoco"]["image"].endswith("exercises/pescoco.webp"))
        self.assertIsNone(steps["autoabraco"]["video"])
        self.assertTrue(steps["autoabraco"]["image"].endswith("autoabraco.webp"))
        column = sessions["pausa-coluna-5min"]["steps"][0]
        self.assertTrue(column["video"].endswith("ex-inclinacao-frente.mp4"))
        self.assertIsNone(column["image"])

    def test_meditations_are_breathing_sessions_without_narration(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("wellbeing_meditation"))
        sessions = self.sessions(response)
        self.assertEqual(
            [(s["title"], s["duration"]) for s in sessions],
            [
                ("Respiração para foco", 120),
                ("Reduzir ansiedade", 300),
                ("Relaxamento profundo", 600),
            ],
        )
        for session in sessions:
            self.assertEqual(
                session["breathing"],
                {
                    "inhale": catalog.BREATH_IN_SECONDS,
                    "exhale": catalog.BREATH_OUT_SECONDS,
                },
            )
        self.assertContains(response, "sem narração")
        self.assertContains(response, "data-player-noise")

    def test_relax_pending_sounds_have_no_play_control(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("wellbeing_relax"))
        html = response.content.decode()
        for item in catalog.SOUNDS:
            card = re.search(
                rf'<article[^>]*data-sound-card="{item["slug"]}".*?</article>',
                html,
                re.DOTALL,
            ).group(0)
            with self.subTest(sound=item["slug"]):
                if item["status"] == catalog.IN_PREPARATION:
                    self.assertIn("Em preparação", card)
                    self.assertNotIn("data-sound-play", card)
                    self.assertNotIn("<audio", card)
                else:
                    self.assertIn(f'data-noise="{item["noise"]}"', card)
        for minutes in catalog.RELAX_TIMER_MINUTES:
            self.assertContains(response, f'value="{minutes}"')
        self.assertContains(response, "med-relaxamento.webp")
