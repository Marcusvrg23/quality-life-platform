"""Gabarito independente da pontuação do questionário v2.

Lê SÓ o JSON oficial. Não importa Django, `assessments.services` nem models:
se o sistema e este arquivo concordarem, a conta foi feita duas vezes de
formas diferentes e deu o mesmo número.

Regras (proposta "oficial-v1", aguardando aprovação da Quality Life):
- Só contam perguntas com `scorable: true` ligadas a um pilar.
- Nota da pergunta = `score_value` da opção marcada. Opção com
  `counts_for_score: false` não entra na conta daquele pilar.
- Nota do pilar = média ponderada (peso `question_weight`) das perguntas que
  contaram, arredondada para 2 casas (meio para cima).
- Nota geral = média ponderada (peso `pillar_weight`) das notas dos pilares
  ainda sem arredondar; depois arredonda para 2 casas.
- Faixa da nota arredondada: abaixo de 40 PRIORIDADE, abaixo de 70 ATENÇÃO,
  abaixo de 85 BOM, senão EXCELENTE.
"""

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

JSON_PATH = (
    Path(__file__).resolve().parent.parent
    / "assessments"
    / "questionnaires"
    / "quality_life_oficial_v2.json"
)
TWO_PLACES = Decimal("0.01")
REVERSE = "REVERSE"


def load(path=JSON_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)


def questions(data):
    """Todas as perguntas, na ordem do texto oficial."""
    return [q for section in data["sections"] for q in section["questions"]]


def question_label(question):
    """Número que o cliente lê no texto oficial: 2.1, 11.3, Identificação..."""
    if question["number"]:
        return question["number"]
    section, _, item = question["code"][1:].partition("-")
    return f"{section}.{item}"


def band(score):
    if score < 40:
        return "PRIORIDADE"
    if score < 70:
        return "ATENÇÃO"
    if score < 85:
        return "BOM"
    return "EXCELENTE"


def rounded(value):
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Item:
    question: str  # número da pergunta, ex. "2.1"
    option: str  # texto da opção marcada
    value: Decimal | None  # None = opção que não conta ponto


@dataclass(frozen=True)
class PillarScore:
    raw: Decimal
    score: Decimal
    band: str
    items: tuple[Item, ...]


@dataclass(frozen=True)
class Scores:
    pillars: dict  # código do pilar -> PillarScore, na ordem do JSON
    overall: Decimal
    overall_band: str


def score(data, answers):
    """`answers`: código da pergunta -> código da opção marcada.

    Perguntas que não pontuam podem vir ou não; são ignoradas.
    """
    question_weight = Decimal(data["question_weight"])
    pillar_weight = Decimal(data["pillar_weight"])
    sums = {code: [Decimal(0), Decimal(0), []] for code in data["pillars"]}
    for question in questions(data):
        if not question["scorable"]:
            continue
        chosen = answers.get(question["code"])
        if chosen is None:
            if question["required"]:
                raise ValueError(
                    f"Pergunta obrigatória sem resposta: {question['code']}"
                )
            continue
        option = next(o for o in question["options"] if o["code"] == chosen)
        bucket = sums[question["pillar_code"]]
        if not option["counts_for_score"]:
            bucket[2].append(Item(question_label(question), option["label"], None))
            continue
        value = Decimal(option["score_value"])
        if question.get("score_direction") == REVERSE:
            value = 100 - value
        bucket[0] += value * question_weight
        bucket[1] += question_weight
        bucket[2].append(Item(question_label(question), option["label"], value))
    pillars = {}
    overall_sum = Decimal(0)
    for code, (total, weight, items) in sums.items():
        if not weight:
            raise ValueError(f"Pilar sem pergunta que conte ponto: {code}")
        raw = total / weight
        pillars[code] = PillarScore(raw, rounded(raw), band(rounded(raw)), tuple(items))
        overall_sum += raw * pillar_weight
    overall = rounded(overall_sum / (pillar_weight * len(pillars)))
    return Scores(pillars, overall, band(overall))
