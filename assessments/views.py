"""Server-rendered assessment flow backed by the M3 services."""

from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from config.tenant import resolve_tenant_context
from identity.consent import grant_consent, has_active_consent
from identity.models import Membership

from . import quality_map
from .models import Assessment, AssessmentResult, Question, QuestionnaireVersion
from .services import (
    complete_assessment,
    ordered_questions,
    record_answer,
    start_assessment,
)


def _tenant(request):
    tenant = resolve_tenant_context(request)
    if tenant is None or tenant.role != Membership.Role.COLLABORATOR:
        raise PermissionDenied("Assessment unavailable.")
    return tenant


CONSENT_REQUIRED = "Marque a autorização para usar seus dados na avaliação."


def _without_consent(request, tenant):
    """Server-side gate: no consent in this company means back to the hub."""
    if has_active_consent(request.user, tenant.organization):
        return None
    messages.error(request, CONSENT_REQUIRED)
    return redirect("assessment_hub")


def _assessment(request, tenant, assessment_id):
    assessment = (
        Assessment.objects.select_related("questionnaire_version")
        .filter(pk=assessment_id, user=request.user, organization=tenant.organization)
        .first()
    )
    if assessment is None:
        raise Http404
    return assessment


ANSWER_ERRORS = {
    "required": "Selecione uma resposta antes de salvar.",
    "needs_text": "Descreva a opção “Outro:” antes de salvar.",
    "too_long": "Sua resposta passou do limite de caracteres.",
}
TEXT_REQUIRED = "Escreva sua resposta antes de salvar."
INVALID_ANSWER = "Resposta inválida. Escolha uma das alternativas desta pergunta."


def _flow(assessment):
    questions = ordered_questions(assessment.questionnaire_version)
    answers = {
        answer.question_id: answer
        for answer in assessment.answers.select_related(
            "selected_option"
        ).prefetch_related("choices__option")
    }
    answered = sum(question.pk in answers for question in questions)
    return questions, answers, answered


def _summary(answer):
    """What the person answered, in words. Only ever shown to that person."""
    if answer.selected_option is None:
        choices = sorted(
            answer.choices.all(), key=lambda choice: choice.option.display_order
        )
        return ", ".join(choice.option.label for choice in choices) or (
            answer.text_value
        )
    if answer.text_value:
        return f"{answer.selected_option.label} {answer.text_value}"
    return answer.selected_option.label


def _answer_error(error, question):
    code = getattr(error, "code", None)
    if code == "required" and question.kind == Question.Kind.TEXT:
        return TEXT_REQUIRED
    if code == "exclusive":
        label = next(o.label for o in question.options.all() if o.exclusive)
        return f"“{label}” não pode ser marcada junto com outras opções."
    return ANSWER_ERRORS.get(code, INVALID_ANSWER)


@login_required
@require_GET
def hub(request):
    tenant = _tenant(request)
    assessments = Assessment.objects.filter(
        user=request.user, organization=tenant.organization
    ).select_related("questionnaire_version")
    current = (
        assessments.filter(status=Assessment.Status.IN_PROGRESS)
        .order_by("-started_at", "-pk")
        .first()
    )
    latest_completed = (
        assessments.filter(status=Assessment.Status.COMPLETED)
        .order_by("-completed_at", "-pk")
        .first()
    )
    published_count = QuestionnaireVersion.objects.filter(
        status=QuestionnaireVersion.Status.PUBLISHED
    ).count()
    return render(
        request,
        "assessments/hub.html",
        {
            "tenant": tenant,
            "has_consent": has_active_consent(request.user, tenant.organization),
            "current": current,
            "latest_completed": latest_completed,
            "available": not current and not latest_completed and published_count == 1,
            "multiple": not current and not latest_completed and published_count > 1,
        },
    )


@login_required
@require_POST
def start(request):
    tenant = _tenant(request)
    # Lock the user row so parallel submissions cannot create two current assessments.
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        consented = has_active_consent(request.user, tenant.organization)
        if not consented and request.POST.get("consent") != "on":
            messages.error(request, CONSENT_REQUIRED)
            return redirect("assessment_hub")
        own = Assessment.objects.filter(
            user=request.user, organization=tenant.organization
        )
        existing = (
            own.filter(status=Assessment.Status.IN_PROGRESS)
            .order_by("-started_at", "-pk")
            .first()
            or own.filter(status=Assessment.Status.COMPLETED)
            .order_by("-completed_at", "-pk")
            .first()
        )
        if existing:
            if not consented:
                grant_consent(request.user, tenant.organization)
            return redirect("assessment_detail", assessment_id=existing.pk)
        versions = list(
            QuestionnaireVersion.objects.filter(
                status=QuestionnaireVersion.Status.PUBLISHED
            )[:2]
        )
        if len(versions) != 1:
            return redirect("assessment_hub")
        try:
            if not consented:
                grant_consent(request.user, tenant.organization)
            assessment = start_assessment(
                request.user, tenant.organization, versions[0].pk
            )
        except ValidationError:
            # Consent and assessment are one unit: neither survives a failed start.
            transaction.set_rollback(True)
            return redirect("assessment_hub")
    return redirect("assessment_detail", assessment_id=assessment.pk)


@login_required
@require_GET
def detail(request, assessment_id):
    tenant = _tenant(request)
    assessment = _assessment(request, tenant, assessment_id)
    if assessment.status == Assessment.Status.COMPLETED:
        return redirect("assessment_completed", assessment_id=assessment.pk)
    questions, answers, _ = _flow(assessment)
    if not questions:
        return render(
            request,
            "assessments/unavailable.html",
            {"tenant": tenant},
            status=409,
        )
    next_question = next((q for q in questions if q.pk not in answers), questions[0])
    return redirect(
        "assessment_question", assessment_id=assessment.pk, question_id=next_question.pk
    )


@login_required
@require_http_methods(["GET", "POST"])
def question(request, assessment_id, question_id):
    tenant = _tenant(request)
    if blocked := _without_consent(request, tenant):
        return blocked
    assessment = _assessment(request, tenant, assessment_id)
    if assessment.status == Assessment.Status.COMPLETED:
        return redirect("assessment_completed", assessment_id=assessment.pk)
    questions, answers, answered = _flow(assessment)
    position = next((i for i, q in enumerate(questions) if q.pk == question_id), None)
    if position is None:
        raise Http404
    current = questions[position]
    previous = questions[position - 1] if position else None
    following = questions[position + 1] if position + 1 < len(questions) else None
    answer = answers.get(question_id)
    selected_ids = set()
    text_value = ""
    if answer is not None:
        selected_ids = {choice.option_id for choice in answer.choices.all()}
        selected_ids.add(answer.selected_option_id)
        text_value = answer.text_value
    error = None
    if request.method == "POST":
        option_ids = request.POST.getlist("options")
        selected_ids = set(option_ids) | {request.POST.get("option")}
        text_value = request.POST.get(
            "text" if current.kind == Question.Kind.TEXT else "other_text", ""
        )
        try:
            record_answer(
                request.user,
                tenant.organization,
                assessment.pk,
                current.pk,
                request.POST.get("option") or None,
                option_ids=option_ids,
                text=text_value,
            )
        except ValidationError as exc:
            error = _answer_error(exc, current)
        except (ValueError, OverflowError):
            error = INVALID_ANSWER
        if error is None:
            destination = request.POST.get("destination")
            if destination == "review" or following is None:
                return redirect("assessment_review", assessment_id=assessment.pk)
            return redirect(
                "assessment_question",
                assessment_id=assessment.pk,
                question_id=following.pk,
            )
    return render(
        request,
        "assessments/question.html",
        {
            "tenant": tenant,
            "assessment": assessment,
            "question": current,
            "selected_ids": {int(v) for v in selected_ids if str(v).isdigit()},
            "text_value": text_value,
            # Identification fields are one line; other open answers are paragraphs.
            "multiline": current.section is None or current.section.number != 1,
            "previous": previous,
            "following": following,
            "position": position + 1,
            "total": len(questions),
            "answered": answered,
            "error": error,
        },
    )


@login_required
@require_GET
def review(request, assessment_id):
    tenant = _tenant(request)
    if blocked := _without_consent(request, tenant):
        return blocked
    assessment = _assessment(request, tenant, assessment_id)
    if assessment.status == Assessment.Status.COMPLETED:
        return redirect("assessment_completed", assessment_id=assessment.pk)
    questions, answers, answered = _flow(assessment)
    items = [
        {
            "question": question,
            "answer": answers.get(question.pk) and _summary(answers.get(question.pk)),
        }
        for question in questions
    ]
    return render(
        request,
        "assessments/review.html",
        {
            "tenant": tenant,
            "assessment": assessment,
            "items": items,
            "answered": answered,
            "total": len(questions),
            "error": request.GET.get("incomplete") == "1",
        },
    )


@login_required
@require_POST
def complete(request, assessment_id):
    tenant = _tenant(request)
    if blocked := _without_consent(request, tenant):
        return blocked
    assessment = _assessment(request, tenant, assessment_id)
    if assessment.status == Assessment.Status.COMPLETED:
        return redirect("assessment_completed", assessment_id=assessment.pk)
    try:
        complete_assessment(request.user, tenant.organization, assessment.pk)
    except ValidationError:
        return redirect(f"/app/assessment/{assessment.pk}/review/?incomplete=1")
    return redirect("assessment_completed", assessment_id=assessment.pk)


@login_required
@require_GET
def completed(request, assessment_id):
    tenant = _tenant(request)
    assessment = _assessment(request, tenant, assessment_id)
    if assessment.status != Assessment.Status.COMPLETED:
        raise Http404
    result = (
        AssessmentResult.objects.filter(assessment=assessment)
        .prefetch_related("pillars__pillar")
        .first()
    )
    if result is None:
        raise Http404
    pillars = list(result.pillars.all())
    # The owner's own identification answers (section 1, never scored).
    answers = assessment.answers.filter(
        question__section__number=1, question__section__is_scored=False
    ).select_related("question", "selected_option")
    # Previous completed assessment of the same person in the same company.
    previous_assessment = (
        Assessment.objects.filter(
            user=request.user,
            organization=tenant.organization,
            status=Assessment.Status.COMPLETED,
            result__isnull=False,
            completed_at__lt=assessment.completed_at,
        )
        .order_by("-completed_at", "-pk")
        .first()
    )
    previous = None
    if previous_assessment is not None:
        previous = SimpleNamespace(
            completed_at=previous_assessment.completed_at,
            pillars=list(previous_assessment.result.pillars.select_related("pillar")),
        )
    try:
        context = quality_map.build_context(
            assessment=assessment,
            result=result,
            pillars=pillars,
            answers=list(answers),
            previous=previous,
        )
    except ValueError as error:
        raise Http404 from error
    return render(request, "assessments/completed.html", {"tenant": tenant, **context})
