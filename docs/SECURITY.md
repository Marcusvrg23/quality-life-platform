# Segurança

Este documento registra os requisitos mínimos de segurança da Quality Life V2. A implementação e a validação desses controles ocorrerão nas milestones apropriadas; a M0 apenas estabelece as regras.

## Controles obrigatórios

- Autenticação deve ser feita no servidor, com sessões e cookies configurados de forma segura.
- Autorização deve ser aplicada no servidor em toda operação protegida; esconder elementos na interface não substitui controle de acesso.
- Todo dado de negócio deve ser isolado por empresa (tenant). Consultas, alterações e relatórios devem respeitar esse escopo, inclusive em tarefas administrativas.
- Operações que alteram estado devem usar a proteção CSRF do Django.
- Conteúdo exibido deve permanecer escapado por padrão. HTML fornecido por usuários não pode ser marcado como seguro sem sanitização e revisão contra XSS.
- Secrets e credenciais devem vir do ambiente, nunca do repositório ou do código-fonte.
- Eventos relevantes de autenticação, autorização, administração e acesso a dados sensíveis devem produzir logs de auditoria úteis, sem registrar secrets ou conteúdo sensível desnecessário.
- Dados pessoais e respostas individuais devem ter acesso mínimo, retenção definida e proteção compatível com sua sensibilidade.
- Diretoria e dashboard corporativo devem receber somente dados agregados. Grupos abaixo do limiar mínimo definido para privacidade não podem ser exibidos nem inferidos por filtros ou combinações de relatórios.

## Relatório executivo e inferência por diferença

O relatório usa sempre os últimos 90 dias até hoje e ignora parâmetros de período na URL, porque um período livre permitia comparar dois recortes quase iguais e isolar as respostas de uma pessoa, mesmo com o grupo mínimo de 5.

Risco residual conhecido: como a janela é móvel, um gestor ainda pode comparar o relatório de dias seguidos e, se uma única avaliação entrar ou sair da janela, inferir a contribuição dela. A correção definitiva é trabalhar com ciclos de avaliação fechados (o relatório só mostra ciclos encerrados, sem janela móvel), prevista para depois do lançamento.

## Uso das práticas de bem-estar

Cada prática (`wellbeing.ActivitySession`) é gravada só pelo próprio usuário, na empresa ativa, e só ele vê o próprio progresso. No relatório da empresa aparecem apenas agregados da semana e do mês correntes (pessoas ativas, minutos, práticas): com menos de 5 pessoas no período nada é exibido, e a divisão por tipo só aparece se todo tipo tiver 0 ou 5+ pessoas, para que "total menos tipos visíveis" não revele um grupo pequeno. Nunca há nome, e-mail ou ranking.

Risco residual conhecido: a semana está contida no mês, e as duas janelas crescem dia a dia; comparar mês e semana, ou o mesmo relatório em dias seguidos, mostra a variação de um grupo que pode ter menos de 5 pessoas (quantas práticas e minutos, nunca quem). A mesma correção prevista para o relatório (ciclos fechados) vale aqui.

## Consentimento LGPD

A avaliação trata dado de saúde (dado sensível) com base em consentimento específico e destacado, registrado por empresa em `identity.ConsentRecord` (somente inclusão; a única alteração permitida é preencher `revoked_at` uma vez). Sem consentimento ativo na versão vigente (`config/legal.py`), o servidor bloqueia início, respostas, revisão e conclusão. Quem tem o consentimento mais recente revogado naquela empresa sai do relatório executivo. A exclusão dos dados é pedida ao encarregado; não há exclusão automática.

## Login com Google e lista de e-mails liberados

Entrar é "Continuar com o Google" (OAuth 2.0 / OpenID Connect via django-allauth, só as duas rotas do fluxo: `/accounts/google/login/` e `/accounts/google/login/callback/`). Quem decide o acesso é a lista de e-mails de cada empresa (`identity.AllowedEmail`) e só o código em `identity/eligibility.py`: uma conta nova nasce apenas se o e-mail, com `email_verified = true` no id_token, estiver liberado em ao menos uma empresa ativa; o papel (colaborador ou gestor) vem da lista; remover da lista desativa a Membership na hora. Um e-mail recusado não é gravado em lugar nenhum: a resposta é renderizada direto, sem conta, sem `SocialAccount`, sem mensagem em sessão. Conta existente com o mesmo e-mail verificado é ligada ao identificador estável da conta Google (`SocialAccount.uid = sub`) e a senha continua valendo; o login por senha também aplica a lista. Tokens do Google não são guardados (`SOCIALACCOUNT_STORE_TOKENS = False`), escopos só `openid email profile`, e nenhuma tela ou rota padrão do allauth (cadastro, troca de e-mail, redefinição) existe. As credenciais `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` vêm só do ambiente; com uma delas faltando o settings falha alto e, sem as duas, o botão some e as rotas respondem 404. Logs do fluxo registram ids, nunca e-mails.

## PWA e service worker

O service worker do protótipo não será migrado nem modificado na M0. Antes de habilitar PWA nas páginas autenticadas ou dinâmicas, a estratégia de cache deverá passar por revisão de segurança. Conteúdo privado, personalizado ou sujeito a atualização não poderá ser armazenado ou servido como dado stale de forma indevida; logout, invalidação e uso em dispositivo compartilhado também deverão ser testados.

Estratégia adotada (docs/specs/13-pwa-lembretes.md): o `/sw.js` servido pelo Django (os arquivos PWA da raiz continuam sendo só do protótipo) guarda em cache apenas a página pública `/offline/`, o ícone e arquivos de `/static/` com hash no nome. Ele ignora requisições que não sejam GET e nunca grava navegação: páginas do `/app/` sempre vêm da rede e, sem conexão, são trocadas pela página offline. Por isso o logout e um aparelho compartilhado não deixam dado pessoal no cache; o teste de navegador confere que nenhuma URL do `/app/` entra no cache. A notificação de pausa tem texto genérico, sem dado de saúde, e no aparelho fica só o horário do último aviso (`localStorage`). A agenda de lembretes (`/app/lembretes/agenda/`) responde com `Cache-Control: no-store, private` e só para o dono.

## Notificações push

O push com o app fechado (spec 13) segue as mesmas regras. A assinatura de cada aparelho (`wellbeing.PushSubscription`: endereço do serviço de push e chaves de cifragem do navegador, nunca dado de saúde) é criada e apagada só pelo dono, na empresa ativa, por endpoints com login e CSRF; o id da Membership nunca vem do cliente e uma empresa forjada na sessão recebe 403. Cada conta tem a própria linha por aparelho: "Desativar notificações neste aparelho" apaga só a linha da conta logada e nunca cancela a assinatura do navegador, então outras contas no mesmo aparelho não são afetadas; desativar os lembretes de pausa ou sair da conta mantém o aparelho ligado (as mensagens são sempre genéricas). Todo envio passa por `wellbeing.notifications.notify()`, o único módulo que chama o `pywebpush`: ele exige Membership e empresa ativas, respeita a preferência da pessoa por categoria ("pausas", "dicas"), recusa texto que contenha o nome ou o e-mail da pessoa ou palavras de resultado (nota, pilar, resposta, diagnóstico…), porque a notificação aparece na tela bloqueada. O futuro assistente só envia por `notify(..., category="dicas")`. As chaves VAPID vêm só do ambiente (as três juntas ou nenhuma); os logs registram ids e contagens, nunca e-mail ou texto. Nenhum gestor vê lembretes, preferências ou aparelhos de ninguém.

## IA futura

A IA será opcional e não fará parte do core. Ela nunca poderá alterar score nem ser necessária para o funcionamento do produto. Uma integração futura deverá acessar apenas operações e dados explicitamente autorizados, com escopo de tenant, minimização e auditoria; modelos ou agentes não terão credenciais de banco nem acesso irrestrito a consultas. Dados sensíveis não poderão ser enviados a provedores sem base legal, contrato, consentimento quando aplicável e controles de retenção definidos.
