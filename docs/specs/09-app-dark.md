# 09 — App logado e autenticação no visual escuro neon/vidro da "/"

OBJETIVO        O colaborador e o gestor veem o app (shell, páginas internas) e as telas de autenticação no mesmo visual escuro neon/vidro da landing "/", sem mudança de funcionalidade, rotas, textos, formulários ou permissões.

ATORES E FLUXO  Visitante entra pelo login (ou convite, ou redefinir senha) e cai no app: Hoje, Exercícios (lista, filtros, player), Aulas, Minha avaliação (hub, pergunta, revisão, mapa), Privacidade, Trocar senha; o gestor também vê Relatório da empresa e Equipe. Sem vínculo ativo → "Sem acesso"; com vários vínculos → "Escolher empresa". Privacidade e Termos públicos seguem o mesmo visual.

ACEITE
- Dado 390×844 e 1280×800, quando cada página listada abre, então não há rolagem horizontal, nem erro no console, e o fundo é escuro (luminância baixa) com tipografia Figtree (texto) e Cormorant Garamond (títulos).
- Dado qualquer página listada, quando a checagem automática mede o contraste dos textos principais (títulos, parágrafos, links, botões, rótulos, células e selos) contra o fundo efetivo, então todos atingem AA (4,5:1; 3:1 para texto grande).
- Dado foco por teclado, quando um link, botão ou campo recebe foco, então o contorno de foco é visível (outline com largura > 0 ou anel por box-shadow).
- Dado 390×844 no app, quando o usuário abre o hambúrguer, então `aria-expanded` vira "true", o menu em vidro aparece, Esc fecha e o foco volta ao botão.
- Dado movimento permitido, quando uma página do shell com fundo animado abre, então o canvas `#ql-ambient` (modo leve) avança quadros; com a aba oculta, para; páginas de leitura longa (questionário, mapa, relatório, documentos jurídicos) não têm canvas.
- Dado `prefers-reduced-motion: reduce`, quando qualquer página abre, então nenhum loop roda (canvas parado, nenhum tween GSAP pendente) e todos os cards estão visíveis (opacidade 1).
- Dado o mapa individual concluído, quando a página abre, então o conteúdo do resultado fica num cartão claro (fundo claro, texto escuro) dentro do app escuro, com o mesmo SVG e a mesma lógica.
- Dado o player de exercícios, quando o usuário avança, então "Exercício X de 8" atualiza, a imagem de fundo branco fica numa moldura clara arredondada, e a troca é suave (sem animação com movimento reduzido).

INVARIANTES     Rotas, nomes de campos, textos jurídicos e de regra, fluxo de autenticação e permissões inalterados; scoring e SVG do mapa intocados; nenhum dado novo exibido a gestor; sem CDN ou fonte remota; `identity.css` não é editado (sobrescrito em `app-dark.css`); regra `<style>` de imagens do `app_shell.html` preservada; sem scroll horizontal em 390×844; nenhuma biblioteca nova além do GSAP já vendorizado.

FORA DO ESCOPO  Refazer o mapa (Prompt 10), mudar textos, PWA, novas telas, deploy e merge.

RISCO           R0 visual (sem dados novos; templates só ganham classes, folhas e scripts).

PERGUNTAS       Nenhuma bloqueante.
