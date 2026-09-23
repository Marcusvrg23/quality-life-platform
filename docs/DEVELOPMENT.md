# Desenvolvimento local da Quality Life V2

Esta fundação é um monólito Django com PostgreSQL. Ela ainda não contém domínio de negócio, autenticação do produto nem migração do protótipo V8.1.

## Pré-requisitos

- Python 3.11;
- PostgreSQL 16, diretamente ou por Docker Compose;
- Git.

## Preparação no PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "from secrets import token_urlsafe; print(token_urlsafe(50))"
```

Substitua em `.env` a chave exibida e a senha de banco indicada como placeholder. O arquivo `.env` é ignorado pelo Git; não versione credenciais reais.

## PostgreSQL local

Com Docker Compose instalado:

```powershell
docker compose up -d postgres
docker compose ps
```

Também é possível usar uma instância PostgreSQL 16 já instalada. Nesse caso, ajuste `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` e `POSTGRES_PASSWORD` em `.env`. Não há fallback para SQLite.

## Inicialização e verificação

```powershell
python manage.py migrate
python manage.py check --database default
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); cursor = connection.cursor(); cursor.execute('SELECT 1'); assert cursor.fetchone() == (1,); print(connection.vendor)"
python manage.py test --settings=config.settings.test
python manage.py runserver
```

O comando de conexão deve imprimir `postgresql`. O servidor Django não publica as telas do protótipo estático nesta milestone; a configuração de URLs permanece vazia até uma milestone funcional.

Para encerrar o PostgreSQL iniciado pelo Compose sem apagar o volume local:

```powershell
docker compose stop postgres
```

## Configurações por ambiente

- `config.settings.development`: padrão de `manage.py`; carrega `.env` local sem sobrescrever variáveis já exportadas.
- `config.settings.test`: usa PostgreSQL e um banco de testes separado; nunca usa SQLite.
- `config.settings.production`: não carrega `.env`, força `DEBUG=False` e cookies/redirect HTTPS seguros. Configuração e deploy reais serão tratados em milestone posterior.

ASGI e WSGI apontam para as configurações de produção por padrão. Todo secret e toda credencial devem ser fornecidos pelo ambiente de execução.

Os timeouts de conexão podem ser ajustados por `POSTGRES_CONNECT_TIMEOUT`; o padrão é cinco segundos para que falhas de configuração não fiquem bloqueadas indefinidamente.
