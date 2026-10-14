"""Presentation of the individual quality map (spec 10).

Geometry, icons and colors come from ``heart_spec.json`` (an exact copy of the
approved ``docs/design/heart/heart-spec.json``). Scores and bands are the
persisted values: this module only formats them for the screen and never
calculates a score, a band or a priority.
"""

import json
import textwrap
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from itertools import pairwise
from pathlib import Path

from django.urls import reverse

from config import pillar_guidance
from config.recommendations import EXERCISE_PILLARS

SPEC = json.loads(
    (Path(__file__).with_name("heart_spec.json")).read_text(encoding="utf-8")
)
WHITE = "#ffffff"
INK = "#2a1d00"
TOP_FACTOR = Decimal("1.10")
BOTTOM_FACTOR = Decimal("0.86")
CENTER_BAND_COLORS = {
    "PRIORIDADE": "#c42028",
    "ATENÇÃO": "#d97706",
    "BOM": "#4f8a2b",
    "EXCELENTE": "#187838",
}
# Order and short labels of the identification panel (section 1 of v2).
IDENTIFICATION_FIELDS = (
    ("q1-1", "Nome"),
    ("q1-2", "Matrícula"),
    ("q1-4", "Cargo/Função"),
    ("q1-3", "Setor/Departamento"),
    ("q1-5", "Faixa etária"),
    ("q1-6", "Tempo de empresa"),
    ("q1-7", "Modalidade de trabalho"),
    ("q1-8", "Jornada de trabalho"),
)
CHART_LABELS = {
    "physical_health": ("Saúde", "Física"),
    "preventive_behavior": ("Comport.", "Preventivo"),
    "physical_activity": ("Atividade", "Física"),
    "nutrition_hydration": ("Aliment.", "Hidratação"),
    "mental_emotional_health": ("Saúde", "Mental"),
    "sleep_recovery": ("Sono e", "Recup."),
    "ergonomics_workplace": ("Ergonomia", "Ambiente"),
    "relationships": ("Relacio-", "namentos"),
    "work_life_balance": ("Equilíbrio", "Vida/Trab."),
}
CHART = {"left": 50, "right": 546, "top": 30, "bottom": 206}


def display_score(score):
    """Integer part of the saved score, for display only (36.67 -> 36)."""
    return int(Decimal(score).to_integral_value(rounding=ROUND_DOWN))


def _round(value):
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def score_rgb(score):
    """Linear interpolation between the spec's ``color_stops_by_score``."""
    score = Decimal(score)
    stops = SPEC["color_stops_by_score"]
    for low, high in pairwise(stops):
        if low["score"] <= score <= high["score"]:
            span = Decimal(high["score"] - low["score"])
            ratio = (score - low["score"]) / span
            return tuple(
                _round(a + (b - a) * ratio)
                for a, b in zip(low["rgb"], high["rgb"], strict=True)
            )
    raise ValueError("Score must be between 0 and 100.")


def _hex(rgb):
    return "#" + "".join(f"{min(255, channel):02x}" for channel in rgb)


def segment_colors(score):
    """Vertical gradient: top = color x1.10, bottom = color x0.86."""
    rgb = score_rgb(score)
    return {
        "base": _hex(rgb),
        "top": _hex(_round(channel * TOP_FACTOR) for channel in rgb),
        "bottom": _hex(_round(channel * BOTTOM_FACTOR) for channel in rgb),
    }


def text_color(score):
    """White below 50 and from 70; dark ink on the yellows (50-69)."""
    return INK if 50 <= Decimal(score) < 70 else WHITE


def _wrap(text, width=24):
    lines = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width) or [""])
    return lines


def _by_code(pillars):
    return {item.pillar.code: item for item in pillars}


def heart_segments(pillars):
    """The nine segments in the spec's position order (not display_order)."""
    by_code = _by_code(pillars)
    expected = [segment["pillar_code"] for segment in SPEC["segments"]]
    if len(pillars) != len(expected) or set(by_code) != set(expected):
        raise ValueError("The map needs exactly the nine spec pillars.")
    segments = []
    for spec in SPEC["segments"]:
        item = by_code[spec["pillar_code"]]
        shown = display_score(item.score)
        segments.append(
            {
                "position": spec["position"],
                "code": spec["pillar_code"],
                "pillar": item,
                "name": item.pillar.name,
                "band": item.band,
                "display": shown,
                "polygon": spec["polygon"],
                "lines": spec["label_lines_example"],
                "icon": SPEC["icons_24px_stroke"][spec["icon"]],
                "icon_x": spec["icon_translate"][0],
                "icon_y": spec["icon_translate"][1],
                "icon_scale": spec["icon_scale"],
                "text_x": spec["text_x"],
                "text_y": spec["text_y"],
                "anchor": spec["text_anchor"],
                "colors": segment_colors(shown),
                "text_color": text_color(shown),
            }
        )
    return segments


def _rank(pillars):
    return sorted(pillars, key=lambda item: (item.score, item.pillar.display_order))


def attention_pillars(pillars):
    """Three lowest saved scores; ties broken by ``Pillar.display_order``."""
    return _rank(pillars)[:3]


def _action(code):
    if code in EXERCISE_PILLARS:
        return "Ver exercícios", reverse("exercises")
    return "Ver aulas", reverse("lessons")


def recommendations(pillars):
    """A card per attention pillar, plus "Continue assim!" for a best >= 85."""
    attention = attention_pillars(pillars)
    cards = []
    for item in attention:
        button, url = _action(item.pillar.code)
        cards.append(
            {
                "kind": "attention",
                "code": item.pillar.code,
                "title": item.pillar.name,
                "band": item.band,
                "text": pillar_guidance.PILLAR_GUIDANCE.get(item.pillar.code, ""),
                "button": button,
                "url": url,
            }
        )
    chosen = {item.pillar.code for item in attention}
    rest = [item for item in pillars if item.pillar.code not in chosen]
    if rest:
        best = min(rest, key=lambda item: (-item.score, item.pillar.display_order))
        if best.score >= 85:
            button, url = _action(best.pillar.code)
            cards.append(
                {
                    "kind": "keep",
                    "code": best.pillar.code,
                    "title": "Continue assim!",
                    "band": best.band,
                    "text": "",
                    "summary": f"Seu resultado em {best.pillar.name} está excelente.",
                    "button": button,
                    "url": url,
                }
            )
    return cards


def identification(answers):
    """The owner's own answers to q1-1..q1-8; blank answers are left out."""
    by_code = {answer.question.code: answer for answer in answers}
    items = []
    for code, label in IDENTIFICATION_FIELDS:
        answer = by_code.get(code)
        if answer is None:
            continue
        option = answer.selected_option
        if answer.question.kind == "TEXT":
            value = answer.text_value
        elif option is None:
            value = ""
        elif option.requires_text:
            value = answer.text_value
        else:
            value = option.label
        value = (value or "").strip()
        if value:
            items.append((label, value))
    return items


def initials(name):
    words = (name or "").split()
    if not words:
        return ""
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[-1][0]).upper()


def _chart_y(value):
    span = CHART["bottom"] - CHART["top"]
    return round(CHART["bottom"] - span * value / 100, 1)


def _line(points, key):
    path = []
    for point in points:
        if point[key] is None:
            continue
        command = "L" if path else "M"
        path.append(f"{command}{point['x']} {point[key + '_y']}")
    return " ".join(path)


def evolution(current, previous):
    """Two-series line chart data, or None without a previous assessment."""
    if previous is None:
        return None
    now, before = _by_code(current), _by_code(previous)
    codes = [segment["pillar_code"] for segment in SPEC["segments"]]
    step = (CHART["right"] - CHART["left"]) / (len(codes) - 1)
    points = []
    for index, code in enumerate(codes):
        current_value = display_score(now[code].score) if code in now else None
        previous_value = display_score(before[code].score) if code in before else None
        points.append(
            {
                "code": code,
                "x": round(CHART["left"] + step * index, 1),
                "labels": CHART_LABELS[code],
                "current": current_value,
                "previous": previous_value,
                "current_y": None if current_value is None else _chart_y(current_value),
                "previous_y": (
                    None if previous_value is None else _chart_y(previous_value)
                ),
            }
        )
    return {
        "points": points,
        "current_path": _line(points, "current"),
        "previous_path": _line(points, "previous"),
        "grid": [{"value": v, "y": _chart_y(v)} for v in (0, 25, 50, 75, 100)],
        **CHART,
    }


def _band_message(band):
    message = pillar_guidance.OVERALL_MESSAGES.get(band)
    if message is None:
        message = {b: text for b, _, text in pillar_guidance.BAND_LEGEND}.get(band, "")
    return _wrap(message)


def build_context(*, assessment, result, pillars, answers, previous):
    """Template context. ``previous`` has ``completed_at`` and ``pillars``."""
    segments = heart_segments(pillars)
    icons = {segment["code"]: segment for segment in segments}
    items = identification(answers)
    name = next((value for label, value in items if label == "Nome"), "")
    attention = [
        {
            "pillar": item,
            "display": display_score(item.score),
            "icon": icons[item.pillar.code]["icon"],
            "color": icons[item.pillar.code]["colors"]["bottom"],
        }
        for item in attention_pillars(pillars)
    ]
    bands = {band for band, _, _ in pillar_guidance.BAND_LEGEND}
    return {
        "assessment": assessment,
        "result": result,
        "overall_display": display_score(result.overall_score),
        "center_band_color": CENTER_BAND_COLORS.get(result.overall_band, INK),
        "center_message": _band_message(result.overall_band),
        "band_messages": {band: _band_message(band) for band in bands},
        "band_colors": CENTER_BAND_COLORS,
        "segments": segments,
        "spec": SPEC,
        "attention": attention,
        "recommendations": recommendations(pillars),
        "legend": pillar_guidance.BAND_LEGEND,
        "identification": items,
        "collaborator_name": name,
        "initials": initials(name),
        "evolution": evolution(pillars, previous.pillars if previous else None),
        "previous_completed_at": previous.completed_at if previous else None,
    }
