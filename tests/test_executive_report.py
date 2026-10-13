"""TEST ONLY — NOT PRODUCTION CONTENT. Aggregate-only executive report."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import localize

from assessments.models import (
    Assessment,
    AssessmentResult,
    Pillar,
    PillarResult,
    QuestionnaireVersion,
)
from assessments.services import classify_score
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.consent import grant_consent, revoke_consent
from identity.models import Membership, Organization
from reports.catalog import CATALOG, PENDING_CONTENT, catalog_for
from reports.services import (
    PRIORITY_HIGH,
    PRIORITY_IMMEDIATE,
    PRIORITY_MAINTENANCE,
    PRIORITY_MODERATE,
    build_executive_report,
    classify_priority,
    percent,
)
from reports.views import DEFAULT_PERIOD_DAYS, report_period

INSUFFICIENT = (
    "São necessárias pelo menos 5 avaliações concluídas no período para gerar "
    "o relatório."
)
BANDS = ("EXCELENTE", "BOM", "ATENÇÃO", "PRIORIDADE")

# Reference case: one row per collaborator, pillar scores by display_order 1..9.
REFERENCE_OVERALL = ("63.25", "70.10", "55.55", "80.00", "41.11")
REFERENCE_PILLARS = (
    ("90", "80", "50", "30", "75", "60", "85", "100", "70"),
    ("85", "75", "55", "35", "75", "60", "85", "100", "70"),
    ("80", "70", "60", "20", "75", "65", "85", "100", "70"),
    ("95", "72", "45", "10", "75", "30", "85", "10", "70"),
    ("88", "71", "65", "39.99", "75", "20", "85", "10", "70"),
)


class ReportPureRulesTests(SimpleTestCase):
    def test_matrix_boundaries(self):
        cases = (
            ("39.99", 0, PRIORITY_IMMEDIATE),
            ("39.99", 100, PRIORITY_IMMEDIATE),
            ("40", 49, PRIORITY_MODERATE),
            ("40", 50, PRIORITY_HIGH),
            ("69.99", 49, PRIORITY_MODERATE),
            ("69.99", 50, PRIORITY_HIGH),
            ("70", 50, PRIORITY_MAINTENANCE),
            ("70", 100, PRIORITY_MAINTENANCE),
        )
        for average, affected, expected in cases:
            with self.subTest(average=average, affected=affected):
                self.assertEqual(
                    classify_priority(Decimal(average), affected), expected
                )

    def test_percent_is_integer_round_half_up(self):
        self.assertEqual(percent(1, 8), 13)  # 12.5
        self.assertEqual(percent(49, 100), 49)
        self.assertEqual(percent(5, 6), 83)
        self.assertEqual(percent(0, 0), 0)

    def test_period_is_always_the_last_90_days(self):
        today = timezone.localdate()
        self.assertEqual(
            report_period(),
            (today - timedelta(days=DEFAULT_PERIOD_DAYS - 1), today),
        )

    def test_catalog_covers_nine_pillar_codes(self):
        self.assertEqual(len(CATALOG), 9)
        self.assertEqual(catalog_for("physical_health").investment, PENDING_CONTENT)
        self.assertEqual(
            catalog_for("sleep_recovery").investment,
            "Campanha de sono e recuperação.",
        )
        self.assertEqual(catalog_for("relationships").indicator, "")


class ExecutiveReportTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.org = Organization.objects.create(name="Report test", slug="report-test")
        self.other_org = Organization.objects.create(
            name="Other report test", slug="other-report-test"
        )
        self.collaborators = [
            user_model.objects.create_user(
                email=f"collab{index}@example.test", password="test-password"
            )
            for index in range(6)
        ]
        for user in self.collaborators:
            Membership.objects.create(
                user=user, organization=self.org, role=Membership.Role.COLLABORATOR
            )
        self.inactive = user_model.objects.create_user(
            email="inactive@example.test", password="test-password"
        )
        Membership.objects.create(
            user=self.inactive,
            organization=self.org,
            role=Membership.Role.COLLABORATOR,
            is_active=False,
        )
        self.manager = user_model.objects.create_user(
            email="manager@example.test", password="test-password"
        )
        Membership.objects.create(
            user=self.manager,
            organization=self.org,
            role=Membership.Role.CORPORATE_MANAGER,
        )
        self.other_manager = user_model.objects.create_user(
            email="other-manager@example.test", password="test-password"
        )
        Membership.objects.create(
            user=self.other_manager,
            organization=self.other_org,
            role=Membership.Role.CORPORATE_MANAGER,
        )
        self.version = QuestionnaireVersion.objects.create(
            code="report-test-only",
            version=1,
            title="TEST ONLY — NOT PRODUCTION CONTENT",
            scoring_version="test-report",
        )
        self.pillars = list(Pillar.objects.order_by("display_order"))
        self.today = timezone.localdate()
        self.start = self.today - timedelta(days=30)
        self.url = reverse("executive_report")

    def login(self, user, organization):
        self.client.force_login(user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = organization.pk
        session.save()

    def persist(
        self,
        user,
        overall,
        pillar_scores,
        *,
        organization=None,
        completed_at=None,
        complete=True,
    ):
        """Create the result first, then complete, as the immutability rules expect."""
        assessment = Assessment.objects.create(
            user=user,
            organization=organization or self.org,
            questionnaire_version=self.version,
        )
        result = AssessmentResult.objects.create(
            assessment=assessment,
            overall_score=Decimal(overall),
            overall_band=classify_score(Decimal(overall)),
            scoring_version="test-report",
        )
        for pillar, score in zip(self.pillars, pillar_scores, strict=True):
            PillarResult.objects.create(
                assessment_result=result,
                pillar=pillar,
                score=Decimal(score),
                band=classify_score(Decimal(score)),
            )
        if complete:
            assessment.status = Assessment.Status.COMPLETED
            assessment.completed_at = completed_at or timezone.now()
            assessment.save()
        return assessment

    def persist_reference(self):
        for user, overall, scores in zip(
            self.collaborators, REFERENCE_OVERALL, REFERENCE_PILLARS, strict=False
        ):
            self.persist(user, overall, scores)

    def build(self):
        return build_executive_report(self.org, self.start, self.today)

    def by_order(self, report):
        return {item.pillar.display_order: item for item in report.pillars}

    def assert_reference(self, report):
        self.assertFalse(report.insufficient_data)
        self.assertEqual(report.population, 6)
        self.assertEqual(report.evaluated, 5)
        self.assertEqual(report.participation_percent, 83)
        self.assertEqual(report.overall_average, Decimal("62.00"))
        self.assertEqual(report.overall_band, "ATENÇÃO")
        pillars = self.by_order(report)
        self.assertEqual(list(pillars), list(range(1, 10)))
        expected = {
            1: ("87.60", "EXCELENTE", (80, 20, 0, 0), 0, PRIORITY_MAINTENANCE),
            2: ("73.60", "BOM", (0, 100, 0, 0), 0, PRIORITY_MAINTENANCE),
            3: ("55.00", "ATENÇÃO", (0, 0, 100, 0), 100, PRIORITY_HIGH),
            4: ("27.00", "PRIORIDADE", (0, 0, 0, 100), 100, PRIORITY_IMMEDIATE),
            5: ("75.00", "BOM", (0, 100, 0, 0), 0, PRIORITY_MAINTENANCE),
            6: ("47.00", "ATENÇÃO", (0, 0, 60, 40), 100, PRIORITY_HIGH),
            7: ("85.00", "EXCELENTE", (100, 0, 0, 0), 0, PRIORITY_MAINTENANCE),
            8: ("64.00", "ATENÇÃO", (60, 0, 0, 40), 40, PRIORITY_MODERATE),
            9: ("70.00", "BOM", (0, 100, 0, 0), 0, PRIORITY_MAINTENANCE),
        }
        for order, (average, band, shares, affected, priority) in expected.items():
            with self.subTest(pillar=order):
                item = pillars[order]
                self.assertEqual(item.average, Decimal(average))
                self.assertEqual(item.band, band)
                self.assertEqual(item.distribution, tuple(zip(BANDS, shares)))
                self.assertEqual(item.affected_percent, affected)
                self.assertEqual(item.priority, priority)

    def orders(self, items):
        return [item.pillar.display_order for item in items]

    def test_reference_case_aggregates(self):
        self.persist_reference()
        report = self.build()
        self.assert_reference(report)
        self.assertEqual(self.orders(report.strengths), [1, 7, 5])
        self.assertEqual(self.orders(report.attention), [4, 6, 3, 8])
        self.assertEqual(self.orders(report.priorities), [4, 6, 3])
        self.assertEqual(self.orders(report.investments), [4, 6, 3, 8, 9, 2, 5, 7, 1])
        self.assertEqual(self.orders(report.action_plan), [4, 6, 3])
        self.assertEqual(
            [(row.level, self.orders(row.pillars)) for row in report.matrix],
            [
                (PRIORITY_IMMEDIATE, [4]),
                (PRIORITY_HIGH, [6, 3]),
                (PRIORITY_MODERATE, [8]),
                (PRIORITY_MAINTENANCE, [9, 2, 5, 7, 1]),
            ],
        )

    def test_ties_fall_back_to_display_order(self):
        for user in self.collaborators[:5]:
            self.persist(user, "50", ["50"] * 9)
        report = self.build()
        self.assertEqual(self.orders(report.strengths), [1, 2, 3])
        self.assertEqual(self.orders(report.priorities), [1, 2, 3])
        self.assertEqual(self.orders(report.attention), list(range(1, 10)))

    def test_insufficient_data_below_five(self):
        for user, overall, scores in zip(
            self.collaborators[:4], REFERENCE_OVERALL, REFERENCE_PILLARS, strict=False
        ):
            self.persist(user, overall, scores)
        report = self.build()
        self.assertTrue(report.insufficient_data)
        self.assertEqual(report.evaluated, 4)
        self.assertEqual(report.participation_percent, 67)
        self.assertIsNone(report.overall_average)
        self.assertEqual(report.pillars, ())

        self.login(self.manager, self.org)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, INSUFFICIENT)
        html = response.content.decode()
        for band in BANDS:
            self.assertNotIn(band, html)
        for value in ("87,60", "73,60", "55,00", "27,00", "62,00", "63,25"):
            self.assertNotIn(value, html)
        self.assertNotIn("Mapa por pilar", html)
        self.assertNotIn("Prioridades", html)

    def test_only_latest_completed_in_period_and_organization(self):
        first, second, third = self.collaborators[:3]
        Membership.objects.create(
            user=third, organization=self.other_org, role=Membership.Role.COLLABORATOR
        )
        now = timezone.now()
        # Older completed assessment in period: superseded by the reference one.
        self.persist(first, "5", ["5"] * 9, completed_at=now - timedelta(days=3))
        # Outside the period.
        self.persist(second, "1", ["1"] * 9, completed_at=now - timedelta(days=60))
        # Another organization.
        self.persist(third, "2", ["2"] * 9, organization=self.other_org)
        self.persist_reference()
        # Newer but never completed.
        self.persist(first, "3", ["3"] * 9, complete=False)
        self.assert_reference(self.build())

    def test_manager_and_admin_get_report(self):
        self.persist_reference()
        self.login(self.manager, self.org)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "reports/executive.html")
        self.assert_reference(response.context["report"])
        self.assertContains(response, "Report test")
        self.assertContains(response, "83%")
        self.assertContains(response, localize(Decimal("62.00")))
        self.assertContains(response, "Programa de saúde emocional.")
        self.assertContains(response, "Diagnosticar")

        admin = get_user_model().objects.create_user(
            email="admin@example.test", password="test-password"
        )
        Membership.objects.create(
            user=admin, organization=self.org, role=Membership.Role.ADMIN
        )
        self.login(admin, self.org)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_collaborator_and_professional_are_forbidden(self):
        self.login(self.collaborators[0], self.org)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        professional = get_user_model().objects.create_user(
            email="professional@example.test", password="test-password"
        )
        Membership.objects.create(
            user=professional,
            organization=self.org,
            role=Membership.Role.PROFESSIONAL,
        )
        self.login(professional, self.org)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.url}",
            fetch_redirect_response=False,
        )

    def test_without_selected_tenant_redirects_to_app(self):
        Membership.objects.create(
            user=self.manager,
            organization=self.other_org,
            role=Membership.Role.CORPORATE_MANAGER,
        )
        self.client.force_login(self.manager)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)

    def test_post_is_not_allowed(self):
        self.login(self.manager, self.org)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_other_company_manager_sees_no_data_from_this_company(self):
        self.persist_reference()
        self.login(self.other_manager, self.other_org)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        report = response.context["report"]
        self.assertTrue(report.insufficient_data)
        self.assertEqual((report.population, report.evaluated), (0, 0))
        self.assertNotContains(response, "Report test")
        self.assertNotContains(response, localize(Decimal("62.00")))

        # Forging the session to this company is rejected server-side.
        self.login(self.other_manager, self.org)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_period_query_is_ignored(self):
        self.persist_reference()
        self.login(self.manager, self.org)
        plain = self.client.get(self.url)
        for query in (
            {"inicio": "2020-01-01", "fim": "2020-01-31"},
            {"inicio": self.today.isoformat(), "fim": self.today.isoformat()},
        ):
            with self.subTest(query=query):
                forged = self.client.get(self.url, query)
                self.assertEqual(forged.context["report"], plain.context["report"])
        report = plain.context["report"]
        self.assertEqual(
            (report.start_date, report.end_date),
            (self.today - timedelta(days=DEFAULT_PERIOD_DAYS - 1), self.today),
        )
        self.assert_reference(report)
        self.assertNotContains(plain, 'name="inicio"')
        self.assertNotContains(plain, 'name="fim"')
        self.assertContains(plain, "últimos 90 dias")

    def test_revoked_consent_leaves_the_report(self):
        self.persist_reference()
        revoking = self.collaborators[0]
        grant_consent(revoking, self.org)
        # Revoking in another company does not touch this company's report.
        grant_consent(self.collaborators[1], self.other_org)
        revoke_consent(self.collaborators[1], self.other_org)
        self.assert_reference(self.build())

        revoke_consent(revoking, self.org)
        report = self.build()
        self.assertEqual((report.population, report.evaluated), (6, 4))
        self.assertTrue(report.insufficient_data)

        # A later, explicit consent brings the person back.
        grant_consent(revoking, self.org)
        self.assert_reference(self.build())

    def test_html_has_no_collaborator_email_or_individual_score(self):
        self.persist_reference()
        self.login(self.manager, self.org)
        html = self.client.get(self.url).content.decode()
        for user in [*self.collaborators, self.inactive]:
            self.assertNotIn(user.email, html)
        # Individual values that differ from every aggregate in the reference case.
        for value in ("63.25", "70.10", "55.55", "41.11", "90", "95", "88", "39.99"):
            self.assertNotIn(localize(Decimal(value).quantize(Decimal("0.01"))), html)

    def test_menu_link_only_for_manager(self):
        self.login(self.manager, self.org)
        response = self.client.get(reverse("app"))
        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, "Relatório da empresa")
        self.login(self.collaborators[0], self.org)
        response = self.client.get(reverse("app"))
        self.assertNotContains(response, f'href="{self.url}"')
        self.assertNotContains(response, "Relatório da empresa")
