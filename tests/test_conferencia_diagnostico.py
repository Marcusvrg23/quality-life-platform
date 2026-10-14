"""Conferência do diagnóstico v2: telas, pontuação contra o gabarito e relatório.

Tudo que a pessoa faz passa pelas telas (cliente HTTP com CSRF ligado, GET da
página e POST do formulário, como o navegador). O resultado salvo é comparado
com `tests/oracle_v2.py`, que calcula sozinho a partir do JSON oficial.
"""

import os
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from assessments.models import (
    Answer,
    Assessment,
    AssessmentResult,
    Pillar,
    PillarResult,
    Question,
    QuestionnaireVersion,
)
from assessments.services import complete_assessment, record_answer, start_assessment
from identity.models import Membership, Organization

from . import oracle_v2 as oracle
from . import perfis_v2 as perfis

PASSWORD = "senha-de-teste-conferencia"
CSRF_FIELD = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
DOC_PATH = Path(settings.BASE_DIR) / "docs" / "qa" / "conferencia-diagnostico.md"
DOC_NAME = "conferencia-diagnostico.md"
REPORT_PROFILES = ("a", "b", "c", "d", "e")
BANDS = ("EXCELENTE", "BOM", "ATENÇÃO", "PRIORIDADE")
BAND_NAMES = {
    "EXCELENTE": "Excelente",
    "BOM": "Bom",
    "ATENÇÃO": "Atenção",
    "PRIORIDADE": "Prioridade",
}
# Matriz de prioridade como descrita na proposta do relatório (em ordem).
IMMEDIATE = "Prioridade imediata"
HIGH = "Prioridade alta"
MODERATE = "Prioridade moderada"
MAINTENANCE = "Manutenção"
PRIORITY_ORDER = (IMMEDIATE, HIGH, MODERATE, MAINTENANCE)
NOT_FOUND_OR_FORBIDDEN = (403, 404)


def load_v2():
    call_command(
        "load_official_questionnaire",
        file=str(oracle.JSON_PATH),
        retire_other_published=True,
        stdout=StringIO(),
    )
    data = oracle.load()
    return QuestionnaireVersion.objects.get(code=data["code"], version=data["version"])


def make_member(email, organization, role=Membership.Role.COLLABORATOR):
    user = get_user_model().objects.create_user(email=email, password=PASSWORD)
    Membership.objects.create(user=user, organization=organization, role=role)
    return user


class Screens:
    """Tradução código do JSON <-> ids que aparecem nas telas."""

    def __init__(self, version, data):
        self.data = data
        self.kinds = {q["code"]: q["kind"] for q in oracle.questions(data)}
        self.by_pk = {}
        self.pks = {}
        self.options = {}
        for question in Question.objects.filter(
            section__questionnaire=version
        ).prefetch_related("options"):
            self.by_pk[question.pk] = question.code
            self.pks[question.code] = question.pk
            for option in question.options.all():
                self.options[question.code, option.code] = option.pk

    def url(self, assessment_id, code):
        return reverse("assessment_question", args=[assessment_id, self.pks[code]])

    def form(self, code, spec):
        """Campos que o navegador envia para esta resposta."""
        kind = self.kinds[code]
        if spec is None:
            return {"text": ""} if kind == "TEXT" else {}
        if kind == "TEXT":
            return {"text": spec["text"]}
        if kind == "MULTIPLE":
            return {"options": [self.options[code, o] for o in spec["options"]]}
        form = {"option": self.options[code, spec["option"]]}
        if spec.get("text"):
            form["other_text"] = spec["text"]
        return form


class Browser:
    """Uma pessoa usando o app: GET da página, POST do formulário com CSRF."""

    def __init__(self, email):
        self.client = Client(enforce_csrf_checks=True)
        self.token = ""
        self.get(reverse("login"))
        response = self.post(
            reverse("login"), {"username": email, "password": PASSWORD}
        )
        expect(response.status_code == 302, f"login falhou para {email}")

    def get(self, url):
        response = self.client.get(url)
        found = CSRF_FIELD.search(response.content.decode())
        if found:
            self.token = found.group(1)
        return response

    def post(self, url, data=None):
        return self.client.post(
            url, {"csrfmiddlewaretoken": self.token, **(data or {})}
        )

    def start(self):
        self.get(reverse("assessment_hub"))
        response = self.post(reverse("assessment_start"), {"consent": "on"})
        expect(response.status_code == 302, "não iniciou a avaliação")
        return resolve(response["Location"]).kwargs["assessment_id"]

    def answer(self, url, screens, code, spec):
        page = self.get(url)
        expect(page.status_code == 200, f"{code}: página {page.status_code}")
        html = page.content.decode()
        for value in screens.form(code, spec).values():
            for pk in value if isinstance(value, list) else [value]:
                if isinstance(pk, int):
                    expect(f'value="{pk}"' in html, f"{code}: opção {pk} fora da tela")
        return self.post(url, screens.form(code, spec))

    def fill(self, screens, plan):
        """Responde na ordem que as telas mostram. Devolve (id, ordem visitada)."""
        assessment_id = self.start()
        url = self.get(reverse("assessment_detail", args=[assessment_id]))["Location"]
        visited = []
        while resolve(url).url_name == "assessment_question":
            code = screens.by_pk[resolve(url).kwargs["question_id"]]
            response = self.answer(url, screens, code, plan[code])
            expect(response.status_code == 302, f"{code}: resposta recusada")
            visited.append(code)
            url = response["Location"]
        expect(resolve(url).url_name == "assessment_review", f"parou em {url}")
        return assessment_id, visited

    def complete(self, assessment_id):
        self.get(reverse("assessment_review", args=[assessment_id]))
        return self.post(reverse("assessment_complete", args=[assessment_id]))

    def revoke_consent(self):
        self.get(reverse("privacy_settings"))
        response = self.post(reverse("privacy_revoke"), {"confirm": "on"})
        expect(response.status_code == 302, "revogação falhou")


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def system_scores(assessment_id):
    result = AssessmentResult.objects.get(assessment_id=assessment_id)
    pillars = {
        item.pillar.code: (item.score, item.band)
        for item in PillarResult.objects.filter(
            assessment_result=result
        ).select_related("pillar")
    }
    return result, pillars


def complete_by_service(user, organization, version, screens, plan, when):
    """Avaliação extra (histórico): mesmas regras do sistema, data controlada."""
    assessment = start_assessment(user, organization, version.pk)
    for code, spec in plan.items():
        if spec is None:
            continue
        form = screens.form(code, spec)
        record_answer(
            user,
            organization,
            assessment.pk,
            screens.pks[code],
            form.get("option"),
            option_ids=form.get("options"),
            text=form.get("text") or form.get("other_text"),
        )
    with mock.patch("django.utils.timezone.now", return_value=when):
        complete_assessment(user, organization, assessment.pk)
    return assessment


# ---------------------------------------------------------------- relatório


def half_up(value, places="0.01"):
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def share(part, whole):
    return int(half_up(Decimal(part) * 100 / whole, "1"))


def priority(average, affected):
    if average < 40:
        return IMMEDIATE
    if average < 70:
        return HIGH if affected >= 50 else MODERATE
    return MAINTENANCE


@dataclass(frozen=True)
class ExpectedPillar:
    code: str
    scores: tuple
    average: Decimal
    band: str
    distribution: tuple
    affected: int
    priority: str


@dataclass(frozen=True)
class ExpectedReport:
    overall: Decimal
    overall_band: str
    pillars: dict
    lowest: tuple
    highest: tuple
    investments: tuple


def expected_report(data, people):
    """Conta do relatório feita no teste, a partir das notas do gabarito."""
    count = len(people)
    order = {code: index for index, code in enumerate(data["pillars"], 1)}
    pillars = {}
    for code in data["pillars"]:
        scores = tuple(person.pillars[code].score for person in people)
        bands = [oracle.band(score) for score in scores]
        average = half_up(sum(scores) / count)
        affected = share(sum(b in ("ATENÇÃO", "PRIORIDADE") for b in bands), count)
        pillars[code] = ExpectedPillar(
            code,
            scores,
            average,
            oracle.band(average),
            tuple((band, share(bands.count(band), count)) for band in BANDS),
            affected,
            priority(average, affected),
        )
    items = pillars.values()
    overall = half_up(sum(person.overall for person in people) / count)
    return ExpectedReport(
        overall,
        oracle.band(overall),
        pillars,
        tuple(p.code for p in sorted(items, key=lambda p: (p.average, order[p.code]))),
        tuple(p.code for p in sorted(items, key=lambda p: (-p.average, order[p.code]))),
        tuple(
            p.code
            for p in sorted(
                items,
                key=lambda p: (
                    PRIORITY_ORDER.index(p.priority),
                    p.average,
                    order[p.code],
                ),
            )
        ),
    )


def report_mismatches(report, expected, population, evaluated):
    """Lista de (o quê, esperado, obtido). Vazia quando tudo bate."""
    found = []

    def check(what, want, got):
        if want != got:
            found.append((what, want, got))

    check("população", population, report.population)
    check("avaliados", evaluated, report.evaluated)
    check("dados insuficientes", False, report.insufficient_data)
    check("média geral", expected.overall, report.overall_average)
    check("faixa geral", expected.overall_band, report.overall_band)
    check(
        "pilares exibidos",
        set(expected.pillars),
        {p.pillar.code for p in report.pillars},
    )
    for item in report.pillars:
        want = expected.pillars[item.pillar.code]
        name = item.pillar.name
        check(f"{name}: média", want.average, item.average)
        check(f"{name}: faixa", want.band, item.band)
        check(f"{name}: distribuição", want.distribution, item.distribution)
        check(f"{name}: % afetados", want.affected, item.affected_percent)
        check(f"{name}: prioridade", want.priority, item.priority)
    check(
        "3 prioridades",
        expected.lowest[:3],
        tuple(p.pillar.code for p in report.priorities),
    )
    check(
        "3 pontos fortes",
        expected.highest[:3],
        tuple(p.pillar.code for p in report.strengths),
    )
    check(
        "ordem de investimento",
        expected.investments,
        tuple(p.pillar.code for p in report.investments),
    )
    check(
        "abaixo de 70",
        tuple(c for c in expected.lowest if expected.pillars[c].average < 70),
        tuple(p.pillar.code for p in report.attention),
    )
    return found


# ---------------------------------------------------------------- documento


def br(value):
    value = Decimal(value)
    if value == value.to_integral_value():
        return str(int(value))
    return f"{half_up(value):.2f}".replace(".", ",")


def score_br(value):
    return f"{half_up(value):.2f}".replace(".", ",")


def cell(text):
    return text.replace("|", "/")


def facts_to_confirm(data):
    """Pontos da proposta que o cliente deve olhar, tirados só do JSON."""
    lines = []
    scored = [q for q in oracle.questions(data) if q["scorable"]]
    free = [
        f"{oracle.question_label(q)} “{o['label']}”"
        for q in scored
        for o in q["options"]
        if not o["counts_for_score"]
    ]
    lines.append(
        "- Opções que **não contam ponto** (a pergunta sai da média da área): "
        + "; ".join(free)
        + "."
    )
    floor = [
        f"{oracle.question_label(q)} (menor valor {br(min(o['score_value'] for o in perfis.counting(q)))})"
        for q in scored
        if min(o["score_value"] for o in perfis.counting(q)) > 0
    ]
    if floor:
        lines.append(
            "- Perguntas pontuadas cuja pior opção **não vale 0**: "
            + "; ".join(floor)
            + "."
        )
    ties = []
    for q in scored:
        top = [
            o["label"]
            for o in q["options"]
            if o["counts_for_score"] and o["score_value"] == 100
        ]
        if len(top) > 1:
            ties.append(f"{oracle.question_label(q)} ({' e '.join(top)})")
    if ties:
        lines.append(
            "- Perguntas em que **mais de uma opção vale 100**: "
            + "; ".join(ties)
            + "."
        )
    reverse = [q for q in scored if q.get("score_direction") == oracle.REVERSE]
    lines.append(
        "- Perguntas de nota invertida: "
        + (
            ", ".join(oracle.question_label(q) for q in reverse)
            if reverse
            else "nenhuma no v2"
        )
        + "."
    )
    return lines


def build_document(data, names, oracle_by_profile, system_by_profile, report_block):
    total_q = len(oracle.questions(data))
    scored_q = sum(q["scorable"] for q in oracle.questions(data))
    out = [
        "# Conferência do diagnóstico — questionário v2",
        "",
        (
            "> Gerado automaticamente por `tests/test_conferencia_diagnostico.py`. "
            "Não edite à mão: se a pontuação mudar, o teste falha e mostra como "
            "gerar de novo."
        ),
        "",
        f"**Pontuação conferida:** `{data['scoring_version']}` — {data['status_note']}.",
        "",
        f"Questionário: {total_q} perguntas, {scored_q} valem ponto, 9 áreas.",
        "",
        "## Como ler",
        "",
        (
            "- **Gabarito**: conta feita à parte, só com a tabela de pontos do "
            "questionário oficial, sem usar o código do sistema."
        ),
        (
            "- **Sistema**: a nota que o sistema salvou depois que a pessoa respondeu "
            "todas as perguntas pelas telas do aplicativo."
        ),
        (
            "- Quando as duas colunas são iguais em todas as linhas, o sistema está "
            "seguindo a proposta de pontuação."
        ),
        "",
        "## As regras da proposta",
        "",
        (
            "- Cada opção vale de 0 a 100 pontos. As perguntas da seção 1 "
            "(Identificação), da seção 12, as perguntas abertas, as de múltipla "
            "escolha e as informativas não valem ponto."
        ),
        (
            "- **Nota da área** = média das respostas daquela área que valem ponto, "
            "com 2 casas (meio para cima)."
        ),
        "- **Nota geral** = média das 9 áreas.",
        (
            "- **Faixas**: abaixo de 40 Prioridade; de 40 a menos de 70 Atenção; "
            "de 70 a menos de 85 Bom; 85 ou mais Excelente."
        ),
        "",
        "### Pontos da proposta para confirmar",
        "",
        *facts_to_confirm(data),
        "",
    ]
    for profile in ("a", "b", "c"):
        expected = oracle_by_profile[profile]
        result, pillars = system_by_profile[profile]
        out += [
            f"## Perfil {profile.upper()} — {perfis.TITLES[profile]}",
            "",
            (
                "| Área | Respostas (pergunta, opção → pontos) | Nota esperada (gabarito) "
                "| Nota do sistema | Faixa |"
            ),
            "|---|---|---|---|---|",
        ]
        for code in data["pillars"]:
            want = expected.pillars[code]
            got_score, got_band = pillars[code]
            answers = "<br>".join(
                f"{i.question} {cell(i.option)} → "
                + ("não conta" if i.value is None else br(i.value))
                for i in want.items
            )
            band = BAND_NAMES[got_band]
            if got_band != want.band:
                band += f" (esperado {BAND_NAMES[want.band]})"
            out.append(
                f"| {names[code]} | {answers} | {score_br(want.score)} "
                f"| {score_br(got_score)} | {band} |"
            )
        band = BAND_NAMES[result.overall_band]
        if result.overall_band != expected.overall_band:
            band += f" (esperado {BAND_NAMES[expected.overall_band]})"
        out += [
            (
                f"| **Geral** | média das 9 áreas | **{score_br(expected.overall)}** "
                f"| **{score_br(result.overall_score)}** | **{band}** |"
            ),
            "",
        ]
    out += report_block
    return "\n".join(out) + "\n"


def report_document(data, names, oracle_by_profile, expected, report):
    system = {item.pillar.code: item for item in report.pillars}
    heads = " | ".join(f"Pessoa {p.upper()}" for p in REPORT_PROFILES)
    out = [
        "## Relatório da empresa com 5 pessoas (perfis A a E)",
        "",
        (
            "O gestor só vê números do grupo, nunca de uma pessoa, e só a partir de "
            "5 avaliações concluídas no período."
        ),
        "",
        "- **Média da área** = soma das notas das 5 pessoas ÷ 5, com 2 casas.",
        "- **% afetados** = pessoas em Atenção ou Prioridade naquela área ÷ 5.",
        (
            "- **Prioridade**: média abaixo de 40 → imediata; de 40 a menos de 70 com "
            "50% ou mais de afetados → alta; de 40 a menos de 70 com menos de 50% → "
            "moderada; 70 ou mais → manutenção."
        ),
        "",
        (
            f"| Área | {heads} | Média esperada | Média do sistema | Faixa "
            "| % afetados | Prioridade |"
        ),
        "|---|" + "---|" * len(REPORT_PROFILES) + "---|---|---|---|---|",
    ]
    for code in data["pillars"]:
        want = expected.pillars[code]
        got = system.get(code)
        scores = " | ".join(score_br(s) for s in want.scores)
        out.append(
            f"| {names[code]} | {scores} | {score_br(want.average)} "
            f"| {score_br(got.average) if got else '—'} "
            f"| {BAND_NAMES[got.band] if got else '—'} "
            f"| {got.affected_percent if got else '—'}% | {got.priority if got else '—'} |"
        )
    overall = " | ".join(
        score_br(oracle_by_profile[p].overall) for p in REPORT_PROFILES
    )
    out += [
        (
            f"| **Geral** | {overall} | **{score_br(expected.overall)}** "
            f"| **{score_br(report.overall_average)}** "
            f"| **{BAND_NAMES[report.overall_band]}** | | |"
        ),
        "",
        "Distribuição por faixa em cada área (Excelente · Bom · Atenção · Prioridade):",
        "",
    ]
    for code in data["pillars"]:
        got = system[code]
        parts = " · ".join(f"{pct}%" for _, pct in got.distribution)
        out.append(f"- {names[code]}: {parts}")
    lowest = ", ".join(names[c] for c in expected.lowest[:3])
    shown = ", ".join(p.pillar.name for p in report.priorities)
    out += [
        "",
        (
            "3 áreas que mais pedem atenção (menor média; empate segue a ordem "
            "oficial das áreas):"
        ),
        "",
        f"- Esperado: {lowest}",
        f"- Sistema: {shown}",
        "",
    ]
    return out


# ---------------------------------------------------------------- testes


class ConferenciaPontaAPontaTests(TestCase):
    """6 colaboradores respondem pelas telas; o salvo é comparado ao gabarito."""

    @classmethod
    def setUpTestData(cls):
        cls.data = oracle.load()
        cls.version = load_v2()
        cls.screens = Screens(cls.version, cls.data)
        cls.org = Organization.objects.create(
            name="Empresa Conferência", slug="empresa-conferencia"
        )
        cls.manager = make_member(
            "gestor@conferencia.test", cls.org, Membership.Role.CORPORATE_MANAGER
        )
        cls.users, cls.assessments, cls.visited, cls.plans = {}, {}, {}, {}
        for profile in perfis.PROFILES:
            email = f"perfil-{profile}@conferencia.test"
            cls.users[profile] = make_member(email, cls.org)
            cls.plans[profile] = perfis.plan(cls.data, profile)
            browser = Browser(email)
            assessment_id, visited = browser.fill(cls.screens, cls.plans[profile])
            response = browser.complete(assessment_id)
            expect(
                response["Location"]
                == reverse("assessment_completed", args=[assessment_id]),
                f"perfil {profile} não concluiu",
            )
            cls.assessments[profile] = assessment_id
            cls.visited[profile] = visited
        cls.expected = {
            profile: oracle.score(
                cls.data, perfis.scored_choices(cls.data, cls.plans[profile])
            )
            for profile in perfis.PROFILES
        }

    def manager_report(self):
        browser = Browser("gestor@conferencia.test")
        response = browser.get(reverse("executive_report"))
        self.assertEqual(response.status_code, 200)
        return response

    def people(self, *profiles):
        return [self.expected[p] for p in profiles]

    def assert_report(self, people, population):
        report = self.manager_report().context["report"]
        expected = expected_report(self.data, people)
        self.assertEqual(
            report_mismatches(report, expected, population, len(people)), []
        )
        return report

    def deactivate(self, profile):
        Membership.objects.filter(
            user=self.users[profile], organization=self.org
        ).update(is_active=False)

    def test_telas_seguem_a_ordem_oficial_sem_pular_pergunta(self):
        official = [q["code"] for q in oracle.questions(self.data)]
        self.assertEqual(len(official), 101)
        for profile in perfis.PROFILES:
            with self.subTest(perfil=profile):
                self.assertEqual(self.visited[profile], official)

    def test_mapa_salvo_igual_ao_gabarito_nota_a_nota(self):
        compared = 0
        for profile in perfis.PROFILES:
            expected = self.expected[profile]
            result, pillars = system_scores(self.assessments[profile])
            self.assertEqual(result.scoring_version, self.data["scoring_version"])
            self.assertEqual(set(pillars), set(self.data["pillars"]))
            for code in self.data["pillars"]:
                with self.subTest(perfil=profile, pilar=code):
                    want = expected.pillars[code]
                    self.assertEqual(pillars[code], (want.score, want.band))
                    compared += 1
            with self.subTest(perfil=profile, pilar="geral"):
                self.assertEqual(
                    (result.overall_score, result.overall_band),
                    (expected.overall, expected.overall_band),
                )
                compared += 1
        self.assertEqual(compared, 60)

    def test_meu_mapa_mostra_a_nota_salva_so_para_a_propria_pessoa(self):
        browser = Browser("perfil-c@conferencia.test")
        page = browser.get(
            reverse("assessment_completed", args=[self.assessments["c"]])
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pessoa Perfil C")
        html = page.content.decode()
        for code in self.data["pillars"]:
            # The map shows the integer part of the saved score (36.67 -> 36).
            score = int(self.expected["c"].pillars[code].score)
            with self.subTest(pilar=code):
                self.assertRegex(
                    html, rf'data-pillar-code="{code}"[^>]*data-score="{score}"'
                )

    def test_texto_multipla_e_opcionais_nao_mudam_nota(self):
        _, best = system_scores(self.assessments["a"])
        for profile in ("e", "f"):
            with self.subTest(perfil=profile):
                result, pillars = system_scores(self.assessments[profile])
                self.assertEqual(pillars, best)
                self.assertEqual(result.overall_score, Decimal("100.00"))
        blank = Answer.objects.filter(
            assessment_id=self.assessments["e"],
            question__code__in=["q1-2", "q2-12", "q12-3"],
        )
        self.assertFalse(blank.exists())
        exclusive = Answer.objects.get(
            assessment_id=self.assessments["f"], question__code="q2-9"
        )
        self.assertEqual([c.option.code for c in exclusive.choices.all()], ["o11"])
        other = Answer.objects.get(
            assessment_id=self.assessments["f"], question__code="q1-3"
        )
        self.assertEqual(other.text_value, "Setor Secreto F")

    def test_opcao_que_nao_conta_sai_da_media_da_area(self):
        _, pillars = system_scores(self.assessments["d"])
        expected = self.expected["d"]
        checked = 0
        for code, pillar in expected.pillars.items():
            values = [i.value for i in pillar.items if i.value is not None]
            if len(values) == len(pillar.items):
                continue
            as_zero = oracle.rounded(sum(values) / len(pillar.items))
            with self.subTest(pilar=code):
                self.assertEqual(pillars[code][0], pillar.score)
                self.assertNotEqual(pillars[code][0], as_zero)
                checked += 1
        self.assertGreaterEqual(checked, 4)

    def test_nao_ha_pergunta_invertida_no_v2(self):
        self.assertFalse(
            [
                q["code"]
                for q in oracle.questions(self.data)
                if q.get("score_direction") == oracle.REVERSE
            ]
        )
        self.assertFalse(
            Question.objects.filter(
                section__questionnaire=self.version,
                score_direction=Question.Direction.REVERSE,
            ).exists()
        )

    def test_ordem_das_areas_no_banco_igual_ao_json(self):
        self.assertEqual(
            list(
                Pillar.objects.order_by("display_order").values_list("code", flat=True)
            ),
            self.data["pillars"],
        )

    def test_relatorio_com_seis_pessoas(self):
        self.assert_report(self.people(*perfis.PROFILES), population=6)

    def test_relatorio_com_cinco_pessoas(self):
        self.deactivate("f")
        report = self.assert_report(self.people(*REPORT_PROFILES), population=5)
        self.assertEqual(len(report.pillars), 9)

    def test_relatorio_com_quatro_pessoas_nao_mostra_numeros(self):
        self.deactivate("f")
        Browser("perfil-e@conferencia.test").revoke_consent()
        response = self.manager_report()
        report = response.context["report"]
        self.assertTrue(report.insufficient_data)
        self.assertEqual(report.evaluated, 4)
        self.assertIsNone(report.overall_average)
        self.assertEqual(report.pillars, ())
        self.assertContains(response, "São necessárias pelo menos 5 avaliações")

    def test_revogar_consentimento_tira_a_pessoa_do_relatorio(self):
        Browser("perfil-b@conferencia.test").revoke_consent()
        self.assert_report(self.people("a", "c", "d", "e", "f"), population=6)

    def test_colaborador_inativo_sai_da_populacao(self):
        self.deactivate("b")
        self.assert_report(self.people("a", "c", "d", "e", "f"), population=5)

    def test_so_a_ultima_avaliacao_do_periodo_conta(self):
        now = timezone.now()
        # c já tinha uma avaliação anterior (pior), ainda dentro do período.
        complete_by_service(
            self.users["c"],
            self.org,
            self.version,
            self.screens,
            perfis.plan(self.data, "b"),
            now - timedelta(days=10),
        )
        # b refez depois (melhor): só a nova conta.
        complete_by_service(
            self.users["b"],
            self.org,
            self.version,
            self.screens,
            perfis.plan(self.data, "a"),
            timezone.now(),
        )
        # b passa a contar com a nota nova (igual à do perfil a).
        self.assert_report(self.people("a", "a", "c", "d", "e", "f"), population=6)

    def test_avaliacao_fora_do_periodo_nao_conta(self):
        late = make_member("fora-do-periodo@conferencia.test", self.org)
        complete_by_service(
            late,
            self.org,
            self.version,
            self.screens,
            perfis.plan(self.data, "b"),
            timezone.now() - timedelta(days=120),
        )
        self.assert_report(self.people(*perfis.PROFILES), population=7)

    def test_gestor_nunca_ve_nome_identificacao_nem_texto_livre(self):
        response = self.manager_report()
        html = response.content.decode()
        report = repr(response.context["report"])
        multiple = [
            o["label"]
            for q in oracle.questions(self.data)
            if q["kind"] == "MULTIPLE"
            for o in q["options"]
        ]
        for profile in perfis.PROFILES:
            typed = list(perfis.secrets(profile).values())
            for secret in [*typed, f"perfil-{profile}@conferencia.test", *multiple]:
                with self.subTest(perfil=profile, texto=secret):
                    self.assertNotIn(secret, html)
                    self.assertNotIn(secret, report)
        manager = Browser("gestor@conferencia.test")
        assessment_id = self.assessments["a"]
        name = self.screens.url(assessment_id, "q1-1")
        for url in (
            reverse("assessment_hub"),
            reverse("assessment_completed", args=[assessment_id]),
            reverse("assessment_review", args=[assessment_id]),
            name,
        ):
            with self.subTest(url=url):
                self.assertEqual(manager.get(url).status_code, 403)

    def test_documento_de_conferencia(self):
        """Gera docs/qa/conferencia-diagnostico.md e confere que está atualizado."""
        self.deactivate("f")
        report = self.manager_report().context["report"]
        names = dict(Pillar.objects.values_list("code", "name"))
        people = [self.expected[p] for p in REPORT_PROFILES]
        expected = expected_report(self.data, people)
        systems = {p: system_scores(self.assessments[p]) for p in ("a", "b", "c")}
        document = build_document(
            self.data,
            names,
            self.expected,
            systems,
            report_document(self.data, names, self.expected, expected, report),
        )
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir:
            path = Path(artifact_dir)
            path.mkdir(parents=True, exist_ok=True)
            (path / DOC_NAME).write_text(document, encoding="utf-8")
        if os.environ.get("CONFERENCIA_WRITE") == "1":
            DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
            DOC_PATH.write_text(document, encoding="utf-8")
        for profile in ("a", "b", "c"):
            result, pillars = systems[profile]
            want = self.expected[profile]
            self.assertEqual(
                {c: pillars[c] for c in self.data["pillars"]},
                {c: (p.score, p.band) for c, p in want.pillars.items()},
            )
            self.assertEqual(result.overall_score, want.overall)
        self.assertEqual(report_mismatches(report, expected, 5, 5), [])
        committed = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
        self.assertEqual(
            committed,
            document,
            "docs/qa/conferencia-diagnostico.md está desatualizado. Gere de novo "
            "com CONFERENCIA_WRITE=1 python manage.py test "
            "tests.test_conferencia_diagnostico --settings=config.settings.test "
            "(ou copie o arquivo do artifact de QA do CI).",
        )


class ComportamentoQuestionarioTests(TestCase):
    """Regras das telas do questionário, uma pessoa por vez."""

    @classmethod
    def setUpTestData(cls):
        cls.data = oracle.load()
        cls.version = load_v2()
        cls.screens = Screens(cls.version, cls.data)
        cls.org = Organization.objects.create(name="Empresa", slug="empresa")
        cls.other_org = Organization.objects.create(name="Outra", slug="outra")
        cls.user = make_member("pessoa@conferencia.test", cls.org)
        make_member("colega@conferencia.test", cls.org)
        make_member("outra-empresa@conferencia.test", cls.other_org)
        make_member(
            "gestor@conferencia.test", cls.org, Membership.Role.CORPORATE_MANAGER
        )

    def setUp(self):
        self.browser = Browser("pessoa@conferencia.test")
        self.assessment_id = self.browser.start()

    def url(self, code):
        return self.screens.url(self.assessment_id, code)

    def post(self, code, spec):
        return self.browser.answer(self.url(code), self.screens, code, spec)

    def stored(self, code):
        return Answer.objects.filter(
            assessment_id=self.assessment_id, question__code=code
        ).first()

    def choices(self, code):
        return sorted(c.option.code for c in self.stored(code).choices.all())

    def answer_everything(self, plan):
        for code, spec in plan.items():
            response = self.post(code, spec)
            self.assertEqual(response.status_code, 302, code)

    def test_obrigatoria_bloqueia_o_avanco(self):
        cases = {
            "q2-1": "Selecione uma resposta antes de salvar.",
            "q11-1": "Selecione uma resposta antes de salvar.",
            "q2-9": "Selecione uma resposta antes de salvar.",
            "q1-1": "Escreva sua resposta antes de salvar.",
        }
        for code, message in cases.items():
            with self.subTest(pergunta=code):
                response = self.post(code, None)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertIsNone(self.stored(code))
        plan = perfis.plan(self.data, "a")
        plan.pop("q7-5")
        self.answer_everything(plan)
        response = self.browser.complete(self.assessment_id)
        self.assertEqual(
            response["Location"],
            reverse("assessment_review", args=[self.assessment_id]) + "?incomplete=1",
        )
        self.assertFalse(AssessmentResult.objects.exists())
        self.assertEqual(
            Assessment.objects.get(pk=self.assessment_id).status,
            Assessment.Status.IN_PROGRESS,
        )

    def test_opcionais_podem_ficar_em_branco(self):
        for code in ("q1-2", "q2-12", "q12-3"):
            with self.subTest(pergunta=code):
                self.assertEqual(self.post(code, None).status_code, 302)
                self.assertIsNone(self.stored(code))
        self.post("q2-12", {"option": "o1"})
        self.assertIsNotNone(self.stored("q2-12"))
        self.post("q2-12", None)
        self.assertIsNone(self.stored("q2-12"))

    def test_exclusiva_nao_combina_e_substitui_as_outras(self):
        for code, exclusive in (("q2-9", "o11"), ("q4-4", "o10")):
            with self.subTest(pergunta=code):
                page = self.browser.get(self.url(code))
                self.assertContains(page, "data-exclusive", count=1)
                combined = self.post(code, {"options": [exclusive, "o1"]})
                self.assertContains(combined, "não pode ser marcada junto")
                self.assertIsNone(self.stored(code))
                self.post(code, {"options": ["o1", "o2"]})
                self.assertEqual(self.choices(code), ["o1", "o2"])
                self.post(code, {"options": [exclusive]})
                self.assertEqual(self.choices(code), [exclusive])

    def test_outro_exige_texto(self):
        missing = self.post("q1-3", {"option": "o6"})
        self.assertContains(missing, "Descreva a opção")
        self.assertIsNone(self.stored("q1-3"))
        self.post("q1-3", {"option": "o6", "text": "Logística"})
        self.assertEqual(self.stored("q1-3").text_value, "Logística")
        self.post("q1-3", {"option": "o1", "text": "texto esquecido"})
        self.assertEqual(self.stored("q1-3").text_value, "")

    def test_voltar_e_alterar_resposta_recalcula(self):
        plan = perfis.plan(self.data, "a")
        self.answer_everything(plan)
        page = self.browser.get(self.url("q2-1"))
        best = self.screens.options["q2-1", "o1"]
        self.assertContains(page, f'value="{best}" checked')
        plan["q2-1"] = {"option": "o5"}
        response = self.browser.post(
            self.url("q2-1"),
            {**self.screens.form("q2-1", plan["q2-1"]), "destination": "review"},
        )
        self.assertEqual(
            response["Location"],
            reverse("assessment_review", args=[self.assessment_id]),
        )
        self.browser.complete(self.assessment_id)
        expected = oracle.score(self.data, perfis.scored_choices(self.data, plan))
        result, pillars = system_scores(self.assessment_id)
        # Conta à mão: (0 + 7 x 100) / 8 perguntas da área = 87,50.
        self.assertEqual(pillars["physical_health"][0], Decimal("87.50"))
        self.assertEqual(
            pillars["physical_health"],
            (expected.pillars["physical_health"].score, "EXCELENTE"),
        )
        self.assertEqual(result.overall_score, expected.overall)

    def test_nao_conclui_duas_vezes(self):
        self.answer_everything(perfis.plan(self.data, "a"))
        completed = reverse("assessment_completed", args=[self.assessment_id])
        self.assertEqual(
            self.browser.complete(self.assessment_id)["Location"], completed
        )
        result = AssessmentResult.objects.get()
        again = self.browser.post(
            reverse("assessment_complete", args=[self.assessment_id])
        )
        self.assertEqual(again["Location"], completed)
        changed = self.browser.post(
            self.url("q2-1"), self.screens.form("q2-1", {"option": "o5"})
        )
        self.assertEqual(changed["Location"], completed)
        restart = self.browser.post(reverse("assessment_start"), {"consent": "on"})
        self.assertEqual(
            restart["Location"],
            reverse("assessment_detail", args=[self.assessment_id]),
        )
        self.assertEqual(AssessmentResult.objects.get(), result)
        self.assertEqual(Assessment.objects.count(), 1)
        self.assertEqual(self.stored("q2-1").selected_option.code, "o1")

    def test_outra_pessoa_nao_acessa_a_avaliacao(self):
        self.post("q1-1", {"text": "Nome Particular"})
        urls = [
            reverse("assessment_detail", args=[self.assessment_id]),
            reverse("assessment_review", args=[self.assessment_id]),
            reverse("assessment_completed", args=[self.assessment_id]),
            self.url("q1-1"),
        ]
        for email in (
            "colega@conferencia.test",
            "outra-empresa@conferencia.test",
            "gestor@conferencia.test",
        ):
            other = Browser(email)
            if email != "gestor@conferencia.test":
                # Com consentimento e avaliação própria: só falta ser o dono.
                other.start()
            for url in urls:
                with self.subTest(pessoa=email, url=url):
                    response = other.get(url)
                    self.assertIn(response.status_code, NOT_FOUND_OR_FORBIDDEN)
                    self.assertNotIn("Nome Particular", response.content.decode())
            for url, data in (
                (self.url("q1-1"), {"text": "invasão"}),
                (reverse("assessment_complete", args=[self.assessment_id]), {}),
            ):
                with self.subTest(pessoa=email, post=url):
                    response = other.post(url, data)
                    self.assertIn(response.status_code, NOT_FOUND_OR_FORBIDDEN)
        self.assertEqual(self.stored("q1-1").text_value, "Nome Particular")
        self.assertEqual(
            Assessment.objects.get(pk=self.assessment_id).status,
            Assessment.Status.IN_PROGRESS,
        )
