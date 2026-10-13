"""Deterministic home recommendation from the user's own latest result."""

from django.urls import reverse

from assessments.models import Assessment, PillarResult

EXERCISE_PILLARS = frozenset(
    {"physical_activity", "ergonomics_workplace", "physical_health"}
)


def build_recommendation(user, organization):
    """Lowest-scoring pillar of the user's latest completed assessment.

    Ties are broken by ``Pillar.display_order``. Reads only rows owned by
    ``user`` in ``organization``; returns None without a completed result.
    """
    latest = (
        Assessment.objects.filter(
            user=user,
            organization=organization,
            status=Assessment.Status.COMPLETED,
            result__isnull=False,
        )
        .order_by("-completed_at", "-pk")
        .first()
    )
    if latest is None:
        return None
    lowest = (
        PillarResult.objects.filter(assessment_result__assessment=latest)
        .select_related("pillar")
        .order_by("score", "pillar__display_order")
        .first()
    )
    if lowest is None:
        return None
    to_exercises = lowest.pillar.code in EXERCISE_PILLARS
    return {
        "pillar_name": lowest.pillar.name,
        "to_exercises": to_exercises,
        "url": reverse("exercises" if to_exercises else "assessment_hub"),
    }
