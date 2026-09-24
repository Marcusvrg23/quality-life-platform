"""Focused checks for the guarded, repeatable demonstration dataset."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from assessments.management.commands.seed_quality_life_demo import (
    DEMO_CODE,
    DEMO_EMAILS,
    DEMO_NAME,
    DEMO_SLUG,
    DEMO_TITLE,
)
from assessments.models import (
    Assessment,
    Pillar,
    Question,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import validate_questionnaire
from identity.models import Membership, Organization


class DemoSeedTests(TestCase):
    def seed(self, *, enabled="true", password="Long-demo-passphrase-8274"):
        with patch.dict(
            "os.environ",
            {
                "QUALITY_LIFE_DEMO_SEED_ENABLED": enabled,
                "QUALITY_LIFE_DEMO_PASSWORD": password,
            },
        ):
            call_command("seed_quality_life_demo", stdout=StringIO())

    def test_flag_off_refuses_without_writes(self):
        with self.assertRaisesMessage(CommandError, "QUALITY_LIFE_DEMO_SEED_ENABLED"):
            self.seed(enabled="false")
        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(QuestionnaireVersion.objects.count(), 0)

    def test_missing_or_invalid_password_refuses_without_writes(self):
        for password in ("", "123"):
            with self.subTest(password=password):
                with self.assertRaises(CommandError):
                    self.seed(password=password)
                self.assertEqual(Organization.objects.count(), 0)
                self.assertEqual(get_user_model().objects.count(), 0)

    def test_seed_creates_published_demo_and_is_idempotent(self):
        other = Organization.objects.create(name="Empresa real", slug="empresa-real")
        real_user = get_user_model().objects.create_user(
            email="real@example.org", password="Real-user-passphrase-824"
        )
        Membership.objects.create(
            user=real_user, organization=other, role=Membership.Role.ADMIN
        )
        self.seed()
        demo = Organization.objects.get(slug=DEMO_SLUG)
        self.assertEqual(demo.name, DEMO_NAME)
        questionnaire = QuestionnaireVersion.objects.get(code=DEMO_CODE, version=1)
        self.assertEqual(questionnaire.title, DEMO_TITLE)
        self.assertEqual(questionnaire.status, QuestionnaireVersion.Status.PUBLISHED)
        validate_questionnaire(questionnaire)
        self.assertEqual(
            set(questionnaire.pillars.values_list("pillar__code", flat=True)),
            set(Pillar.objects.values_list("code", flat=True)),
        )
        self.assertEqual(questionnaire.pillars.count(), 9)
        self.assertEqual(Question.objects.count(), 9)
        self.assertEqual(QuestionOption.objects.count(), 45)
        self.assertTrue(
            all(q.text.startswith("DEMO —") for q in Question.objects.all())
        )
        self.assertEqual(
            set(
                Membership.objects.filter(organization=demo).values_list(
                    "user__email", flat=True
                )
            ),
            set(DEMO_EMAILS),
        )
        self.assertFalse(get_user_model().objects.filter(is_superuser=True).exists())
        self.assertEqual(
            set(
                Membership.objects.filter(organization=demo).values_list(
                    "role", flat=True
                )
            ),
            {Membership.Role.COLLABORATOR},
        )
        hashes = dict(get_user_model().objects.values_list("email", "password"))
        demo_user = get_user_model().objects.get(email=DEMO_EMAILS[0])
        assessment = Assessment.objects.create(
            user=demo_user, organization=demo, questionnaire_version=questionnaire
        )
        self.seed()
        self.assertEqual(Organization.objects.count(), 2)
        self.assertEqual(get_user_model().objects.count(), 4)
        self.assertEqual(Membership.objects.count(), 4)
        self.assertEqual(QuestionnaireVersion.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 9)
        self.assertEqual(QuestionOption.objects.count(), 45)
        self.assertEqual(
            dict(get_user_model().objects.values_list("email", "password")), hashes
        )
        self.assertTrue(Assessment.objects.filter(pk=assessment.pk).exists())
        self.assertEqual(Organization.objects.get(pk=other.pk).name, "Empresa real")
        self.assertEqual(
            Membership.objects.get(user=real_user).role, Membership.Role.ADMIN
        )

    def test_reserved_email_collision_rolls_back(self):
        get_user_model().objects.create_user(
            email=DEMO_EMAILS[0], password="Preexisting-user-password-842"
        )
        with self.assertRaisesMessage(CommandError, "reserved demo email"):
            self.seed()
        self.assertFalse(Organization.objects.filter(slug=DEMO_SLUG).exists())
        self.assertFalse(QuestionnaireVersion.objects.filter(code=DEMO_CODE).exists())

    def test_changed_password_refuses_without_resetting_accounts(self):
        self.seed()
        old_hash = get_user_model().objects.get(email=DEMO_EMAILS[0]).password
        with self.assertRaisesMessage(CommandError, "reserved demo email"):
            self.seed(password="Different-demo-passphrase-8247")
        self.assertEqual(
            get_user_model().objects.get(email=DEMO_EMAILS[0]).password, old_hash
        )
