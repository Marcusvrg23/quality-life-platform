"""Server-rendered assessment flow backed by the M3 services."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from config.tenant import resolve_tenant_context
from identity.models import Membership

from .models import Assessment, Question, QuestionnaireVersion
from .services import complete_assessment, record_answer, start_assessment


def _tenant(request):
    tenant = resolve_tenant_context(request)
    if tenant is None or tenant.role != Membership.Role.COLLABORATOR:
        raise PermissionDenied("Assessment unavailable.")
    return tenant


def _assessment(request, tenant, assessment_id):
    assessment = (
        Assessment.objects.select_related("questionnaire_version")
        .filter(pk=assessment_id, user=request.user, organization=tenant.organization)
        .first()
    )
    if assessment is None:
        raise Http404
    return assessment


def _questions(assessment):
    return list(
        Question.objects.filter(
            questionnaire_pillar__questionnaire=assessment.questionnaire_version,
            questionnaire_pillar__is_active=True,
            is_active=True,
        )
        .select_related("questionnaire_pillar__pillar")
        .prefetch_related("options")
        .order_by("questionnaire_pillar__display_order", "display_order", "pk")
    )


def _flow(assessment):
    questions = _questions(assessment)
    answers = {
        answer.question_id: answer.selected_option
        for answer in assessment.answers.select_related("selected_option")
    }
    answered = sum(question.pk in answers for question in questions)
    return questions, answers, answered


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
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
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
            return redirect("assessment_detail", assessment_id=existing.pk)
        versions = list(
            QuestionnaireVersion.objects.filter(
                status=QuestionnaireVersion.Status.PUBLISHED
            )[:2]
        )
        if len(versions) != 1:
            return redirect("assessment_hub")
        try:
            assessment = start_assessment(
                request.user, tenant.organization, versions[0].pk
            )
        except ValidationError:
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
    selected = answers.get(question_id)
    error = None
    if request.method == "POST":
        option_id = request.POST.get("option")
        if not option_id:
            error = "Selecione uma resposta antes de salvar."
        else:
            try:
                record_answer(
                    request.user,
                    tenant.organization,
                    assessment.pk,
                    current.pk,
                    option_id,
                )
            except (ValidationError, ValueError, OverflowError):
                error = (
                    "Resposta inválida. Escolha uma das alternativas desta pergunta."
                )
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
            "selected": selected,
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
    assessment = _assessment(request, tenant, assessment_id)
    if assessment.status == Assessment.Status.COMPLETED:
        return redirect("assessment_completed", assessment_id=assessment.pk)
    questions, answers, answered = _flow(assessment)
    items = [
        {"question": question, "answer": answers.get(question.pk)}
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
    return render(
        request,
        "assessments/completed.html",
        {"tenant": tenant, "assessment": assessment},
    )
