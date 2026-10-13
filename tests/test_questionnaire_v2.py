"""Questionnaire v2 on PostgreSQL: new kinds, unscored sections, same scores as v1."""

import json
import random
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from assessments.models import (
    Answer,
    AnswerChoice,
    Assessment,
    Question,
    QuestionnaireSection,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import (
    calculate_assessment_scores,
    complete_assessment,
    ordered_questions,
    record_answer,
    start_assessment,
)
from config.tenant import SESSION_ORGANIZATION_KEY
from identity.consent import grant_consent
from identity.models import Membership, Organization
from reports.services import build_executive_report
from reports.views import report_period

QUESTIONNAIRES = Path(settings.BASE_DIR) / "assessments" / "questionnaires"
V1_FILE = QUESTIONNAIRES / "quality_life_oficial_v1.json"
V2_FILE = QUESTIONNAIRES / "quality_life_oficial_v2.json"
CODE = "quality-life-oficial"
SECRET_NAME = "Nome Secreto Exemplo"
SECRET_ID = "MATRICULA-SECRETA-77"
SECRET_ROLE = "Cargo Secreto"
SECRET_SECTOR = "Setor Secreto Outro"
SECRET_SHARE = "Texto livre secreto"


def load(path, *, retire=False):
    call_command(
        "load_official_questionnaire",
        file=str(path),
        retire_other_published=retire,
        stdout=StringIO(),
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return QuestionnaireVersion.objects.get(code=data["code"], version=data["version"])


def make_member(email, organization, role=Membership.Role.COLLABORATOR):
    user = get_user_model().objects.create_user(email=email, password="test-password")
    Membership.objects.create(user=user, organization=organization, role=role)
    return user


def v2_question(questionnaire, code):
    return Question.objects.get(section__questionnaire=questionnaire, code=code)


def unscored_answer(question, variant):
    """Answer for a question that must never change the score."""
    options = list(question.options.all())
    if question.kind == Question.Kind.TEXT:
        if not question.required and variant == "b":
            return None
        return {"text": f"Resposta {variant} {question.code}"[: question.max_length]}
    if question.kind == Question.Kind.MULTIPLE:
        exclusive = [o for o in options if o.exclusive]
        if variant == "b" and exclusive:
            return {"option_ids": [exclusive[0].pk]}
        return {"option_ids": [o.pk for o in options if not o.exclusive][:3]}
    if not question.required and variant == "b":
        return None
    option = options[0] if variant == "a" else options[-1]
    text = "Outro setor" if option.requires_text else None
    return {"option_id": option.pk, "text": text}


def fill(user, organization, assessment, scored_choice, variant="a"):
    for question in ordered_questions(assessment.questionnaire_version):
        if question.scorable:
            option = question.options.get(code=scored_choice(question))
            answer = {"option_id": option.pk}
        else:
            answer = unscored_answer(question, variant)
        if answer is not None:
            record_answer(user, organization, assessment.pk, question.pk, **answer)


def scored_codes(question):
    return sorted(
        question.options.exclude(question__code="q4-3", code="o6").values_list(
            "code", flat=True
        )
    )


def highest(question):
    return (
        question.options.filter(counts_for_score=True)
        .order_by("-score_value", "code")[0]
        .code
    )


def lowest(question):
    return (
        question.options.filter(counts_for_score=True)
        .order_by("score_value", "code")[0]
        .code
    )


def seeded(seed):
    def choose(question):
        rng = random.Random(f"{seed}-{question.code}")
        return rng.choice(scored_codes(question))

    return choose


class QuestionnaireV2LoadTests(TestCase):
    def test_loads_sections_kinds_and_scoring_flags(self):
        questionnaire = load(V2_FILE)

        self.assertEqual(questionnaire.status, QuestionnaireVersion.Status.PUBLISHED)
        sections = list(questionnaire.sections.order_by("display_order"))
        self.assertEqual([s.number for s in sections], list(range(1, 13)))
        self.assertEqual(
            [s.is_scored for s in sections], [False] + [True] * 10 + [False]
        )
        questions = ordered_questions(questionnaire)
        self.assertEqual(len(questions), 101)
        kinds = {}
        for question in questions:
            kinds[question.kind] = kinds.get(question.kind, 0) + 1
            self.assertIsNotNone(question.section_id)
            self.assertEqual(
                question.scorable, question.questionnaire_pillar_id is not None
            )
        self.assertEqual(kinds, {"SINGLE": 84, "SCALE": 11, "TEXT": 4, "MULTIPLE": 2})
        self.assertEqual(sum(q.scorable for q in questions), 77)
        self.assertEqual(questionnaire.pillars.count(), 9)

    def test_flow_order_follows_the_official_text(self):
        questionnaire = load(V2_FILE)
        data = json.loads(V2_FILE.read_text(encoding="utf-8"))
        expected = [q["code"] for s in data["sections"] for q in s["questions"]]

        actual = [q.code for q in ordered_questions(questionnaire)]

        self.assertEqual(actual, expected)
        self.assertEqual(actual[0], "q1-1")
        self.assertEqual(actual[-3:], ["q12-1", "q12-2", "q12-3"])

    def test_second_run_changes_nothing(self):
        load(V2_FILE)
        counts = (Question.objects.count(), QuestionOption.objects.count())
        stdout = StringIO()

        call_command("load_official_questionnaire", file=str(V2_FILE), stdout=stdout)

        self.assertIn("já carregado", stdout.getvalue())
        self.assertEqual(
            (Question.objects.count(), QuestionOption.objects.count()), counts
        )
        self.assertEqual(QuestionnaireSection.objects.count(), 12)

    def broken(self, mutate):
        data = json.loads(V2_FILE.read_text(encoding="utf-8"))
        mutate(data)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(data, handle, ensure_ascii=False)
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def question(self, data, code):
        return next(
            q for s in data["sections"] for q in s["questions"] if q["code"] == code
        )

    def test_invalid_files_write_nothing(self):
        def unscored_with_pillar(data):
            self.question(data, "q2-3")["pillar_code"] = "physical_health"

        def scored_without_pillar(data):
            self.question(data, "q2-1")["pillar_code"] = None

        def text_with_options(data):
            self.question(data, "q1-1")["options"] = self.question(data, "q1-5")[
                "options"
            ]

        def multiple_scored(data):
            question = self.question(data, "q2-9")
            question.update(scorable=True, pillar_code="physical_health")

        def exclusive_on_single(data):
            self.question(data, "q1-5")["options"][0]["exclusive"] = True

        def unknown_kind(data):
            self.question(data, "q1-5")["kind"] = "DATE"

        def text_too_long(data):
            self.question(data, "q12-3")["max_length"] = 501

        def scored_in_unscored_section(data):
            data["sections"][0]["questions"].append(
                dict(self.question(data, "q2-1"), code="q1-extra")
            )

        def duplicated_code(data):
            data["sections"][11]["questions"][0]["code"] = "q1-1"

        for mutate in (
            unscored_with_pillar,
            scored_without_pillar,
            text_with_options,
            multiple_scored,
            exclusive_on_single,
            unknown_kind,
            text_too_long,
            scored_in_unscored_section,
            duplicated_code,
        ):
            with self.subTest(mutate.__name__):
                with self.assertRaises(CommandError):
                    call_command(
                        "load_official_questionnaire",
                        file=self.broken(mutate),
                        stdout=StringIO(),
                    )
                self.assertFalse(QuestionnaireVersion.objects.exists())
                self.assertFalse(QuestionnaireSection.objects.exists())


class SameScoresAsV1Tests(TestCase):
    def test_same_scored_answers_give_identical_scores(self):
        organization = Organization.objects.create(name="Empresa", slug="empresa")
        user = make_member("pessoa@example.test", organization)
        v1 = load(V1_FILE)
        patterns = {"max": highest, "min": lowest}
        patterns.update({f"seed-{seed}": seeded(seed) for seed in range(4)})
        v1_assessments = {}
        for name, choose in patterns.items():
            assessment = start_assessment(user, organization, v1.pk)
            fill(user, organization, assessment, choose)
            v1_assessments[name] = assessment

        v2 = load(V2_FILE, retire=True)
        v1.refresh_from_db()
        self.assertEqual(v1.status, QuestionnaireVersion.Status.RETIRED)
        for name, choose in patterns.items():
            with self.subTest(name):
                expected = calculate_assessment_scores(v1_assessments[name])
                for variant in ("a", "b"):
                    assessment = start_assessment(user, organization, v2.pk)
                    fill(user, organization, assessment, choose, variant)
                    self.assertEqual(calculate_assessment_scores(assessment), expected)

        # Persisted path: retired v1 still completes; both store the same result.
        name = "seed-0"
        v2_assessment = start_assessment(user, organization, v2.pk)
        fill(user, organization, v2_assessment, patterns[name], "b")
        first = complete_assessment(user, organization, v1_assessments[name].pk)
        second = complete_assessment(user, organization, v2_assessment.pk)
        self.assertEqual(
            (first.overall_score, first.overall_band, first.scoring_version),
            (second.overall_score, second.overall_band, second.scoring_version),
        )
        self.assertEqual(
            sorted(first.pillars.values_list("pillar_id", "score", "band")),
            sorted(second.pillars.values_list("pillar_id", "score", "band")),
        )


class V2AnswerRulesTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.user = make_member("pessoa@example.test", self.organization)
        self.questionnaire = load(V2_FILE)
        self.assessment = start_assessment(
            self.user, self.organization, self.questionnaire.pk
        )

    def answer(self, code, **kwargs):
        question = v2_question(self.questionnaire, code)
        return record_answer(
            self.user, self.organization, self.assessment.pk, question.pk, **kwargs
        )

    def option(self, code, label):
        return QuestionOption.objects.get(
            question=v2_question(self.questionnaire, code), label=label
        )

    def test_exclusive_option_cannot_be_combined(self):
        none = self.option("q2-9", "Não sinto dores")
        neck = self.option("q2-9", "Pescoço")
        shoulders = self.option("q2-9", "Ombros")

        with self.assertRaises(ValidationError):
            self.answer("q2-9", option_ids=[none.pk, neck.pk])
        self.assertFalse(Answer.objects.exists())

        answer = self.answer("q2-9", option_ids=[none.pk])
        self.assertEqual([c.option for c in answer.choices.all()], [none])
        answer = self.answer("q2-9", option_ids=[neck.pk, shoulders.pk])
        self.assertEqual(
            sorted(c.option.label for c in answer.choices.all()), ["Ombros", "Pescoço"]
        )
        self.assertIsNone(answer.selected_option)
        self.assertEqual(AnswerChoice.objects.count(), 2)
        nothing = self.option("q4-4", "Não pratico")
        walk = self.option("q4-4", "Caminhada")
        with self.assertRaises(ValidationError):
            self.answer("q4-4", option_ids=[walk.pk, nothing.pk])
        with self.assertRaises(ValidationError):
            self.answer("q2-9", option_ids=[])
        with self.assertRaises(ValidationError):
            self.answer("q2-9", option_ids=[walk.pk])
        self.assertEqual(AnswerChoice.objects.count(), 2)

    def test_required_text_and_limits(self):
        with self.assertRaises(ValidationError):
            self.answer("q1-1", text="   ")
        with self.assertRaises(ValidationError):
            self.answer("q1-1", text="x" * 151)
        answer = self.answer("q1-1", text="  Ana Souza  ")
        self.assertEqual(answer.text_value, "Ana Souza")
        self.assertIsNone(answer.selected_option)
        self.answer("q1-2", text="x" * 500)
        with self.assertRaises(ValidationError):
            self.answer("q1-2", text="x" * 501)

    def test_optional_text_and_single_may_stay_blank(self):
        self.assertIsNone(self.answer("q12-3", text=""))
        self.answer("q12-3", text="Quero compartilhar")
        self.assertIsNone(self.answer("q12-3", text=""))
        self.assertFalse(Answer.objects.filter(question__code="q12-3").exists())
        self.assertIsNone(self.answer("q2-12"))
        # Matrícula (seção 1) is optional: blank is accepted and clears it.
        self.answer("q1-2", text="MAT-1")
        self.assertIsNone(self.answer("q1-2", text="  "))
        self.assertFalse(Answer.objects.filter(question__code="q1-2").exists())
        with self.assertRaises(ValidationError):
            self.answer("q2-11")

    def test_other_sector_requires_its_text(self):
        other = self.option("q1-3", "Outro:")
        admin = self.option("q1-3", "Administrativo")

        with self.assertRaises(ValidationError):
            self.answer("q1-3", option_id=other.pk, text=" ")
        answer = self.answer("q1-3", option_id=other.pk, text="Logística")
        self.assertEqual(
            (answer.selected_option, answer.text_value), (other, "Logística")
        )
        answer = self.answer("q1-3", option_id=admin.pk, text="ignorado")
        self.assertEqual((answer.selected_option, answer.text_value), (admin, ""))

    def test_completion_requires_required_unscored_questions(self):
        fill_all = list(ordered_questions(self.questionnaire))
        for question in fill_all:
            if question.code == "q1-1":
                continue
            answer = (
                {"option_id": question.options.order_by("display_order")[0].pk}
                if question.scorable
                else unscored_answer(question, "a")
            )
            record_answer(
                self.user, self.organization, self.assessment.pk, question.pk, **answer
            )
        with self.assertRaises(ValidationError):
            complete_assessment(self.user, self.organization, self.assessment.pk)
        self.answer("q1-1", text="Ana Souza")
        result = complete_assessment(self.user, self.organization, self.assessment.pk)
        self.assertEqual(result.pillars.count(), 9)


class V2ImmutabilityTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.user = make_member("pessoa@example.test", self.organization)
        self.questionnaire = load(V2_FILE)

    def test_published_sections_and_unscored_questions_are_immutable(self):
        section = self.questionnaire.sections.get(number=1)
        name = v2_question(self.questionnaire, "q1-1")
        sector_option = v2_question(self.questionnaire, "q1-3").options.first()

        section.title = "Outro"
        with self.assertRaises(ValidationError):
            section.save()
        with self.assertRaises(ValidationError):
            QuestionnaireSection.objects.create(
                questionnaire=self.questionnaire,
                code="s13",
                number=13,
                title="Nova",
                display_order=13,
            )
        for queryset, values in (
            (QuestionnaireSection.objects.filter(pk=section.pk), {"title": "X"}),
            (Question.objects.filter(pk=name.pk), {"text": "X"}),
            (QuestionOption.objects.filter(pk=sector_option.pk), {"label": "X"}),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                queryset.update(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Question.objects.filter(pk=name.pk).delete()
        with (
            self.assertRaises(IntegrityError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "INSERT INTO assessments_questionnairesection "
                "(questionnaire_id, code, number, title, intro, is_scored, display_order) "
                "VALUES (%s, 's99', 99, 'X', '', false, 99)",
                [self.questionnaire.pk],
            )

    def test_completed_text_and_multiple_answers_are_immutable(self):
        assessment = start_assessment(
            self.user, self.organization, self.questionnaire.pk
        )
        fill(self.user, self.organization, assessment, highest)
        complete_assessment(self.user, self.organization, assessment.pk)
        name = Answer.objects.get(assessment=assessment, question__code="q1-1")
        pain = Answer.objects.get(assessment=assessment, question__code="q2-9")
        choice = pain.choices.first()
        other = pain.question.options.exclude(
            pk__in=pain.choices.values("option")
        ).first()

        with self.assertRaises(ValidationError):
            record_answer(
                self.user, self.organization, assessment.pk, name.question_id, text="X"
            )
        name.text_value = "Outro nome"
        with self.assertRaises(ValidationError):
            name.save()
        with self.assertRaises(ValidationError):
            AnswerChoice.objects.create(answer=pain, option=other)
        with self.assertRaises(ValidationError):
            choice.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.filter(pk=name.pk).update(text_value="Outro nome")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnswerChoice.objects.filter(pk=choice.pk).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnswerChoice.objects.bulk_create([AnswerChoice(answer=pain, option=other)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnswerChoice.objects.filter(pk=choice.pk).update(option=other)

    def test_choice_must_belong_to_the_answer_question(self):
        assessment = start_assessment(
            self.user, self.organization, self.questionnaire.pk
        )
        pain = v2_question(self.questionnaire, "q2-9")
        activity_option = v2_question(self.questionnaire, "q4-4").options.first()
        answer = record_answer(
            self.user,
            self.organization,
            assessment.pk,
            pain.pk,
            option_ids=[pain.options.first().pk],
        )

        with self.assertRaises(ValidationError):
            AnswerChoice.objects.create(answer=answer, option=activity_option)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnswerChoice.objects.bulk_create(
                [AnswerChoice(answer=answer, option=activity_option)]
            )


class V2PrivacyAndTenantTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.other_organization = Organization.objects.create(
            name="Outra", slug="outra"
        )
        self.questionnaire = load(V2_FILE)
        self.manager = make_member(
            "gestor@example.test",
            self.organization,
            Membership.Role.CORPORATE_MANAGER,
        )

    def complete_with_secrets(self, user, index):
        assessment = start_assessment(user, self.organization, self.questionnaire.pk)
        secrets = {
            "q1-1": {"text": f"{SECRET_NAME} {index}"},
            "q1-2": {"text": f"{SECRET_ID}-{index}"},
            "q1-4": {"text": SECRET_ROLE},
            "q12-3": {"text": SECRET_SHARE},
        }
        for question in ordered_questions(self.questionnaire):
            if question.code in secrets:
                answer = secrets[question.code]
            elif question.code == "q1-3":
                other = question.options.get(requires_text=True)
                answer = {"option_id": other.pk, "text": SECRET_SECTOR}
            elif question.scorable:
                answer = {"option_id": question.options.get(code=highest(question)).pk}
            else:
                answer = unscored_answer(question, "a")
            record_answer(user, self.organization, assessment.pk, question.pk, **answer)
        complete_assessment(user, self.organization, assessment.pk)
        return assessment

    def test_manager_report_never_shows_identification_text_or_multiple_choice(self):
        for index in range(5):
            user = make_member(f"pessoa{index}@example.test", self.organization)
            grant_consent(user, self.organization)
            self.complete_with_secrets(user, index)
        self.client.force_login(self.manager)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.organization.pk
        session.save()

        response = self.client.get(reverse("executive_report"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["report"].evaluated, 5)
        html = response.content.decode()
        report = repr(build_executive_report(self.organization, *report_period()))
        multiple_labels = QuestionOption.objects.filter(
            question__section__questionnaire=self.questionnaire,
            question__kind=Question.Kind.MULTIPLE,
        ).values_list("label", flat=True)
        for secret in (
            SECRET_NAME,
            SECRET_ID,
            SECRET_ROLE,
            SECRET_SECTOR,
            SECRET_SHARE,
            "pessoa0@example.test",
            *multiple_labels,
        ):
            self.assertNotIn(secret, html)
            self.assertNotIn(secret, report)

    def test_other_company_cannot_read_or_write_answers(self):
        owner = make_member("dono@example.test", self.organization)
        assessment = self.complete_with_secrets(owner, 1)
        intruder = make_member("intruso@example.test", self.other_organization)
        grant_consent(intruder, self.other_organization)
        name = v2_question(self.questionnaire, "q1-1")
        in_progress = start_assessment(owner, self.organization, self.questionnaire.pk)

        for organization in (self.organization, self.other_organization):
            with self.assertRaises(PermissionDenied):
                record_answer(
                    intruder, organization, in_progress.pk, name.pk, text="invasão"
                )
        self.client.force_login(intruder)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.other_organization.pk
        session.save()
        for url in (
            reverse("assessment_completed", args=[assessment.pk]),
            reverse("assessment_review", args=[in_progress.pk]),
            reverse("assessment_question", args=[in_progress.pk, name.pk]),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404, url)
            self.assertNotContains(response, SECRET_NAME, status_code=404)
        self.assertFalse(Answer.objects.filter(assessment=in_progress).exists())


class V2FlowViewTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.user = make_member("pessoa@example.test", self.organization)
        self.questionnaire = load(V2_FILE)
        self.client.force_login(self.user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.organization.pk
        session.save()

    def start(self):
        hub = self.client.get(reverse("assessment_hub"))
        self.assertContains(hub, 'name="consent"')
        self.client.post(reverse("assessment_start"))
        self.assertFalse(Assessment.objects.exists())
        self.client.post(reverse("assessment_start"), {"consent": "on"})
        return Assessment.objects.get(user=self.user)

    def url(self, assessment, code):
        question = v2_question(self.questionnaire, code)
        return reverse("assessment_question", args=[assessment.pk, question.pk])

    def test_flow_starts_with_identification_and_renders_each_kind(self):
        assessment = self.start()
        first = self.client.get(reverse("assessment_detail", args=[assessment.pk]))
        self.assertRedirects(first, self.url(assessment, "q1-1"))

        name_page = self.client.get(self.url(assessment, "q1-1"))
        self.assertContains(name_page, "IDENTIFICAÇÃO DO COLABORADOR")
        self.assertContains(name_page, 'maxlength="150"')
        self.assertContains(name_page, 'name="text"')
        self.assertContains(name_page, "0/150")
        response = self.client.post(self.url(assessment, "q1-1"), {"text": "Ana Souza"})
        self.assertRedirects(response, self.url(assessment, "q1-2"))

        sector = self.client.get(self.url(assessment, "q1-3"))
        self.assertContains(sector, "Outro:")
        self.assertContains(sector, 'name="other_text"')
        other = QuestionOption.objects.get(
            question__section__questionnaire=self.questionnaire,
            question__code="q1-3",
            requires_text=True,
        )
        missing = self.client.post(self.url(assessment, "q1-3"), {"option": other.pk})
        self.assertContains(missing, "Descreva a opção", status_code=200)

        pain = self.client.get(self.url(assessment, "q2-9"))
        self.assertContains(pain, 'type="checkbox"', count=11)
        self.assertContains(pain, "Pode marcar mais de uma opção.")
        self.assertContains(pain, "2.9")
        none = QuestionOption.objects.get(
            question__section__questionnaire=self.questionnaire,
            question__code="q2-9",
            exclusive=True,
        )
        neck = QuestionOption.objects.get(
            question__section__questionnaire=self.questionnaire,
            question__code="q2-9",
            label="Pescoço",
        )
        combined = self.client.post(
            self.url(assessment, "q2-9"), {"options": [none.pk, neck.pk]}
        )
        self.assertContains(combined, "não pode ser marcada junto", status_code=200)
        self.assertFalse(Answer.objects.filter(question__code="q2-9").exists())

        scale = self.client.get(self.url(assessment, "q11-1"))
        self.assertContains(scale, "De 0 a 10, qual nota você daria para:")
        self.assertContains(scale, 'type="radio"', count=11)

        optional = self.client.post(self.url(assessment, "q12-3"), {"text": ""})
        self.assertRedirects(
            optional, reverse("assessment_review", args=[assessment.pk])
        )

    def test_review_and_map_show_own_answers_and_name(self):
        assessment = self.start()
        Answer.objects.filter(assessment=assessment).delete()
        for question in ordered_questions(self.questionnaire):
            if question.code == "q1-1":
                answer = {"text": "Ana Souza"}
            elif question.code == "q2-9":
                answer = {
                    "option_ids": list(
                        question.options.filter(
                            label__in=["Pescoço", "Ombros"]
                        ).values_list("pk", flat=True)
                    )
                }
            elif question.scorable:
                answer = {"option_id": question.options.get(code=highest(question)).pk}
            else:
                answer = unscored_answer(question, "a")
            record_answer(
                self.user, self.organization, assessment.pk, question.pk, **answer
            )

        review = self.client.get(reverse("assessment_review", args=[assessment.pk]))
        self.assertContains(review, "Ana Souza")
        self.assertContains(review, "Pescoço, Ombros")
        self.assertContains(review, "101 de 101")
        self.client.post(reverse("assessment_complete", args=[assessment.pk]))
        result = self.client.get(reverse("assessment_completed", args=[assessment.pk]))
        self.assertContains(result, "Nome do colaborador")
        self.assertContains(result, "Ana Souza")
        self.assertContains(result, "Data da avaliação")
        self.assertNotContains(result, "Pescoço")
