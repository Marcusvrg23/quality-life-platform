"""Questionnaire v2 must match the official Markdown text exactly. No database."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from assessments.official_markdown import parse_official_markdown

BASE_DIR = Path(settings.BASE_DIR)
OFFICIAL_MD = (
    BASE_DIR / "docs" / "questionario" / "questionario-oficial-quality-life.md"
)
QUESTIONNAIRES = BASE_DIR / "assessments" / "questionnaires"
V1_FILE = QUESTIONNAIRES / "quality_life_oficial_v1.json"
V2_FILE = QUESTIONNAIRES / "quality_life_oficial_v2.json"


def official_sections():
    return parse_official_markdown(OFFICIAL_MD.read_text(encoding="utf-8"))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def json_questions(data):
    return [
        question for section in data["sections"] for question in section["questions"]
    ]


def md_question(number):
    return next(
        question
        for section in official_sections()
        for question in section.questions
        if question.number == number
    )


class OfficialMarkdownParserTests(SimpleTestCase):
    def test_reads_twelve_sections_in_order(self):
        sections = official_sections()

        self.assertEqual([s.number for s in sections], list(range(1, 13)))
        self.assertEqual(sections[0].title, "IDENTIFICAÇÃO DO COLABORADOR")
        self.assertEqual(sections[-1].title, "SUA PRINCIPAL NECESSIDADE")
        self.assertEqual(sections[10].intro, "De 0 a 10, qual nota você daria para:")

    def test_counts_questions_by_kind(self):
        kinds = Counter(q.kind for s in official_sections() for q in s.questions)

        self.assertEqual(
            kinds, Counter({"SINGLE": 84, "SCALE": 11, "TEXT": 4, "MULTIPLE": 2})
        )

    def test_reads_options_and_texts_exactly(self):
        self.assertEqual(
            [o.label for o in md_question("2.10").options],
            ["Não", "Sim", "Talvez", "Não sei"],
        )
        self.assertEqual(len(md_question("4.3").options), 5)
        self.assertIn('"desligar"', md_question("7.7").text)
        self.assertEqual(md_question("2.9").help_text, "Pode marcar mais de uma opção.")
        self.assertEqual(md_question("2.9").kind, "MULTIPLE")
        identification = official_sections()[0].questions
        sector = identification[2]
        self.assertEqual(sector.text, "Setor/Departamento")
        self.assertEqual(sector.options[-1].label, "Outro:")
        self.assertTrue(sector.options[-1].requires_text)
        self.assertFalse(any(o.requires_text for o in sector.options[:-1]))
        overall = official_sections()[10].questions[-1]
        self.assertEqual(
            overall.text, "De forma geral, como você avalia sua qualidade de vida hoje?"
        )
        self.assertEqual(overall.kind, "SCALE")
        self.assertEqual(
            [o.label for o in overall.options], [str(n) for n in range(11)]
        )

    def test_rejects_unexpected_content_inside_a_question(self):
        text = "# 👤 1. TESTE\n\n### Pergunta?\n- ( ) Sim\nlinha solta\n"

        with self.assertRaisesMessage(ValueError, "linha 5"):
            parse_official_markdown(text)

    def test_rejects_mixed_single_and_multiple_options(self):
        text = "# 👤 1. TESTE\n\n### Pergunta?\n- ( ) Sim\n- [ ] Não\n"

        with self.assertRaisesMessage(ValueError, "linha 5"):
            parse_official_markdown(text)


class QuestionnaireV2StructureTests(SimpleTestCase):
    def test_every_question_matches_the_markdown(self):
        data = load(V2_FILE)
        expected = [
            (
                section.number,
                section.title,
                section.intro,
                question.number,
                question.text,
                question.help_text,
                question.kind,
                [(o.label, o.requires_text) for o in question.options],
            )
            for section in official_sections()
            for question in section.questions
        ]
        actual = [
            (
                section["number"],
                section["title"],
                section["intro"],
                question["number"],
                question["text"],
                question["help_text"],
                question["kind"],
                [(o["label"], o["requires_text"]) for o in question["options"]],
            )
            for section in data["sections"]
            for question in section["questions"]
        ]

        self.assertEqual(len(actual), len(expected))
        for position, (got, want) in enumerate(zip(actual, expected, strict=True)):
            self.assertEqual(got, want, f"pergunta {position + 1} difere do .md")

    def test_identity_matches_v1_with_version_two(self):
        v1, v2 = load(V1_FILE), load(V2_FILE)

        self.assertEqual(v2["code"], v1["code"])
        self.assertEqual(v2["version"], 2)
        self.assertEqual(v2["scoring_version"], v1["scoring_version"])
        self.assertEqual(
            v2["pillars"], [pillar["pillar_code"] for pillar in v1["pillars"]]
        )

    def test_scored_questions_keep_v1_scores(self):
        v1, v2 = load(V1_FILE), load(V2_FILE)
        v2_by_code = {q["code"]: q for q in json_questions(v2)}
        v1_count = 0
        for pillar in v1["pillars"]:
            for question in pillar["questions"]:
                v1_count += 1
                twin = v2_by_code[question["code"]]
                self.assertTrue(twin["scorable"], question["code"])
                self.assertEqual(twin["pillar_code"], pillar["pillar_code"])
                v2_options = {o["code"]: o for o in twin["options"]}
                for option in question["options"]:
                    if (question["code"], option["code"]) == ("q4-3", "o6"):
                        self.assertNotIn(option["code"], v2_options)
                        continue
                    same = v2_options[option["code"]]
                    self.assertEqual(same["label"], option["label"])
                    self.assertEqual(same["score_value"], option["score_value"])
                    self.assertEqual(
                        same["counts_for_score"], option["counts_for_score"]
                    )
                self.assertEqual(
                    len(v2_options),
                    len(question["options"]) - (question["code"] == "q4-3"),
                )

        scorable = [q for q in json_questions(v2) if q["scorable"]]
        self.assertEqual(len(scorable), v1_count)
        self.assertEqual(v1_count, 77)

    def test_only_single_and_scale_questions_are_scored(self):
        data = load(V2_FILE)
        for section in data["sections"]:
            for question in section["questions"]:
                if question["scorable"]:
                    self.assertIn(question["kind"], {"SINGLE", "SCALE"})
                    self.assertTrue(section["scored"])
                    self.assertIsNotNone(question["pillar_code"])
                else:
                    self.assertIsNone(question["pillar_code"], question["code"])
        self.assertFalse(data["sections"][0]["scored"])
        self.assertFalse(data["sections"][-1]["scored"])
        self.assertEqual(
            Counter(q["scorable"] for q in json_questions(data)),
            Counter({True: 77, False: 24}),
        )

    def test_exclusive_options_required_flags_and_text_limits(self):
        questions = {q["code"]: q for q in json_questions(load(V2_FILE))}
        exclusive = {
            (code, o["label"])
            for code, q in questions.items()
            for o in q["options"]
            if o["exclusive"]
        }
        self.assertEqual(
            exclusive, {("q2-9", "Não sinto dores"), ("q4-4", "Não pratico")}
        )
        optional = {code for code, q in questions.items() if not q["required"]}
        self.assertEqual(optional, {"q2-12", "q12-3"})
        limits = {
            code: q["max_length"]
            for code, q in questions.items()
            if q["kind"] == "TEXT"
        }
        self.assertEqual(limits, {"q1-1": 150, "q1-2": 500, "q1-4": 500, "q12-3": 500})

    def test_generator_reproduces_the_committed_file(self):
        result = subprocess.run(
            [sys.executable, "scripts/build_questionnaire_v2.py", "--check"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
