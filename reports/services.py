"""Deterministic, aggregate-only executive report. No AI and no individual data."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from assessments.models import Assessment, Pillar, PillarResult
from assessments.services import canonical_score, classify_score
from identity.consent import revoked_user_ids
from identity.models import Membership

from .catalog import CatalogEntry, catalog_for

# Privacy threshold: no averages or distributions below this many people.
MIN_GROUP = 5

BANDS = ("EXCELENTE", "BOM", "ATENÇÃO", "PRIORIDADE")
AFFECTED_BANDS = ("ATENÇÃO", "PRIORIDADE")
TOP_COUNT = 3

# Prioritization matrix thresholds and labels, in investment order.
IMMEDIATE_BELOW = Decimal(40)
ATTENTION_BELOW = Decimal(70)
HIGH_AFFECTED_FROM = 50
PRIORITY_IMMEDIATE = "Prioridade imediata"
PRIORITY_HIGH = "Prioridade alta"
PRIORITY_MODERATE = "Prioridade moderada"
PRIORITY_MAINTENANCE = "Manutenção"
PRIORITY_CRITERIA = (
    (PRIORITY_IMMEDIATE, f"Média abaixo de {IMMEDIATE_BELOW}"),
    (
        PRIORITY_HIGH,
        (
            f"Média de {IMMEDIATE_BELOW} a menos de {ATTENTION_BELOW} "
            f"e {HIGH_AFFECTED_FROM}% ou mais de afetados"
        ),
    ),
    (
        PRIORITY_MODERATE,
        (
            f"Média de {IMMEDIATE_BELOW} a menos de {ATTENTION_BELOW} "
            f"e menos de {HIGH_AFFECTED_FROM}% de afetados"
        ),
    ),
    (PRIORITY_MAINTENANCE, f"Média de {ATTENTION_BELOW} ou mais"),
)
PRIORITY_LEVELS = tuple(level for level, _ in PRIORITY_CRITERIA)
ACTION_PLAN_LEVELS = (PRIORITY_IMMEDIATE, PRIORITY_HIGH)


@dataclass(frozen=True)
class PillarSummary:
    pillar: Pillar
    average: Decimal
    band: str
    distribution: tuple[tuple[str, int], ...]
    affected_percent: int
    priority: str
    catalog: CatalogEntry


@dataclass(frozen=True)
class MatrixRow:
    level: str
    criterion: str
    pillars: tuple[PillarSummary, ...]


@dataclass(frozen=True)
class ExecutiveReport:
    start_date: date
    end_date: date
    population: int
    evaluated: int
    participation_percent: int
    insufficient_data: bool
    overall_average: Decimal | None = None
    overall_band: str | None = None
    pillars: tuple[PillarSummary, ...] = ()
    strengths: tuple[PillarSummary, ...] = ()
    attention: tuple[PillarSummary, ...] = ()
    priorities: tuple[PillarSummary, ...] = ()
    investments: tuple[PillarSummary, ...] = ()
    action_plan: tuple[PillarSummary, ...] = ()
    matrix: tuple[MatrixRow, ...] = ()


def percent(part, whole):
    if not whole:
        return 0
    return int(
        (Decimal(part) * 100 / Decimal(whole)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


def average(scores):
    return canonical_score(sum(scores, Decimal(0)) / len(scores))


def classify_priority(average_score, affected_percent):
    if average_score < IMMEDIATE_BELOW:
        return PRIORITY_IMMEDIATE
    if average_score < ATTENTION_BELOW:
        if affected_percent >= HIGH_AFFECTED_FROM:
            return PRIORITY_HIGH
        return PRIORITY_MODERATE
    return PRIORITY_MAINTENANCE


def _period_bounds(start_date, end_date):
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), zone)
    end = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min), zone
    )
    return start, end


def _latest_assessment_ids(organization, population_user_ids, start_date, end_date):
    start, end = _period_bounds(start_date, end_date)
    return list(
        Assessment.objects.filter(
            organization=organization,
            user_id__in=population_user_ids,
            status=Assessment.Status.COMPLETED,
            completed_at__gte=start,
            completed_at__lt=end,
            result__isnull=False,
        )
        .order_by("user_id", "-completed_at", "-pk")
        .distinct("user_id")
        .values_list("pk", flat=True)
    )


def _pillar_summaries(assessment_ids):
    results = (
        PillarResult.objects.filter(assessment_result__assessment_id__in=assessment_ids)
        .select_related("pillar")
        .order_by("pillar__display_order", "pk")
    )
    grouped = {}
    for result in results:
        grouped.setdefault(result.pillar, []).append(result)
    summaries = []
    for pillar, items in grouped.items():
        if len(items) < MIN_GROUP:
            continue
        count = len(items)
        mean = average([item.score for item in items])
        affected = percent(sum(item.band in AFFECTED_BANDS for item in items), count)
        summaries.append(
            PillarSummary(
                pillar=pillar,
                average=mean,
                band=classify_score(mean),
                distribution=tuple(
                    (band, percent(sum(item.band == band for item in items), count))
                    for band in BANDS
                ),
                affected_percent=affected,
                priority=classify_priority(mean, affected),
                catalog=catalog_for(pillar.code),
            )
        )
    return tuple(summaries)


def build_executive_report(organization, start_date, end_date):
    population_user_ids = list(
        Membership.objects.filter(
            organization=organization,
            role=Membership.Role.COLLABORATOR,
            is_active=True,
        ).values_list("user_id", flat=True)
    )
    # Revoked consent (latest record in this company) removes the person's data.
    revoked = revoked_user_ids(organization)
    assessment_ids = _latest_assessment_ids(
        organization,
        [user_id for user_id in population_user_ids if user_id not in revoked],
        start_date,
        end_date,
    )
    population = len(population_user_ids)
    evaluated = len(assessment_ids)
    participation = percent(evaluated, population)
    if evaluated < MIN_GROUP:
        return ExecutiveReport(
            start_date=start_date,
            end_date=end_date,
            population=population,
            evaluated=evaluated,
            participation_percent=participation,
            insufficient_data=True,
        )

    overall = average(
        list(
            Assessment.objects.filter(pk__in=assessment_ids).values_list(
                "result__overall_score", flat=True
            )
        )
    )
    pillars = _pillar_summaries(assessment_ids)

    # Ties always fall back to the approved pillar display order.
    def ascending(item):
        return (item.average, item.pillar.display_order)

    by_lowest = tuple(sorted(pillars, key=ascending))
    by_highest = tuple(
        sorted(pillars, key=lambda item: (-item.average, item.pillar.display_order))
    )
    investments = tuple(
        sorted(
            pillars,
            key=lambda item: (PRIORITY_LEVELS.index(item.priority), *ascending(item)),
        )
    )
    return ExecutiveReport(
        start_date=start_date,
        end_date=end_date,
        population=population,
        evaluated=evaluated,
        participation_percent=participation,
        insufficient_data=False,
        overall_average=overall,
        overall_band=classify_score(overall),
        pillars=pillars,
        strengths=by_highest[:TOP_COUNT],
        attention=tuple(item for item in by_lowest if item.average < ATTENTION_BELOW),
        priorities=by_lowest[:TOP_COUNT],
        investments=investments,
        action_plan=tuple(
            item for item in investments if item.priority in ACTION_PLAN_LEVELS
        ),
        matrix=tuple(
            MatrixRow(
                level=level,
                criterion=criterion,
                pillars=tuple(item for item in investments if item.priority == level),
            )
            for level, criterion in PRIORITY_CRITERIA
        ),
    )
