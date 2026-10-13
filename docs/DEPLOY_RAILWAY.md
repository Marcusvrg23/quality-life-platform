# Quality Life — publicar em produção no Railway

> Outra opção de hospedagem: [DEPLOY_SQUARE_CLOUD.md](DEPLOY_SQUARE_CLOUD.md) (Square Cloud + Neon).

Guia passo a passo para quem não é programador. Siga na ordem. Nenhuma senha ou chave deve ser escrita neste repositório: tudo vai nas **Variables** do Railway.

## 1. O que você vai criar no Railway

1. Um projeto novo.
2. Um banco **PostgreSQL** dentro do projeto (botão *New* → *Database* → *PostgreSQL*). Deixe o nome do serviço como `Postgres`; as variáveis abaixo usam esse nome.
3. Um serviço a partir do repositório do GitHub (*New* → *GitHub Repo*), apontando para o branch `main`.

O Railway lê o arquivo `.python-version` do repositório e usa Python 3.11, a mesma versão dos testes automáticos.

## 2. Comandos do serviço (aba *Settings*)

Copie exatamente:

| Campo no Railway | Valor |
|---|---|
| Build Command | `python manage.py collectstatic --noinput` |
| Pre-deploy Command | `python manage.py release` |
| Start Command | `gunicorn config.wsgi:application --workers 2 --timeout 60` |
| Healthcheck Path | `/health/` |

O que cada um faz:

- **Build**: junta CSS, imagens e vídeos para o servidor entregar.
- **Pre-deploy**: roda antes de cada versão entrar no ar. Atualiza o banco (`migrate`), publica o questionário oficial **v2** (`quality_life_oficial_v2.json`), aposenta o v1 e cria o primeiro administrador. Pode rodar quantas vezes for preciso: o que já existe não é alterado. Se der erro, a versão nova não entra no ar e a anterior continua funcionando.
- **Start**: liga o site. A porta vem sozinha da variável `PORT` do Railway.
- **Não** adicione `--access-logfile` ao Start: os links de convite e de redefinição de senha têm um código secreto na URL, e esse log gravaria o código.
- **Nunca** rode `seed_quality_life_demo` em produção; ele cria usuários de demonstração.

## 3. Variáveis (aba *Variables* do serviço do site)

Copie os nomes exatamente. O que está entre `${{ }}` é preenchido pelo próprio Railway.

```
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<gerada por você, veja abaixo>
DJANGO_ALLOWED_HOSTS=${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}
POSTGRES_DB=${{Postgres.PGDATABASE}}
POSTGRES_USER=${{Postgres.PGUSER}}
POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}
POSTGRES_HOST=${{Postgres.PGHOST}}
POSTGRES_PORT=${{Postgres.PGPORT}}
POSTGRES_SSLMODE=require
DJANGO_SUPERUSER_EMAIL=<e-mail do primeiro administrador>
DJANGO_SUPERUSER_PASSWORD=<senha forte do primeiro administrador>
LEGAL_COMPANY_NAME=<razão social fornecida pelo cliente>
LEGAL_CNPJ=<CNPJ fornecido pelo cliente>
LEGAL_DPO_EMAIL=<e-mail do encarregado de dados fornecido pelo cliente>
```

Como gerar a `DJANGO_SECRET_KEY` (no seu computador, com Python instalado):

```
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Cole o resultado na variável. Não reutilize a chave de outro ambiente e não envie por e-mail ou chat.

Sobre o administrador:

- A senha precisa ser forte (o comando recusa senha curta, comum, só de números ou parecida com o e-mail).
- O comando só cria o usuário se o e-mail ainda não existir. Ele nunca troca a senha de quem já existe.
- **Depois do primeiro login em `/admin/`, apague a variável `DJANGO_SUPERUSER_PASSWORD`.**

Sem `LEGAL_COMPANY_NAME`, `LEGAL_CNPJ` e `LEGAL_DPO_EMAIL`, as páginas de privacidade e termos mostram `[RAZÃO SOCIAL]`, `[CNPJ]` e `[E-MAIL DO ENCARREGADO]`.

## 4. Avisos importantes

- **Domínio próprio** (ex.: `app.empresa.com.br`): acrescente o domínio em `DJANGO_ALLOWED_HOSTS` (separado por vírgula, sem `https://`) e em `DJANGO_CSRF_TRUSTED_ORIGINS` (com `https://`). Sem isso, o site responde "Bad Request (400)" ou recusa formulários.
- **Questionário v2 (atual)**: o `release` publica `quality_life_oficial_v2.json`, gerado a partir do texto oficial `docs/questionario/questionario-oficial-quality-life.md` por `scripts/build_questionnaire_v2.py`. Ele roda com `--retire-other-published`: o v1 (e qualquer outro questionário publicado, inclusive o de demonstração) passa para `RETIRED` na mesma transação. **Avaliações já concluídas no v1 são preservadas**, com notas e mapa intactos, e uma avaliação do v1 em andamento ainda pode ser concluída. Novas avaliações usam o v2.
- **Pontuação**: o v2 mantém a pontuação **PROPOSTA** do v1 sem nenhuma mudança; as perguntas novas do texto oficial (identificação, múltipla escolha, textos e as demais) não entram na nota. Um questionário publicado não pode ser editado. Por isso, a aprovação formal do cliente sobre perguntas e pontuação deve vir **antes** de colaboradores reais responderem. Mudanças depois disso exigem uma nova versão (`version` maior no JSON).
- **Identificação (seção 1) e respostas abertas**: nome, matrícula, cargo, setor, textos livres e múltipla escolha só aparecem para o próprio colaborador. O relatório do gestor continua mostrando apenas médias de pilares de grupos com 5 pessoas ou mais.

## 5. Checklist depois do deploy

Marque cada item:

- [ ] `https://<domínio>/health/` mostra `{"status": "ok"}`.
- [ ] Login em `https://<domínio>/admin/` com o administrador criado.
- [ ] No admin, criar a **Organization** do cliente e a **Membership** do gestor (papel gestor).
- [ ] Gerar o link de definição de senha do gestor e entregar a ele.
- [ ] Gestor envia um **convite** para um colaborador de teste.
- [ ] Colaborador de teste aceita o **consentimento** e conclui **uma avaliação completa**.
- [ ] Colaborador revoga o consentimento em `/app/privacidade/`.
- [ ] Gestor abre o **relatório**.
- [ ] `/privacidade/` e `/termos/` mostram razão social, CNPJ e e-mail do encarregado corretos.
- [ ] Um vídeo de `/app/aulas/` toca no **iPhone** (Safari).
- [ ] No terminal, este comando responde `206`:

  ```
  curl -I -H "Range: bytes=0-1" https://<domínio>/static/quality_life/videos/inicio-trabalho.mp4
  ```

## 6. Quando algo dá errado

- **Deploy parado no pre-deploy**: abra os logs do deploy; a mensagem do erro aparece ali (ex.: senha do administrador recusada, questionário v2 já existente com conteúdo diferente do arquivo).
- **Erro 500 no site**: os logs do serviço mostram o traceback completo do erro.
- **Health check falhando**: confirme que `healthcheck.railway.app` está em `DJANGO_ALLOWED_HOSTS`.
