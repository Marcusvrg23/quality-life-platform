# Credenciais do Google para "Continuar com o Google"

Guia passo a passo para quem não é programador. Leva uns 15 minutos e só precisa ser feito uma vez por ambiente (produção). Sem estas credenciais o site continua funcionando: o botão do Google simplesmente não aparece e o login por e-mail e senha segue normal.

Nenhuma credencial vai para o repositório. As duas chaves entram só nas **variáveis de ambiente** da Square Cloud (`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`).

## 1. Projeto no Google Cloud

1. Entre em <https://console.cloud.google.com/> com a conta Google da Quality Life.
2. No topo, abra o seletor de projetos e clique em **Novo projeto**. Nome sugerido: `Quality Life`. Clique em **Criar** e aguarde o projeto ficar selecionado.

## 2. Tela de consentimento (uma vez)

1. Menu ☰ → **APIs e serviços** → **Tela de permissão OAuth** (pode aparecer como "Branding" / "Google Auth Platform").
2. Tipo de usuário: **Externo**. Clique em **Criar**.
3. Preencha:
   - Nome do app: `Quality Life`
   - E-mail de suporte do usuário: o e-mail da Quality Life
   - **Logotipo do app: deixe em branco.** Com logotipo o Google exige um processo de verificação demorado; sem logotipo não exige.
   - Domínios autorizados: `squareweb.app`
   - Links da política de privacidade e dos termos: `https://quality-life-mvrg23.squareweb.app/privacidade/` e `https://quality-life-mvrg23.squareweb.app/termos/`
   - E-mail de contato do desenvolvedor: o e-mail da Quality Life
4. **Escopos**: clique em **Adicionar ou remover escopos** e marque somente estes três (todos são "não sensíveis", não exigem verificação):
   - `openid`
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
5. Salve até o fim.
6. Em **Público-alvo** (ou "Status de publicação"), clique em **Publicar app** e confirme. O status precisa ficar **Em produção**. Enquanto estiver "Em teste", só os e-mails de teste conseguem entrar e o acesso expira em 7 dias.

## 3. Credencial OAuth (ID do cliente)

1. Menu ☰ → **APIs e serviços** → **Credenciais** → **Criar credenciais** → **ID do cliente OAuth**.
2. Tipo de aplicativo: **Aplicativo da Web**. Nome: `Quality Life produção`.
3. **Origens JavaScript autorizadas**: `https://quality-life-mvrg23.squareweb.app`
4. **URIs de redirecionamento autorizados**: cole exatamente, com a barra no fim:

   ```
   https://quality-life-mvrg23.squareweb.app/accounts/google/login/callback/
   ```

   Qualquer diferença (http, sem a barra final, outro domínio) faz o Google responder `redirect_uri_mismatch`.
5. Clique em **Criar**. Vai aparecer o **ID do cliente** (termina em `.apps.googleusercontent.com`) e a **Chave secreta do cliente**. Copie os dois agora; a chave secreta não é mostrada de novo depois (dá para gerar outra).

## 4. Variáveis na Square Cloud

No painel da Square Cloud (ou no `.env` enviado com `squarecloud app env set`), acrescente:

```
GOOGLE_CLIENT_ID=<ID do cliente>
GOOGLE_CLIENT_SECRET=<Chave secreta do cliente>
```

As duas precisam estar juntas: com só uma delas o site não sobe (erro proposital para não ficar meio configurado). Depois **reinicie o app**. O botão "Continuar com o Google" aparece em `/login/`.

## 5. Teste

1. No painel (`/app/painel/`), cadastre uma empresa de teste com o seu próprio e-mail na lista.
2. Saia e, em `/login/`, clique em **Continuar com o Google**. O Google mostra a escolha de conta; escolha o e-mail que está na lista.
3. Você deve cair no app dessa empresa. Um e-mail fora da lista recebe "Seu e-mail ainda não foi liberado…" e nenhuma conta é criada.

## Domínio próprio no futuro

Se o site ganhar um domínio próprio (ex.: `app.empresa.com.br`), repita o passo 3 adicionando a nova origem e a nova URI de redirecionamento `https://<domínio>/accounts/google/login/callback/`, e acrescente o domínio em **Domínios autorizados** da tela de consentimento. O mesmo ID de cliente serve para os dois endereços.

## Problemas comuns

- **`redirect_uri_mismatch`**: a URI do passo 3.4 não está idêntica. Confira `https`, o domínio e a barra final.
- **"Este app está bloqueado" / "não verificado"**: o app ainda está "Em teste" ou foi adicionado logotipo/escopo sensível. Volte ao passo 2.6 e 2.4.
- **Botão não aparece**: as variáveis do passo 4 não foram salvas ou o app não foi reiniciado.
- **"Seu e-mail ainda não foi liberado"**: o e-mail da conta Google escolhida não está na lista de nenhuma empresa ativa. Peça ao RH (ou inclua no painel) exatamente o e-mail que o Google mostra na escolha de conta.
