"""Wellbeing catalog: gym sessions, meditations, sounds and tips of the day.

COMO PREENCHER (sem mexer em código de tela):
- Vídeo novo: coloque o .mp4 (≤ 3 MB, sem áudio) e o poster .webp de mesmo
  nome em static/quality_life/videos/wellbeing/ e aponte "file" para ele.
- Áudio novo (natureza, mar, chuva, música): coloque o arquivo em
  static/quality_life/audio/, preencha "file" com
  "quality_life/audio/<nome>.mp3" e troque "status" para AVAILABLE.
- Dica do dia: acrescente {"slug": ..., "text": ..., "source": ...} em TIPS,
  só com texto aprovado pela Quality Life. A Home mostra a dica apenas se
  houver alguma.
- Nunca escreva roteiro de meditação, dica de saúde ou tempo "oficial" aqui
  sem aprovação: o que não existe fica IN_PREPARATION ("Em preparação").

Each item has: slug, title, category, duration_seconds (None when the person
picks a timer), type (sequence | breathing | noise | audio | video), file
(static path or None), status (AVAILABLE | IN_PREPARATION) and kind (the
ActivitySession kind it is recorded under). Composition of the gym sessions is
documented in docs/specs/11-bem-estar.md.
"""

from itertools import cycle, islice

from .exercises import VIDEO_DIR

AVAILABLE = "disponivel"
IN_PREPARATION = "em_preparacao"

KIND_GYM = "ginastica"
KIND_MEDITATION = "meditacao"
KIND_RELAXATION = "relaxamento"

# PROPOSTA — aguardando aprovação da Quality Life.
# Seconds each exercise stays on screen in a gym session.
SECONDS_PER_EXERCISE = 30
# PROPOSTA — aguardando aprovação da Quality Life.
# Breathing guide rhythm (inhale, then exhale) used by every meditation.
BREATH_IN_SECONDS = 4
# PROPOSTA — aguardando aprovação da Quality Life.
BREATH_OUT_SECONDS = 6

# Shown next to every timed session while the constants above are proposals.
PROPOSAL_NOTE = "Tempos em proposta, aguardando aprovação da Quality Life."
AI_VIDEO_NOTE = (
    "Vídeos ilustrativos gerados por IA a partir do material Quality Life;"
    " revisão por profissional de educação física pendente."
)

GYM_MINUTES = (3, 5, 10)
GYM_CATEGORIES = (
    {
        "slug": "pescoco-ombros",
        "title": "Alongamento para pescoço e ombros",
        "exercises": ("pescoco", "abertura-peito", "punhos", "autoabraco"),
        # "Na cadeira": the seated finger/wrist stretch replaces the standing
        # arms/wrists one; the other exercises stay as in the material.
        "chair": {"punhos": "sentado"},
    },
    {
        "slug": "pausa-coluna",
        "title": "Pausa ativa para coluna",
        "exercises": ("inclinacao-frente", "lateral", "passo-largo", "abertura-peito"),
        "chair": None,
    },
    {
        "slug": "energizacao",
        "title": "Energização matinal",
        "exercises": ("passo-largo", "lateral", "punhos", "abertura-peito"),
        "chair": None,
    },
)


def _gym_session(category, minutes, chair):
    exercises = category["exercises"]
    if chair:
        exercises = tuple(category["chair"].get(slug, slug) for slug in exercises)
    seconds = minutes * 60
    steps = tuple(islice(cycle(exercises), seconds // SECONDS_PER_EXERCISE))
    suffix = "-cadeira" if chair else ""
    return {
        "slug": f"{category['slug']}{suffix}-{minutes}min",
        "title": category["title"],
        "category": category["title"],
        "category_slug": category["slug"],
        "duration_seconds": seconds,
        "minutes": minutes,
        "chair": chair,
        "type": "sequence",
        "file": None,
        "status": AVAILABLE,
        "kind": KIND_GYM,
        "steps": steps,
    }


GYM_SESSIONS = tuple(
    _gym_session(category, minutes, chair)
    for category in GYM_CATEGORIES
    for chair in ((False, True) if category["chair"] else (False,))
    for minutes in GYM_MINUTES
)

MEDITATIONS = (
    {
        "slug": "respiracao-foco",
        "title": "Respiração para foco",
        "category": "Meditação",
        "duration_seconds": 120,
        "type": "breathing",
        "file": f"{VIDEO_DIR}med-foco.mp4",
        "status": AVAILABLE,
        "kind": KIND_MEDITATION,
    },
    {
        "slug": "reduzir-ansiedade",
        "title": "Reduzir ansiedade",
        "category": "Meditação",
        "duration_seconds": 300,
        "type": "breathing",
        "file": f"{VIDEO_DIR}med-ansiedade.mp4",
        "status": AVAILABLE,
        "kind": KIND_MEDITATION,
    },
    {
        "slug": "relaxamento-profundo",
        "title": "Relaxamento profundo",
        "category": "Meditação",
        "duration_seconds": 600,
        "type": "breathing",
        "file": f"{VIDEO_DIR}med-relaxamento.mp4",
        "status": AVAILABLE,
        "kind": KIND_MEDITATION,
    },
)


def _sound(slug, title, category, sound_type, *, noise=None):
    return {
        "slug": slug,
        "title": title,
        "category": category,
        "duration_seconds": None,
        "type": sound_type,
        "file": None,
        "status": AVAILABLE if sound_type == "noise" else IN_PREPARATION,
        "kind": KIND_RELAXATION,
        "noise": noise,
    }


SOUNDS = (
    # Generated in the browser with the Web Audio API: no file.
    _sound("ruido-branco", "Ruído branco", "Ruídos", "noise", noise="white"),
    _sound("ruido-rosa", "Ruído rosa", "Ruídos", "noise", noise="pink"),
    _sound("ruido-marrom", "Ruído marrom", "Ruídos", "noise", noise="brown"),
    # Em preparação until a file exists in static/quality_life/audio/.
    _sound("natureza", "Sons da natureza", "Sons", "audio"),
    _sound("mar", "Mar", "Sons", "audio"),
    _sound("chuva", "Chuva", "Sons", "audio"),
    _sound("musica-concentracao", "Música para concentração", "Sons", "audio"),
)
RELAX_TIMER_MINUTES = (5, 10, 15, 30)
RELAX_BACKGROUND = f"{VIDEO_DIR}med-relaxamento.mp4"

TIPS = ()


def all_items():
    return (*GYM_SESSIONS, *MEDITATIONS, *SOUNDS)


def find_available(kind, slug):
    """The playable catalog item for a recorded practice, or None."""
    for item in all_items():
        if (
            item["kind"] == kind
            and item["slug"] == slug
            and item["status"] == AVAILABLE
        ):
            return item
    return None


def max_seconds(item):
    """Longest practice the server accepts for an item."""
    return item["duration_seconds"] or max(RELAX_TIMER_MINUTES) * 60


def tip_of_the_day(day):
    """Deterministic tip for a date, or None while TIPS has no text."""
    tips = [tip for tip in TIPS if tip.get("text", "").strip()]
    if not tips:
        return None
    return tips[day.toordinal() % len(tips)]
