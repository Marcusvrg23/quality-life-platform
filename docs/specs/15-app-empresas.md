# 15 — App para empresas: textos finais e conclusão das atividades

OBJETIVO
O colaborador usa um app de empresa, não um protótipo: nenhum texto sobre IA,
proposta, aprovação pendente, minuta, exemplo ou conteúdo em definição na tela,
e cada atividade deixa claro quando terminou e o que entrou no progresso.

ATORES E FLUXO
Qualquer papel com empresa ativa: Hoje → Ginástica / Meditação / Relaxamento /
Exercícios / Aulas → concluir ou sair → tela ou aviso diz o que contou →
"Ver meu progresso". Detalhes do fluxo em `11-bem-estar.md`, seção
"CONCLUSÃO DAS ATIVIDADES".

ACEITE
1. Dadas as páginas Hoje, Ginástica, Meditação, Relaxamento, Exercícios, Aulas,
   Progresso, Lembretes, Instalar, Privacidade e Termos (logado, em setembro),
   então nenhuma contém `\bIA\b`, "inteligência artificial", "proposta",
   "aguardando", "MINUTA", "Exemplo de" ou "em definição".
2. `CONSENT_VERSION` continua "2026-10-minuta-1"; Privacidade mostra
   "Versão do texto: outubro de 2026".
3. `sequencia-exercicios` e `aula-<slug>` passam por `find_available`
   (kind `ginastica`), exigem 60 s e gravam na empresa ativa; tenant forjado → 403.
4. O cartão Hoje mostra só os números do dono na empresa ativa.
5. Em 390×844 e 1280×800: a tela de conclusão aparece sem rolagem e recebe o
   foco; os avisos de 60 s aparecem; Exercícios termina em "Sequência
   concluída"; Aulas mostra "Aula concluída"; Relaxamento mostra "Ver meu
   progresso"; sem erro de console e sem scroll horizontal.

INVARIANTES
Tenant e autorização no servidor (`resolve_tenant_context` no POST e no Hoje);
mínimo de 60 s no cliente e no banco (`MIN_RECORD_SECONDS` + CheckConstraint);
`ActivitySession.kind` continua só ginastica/meditacao/relaxamento (sem
migração); scoring e `CONSENT_VERSION` intocados.

TEXTOS QUE SAÍRAM DA TELA (antes → depois)
- Ginástica, rodapé e player: "Tempos em proposta, aguardando aprovação da
  Quality Life." e "Vídeos ilustrativos gerados por IA…; revisão por
  profissional de educação física pendente." → só "Instruções: <material>.";
  o player não tem mais `p.wb-note`.
- Meditação, rodapé: "… Tempos em proposta… Vídeos ilustrativos gerados por
  IA." → "Ritmo da respiração: inspire 4 s, expire 6 s."
- aria-label do vídeo do player: "Vídeo ilustrativo gerado por IA" →
  "<título>: vídeo do exercício" (ou "vídeo da meditação").
- Relaxamento: aria-label "Fundo visual ilustrativo gerado por IA" → "Fundo
  visual"; rodapé "Todos os sons são gerados no próprio navegador. Fundo
  visual: vídeo ilustrativo gerado por IA." → removido.
- Exercícios: alt "<título>: quadro do vídeo ilustrativo" → "<título>";
  "A sequência indica apenas sua navegação nesta sessão." → "Com 1 minuto ou
  mais na sequência, a prática entra no seu progresso."
- Hoje: "Conteúdo em definição pela Quality Life" (data comemorativa e
  prioridade fora dos pilares físicos) → removido; fica título + texto de apoio.
- Aulas: "Exemplo de…"/"Demonstração de…" → textos finais em `config/lessons.py`.
- Privacidade e Termos: faixa "MINUTA — pendente de revisão jurídica" →
  removida; "Versão do texto de consentimento: 2026-10-minuta-1" → "Versão do
  texto: outubro de 2026" (`CONSENT_TEXT_LABEL`).

PENDÊNCIAS QUE CONTINUAM (saíram da tela, não foram resolvidas)
- Aprovação da Quality Life dos tempos (`SECONDS_PER_EXERCISE`,
  `BREATH_IN_SECONDS`, `BREATH_OUT_SECONDS`, ainda "PROPOSTA" no código) e da
  pontuação do questionário (`status_note` do JSON).
- Revisão dos exercícios e dos vídeos ilustrativos (gerados por IA) por
  profissional de educação física.
- Revisão jurídica de Privacidade e Termos (os campos "[A definir pelo
  jurídico]" continuam no texto; `CONSENT_VERSION` não muda até lá).
- Vídeos definitivos das Aulas: os atuais têm 10 s e nunca somam os 60 s
  necessários para entrar no progresso.

FORA DO ESCOPO
Mudar constantes, docs de conteúdo, READMEs, o bloco de segurança
`exercises/_safety.html`, o scoring e migrações.

RISCO
R1 (telas e registro já existente; POST reutilizado sem migração).
