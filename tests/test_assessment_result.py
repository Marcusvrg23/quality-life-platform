"""TEST ONLY — NOT PRODUCTION CONTENT. Persisted result presentation."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assessments import quality_map
from assessments.models import (
    Answer,
    Assessment,
    AssessmentResult,
    Pillar,
    PillarResult,
    Question,
    QuestionnaireSection,
    QuestionnaireVersion,
    QuestionOption,
)
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization


def answer_identification(version, assessment, registration="", sector_other=""):
    """Section 1 of v2 answered by the owner (while still in progress)."""
    section = QuestionnaireSection.objects.create(
        questionnaire=version,
        code="s1",
        number=1,
        title="IDENTIFICAÇÃO DO COLABORADOR",
        is_scored=False,
        display_order=1,
    )
    texts = {
        "q1-1": "Carla Souza Oliveira",
        "q1-2": registration,
        "q1-4": "Analista Administrativo",
    }
    singles = {
        "q1-3": ("Administrativo", "Outro:"),
        "q1-5": ("31 a 40 anos",),
        "q1-6": ("4 anos",),
        "q1-7": ("Híbrido",),
        "q1-8": ("8 horas por dia",),
    }
    for order in range(1, 9):
        code = f"q1-{order}"
        kind = Question.Kind.TEXT if code in texts else Question.Kind.SINGLE
        question = Question.objects.create(
            section=section,
            code=code,
            text=f"TEST ONLY {code}",
            kind=kind,
            max_length=150 if kind == Question.Kind.TEXT else None,
            required=code != "q1-2",
            scorable=False,
            weight=Decimal(1),
            display_order=order,
        )
        if kind == Question.Kind.TEXT:
            if texts[code]:
                Answer.objects.create(
                    assessment=assessment, question=question, text_value=texts[code]
                )
            continue
        options = [
            QuestionOption.objects.create(
                question=question,
                code=f"o{index}",
                label=label,
                score_value=Decimal(0),
                counts_for_score=False,
                requires_text=label == "Outro:",
                display_order=index,
            )
            for index, label in enumerate(singles[code], 1)
        ]
        chosen = options[-1]
        Answer.objects.create(
            assessment=assessment,
            question=question,
            selected_option=chosen,
            text_value=sector_other if chosen.requires_text else "",
        )


def band_of(score):
    """TEST ONLY: the band a saved score would carry (classify_score rules)."""
    score = Decimal(score)
    if score < 40:
        return "PRIORIDADE"
    if score < 70:
        return "ATENÇÃO"
    if score < 85:
        return "BOM"
    return "EXCELENTE"


def completed_result(user, organization, version, overall, scores, days=0, start=None):
    """A completed assessment with persisted results (scores by pillar code)."""
    assessment = start or Assessment.objects.create(
        user=user, organization=organization, questionnaire_version=version
    )
    result = AssessmentResult.objects.create(
        assessment=assessment,
        overall_score=Decimal(overall),
        overall_band=band_of(overall),
        scoring_version="test-result",
    )
    for pillar in Pillar.objects.all():
        PillarResult.objects.create(
            assessment_result=result,
            pillar=pillar,
            score=Decimal(scores[pillar.code]),
            band=band_of(scores[pillar.code]),
        )
    assessment.status = Assessment.Status.COMPLETED
    assessment.completed_at = timezone.now() - timedelta(days=days)
    assessment.save()
    return assessment


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
        self.admin = user_model.objects.create_user(
            email="result-admin@example.test", password="test-password"
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
            (self.admin, self.org, Membership.Role.ADMIN),
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

    def persist_result(self, equal_scores=False):
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
                score=Decimal("50.00") if equal_scores else Decimal(index * 10),
                band=(
                    "ATENÇÃO"
                    if equal_scores
                    else "PRIORIDADE"
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
        content = response.content.decode()
        self.assertEqual(content.count('class="heart-segment"'), 9)
        self.assertEqual(content.count('class="pillar-row"'), 9)
        self.assertIn('role="group" aria-labelledby="heart-title heart-desc"', content)
        self.assertIn('data-count="63">63<', content)  # 63.25 shown as 63
        self.assertIn("ATENÇÃO", content)
        self.assertContains(response, 'class="heart-center-score"')
        self.assertContains(response, 'class="quality-map-reset button-secondary"')
        self.assertContains(response, 'class="attention-item"', count=3)
        self.assertContains(response, 'tabindex="0" role="button"', count=9)
        self.assertContains(
            response,
            timezone.localtime(self.assessment.completed_at).strftime("%d/%m/%Y"),
        )
        segments = response.context["segments"]
        self.assertEqual(
            [segment["code"] for segment in segments],
            [segment["pillar_code"] for segment in quality_map.SPEC["segments"]],
        )
        self.assertEqual(
            [segment["polygon"] for segment in segments],
            [segment["polygon"] for segment in quality_map.SPEC["segments"]],
        )
        by_pk = {item.pk: item for item in expected}
        for segment in segments:
            stored = by_pk[segment["pillar"].pk]
            self.assertEqual(segment["band"], stored.band)
            self.assertEqual(segment["display"], int(stored.score))
        self.assertEqual(
            [item["pillar"].pk for item in response.context["attention"]],
            [item.pk for item in sorted(expected, key=lambda item: item.score)[:3]],
        )
        self.client.get(self.url)
        result.refresh_from_db()
        self.assessment.refresh_from_db()
        self.assertEqual(result.overall_score, Decimal("63.25"))
        self.assertEqual(self.assessment.status, Assessment.Status.COMPLETED)
        self.assertEqual(result.pillars.count(), 9)

    def test_equal_scores_use_persisted_display_order_for_attention(self):
        result = self.persist_result(equal_scores=True)
        response = self.client.get(self.url)
        self.assertEqual(
            [
                item["pillar"].pillar.display_order
                for item in response.context["attention"]
            ],
            [1, 2, 3],
        )
        self.assertEqual(result.overall_score, Decimal("63.25"))

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

    def identify(self, registration="", sector_other="Laboratório"):
        answer_identification(self.version, self.assessment, registration, sector_other)

    def previous_result(self, user, organization, score="50.00", days=30):
        scores = dict.fromkeys(Pillar.objects.values_list("code", flat=True), score)
        return completed_result(user, organization, self.version, score, scores, days)

    def test_identification_shows_other_text_and_skips_blank_registration(self):
        self.identify()
        self.persist_result()
        response = self.client.get(self.url)
        self.assertContains(response, "Identificação do colaborador")
        self.assertContains(response, "Carla Souza Oliveira")
        self.assertContains(response, "<dd>Laboratório</dd>")
        self.assertNotContains(response, "Outro:")
        self.assertNotContains(response, "Matrícula")
        self.assertContains(response, "<dd>Híbrido</dd>")
        self.assertContains(response, ">CO<")

    def test_identification_shows_registration_when_answered(self):
        self.identify(registration="12548")
        self.persist_result()
        response = self.client.get(self.url)
        self.assertContains(response, "<dt>Matrícula:</dt><dd>12548</dd>")

    def test_evolution_needs_previous_of_same_person_and_company(self):
        # Previous results of a colleague and of another company never count.
        self.previous_result(self.other, self.org, score="11.00")
        self.previous_result(self.owner, self.other_org, score="12.00")
        self.persist_result()
        response = self.client.get(self.url)
        self.assertContains(
            response, "Sua evolução aparece a partir da segunda avaliação."
        )
        self.assertNotContains(response, 'class="evolution-chart"')
        self.assertIsNone(response.context["evolution"])

    def test_evolution_compares_with_the_previous_assessment(self):
        previous = self.previous_result(self.owner, self.org, score="50.75")
        self.persist_result()
        response = self.client.get(self.url)
        self.assertContains(response, 'class="evolution-chart"')
        self.assertContains(
            response,
            timezone.localtime(previous.completed_at).strftime("%d/%m/%Y"),
        )
        chart = response.context["evolution"]
        self.assertEqual({point["previous"] for point in chart["points"]}, {50})
        self.assertNotContains(
            response, "Sua evolução aparece a partir da segunda avaliação."
        )
        # The older map has nothing before it to compare with.
        older = self.client.get(reverse("assessment_completed", args=[previous.pk]))
        self.assertIsNone(older.context["evolution"])

    def test_scores_are_truncated_for_display_only(self):
        result = AssessmentResult.objects.create(
            assessment=self.assessment,
            overall_score=Decimal("36.67"),
            overall_band="PRIORIDADE",
            scoring_version="test-result",
        )
        for pillar in Pillar.objects.all():
            PillarResult.objects.create(
                assessment_result=result,
                pillar=pillar,
                score=Decimal("69.99"),
                band="ATENÇÃO",
            )
        self.assessment.status = Assessment.Status.COMPLETED
        self.assessment.completed_at = timezone.now()
        self.assessment.save()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-count="36">36<')
        self.assertContains(response, 'data-count="69">69<', count=9)
        self.assertNotContains(response, "36,67")
        self.assertNotContains(response, "69,99")
        self.assertContains(response, ">PRIORIDADE<")
        result.refresh_from_db()
        self.assertEqual(result.overall_score, Decimal("36.67"))
        self.assertEqual(
            set(result.pillars.values_list("score", flat=True)), {Decimal("69.99")}
        )

    def test_managers_admins_and_colleagues_never_see_the_map(self):
        self.identify(registration="12548")
        self.persist_result()
        for user, status in (
            (self.manager, 403),
            (self.admin, 403),
            (self.other, 404),
        ):
            self.client.force_login(user)
            session = self.client.session
            session[SESSION_ORGANIZATION_KEY] = self.org.pk
            session.save()
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status, user.email)
            for secret in ("Carla Souza Oliveira", "12548", "Laboratório"):
                self.assertNotContains(response, secret, status_code=status)
