# 06 — Questionário v2 igual ao texto oficial

OBJETIVO
O colaborador responde exatamente o questionário de `docs/questionario/questionario-oficial-quality-life.md` (textos, ordem e opções), sem mudar nenhuma nota.

ATORES E FLUXO
- Colaborador: autoriza o uso dos dados → seção 1 (Identificação) → seções 2–11 → seção 12 → revisão → conclusão → Meu mapa com "Nome do colaborador" e "Data da avaliação".
- Gestor: relatório executivo inalterado; continua lendo só `PillarResult` agregado (grupo mínimo 5).
- Operação: `release` publica o v2 com `--retire-other-published`; o v1 vira RETIRED e avaliações concluídas no v1 continuam intactas.

ACEITE
1. Dado o `.md` oficial, quando comparado ao `quality_life_oficial_v2.json`, então número, texto, tipo, opções e ordem de cada pergunta são idênticos (teste falha em qualquer diferença).
2. Dadas as mesmas respostas pontuadas, quando calculadas no v1 e no v2, então nota geral, notas por pilar e faixas são idênticas, quaisquer que sejam as respostas não pontuadas.
3. Dada uma múltipla escolha (2.9, 4.4), quando a opção exclusiva ("Não sinto dores"/"Não pratico") vem junto com outra, então a resposta é recusada.
4. Dada uma pergunta de texto obrigatória vazia ou acima do limite (nome 150, demais 500), então é recusada; a opcional (12.3) pode ficar em branco. "Outro:" do Setor exige o texto.
5. Dado o relatório do gestor, então nenhuma resposta de identificação, texto livre ou múltipla escolha aparece; nenhuma agregação nova é criada.
6. Dado um colaborador de outra empresa, então não lê nem grava respostas de outra empresa (404/PermissionDenied).
7. Dado `release` rodando duas vezes, então o v2 fica PUBLISHED, o v1 RETIRED e a segunda execução não muda nada.
8. Dado 390×844, quando o colaborador percorre o fluxo completo (consentimento → seção 1 → … → seção 12 → mapa), então não há rolagem horizontal.

INVARIANTES
- Scoring determinístico: `calculate_assessment_scores` só usa perguntas `scorable` com pilar; pontuação idêntica ao v1.
- Imutabilidade: seções, novos campos e respostas (texto e múltipla escolha) seguem as guardas de modelo e os triggers PostgreSQL de questionário publicado e de avaliação concluída.
- Isolamento entre empresas e autorização no servidor (`_authorized_assessment`, `_assessment`).
- Gestor só vê agregado: nada de identificação, texto ou múltipla escolha em relatório.
- Regra dos 9 pilares intacta: seções 1 e 12 são seções não pontuadas, não pilares.
- Mobile-first, sem rolagem horizontal em 390×844.

FORA DO ESCOPO
Mudar pontuação ou faixas; recomendações personalizadas novas; exportar identificação; editar o v1 publicado; deploy.

RISCO
R2 (scoring, migração com triggers, dados pessoais de identificação).

PERGUNTAS
Nenhuma bloqueante. Decisões que não estavam no pedido ficam no handoff para o cliente revisar.
