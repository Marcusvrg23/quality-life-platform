# 16 — Conheça a Quality

OBJETIVO
Quem usa a plataforma conhece a Quality Life pelo próprio app: uma página com
todo o conteúdo da apresentação empresarial, o logo em 3D e animações de
rolagem, aberta pelo item "Conheça a Quality" do menu lateral.

ATORES E FLUXO
Qualquer pessoa logada (colaborador, gestor, admin, operador sem empresa):
menu lateral → "✦ Conheça a Quality" → `/app/conheca-a-quality/` → lê,
gira o logo, copia o e-mail de contato ou abre www.qualitylife.online.

ACEITE
1. Dado um usuário anônimo, quando abre `/app/conheca-a-quality/`, então vai
   para o login (302).
2. Dado colaborador, gestor ou operador sem empresa, quando abre a página,
   então recebe 200 e o menu mostra "Conheça a Quality" com `aria-current`;
   nas outras telas o item aparece sem `aria-current`.
3. Dada uma empresa forjada na sessão, então 403.
4. A página traz o conteúdo da apresentação: título, Educação Física, as
   quatro soluções, os 10 serviços, as 5 etapas, os 5 benefícios, o e-mail de
   contato e www.qualitylife.online. Nada escrito "prévia", "IA",
   "inteligência artificial", "aguardando", "MINUTA", "Exemplo de" ou
   "em definição".
5. O e-mail é `QL_SALES_EMAIL` quando definido; sem ele, o e-mail da
   apresentação (ceo.qualitylife.online@gmail.com), nunca o marcador
   "[EMAIL-COMERCIAL]".
6. Em 390×844 e 1280×800: sem scroll horizontal e sem erro de console; com
   WebGL o logo vira 3D (`data-state="3d"`), sem WebGL fica a imagem; com
   `prefers-reduced-motion: reduce` todo o texto aparece sem animação.

INVARIANTES
Página só de conteúdo: não lê nem grava dado de pessoa ou empresa. Login e
`resolve_tenant_context` no servidor. Bibliotecas servidas pelo próprio app
(`static/quality_life/vendor/`), sem CDN. Scoring e `CONSENT_VERSION`
intocados; sem migração.

DECISÕES
- "Entrega da proposta" e "Propostas personalizadas" são o texto comercial da
  apresentação e ficam; a regra de "proposta" do spec 15 vale para notas
  internas nas telas de prática, não para esta página.
- three.js r128 (MIT) só nesta página; GSAP 3.13 e ScrollTrigger já estavam no
  projeto. Fotos de banco de imagens da apresentação não foram usadas.

FORA DO ESCOPO
Página pública fora do login; edição do conteúdo pelo painel.

RISCO
R1 (tela nova, sem dado sensível).
