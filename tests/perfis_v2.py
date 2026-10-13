"""Perfis de resposta do questionário v2, montados só a partir do JSON.

Cada perfil é um plano: código da pergunta -> o que a pessoa marca na tela.
- {"option": "o1"} ou {"option": "o6", "text": "..."}: escolha única/escala
- {"options": ["o1", "o2"]}: múltipla escolha
- {"text": "..."}: pergunta aberta
- None: deixa em branco (só perguntas opcionais)
"""

from .oracle_v2 import questions

PROFILES = ("a", "b", "c", "d", "e", "f")
TITLES = {
    "a": "tudo na melhor opção",
    "b": "tudo na pior opção",
    "c": "misto realista",
    "d": "misto com opções que não contam ponto",
    "e": "melhor opção com as opcionais em branco",
    "f": "melhor opção com exclusivas e “Outro:”",
}
# Perfil (c): posição no ranking da melhor para a pior opção, em ciclo.
MIXED_RANKS = (1, 0, 2, 1, 3, 1, 0, 2, 1)
# Perfil (c): notas de 0 a 10 marcadas na autoavaliação, em ciclo.
MIXED_SCALE = (7, 8, 6, 5, 9, 7)


def secrets(profile):
    """Textos pessoais digitados. Nunca podem chegar ao gestor."""
    tag = profile.upper()
    return {
        "q1-1": f"Pessoa Perfil {tag}",
        "q1-2": f"MATRICULA-SECRETA-{tag}",
        "q1-4": f"Cargo Secreto {tag}",
        "q12-3": f"Texto livre secreto {tag}",
        "other": f"Setor Secreto {tag}",
    }


def counting(question):
    """Opções que contam ponto, da melhor para a pior (empate: ordem do texto)."""
    options = [o for o in question["options"] if o["counts_for_score"]]
    return sorted(options, key=lambda o: -o["score_value"])


def _scored(profile, question, index, scale_index):
    ranked = counting(question)
    if profile in ("a", "e", "f"):
        return ranked[0]["code"]
    if profile == "b":
        return ranked[-1]["code"]
    if profile == "d":
        free = [o for o in question["options"] if not o["counts_for_score"]]
        if free:
            return free[0]["code"]
    if question["kind"] == "SCALE":
        return f"o{MIXED_SCALE[scale_index % len(MIXED_SCALE)] + 1}"
    return ranked[min(MIXED_RANKS[index % len(MIXED_RANKS)], len(ranked) - 1)]["code"]


def _unscored(profile, question):
    typed = secrets(profile)
    blank_optionals = profile == "e"
    if not question["required"] and blank_optionals:
        return None
    if question["kind"] == "TEXT":
        return {"text": typed.get(question["code"], f"Resposta {question['code']}")}
    options = question["options"]
    if question["kind"] == "MULTIPLE":
        if profile == "f":
            return {"options": [o["code"] for o in options if o["exclusive"]]}
        return {"options": [o["code"] for o in options if not o["exclusive"]][:2]}
    if profile == "f":
        other = [o for o in options if o["requires_text"]]
        if other:
            return {"option": other[0]["code"], "text": typed["other"]}
        return {"option": options[-1]["code"]}
    return {"option": options[0]["code"]}


def plan(data, profile):
    answers = {}
    index = scale_index = 0
    for question in questions(data):
        if question["scorable"]:
            answers[question["code"]] = {
                "option": _scored(profile, question, index, scale_index)
            }
            if question["kind"] == "SCALE":
                scale_index += 1
            else:
                index += 1
        else:
            answers[question["code"]] = _unscored(profile, question)
    return answers


def scored_choices(data, answers):
    """Só o que o gabarito precisa: pergunta pontuada -> opção."""
    return {
        q["code"]: answers[q["code"]]["option"]
        for q in questions(data)
        if q["scorable"] and answers.get(q["code"])
    }
