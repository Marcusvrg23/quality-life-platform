"""Textos exibidos no mapa individual (tela "Seu mapa de qualidade de vida").

ONDE O CLIENTE PREENCHE AS RECOMENDAÇÕES
    ``PILLAR_GUIDANCE``: um texto por pilar, mostrado no card de
    "Recomendações personalizadas" quando o pilar está entre as 3 menores
    notas. Os textos de orientação de saúde AINDA NÃO FORAM APROVADOS pela
    Quality Life, então ficam vazios. Com texto vazio, o card mostra só o
    título e o botão ("Ver exercícios" ou "Ver aulas"). Para publicar um
    texto aprovado, escreva-o entre as aspas do pilar; quebras de linha
    viram parágrafos.

Nada aqui altera nota, faixa ou prioridade: é só texto de tela.
"""

PILLAR_GUIDANCE = {
    "physical_health": "",
    "preventive_behavior": "",
    "physical_activity": "",
    "nutrition_hydration": "",
    "mental_emotional_health": "",
    "sleep_recovery": "",
    "ergonomics_workplace": "",
    "relationships": "",
    "work_life_balance": "",
}

# Legenda e mensagem do centro do coração: textos do modelo aprovado
# (docs/questionario/referencia-mapa-individual.png).
BAND_LEGEND = (
    ("EXCELENTE", "85 a 100", "Você está indo muito bem!"),
    ("BOM", "70 a 84", "Continue assim!"),
    ("ATENÇÃO", "40 a 69", "Atenção! Há pontos que precisam de cuidado."),
    ("PRIORIDADE", "0 a 39", "Essas áreas precisam de atenção prioritária."),
)

# O modelo só traz a mensagem do centro para ATENÇÃO; as outras faixas usam
# a frase da legenda.
OVERALL_MESSAGES = {
    "ATENÇÃO": "Você está no caminho certo! Algumas áreas merecem mais atenção.",
}
