"""Weekly tips and special dates (docs/specs/17-dicas-da-semana.md).

COMO FUNCIONA
- Toda segunda-feira às 10h (America/Sao_Paulo) sai a dica da semana; numa
  data especial sai a dica da data. No máximo uma dica por pessoa por dia.
- A tela Hoje mostra a dica da data no dia dela e, nos outros dias, a dica da
  semana.
- Os textos são genéricos (podem aparecer na tela bloqueada): nunca nome,
  nota, resposta ou dado de saúde.

APROVAÇÃO
Os textos abaixo são o rascunho do doc "Dicas Quality Life — calendário para
aprovação". Nada aparece nem é enviado enquanto ``PUBLISHED`` for False; só
ligue depois que a Quality Life aprovar os textos (e aplique aqui as
correções dela).
"""

from dataclasses import dataclass
from datetime import date, time, timedelta

PUBLISHED = False
SEND_TIME = time(10, 0)
WEEKLY_WEEKDAY = 0  # Monday


@dataclass(frozen=True)
class Tip:
    title: str
    text: str
    route: str = "app"  # URL name the notification opens
    label: str = "Dica da semana"


WEEKLY_TIPS = (
    Tip(
        "Copo d'água por perto",
        "Deixe um copo ou garrafa de água na mesa e beba aos poucos durante o dia.",
    ),
    Tip(
        "Levante a cada hora",
        "Uma vez por hora, levante e dê alguns passos, nem que seja até o bebedouro.",
    ),
    Tip(
        "Pés no chão",
        "Sente com os pés apoiados no chão e as costas encostadas na cadeira.",
    ),
    Tip(
        "Descanse a vista",
        "A cada 20 minutos de tela, olhe para longe por uns 20 segundos.",
    ),
    Tip(
        "Três respirações",
        "Antes de uma reunião, respire fundo três vezes, soltando o ar devagar.",
    ),
    Tip(
        "Pescoço solto",
        "Incline a cabeça devagar para um lado e para o outro, sem forçar.",
    ),
    Tip(
        "Tela na altura dos olhos",
        "Ajuste o monitor para que o topo da tela fique na altura dos seus olhos.",
    ),
    Tip(
        "Escada quando der",
        "Se for possível e confortável, troque o elevador pela escada em um trajeto curto.",
    ),
    Tip(
        "Pausa com alguém",
        "Chame um colega para a pausa do café e converse sobre algo fora do trabalho.",
    ),
    Tip(
        "Abra e feche as mãos",
        "Abra e feche as mãos algumas vezes e gire os punhos com calma.",
    ),
    Tip(
        "Uma tarefa por vez",
        "Escolha a tarefa mais importante do dia e comece por ela, sem pular entre abas.",
    ),
    Tip(
        "Solte os ombros",
        "Suba os ombros em direção às orelhas e solte devagar. Repita algumas vezes.",
    ),
    Tip(
        "Um pouco de luz do dia",
        "Se puder, passe alguns minutos perto de uma janela ou ao ar livre.",
    ),
    Tip(
        "Fruta no lanche", "Que tal incluir uma fruta no lanche da tarde desta semana?"
    ),
    Tip(
        "Almoço sem tela",
        "No almoço, deixe o celular de lado e preste atenção na refeição.",
    ),
    Tip(
        "Cinco minutos de movimento",
        "Abra a Ginástica Laboral no app e faça uma sequência curta.",
        "wellbeing_gym",
    ),
    Tip(
        "Alongue as costas",
        "Em pé, entrelace as mãos à frente e estique os braços, arredondando as costas.",
    ),
    Tip("Rotina de dormir", "Tente deitar perto do mesmo horário nos dias de semana."),
    Tip("Uma coisa boa", "Ao fim do dia, pense em uma coisa que deu certo hoje."),
    Tip(
        "Um minuto de silêncio",
        "Abra a Meditação no app e fique um minuto só respirando.",
        "wellbeing_meditation",
    ),
    Tip(
        "Tornozelos em movimento",
        "Sentado, gire os tornozelos e mova os pés para cima e para baixo.",
    ),
    Tip(
        "Garrafa à vista",
        "Água à vista lembra de beber. Encha a garrafa logo ao chegar.",
    ),
    Tip(
        "Som de natureza",
        "Na pausa, abra o Relaxamento no app e escute um som de natureza.",
        "wellbeing_relax",
    ),
    Tip(
        "Mesa em ordem", "Tire da mesa o que não está usando. Menos bagunça, mais foco."
    ),
    Tip("Pausa de verdade", "Na pausa, levante da cadeira e saia da frente da tela."),
    Tip(
        "Veja seu progresso",
        "Abra Meu Progresso e veja quantas pausas você já fez.",
        "wellbeing_progress",
    ),
)

# When a special date goes out:
# ("date", month, day)        that day; Saturday/Sunday -> the Friday before
# ("first_business_day", m)   first Monday-to-Friday of the month
# ("last_day", month)         last day of the month; weekend -> Friday before
# ("business_day_before", m, d) the Monday-to-Friday day before (a holiday)
CVV = "Precisa conversar? CVV, ligue 188, 24 horas, gratuito."
SPECIAL_DATES = (
    (
        ("first_business_day", 1),
        Tip(
            "Janeiro Branco",
            "Comece o ano com calma: reserve alguns minutos hoje para uma pausa de respiração.",
            label="Data especial",
        ),
    ),
    (
        ("last_day", 2),
        Tip(
            "Cuide das mãos e punhos",
            "Hoje é dia de prevenção às LER/DORT. Faça uma pausa e alongue mãos, punhos e ombros.",
            label="Data especial",
        ),
    ),
    (
        ("date", 3, 8),
        Tip(
            "Dia Internacional da Mulher",
            "Hoje celebramos as mulheres que fazem a empresa acontecer. Cuide-se e faça sua pausa.",
            label="Data especial",
        ),
    ),
    (
        ("date", 3, 22),
        Tip(
            "Dia Mundial da Água",
            "Deixe uma garrafa de água por perto e beba aos poucos ao longo do dia.",
            label="Data especial",
        ),
    ),
    (
        ("date", 4, 6),
        Tip(
            "Dia da Atividade Física",
            "Mexa-se hoje: uma caminhada curta ou a ginástica laboral do app já contam.",
            "wellbeing_gym",
            "Data especial",
        ),
    ),
    (
        ("date", 4, 7),
        Tip(
            "Dia Mundial da Saúde",
            "Saúde também é rotina: pausa, água, movimento e descanso. Escolha um para hoje.",
            label="Data especial",
        ),
    ),
    (
        ("date", 4, 28),
        Tip(
            "Segurança no trabalho",
            "Ajuste a cadeira e a altura da tela hoje. Um posto confortável também é cuidado.",
            label="Data especial",
        ),
    ),
    (
        ("business_day_before", 5, 1),
        Tip(
            "Dia do Trabalhador",
            "Reconhecemos o trabalho de cada um. Bom descanso no feriado.",
            label="Data especial",
        ),
    ),
    (
        ("date", 7, 27),
        Tip(
            "Prevenção de acidentes",
            "Olhe ao redor: fio solto, caixa no caminho ou cadeira bamba? Avise quem pode resolver.",
            label="Data especial",
        ),
    ),
    (
        ("date", 9, 1),
        Tip(
            "Dia da Educação Física",
            "Hoje celebramos quem ensina o movimento. Aproveite e faça a ginástica laboral do app.",
            "wellbeing_gym",
            "Data especial",
        ),
    ),
    (
        ("date", 9, 10),
        Tip(
            "Setembro Amarelo",
            f"Cuidar da mente também é cuidar da saúde. {CVV}",
            label="Data especial",
        ),
    ),
    (
        ("first_business_day", 10),
        Tip(
            "Outubro Rosa",
            "Um lembrete carinhoso: cuide de você e mantenha consultas e exames em dia.",
            label="Data especial",
        ),
    ),
    (
        ("date", 10, 10),
        Tip(
            "Saúde mental",
            "Respire fundo três vezes, devagar. Uma pausa curta ajuda a recomeçar com calma.",
            label="Data especial",
        ),
    ),
    (
        ("first_business_day", 11),
        Tip(
            "Novembro Azul",
            "Um lembrete carinhoso: cuide de você e mantenha consultas e exames em dia.",
            label="Data especial",
        ),
    ),
)


def _weekday_or_friday_before(day):
    # Saturday (5) -> Friday, Sunday (6) -> Friday.
    return day - timedelta(days=max(0, day.weekday() - 4))


def send_day(rule, year):
    """The local date a special date goes out in ``year``."""
    kind = rule[0]
    if kind == "date":
        return _weekday_or_friday_before(date(year, rule[1], rule[2]))
    if kind == "first_business_day":
        day = date(year, rule[1], 1)
        while day.weekday() > 4:
            day += timedelta(days=1)
        return day
    if kind == "last_day":
        month = rule[1]
        first_next = date(year + (month == 12), month % 12 + 1, 1)
        return _weekday_or_friday_before(first_next - timedelta(days=1))
    if kind == "business_day_before":
        day = date(year, rule[1], rule[2]) - timedelta(days=1)
        while day.weekday() > 4:
            day -= timedelta(days=1)
        return day
    raise ValueError(f"Unknown special date rule: {rule!r}")


def special_tip_on(day):
    """The special date that goes out on ``day``; the first listed wins a tie."""
    for rule, tip in SPECIAL_DATES:
        if send_day(rule, day.year) == day:
            return tip
    return None


def weekly_tip(day):
    """The tip of the ISO week of ``day`` (26 tips, twice a year)."""
    return WEEKLY_TIPS[(day.isocalendar().week - 1) % len(WEEKLY_TIPS)]


def tip_to_send(day):
    """What goes out by push on ``day`` at ``SEND_TIME``, or None."""
    if not PUBLISHED:
        return None
    special = special_tip_on(day)
    if special is not None:
        return special
    if day.weekday() == WEEKLY_WEEKDAY:
        return weekly_tip(day)
    return None


def tip_to_show(day):
    """What the Hoje screen shows on ``day``, or None while unpublished."""
    if not PUBLISHED:
        return None
    return special_tip_on(day) or weekly_tip(day)
