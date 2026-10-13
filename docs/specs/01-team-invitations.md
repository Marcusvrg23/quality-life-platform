# 01 — Equipe, convites por link e senha sem e-mail

OBJETIVO
O gestor da empresa adiciona e retira colaboradores sozinho, por link de convite enviado no WhatsApp, e o suporte gera link de nova senha sem e-mail.

ATORES E FLUXO
- Gestor (CORPORATE_MANAGER ou ADMIN da empresa ativa): abre "Equipe" (`/app/equipe/`), vê membros (e-mail, papel, ativo, entrada), desativa/reativa colaboradores, gera 1–50 convites, copia ou envia cada link pelo WhatsApp (mostrado uma única vez) e revoga convites pendentes.
- Convidado: abre `/convite/<token>/`. Sem login cria conta (e-mail + senha); com login confirma "Entrar na empresa <nome>". Entra como COLLABORATOR na empresa e cai em `/app/`.
- Qualquer usuário logado: troca a própria senha em `/app/senha/`.
- Suporte (superusuário no admin): ação "Gerar link de redefinição de senha" em Usuários; a pessoa abre `/senha/redefinir/<uidb64>/<token>/` e define nova senha.

ACEITE
1. Dado um colaborador, quando abre `/app/equipe/`, então recebe 403; dado um gestor, recebe 200 só com membros da própria empresa e sem dado de avaliação.
2. Dado um gestor, quando desativa/reativa um COLLABORATOR da empresa, então o vínculo muda e o desativado perde o acesso; o próprio usuário e não-colaboradores são recusados; id de outra empresa → 404.
3. Dado um gestor, quando gera N convites (1 ≤ N ≤ 50), então vê N links uma única vez, com "Copiar" e "Enviar por WhatsApp"; 0 e 51 são recusados; o banco guarda só o SHA-256 do token.
4. Dado um convite pendente, quando o gestor revoga, então o link passa a responder 404.
5. Dado um link válido, quando um visitante cria conta ou um usuário logado aceita, então nasce Membership COLLABORATOR ativa, o convite é marcado usado e a pessoa entra em `/app/`; o segundo uso do mesmo link falha.
6. Dado um link inexistente, expirado, usado, revogado ou de empresa inativa, então a resposta é a mesma página genérica com 404.
7. Dado um usuário logado, quando troca a senha em `/app/senha/`, então a nova senha passa a valer.
8. Dado um superusuário com exatamente 1 usuário selecionado, quando roda a ação do admin, então recebe um link que redefine a senha; com 0 ou 2+ usuários, recebe erro; não-superusuário não acessa.

INVARIANTES
- Isolamento: toda consulta da Equipe filtra por `resolve_tenant_context(request).organization`; id de outra empresa → 404.
- Autorização no servidor: papel verificado na view; o link no menu é só conveniência.
- Gestor não vê dado de avaliação na Equipe (nem status de resposta, nem nota).
- Token de convite só como hash SHA-256; link exibido uma vez, nunca regravado nem guardado em sessão.
- Aceite com `transaction.atomic` + `select_for_update`; revogação é UPDATE condicional.
- Mobile-first: sem scroll horizontal em 390×844; regra `<style>` de imagens do `app_shell.html` preservada.

FORA DO ESCOPO
Envio de e-mail, convite para outros papéis, limite de vagas, cadastro de empresas fora do admin, scoring, avaliações, questionário e relatório.

RISCO
R2 (auth, tenant, tokens, migração).

PERGUNTAS
Nenhuma bloqueante.
