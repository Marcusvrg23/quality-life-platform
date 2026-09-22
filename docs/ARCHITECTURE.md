# Arquitetura da Quality Life V2

## Decisão

A V2 será um monólito Django com PostgreSQL, templates Django e JavaScript modular/progressivo. O servidor concentra regras de negócio, autorização, persistência e renderização inicial; JavaScript melhora interações específicas sem duplicar o domínio no navegador.

## Por que não SPA separada + API nesta fase

O produto ainda precisa consolidar domínio, fluxos e controles de privacidade. Uma SPA e uma API separadas criariam dois ciclos de build/deploy, contrato de API prematuro, autenticação entre aplicações e duplicação de estado sem benefício comprovado para a M1. O monólito entrega uma superfície menor para proteger e testar e não impede extrair APIs quando houver consumidor real ou necessidade operacional demonstrada.

## Direção estrutural

```text
config/             # settings, URLs e ASGI/WSGI
accounts/           # identidade e perfis
organizations/      # empresas, vínculos e isolamento
assessments/        # questionários, respostas e scoring
recommendations/    # regras e recomendações
activities/         # biblioteca e execução de atividades
reporting/          # agregações, dashboard e relatórios
templates/          # templates Django
static/             # CSS, JavaScript modular e assets selecionados
tests/              # testes transversais e de integração
```

As fronteiras são direção inicial, não autorização para criar esses módulos na M0. Dependências devem apontar para serviços/regras de domínio claros, com PostgreSQL e backend como fontes de verdade.

## PROTOTYPE ≠ PRODUCTION CORE

O protótipo estático V8.1 permanece como baseline visual. HTML, JavaScript demo, autenticação client-side, mocks e cache atual não serão tratados como core de produção. Identidade, mascotes e outros assets aprovados serão migrados seletivamente, preservando aparência e procedência sem carregar decisões técnicas do protótipo.

## Inventário de assets da baseline

### Usados diretamente pela interface atual

- Logos: `quality-life-logo-dark-arc.png` e `quality-life-logo-dark-arc-small.png`.
- Mascotes: os três arquivos `mascot-ui/card-*.png` e os quatro `mascot-ui/step-*.png`.
- Aulas: três vídeos em `assets/videos/` e seus três posters em `assets/posters/`.

### Referenciados apenas pelo cache legado

- Quatro imagens em `assets/activity-frames/`.
- Quatro imagens em `assets/people-scenes/`.
- Seis imagens em `assets/ui-home/`.
- `icon.svg`.

Esses arquivos constam do precache de `sw.js`, mas não são renderizados pelo `index.html` ou pelo `app.js` atual. Devem ser tratados como legado/candidatos a uso, não apagados nesta milestone.

### Sem referência encontrada

- `assets/quality-life-logo-original.png`.

Nada será excluído. Logos e todo o conjunto `mascot-ui/` devem permanecer por identidade visual; a logo original também fica preservada como fonte de marca.

### Otimização futura

PNG/JPG fotográficos, cards, frames, cenas, mascotes e posters são candidatos a variantes WebP/AVIF após medição visual e de tamanho. Transparência, nitidez, cores da marca e fallbacks devem ser validados antes da troca. Vídeos exigem uma decisão separada de codecs/streaming e não fazem parte de WebP/AVIF.

## PWA e service worker

`sw.js` não será migrado nem modificado na M0. Antes de usar PWA nas páginas Django autenticadas, a estratégia de cache será redesenhada para que respostas privadas, personalizadas ou desatualizadas não sejam armazenadas ou servidas incorretamente. Nenhuma página autenticada deve entrar em precache por padrão.

## IA

Não há SDK ou dependência de IA na fundação. Uma integração futura, se aprovada, ficará atrás de uma interface opcional, com dados mínimos autorizados, auditoria e indisponibilidade tolerável pelo core.
