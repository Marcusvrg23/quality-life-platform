# Quality Life — base visual pública

`static/quality_life/brand.css` é a fonte de tokens. A landing carrega essa base;
a troca da identidade no app logado (`app_shell`) e no login é a próxima etapa.
A logo antiga continua intacta. As duas logos ring foram fornecidas por Marcus.

| Token `--ql-` | Valor / uso |
| --- | --- |
| purple | #84267D — títulos em destaque, ação principal |
| teal / lime / orange | #19B4A5 / #A8B108 / #FA8B16 — superfícies |
| magenta / lilac | #D3268E / #7E5BA3 — detalhes decorativos |
| ink / canvas / teal-text | #1B1A1F / #FBF8F4 / #0E7369 |
| font-heading | Quicksand 600/700 |
| font-body | Figtree 400/500/600/700 |
| radius-sm / md / lg / pill | 14 / 20 / 28 / 999 px |
| space-1 / 2 / 3 / 4 / 6 / 8 / 12 / 16 / 22 | 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 88 px |
| shadow-card | sombra suave em duas camadas; reservada à prévia do app |

Fontes WOFF2 locais em `fonts/`, com licenças OFL. Sem Google Fonts em runtime.
Use tinta sobre turquesa, limão e laranja; essas cores não são texto pequeno sobre
branco. Roxo aceita texto branco; use `teal-text` para texto turquesa sobre fundo
claro. Mantenha foco visível, títulos hierárquicos e alvos de toque de 44 px ou mais.

## Movimento e layout

- `data-anim="reveal"`: entrada única com 24 px de deslocamento e fade.
- `data-anim="stagger"`: a mesma entrada nos filhos, com intervalo de 0,08 s.
- `data-parallax="0.5"`: deslocamento proporcional ao scroll do hero, fator × 40,
  limitado a -40…40 `yPercent`. Reserve para decoração `aria-hidden` no hero;
  não coloque parallax no mesmo nó que recebe reveal.
- Só transform e opacity são animados. Estados iniciais vêm de `gsap.from()`
  dentro de `gsap.matchMedia`. Sem JS ou com movimento reduzido tudo fica visível.
  Alterar a preferência durante a sessão reverte os estilos e ScrollTriggers.
- Layout intrínseco: flex-wrap e grid auto-fit/minmax, sem breakpoints obrigatórios.
- Scripts GSAP/ScrollTrigger 3.13.0 e home.js são locais, defer, só nesta página.

## Referências e configuração

Inspiração conceitual, sem copiar identidade: [Oura](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/oura/DESIGN.md)
(fundo acolhedor, respiro, alternância claro/escuro) e
[Intercom](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/intercom/DESIGN.md)
(prévia de produto e hierarquia editorial), do awesome-design-md. A paleta,
fontes, logo e conteúdo seguem o briefing Quality Life.

`QL_SALES_EMAIL` define o contato comercial, separado de `LEGAL_DPO_EMAIL`.
O padrão `[EMAIL-COMERCIAL]` permite renderizar sem configuração, mas deve ser
substituído por um e-mail real antes de publicar. Os pilares vêm do banco,
ordenados por `display_order`; não são reproduzidos como lista fixa no template.
