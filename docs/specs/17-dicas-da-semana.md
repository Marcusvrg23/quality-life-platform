# 17 — Dicas da semana e datas especiais

OBJETIVO
Cada colaborador recebe dicas curtas de bem-estar aprovadas pela Quality Life
por notificação, no intervalo que ele mesmo escolhe (padrão 60 min, de 3 a
480 min) dentro do seu expediente, e vê a dica da semana na tela Hoje. Nas
datas especiais a primeira dica do dia é a da data.

ATORES E FLUXO
Colaborador, gestor e admin com empresa ativa. Hoje mostra o cartão "Dica da
semana" (ou "Data especial" no dia). Quem ativou as notificações neste
aparelho em Lembretes recebe as dicas no celular, mesmo com os lembretes de
pausa desligados; desmarcar "Dicas e datas especiais" ou desativar as
notificações do aparelho desliga só para aquela conta.

ACEITE
1. Com `PUBLISHED = False` a Hoje não mostra dica da semana, nada é enviado e
   o plano do agendador não faz consulta a mais.
2. Com os textos publicados, cada pessoa ativa com aparelho recebe uma dica a
   cada `tips_interval_minutes` (início + k × intervalo, estritamente dentro
   do expediente, nos dias marcados, America/Sao_Paulo), com os lembretes de
   pausa ligados ou não; fora do expediente, em dia não marcado ou com mais de
   5 minutos de atraso não sai nada. Dicas seguidas da mesma pessoa percorrem
   as 26 dicas aprovadas em ordem.
3. Data especial: é a primeira dica do dia calculado (fim de semana → sexta
   antes; 1º de maio → dia útil anterior; campanha de mês → 1º dia útil); se
   duas caem no mesmo dia, sai a primeira da lista.
4. Dois workers ou um reinício não repetem a dica: `TipDispatch` é único por
   (pessoa, horário). Mudar o intervalo depois do refresh não envia no horário
   antigo; salvar Lembretes, as preferências ou o aparelho acorda o agendador.
5. Quem desligou as dicas, membership/empresa inativa ou sem aparelho não
   recebe. Não há limite diário: o ritmo é o intervalo da pessoa. Texto que
   contém o nome/e-mail da pessoa (ex.: "Outubro Rosa" para rosa@…) pula só
   essa pessoa naquele horário.
6. A Hoje mostra a dica da semana em qualquer dia da semana e a data especial
   no dia dela, com link quando a dica aponta para uma tela do app.
7. Lembretes explica que as dicas ainda não são enviadas enquanto não houver
   publicação e, publicadas, que chegam no intervalo escolhido.
8. Textos aprovados pela Quality Life em 19/10/2026: `PUBLISHED = True`.
9. Intervalo das dicas livre por pessoa (3 a 480 min, padrão 60), salvo em
   Lembretes junto com o expediente; fora da faixa → 400 com "Escolha um
   intervalo das dicas entre 3 e 480 minutos."; expediente menor ou igual ao
   intervalo → 400.

INVARIANTES
Textos genéricos (`ensure_generic`): nunca nome, nota, resposta ou dado de
saúde; o registro de envio guarda só ids e horário. Nenhum envio fora de
`notify()`. Plano econômico para o Neon: só acorda o banco no horário de uma
dica (intervalos curtos, como 3 min, mantêm o banco acordado no expediente de
quem os escolheu).

DECISÕES
- Doc "Dicas Quality Life — calendário para aprovação": 26 dicas semanais em
  ciclo pela semana ISO e 14 datas especiais, aprovadas sem alterações em
  19/10/2026, inclusive a revisão por profissional de Educação Física das
  dicas 6, 10, 12, 17 e 21.
- Horário: a Quality Life aceita qualquer horário comercial. Em 19/10/2026
  Marcus pediu envio automático a cada 60 min, com o colaborador ajustando o
  intervalo livremente (ex.: de 3 em 3 min); o envio fixo de segunda às 10h
  deixou de existir. O expediente e os dias são os de Lembretes (padrão
  08:00–18:00, seg–sex).
- Com as dicas ligadas, a "Dica do dia" do catálogo (`wellbeing_catalog.TIPS`,
  vazia) não aparece mais: a Hoje mostra a dica da semana.
- Sem IA nesta etapa: textos fixos, aprovados.

FORA DO ESCOPO
Chat com IA; dicas por empresa; edição dos textos pelo Painel.

RISCO
R1 (envio de notificação, migrações `wellbeing.0005_tip_dispatch` e
`wellbeing.0007_notificacoes_por_conta`, que troca o dia por horário e apaga
os registros de envio antigos, de no máximo dois dias).
