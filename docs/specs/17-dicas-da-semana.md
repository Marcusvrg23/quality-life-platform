# 17 — Dicas da semana e datas especiais

OBJETIVO
Toda segunda-feira às 10h cada colaborador recebe uma dica curta de bem-estar
(na tela Hoje e por notificação), e nas datas especiais recebe a dica da data.
Textos escritos pela Quality Life ou aprovados por ela.

ATORES E FLUXO
Colaborador, gestor e admin com empresa ativa. Hoje mostra o cartão "Dica da
semana" (ou "Data especial" no dia). Quem ativou as notificações em Lembretes
recebe a dica no celular; desmarcar "Dicas e datas especiais" desliga.

ACEITE
1. Com `PUBLISHED = False` (estado deste PR) a Hoje não mostra dica da semana,
   nada é enviado e o plano do agendador não faz consulta a mais.
2. Com os textos publicados, segunda às 10h (America/Sao_Paulo) cada pessoa
   ativa com aparelho recebe a dica da semana uma vez; terça não há envio; um
   envio com mais de 5 minutos de atraso não sai.
3. Data especial: sai às 10h do dia calculado (fim de semana → sexta antes;
   1º de maio → dia útil anterior; campanha de mês → 1º dia útil); se duas
   caem no mesmo dia, sai a primeira da lista.
4. Dois workers ou um reinício não repetem a dica: `TipDispatch` é único por
   (pessoa, dia).
5. Quem desligou as dicas, membership/empresa inativa ou quem já recebeu uma
   dica no dia não recebe. Texto que contém o nome/e-mail da pessoa (ex.:
   "Outubro Rosa" para rosa@…) pula só essa pessoa.
6. A Hoje mostra a dica da semana em qualquer dia da semana e a data especial
   no dia dela, com link quando a dica aponta para uma tela do app.
7. Lembretes explica que as dicas ainda não são enviadas enquanto não houver
   publicação, e o horário quando houver.

INVARIANTES
Textos genéricos (`ensure_generic`): nunca nome, nota, resposta ou dado de
saúde; o registro de envio guarda só ids e data. Nenhum envio fora de
`notify()`. Plano econômico para o Neon: só acorda o banco no horário da dica.

DECISÕES
- Rascunho no doc "Dicas Quality Life — calendário para aprovação" (19/10/2026):
  26 dicas semanais em ciclo pela semana ISO e 14 datas especiais. Ligar =
  `PUBLISHED = True` depois da aprovação, com as correções dela.
- Sem IA nesta etapa: textos fixos, aprovados.

FORA DO ESCOPO
Chat com IA; dicas por empresa; edição dos textos pelo Painel.

RISCO
R1 (envio de notificação, migração aditiva `wellbeing.0005_tip_dispatch`).
