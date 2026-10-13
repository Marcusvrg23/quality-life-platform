# Design system

A base do design system está em `static/quality_life/brand.css`: tokens em `:root` e as fontes hospedadas no próprio projeto. Hoje só a landing page pública (`templates/home.html`, `static/quality_life/home.css`) usa esses tokens.

## Tokens

| Grupo | Tokens |
|---|---|
| Marca | `--ql-purple` #84267D, `--ql-turquoise` #19B4A5, `--ql-lime` #A8B108, `--ql-orange` #FA8B16, `--ql-magenta` #D3268E, `--ql-lilac` #7E5BA3 |
| Texto e fundo | `--ql-ink` #1B1A1F, `--ql-ink-soft`, `--ql-turquoise-text` #0E7369, `--ql-on-purple` #FFF, `--ql-bg` #FBF8F4, `--ql-surface`, `--ql-line` |
| Fontes | `--ql-font-display` Quicksand 600/700 (títulos do app), `--ql-font-serif` Cormorant Garamond 500/600 (títulos da landing), `--ql-font-body` Figtree 400/500/600/700 (texto) |
| Raios | `--ql-radius-sm` 14px, `--ql-radius-md` 20px, `--ql-radius-lg` 28px, `--ql-radius-pill` 999px |
| Espaços | `--ql-space-1` a `--ql-space-9`: 4, 8, 12, 16, 24, 32, 48, 64, 88px |
| Sombra | `--ql-shadow-card` |

As fontes ficam em `static/quality_life/fonts/` (woff2, subconjunto latino, licença SIL OFL 1.1 em `OFL-*.txt`). Não use Google Fonts nem CDN em tempo de execução.

## Contraste

- Turquesa, limão e laranja **não** servem para texto pequeno sobre branco. Use-os como fundo, com texto `--ql-ink`.
- Texto turquesa sobre branco: use `--ql-turquoise-text` (#0E7369).
- Roxo, magenta e lilás aceitam texto branco.
- No bloco escuro (`--ql-ink`), use texto branco e botões turquesa com texto `--ql-ink`.
- Na landing escura (fundo #061419 → #0A222B), o texto secundário é #B8C9CE e o turquesa de texto é #4FD8CA (ambos acima de 4,5:1). Lilás (#7E5BA3) só em texto grande ou decoração; para texto use #B89CF0.

## Animação da landing (GSAP 3.13 + ScrollTrigger + canvas)

Referência visual: `docs/design/landing-dark/`; spec: `docs/specs/07-landing-dark.md`. Tudo é melhoria progressiva: sem JS ou com `prefers-reduced-motion: reduce`, nada é animado, as cenas em camadas ficam ocultas e aparecem as fotos estáticas (`hero.webp`, `hero-mobile.webp`, `cta.webp`). Anime só `transform`, `opacity` e filtros leves.

- `static/quality_life/ambient.js`: um único `requestAnimationFrame` desenha o fundo fixo da página (`#ql-ambient`: aurora, fitas nas bordas das seções, partículas, rastro do cursor) e os canvas das cenas. Para com a aba oculta e, nas cenas, fora da tela. Se a média de 30 quadros passar de 24 ms, reduz partículas, desliga o rastro e põe `.ql-lite` no `<html>` (sem `backdrop-filter`).
- Cena em camadas (`.ql-scene`): `-bg` < canvas trás < `-pessoa` < canvas frente, com o mesmo enquadramento. Só o wrapper `.ql-scene__rig` é animado, para a foto e o recorte nunca se separarem; os canvas têm parallax próprio.
- `data-hero`: entra em sequência no topo. `data-reveal`: sobe e aparece ao entrar na tela. `data-reveal-group`: os filhos entram em sequência, com leve rotação e escala. `data-float`: ícone flutuando em loop.
- Tweens sem fim usam `data: "loop"` e pausam fora da tela; tweens de rolagem usam `data: "parallax"` (`scrub: 1`). Os testes de navegador ignoram esses dois tipos ao esperar o GSAP ficar ocioso.

Os scripts entram com `defer` e só nas páginas que os usam.

## Próxima etapa

Trocar a identidade no app logado (`templates/app_shell.html`, login) para estes tokens e para a logo nova (`images/brand/quality-life-logo-ring-*.png`). A logo antiga (`images/quality-life-logo.png`) continua no app até lá.
