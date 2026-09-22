# Quality Life V2

## Visão do produto

A V2 transforma o protótipo visual em um produto multiempresa seguro para acompanhar qualidade de vida no trabalho. O core deve funcionar integralmente sem IA. A identidade visual e os assets aprovados da V8.1 são referência, não arquitetura de produção.

## Fluxo do colaborador

1. Entrar com identidade validada no servidor e no contexto da própria empresa.
2. Responder a avaliação dos nove pilares ou retomar uma avaliação ainda válida.
3. Receber score, coração dinâmico e recomendações explicáveis.
4. Consultar a biblioteca, iniciar atividades e registrar conclusões.
5. Acompanhar histórico e progresso.
6. Fazer reavaliação quando elegível e comparar períodos.

## Nove pilares

O modelo possui exatamente nove pilares de qualidade de vida. Cada pergunta pertence a um pilar e cada pilar produz um resultado próprio, além de contribuir para o resultado geral. Nomes, definições, perguntas, pesos e faixas precisam de aprovação formal de Produto antes da M3; até lá não devem ser inventados nem codificados implicitamente.

## Avaliação e scoring

- O questionário é versionado, tem ordem e opções definidas no backend e registra respostas completas com datas.
- O backend valida elegibilidade, completude e pertencimento à empresa.
- O score geral e os scores dos pilares ficam na faixa de 0 a 100.
- A fórmula, arredondamento, tratamento de respostas ausentes e faixas são determinísticos, versionados e cobertos por testes.
- A mesma versão e as mesmas respostas sempre produzem o mesmo resultado.
- IA não participa do cálculo e nunca pode criar, sobrescrever ou ajustar score.

## Coração dinâmico

O coração é a representação visual dos resultados dos nove pilares. Ele recebe somente resultados calculados pelo backend e deve manter alternativa textual acessível. A correspondência entre score, estado visual, cores e animações será versionada; o componente não calcula nem corrige resultados.

## Recomendações, biblioteca e atividades

- Recomendações são geradas por regras explícitas e rastreáveis a partir de resultados, perfil e conteúdo elegível.
- Cada recomendação explica o motivo e direciona para conteúdo ou atividade disponível.
- A biblioteca organiza exercícios aprovados por objetivo, pilar, duração, momento da jornada e restrições aplicáveis.
- Atividades possuem estado planejado, iniciado, concluído ou ignorado, com registro de data e origem.
- Conteúdo clínico ou contraindicações exigem validação profissional; recomendações não substituem atendimento de saúde.

## Histórico e reavaliação

O colaborador visualiza avaliações, scores, recomendações e atividades próprias ao longo do tempo. A reavaliação cria um novo registro imutável, preserva a versão anterior e só permite comparações semanticamente válidas entre versões.

## Área profissional

Perfis autorizados gerenciam, dentro da própria empresa e do seu escopo, participantes, questionários liberados, biblioteca, recomendações e acompanhamento profissional. A interface deve distinguir edição, publicação e auditoria. Dados sensíveis individuais não são expostos fora de uma finalidade e permissão legítimas.

## Dashboard corporativo

A diretoria recebe apenas indicadores agregados de adesão, participação, evolução e distribuição por pilar. Filtros e exportações obedecem isolamento por empresa e limiar mínimo de grupo, impedindo inferência ou exposição de respostas, diagnósticos ou scores individuais.

## Relatório executivo

O relatório apresenta período, população elegível, taxa de participação, indicadores agregados, tendências e limitações de leitura. Deve registrar versão e data de geração, aplicar as mesmas regras de privacidade do dashboard e nunca prometer causalidade que os dados não sustentem.

## Camada futura opcional de IA

O Quality Coach poderá, no futuro, explicar conteúdo ou personalizar linguagem sobre dados previamente autorizados. Será uma camada substituível e limitada: o produto continua funcional sem ela; IA não calcula score, não toma decisões de autorização, não acessa irrestritamente o banco e não é fonte de verdade.

## Fora da M0

Esta milestone não implementa autenticação, domínio, banco PostgreSQL, questionário, scoring, coração, recomendações, dashboards, IA, deploy ou migração do protótipo.
