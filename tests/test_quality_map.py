"""Individual quality map presentation (spec 10). No database needed."""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from assessments import quality_map
from config import pillar_guidance

DOCS_SPEC = Path(settings.BASE_DIR) / "docs" / "design" / "heart" / "heart-spec.json"
SPEC_ORDER = [
    "physical_health",
    "preventive_behavior",
    "physical_activity",
    "nutrition_hydration",
    "mental_emotional_health",
    "sleep_recovery",
    "ergonomics_workplace",
    "relationships",
    "work_life_balance",
]
# Migration 0002: code, name, display_order.
PILLARS = (
    ("physical_health", "Saúde Física", 1),
    ("preventive_behavior", "Comportamento Preventivo", 2),
    ("physical_activity", "Atividade Física", 3),
    ("nutrition_hydration", "Alimentação e Hidratação", 4),
    ("relationships", "Relacionamentos", 5),
    ("mental_emotional_health", "Saúde Mental e Emocional", 6),
    ("ergonomics_workplace", "Ergonomia e Ambiente de Trabalho", 7),
    ("sleep_recovery", "Sono e Recuperação", 8),
    ("work_life_balance", "Equilíbrio Vida × Trabalho", 9),
)
# The client model's scores, by code.
MODEL_SCORES = {
    "physical_health": "78",
    "preventive_behavior": "88",
    "physical_activity": "56",
    "nutrition_hydration": "48",
    "mental_emotional_health": "42",
    "sleep_recovery": "34",
    "ergonomics_workplace": "59",
    "relationships": "72",
    "work_life_balance": "63",
}


def band(score):
    score = Decimal(score)
    if score < 40:
        return "PRIORIDADE"
    if score < 70:
        return "ATENÇÃO"
    if score < 85:
        return "BOM"
    return "EXCELENTE"


def pillar_results(scores=None):
    scores = scores or MODEL_SCORES
    return [
        SimpleNamespace(
            pillar=SimpleNamespace(code=code, name=name, display_order=order),
            score=Decimal(scores[code]),
            band=band(scores[code]),
        )
        for code, name, order in PILLARS
    ]


def answer(code, kind="TEXT", text="", option=None, requires_text=False):
    selected = (
        SimpleNamespace(label=option, requires_text=requires_text) if option else None
    )
    return SimpleNamespace(
        question=SimpleNamespace(code=code, kind=kind),
        text_value=text,
        selected_option=selected,
    )


IDENTIFICATION = [
    answer("q1-1", text="Carla Souza Oliveira"),
    answer("q1-2", text=""),
    answer("q1-3", "SINGLE", text="Laboratório", option="Outro:", requires_text=True),
    answer("q1-4", text="Analista Administrativo"),
    answer("q1-5", "SINGLE", option="31 a 40 anos"),
    answer("q1-6", "SINGLE", option="4 anos"),
    answer("q1-7", "SINGLE", option="Híbrido"),
    answer("q1-8", "SINGLE", option="8 horas por dia"),
]


class HeartSpecTests(SimpleTestCase):
    def test_runtime_spec_is_the_approved_docs_spec(self):
        self.assertEqual(
            quality_map.SPEC, json.loads(DOCS_SPEC.read_text(encoding="utf-8"))
        )

    def test_segments_follow_spec_position_not_display_order(self):
        segments = quality_map.heart_segments(pillar_results())
        self.assertEqual([s["code"] for s in segments], SPEC_ORDER)
        self.assertEqual([s["position"] for s in segments], list(range(1, 10)))
        for segment, spec in zip(segments, quality_map.SPEC["segments"], strict=True):
            self.assertEqual(segment["polygon"], spec["polygon"])
            self.assertEqual(segment["lines"], spec["label_lines_example"])
            self.assertEqual(segment["text_x"], spec["text_x"])
            self.assertEqual(segment["text_y"], spec["text_y"])
            self.assertEqual(segment["anchor"], spec["text_anchor"])
            self.assertEqual(
                segment["icon"], quality_map.SPEC["icons_24px_stroke"][spec["icon"]]
            )

    def test_segments_need_the_nine_spec_pillars(self):
        with self.assertRaises(ValueError):
            quality_map.heart_segments(pillar_results()[:8])

    def test_color_is_interpolated_from_score_stops(self):
        # Expected values are the reference SVG's gradients for these scores.
        self.assertEqual(quality_map.score_rgb(34), (222, 55, 43))
        for score, top, bottom in (
            (34, "#f43d2f", "#bf2f25"),
            (56, "#ffb218", "#d28b13"),
            (88, "#299e4a", "#207c3a"),
            (78, "#85cc3f", "#689f31"),
            (0, None, None),
            (100, None, None),
        ):
            colors = quality_map.segment_colors(score)
            if top:
                self.assertEqual((colors["top"], colors["bottom"]), (top, bottom))
            for value in colors.values():
                self.assertRegex(value, r"^#[0-9a-f]{6}$")
        self.assertEqual(quality_map.score_rgb(0), (196, 32, 40))
        self.assertEqual(quality_map.score_rgb(100), (24, 120, 56))
        self.assertEqual(quality_map.score_rgb(40), (236, 104, 32))

    def test_text_color_rule(self):
        white, ink = "#ffffff", "#2a1d00"
        for score, expected in (
            (0, white),
            (49, white),
            (50, ink),
            (55, ink),
            (69, ink),
            (70, white),
            (100, white),
        ):
            self.assertEqual(quality_map.text_color(score), expected, score)

    def test_display_truncates_and_keeps_saved_band(self):
        scores = dict(MODEL_SCORES, sleep_recovery="36.67", physical_activity="69.99")
        results = pillar_results(scores)
        segments = {s["code"]: s for s in quality_map.heart_segments(results)}
        self.assertEqual(segments["sleep_recovery"]["display"], 36)
        self.assertEqual(segments["physical_activity"]["display"], 69)
        self.assertEqual(segments["physical_activity"]["band"], "ATENÇÃO")
        self.assertEqual(quality_map.display_score(Decimal("84.99")), 84)
        self.assertEqual(quality_map.display_score(Decimal("100.00")), 100)
        # The saved value is never touched.
        self.assertEqual(results[7].score, Decimal("36.67"))


class AttentionAndRecommendationTests(SimpleTestCase):
    def test_top_three_lowest_with_display_order_tiebreak(self):
        scores = dict.fromkeys(MODEL_SCORES, "90")
        scores.update(
            sleep_recovery="40", relationships="40", work_life_balance="40",
            physical_health="40",
        )  # fmt: skip
        attention = quality_map.attention_pillars(pillar_results(scores))
        # relationships (5), sleep_recovery (8), work_life_balance (9) lose to 1.
        self.assertEqual(
            [p.pillar.code for p in attention],
            ["physical_health", "relationships", "sleep_recovery"],
        )
        model = quality_map.attention_pillars(pillar_results())
        self.assertEqual(
            [p.pillar.code for p in model],
            ["sleep_recovery", "mental_emotional_health", "nutrition_hydration"],
        )

    def test_guidance_has_empty_text_for_each_pillar(self):
        self.assertEqual(set(pillar_guidance.PILLAR_GUIDANCE), set(SPEC_ORDER))
        self.assertTrue(all(v == "" for v in pillar_guidance.PILLAR_GUIDANCE.values()))

    def test_empty_guidance_shows_only_title_and_button(self):
        cards = quality_map.recommendations(pillar_results())
        self.assertEqual(
            [card["code"] for card in cards],
            [
                "sleep_recovery",
                "mental_emotional_health",
                "nutrition_hydration",
                "preventive_behavior",
            ],
        )
        self.assertTrue(all(card["text"] == "" for card in cards))
        self.assertEqual(cards[3]["kind"], "keep")
        self.assertEqual(cards[3]["title"], "Continue assim!")
        for card in cards[:3]:
            self.assertEqual(card["button"], "Ver aulas")
            self.assertEqual(card["url"], reverse("lessons"))

    def test_exercise_pillars_link_to_exercises(self):
        scores = dict.fromkeys(MODEL_SCORES, "80")
        scores.update(
            physical_activity="10", ergonomics_workplace="11", physical_health="12"
        )
        cards = quality_map.recommendations(pillar_results(scores))
        self.assertEqual(len(cards), 3)  # best pillar is 80: no "Continue assim!"
        for card in cards:
            self.assertEqual(card["button"], "Ver exercícios")
            self.assertEqual(card["url"], reverse("exercises"))

    def test_filled_guidance_text_is_shown(self):
        with mock.patch.dict(
            pillar_guidance.PILLAR_GUIDANCE, {"sleep_recovery": "Texto aprovado."}
        ):
            cards = quality_map.recommendations(pillar_results())
        self.assertEqual(cards[0]["text"], "Texto aprovado.")
        self.assertEqual(cards[1]["text"], "")

    def test_keep_going_needs_85_and_is_never_an_attention_pillar(self):
        scores = dict.fromkeys(MODEL_SCORES, "90")
        cards = quality_map.recommendations(pillar_results(scores))
        codes = [card["code"] for card in cards]
        self.assertEqual(len(codes), 4)
        self.assertEqual(len(set(codes)), 4)
        self.assertEqual(codes[3], "nutrition_hydration")  # first after the top 3
        scores = dict(MODEL_SCORES, preventive_behavior="84.99")
        cards = quality_map.recommendations(pillar_results(scores))
        self.assertEqual(len(cards), 3)


class IdentificationTests(SimpleTestCase):
    def test_owner_answers_with_other_text_and_without_blank_registration(self):
        items = quality_map.identification(IDENTIFICATION)
        labels = [label for label, _ in items]
        self.assertNotIn("Matrícula", labels)
        self.assertEqual(
            items,
            [
                ("Nome", "Carla Souza Oliveira"),
                ("Cargo/Função", "Analista Administrativo"),
                ("Setor/Departamento", "Laboratório"),
                ("Faixa etária", "31 a 40 anos"),
                ("Tempo de empresa", "4 anos"),
                ("Modalidade de trabalho", "Híbrido"),
                ("Jornada de trabalho", "8 horas por dia"),
            ],
        )

    def test_registration_shown_when_answered(self):
        answers = [*IDENTIFICATION[:1], answer("q1-2", text="12548")]
        self.assertEqual(
            quality_map.identification(answers),
            [("Nome", "Carla Souza Oliveira"), ("Matrícula", "12548")],
        )

    def test_initials(self):
        self.assertEqual(quality_map.initials("Carla Souza Oliveira"), "CO")
        self.assertEqual(quality_map.initials("  ana  "), "A")
        self.assertEqual(quality_map.initials(""), "")


class EvolutionTests(SimpleTestCase):
    def test_hidden_without_previous(self):
        self.assertIsNone(quality_map.evolution(pillar_results(), None))

    def test_two_series_in_spec_order(self):
        previous = pillar_results(dict.fromkeys(MODEL_SCORES, "50.75"))
        chart = quality_map.evolution(pillar_results(), previous)
        self.assertEqual([p["code"] for p in chart["points"]], SPEC_ORDER)
        self.assertEqual(chart["points"][0]["current"], 78)
        self.assertEqual(chart["points"][0]["previous"], 50)
        self.assertTrue(chart["current_path"].startswith("M"))
        self.assertTrue(chart["previous_path"].startswith("M"))


class MapTemplateTests(SimpleTestCase):
    def render(self, previous=None, answers=IDENTIFICATION, scores=None):
        request = RequestFactory().get("/app/assessment/7/completed/")
        request.user = get_user_model()(email="map.owner@example.test")
        request.resolver_match = resolve(reverse("assessment_hub"))
        assessment = SimpleNamespace(
            pk=7, completed_at=datetime(2025, 5, 27, 15, tzinfo=UTC)
        )
        result = SimpleNamespace(overall_score=Decimal("67.40"), overall_band="ATENÇÃO")
        context = quality_map.build_context(
            assessment=assessment,
            result=result,
            pillars=pillar_results(scores),
            answers=answers,
            previous=previous,
        )
        tenant = SimpleNamespace(
            organization=SimpleNamespace(name="Map Co"), role="COLLABORATOR"
        )
        return render_to_string(
            "assessments/completed.html",
            {"tenant": tenant, **context},
            request=request,
        )

    def test_svg_has_nine_segments_in_spec_order(self):
        html = self.render()
        self.assertEqual(
            re.findall(r'class="heart-segment"[^>]*data-pillar-code="([a-z_]+)"', html),
            SPEC_ORDER,
        )
        self.assertEqual(html.count('tabindex="0" role="button"'), 9)
        self.assertEqual(html.count('aria-pressed="false"'), 9)
        self.assertIn('role="group" aria-labelledby="heart-title heart-desc"', html)
        self.assertIn(quality_map.SPEC["outer_heart_path"], html)
        self.assertIn(quality_map.SPEC["inner_heart_path"], html)
        self.assertIn('stop-color="#f43d2f"', html)  # sleep 34
        self.assertIn('stop-color="#ffb218"', html)  # activity 56
        self.assertIn('stop-color="#299e4a"', html)  # preventive 88
        self.assertIn("1. SAÚDE FÍSICA", html)
        self.assertIn("9. EQUILÍBRIO", html)
        # pt-BR would print "1,35": scale(1, 35) stretches the icons.
        self.assertIn("scale(1.35)", html)
        self.assertNotRegex(html, r'(?:x|y|cx|cy|scale)[=(]"?\d+,\d')

    def test_scores_show_integer_percent_and_saved_band(self):
        html = self.render(scores=dict(MODEL_SCORES, sleep_recovery="36.67"))
        self.assertIn('class="heart-center-score" data-count="67">67<', html)
        self.assertIn('data-count="36">36<', html)
        self.assertNotIn("36,67", html)
        self.assertNotIn("/100", html)
        self.assertIn(">%<", html)

    def test_header_identification_legend_and_footer(self):
        html = self.render()
        for text in (
            "SEU MAPA DE QUALIDADE DE VIDA",
            "Resultado da sua avaliação",
            "27/05/2025",
            "quality-life-logo-ring-",
            "Identificação do colaborador",
            "Carla Souza Oliveira",
            "Laboratório",
            ">CO<",
            "Legenda de pontuação",
            "85 a 100",
            "70 a 84",
            "40 a 69",
            "0 a 39",
            "Suas 3 principais áreas que merecem atenção",
            "Recomendações personalizadas",
            "Continue assim!",
            "Evolução das suas pontuações",
            "Sua evolução aparece a partir da segunda avaliação.",
            (
                "Suas respostas são confidenciais e usadas apenas para promover "
                "sua qualidade de vida."
            ),
            "Salvar em PDF",
            "data-print",
        ):
            self.assertIn(text, html)
        self.assertNotIn("Matrícula", html)
        self.assertEqual(html.count('class="attention-item"'), 3)
        self.assertEqual(html.count('class="recommendation-card'), 4)
        self.assertNotIn('class="evolution-chart"', html)
        self.assertNotIn('<img src="data:', html)

    def test_evolution_chart_with_previous(self):
        previous = SimpleNamespace(
            completed_at=datetime(2025, 2, 10, 15, tzinfo=UTC),
            pillars=pillar_results(dict.fromkeys(MODEL_SCORES, "50")),
        )
        html = self.render(previous=previous)
        self.assertIn('class="evolution-chart"', html)
        chart = html[html.index('class="evolution-chart"') :]
        self.assertNotRegex(chart, r'(?:x|y|cx|cy|x1|x2|y1|y2|d)="[^"]*\d,\d')
        self.assertIn("10/02/2025", html)
        self.assertNotIn("Sua evolução aparece a partir da segunda avaliação.", html)

    def test_no_identification_panel_without_answers(self):
        html = self.render(answers=[])
        self.assertNotIn("Identificação do colaborador", html)
