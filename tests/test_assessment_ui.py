"""TEST ONLY — NOT PRODUCTION CONTENT. Assessment UI integration cases."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from assessments.models import (
    Answer,
    Assessment,
    AssessmentResult,
    Pillar,
    Question,
    QuestionnairePillar,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import publish_questionnaire
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization

User = get_user_model()


class AssessmentUITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="ui@example.test", password="test-pass"
        )
        self.other = User.objects.create_user(
            email="other@example.test", password="test-pass"
        )
        self.org = Organization.objects.create(
            name="Test Organization", slug="test-org"
        )
        self.other_org = Organization.objects.create(
            name="Other Test", slug="other-test"
        )
        self.membership = Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.COLLABORATOR
        )
        Membership.objects.create(
            user=self.other, organization=self.org, role=Membership.Role.COLLABORATOR
        )
        self.client.force_login(self.user)

    def fixture(self, version=1):
        questionnaire = QuestionnaireVersion.objects.create(
            code="test-only-ui",
            version=version,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-ui",
        )
        configured = QuestionnairePillar.objects.create(
            questionnaire=questionnaire,
            pillar=Pillar.objects.get(display_order=1),
            display_order=1,
            weight=Decimal(1),
        )
        required = Question.objects.create(
            questionnaire_pillar=configured,
            code="required",
            text="TEST ONLY — required question?",
            weight=Decimal(1),
            display_order=1,
        )
        optional = Question.objects.create(
            questionnaire_pillar=configured,
            code="optional",
            text="TEST ONLY — optional question?",
            weight=Decimal(1),
            display_order=2,
            required=False,
        )
        options = []
        for question in (required, optional):
            for order, score in enumerate((0, 100), 1):
                options.append(
                    QuestionOption.objects.create(
                        question=question,
                        code=f"test-{score}",
                        label=f"TEST ONLY choice {order}",
                        score_value=Decimal(score),
                        display_order=order,
                    )
                )
        publish_questionnaire(questionnaire.pk)
        return questionnaire, required, optional, options

    def start(self):
        response = self.client.post(reverse("assessment_start"))
        self.assertEqual(response.status_code, 302)
        return Assessment.objects.get(user=self.user)

    def test_anonymous_and_invalid_tenant(self):
        self.client.logout()
        for route in ("assessment_hub", "assessment_start"):
            response = (
                self.client.post(reverse(route))
                if route.endswith("start")
                else self.client.get(reverse(route))
            )
            self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.get(reverse("assessment_hub")).status_code, 403)

    def test_anonymous_assessment_routes_redirect(self):
        _, required, _, _ = self.fixture()
        assessment = self.start()
        self.client.logout()
        for name in (
            "assessment_detail",
            "assessment_review",
            "assessment_completed",
        ):
            self.assertEqual(
                self.client.get(reverse(name, args=[assessment.pk])).status_code, 302
            )
        url = reverse("assessment_question", args=[assessment.pk, required.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(
            self.client.post(
                reverse("assessment_complete", args=[assessment.pk])
            ).status_code,
            302,
        )

    def test_empty_multiple_and_start_post_only(self):
        self.assertContains(
            self.client.get(reverse("assessment_hub")), "ainda não está disponível"
        )
        self.assertEqual(self.client.get(reverse("assessment_start")).status_code, 405)
        self.fixture()
        self.assertContains(
            self.client.get(reverse("assessment_hub")), "Iniciar avaliação"
        )
        self.fixture(2)
        self.assertContains(self.client.get(reverse("assessment_hub")), "configuração")
        self.client.post(reverse("assessment_start"))
        self.assertFalse(Assessment.objects.exists())

    def test_non_collaborator_cannot_use_assessment(self):
        self.fixture()
        self.membership.role = Membership.Role.CORPORATE_MANAGER
        self.membership.save()
        self.assertEqual(self.client.get(reverse("assessment_hub")).status_code, 403)
        self.assertEqual(self.client.post(reverse("assessment_start")).status_code, 403)
        self.assertFalse(Assessment.objects.exists())

    def test_start_resume_persist_change_review_complete(self):
        _, required, optional, options = self.fixture()
        assessment = self.start()
        self.assertContains(
            self.client.get(reverse("assessment_hub")), "Retomar avaliação"
        )
        question_url = reverse("assessment_question", args=[assessment.pk, required.pk])
        response = self.client.post(question_url, {"option": options[0].pk})
        self.assertRedirects(
            response, reverse("assessment_question", args=[assessment.pk, optional.pk])
        )
        self.assertContains(self.client.get(question_url), "checked")
        self.client.post(
            question_url, {"option": options[1].pk, "destination": "review"}
        )
        answer = Answer.objects.get(assessment=assessment, question=required)
        self.assertEqual(answer.selected_option, options[1])
        review_url = reverse("assessment_review", args=[assessment.pk])
        self.assertContains(self.client.get(review_url), "Opcional sem resposta")
        self.assertNotContains(self.client.get(review_url), "score_value")
        self.assertEqual(
            self.client.get(
                reverse("assessment_complete", args=[assessment.pk])
            ).status_code,
            405,
        )
        response = self.client.post(
            reverse("assessment_complete", args=[assessment.pk])
        )
        self.assertRedirects(
            response,
            reverse("assessment_completed", args=[assessment.pk]),
            fetch_redirect_response=False,
        )
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, Assessment.Status.COMPLETED)
        self.assertEqual(
            AssessmentResult.objects.filter(assessment=assessment).count(), 1
        )
        self.client.post(reverse("assessment_complete", args=[assessment.pk]))
        self.client.get(reverse("assessment_completed", args=[assessment.pk]))
        self.assertEqual(
            AssessmentResult.objects.filter(assessment=assessment).count(), 1
        )
        self.assertEqual(
            Answer.objects.get(assessment=assessment).selected_option, options[1]
        )
        self.assertRedirects(
            self.client.get(question_url),
            reverse("assessment_completed", args=[assessment.pk]),
        )
        self.client.post(question_url, {"option": options[0].pk})
        self.assertEqual(
            Answer.objects.get(assessment=assessment).selected_option, options[1]
        )

    def test_required_missing_and_invalid_question_option(self):
        _, required, _, options = self.fixture()
        assessment = self.start()
        complete_url = reverse("assessment_complete", args=[assessment.pk])
        self.client.post(complete_url)
        self.assertEqual(assessment.answers.count(), 0)
        self.assertFalse(AssessmentResult.objects.exists())
        self.assertContains(
            self.client.get(
                reverse("assessment_review", args=[assessment.pk]) + "?incomplete=1"
            ),
            "Obrigatória sem resposta",
        )
        wrong_url = reverse("assessment_question", args=[assessment.pk, 999999])
        self.assertEqual(self.client.get(wrong_url).status_code, 404)
        url = reverse("assessment_question", args=[assessment.pk, required.pk])
        self.assertContains(
            self.client.post(url, {"option": options[2].pk}), "Resposta inválida"
        )
        self.assertFalse(Answer.objects.exists())
        self.client.post(url, {"option": options[0].pk})
        self.assertEqual(Answer.objects.count(), 1)

    def test_question_from_another_version_is_denied(self):
        _, _, _, _ = self.fixture()
        _, wrong_question, _, wrong_options = self.fixture(2)
        assessment = Assessment.objects.create(
            user=self.user,
            organization=self.org,
            questionnaire_version=QuestionnaireVersion.objects.get(version=1),
        )
        url = reverse("assessment_question", args=[assessment.pk, wrong_question.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(url, {"option": wrong_options[0].pk}).status_code, 404
        )
        self.assertFalse(Answer.objects.exists())

    def test_cross_user_cross_tenant_and_client_authority(self):
        _, required, _, options = self.fixture()
        assessment = self.start()
        other_assessment = Assessment.objects.create(
            user=self.other,
            organization=self.org,
            questionnaire_version=assessment.questionnaire_version,
        )
        foreign_assessment = Assessment.objects.create(
            user=self.user,
            organization=self.other_org,
            questionnaire_version=assessment.questionnaire_version,
        )
        for candidate in (other_assessment, foreign_assessment):
            for name in (
                "assessment_detail",
                "assessment_review",
                "assessment_completed",
            ):
                self.assertEqual(
                    self.client.get(reverse(name, args=[candidate.pk])).status_code, 404
                )
            self.assertEqual(
                self.client.post(
                    reverse("assessment_complete", args=[candidate.pk])
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.post(
                    reverse("assessment_question", args=[candidate.pk, required.pk]),
                    {"option": options[0].pk},
                ).status_code,
                404,
            )
        self.client.post(
            reverse("assessment_question", args=[assessment.pk, required.pk]),
            {
                "option": options[0].pk,
                "user_id": self.other.pk,
                "organization_id": self.other_org.pk,
                "score": 100,
                "overall_score": 100,
                "pillar_score": 100,
                "band": "EXCELENTE",
                "weights": 10,
            },
        )
        answer = Answer.objects.get(assessment=assessment)
        self.assertEqual(answer.assessment.user, self.user)
        self.assertEqual(answer.assessment.organization, self.org)
        self.assertNotContains(
            self.client.get(reverse("assessment_review", args=[assessment.pk])),
            "EXCELENTE",
        )

    def test_stale_or_switched_tenant_and_retired_resume(self):
        questionnaire, required, _, options = self.fixture()
        assessment = self.start()
        questionnaire.status = QuestionnaireVersion.Status.RETIRED
        questionnaire.save(update_fields=["status", "updated_at"])
        self.assertContains(
            self.client.get(reverse("assessment_hub")), "Retomar avaliação"
        )
        self.client.post(
            reverse("assessment_question", args=[assessment.pk, required.pk]),
            {"option": options[0].pk},
        )
        self.assertEqual(Answer.objects.count(), 1)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.other_org.pk
        session.save()
        self.assertEqual(self.client.get(reverse("assessment_hub")).status_code, 403)

    def test_csrf(self):
        _, required, _, options = self.fixture()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(reverse("assessment_start")).status_code, 403)
        csrf_client.get(reverse("assessment_hub"))
        self.assertEqual(csrf_client.post(reverse("assessment_start")).status_code, 403)
        assessment = self.start()
        self.assertEqual(
            csrf_client.post(
                reverse("assessment_question", args=[assessment.pk, required.pk]),
                {"option": options[0].pk},
            ).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(
                reverse("assessment_complete", args=[assessment.pk])
            ).status_code,
            403,
        )
