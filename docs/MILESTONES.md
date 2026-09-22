# Milestones da Quality Life V2

Cada milestone entrega um incremento pequeno, revisável e testável. O início de uma milestone depende da conclusão dos critérios da anterior.

## M0 Foundation

Escopo: preservar o protótipo recuperado como baseline Git e registrar as decisões de produto, arquitetura, segurança e desenvolvimento da V2, sem implementar funcionalidades.

Critérios verificáveis:

- existe um commit inicial que reproduz exatamente o protótipo recuperado;
- os hashes dos arquivos principais foram registrados e conferidos;
- `AGENTS.md` e os quatro documentos previstos em `docs/` existem e são coerentes entre si;
- `git diff --check` não apresenta erros e a documentação está em commit separado;
- nenhuma dependência, funcionalidade, migração de domínio ou deploy foi adicionado.

## M1 Django/PostgreSQL foundation

Escopo: criar o monólito Django, a configuração por ambiente e a conexão PostgreSQL, sem domínio de negócio.

Critérios verificáveis:

- o projeto Django inicia localmente com configuração de desenvolvimento documentada;
- PostgreSQL é usado pelo ambiente local e a checagem de conexão passa;
- configurações sensíveis vêm do ambiente e não estão versionadas;
- testes de smoke e checks do Django passam em ambiente limpo.

## M2 Identity/Organizations

Escopo: implementar autenticação server-side, organizações, vínculos de usuários e papéis mínimos.

Critérios verificáveis:

- login, logout e recuperação de acesso possuem testes;
- usuários autenticados acessam somente a própria organização;
- permissões de colaborador, profissional e administrador são validadas no servidor;
- tentativas de acesso cruzado entre tenants falham em testes automatizados.

## M3 Assessment Core

Escopo: modelar os 9 pilares, questionários, respostas e cálculo determinístico do score de 0 a 100.

Critérios verificáveis:

- versões de questionário e respostas são persistidas com integridade;
- casos de referência produzem scores esperados entre 0 e 100;
- o cálculo é reproduzível e não depende de IA;
- regras de negócio e isolamento por organização têm cobertura automatizada.

## M4 Assessment UI

Escopo: entregar o fluxo mobile-first para iniciar, responder, revisar e concluir uma avaliação.

Critérios verificáveis:

- uma avaliação completa pode ser realizada pela interface sem editar dados manualmente;
- validações e estados de erro são apresentados de forma acessível;
- progresso parcial não gera conclusão indevida;
- não existe scroll horizontal no viewport de 390x844 e o fluxo tem teste de ponta a ponta.

## M5 Dynamic Heart

Escopo: apresentar o coração dinâmico a partir dos resultados determinísticos dos 9 pilares, preservando a identidade visual aprovada.

Critérios verificáveis:

- cada caso de referência gera a representação visual esperada;
- a visualização deriva somente dos scores persistidos;
- há alternativa textual acessível para as informações visuais;
- a tela funciona em 390x844 sem scroll horizontal.

## M6 Recommendations

Escopo: gerar recomendações determinísticas por regras e disponibilizar a biblioteca curada de exercícios.

Critérios verificáveis:

- regras versionadas relacionam resultados a recomendações reproduzíveis;
- recomendações respeitam tenant, perfil e permissões;
- a biblioteca pode ser consultada e filtrada pela interface;
- testes confirmam que IA não altera seleção, prioridade ou score.

## M7 Activities

Escopo: permitir ao colaborador planejar, registrar e concluir atividades recomendadas.

Critérios verificáveis:

- atividades podem ser criadas, atualizadas e concluídas nos estados permitidos;
- cada alteração pertence ao usuário e à organização corretos;
- transições inválidas e acessos cruzados são rejeitados;
- a interface principal funciona em 390x844 sem scroll horizontal.

## M8 Progress/Reassessment

Escopo: exibir histórico individual, evolução e iniciar reavaliações sem sobrescrever avaliações anteriores.

Critérios verificáveis:

- avaliações concluídas permanecem imutáveis e ordenadas no histórico;
- comparações usam versões e períodos identificáveis;
- uma reavaliação cria um novo registro independente;
- testes cobrem evolução, ausência de histórico e isolamento de dados.

## M9 Professional Area

Escopo: oferecer ao profissional uma área restrita para acompanhar e apoiar colaboradores autorizados.

Critérios verificáveis:

- o profissional vê somente organizações e colaboradores explicitamente vinculados;
- ações permitidas e proibidas são validadas no servidor;
- acessos e ações sensíveis geram trilha de auditoria;
- testes impedem enumeração e acesso direto a registros não autorizados.

## M10 Corporate Dashboard

Escopo: apresentar indicadores agregados da organização sem expor respostas ou resultados individuais à diretoria.

Critérios verificáveis:

- o dashboard aplica o limiar mínimo de agregação definido para privacidade;
- filtros não permitem inferir dados de grupos abaixo do limiar;
- métricas são reconciliadas com casos de referência conhecidos;
- isolamento entre organizações e permissões executivas têm testes automatizados.

## M11 Executive Report

Escopo: gerar um relatório executivo reproduzível a partir dos mesmos dados agregados do dashboard.

Critérios verificáveis:

- relatório e dashboard apresentam métricas consistentes para o mesmo período;
- exportações respeitam tenant, permissões e limiar mínimo de agregação;
- período, data de geração e critérios usados constam no relatório;
- não há identificação direta nem possibilidade razoável de inferência individual nos casos testados.

## M12 Hardening/Release

Escopo: preparar a primeira release com revisão de segurança, desempenho, acessibilidade, observabilidade, backup e estratégia PWA.

Critérios verificáveis:

- suíte automatizada, checks de segurança e critérios de acessibilidade definidos passam;
- restauração de backup e resposta a falhas críticas são exercitadas;
- logs e alertas não expõem secrets ou dados sensíveis;
- cache, logout, invalidação e uso compartilhado do service worker são aprovados antes de qualquer PWA autenticada;
- checklist de release é aprovado sem realizar deploy não solicitado.

## M13 Optional Quality Coach

Escopo: avaliar e, somente se aprovado, integrar um Quality Coach de IA como camada opcional e limitada.

Critérios verificáveis:

- o produto continua funcional com a integração desativada ou indisponível;
- a IA não altera score, regras determinísticas ou decisões de autorização;
- o acesso ocorre por operações autorizadas, sem credencial nem acesso irrestrito ao banco;
- escopo de tenant, minimização, consentimento, retenção e auditoria são validados;
- testes cobrem indisponibilidade do provedor, respostas inseguras e ausência de vazamento entre tenants.
