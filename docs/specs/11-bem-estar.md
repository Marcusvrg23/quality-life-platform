# 11 — Bem-estar: Ginástica Laboral, Meditação, Relaxamento e Meu Progresso

OBJETIVO
O colaborador pratica pausas guiadas (ginástica em sessões cronometradas com
vídeo, meditação com guia de respiração e sons de relaxamento), acompanha o
próprio progresso, e a empresa vê só o uso agregado.

ATORES E FLUXO
- Qualquer papel com acesso a Exercícios: Hoje (saudação + 4 atalhos) →
  Ginástica Laboral / Meditação / Relaxamento → clica "Começar" → vídeo em loop
  e cronômetro → ao concluir (ou ao sair depois de 60 s) a prática é gravada →
  Meu Progresso mostra dias seguidos, minutos e troféus.
- CORPORATE_MANAGER / ADMIN: Relatório da empresa → seção "Uso das práticas de
  bem-estar" com pessoas ativas, minutos e práticas por tipo, só com 5+ pessoas.

ACEITE
1. Dado o catálogo, quando os testes rodam, então todo item "disponivel" aponta
   para arquivo/exercício existente, nenhum "em_preparacao" tem botão de tocar
   e os 10 mp4 existem com ≤ 3 MB.
2. Dada uma sessão de ginástica, então ela usa só slugs de `config/exercises.py`
   e a soma dos tempos é a duração anunciada (3, 5 ou 10 min).
3. Dado um colaborador que conclui uma sessão (ou passa de 60 s), quando o
   front faz POST com CSRF, então uma `ActivitySession` é gravada para ele e a
   empresa ativa; sem CSRF → 403; slug inexistente → 404; menos de 60 s sem
   concluir → 400.
4. Dado o fuso America/Sao_Paulo, quando há práticas às 23:30 e 00:30 locais,
   então contam em dias diferentes para a sequência e os minutos da semana/mês.
5. Dados os marcos (1ª prática; 3, 7 e 30 dias seguidos; 60 min), então os
   troféus aparecem só quando atingidos.
6. Dado o relatório da empresa, quando 4 pessoas praticaram no período, então
   nenhum número de uso aparece; com 5, aparecem só agregados; colaborador não
   acessa.
7. Dado o Hoje, então aparece "Bom dia/Boa tarde/Boa noite" + primeiro nome da
   última avaliação concluída da própria pessoa (sem avaliação: só saudação).
8. Em 390 e 1280: sem rolagem horizontal, sem erro de console, GSAP ocioso
   (exceto loops `data: 'loop'`), reduced motion sem loop, áudio/vídeo só após
   clique.

INVARIANTES
- Tenant: registro e progresso filtram por `resolve_tenant_context`; dados de
  outra empresa nunca aparecem (inclusive para quem está em duas empresas).
- Autorização no servidor: agregado só para CORPORATE_MANAGER/ADMIN.
- Agregado: `MIN_GROUP = 5` por período e por tipo; nunca nome, e-mail, ranking.
- Conteúdo: nada de roteiro de meditação, dica de saúde ou tempo "oficial"
  inventado; tempos e ritmo de respiração ficam em constantes "PROPOSTA".
- Mobile-first: sem scroll horizontal em 390×844.

FORA DO ESCOPO
Narração, sons da natureza/mar/chuva/música (vagas "Em preparação"), imagem do
material para `inclinacao-frente`, PWA autenticada, edição do catálogo pelo
admin, metas/lembretes.

RISCO
R2 (migração nova, dados por pessoa, agregado para gestor).

PLANO (fatias)
1. Vídeos + README + `inclinacao-frente` + catálogo. 2. App `wellbeing`
(model, migração, POST). 3. Ginástica. 4. Meditação. 5. Relaxamento.
6. Meu Progresso. 7. Hoje + menu. 8. Agregado no relatório. 9. Playwright.
Linha de corte: fundo visual do Relaxamento e som de fundo na Meditação.

DECISÕES
- Registro de prática: uma linha por sessão, enviada ao concluir, ao clicar em
  "Encerrar" ou ao sair da página (fetch `keepalive`) se passou de 60 s. O
  servidor recalcula `started_at` (= agora − duração) e limita a duração ao
  máximo do item do catálogo.
- Sequência de dias: conta até hoje; se ainda não praticou hoje, a sequência de
  ontem continua valendo. Troféus de sequência usam a maior sequência já feita.
- Semana = segunda a domingo; mês = mês do calendário (ambos no fuso local).
- Agregado da empresa: semana e mês correntes; por tipo só aparece se o tipo
  tiver 5+ pessoas.
- Tenant forjado na sessão segue o padrão do projeto (`resolve_tenant_context`
  → 403); slug de outra coisa → 404. Não existe endpoint por id.

PERGUNTAS (não bloqueiam)
- Segundos por exercício (`SECONDS_PER_EXERCISE`) e ritmo de respiração
  (`BREATH_IN_SECONDS`/`BREATH_OUT_SECONDS`) aguardam aprovação da Quality Life.
- Exercícios ilustrados por IA aguardam revisão de profissional de educação
  física.
