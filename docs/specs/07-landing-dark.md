# 07 — Landing "/" escura (neon/vidro), animada e com "Entrar" sempre visível

OBJETIVO        Refazer a página pública "/" no visual das referências escuras (`docs/design/landing-dark/`), com cena em camadas animada no topo e na chamada final, e o botão "Entrar" sempre visível, inclusive em 390×844.

ATORES E FLUXO  Visitante abre "/", entende o produto (exercícios, aulas em 3 momentos, avaliação em 9 pilares com mapa confidencial e prioridade, relatório agregado com 5+ pessoas, convites por link, consentimento LGPD) e entra por "Entrar" ou fala com a Quality Life por e-mail. Usuário logado vê "Abrir o app". No celular, os links de seção ficam num menu hambúrguer acessível; "Entrar" fica fora dele.

ACEITE
- Dado um visitante, quando abre "/", então recebe 200 com os textos da estrutura (hero, essência, momentos, pilares, como funciona, empresas, CTA, rodapé) e sem números ou depoimentos das referências ("50 mil", "10K", "95%", "96%", "4,8", "4.8").
- Dado 390×844 e 1280×800, quando a página carrega, então "Entrar" está visível e clicável sem abrir o menu, e não há rolagem horizontal nem erro no console.
- Dado 390×844, quando o visitante abre o hambúrguer, então `aria-expanded` vira "true", os links aparecem, Esc fecha e o foco volta ao botão.
- Dado os pilares ativos do banco, quando "/" renderiza, então os 9 aparecem por `display_order`, cada um com ícone, sem lista fixa no template.
- Dado movimento permitido, quando a página carrega, então os canvas do fundo e da cena do topo avançam quadros, a ordem das camadas é fundo < canvas trás < pessoa < canvas frente, e o GSAP fica ocioso (exceto tweens `loop` e `parallax`).
- Dado `prefers-reduced-motion: reduce` (ou sem JS), quando a página carrega, então nenhum loop roda, as camadas ficam ocultas e a foto estática `hero.webp` aparece.
- Dado as 13 imagens de `static/quality_life/images/landing/`, quando a página é servida, então todas existem e respondem 200; os recortes `-pessoa` têm alfa e o mesmo tamanho do `-bg`.

INVARIANTES     Nenhum dado individual ou de empresa na página pública; scoring intocado; logo oficial em anel (sem as logos das referências); sem CDN ou fonte remota em tempo de execução; sem scroll horizontal em 390×844; nenhum segredo no repositório; nenhuma biblioteca nova além do GSAP já vendorizado.

FORA DO ESCOPO  App logado, login, PWA, formulário de contato, newsletter, redes sociais, depoimentos, planos, cadastro aberto, vídeo, deploy e merge.

RISCO           R1 (página pública, sem dados sensíveis).

PERGUNTAS       Nenhuma bloqueante. E-mail comercial segue em `QL_SALES_EMAIL` (marcador "[EMAIL-COMERCIAL]" até ser definido).
