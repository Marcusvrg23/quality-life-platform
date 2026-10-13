"""Authorized, deterministic assessment operations. No client supplied scores."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from config.tenant import require_active_membership

from .models import (
    Answer,
    AnswerChoice,
    Assessment,
    AssessmentResult,
    PillarResult,
    Question,
    QuestionnaireVersion,
)

HUNDRED = Decimal(100)
CENT = Decimal("0.01")
SCORED_KINDS = (Question.Kind.SINGLE, Question.Kind.SCALE)
# Identification section (v2): the name shown on the person's own map.
NAME_QUESTION_CODE = "q1-1"


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


def canonical_score(score):
    return score.quantize(CENT, rounding=ROUND_HALF_UP)


def questionnaire_questions(questionnaire):
    """Active questions of a version: in an active pillar, or only in a section."""
    return Question.objects.filter(
        Q(
            questionnaire_pillar__questionnaire=questionnaire,
            questionnaire_pillar__is_active=True,
        )
        | Q(questionnaire_pillar__isnull=True, section__questionnaire=questionnaire),
        is_active=True,
    )


def _reading_order(question):
    if question.section_id:
        return (0, question.section.display_order, question.display_order, question.pk)
    # Versions without sections (v1) are read pillar by pillar.
    pillar_order = question.questionnaire_pillar.display_order
    return (1, pillar_order, question.display_order, question.pk)


def ordered_questions(questionnaire):
    """Questions in the order of the official text."""
    questions = (
        questionnaire_questions(questionnaire)
        .select_related("section", "questionnaire_pillar__pillar")
        .prefetch_related("options")
    )
    return sorted(questions, key=_reading_order)


def _validate_question_shape(question):
    options = list(question.options.all())
    if question.kind == Question.Kind.TEXT:
        if options or not question.max_length:
            raise ValidationError("Text question needs a limit and no options.")
    elif not options:
        raise ValidationError("Active question needs options.")
    if question.scorable and (
        question.questionnaire_pillar_id is None or question.kind not in SCORED_KINDS
    ):
        raise ValidationError(
            "Only single choice or scale questions in a pillar score."
        )
    if question.scorable and question.section_id and not question.section.is_scored:
        raise ValidationError("Unscored section cannot hold scorable questions.")
    if question.kind != Question.Kind.MULTIPLE and any(o.exclusive for o in options):
        raise ValidationError("Only multiple choice has exclusive options.")
    if question.kind != Question.Kind.SINGLE and any(o.requires_text for o in options):
        raise ValidationError("Only single choice options may ask for text.")


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
            options = list(question.options.all())
            if not options and question.kind != Question.Kind.TEXT:
                raise ValidationError("Active question needs options.")
            if question.scorable and not any(o.counts_for_score for o in options):
                raise ValidationError("Scorable question needs a scoring option.")
        if not any(
            q.required
            and q.scorable
            and all(o.counts_for_score for o in q.options.all())
            for q in questions
        ):
            raise ValidationError(
                "Active pillar needs a required question whose options all score."
            )
    for question in (
        questionnaire_questions(questionnaire)
        .select_related("section")
        .prefetch_related("options")
    ):
        _validate_question_shape(question)


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


def _answer_error(message, code):
    return ValidationError(message, code=code)


@transaction.atomic
def record_answer(
    user,
    organization,
    assessment_id,
    question_id,
    option_id=None,
    *,
    option_ids=None,
    text=None,
):
    """Save one answer of any kind. An empty answer clears an optional question."""
    assessment = _authorized_assessment(user, organization, assessment_id, lock=True)
    if assessment.status != Assessment.Status.IN_PROGRESS:
        raise ValidationError("Assessment is completed.")
    question = (
        questionnaire_questions(assessment.questionnaire_version)
        .filter(pk=question_id)
        .first()
    )
    if question is None:
        raise ValidationError("Question unavailable for this assessment.")
    text = (text or "").strip()
    option_ids = list(dict.fromkeys(option_ids or ()))
    if question.kind == Question.Kind.TEXT:
        empty = not text
    elif question.kind == Question.Kind.MULTIPLE:
        empty = not option_ids
    else:
        empty = option_id in (None, "")
    if empty:
        if question.required:
            raise _answer_error("Required question needs an answer.", "required")
        Answer.objects.filter(assessment=assessment, question=question).delete()
        return None
    selected = None
    choices = []
    if question.kind == Question.Kind.TEXT:
        if len(text) > question.max_length:
            raise _answer_error("Text is longer than allowed.", "too_long")
    elif question.kind == Question.Kind.MULTIPLE:
        choices = list(question.options.filter(pk__in=option_ids))
        if len(choices) != len(option_ids):
            raise _answer_error("Option unavailable for this question.", "invalid")
        if len(choices) > 1 and any(option.exclusive for option in choices):
            raise _answer_error("Exclusive option cannot be combined.", "exclusive")
        text = ""
    else:
        selected = question.options.filter(pk=option_id).first()
        if selected is None:
            raise _answer_error("Option unavailable for this question.", "invalid")
        if not selected.requires_text:
            text = ""
        elif not text:
            raise _answer_error("Option needs a description.", "needs_text")
        elif len(text) > Question.MAX_TEXT_LENGTH:
            raise _answer_error("Text is longer than allowed.", "too_long")
    answer, _ = Answer.objects.update_or_create(
        assessment=assessment,
        question=question,
        defaults={
            "selected_option": selected,
            "text_value": text,
            "answered_at": timezone.now(),
        },
    )
    answer.choices.all().delete()
    for option in choices:
        AnswerChoice.objects.create(answer=answer, option=option)
    return answer


def collaborator_name(assessment):
    """Name typed in the identification section. Shown only to its owner."""
    name = (
        assessment.answers.filter(
            question__code=NAME_QUESTION_CODE,
            question__kind=Question.Kind.TEXT,
            question__section__number=1,
            question__section__is_scored=False,
        )
        .values_list("text_value", flat=True)
        .first()
    )
    return name or ""


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


def _check_answer(question, answer):
    """A stored answer must have the shape of its question kind."""
    option = answer.selected_option
    choices = [choice.option for choice in answer.choices.all()]
    if any(item.question_id != question.pk for item in [option, *choices] if item):
        raise ValidationError("Option does not belong to question.")
    if question.kind == Question.Kind.TEXT:
        valid = (
            option is None
            and not choices
            and 0 < len(answer.text_value) <= question.max_length
        )
    elif question.kind == Question.Kind.MULTIPLE:
        valid = (
            option is None
            and bool(choices)
            and not answer.text_value
            and (len(choices) == 1 or not any(item.exclusive for item in choices))
        )
    else:
        valid = (
            option is not None
            and not choices
            and bool(answer.text_value) == option.requires_text
        )
    if not valid:
        raise ValidationError("Answer does not match its question.")


def calculate_assessment_scores(assessment):
    """Calculate with Decimal and classify the same canonical scores we persist.

    Only scorable questions inside a pillar count. Text, multiple choice and
    unscored sections are checked for completeness and never change a score.
    """
    questionnaire = assessment.questionnaire_version
    validate_questionnaire(questionnaire)
    answers = {
        answer.question_id: answer
        for answer in assessment.answers.select_related(
            "selected_option"
        ).prefetch_related("choices__option")
    }
    questions = list(questionnaire_questions(questionnaire))
    for question in questions:
        answer = answers.get(question.pk)
        if answer is None:
            if question.required:
                raise ValidationError("Required question is unanswered.")
            continue
        _check_answer(question, answer)
    if set(answers) - {question.pk for question in questions}:
        raise ValidationError("Assessment contains an invalid question.")
    configured_pillars = list(
        questionnaire.pillars.filter(is_active=True).prefetch_related("questions")
    )
    weighted_overall = Decimal(0)
    total_pillar_weight = Decimal(0)
    results = []
    for configured in configured_pillars:
        numerator = Decimal(0)
        denominator = Decimal(0)
        for question in configured.questions.all():
            answer = answers.get(question.pk)
            if not question.is_active or not question.scorable or answer is None:
                continue
            if not answer.selected_option.counts_for_score:
                continue
            normalized = answer.selected_option.score_value
            if question.score_direction == Question.Direction.REVERSE:
                normalized = HUNDRED - normalized
            numerator += normalized * question.weight
            denominator += question.weight
        if denominator <= 0:
            raise ValidationError("Scored pillar has no answered scorable questions.")
        raw_score = numerator / denominator
        pillar_score = canonical_score(raw_score)
        results.append(
            CalculatedPillar(
                configured.pillar_id, pillar_score, classify_score(pillar_score)
            )
        )
        weighted_overall += raw_score * configured.weight
        total_pillar_weight += configured.weight
    if total_pillar_weight <= 0:
        raise ValidationError("Questionnaire has no scored pillars.")
    raw_overall = weighted_overall / total_pillar_weight
    overall_score = canonical_score(raw_overall)
    return CalculatedScores(
        overall_score, classify_score(overall_score), tuple(results)
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
