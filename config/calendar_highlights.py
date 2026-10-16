"""Fixed commemorative dates shown on the employee home."""

from dataclasses import dataclass

from django.utils import timezone

CVV_TEXT = "Precisa conversar? CVV — ligue 188, 24 horas, gratuito."


@dataclass(frozen=True)
class Highlight:
    title: str
    month: int
    day: int | None = None  # None: the whole month
    support_text: str = ""


HIGHLIGHTS = (
    Highlight("Dia Internacional da Mulher", month=3, day=8),
    Highlight("Dia do Trabalhador", month=5, day=1),
    Highlight(
        "Setembro Amarelo (prevenção do suicídio)",
        month=9,
        support_text=CVV_TEXT,
    ),
)


def active_highlight(today=None):
    """Return the highlight for ``today`` (default: local date), or None."""
    today = today or timezone.localdate()
    for highlight in HIGHLIGHTS:
        if highlight.month == today.month and highlight.day in (None, today.day):
            return highlight
    return None
