"""Non-scoring options on PostgreSQL."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from assessments.models import (
    Pillar,
    Question,
    QuestionnairePillar,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import (
    calculate_assessment_scores,
    complete_assessment,
    publish_questionnaire,
    record_answer,
    start_assessment,
)
from identity.models import Membership, Organization

D = Decimal


def make_member():
    user = get_user_model().objects.create_user(
        email="colaborador@example.com", password="test-password"
    )
    organization = Organization.objects.create(name="Empresa", slug="empresa")
    Membership.objects.create(
        user=user, organization=organization, role=Membership.Role.COLLABORATOR
    )
    return user, organization


class NonScoringOptionTests(TestCase):
    """TEST ONLY — NOT PRODUCTION CONTENT."""

    def setUp(self):
        self.questionnaire = QuestionnaireVersion.objects.create(
            code="test-only",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-v1",
        )
        self.configured = QuestionnairePillar.objects.create(
            questionnaire=self.questionnaire,
            pillar=Pillar.objects.get(display_order=1),
            display_order=1,
            weight=D(1),
        )

    def add_question(self, code, options, *, required=True):
        question = Question.objects.create(
            questionnaire_pillar=self.configured,
            code=code,
            text="TEST ONLY — NOT PRODUCTION CONTENT",
            required=required,
            weight=D(1),
            display_order=self.configured.questions.count() + 1,
        )
        created = {}
        for order, (option_code, score, counts) in enumerate(options, start=1):
            created[option_code] = QuestionOption.objects.create(
                question=question,
                code=option_code,
                label=f"TEST ONLY {option_code}",
                score_value=D(score),
                counts_for_score=counts,
                display_order=order,
            )
        return question, created

    def assert_publication_rejected(self):
        with self.assertRaises(ValidationError):
            publish_questionnaire(self.questionnaire.pk)
        self.questionnaire.refresh_from_db()
        self.assertEqual(self.questionnaire.status, QuestionnaireVersion.Status.DRAFT)

    def test_non_scoring_answer_does_not_change_pillar_score(self):
        safe, safe_options = self.add_question(
            "safe", (("low", 0, True), ("high", 100, True))
        )
        unsure, unsure_options = self.add_question(
            "unsure", (("low", 0, True), ("high", 100, True), ("nao-sei", 0, False))
        )
        publish_questionnaire(self.questionnaire.pk)
        user, organization = make_member()
        assessment = start_assessment(user, organization, self.questionnaire.pk)
        record_answer(
            user, organization, assessment.pk, safe.pk, safe_options["high"].pk
        )
        record_answer(
            user, organization, assessment.pk, unsure.pk, unsure_options["nao-sei"].pk
        )
        calculated = calculate_assessment_scores(assessment)
        self.assertEqual([p.score for p in calculated.pillars], [D("100.00")])
        self.assertEqual(calculated.overall_score, D("100.00"))
        result = complete_assessment(user, organization, assessment.pk)
        self.assertEqual(result.overall_score, D("100.00"))
        self.assertEqual(result.pillars.get().score, D("100.00"))

    def test_rejects_scorable_question_without_scoring_option(self):
        self.add_question("safe", (("low", 0, True), ("high", 100, True)))
        self.add_question("only-unsure", (("nao-sei", 0, False),))
        self.assert_publication_rejected()

    def test_rejects_pillar_without_safe_required_question(self):
        self.add_question(
            "unsure", (("low", 0, True), ("high", 100, True), ("nao-sei", 0, False))
        )
        self.add_question(
            "optional", (("low", 0, True), ("high", 100, True)), required=False
        )
        self.assert_publication_rejected()
