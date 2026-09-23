"""Authorized, deterministic assessment operations. No client supplied scores."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from config.tenant import require_active_membership

from .models import (
    Answer,
    Assessment,
    AssessmentResult,
    PillarResult,
    Question,
    QuestionnaireVersion,
)

HUNDRED = Decimal(100)
CENT = Decimal("0.01")


def classify_score(score):
    score = Decimal(score)
    if not score.is_finite() or score < 0 or score > HUNDRED:
        raise ValidationError("Score must be between 0 and 100.")
    if score < 40:
        return "PRIORIDADE"
    if score < 70:
        return "ATENÇÃO"
    if score < 85:
        return "BOM"
    return "EXCELENTE"


def _rounded(score):
    return score.quantize(CENT, rounding=ROUND_HALF_UP)


def validate_questionnaire(questionnaire):
    """Reject incomplete scoring configuration before publication or completion."""
    pillars = list(
        questionnaire.pillars.filter(is_active=True)
        .select_related("pillar")
        .prefetch_related("questions__options")
    )
    if not pillars:
        raise ValidationError("Questionnaire needs active pillars.")
    for configured in pillars:
        if not configured.pillar.is_active or configured.weight <= 0:
            raise ValidationError("Scored pillar must be active with positive weight.")
        questions = [q for q in configured.questions.all() if q.is_active]
        if not questions:
            raise ValidationError("Active pillar needs questions.")
        if not any(q.scorable for q in questions):
            raise ValidationError("Active pillar needs a scorable question.")
        for question in questions:
            if question.scorable and question.weight <= 0:
                raise ValidationError("Scorable question needs positive weight.")
            if not list(question.options.all()):
                raise ValidationError("Active question needs options.")


@transaction.atomic
def publish_questionnaire(questionnaire_id):
    questionnaire = QuestionnaireVersion.objects.select_for_update().get(
        pk=questionnaire_id
    )
    if questionnaire.status != QuestionnaireVersion.Status.DRAFT:
        raise ValidationError("Only drafts may be published.")
    validate_questionnaire(questionnaire)
    questionnaire.status = QuestionnaireVersion.Status.PUBLISHED
    questionnaire.save(update_fields=["status", "updated_at"])
    return questionnaire


def _authorized_assessment(user, organization, assessment_id, *, lock=False):
    require_active_membership(user, organization)
    organization_id = getattr(organization, "pk", organization)
    queryset = Assessment.objects.select_related(
        "organization", "questionnaire_version"
    )
    if lock:
        queryset = queryset.select_for_update()
    assessment = queryset.filter(
        pk=assessment_id, user=user, organization_id=organization_id
    ).first()
    if assessment is None:
        raise PermissionDenied("Assessment unavailable.")
    return assessment


@transaction.atomic
def start_assessment(user, organization, questionnaire_id):
    require_active_membership(user, organization)
    questionnaire = QuestionnaireVersion.objects.filter(
        pk=questionnaire_id, status=QuestionnaireVersion.Status.PUBLISHED
    ).first()
    if questionnaire is None:
        raise ValidationError("Published questionnaire unavailable.")
    validate_questionnaire(questionnaire)
    return Assessment.objects.create(
        user=user,
        organization_id=getattr(organization, "pk", organization),
        questionnaire_version=questionnaire,
    )


@transaction.atomic
def record_answer(user, organization, assessment_id, question_id, option_id):
    assessment = _authorized_assessment(user, organization, assessment_id, lock=True)
    if assessment.status != Assessment.Status.IN_PROGRESS:
        raise ValidationError("Assessment is completed.")
    question = Question.objects.filter(
        pk=question_id,
        questionnaire_pillar__questionnaire=assessment.questionnaire_version,
        questionnaire_pillar__is_active=True,
        is_active=True,
    ).first()
    if question is None:
        raise ValidationError("Question unavailable for this assessment.")
    option = question.options.filter(pk=option_id).first()
    if option is None:
        raise ValidationError("Option unavailable for this question.")
    answer, _ = Answer.objects.update_or_create(
        assessment=assessment,
        question=question,
        defaults={"selected_option": option, "answered_at": timezone.now()},
    )
    return answer


@dataclass(frozen=True)
class CalculatedPillar:
    pillar_id: int
    score: Decimal
    band: str


@dataclass(frozen=True)
class CalculatedScores:
    overall_score: Decimal
    overall_band: str
    pillars: tuple[CalculatedPillar, ...]


def calculate_assessment_scores(assessment):
    """Pure calculation over validated persisted answers; classification uses raw scores."""
    questionnaire = assessment.questionnaire_version
    validate_questionnaire(questionnaire)
    configured_pillars = list(
        questionnaire.pillars.filter(is_active=True).prefetch_related("questions")
    )
    answers = {
        answer.question_id: answer
        for answer in assessment.answers.select_related("question", "selected_option")
    }
    valid_ids = set()
    weighted_overall = Decimal(0)
    total_pillar_weight = Decimal(0)
    results = []
    for configured in configured_pillars:
        numerator = Decimal(0)
        denominator = Decimal(0)
        for question in configured.questions.all():
            if not question.is_active:
                continue
            valid_ids.add(question.pk)
            answer = answers.get(question.pk)
            if answer is None:
                if question.required:
                    raise ValidationError("Required question is unanswered.")
                continue
            if answer.selected_option.question_id != question.pk:
                raise ValidationError("Option does not belong to question.")
            if not question.scorable:
                continue
            normalized = answer.selected_option.score_value
            if question.score_direction == Question.Direction.REVERSE:
                normalized = HUNDRED - normalized
            numerator += normalized * question.weight
            denominator += question.weight
        if denominator <= 0:
            raise ValidationError("Scored pillar has no answered scorable questions.")
        raw_score = numerator / denominator
        results.append(
            CalculatedPillar(
                configured.pillar_id, _rounded(raw_score), classify_score(raw_score)
            )
        )
        weighted_overall += raw_score * configured.weight
        total_pillar_weight += configured.weight
    if set(answers) != valid_ids.intersection(answers):
        raise ValidationError("Assessment contains an invalid question.")
    if total_pillar_weight <= 0:
        raise ValidationError("Questionnaire has no scored pillars.")
    raw_overall = weighted_overall / total_pillar_weight
    return CalculatedScores(
        _rounded(raw_overall), classify_score(raw_overall), tuple(results)
    )


@transaction.atomic
def complete_assessment(user, organization, assessment_id):
    assessment = _authorized_assessment(user, organization, assessment_id, lock=True)
    if assessment.status != Assessment.Status.IN_PROGRESS:
        raise ValidationError("Assessment is completed.")
    if assessment.questionnaire_version.status not in (
        QuestionnaireVersion.Status.PUBLISHED,
        QuestionnaireVersion.Status.RETIRED,
    ):
        raise ValidationError("Assessment questionnaire is not published.")
    scores = calculate_assessment_scores(assessment)
    result = AssessmentResult.objects.create(
        assessment=assessment,
        overall_score=scores.overall_score,
        overall_band=scores.overall_band,
        scoring_version=assessment.questionnaire_version.scoring_version,
    )
    for pillar in scores.pillars:
        PillarResult.objects.create(
            assessment_result=result,
            pillar_id=pillar.pillar_id,
            score=pillar.score,
            band=pillar.band,
        )
    assessment.status = Assessment.Status.COMPLETED
    assessment.completed_at = timezone.now()
    assessment.save(update_fields=["status", "completed_at", "updated_at"])
    return result
