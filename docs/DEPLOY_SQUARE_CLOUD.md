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
2. `release`: atualiza o banco (`migrate`), publica o questionário oficial **v2** (`quality_life_oficial_v2.json`), aposenta o v1 e cria o primeiro administrador. Pode rodar quantas vezes for preciso: o que já existe não é alterado. Se der erro, o site não liga e a mensagem aparece nos logs.
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
GOOGLE_CLIENT_ID=<ID do cliente OAuth, veja docs/GOOGLE_CLOUD_LOGIN.md>
GOOGLE_CLIENT_SECRET=<chave secreta do cliente OAuth>
VAPID_PUBLIC_KEY=<gerada pelo comando generate_vapid_keys, veja a seção 3.1>
VAPID_PRIVATE_KEY=<gerada pelo mesmo comando>
VAPID_SUBJECT=mailto:<e-mail de contato da Quality Life>
```

As duas variáveis do Google são opcionais, mas andam juntas: sem nenhuma, o botão "Continuar com o Google" não aparece e o login por senha continua; com só uma delas o app não sobe. O passo a passo para obtê-las está em `docs/GOOGLE_CLOUD_LOGIN.md`; a URI de redirecionamento é `https://quality-life-mvrg23.squareweb.app/accounts/google/login/callback/`.

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

### 3.1 Notificações no celular com o app fechado (Web Push)

Os lembretes de pausa chegam como notificação no celular mesmo com o app fechado, a tela bloqueada ou outro app em uso. Para isso o servidor precisa de um par de chaves **VAPID**. Sem as três variáveis o site funciona normalmente: o aviso só aparece com o app aberto e a tela de Lembretes explica isso.

1. No seu computador, na pasta do projeto e com as dependências instaladas (`pip install -r requirements.txt`), rode:

   ```
   python manage.py generate_vapid_keys --subject contato@suaempresa.com.br
   ```

   Ele imprime três linhas (`VAPID_PUBLIC_KEY=...`, `VAPID_PRIVATE_KEY=...`, `VAPID_SUBJECT=mailto:...`) e **não grava nada**. Gere **uma vez só**: trocar as chaves depois desliga as notificações de todos os aparelhos até cada pessoa abrir a tela de Lembretes de novo.
2. No painel da Square Cloud, em variáveis de ambiente, crie as três variáveis com os valores impressos. As três andam juntas: com só uma ou duas, o app não sobe (a mensagem de erro diz quais faltam). Não mande a chave privada por e-mail ou chat.
3. Reinicie o app.
4. Teste no celular (iPhone ou Android), em 3 passos:
   1. Abra o site no celular e entre. **No iPhone**, antes de tudo, toque em Compartilhar → **Adicionar à Tela de Início** e abra o app por lá (iOS 16.4 ou mais novo); no Safari comum o iPhone não recebe notificações. No Android, o Chrome funciona direto (e o app pode ser instalado em `/app/instalar/`).
   2. Em **Lembretes**, escolha o intervalo e o horário, toque **Ativar lembretes** e aceite a permissão de notificação. A tela deve dizer **"Notificações ativas neste aparelho, mesmo com o app fechado."**. Se disser outra coisa, o texto explica o motivo (permissão negada, servidor sem chaves, navegador sem suporte).
   3. Feche o app e bloqueie a tela. No próximo horário do intervalo (por exemplo, às 09:00 com expediente 08:00–18:00 e 60 min) a notificação "Hora da pausa" aparece; tocar nela abre a Ginástica Laboral.

Como funciona por dentro, para quem for dar manutenção:

- O envio roda **dentro do próprio app**, numa thread de cada worker do gunicorn, uma vez por minuto (`wellbeing/scheduler.py`, iniciada em `config/wsgi.py`). A Square Cloud não tem agendador de tarefas e reinicia só o processo principal; um worker que morre renasce com a thread, por isso não há processo separado no `START`.
- O relógio da Square Cloud é UTC; os horários são calculados em `America/Sao_Paulo`, com as mesmas regras da tela (inclusive turno da noite). Um lembrete com mais de 5 minutos de atraso não é enviado.
- Dois workers não mandam a mesma notificação: o banco tem um registro único por (lembrete, horário).
- O texto é sempre genérico ("Hora da pausa. Que tal alguns minutos de Ginástica Laboral?"); nunca nome, nota ou dado de saúde. Os logs registram só ids e contagens.
- Para desligar o envio sem apagar as chaves: `WEB_PUSH_SCHEDULER=false` e reinicie.
- Aparelhos cuja assinatura expirou (o serviço de push responde 404/410) são esquecidos sozinhos.

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
- **Questionário v2 (atual)**: o `release` publica `quality_life_oficial_v2.json`, gerado a partir do texto oficial `docs/questionario/questionario-oficial-quality-life.md` por `scripts/build_questionnaire_v2.py`. Ele roda com `--retire-other-published`: o v1 (e qualquer outro questionário publicado, inclusive o de demonstração) passa para `RETIRED` na mesma transação. **Avaliações já concluídas no v1 são preservadas**, com notas e mapa intactos, e uma avaliação do v1 em andamento ainda pode ser concluída. Novas avaliações usam o v2.
- **Pontuação**: o v2 mantém a pontuação **PROPOSTA** do v1 sem nenhuma mudança; as perguntas novas do texto oficial (identificação, múltipla escolha, textos e as demais) não entram na nota. Um questionário publicado não pode ser editado. Por isso, a aprovação formal do cliente sobre perguntas e pontuação deve vir **antes** de colaboradores reais responderem. Mudanças depois disso exigem uma nova versão (`version` maior no JSON).
- **Identificação (seção 1) e respostas abertas**: nome, matrícula, cargo, setor, textos livres e múltipla escolha só aparecem para o próprio colaborador. O relatório do gestor continua mostrando apenas médias de pilares de grupos com 5 pessoas ou mais.

## 5. Checklist depois do deploy

Marque cada item:

- [ ] Login em `https://quality-life-mvrg23.squareweb.app/admin/` com o administrador criado.
- [ ] Apagar `DJANGO_SUPERUSER_PASSWORD` e reiniciar o app.
- [ ] Em `/app/painel/`, **Nova empresa**: nome, a lista de e-mails dos colaboradores e o e-mail do gestor → **Concluir**. Copiar a mensagem pronta e mandar no WhatsApp.
- [ ] Gestor entra com **Continuar com o Google** usando o e-mail da lista e cai na empresa como gestor.
- [ ] Em `/app/equipe/`, o gestor libera o e-mail de um colaborador de teste; o colaborador entra com o Google.
- [ ] Colaborador de teste aceita o **consentimento** e conclui **uma avaliação completa**.
- [ ] Colaborador revoga o consentimento em `/app/privacidade/`.
- [ ] Gestor abre o **relatório**.
- [ ] `/privacidade/` e `/termos/` mostram razão social, CNPJ e e-mail do encarregado corretos.
- [ ] Um vídeo de `/app/aulas/` toca no **iPhone** (Safari).
- [ ] Com as variáveis VAPID configuradas, a tela de Lembretes diz "Notificações ativas neste aparelho, mesmo com o app fechado." e a notificação chega com o app fechado (seção 3.1).
- [ ] No terminal, este comando responde `206`:

  ```
  curl -I -H "Range: bytes=0-1" https://quality-life-mvrg23.squareweb.app/static/quality_life/videos/inicio-trabalho.mp4
  ```

## 6. Quando algo dá errado

- **Site não liga**: abra os logs do app na Square Cloud. Erros do `release` aparecem ali (ex.: senha do administrador recusada, questionário v2 já existente com conteúdo diferente do arquivo, banco do Neon inacessível).
- **Erro 500 no site**: os logs do app mostram o traceback completo do erro.
- **"Bad Request (400)"**: confira `DJANGO_ALLOWED_HOSTS`.
- **"Redirecionamento em excesso"**: veja a seção acima sobre `DJANGO_SECURE_SSL_REDIRECT`.
- **Erro de conexão com o banco**: confira se o host do Neon está **sem** `-pooler` e se `POSTGRES_SSLMODE=require`.
