# Quality Life — publicar em produção na Square Cloud + Neon

Guia passo a passo para quem não é programador. Siga na ordem. O site roda na **Square Cloud** e o banco de dados fica no **Neon** (PostgreSQL grátis). Nenhuma senha ou chave deve ser escrita neste repositório: tudo vai nas **variáveis de ambiente** da Square Cloud.

> Outra opção de hospedagem: [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md).

## 1. Banco de dados no Neon

1. Crie uma conta grátis em [neon.tech](https://neon.tech).
2. Crie um projeto com **Postgres 16** na região **AWS US East (N. Virginia)**. É a região mais próxima do datacenter da Square Cloud (Nova York), o que deixa o site mais rápido.
3. Clique em **Connect**:
   - **Desligue** a opção **Connection pooling**.
   - Confira que o endereço (host) **não** tem `-pooler` no nome. Exemplo certo: `ep-nome-123456.us-east-1.aws.neon.tech`.
4. Anote os dados mostrados: host, nome do banco, usuário e senha. Eles vão nas variáveis do passo 3.

## 2. Site na Square Cloud

1. Contrate o plano **Hobby** (R$ 12,49/mês, aceita PIX).
2. Envie o projeto de um destes jeitos:
   - **Pelo painel**: faça upload do projeto em ZIP.
   - **Pela linha de comando** (precisa do Node.js instalado), dentro da pasta do projeto:

     ```
     npm install -g @squarecloud/cli
     squarecloud auth login
     squarecloud upload
     ```

3. **Opcional**: ligue o **GitHub App** da Square Cloud no branch `main`. Assim, cada mudança aprovada no `main` publica sozinha.

A Square Cloud lê o arquivo `squarecloud.app` da raiz do projeto. Ele já está pronto: usa Python 3.14, 512 MB de memória, o endereço `quality-life-mvrg23.squareweb.app` e reinicia o site sozinho se ele cair. O arquivo `squarecloud.ignore` impede que arquivos locais (como o `.env`) sejam enviados.

O comando de início (`START`) faz, em ordem, a cada vez que o site liga:

1. `collectstatic`: junta CSS, imagens e vídeos para o servidor entregar.
2. `release`: atualiza o banco (`migrate`), carrega o questionário oficial e cria o primeiro administrador. Pode rodar quantas vezes for preciso: o que já existe não é alterado. Se der erro, o site não liga e a mensagem aparece nos logs.
3. `gunicorn`: liga o site na porta 80, como a Square Cloud exige.

- **Não** adicione `--access-logfile` ao `START`: os links de convite e de redefinição de senha têm um código secreto na URL, e esse log gravaria o código.
- **Nunca** rode `seed_quality_life_demo` em produção; ele cria usuários de demonstração.

## 3. Variáveis de ambiente

Coloque as variáveis pelo painel da Square Cloud **ou** por um arquivo `.env` no seu computador, com o comando:

```
squarecloud app env set --from-file .env --app <appID>
```

Depois, **reinicie o app** para ele ler os valores novos. O arquivo `.env` **nunca** vai para o Git.

Copie os nomes exatamente:

```
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<gerada por você, veja abaixo>
DJANGO_ALLOWED_HOSTS=quality-life-mvrg23.squareweb.app,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://quality-life-mvrg23.squareweb.app
POSTGRES_HOST=<host do Neon, sem -pooler>
POSTGRES_PORT=5432
POSTGRES_DB=<nome do banco no Neon>
POSTGRES_USER=<usuário do Neon>
POSTGRES_PASSWORD=<senha do Neon>
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
- **Depois do primeiro login em `/admin/`, apague a variável `DJANGO_SUPERUSER_PASSWORD`** e reinicie o app.

Sem `LEGAL_COMPANY_NAME`, `LEGAL_CNPJ` e `LEGAL_DPO_EMAIL`, as páginas de privacidade e termos mostram `[RAZÃO SOCIAL]`, `[CNPJ]` e `[E-MAIL DO ENCARREGADO]`.

### Se o navegador mostrar "redirecionamento em excesso"

O site manda todo acesso por `http://` para `https://`. Para isso, ele precisa que a Square Cloud avise que a visita já chegou por HTTPS, e a documentação dela não garante esse aviso. Sem ele, o site fica redirecionando para si mesmo sem parar.

Se isso acontecer, adicione a variável abaixo e reinicie o app:

```
DJANGO_SECURE_SSL_REDIRECT=false
```

O acesso **continua em HTTPS**: quem cuida do cadeado é o proxy da Square Cloud, na frente do site. A variável só desliga o redirecionamento feito pelo próprio Django.

## 4. Avisos importantes

- **Dados nos EUA (LGPD)**: o site (Square Cloud, Nova York) e o banco (Neon, N. Virginia) ficam nos **Estados Unidos**. Isso é transferência internacional de **dados de saúde**, que são dados sensíveis. Esse ponto precisa entrar na **revisão jurídica da política de privacidade** antes de colaboradores reais usarem o sistema.
- **Domínio próprio** (ex.: `app.empresa.com.br`): acrescente o domínio em `DJANGO_ALLOWED_HOSTS` (separado por vírgula, sem `https://`) e em `DJANGO_CSRF_TRUSTED_ORIGINS` (com `https://`). Sem isso, o site responde "Bad Request (400)" ou recusa formulários.
- **Pontuação do questionário v1**: o arquivo `quality_life_oficial_v1.json` traz a pontuação **PROPOSTA**. Um questionário publicado não pode ser editado. Por isso, a aprovação formal do cliente sobre perguntas e pontuação deve vir **antes** de colaboradores reais responderem. Mudanças depois disso exigem uma nova versão.
- **Questionário v2**: quando existir um novo arquivo aprovado, carregue com `python manage.py load_official_questionnaire --file <arquivo_v2> --retire-other-published`. Isso aposenta o v1 e preserva os resultados já calculados.

## 5. Checklist depois do deploy

Marque cada item:

- [ ] Login em `https://quality-life-mvrg23.squareweb.app/admin/` com o administrador criado.
- [ ] Apagar `DJANGO_SUPERUSER_PASSWORD` e reiniciar o app.
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
  curl -I -H "Range: bytes=0-1" https://quality-life-mvrg23.squareweb.app/static/quality_life/videos/inicio-trabalho.mp4
  ```

## 6. Quando algo dá errado

- **Site não liga**: abra os logs do app na Square Cloud. Erros do `release` aparecem ali (ex.: senha do administrador recusada, outro questionário já publicado, banco do Neon inacessível).
- **Erro 500 no site**: os logs do app mostram o traceback completo do erro.
- **"Bad Request (400)"**: confira `DJANGO_ALLOWED_HOSTS`.
- **"Redirecionamento em excesso"**: veja a seção acima sobre `DJANGO_SECURE_SSL_REDIRECT`.
- **Erro de conexão com o banco**: confira se o host do Neon está **sem** `-pooler` e se `POSTGRES_SSLMODE=require`.
