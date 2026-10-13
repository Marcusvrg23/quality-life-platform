"""Generate assessments/questionnaires/quality_life_oficial_v2.json.

Text, order, kind and options come from the official Markdown. Scoring comes
from v1 unchanged: every v1 question keeps its code, pillar and the score of
each option (matched by label). Everything new in the text is not scorable.

    python scripts/build_questionnaire_v2.py          # write the JSON
    python scripts/build_questionnaire_v2.py --check  # fail if it is stale
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from assessments.official_markdown import (
    MULTIPLE,
    SCALE,
    TEXT,
    parse_official_markdown,
)

SOURCE = "docs/questionario/questionario-oficial-quality-life.md"
V1_FILE = BASE_DIR / "assessments" / "questionnaires" / "quality_life_oficial_v1.json"
V2_FILE = BASE_DIR / "assessments" / "questionnaires" / "quality_life_oficial_v2.json"

# Product decisions (handoff 06): not derivable from the text itself.
UNSCORED_SECTIONS = {1, 12}
OPTIONAL = {"q1-2", "q2-12", "q12-3"}
EXCLUSIVE = {"q2-9": "Não sinto dores", "q4-4": "Não pratico"}
TEXT_LIMITS = {"q1-1": 150}
DEFAULT_TEXT_LIMIT = 500
# v1 options that the official text does not have. Only this one may drop.
DROPPED_V1_OPTIONS = {("q4-3", "Não pratico atividade física")}
OVERALL_CODE = "q11-geral"


def _straight_quotes(text):
    return text.replace("“", '"').replace("”", '"')


def _codes(section):
    """Stable question codes: v1 codes for numbered and 0-10 questions."""
    codes = []
    scale_index = 0
    for position, question in enumerate(section.questions, start=1):
        if question.number:
            codes.append("q" + question.number.replace(".", "-"))
        elif section.number == 11 and question.text.startswith("De forma geral"):
            codes.append(OVERALL_CODE)
        elif section.number == 11:
            scale_index += 1
            codes.append(f"q11-{scale_index}")
        else:
            codes.append(f"q{section.number}-{position}")
    return codes


def _v1_questions(v1):
    return {
        question["code"]: (pillar["pillar_code"], question)
        for pillar in v1["pillars"]
        for question in pillar["questions"]
    }


def _scored_options(code, md_question, v1_question):
    v1_text = _straight_quotes(v1_question["text"])
    if md_question.number:
        if v1_text != md_question.text:
            raise SystemExit(f"{code}: texto do v1 difere do .md: {v1_text!r}")
    elif not v1_text.lower().endswith(md_question.text.lower()):
        raise SystemExit(f"{code}: escala do v1 não corresponde: {v1_text!r}")
    by_label = {option["label"]: option for option in v1_question["options"]}
    options = []
    for md_option in md_question.options:
        source = by_label.pop(md_option.label, None)
        if source is None or md_option.requires_text:
            raise SystemExit(f"{code}: opção {md_option.label!r} sem pontuação no v1")
        options.append(
            {
                "code": source["code"],
                "label": md_option.label,
                "score_value": source["score_value"],
                "counts_for_score": source["counts_for_score"],
                "exclusive": False,
                "requires_text": False,
            }
        )
    leftover = {(code, label) for label in by_label}
    if leftover - DROPPED_V1_OPTIONS:
        raise SystemExit(f"{code}: opções do v1 ausentes no .md: {sorted(leftover)}")
    return options


def _unscored_options(code, md_question):
    options = [
        {
            "code": f"o{position}",
            "label": option.label,
            "score_value": 0,
            "counts_for_score": False,
            "exclusive": EXCLUSIVE.get(code) == option.label,
            "requires_text": option.requires_text,
        }
        for position, option in enumerate(md_question.options, start=1)
    ]
    if code in EXCLUSIVE and not any(option["exclusive"] for option in options):
        raise SystemExit(f"{code}: opção exclusiva {EXCLUSIVE[code]!r} não encontrada")
    return options


def build(markdown, v1):
    sections = parse_official_markdown(markdown)
    v1_questions = _v1_questions(v1)
    used = set()
    data = {
        "code": v1["code"],
        "version": 2,
        "title": v1["title"],
        "scoring_version": v1["scoring_version"],
        "status_note": v1["status_note"],
        "source": SOURCE,
        "generated_by": "scripts/build_questionnaire_v2.py",
        "pillar_weight": v1["pillar_weight"],
        "question_weight": v1["question_weight"],
        "pillars": [pillar["pillar_code"] for pillar in v1["pillars"]],
        "sections": [],
    }
    for section in sections:
        questions = []
        for code, md_question in zip(_codes(section), section.questions, strict=True):
            scored = v1_questions.get(code)
            if scored and section.number in UNSCORED_SECTIONS:
                raise SystemExit(f"{code}: pergunta pontuada em seção não pontuada")
            if scored:
                used.add(code)
                pillar_code, v1_question = scored
                options = _scored_options(code, md_question, v1_question)
            else:
                pillar_code = None
                options = _unscored_options(code, md_question)
            questions.append(
                {
                    "code": code,
                    "number": md_question.number,
                    "text": md_question.text,
                    "help_text": md_question.help_text,
                    "kind": md_question.kind,
                    "required": code not in OPTIONAL,
                    "scorable": scored is not None,
                    "pillar_code": pillar_code,
                    "max_length": (
                        TEXT_LIMITS.get(code, DEFAULT_TEXT_LIMIT)
                        if md_question.kind == TEXT
                        else None
                    ),
                    "options": [] if md_question.kind == TEXT else options,
                }
            )
            if scored and md_question.kind not in {"SINGLE", SCALE}:
                raise SystemExit(f"{code}: pergunta pontuada deve ser de escolha única")
            if md_question.kind == MULTIPLE and scored:
                raise SystemExit(f"{code}: múltipla escolha não pode pontuar")
        data["sections"].append(
            {
                "code": f"s{section.number}",
                "number": section.number,
                "title": section.title,
                "intro": section.intro,
                "scored": section.number not in UNSCORED_SECTIONS,
                "questions": questions,
            }
        )
    missing = set(v1_questions) - used
    if missing:
        raise SystemExit(
            f"Perguntas pontuadas do v1 ausentes no .md: {sorted(missing)}"
        )
    return data


def render(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    markdown = (BASE_DIR / SOURCE).read_text(encoding="utf-8")
    v1 = json.loads(V1_FILE.read_text(encoding="utf-8"))
    content = render(build(markdown, v1))
    if args.check:
        current = V2_FILE.read_text(encoding="utf-8") if V2_FILE.exists() else ""
        if current != content:
            print(f"{V2_FILE.name} desatualizado: rode {Path(__file__).name}.")
            return 1
        print(f"{V2_FILE.name} confere com o .md oficial.")
        return 0
    V2_FILE.write_text(content, encoding="utf-8", newline="\n")
    print(f"Gerado {V2_FILE.relative_to(BASE_DIR)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
