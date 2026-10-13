"""Load and publish an official questionnaire from a versioned JSON file."""

import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_slug
from django.db import transaction
from django.db.models import Q

from assessments.models import (
    Pillar,
    Question,
    QuestionnairePillar,
    QuestionnaireSection,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import SCORED_KINDS, publish_questionnaire

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


def _string(data, key, path, max_length):
    value = _require(data, key, path)
    if not isinstance(value, str) or len(value) > max_length:
        _fail(f"{path}.{key}", f"deve ser um texto com até {max_length} caracteres.")
    return value


def _option_spec(raw_option, o_path, display_order=None, *, extended=False):
    option = {
        "code": _code(raw_option, "code", o_path),
        "label": _text(raw_option, "label", o_path, 255),
        "score_value": _decimal(
            raw_option, "score_value", o_path, Decimal(0), Decimal(100)
        ),
        "counts_for_score": _bool(raw_option, "counts_for_score", o_path),
        "display_order": display_order
        or _positive_int(raw_option, "display_order", o_path, MAX_ORDER),
        "exclusive": False,
        "requires_text": False,
    }
    if extended:
        option["exclusive"] = _bool(raw_option, "exclusive", o_path)
        option["requires_text"] = _bool(raw_option, "requires_text", o_path)
    return option


def _question_defaults(question):
    """v1 questions: single choice, scorable, in a pillar, without section."""
    return {
        "section_code": None,
        "number": "",
        "help_text": "",
        "kind": Question.Kind.SINGLE,
        "max_length": None,
        "scorable": True,
        **question,
    }


def _parse_pillars(data, root, pillars):
    """v1 layout: questions grouped by pillar, all scorable single choice."""
    spec_pillars = []
    questions = []
    for p_index, raw_pillar in enumerate(_list(data, "pillars", root)):
        p_path = f"pillars[{p_index}]"
        code = _require(raw_pillar, "pillar_code", p_path)
        pillar = pillars.get(code) if isinstance(code, str) else None
        if pillar is None or not pillar.is_active:
            _fail(f"{p_path}.pillar_code", f"pilar '{code}' inexistente ou inativo.")
        pillar_questions = []
        for q_index, raw_question in enumerate(_list(raw_pillar, "questions", p_path)):
            q_path = f"{p_path}.questions[{q_index}]"
            options = [
                _option_spec(raw_option, f"{q_path}.options[{o_index}]")
                for o_index, raw_option in enumerate(
                    _list(raw_question, "options", q_path)
                )
            ]
            _unique(options, "code", f"{q_path}.options")
            _unique(options, "display_order", f"{q_path}.options")
            pillar_questions.append(
                _question_defaults(
                    {
                        "pillar_code": pillar.code,
                        "code": _code(raw_question, "code", q_path),
                        "text": _text(raw_question, "text", q_path),
                        "required": _bool(raw_question, "required", q_path),
                        "display_order": _positive_int(
                            raw_question, "display_order", q_path, MAX_ORDER
                        ),
                        "options": options,
                    }
                )
            )
        _unique(pillar_questions, "code", f"{p_path}.questions")
        _unique(pillar_questions, "display_order", f"{p_path}.questions")
        questions.extend(pillar_questions)
        spec_pillars.append(pillar)
    return spec_pillars, [], questions


def _parse_sections(data, root, pillars):
    """v2 layout: the official text, section by section, in reading order."""
    spec_pillars = []
    for p_index, code in enumerate(_list(data, "pillars", root)):
        pillar = pillars.get(code) if isinstance(code, str) else None
        if pillar is None or not pillar.is_active:
            _fail(f"pillars[{p_index}]", f"pilar '{code}' inexistente ou inativo.")
        spec_pillars.append(pillar)
    pillar_codes = {pillar.code for pillar in spec_pillars}
    sections = []
    questions = []
    for s_index, raw_section in enumerate(_list(data, "sections", root)):
        s_path = f"sections[{s_index}]"
        section = {
            "code": _code(raw_section, "code", s_path),
            "number": _positive_int(raw_section, "number", s_path, MAX_ORDER),
            "title": _text(raw_section, "title", s_path, 255),
            "intro": _string(raw_section, "intro", s_path, 1000),
            "is_scored": _bool(raw_section, "scored", s_path),
            "display_order": s_index + 1,
        }
        sections.append(section)
        for q_index, raw_question in enumerate(_list(raw_section, "questions", s_path)):
            q_path = f"{s_path}.questions[{q_index}]"
            kind = _require(raw_question, "kind", q_path)
            if kind not in Question.Kind.values:
                _fail(f"{q_path}.kind", f"tipo '{kind}' desconhecido.")
            scorable = _bool(raw_question, "scorable", q_path)
            pillar_code = _require(raw_question, "pillar_code", q_path)
            if scorable != (pillar_code is not None):
                _fail(q_path, "pergunta pontuada exige pilar; não pontuada não tem.")
            if pillar_code is not None and pillar_code not in pillar_codes:
                _fail(f"{q_path}.pillar_code", f"pilar '{pillar_code}' não listado.")
            if scorable and (kind not in SCORED_KINDS or not section["is_scored"]):
                _fail(q_path, "só escolha única ou escala em seção pontuada pontua.")
            max_length = _require(raw_question, "max_length", q_path)
            raw_options = _require(raw_question, "options", q_path)
            if kind == Question.Kind.TEXT:
                max_length = _positive_int(
                    raw_question, "max_length", q_path, Question.MAX_TEXT_LENGTH
                )
                if raw_options != []:
                    _fail(f"{q_path}.options", "pergunta de texto não tem opções.")
            elif max_length is not None:
                _fail(f"{q_path}.max_length", "só pergunta de texto tem limite.")
            options = []
            if kind != Question.Kind.TEXT:
                for o_index, raw_option in enumerate(
                    _list(raw_question, "options", q_path)
                ):
                    o_path = f"{q_path}.options[{o_index}]"
                    option = _option_spec(
                        raw_option, o_path, o_index + 1, extended=True
                    )
                    if option["exclusive"] and kind != Question.Kind.MULTIPLE:
                        _fail(o_path, "só múltipla escolha tem opção exclusiva.")
                    if option["requires_text"] and kind != Question.Kind.SINGLE:
                        _fail(o_path, "só escolha única tem opção com texto.")
                    options.append(option)
                _unique(options, "code", f"{q_path}.options")
            questions.append(
                {
                    "pillar_code": pillar_code,
                    "section_code": section["code"],
                    "code": _code(raw_question, "code", q_path),
                    "number": _string(raw_question, "number", q_path, 8),
                    "text": _text(raw_question, "text", q_path),
                    "help_text": _string(raw_question, "help_text", q_path, 1000),
                    "kind": kind,
                    "max_length": max_length,
                    "required": _bool(raw_question, "required", q_path),
                    "scorable": scorable,
                    "display_order": len(questions) + 1,
                    "options": options,
                }
            )
    _unique(sections, "code", "sections")
    _unique(sections, "number", "sections")
    _unique(questions, "code", "sections[].questions")
    return spec_pillars, sections, questions


def parse_questionnaire(data):
    """Validate the whole file before any write and return a normalized spec."""
    root = "arquivo"
    spec = {
        "code": _code(data, "code", root),
        "version": _positive_int(data, "version", root),
        "title": _text(data, "title", root, 255),
        "scoring_version": _text(data, "scoring_version", root, 32),
    }
    pillar_weight = _decimal(data, "pillar_weight", root, CENT, MAX_WEIGHT)
    question_weight = _decimal(data, "question_weight", root, CENT, MAX_WEIGHT)
    pillars = {pillar.code: pillar for pillar in Pillar.objects.all()}
    parse = _parse_sections if "sections" in data else _parse_pillars
    spec_pillars, sections, questions = parse(data, root, pillars)
    codes = [pillar.code for pillar in spec_pillars]
    expected = {code for code, pillar in pillars.items() if pillar.is_active}
    if len(codes) != len(set(codes)) or set(codes) != expected or len(codes) != 9:
        _fail("pillars", "deve conter exatamente os 9 pilares ativos, sem repetição.")
    for question in questions:
        question["weight"] = question_weight
    spec["pillars"] = [
        {"pillar": pillar, "display_order": index, "weight": pillar_weight}
        for index, pillar in enumerate(spec_pillars, start=1)
    ]
    spec["sections"] = sections
    spec["questions"] = questions
    return spec


def _question_row(pillar_code, section_code, question, options):
    return (
        pillar_code or "",
        section_code or "",
        question["code"],
        question["number"],
        question["text"],
        question["help_text"],
        question["kind"],
        question["max_length"],
        question["required"],
        question["scorable"],
        question["score_direction"],
        question["weight"],
        question["display_order"],
        question["is_active"],
        tuple(
            (
                option["code"],
                option["label"],
                option["score_value"],
                option["counts_for_score"],
                option["exclusive"],
                option["requires_text"],
                option["display_order"],
            )
            for option in sorted(options, key=lambda o: o["display_order"])
        ),
    )


def _rows(rows):
    return tuple(sorted(rows, key=lambda row: row[:3]))


def _spec_snapshot(spec):
    return (
        spec["title"],
        spec["scoring_version"],
        tuple(
            (item["pillar"].code, item["display_order"], item["weight"], True)
            for item in spec["pillars"]
        ),
        tuple(
            (
                section["code"],
                section["number"],
                section["title"],
                section["intro"],
                section["is_scored"],
                section["display_order"],
            )
            for section in spec["sections"]
        ),
        _rows(
            _question_row(
                question["pillar_code"],
                question["section_code"],
                {
                    **question,
                    "score_direction": Question.Direction.NORMAL,
                    "is_active": True,
                },
                question["options"],
            )
            for question in spec["questions"]
        ),
    )


def _db_snapshot(questionnaire):
    option_fields = (
        "code",
        "label",
        "score_value",
        "counts_for_score",
        "exclusive",
        "requires_text",
        "display_order",
    )
    questions = (
        Question.objects.filter(
            Q(questionnaire_pillar__questionnaire=questionnaire)
            | Q(section__questionnaire=questionnaire)
        )
        .select_related("questionnaire_pillar__pillar", "section")
        .prefetch_related("options")
    )
    return (
        questionnaire.title,
        questionnaire.scoring_version,
        tuple(
            (item.pillar.code, item.display_order, item.weight, item.is_active)
            for item in questionnaire.pillars.select_related("pillar")
        ),
        tuple(
            (
                section.code,
                section.number,
                section.title,
                section.intro,
                section.is_scored,
                section.display_order,
            )
            for section in questionnaire.sections.all()
        ),
        _rows(
            _question_row(
                question.questionnaire_pillar
                and question.questionnaire_pillar.pillar.code,
                question.section and question.section.code,
                {
                    "code": question.code,
                    "number": question.number,
                    "text": question.text,
                    "help_text": question.help_text,
                    "kind": question.kind,
                    "max_length": question.max_length,
                    "required": question.required,
                    "scorable": question.scorable,
                    "score_direction": question.score_direction,
                    "weight": question.weight,
                    "display_order": question.display_order,
                    "is_active": question.is_active,
                },
                [
                    {field: getattr(option, field) for field in option_fields}
                    for option in question.options.all()
                ],
            )
            for question in questions
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
        configured = {
            item["pillar"].code: QuestionnairePillar.objects.create(
                questionnaire=questionnaire,
                pillar=item["pillar"],
                display_order=item["display_order"],
                weight=item["weight"],
            )
            for item in spec["pillars"]
        }
        sections = {
            item["code"]: QuestionnaireSection.objects.create(
                questionnaire=questionnaire, **item
            )
            for item in spec["sections"]
        }
        option_count = 0
        for question_spec in spec["questions"]:
            fields = {
                key: value
                for key, value in question_spec.items()
                if key not in ("pillar_code", "section_code", "options")
            }
            question = Question.objects.create(
                questionnaire_pillar=configured.get(question_spec["pillar_code"]),
                section=sections.get(question_spec["section_code"]),
                score_direction=Question.Direction.NORMAL,
                **fields,
            )
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
        sections_note = f", {len(sections)} seções" if sections else ""
        return (
            f"Questionário {label} publicado: {len(spec['pillars'])} pilares, "
            f"{len(spec['questions'])} perguntas, {option_count} opções"
            f"{sections_note}.{retired}"
        )
