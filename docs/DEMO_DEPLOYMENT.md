# Quality Life V2 — deployment da demonstração

> **Produção:** o guia oficial de produção agora é [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md). Este arquivo descreve apenas a demonstração isolada.

Use um Render Web Service e um PostgreSQL 16 **dedicado à demonstração**. O questionário publicado pelo seed é selecionado pelo fluxo M4 atual, que pressupõe uma única versão publicada no banco. Não conecte este serviço ao banco de outro projeto ou ambiente.

## Configuração do Web Service

- Runtime: Python 3.11 ou superior.
- Build: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Start: `python manage.py migrate --noinput && python manage.py seed_quality_life_demo && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Health check path: `/health/`

Configure as variáveis de ambiente no serviço, sem gravar valores no Git:

- `DJANGO_SETTINGS_MODULE=config.settings.production`
- `DJANGO_SECRET_KEY`: chave aleatória longa.
- `DJANGO_ALLOWED_HOSTS`: hostname exato do serviço Render, sem `https://`.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: origem HTTPS completa do serviço Render.
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`: credenciais do PostgreSQL dedicado.
- `POSTGRES_SSLMODE=require` (ou modo de verificação compatível com o certificado da instância).
- `QUALITY_LIFE_DEMO_SEED_ENABLED=true`.
- `QUALITY_LIFE_DEMO_PASSWORD`: senha forte compartilhada pelos três usuários demo, mantida só no ambiente.

Os logins são `demo1@example.com` para ensaio, `demo2@example.com` para apresentação e `demo3@example.com` para backup. O seed é idempotente, não reinicia avaliações e recusa mudanças de senha em contas existentes. Para substituir uma senha, faça uma operação administrativa explícita; não use o seed como reset.

O endpoint `/health/` confirma apenas a disponibilidade do processo. Após o primeiro start, confira também o login, a seleção da organização, o fluxo de avaliação até o resultado e um asset CSS em `/static/quality_life/`.

## Produção

Para publicar no Railway, siga [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md): lá o `migrate` e o carregamento do questionário rodam no Pre-deploy (`python manage.py release`), não no Start. Esta seção documenta o comportamento do carregador.

Em produção **não** rode `seed_quality_life_demo` e não defina `QUALITY_LIFE_DEMO_SEED_ENABLED` nem `QUALITY_LIFE_DEMO_PASSWORD`. O questionário oficial versionado no repositório é carregado com `load_official_questionnaire`:

- Start: `python manage.py migrate --noinput && python manage.py load_official_questionnaire --file assessments/questionnaires/quality_life_oficial_v1.json && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`

Antes de usar um arquivo em produção, confirme que a Quality Life aprovou formalmente perguntas e pontuação. O comando:

- valida o arquivo inteiro antes de gravar (os 9 pilares ativos, códigos slug de até 64 caracteres, `score_value` entre 0 e 100 com até 2 casas); qualquer erro aborta sem gravar nada;
- cria o questionário como rascunho e o publica na mesma transação, imprimindo o total de pilares, perguntas e opções;
- é idempotente: rodar de novo com o mesmo arquivo informa "já carregado" e não altera o banco;
- recusa um arquivo com o mesmo `code` e `version` de um questionário existente, mas com conteúdo diferente. Questionário publicado é imutável: para mudar perguntas ou pontuação, crie um novo arquivo com `version` maior;
- recusa carregar enquanto houver outro questionário `PUBLISHED`, porque o fluxo de avaliação exige exatamente um. Com `--retire-other-published`, os outros publicados passam para `RETIRED` na mesma transação; resultados já calculados são preservados.

Opções com `counts_for_score: false` (por exemplo, "Não sei" e "Prefiro não responder") aparecem para o colaborador, mas a resposta não entra no numerador nem no denominador da nota do pilar.
