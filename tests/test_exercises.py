"""Exercise content provenance and tenant boundaries (no progress persistence)."""

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from config.exercises import EXERCISES
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization


class ExerciseContentTests(SimpleTestCase):
    def test_selection_has_sources_images_and_unique_slugs(self):
        self.assertEqual(len(EXERCISES), 8)
        self.assertEqual(len({item["slug"] for item in EXERCISES}), 8)
        for item in EXERCISES:
            with self.subTest(exercise=item["slug"]):
                self.assertTrue(item["instruction"])
                self.assertTrue(item["page"])
                self.assertGreater(item["image_page"], 0)
                self.assertIsNotNone(
                    finders.find(f"quality_life/images/exercises/{item['slug']}.webp")
                )
        calf = next(item for item in EXERCISES if item["slug"] == "panturrilha")
        self.assertTrue(calf["visual_only"])
        self.assertIn("sem detalhar", calf["instruction"])


class ExerciseAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="exercise@example.test", password="test-only-password"
        )
        self.org = Organization.objects.create(name="Exercise QA", slug="exercise-qa")
        self.membership = Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.COLLABORATOR
        )
        self.url = reverse("exercises")

    def test_authenticated_library_has_read_only_sequence_and_no_fake_time(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "Autoabraço")
        self.assertContains(response, "Começar sequência")
        self.assertContains(response, "Antes de começar")
        self.assertContains(response, "data-open-exercise=", count=8)
        self.assertNotContains(response, "cronômetro")
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_anonymous_and_stale_tenant_cannot_access(self):
        self.assertRedirects(self.client.get(self.url), "/login/?next=/app/exercises/")
        self.client.force_login(self.user)
        self.client.get(self.url)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_forged_tenant_and_missing_context_denied(self):
        self.client.force_login(self.user)
        other = Organization.objects.create(name="Other", slug="other-exercise")
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = other.pk
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertNotIn(SESSION_ORGANIZATION_KEY, self.client.session)
        Membership.objects.create(
            user=self.user, organization=other, role=Membership.Role.COLLABORATOR
        )
        self.assertEqual(self.client.get(self.url).status_code, 403)
