"""Load and publish an official questionnaire from a versioned JSON file."""

import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_slug
from django.db import transaction

from assessments.models import (
    Pillar,
    Question,
    QuestionnairePillar,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import publish_questionnaire

CENT = Decimal("0.01")
MAX_WEIGHT = Decimal("999999.99")
MAX_ORDER = 32767


def _fail(path, message):
    raise CommandError(f"{path}: {message}")


def _require(data, key, path):
    if not isinstance(data, dict):
        _fail(path, "deve ser um objeto.")
    if key not in data:
        _fail(f"{path}.{key}", "campo obrigatório ausente.")
    return data[key]


def _code(data, key, path):
    value = _require(data, key, path)
    try:
        if not isinstance(value, str) or len(value) > 64:
            raise ValidationError("invalid")
        validate_slug(value)
    except ValidationError:
        _fail(f"{path}.{key}", "deve ser um slug com até 64 caracteres.")
    return value


def _text(data, key, path, max_length=None):
    value = _require(data, key, path)
    if not isinstance(value, str) or not value.strip():
        _fail(f"{path}.{key}", "deve ser um texto não vazio.")
    if max_length and len(value) > max_length:
        _fail(f"{path}.{key}", f"deve ter até {max_length} caracteres.")
    return value


def _bool(data, key, path):
    value = _require(data, key, path)
    if not isinstance(value, bool):
        _fail(f"{path}.{key}", "deve ser true ou false.")
    return value


def _positive_int(data, key, path, maximum=None):
    value = _require(data, key, path)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{path}.{key}", "deve ser um inteiro positivo.")
    if maximum and value > maximum:
        _fail(f"{path}.{key}", f"deve ser no máximo {maximum}.")
    return value


def _decimal(data, key, path, minimum, maximum):
    value = _require(data, key, path)
    if isinstance(value, bool) or not isinstance(value, int | Decimal):
        _fail(f"{path}.{key}", "deve ser um número.")
    value = Decimal(value)
    if (
        not value.is_finite()
        or value < minimum
        or value > maximum
        or value != value.quantize(CENT)
    ):
        _fail(
            f"{path}.{key}",
            f"deve estar entre {minimum} e {maximum} com até 2 casas decimais.",
        )
    return value


def _list(data, key, path):
    value = _require(data, key, path)
    if not isinstance(value, list) or not value:
        _fail(f"{path}.{key}", "deve ser uma lista não vazia.")
    return value


def _unique(items, key, path):
    seen = set()
    for item in items:
        if item[key] in seen:
            _fail(path, f"{key} '{item[key]}' repetido.")
        seen.add(item[key])


def parse_questionnaire(data):
    """Validate the whole file before any write and return a normalized spec."""
    root = "arquivo"
    spec = {
        "code": _code(data, "code", root),
        "version": _positive_int(data, "version", root),
        "title": _text(data, "title", root, 255),
        "scoring_version": _text(data, "scoring_version", root, 32),
        "pillars": [],
    }
    pillar_weight = _decimal(data, "pillar_weight", root, CENT, MAX_WEIGHT)
    question_weight = _decimal(data, "question_weight", root, CENT, MAX_WEIGHT)
    pillars = {pillar.code: pillar for pillar in Pillar.objects.all()}
    for p_index, raw_pillar in enumerate(_list(data, "pillars", root)):
        p_path = f"pillars[{p_index}]"
        code = _require(raw_pillar, "pillar_code", p_path)
        pillar = pillars.get(code) if isinstance(code, str) else None
        if pillar is None or not pillar.is_active:
            _fail(f"{p_path}.pillar_code", f"pilar '{code}' inexistente ou inativo.")
        questions = []
        for q_index, raw_question in enumerate(_list(raw_pillar, "questions", p_path)):
            q_path = f"{p_path}.questions[{q_index}]"
            options = []
            for o_index, raw_option in enumerate(
                _list(raw_question, "options", q_path)
            ):
                o_path = f"{q_path}.options[{o_index}]"
                options.append(
                    {
                        "code": _code(raw_option, "code", o_path),
                        "label": _text(raw_option, "label", o_path, 255),
                        "score_value": _decimal(
                            raw_option, "score_value", o_path, Decimal(0), Decimal(100)
                        ),
                        "counts_for_score": _bool(
                            raw_option, "counts_for_score", o_path
                        ),
                        "display_order": _positive_int(
                            raw_option, "display_order", o_path, MAX_ORDER
                        ),
                    }
                )
            _unique(options, "code", f"{q_path}.options")
            _unique(options, "display_order", f"{q_path}.options")
            questions.append(
                {
                    "code": _code(raw_question, "code", q_path),
                    "text": _text(raw_question, "text", q_path),
                    "required": _bool(raw_question, "required", q_path),
                    "display_order": _positive_int(
                        raw_question, "display_order", q_path, MAX_ORDER
                    ),
                    "weight": question_weight,
                    "options": options,
                }
            )
        _unique(questions, "code", f"{p_path}.questions")
        _unique(questions, "display_order", f"{p_path}.questions")
        spec["pillars"].append(
            {
                "pillar": pillar,
                "display_order": p_index + 1,
                "weight": pillar_weight,
                "questions": questions,
            }
        )
    codes = [configured["pillar"].code for configured in spec["pillars"]]
    expected = {code for code, pillar in pillars.items() if pillar.is_active}
    if len(codes) != len(set(codes)) or set(codes) != expected or len(codes) != 9:
        _fail("pillars", "deve conter exatamente os 9 pilares ativos, sem repetição.")
    return spec


def _spec_snapshot(spec):
    return (
        spec["title"],
        spec["scoring_version"],
        tuple(
            (
                configured["pillar"].code,
                configured["display_order"],
                configured["weight"],
                True,
                tuple(
                    (
                        question["code"],
                        question["text"],
                        question["required"],
                        True,
                        Question.Direction.NORMAL,
                        question["weight"],
                        question["display_order"],
                        True,
                        tuple(
                            (
                                option["code"],
                                option["label"],
                                option["score_value"],
                                option["counts_for_score"],
                                option["display_order"],
                            )
                            for option in sorted(
                                question["options"], key=lambda o: o["display_order"]
                            )
                        ),
                    )
                    for question in sorted(
                        configured["questions"], key=lambda q: q["display_order"]
                    )
                ),
            )
            for configured in spec["pillars"]
        ),
    )


def _db_snapshot(questionnaire):
    return (
        questionnaire.title,
        questionnaire.scoring_version,
        tuple(
            (
                configured.pillar.code,
                configured.display_order,
                configured.weight,
                configured.is_active,
                tuple(
                    (
                        question.code,
                        question.text,
                        question.required,
                        question.scorable,
                        question.score_direction,
                        question.weight,
                        question.display_order,
                        question.is_active,
                        tuple(
                            (
                                option.code,
                                option.label,
                                option.score_value,
                                option.counts_for_score,
                                option.display_order,
                            )
                            for option in question.options.all()
                        ),
                    )
                    for question in configured.questions.all()
                ),
            )
            for configured in questionnaire.pillars.select_related(
                "pillar"
            ).prefetch_related("questions__options")
        ),
    )


class Command(BaseCommand):
    help = "Load and publish the official Quality Life questionnaire from JSON."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument(
            "--retire-other-published",
            action="store_true",
            help="Move other PUBLISHED questionnaires to RETIRED.",
        )

    def handle(self, *args, **options):
        try:
            with open(options["file"], encoding="utf-8") as handle:
                data = json.load(handle, parse_float=Decimal)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"Não foi possível ler o arquivo: {exc}") from exc
        spec = parse_questionnaire(data)
        label = f"{spec['code']} v{spec['version']}"
        try:
            with transaction.atomic():
                summary = self._load(spec, label, options["retire_other_published"])
        except ValidationError as exc:
            raise CommandError(f"Questionário inválido: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(summary))

    def _load(self, spec, label, retire_other_published):
        existing = (
            QuestionnaireVersion.objects.select_for_update()
            .filter(code=spec["code"], version=spec["version"])
            .first()
        )
        if existing:
            if existing.status == QuestionnaireVersion.Status.PUBLISHED and (
                _db_snapshot(existing) == _spec_snapshot(spec)
            ):
                return f"Questionário {label} já carregado; nada a fazer."
            raise CommandError(
                f"Questionário {label} já existe ({existing.status}) com conteúdo "
                "diferente do arquivo. Aumente a versão no arquivo."
            )
        others = list(
            QuestionnaireVersion.objects.select_for_update().filter(
                status=QuestionnaireVersion.Status.PUBLISHED
            )
        )
        if others and not retire_other_published:
            published = ", ".join(f"{q.code} v{q.version}" for q in others)
            raise CommandError(
                f"Já existe questionário publicado ({published}). O fluxo de "
                "avaliação exige exatamente um. Use --retire-other-published "
                "para aposentá-lo(s)."
            )
        questionnaire = QuestionnaireVersion.objects.create(
            code=spec["code"],
            version=spec["version"],
            title=spec["title"],
            scoring_version=spec["scoring_version"],
        )
        question_count = option_count = 0
        for configured_spec in spec["pillars"]:
            configured = QuestionnairePillar.objects.create(
                questionnaire=questionnaire,
                pillar=configured_spec["pillar"],
                display_order=configured_spec["display_order"],
                weight=configured_spec["weight"],
            )
            for question_spec in configured_spec["questions"]:
                question = Question.objects.create(
                    questionnaire_pillar=configured,
                    code=question_spec["code"],
                    text=question_spec["text"],
                    required=question_spec["required"],
                    scorable=True,
                    score_direction=Question.Direction.NORMAL,
                    weight=question_spec["weight"],
                    display_order=question_spec["display_order"],
                )
                question_count += 1
                for option_spec in question_spec["options"]:
                    QuestionOption.objects.create(question=question, **option_spec)
                    option_count += 1
        for other in others:
            other.status = QuestionnaireVersion.Status.RETIRED
            other.save(update_fields=["status", "updated_at"])
        publish_questionnaire(questionnaire.pk)
        retired = "".join(
            f"\nAposentado: {other.code} v{other.version}." for other in others
        )
        return (
            f"Questionário {label} publicado: {len(spec['pillars'])} pilares, "
            f"{question_count} perguntas, {option_count} opções.{retired}"
        )
