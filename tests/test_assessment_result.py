"""TEST ONLY — NOT PRODUCTION CONTENT. Persisted result presentation."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import localize

from assessments.models import (
    Assessment,
    AssessmentResult,
    Pillar,
    PillarResult,
    QuestionnaireVersion,
)
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization


class AssessmentResultPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="result-owner@example.test", password="test-password"
        )
        self.other = user_model.objects.create_user(
            email="result-other@example.test", password="test-password"
        )
        self.manager = user_model.objects.create_user(
            email="result-manager@example.test", password="test-password"
        )
        self.org = Organization.objects.create(name="Result test", slug="result-test")
        self.other_org = Organization.objects.create(
            name="Other result test", slug="other-result-test"
        )
        for user, org, role in (
            (self.owner, self.org, Membership.Role.COLLABORATOR),
            (self.owner, self.other_org, Membership.Role.COLLABORATOR),
            (self.other, self.org, Membership.Role.COLLABORATOR),
            (self.manager, self.org, Membership.Role.CORPORATE_MANAGER),
        ):
            Membership.objects.create(user=user, organization=org, role=role)
        self.version = QuestionnaireVersion.objects.create(
            code="result-test-only",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-result",
        )
        self.assessment = Assessment.objects.create(
            user=self.owner, organization=self.org, questionnaire_version=self.version
        )
        self.url = reverse("assessment_completed", args=[self.assessment.pk])
        self.client.force_login(self.owner)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.org.pk
        session.save()

    def persist_result(self):
        result = AssessmentResult.objects.create(
            assessment=self.assessment,
            overall_score=Decimal("63.25"),
            overall_band="ATENÇÃO",
            scoring_version="test-result",
        )
        for index, pillar in enumerate(Pillar.objects.order_by("-display_order"), 1):
            PillarResult.objects.create(
                assessment_result=result,
                pillar=pillar,
                score=Decimal(index * 10),
                band=(
                    "PRIORIDADE"
                    if index < 4
                    else "ATENÇÃO"
                    if index < 7
                    else "BOM"
                    if index < 9
                    else "EXCELENTE"
                ),
            )
        self.assessment.status = Assessment.Status.COMPLETED
        self.assessment.completed_at = timezone.now()
        self.assessment.save()
        return result

    def test_missing_result_and_in_progress_fail_safely(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        result = AssessmentResult.objects.create(
            assessment=self.assessment,
            overall_score=Decimal("63.25"),
            overall_band="ATENÇÃO",
            scoring_version="test-result",
        )
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assessment.status = Assessment.Status.COMPLETED
        self.assessment.completed_at = timezone.now()
        self.assessment.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(result.pillars.count(), 0)

    def test_persisted_result_and_nine_ordered_pillars(self):
        result = self.persist_result()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mapa de Qualidade de Vida")
        self.assertEqual(response.context["result"], result)
        self.assertEqual(response.context["result"].overall_score, Decimal("63.25"))
        self.assertEqual(response.context["result"].overall_band, "ATENÇÃO")
        expected = list(
            result.pillars.select_related("pillar").order_by("pillar__display_order")
        )
        self.assertEqual(
            [item.pk for item in response.context["pillars"]],
            [item.pk for item in expected],
        )
        for shown, stored in zip(response.context["pillars"], expected, strict=True):
            self.assertEqual((shown.score, shown.band), (stored.score, stored.band))
        content = response.content.decode()
        self.assertEqual(content.count('class="heart-segment"'), 9)
        self.assertEqual(content.count('class="pillar-row"'), 9)
        self.assertIn('role="img" aria-labelledby="heart-title heart-desc"', content)
        self.assertIn(localize(result.overall_score), content)
        self.assertIn("ATENÇÃO", content)
        self.client.get(self.url)
        result.refresh_from_db()
        self.assessment.refresh_from_db()
        self.assertEqual(result.overall_score, Decimal("63.25"))
        self.assertEqual(self.assessment.status, Assessment.Status.COMPLETED)
        self.assertEqual(result.pillars.count(), 9)

    def test_owner_only_and_active_tenant(self):
        self.persist_result()
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.owner)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.other_org.pk
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
