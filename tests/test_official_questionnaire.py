"""Official questionnaire loading and non-scoring options on PostgreSQL."""

import json
import shutil
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase

from assessments.management.commands.seed_quality_life_demo import DEMO_CODE
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
OFFICIAL_FILE = (
    Path(settings.BASE_DIR)
    / "assessments"
    / "questionnaires"
    / "quality_life_oficial_v1.json"
)
OFFICIAL_CODE = "quality-life-oficial"


def official_data():
    return json.loads(OFFICIAL_FILE.read_text(encoding="utf-8"))


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


class LoadOfficialQuestionnaireTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def load(self, path=OFFICIAL_FILE, **options):
        out = StringIO()
        call_command(
            "load_official_questionnaire", file=str(path), stdout=out, **options
        )
        return out.getvalue()

    def write(self, data, name="questionnaire.json"):
        path = self.tmp / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def seed_demo(self):
        with patch.dict(
            "os.environ",
            {
                "QUALITY_LIFE_DEMO_SEED_ENABLED": "true",
                "QUALITY_LIFE_DEMO_PASSWORD": "Long-demo-passphrase-8274",
            },
        ):
            call_command("seed_quality_life_demo", stdout=StringIO())
        return QuestionnaireVersion.objects.get(code=DEMO_CODE)

    def official_counts(self):
        return (
            QuestionnairePillar.objects.filter(
                questionnaire__code=OFFICIAL_CODE
            ).count(),
            Question.objects.filter(
                questionnaire_pillar__questionnaire__code=OFFICIAL_CODE
            ).count(),
            QuestionOption.objects.filter(
                question__questionnaire_pillar__questionnaire__code=OFFICIAL_CODE
            ).count(),
        )

    def test_loads_real_file_and_publishes(self):
        output = self.load()
        questionnaire = QuestionnaireVersion.objects.get(code=OFFICIAL_CODE)
        self.assertEqual(questionnaire.version, 1)
        self.assertEqual(questionnaire.status, QuestionnaireVersion.Status.PUBLISHED)
        option_total = sum(
            len(q["options"])
            for p in official_data()["pillars"]
            for q in p["questions"]
        )
        self.assertEqual(self.official_counts(), (9, 77, option_total))
        self.assertEqual(
            set(questionnaire.pillars.values_list("pillar__code", flat=True)),
            set(Pillar.objects.values_list("code", flat=True)),
        )
        questions = Question.objects.filter(
            questionnaire_pillar__questionnaire=questionnaire
        )
        self.assertFalse(questions.exclude(score_direction="NORMAL").exists())
        self.assertTrue(
            QuestionOption.objects.filter(
                question__in=questions, counts_for_score=False
            ).exists()
        )
        self.assertIn("9 pilares, 77 perguntas", output)
        self.assertIn(f"{option_total} opções", output)

    def test_second_run_does_not_duplicate(self):
        self.load()
        counts = self.official_counts()
        output = self.load()
        self.assertIn("já carregado", output)
        self.assertEqual(self.official_counts(), counts)
        self.assertEqual(QuestionnaireVersion.objects.count(), 1)

    def test_changed_file_with_same_version_is_refused(self):
        self.load()
        data = official_data()
        data["pillars"][0]["questions"][0]["options"][0]["label"] = "Alterado"
        with self.assertRaisesMessage(CommandError, "Aumente a versão"):
            self.load(self.write(data))
        self.assertEqual(QuestionnaireVersion.objects.count(), 1)

    def test_refuses_when_demo_is_published_without_flag(self):
        demo = self.seed_demo()
        with self.assertRaisesMessage(CommandError, "--retire-other-published"):
            self.load()
        self.assertFalse(
            QuestionnaireVersion.objects.filter(code=OFFICIAL_CODE).exists()
        )
        demo.refresh_from_db()
        self.assertEqual(demo.status, QuestionnaireVersion.Status.PUBLISHED)

    def test_flag_retires_demo_and_publishes_official(self):
        demo = self.seed_demo()
        output = self.load(retire_other_published=True)
        demo.refresh_from_db()
        self.assertEqual(demo.status, QuestionnaireVersion.Status.RETIRED)
        self.assertEqual(
            list(
                QuestionnaireVersion.objects.filter(
                    status=QuestionnaireVersion.Status.PUBLISHED
                ).values_list("code", flat=True)
            ),
            [OFFICIAL_CODE],
        )
        self.assertIn(f"Aposentado: {DEMO_CODE} v1.", output)

    def test_invalid_file_writes_nothing(self):
        def mutate(change):
            data = official_data()
            change(data)
            return data

        def option(data):
            return data["pillars"][0]["questions"][0]["options"][0]

        cases = {
            "missing-pillar": mutate(lambda d: d["pillars"].pop()),
            "duplicate-pillar": mutate(
                lambda d: d["pillars"].__setitem__(1, d["pillars"][0])
            ),
            "unknown-pillar": mutate(
                lambda d: d["pillars"][0].__setitem__("pillar_code", "unknown")
            ),
            "bad-slug": mutate(
                lambda d: d["pillars"][0]["questions"][0].__setitem__("code", "q 1")
            ),
            "long-code": mutate(lambda d: option(d).__setitem__("code", "o" * 65)),
            "score-above-100": mutate(
                lambda d: option(d).__setitem__("score_value", 101)
            ),
            "score-negative": mutate(
                lambda d: option(d).__setitem__("score_value", -1)
            ),
            "score-three-places": mutate(
                lambda d: option(d).__setitem__("score_value", 33.333)
            ),
            "counts-not-bool": mutate(
                lambda d: option(d).__setitem__("counts_for_score", "true")
            ),
            "fails-publication": mutate(
                lambda d: [
                    q.__setitem__("required", False)
                    for q in d["pillars"][0]["questions"]
                ]
            ),
        }
        for name, data in cases.items():
            with self.subTest(name=name), self.assertRaises(CommandError):
                self.load(self.write(data, f"{name}.json"))
        malformed = self.tmp / "malformed.json"
        malformed.write_text("{not json", encoding="utf-8")
        with self.assertRaises(CommandError):
            self.load(malformed)
        with self.assertRaises(CommandError):
            self.load(self.tmp / "missing.json")
        self.assertEqual(QuestionnaireVersion.objects.count(), 0)
        self.assertEqual(QuestionnairePillar.objects.count(), 0)
        self.assertEqual(Question.objects.count(), 0)
        self.assertEqual(QuestionOption.objects.count(), 0)


class OfficialQuestionnaireScoringTests(TestCase):
    def setUp(self):
        call_command(
            "load_official_questionnaire", file=str(OFFICIAL_FILE), stdout=StringIO()
        )
        self.questionnaire = QuestionnaireVersion.objects.get(code=OFFICIAL_CODE)
        self.user, self.organization = make_member()

    def complete_choosing(self, choose):
        assessment = start_assessment(
            self.user, self.organization, self.questionnaire.pk
        )
        questions = Question.objects.filter(
            questionnaire_pillar__questionnaire=self.questionnaire
        ).prefetch_related("options")
        for question in questions:
            option = choose(list(question.options.all()))
            record_answer(
                self.user, self.organization, assessment.pk, question.pk, option.pk
            )
        result = complete_assessment(self.user, self.organization, assessment.pk)
        pillars = dict(result.pillars.values_list("pillar__code", "score"))
        self.assertEqual(len(pillars), 9)
        return result.overall_score, pillars

    def test_highest_option_everywhere_scores_100(self):
        overall, pillars = self.complete_choosing(
            lambda options: max(options, key=lambda o: o.score_value)
        )
        self.assertEqual(overall, D("100.00"))
        self.assertEqual(set(pillars.values()), {D("100.00")})

    def test_lowest_scoring_option_everywhere(self):
        overall, pillars = self.complete_choosing(
            lambda options: min(
                (o for o in options if o.counts_for_score),
                key=lambda o: o.score_value,
            )
        )
        # q4-3 (session duration) has no scoring option below 25:
        # Atividade Física = (0 * 4 + 25) / 5 = 5.00; overall = 5 / 9.
        self.assertEqual(pillars.pop("physical_activity"), D("5.00"))
        self.assertEqual(set(pillars.values()), {D("0.00")})
        self.assertEqual(overall, D("0.56"))

    def test_lowest_options_including_non_scoring_score_zero(self):
        overall, pillars = self.complete_choosing(
            lambda options: min(
                options, key=lambda o: (o.score_value, o.counts_for_score)
            )
        )
        self.assertEqual(overall, D("0.00"))
        self.assertEqual(set(pillars.values()), {D("0.00")})
