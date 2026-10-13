"""TEST ONLY — NOT PRODUCTION CONTENT. LGPD consent gate for the assessment."""

from decimal import Decimal
from unittest import mock

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from assessments.models import (
    Answer,
    Assessment,
    Pillar,
    Question,
    QuestionnairePillar,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import publish_questionnaire
from config.legal import CONSENT_VERSION
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.consent import grant_consent, has_active_consent
from identity.models import ConsentRecord, Membership, Organization

User = get_user_model()
PURPOSE = ConsentRecord.Purpose.ASSESSMENT_HEALTH_DATA


class ConsentFixtureMixin:
    def setUp(self):
        self.user = User.objects.create_user(
            email="consent@example.test", password="test-pass"
        )
        self.org = Organization.objects.create(name="Consent Org", slug="consent-org")
        self.other_org = Organization.objects.create(
            name="Consent Other", slug="consent-other"
        )
        Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.COLLABORATOR
        )
        self.client.force_login(self.user)
        self.select(self.org)

    def select(self, organization):
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = organization.pk
        session.save()

    def questionnaire(self):
        version = QuestionnaireVersion.objects.create(
            code="test-only-consent",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-consent",
        )
        configured = QuestionnairePillar.objects.create(
            questionnaire=version,
            pillar=Pillar.objects.get(display_order=1),
            display_order=1,
            weight=Decimal(1),
        )
        question = Question.objects.create(
            questionnaire_pillar=configured,
            code="only",
            text="TEST ONLY — question?",
            weight=Decimal(1),
            display_order=1,
        )
        options = [
            QuestionOption.objects.create(
                question=question,
                code=f"test-{score}",
                label=f"TEST ONLY choice {order}",
                score_value=Decimal(score),
                display_order=order,
            )
            for order, score in enumerate((0, 100), 1)
        ]
        publish_questionnaire(version.pk)
        return question, options

    def start(self, consent=True):
        data = {"consent": "on"} if consent else {}
        return self.client.post(reverse("assessment_start"), data)

    def revoke(self):
        return self.client.post(reverse("privacy_revoke"), {"confirm": "on"})


class ConsentRecordModelTests(ConsentFixtureMixin, TestCase):
    def record(self, organization=None):
        return ConsentRecord.objects.create(
            user=self.user,
            organization=organization or self.org,
            purpose=PURPOSE,
            version=CONSENT_VERSION,
            accepted_at=timezone.now(),
        )

    def test_revoked_at_can_be_filled_once(self):
        record = self.record()
        record.revoke()
        record.refresh_from_db()
        self.assertIsNotNone(record.revoked_at)
        with self.assertRaises(ValidationError):
            record.revoke()

    def test_other_fields_and_deletion_are_immutable(self):
        record = self.record()
        record.version = "outra"
        with self.assertRaises(ValidationError):
            record.save()
        record.refresh_from_db()
        with self.assertRaises(ValidationError):
            record.delete()
        with self.assertRaises(ValidationError):
            ConsentRecord.objects.filter(pk=record.pk).update(revoked_at=None)
        with self.assertRaises(ValidationError):
            ConsentRecord.objects.filter(pk=record.pk).delete()
        self.assertEqual(ConsentRecord.objects.count(), 1)

    def test_consent_is_scoped_to_one_company(self):
        self.record()
        self.assertTrue(has_active_consent(self.user, self.org))
        self.assertFalse(has_active_consent(self.user, self.other_org))

    def test_old_version_is_not_active(self):
        ConsentRecord.objects.create(
            user=self.user,
            organization=self.org,
            purpose=PURPOSE,
            version="versao-antiga",
            accepted_at=timezone.now(),
        )
        self.assertFalse(has_active_consent(self.user, self.org))

    def test_admin_is_read_only(self):
        admin_user = User.objects.create_superuser(
            email="root@example.test", password="test-pass"
        )
        request = RequestFactory().get("/admin/")
        request.user = admin_user
        model_admin = site._registry[ConsentRecord]
        record = self.record()
        self.assertTrue(model_admin.has_view_permission(request, record))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, record))
        self.assertFalse(model_admin.has_delete_permission(request, record))
        request.user = self.user
        self.assertFalse(model_admin.has_view_permission(request, record))


class ConsentGateTests(ConsentFixtureMixin, TestCase):
    def test_hub_shows_prominent_unchecked_consent(self):
        self.questionnaire()
        response = self.client.get(reverse("assessment_hub"))
        html = response.content.decode()
        self.assertContains(response, 'name="consent"')
        self.assertContains(response, "required")
        self.assertNotIn("checked", html)
        self.assertContains(response, "5 pessoas ou mais")
        self.assertContains(response, "nunca respostas individuais")
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertContains(response, f'href="{reverse("terms")}"')

    def test_start_without_checkbox_creates_nothing(self):
        self.questionnaire()
        response = self.start(consent=False)
        self.assertRedirects(
            response, reverse("assessment_hub"), fetch_redirect_response=False
        )
        self.assertFalse(ConsentRecord.objects.exists())
        self.assertFalse(Assessment.objects.exists())
        self.assertContains(
            self.client.get(reverse("assessment_hub")), "Marque a autorização"
        )

    def test_start_with_checkbox_creates_one_consent_and_assessment(self):
        self.questionnaire()
        self.start()
        record = ConsentRecord.objects.get()
        self.assertEqual(
            (record.user, record.organization, record.purpose, record.version),
            (self.user, self.org, PURPOSE, CONSENT_VERSION),
        )
        self.assertIsNone(record.revoked_at)
        self.assertEqual(Assessment.objects.count(), 1)

    def test_repeated_start_does_not_duplicate_consent(self):
        self.questionnaire()
        self.start()
        self.start()
        self.start(consent=False)
        self.assertEqual(ConsentRecord.objects.count(), 1)
        self.assertEqual(Assessment.objects.count(), 1)

    def test_failed_start_rolls_back_consent(self):
        self.questionnaire()
        with mock.patch(
            "assessments.views.start_assessment",
            side_effect=ValidationError("TEST ONLY"),
        ):
            self.start()
        self.assertFalse(ConsentRecord.objects.exists())
        self.assertFalse(Assessment.objects.exists())

    def test_no_published_questionnaire_creates_no_consent(self):
        self.start()
        self.assertFalse(ConsentRecord.objects.exists())

    def test_revocation_blocks_start_question_review_and_complete(self):
        question, options = self.questionnaire()
        self.start()
        assessment = Assessment.objects.get()
        self.assertRedirects(self.revoke(), reverse("privacy_settings"))
        hub = reverse("assessment_hub")
        question_url = reverse("assessment_question", args=[assessment.pk, question.pk])

        self.assertRedirects(self.client.get(question_url), hub)
        self.assertRedirects(
            self.client.post(question_url, {"option": options[1].pk}), hub
        )
        self.assertFalse(Answer.objects.exists())
        self.assertRedirects(
            self.client.get(reverse("assessment_review", args=[assessment.pk])), hub
        )
        self.assertRedirects(
            self.client.post(reverse("assessment_complete", args=[assessment.pk])),
            hub,
        )
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, Assessment.Status.IN_PROGRESS)

    def test_revocation_blocks_new_assessment(self):
        self.questionnaire()
        grant_consent(self.user, self.org)
        self.revoke()
        self.assertRedirects(self.start(consent=False), reverse("assessment_hub"))
        self.assertFalse(Assessment.objects.exists())

    def test_new_explicit_consent_after_revocation_is_a_new_record(self):
        self.questionnaire()
        self.start()
        self.revoke()
        self.assertContains(
            self.client.get(reverse("assessment_hub")), 'name="consent"'
        )
        self.start()
        self.assertEqual(ConsentRecord.objects.count(), 2)
        self.assertTrue(has_active_consent(self.user, self.org))

    def test_consent_from_one_company_does_not_cover_another(self):
        self.questionnaire()
        Membership.objects.create(
            user=self.user,
            organization=self.other_org,
            role=Membership.Role.COLLABORATOR,
        )
        self.start()
        self.select(self.other_org)
        self.assertRedirects(self.start(consent=False), reverse("assessment_hub"))
        self.assertEqual(
            Assessment.objects.filter(organization=self.other_org).count(), 0
        )
        self.assertContains(
            self.client.get(reverse("assessment_hub")), 'name="consent"'
        )
        self.start()
        self.assertEqual(
            ConsentRecord.objects.filter(organization=self.other_org).count(), 1
        )
        # Revoking in the other company leaves this company's consent active.
        self.revoke()
        self.assertTrue(has_active_consent(self.user, self.org))
        self.assertFalse(has_active_consent(self.user, self.other_org))


class PrivacySettingsTests(ConsentFixtureMixin, TestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("privacy_settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertEqual(self.client.post(reverse("privacy_revoke")).status_code, 302)

    def test_shows_active_consent_and_dpo_guidance(self):
        self.questionnaire()
        self.start()
        response = self.client.get(reverse("privacy_settings"))
        self.assertContains(response, CONSENT_VERSION)
        self.assertContains(response, "Revogar")
        self.assertContains(response, 'name="confirm"')
        self.assertContains(response, "encarregado")

    def test_revoke_requires_confirmation_and_post(self):
        self.questionnaire()
        self.start()
        self.assertEqual(self.client.get(reverse("privacy_revoke")).status_code, 405)
        self.client.post(reverse("privacy_revoke"))
        self.assertTrue(has_active_consent(self.user, self.org))
        self.revoke()
        self.assertFalse(has_active_consent(self.user, self.org))
        self.assertIsNotNone(ConsentRecord.objects.get().revoked_at)

    def test_revoke_requires_csrf(self):
        self.questionnaire()
        self.start()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        session = csrf_client.session
        session[SESSION_ORGANIZATION_KEY] = self.org.pk
        session.save()
        response = csrf_client.post(reverse("privacy_revoke"), {"confirm": "on"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(has_active_consent(self.user, self.org))
