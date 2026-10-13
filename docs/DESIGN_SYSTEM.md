# Design system

A base do design system está em `static/quality_life/brand.css`: tokens em `:root` e as fontes hospedadas no próprio projeto. Hoje só a landing page pública (`templates/home.html`, `static/quality_life/home.css`) usa esses tokens.

## Tokens

| Grupo | Tokens |
|---|---|
| Marca | `--ql-purple` #84267D, `--ql-turquoise` #19B4A5, `--ql-lime` #A8B108, `--ql-orange` #FA8B16, `--ql-magenta` #D3268E, `--ql-lilac` #7E5BA3 |
| Texto e fundo | `--ql-ink` #1B1A1F, `--ql-ink-soft`, `--ql-turquoise-text` #0E7369, `--ql-on-purple` #FFF, `--ql-bg` #FBF8F4, `--ql-surface`, `--ql-line` |
| Fontes | `--ql-font-display` Quicksand 600/700 (títulos), `--ql-font-body` Figtree 400/500/600/700 (texto) |
| Raios | `--ql-radius-sm` 14px, `--ql-radius-md` 20px, `--ql-radius-lg` 28px, `--ql-radius-pill` 999px |
| Espaços | `--ql-space-1` a `--ql-space-9`: 4, 8, 12, 16, 24, 32, 48, 64, 88px |
| Sombra | `--ql-shadow-card` |

As fontes ficam em `static/quality_life/fonts/` (woff2, subconjunto latino, licença SIL OFL 1.1 em `OFL-*.txt`). Não use Google Fonts nem CDN em tempo de execução.

## Contraste

- Turquesa, limão e laranja **não** servem para texto pequeno sobre branco. Use-os como fundo, com texto `--ql-ink`.
- Texto turquesa sobre branco: use `--ql-turquoise-text` (#0E7369).
- Roxo, magenta e lilás aceitam texto branco.
- No bloco escuro (`--ql-ink`), use texto branco e botões turquesa com texto `--ql-ink`.

## Animação (GSAP 3.13 + ScrollTrigger)

`static/quality_life/home.js` é melhoria progressiva: sem JS ou com `prefers-reduced-motion: reduce`, nada é animado e todo o conteúdo aparece. O CSS nunca esconde conteúdo; os estados iniciais vêm de `gsap.from()` dentro de `gsap.matchMedia("(prefers-reduced-motion: no-preference)")`. Anime só `transform` e `opacity`.

- `data-anim="reveal"`: o elemento sobe e aparece ao entrar na tela (uma vez).
- `data-anim="stagger"`: os filhos diretos aparecem em sequência (0,08s entre eles, uma vez).
- `data-parallax="<fator>"`: o elemento se move com a rolagem da seção (`yPercent = fator × 100`, limitado entre -40 e 40). Use fatores pequenos (0,1 a 0,4) e só em elementos decorativos `aria-hidden`.

Os scripts entram com `defer` e só nas páginas que os usam.

## Próxima etapa

Trocar a identidade no app logado (`templates/app_shell.html`, login) para estes tokens e para a logo nova (`images/brand/quality-life-logo-ring-*.png`). A logo antiga (`images/quality-life-logo.png`) continua no app até lá.
