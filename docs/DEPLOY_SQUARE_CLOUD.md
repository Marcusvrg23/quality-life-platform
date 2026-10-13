# Quality Life — Square Cloud

## Estado
Preparação de deploy apenas: o servidor ainda não foi publicado. Este projeto usa Django, PostgreSQL e WhiteNoise. A raiz também contém uma PWA de demonstração antiga: publique o backend com `squarecloud.app`, não apenas o HTML.

## Deploy
1. Faça checkout desta branch, ou faça merge após revisar e executar o CI.
2. Contrate/ative a Square Cloud e crie um PostgreSQL exclusivo para a Quality Life com TLS e backups.
3. No painel Square Cloud, configure as variáveis privadas abaixo, sem salvá-las no repositório.
4. Use o painel ou o CLI oficial: `npm install -g @squarecloud/cli@latest`, `squarecloud auth login`, `squarecloud upload`.
5. Valide `https://quality-life-mvrg23.squareweb.app/health/`, `/login/`, arquivos estáticos e a conexão ao banco. O endereço só existirá depois de o deploy ser concluído e o subdomínio aprovado.

## Variáveis no painel
- `DJANGO_SETTINGS_MODULE=config.settings.production`
- `DJANGO_SECRET_KEY`: gerar localmente com `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=quality-life-mvrg23.squareweb.app`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://quality-life-mvrg23.squareweb.app`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=require`, `POSTGRES_CONNECT_TIMEOUT=5`, `POSTGRES_CONN_MAX_AGE=0`
- `LEGAL_COMPANY_NAME`, `LEGAL_CNPJ`, `LEGAL_DPO_EMAIL`

## Segurança e dados
O START executa collectstatic, migrate e Gunicorn na porta 80. Não executa automaticamente `release` ou `seed_quality_life_demo`. Só carregue o questionário oficial e crie o administrador depois de ter aprovação da pontuação: `python manage.py release --settings=config.settings.production` com `DJANGO_SUPERUSER_EMAIL` e `DJANGO_SUPERUSER_PASSWORD` privados. Remova a senha da variável depois. Nunca insira dados de saúde reais sem revisar LGPD, consentimento, isolamento, backup e mídia privada. Um /health/ HTTP 200 não testa o PostgreSQL.

Leia também docs/DEPLOY_RAILWAY.md para entender o comando release. Guia Square: https://docs.squarecloud.app/en/tutorials/api/django
