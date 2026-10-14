"""Practice records: owner-only writes, tenant scope, CSRF (spec 11, aceite 3)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization
from wellbeing.models import ActivitySession

PASSWORD = "test-only-password"


class RecordPracticeTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.user = users.create_user(email="pratica@example.test", password=PASSWORD)
        self.other_user = users.create_user(
            email="outra@example.test", password=PASSWORD
        )
        self.org = Organization.objects.create(name="Bem-estar", slug="bem-estar")
        self.other_org = Organization.objects.create(name="Outra", slug="outra-be")
        self.membership = Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.COLLABORATOR
        )
        Membership.objects.create(
            user=self.other_user,
            organization=self.other_org,
            role=Membership.Role.COLLABORATOR,
        )
        self.url = reverse("wellbeing_record")

    def post(self, client=None, **data):
        payload = {
            "kind": "meditacao",
            "slug": "respiracao-foco",
            "duration_seconds": "120",
            "completed": "1",
        }
        payload.update(data)
        return (client or self.client).post(self.url, payload)

    def test_owner_records_for_active_organization_only(self):
        self.client.force_login(self.user)
        response = self.post()
        self.assertEqual(response.status_code, 201)
        session = ActivitySession.objects.get()
        self.assertEqual(
            (session.user, session.organization, session.kind, session.slug),
            (self.user, self.org, "meditacao", "respiracao-foco"),
        )
        self.assertTrue(session.completed)
        self.assertEqual(session.duration_seconds, 120)
        # The server sets the start time from its own clock.
        self.assertLess(
            abs(timezone.now() - timedelta(seconds=120) - session.started_at),
            timedelta(seconds=5),
        )
        # Fields for another user or organization are ignored.
        ActivitySession.objects.all().delete()
        self.post(user=self.other_user.pk, organization=self.other_org.pk)
        self.assertEqual(ActivitySession.objects.get().user, self.user)
        self.assertEqual(ActivitySession.objects.get().organization, self.org)

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(self.post(client).status_code, 403)
        self.assertFalse(ActivitySession.objects.exists())

    def test_anonymous_get_and_forged_tenant_are_rejected(self):
        response = self.post()
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.other_org.pk
        session.save()
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(ActivitySession.objects.exists())

    def test_unknown_or_unavailable_items_are_404(self):
        self.client.force_login(self.user)
        for kind, slug in (
            ("meditacao", "nao-existe"),
            ("relaxamento", "mar"),  # em preparação: nothing to play
            ("ginastica", "respiracao-foco"),  # wrong kind
            ("outro", "respiracao-foco"),
        ):
            with self.subTest(kind=kind, slug=slug):
                self.assertEqual(self.post(kind=kind, slug=slug).status_code, 404)
        self.assertFalse(ActivitySession.objects.exists())

    def test_short_or_invalid_durations_are_rejected_and_long_ones_capped(self):
        self.client.force_login(self.user)
        for value in ("59", "0", "-5", "abc", ""):
            with self.subTest(duration=value):
                self.assertEqual(
                    self.post(duration_seconds=value, completed="0").status_code, 400
                )
        self.assertFalse(ActivitySession.objects.exists())
        self.assertEqual(
            self.post(duration_seconds="60", completed="0").status_code, 201
        )
        ActivitySession.objects.all().delete()
        self.assertEqual(self.post(duration_seconds="9999").status_code, 201)
        self.assertEqual(ActivitySession.objects.get().duration_seconds, 120)

    def test_overlapping_practice_is_not_counted_twice(self):
        self.client.force_login(self.user)
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(ActivitySession.objects.count(), 1)

    def test_relaxation_accepts_up_to_the_longest_timer(self):
        self.client.force_login(self.user)
        response = self.post(
            kind="relaxamento", slug="ruido-rosa", duration_seconds="3600"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ActivitySession.objects.get().duration_seconds, 1800)

    def test_database_rejects_invalid_rows(self):
        base = {
            "user": self.user,
            "organization": self.org,
            "slug": "x",
            "started_at": timezone.now(),
        }
        for kind, seconds in (("outro", 120), ("meditacao", 10)):
            with (
                self.subTest(kind=kind, seconds=seconds),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                ActivitySession.objects.create(
                    kind=kind, duration_seconds=seconds, **base
                )
