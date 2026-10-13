"""Read the official questionnaire Markdown into plain data.

The file in docs/questionario/ is the source of truth for v2 question text,
order, kind and options. Parsing is strict: an unexpected line is an error,
so a change to the text cannot slip silently into or out of the JSON.
No database, no Django: the generator script and the tests share this module.
"""

import re
from dataclasses import dataclass, field

SINGLE = "SINGLE"
MULTIPLE = "MULTIPLE"
TEXT = "TEXT"
SCALE = "SCALE"

SCALE_LABELS = tuple(str(value) for value in range(11))
_SECTION = re.compile(r"^# \S+\s+(\d+)\.\s+(.+?)\s*$")
_NUMBERED = re.compile(r"^(\d+\.\d+)\s+(.+)$")
_BOLD = re.compile(r"^\*\*(.+?)\*\*$")
_BLANK = re.compile(r"_{3,}")
_LEADING_SYMBOLS = re.compile(r"^[^\w\"(]+")
_OPTION_PREFIXES = {"- ( ) ": SINGLE, "- [ ] ": MULTIPLE}


@dataclass
class MarkdownOption:
    label: str
    requires_text: bool = False


@dataclass
class MarkdownQuestion:
    number: str
    text: str
    kind: str = ""
    help_text: str = ""
    options: list = field(default_factory=list)


@dataclass
class MarkdownSection:
    number: int
    title: str
    intro: str = ""
    questions: list = field(default_factory=list)


def _plain(text):
    return text.replace("**", "").strip()


def _option(raw):
    label = _BLANK.sub("", raw).strip()
    return MarkdownOption(label=label, requires_text=label != raw.strip())


def parse_official_markdown(text):
    """Return the numbered sections with their questions, in reading order."""
    sections = []
    question = None
    lines = text.splitlines()

    def fail(index, message):
        raise ValueError(f"linha {index + 1}: {message}: {lines[index]!r}")

    def set_kind(index, kind):
        if question.kind and question.kind != kind:
            fail(index, "tipo de resposta misturado na mesma pergunta")
        question.kind = kind

    def is_scale(line):
        return _plain(line) == " ".join(SCALE_LABELS)

    def next_is_scale(index):
        following = (line for line in lines[index + 1 :] if line.strip())
        return is_scale(next(following, ""))

    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line or line == "---":
            continue
        if raw.startswith("# "):
            match = _SECTION.match(raw)
            if match:
                sections.append(MarkdownSection(int(match[1]), match[2]))
                question = None
                continue
            if sections:
                break  # The result description after section 12 is not a question.
            continue
        if not sections:
            continue
        section = sections[-1]
        if raw.startswith("### "):
            heading = _LEADING_SYMBOLS.sub("", raw[4:]).strip()
            match = _NUMBERED.match(heading)
            number, body = (match[1], match[2]) if match else ("", heading)
            question = MarkdownQuestion(number=number, text=body)
            section.questions.append(question)
            continue
        if is_scale(line):
            if question is None or question.options:
                fail(index, "escala sem pergunta")
            set_kind(index, SCALE)
            question.options = [MarkdownOption(label) for label in SCALE_LABELS]
            continue
        bold = _BOLD.match(line)
        if bold and next_is_scale(index):
            # Section 11: an unnumbered bold question answered on the 0-10 scale.
            question = MarkdownQuestion(number="", text=bold[1].strip())
            section.questions.append(question)
            continue
        if bold and question is not None and not question.kind:
            question.help_text = bold[1].strip()
            continue
        prefix = next((p for p in _OPTION_PREFIXES if line.startswith(p)), None)
        if prefix:
            if question is None:
                fail(index, "opção fora de pergunta")
            set_kind(index, _OPTION_PREFIXES[prefix])
            question.options.append(_option(line[len(prefix) :]))
            continue
        if _BLANK.fullmatch(line):
            if question is None or question.options:
                fail(index, "campo de texto fora de pergunta")
            set_kind(index, TEXT)
            continue
        if question is None and not section.intro:
            section.intro = _plain(line)
            continue
        fail(index, "linha inesperada")
    for section in sections:
        for item in section.questions:
            if not item.kind:
                raise ValueError(f"pergunta sem resposta: {item.text!r}")
    return sections
