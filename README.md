# Quality Life PWA v2

Protótipo mobile-first da plataforma Quality Life, reorganizado para uma experiência de ginástica laboral diária.

## Fluxo do cliente
Hoje → check-in → atividade do dia → prática guiada → conclusão → progresso.

## Fluxo profissional
Visão geral → clientes → anamneses → programas → biblioteca → relatórios.

## Credenciais de demonstração
Cliente:
- cliente@qualitylife.com
- demo123

Profissional:
- profissional@qualitylife.com
- admin123

## Deploy Netlify
1. Extraia o ZIP.
2. No Netlify, use **Add new site > Deploy manually**.
3. Arraste a pasta `quality-life-pwa-v2`.

A aplicação é uma PWA estática e pode ser instalada na tela inicial em navegadores compatíveis.

## Atenção
Esta é uma versão de demonstração front-end. O login e os dados são simulados no navegador.

NÃO use esta versão para armazenar anamneses reais, dados de saúde, senhas reais ou informações pessoais sensíveis.

Para produção, implemente:
- backend e API;
- PostgreSQL;
- autenticação real;
- hash de senha;
- controle de acesso por perfil e empresa;
- recuperação de senha;
- logs de auditoria;
- consentimento e políticas LGPD;
- armazenamento privado de arquivos;
- isolamento de dados entre empresas;
- backups e retenção de dados;
- HTTPS e configuração de segurança.


## V2.1 — correção de login

- autenticação demo revisada;
- senha recebe `trim()` para evitar espaço acidental no iPhone;
- sessão usa `sessionStorage` quando "Lembrar de mim" está desmarcado;
- botões "Entrar como cliente" e "Entrar como profissional";
- service worker atualizado para reduzir cache antigo no Safari/iOS;
- cache-busting em CSS e JavaScript.


## V3 — ajustes visuais
- tela de login atualizada com a logo original da Quality Life;
- ícone superior do login substituído pela marca original;
- início da área do cliente ajustado com exemplos visuais baseados nos bonequinhos da logo (início do trabalho, durante o trabalho, final do trabalho e ergonomia).


## V4 — logo com estilo semelhante à referência enviada
- logo principal trocada para uma versão com arco superior e inferior escuros, com visual mais próximo da referência;
- logo aplicada na tela de login;
- logo aplicada no menu lateral da plataforma;
- manifesto PWA ajustado para usar a nova identidade visual.


## V6 — sequência de imagens ao apertar play
- o mockup abstrato foi substituído por imagens reais da mulher em alongamento;
- o card principal "Atividade de hoje" agora usa uma foto real;
- dentro do player da atividade, ao tocar no botão play, a plataforma percorre automaticamente 4 imagens diferentes;
- os botões "Anterior" e "Próximo exercício" continuam funcionando manualmente.


## V6.1 — imagens reais no lugar dos mockups
- os mockups visuais restantes foram substituídos por imagens reais geradas;
- a home mantém o mesmo formato anterior, mas agora com imagens de pessoas reais em contexto corporativo;
- a atividade principal e a sequência do player também usam essas imagens.


## V6.1.1 — hero corrigido
- imagem principal de “Atividade de hoje” substituída por uma mulher alongando;
- versão atualizada para quebrar cache no deploy.


## V6.1.2 — imagem de pescoço
- a imagem masculina de alongamento do ombro foi substituída pela imagem de alongamento do pescoço no site;
- versão atualizada para quebrar cache no deploy.


## V7 — design atualizado com base no mockup aprovado
- a home do cliente foi substituída por uma versão visual baseada no mockup gerado e aprovado;
- o hero, os 3 cards recomendados e o banner foram recortados do mockup e aplicados no site;
- o botão de iniciar atividade continua abrindo a sequência de exercícios.


## V8 — mascotes + vídeos
- home do cliente adaptada para os três cards com mascotes proporcionais;
- Mobilidade abre o passo 1; Respiração abre a etapa de respiração; Alongamento abre a etapa de alongamento;
- as quatro etapas do player agora usam apenas mascotes, sem fotos de pessoas;
- os três vídeos mais recentes enviados foram mantidos na seção Aulas, organizados em Início do trabalho, Durante o trabalho e Final do trabalho;
- posters dos vídeos foram regenerados a partir dos novos arquivos.
