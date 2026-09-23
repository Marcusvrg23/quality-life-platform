"""TEST ONLY — NOT PRODUCTION CONTENT. PostgreSQL assessment reference cases."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from assessments.models import (
    Answer,
    Assessment,
    AssessmentResult,
    Pillar,
    PillarResult,
    Question,
    QuestionnairePillar,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import (
    calculate_assessment_scores,
    canonical_score,
    classify_score,
    complete_assessment,
    publish_questionnaire,
    record_answer,
    start_assessment,
)
from identity.models import Membership, Organization

User = get_user_model()
D = Decimal


class AssessmentCoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="a@example.com", password="test-password"
        )
        self.other = User.objects.create_user(
            email="b@example.com", password="test-password"
        )
        self.org_a = Organization.objects.create(name="A", slug="a")
        self.org_b = Organization.objects.create(name="B", slug="b")
        self.member_a = Membership.objects.create(
            user=self.user, organization=self.org_a, role=Membership.Role.COLLABORATOR
        )
        self.member_b = Membership.objects.create(
            user=self.other, organization=self.org_b, role=Membership.Role.COLLABORATOR
        )
        self.questionnaire = self.make_version(1)

    def make_version(self, version):
        return QuestionnaireVersion.objects.create(
            code="test-only",
            version=version,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-v1",
        )

    def add_question(
        self,
        questionnaire,
        pillar_index,
        code,
        *,
        pillar_weight="1",
        question_weight="1",
        direction="NORMAL",
        required=True,
        scorable=True,
    ):
        pillar = Pillar.objects.get(display_order=pillar_index)
        configured, _ = QuestionnairePillar.objects.get_or_create(
            questionnaire=questionnaire,
            pillar=pillar,
            defaults={"display_order": pillar_index, "weight": D(pillar_weight)},
        )
        question = Question.objects.create(
            questionnaire_pillar=configured,
            code=code,
            text="TEST ONLY — NOT PRODUCTION CONTENT",
            required=required,
            scorable=scorable,
            score_direction=direction,
            weight=D(question_weight),
            display_order=configured.questions.count() + 1,
        )
        options = {}
        for order, score in enumerate((0, 25, 100), start=1):
            options[score] = QuestionOption.objects.create(
                question=question,
                code=f"value-{score}",
                label=f"TEST ONLY {score}",
                score_value=D(score),
                display_order=order,
            )
        return question, options

    def publish(self, questionnaire=None):
        return publish_questionnaire((questionnaire or self.questionnaire).pk)

    def test_nine_approved_pillars_and_unique_codes(self):
        self.assertEqual(Pillar.objects.count(), 9)
        self.assertEqual(
            list(Pillar.objects.values_list("name", flat=True)),
            [
                "Saúde Física",
                "Comportamento Preventivo",
                "Atividade Física",
                "Alimentação e Hidratação",
                "Relacionamentos",
                "Saúde Mental e Emocional",
                "Ergonomia e Ambiente de Trabalho",
                "Sono e Recuperação",
                "Equilíbrio Vida × Trabalho",
            ],
        )
        self.assertEqual(Pillar.objects.values("code").distinct().count(), 9)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pillar.objects.create(
                code="physical_health", name="Duplicate", display_order=10
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pillar.objects.create(code="tenth", name="Tenth", display_order=10)

    def test_versioning_and_publication_validation(self):
        with self.assertRaises(ValidationError):
            QuestionnaireVersion.objects.create(
                code="bad",
                version=1,
                title="bad",
                scoring_version="test-v1",
                status=QuestionnaireVersion.Status.PUBLISHED,
            )
        with self.assertRaises(ValidationError):
            self.publish()
        self.add_question(self.questionnaire, 1, "q1")
        self.publish()
        with self.assertRaises(ValidationError):
            self.publish()
        self.assertEqual(self.make_version(2).version, 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_version(1)
        self.questionnaire.title = "tampered"
        with self.assertRaises(ValidationError):
            self.questionnaire.save()
        question = Question.objects.get(code="q1")
        question.weight = D(9)
        with self.assertRaises(ValidationError):
            question.save()
        with self.assertRaises(ValidationError):
            QuestionOption.objects.create(
                question=question,
                code="new",
                label="new",
                score_value=D(50),
                display_order=4,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Question.objects.filter(pk=question.pk).update(weight=D(8))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pillar.objects.filter(display_order=1).update(is_active=False)

    def test_normal_reverse_weights_and_persisted_results(self):
        q1, o1 = self.add_question(self.questionnaire, 1, "q1", question_weight="3")
        q2, o2 = self.add_question(self.questionnaire, 1, "q2", question_weight="1")
        q3, o3 = self.add_question(
            self.questionnaire, 2, "q3", pillar_weight="3", direction="REVERSE"
        )
        self.publish()
        assessment = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        record_answer(self.user, self.org_a, assessment.pk, q1.pk, o1[100].pk)
        record_answer(self.user, self.org_a, assessment.pk, q2.pk, o2[0].pk)
        record_answer(self.user, self.org_a, assessment.pk, q3.pk, o3[25].pk)
        first = calculate_assessment_scores(assessment)
        self.assertEqual(first, calculate_assessment_scores(assessment))
        self.assertEqual([p.score for p in first.pillars], [D("75.00"), D("75.00")])
        self.assertEqual(first.overall_score, D("75.00"))
        result = complete_assessment(self.user, self.org_a, assessment.pk)
        self.assertEqual(result.overall_score, D("75.00"))
        self.assertEqual(result.overall_band, "BOM")
        self.assertEqual(result.scoring_version, "test-v1")
        self.assertEqual(
            list(result.pillars.values_list("score", flat=True)),
            [D("75.00"), D("75.00")],
        )
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, Assessment.Status.COMPLETED)
        self.assertIsNotNone(assessment.completed_at)

    def test_pillar_weights_do_not_count_questions(self):
        q1, o1 = self.add_question(self.questionnaire, 1, "q1")
        q2, o2 = self.add_question(self.questionnaire, 1, "q2")
        q3, o3 = self.add_question(self.questionnaire, 2, "q3", pillar_weight="3")
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        for q, option in ((q1, o1[100]), (q2, o2[0]), (q3, o3[100])):
            record_answer(self.user, self.org_a, a.pk, q.pk, option.pk)
        self.assertEqual(calculate_assessment_scores(a).overall_score, D("87.50"))

    def test_equal_question_weights_reference_50(self):
        q1, o1 = self.add_question(self.questionnaire, 1, "q1")
        q2, o2 = self.add_question(self.questionnaire, 1, "q2")
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        record_answer(self.user, self.org_a, a.pk, q1.pk, o1[100].pk)
        record_answer(self.user, self.org_a, a.pk, q2.pk, o2[0].pk)
        self.assertEqual(
            complete_assessment(self.user, self.org_a, a.pk).overall_score, D("50.00")
        )

    def test_persisted_band_uses_canonical_score(self):
        q1, _ = self.add_question(self.questionnaire, 1, "q1")
        q2, _ = self.add_question(self.questionnaire, 1, "q2")
        low = QuestionOption.objects.create(
            question=q1,
            code="low",
            label="TEST ONLY",
            score_value=D("84.99"),
            display_order=4,
        )
        high = QuestionOption.objects.create(
            question=q2,
            code="high",
            label="TEST ONLY",
            score_value=D("85.00"),
            display_order=4,
        )
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        record_answer(self.user, self.org_a, a.pk, q1.pk, low.pk)
        record_answer(self.user, self.org_a, a.pk, q2.pk, high.pk)
        calculated = calculate_assessment_scores(a)
        self.assertEqual(calculated, calculate_assessment_scores(a))
        result = complete_assessment(self.user, self.org_a, a.pk)
        self.assertEqual(result.overall_score, D("85.00"))
        self.assertEqual(result.overall_band, "EXCELENTE")
        self.assertEqual(result.overall_score, calculated.overall_score)
        self.assertEqual(result.overall_band, calculated.overall_band)
        self.assertEqual(classify_score(result.overall_score), result.overall_band)
        for pillar in result.pillars.all():
            self.assertEqual(pillar.score, D("85.00"))
            self.assertEqual(classify_score(pillar.score), pillar.band)

    def test_overall_and_pillars_use_same_canonical_policy(self):
        q1, _ = self.add_question(self.questionnaire, 1, "q1")
        q2, _ = self.add_question(self.questionnaire, 2, "q2")
        low = QuestionOption.objects.create(
            question=q1,
            code="low",
            label="TEST ONLY",
            score_value=D("84.99"),
            display_order=4,
        )
        high = QuestionOption.objects.create(
            question=q2,
            code="high",
            label="TEST ONLY",
            score_value=D("85.00"),
            display_order=4,
        )
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        record_answer(self.user, self.org_a, a.pk, q1.pk, low.pk)
        record_answer(self.user, self.org_a, a.pk, q2.pk, high.pk)
        result = complete_assessment(self.user, self.org_a, a.pk)
        self.assertEqual(
            (result.overall_score, result.overall_band), (D("85.00"), "EXCELENTE")
        )
        self.assertEqual(classify_score(result.overall_score), result.overall_band)
        self.assertEqual(
            list(
                result.pillars.order_by("pillar__display_order").values_list(
                    "score", "band"
                )
            ),
            [(D("84.99"), "BOM"), (D("85.00"), "EXCELENTE")],
        )
        for pillar in result.pillars.all():
            self.assertEqual(classify_score(pillar.score), pillar.band)

    def test_non_scorable_optional_and_required(self):
        scored, options = self.add_question(self.questionnaire, 1, "scored")
        context, context_options = self.add_question(
            self.questionnaire, 1, "context", scorable=False
        )
        optional, _ = self.add_question(
            self.questionnaire, 1, "optional", required=False
        )
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        record_answer(self.user, self.org_a, a.pk, scored.pk, options[100].pk)
        with self.assertRaises(ValidationError):
            complete_assessment(self.user, self.org_a, a.pk)
        self.assertFalse(AssessmentResult.objects.filter(assessment=a).exists())
        record_answer(self.user, self.org_a, a.pk, context.pk, context_options[0].pk)
        result = complete_assessment(self.user, self.org_a, a.pk)
        self.assertEqual(result.overall_score, D("100.00"))
        self.assertFalse(
            Answer.objects.filter(assessment=a, question=optional).exists()
        )

    def test_unanswered_optional_only_pillar_fails_explicitly(self):
        self.add_question(self.questionnaire, 1, "optional", required=False)
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        with self.assertRaises(ValidationError):
            complete_assessment(self.user, self.org_a, a.pk)
        self.assertFalse(AssessmentResult.objects.filter(assessment=a).exists())

    def test_wrong_question_option_version_and_duplicate_answer(self):
        q1, o1 = self.add_question(self.questionnaire, 1, "q1")
        q2, o2 = self.add_question(self.questionnaire, 1, "q2")
        self.publish()
        new_version = self.make_version(2)
        other_q, other_o = self.add_question(new_version, 1, "q1")
        self.publish(new_version)
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        for q, option in ((q1, o2[0]), (other_q, other_o[0])):
            with self.assertRaises(ValidationError):
                record_answer(self.user, self.org_a, a.pk, q.pk, option.pk)
        record_answer(self.user, self.org_a, a.pk, q1.pk, o1[0].pk)
        with self.assertRaises(ValidationError):
            Answer.objects.create(assessment=a, question=q2, selected_option=o1[0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.bulk_create(
                [Answer(assessment=a, question=q1, selected_option=o1[100])]
            )

    def test_completed_immutability_and_old_version_survives_new_version(self):
        q, options = self.add_question(self.questionnaire, 1, "q")
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        answer = record_answer(self.user, self.org_a, a.pk, q.pk, options[100].pk)
        result = complete_assessment(self.user, self.org_a, a.pk)
        new_version = self.make_version(2)
        self.add_question(new_version, 1, "q")
        self.publish(new_version)
        self.assertEqual(
            AssessmentResult.objects.get(pk=result.pk).overall_score, D("100.00")
        )
        with self.assertRaises(ValidationError):
            record_answer(self.user, self.org_a, a.pk, q.pk, options[0].pk)
        with self.assertRaises(ValidationError):
            answer.delete()
        answer.selected_option = options[0]
        with self.assertRaises(ValidationError):
            answer.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.filter(pk=answer.pk).update(selected_option=options[0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.filter(pk=answer.pk).delete()
        a.user = self.other
        with self.assertRaises(ValidationError):
            a.save()
        result.overall_score = D(0)
        with self.assertRaises(ValidationError):
            result.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssessmentResult.objects.filter(pk=result.pk).update(overall_score=D(0))
        pillar_result = result.pillars.get()
        with self.assertRaises(ValidationError):
            pillar_result.delete()

    def test_completion_rolls_back_partial_result(self):
        q, options = self.add_question(self.questionnaire, 1, "q")
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        record_answer(self.user, self.org_a, a.pk, q.pk, options[100].pk)
        with (
            patch.object(
                PillarResult.objects, "create", side_effect=RuntimeError("failure")
            ),
            self.assertRaises(RuntimeError),
        ):
            complete_assessment(self.user, self.org_a, a.pk)
        self.assertFalse(AssessmentResult.objects.filter(assessment=a).exists())
        a.refresh_from_db()
        self.assertEqual(a.status, Assessment.Status.IN_PROGRESS)

    def test_tenant_and_owner_authorization(self):
        q, options = self.add_question(self.questionnaire, 1, "q")
        self.publish()
        with self.assertRaises(PermissionDenied):
            start_assessment(self.user, self.org_b, self.questionnaire.pk)
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        for operation in (
            lambda: record_answer(self.other, self.org_b, a.pk, q.pk, options[100].pk),
            lambda: complete_assessment(self.other, self.org_b, a.pk),
        ):
            with self.assertRaises(PermissionDenied):
                operation()
        self.member_a.is_active = False
        self.member_a.save()
        for operation in (
            lambda: start_assessment(self.user, self.org_a, self.questionnaire.pk),
            lambda: record_answer(self.user, self.org_a, a.pk, q.pk, options[100].pk),
            lambda: complete_assessment(self.user, self.org_a, a.pk),
        ):
            with self.assertRaises(PermissionDenied):
                operation()
        self.member_a.is_active = True
        self.member_a.save()
        self.org_a.is_active = False
        self.org_a.save()
        with self.assertRaises(PermissionDenied):
            complete_assessment(self.user, self.org_a, a.pk)

    def test_same_user_two_memberships_cannot_switch_assessment_tenant(self):
        Membership.objects.create(
            user=self.user, organization=self.org_b, role=Membership.Role.COLLABORATOR
        )
        q, options = self.add_question(self.questionnaire, 1, "q")
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        b = start_assessment(self.user, self.org_b, self.questionnaire.pk)
        with self.assertRaises(PermissionDenied):
            record_answer(self.user, self.org_b, a.pk, q.pk, options[0].pk)
        with self.assertRaises(PermissionDenied):
            complete_assessment(self.user, self.org_b, a.pk)
        record_answer(self.user, self.org_a, a.pk, q.pk, options[0].pk)
        record_answer(self.user, self.org_b, b.pk, q.pk, options[100].pk)
        self.assertEqual(
            complete_assessment(self.user, self.org_a, a.pk).overall_score, D(0)
        )
        self.assertEqual(
            complete_assessment(self.user, self.org_b, b.pk).overall_score, D(100)
        )
        self.member_a.is_active = False
        self.member_a.save()
        with self.assertRaises(PermissionDenied):
            complete_assessment(self.user, self.org_a, a.pk)

    def test_database_constraints(self):
        q, options = self.add_question(self.questionnaire, 1, "q")
        for model, fields in (
            (
                QuestionOption,
                {
                    "question": q,
                    "code": "bad",
                    "label": "bad",
                    "score_value": D(101),
                    "display_order": 4,
                },
            ),
            (
                Question,
                {
                    "questionnaire_pillar": q.questionnaire_pillar,
                    "code": "bad",
                    "text": "bad",
                    "weight": D(0),
                    "display_order": 2,
                },
            ),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.bulk_create([model(**fields)])
        self.publish()
        a = start_assessment(self.user, self.org_a, self.questionnaire.pk)
        record_answer(self.user, self.org_a, a.pk, q.pk, options[100].pk)
        result = complete_assessment(self.user, self.org_a, a.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssessmentResult.objects.filter(pk=result.pk).update(overall_score=D(101))


class ScoreBandTests(TestCase):
    def test_official_boundaries(self):
        cases = (
            ("0", "PRIORIDADE"),
            ("39.99", "PRIORIDADE"),
            ("40", "ATENÇÃO"),
            ("69.99", "ATENÇÃO"),
            ("70", "BOM"),
            ("84.99", "BOM"),
            ("85", "EXCELENTE"),
            ("100", "EXCELENTE"),
        )
        for score, band in cases:
            with self.subTest(score=score):
                self.assertEqual(classify_score(D(score)), band)
        for score in ("-0.01", "100.01", "NaN"):
            with self.assertRaises(ValidationError):
                classify_score(D(score))

    def test_canonical_quantization_at_band_boundaries(self):
        cases = (
            ("39.994", "39.99", "PRIORIDADE"),
            ("39.995", "40.00", "ATENÇÃO"),
            ("40.00", "40.00", "ATENÇÃO"),
            ("69.994", "69.99", "ATENÇÃO"),
            ("69.995", "70.00", "BOM"),
            ("70.00", "70.00", "BOM"),
            ("84.99", "84.99", "BOM"),
            ("84.994", "84.99", "BOM"),
            ("84.995", "85.00", "EXCELENTE"),
            ("84.999", "85.00", "EXCELENTE"),
            ("85.00", "85.00", "EXCELENTE"),
        )
        for raw, expected_score, expected_band in cases:
            with self.subTest(raw=raw):
                persisted_score = canonical_score(D(raw))
                self.assertEqual(persisted_score, D(expected_score))
                self.assertEqual(classify_score(persisted_score), expected_band)
