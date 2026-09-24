# Quality Life V2 — deployment da demonstração

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
