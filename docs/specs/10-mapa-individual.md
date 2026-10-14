# 10 — Mapa individual igual ao modelo do cliente

OBJETIVO        O colaborador vê o resultado da própria avaliação no layout de `docs/questionario/referencia-mapa-individual.png`, com o coração desenhado exatamente por `docs/design/heart/heart-spec.json`, e salva em PDF A4 paisagem.

ATORES E FLUXO  Colaborador conclui a avaliação → `/app/assessment/<id>/completed/` mostra, num cartão claro: cabeçalho (logo em anel, título, data), coração dos 9 pilares, identificação (q1-1 a q1-8), legenda, 3 áreas de atenção, recomendações, evolução e rodapé de confidencialidade. "Salvar em PDF" abre a impressão. Gestor, admin e colegas não acessam.

ACEITE
- Dado um resultado salvo, quando a página abre, então o SVG tem 9 gomos na ordem de posição do spec, cada um com `data-pillar-code`, polígono, ícone e posição de texto do spec.
- Dado notas 34, 56 e 88, então a cor de cada gomo é a interpolação de `color_stops_by_score` (gradiente topo ×1,10 e base ×0,86) e o texto é branco abaixo de 50 e a partir de 70, escuro entre 50 e 69.
- Dado uma nota salva com casas decimais (36,67), então a tela mostra só a parte inteira com "%" ("36%") e a faixa salva; o valor salvo e o relatório não mudam.
- Dado notas empatadas, então as 3 áreas de atenção são as 3 menores, com desempate por `Pillar.display_order`; cada uma tem um card de recomendação com o texto de `config/pillar_guidance.py` (vazio = só título e botão) e "Ver exercícios" para os pilares de exercício, "Ver aulas" para os demais; "Continue assim!" aparece para o melhor pilar se a nota for ≥ 85.
- Dado uma única avaliação concluída, então a evolução mostra "Sua evolução aparece a partir da segunda avaliação."; dada uma anterior da mesma pessoa na mesma empresa, então aparece o gráfico com as duas séries.
- Dado a identificação respondida, então o painel mostra as respostas da própria pessoa (texto digitado no "Outro:"; Matrícula só se respondida) e um avatar com iniciais.
- Dado outro colaborador, gestor ou outra empresa ativa, quando abre a URL, então recebe 404/403 e nenhum dado.
- Dado 390×844 e 1280×800, então não há rolagem horizontal, erro no console nem tween GSAP pendente; em impressão A4 paisagem o mapa cabe numa página sem cortar o coração.

INVARIANTES     Notas e faixas vêm do banco (nunca recalculadas na tela); só o dono vê o mapa; nada individual chega a gestor/admin; regressão do PR #21 (ponteiro durante a entrada) mantida; teclado, `aria-pressed`, Esc e "Ver resultado geral" mantidos; sem biblioteca nova (GSAP do app_shell); sem scroll horizontal em 390×844.

FORA DO ESCOPO  Texto de orientação de saúde (aguarda aprovação do cliente), painel "Sua mensagem" do modelo, foto do colaborador, mudança no relatório do gestor, deploy e merge.

RISCO           R2 (dados individuais de saúde e identificação; autorização do dono).

PERGUNTAS       Nenhuma bloqueante. Textos de orientação por pilar: o cliente preenche em `config/pillar_guidance.py`.
