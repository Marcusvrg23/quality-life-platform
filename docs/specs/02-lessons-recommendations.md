# 02 — Aulas em vídeo, recomendação e datas comemorativas na tela Hoje

OBJETIVO
O colaborador assiste às 3 aulas em vídeo do protótipo, vê na home a prioridade vinda da própria avaliação e recebe avisos de datas comemorativas.

ATORES E FLUXO
- Qualquer papel com empresa ativa: abre "Aulas" (`/app/aulas/`) e assiste aos 3 vídeos.
- Colaborador: na home vê o card "Sua prioridade agora" (pilar de menor nota da última avaliação concluída na empresa ativa) ou o convite para avaliar-se.
- Qualquer papel: na home vê o aviso da data comemorativa do dia.

ACEITE
1. Dado visitante anônimo, quando abre `/app/aulas/`, então vai ao login; logado com empresa ativa, vê 3 `<video controls playsinline preload="none" poster>` com `src` estático e os textos do protótipo.
2. Dado o menu, então "Aulas" aparece para todos os papéis; "Relatório da empresa", "Equipe" e "Trocar senha" continuam.
3. Dado avaliação concluída na empresa ativa, quando abre a home, então vê "Sua prioridade agora: <pilar de menor nota>"; empate decidido por `display_order`.
4. Dado o pilar physical_activity, ergonomics_workplace ou physical_health, então o card leva a Exercícios; nos demais, leva a "Minha avaliação" com "Conteúdo em definição pela Quality Life".
5. Dado usuário sem avaliação concluída na empresa ativa, então vê o convite para fazer a avaliação.
6. Dado dados de outro usuário ou de outra empresa, então nunca influenciam o card.
7. Dado 08/03, 01/05 ou qualquer dia de setembro, então a home mostra o aviso com título e "Conteúdo em definição pela Quality Life"; 02/05 não mostra.
8. Dado setembro, então também mostra "Precisa conversar? CVV — ligue 188, 24 horas, gratuito."; fora de setembro, nunca.

INVARIANTES
- Recomendação determinística, usa só `PillarResult` persistido; sem IA; nenhuma faixa de nota duplicada.
- Consulta filtra por `request.user` e pela empresa ativa; sem dado de terceiros.
- Mobile-first: sem scroll horizontal em 390×844.

FORA DO ESCOPO
Upload de vídeos pelo admin, IA, lembretes, outras datas, mudanças em scoring, relatório, equipe ou convites.

RISCO
R1.
