# 05 — Landing page pública e tokens da marca

OBJETIVO        Trocar o placeholder de "/" por uma landing page responsiva com a nova logo (anel colorido), tokens do design system e animações GSAP como melhoria progressiva.

ATORES E FLUXO  Visitante abre "/", entende o produto (exercícios, aulas, avaliação em 9 pilares, prioridade, relatório agregado), entra pelo botão "Entrar" ou fala com a Quality Life por e-mail. Usuário já logado vê "Abrir o app".

ACEITE
- Dado um visitante, quando abre "/", então recebe 200 com `home.html`, links para login, privacidade e termos.
- Dado os pilares do banco, quando "/" renderiza, então os 9 nomes aparecem na ordem de `display_order`, sem lista fixa no template.
- Dado um usuário autenticado, quando abre "/", então o botão do cabeçalho é "Abrir o app" e aponta para `/app/`.
- Dado `QL_SALES_EMAIL` ausente, quando "/" renderiza, então não há erro e o contato usa o marcador "[EMAIL-COMERCIAL]".
- Dado 390×844 e 1280×800, quando a página carrega, então não há rolagem horizontal nem erro no console.
- Dado `prefers-reduced-motion: reduce` (ou sem JS), quando a página carrega, então o H1 e os 4 cards estão visíveis (opacity 1).
- Dado `collectstatic` com manifest e DEBUG=False, quando "/" é aberta, então responde 200.

INVARIANTES     Nenhum dado individual ou de empresa na página pública; scoring intocado; logo antiga do app intocada; sem Google Fonts nem CDN em tempo de execução; sem scroll horizontal em 390×844; nenhum segredo no repositório.

FORA DO ESCOPO  Troca da identidade no app logado (app_shell, login), PWA, formulário de contato, deploy.

RISCO           R1 (página pública nova, sem dados sensíveis).

PERGUNTAS       Nenhuma bloqueante. E-mail comercial real fica em `QL_SALES_EMAIL` (marcador até ser definido).
