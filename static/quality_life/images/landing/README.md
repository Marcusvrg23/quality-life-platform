# Imagens da landing page

Todas as imagens desta pasta foram geradas por IA para a Quality Life (Higgsfield), em outubro de 2026, e convertidas de PNG para WebP (qualidade 82, sem metadados). Os recortes `-pessoa` mantêm a transparência (WebP com alfa). Não retratam pessoas reais nem clientes.

## Cena em camadas (topo e chamada final)

As camadas de cada cena têm o mesmo tamanho e o mesmo enquadramento. O `-bg` ainda contém a pessoa, então as duas imagens se movem sempre juntas. A profundidade vem dos canvas de fitas e partículas entre elas.

| Arquivo | Tamanho | Função |
| --- | --- | --- |
| `hero-bg.webp` | 1344×752 | Topo, desktop: foto limpa (camada 1, fundo) |
| `hero-pessoa.webp` | 1344×752 | Topo, desktop: recorte da pessoa (camada 3, sobre o canvas de trás) |
| `hero-mobile-bg.webp` | 752×1344 | Topo, celular (< 600 px): foto limpa |
| `hero-mobile-pessoa.webp` | 752×1344 | Topo, celular (< 600 px): recorte da pessoa |
| `cta-bg.webp` | 1344×752 | Chamada final: foto limpa |
| `cta-pessoa.webp` | 1344×752 | Chamada final: recorte da pessoa |

## Versões estáticas

São usadas com `prefers-reduced-motion: reduce` ou sem JavaScript. Já trazem as fitas e as partículas na própria foto.

| Arquivo | Tamanho | Função |
| --- | --- | --- |
| `hero.webp` | 1344×752 | Topo, desktop |
| `hero-mobile.webp` | 752×1344 | Topo, celular |
| `cta.webp` | 1344×752 | Chamada final |

## Fotos dos cards

| Arquivo | Tamanho | Função |
| --- | --- | --- |
| `momento-comecar.webp` | 1168×880 | Card "Ao começar o dia" |
| `momento-durante.webp` | 1168×880 | Card "Durante o dia" |
| `momento-encerrar.webp` | 1168×880 | Card "Ao encerrar o dia" |
| `jornada.webp` | 1168×880 | Foto ao lado de "Um caminho simples" |
