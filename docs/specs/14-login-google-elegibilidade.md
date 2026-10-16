# 14 — Login com Google e elegibilidade por lista de e-mails

OBJETIVO
Quem está na lista de e-mails liberados de uma empresa entra com "Continuar com o Google" e cai na empresa certa com o papel certo (colaborador ou gestor); quem não está em nenhuma lista não entra e nenhuma conta é criada. Cadastrar uma empresa com a lista inteira leva uma tela.

ATORES E FLUXO
- Operadora Quality Life (superusuário): no painel (`/app/painel/`), "Nova empresa" pede nome, a lista colada de e-mails dos colaboradores e o(s) e-mail(s) do gestor e termina em "Concluir". Vê quantos entraram, quais foram ignorados (inválidos ou repetidos) e uma mensagem pronta para o WhatsApp. Por empresa, abre "E-mails liberados" para adicionar, remover, "Tornar gestor" ou "Voltar a colaborador".
- Gestor (CORPORATE_MANAGER ou ADMIN da empresa ativa): em "Equipe" (`/app/equipe/`) cola e-mails em "Liberar e-mails" (sempre colaboradores), remove e-mails de colaboradores e continua ativando/desativando membros. Não libera nem remove outro gestor.
- Pessoa liberada: em `/login/` clica em "Continuar com o Google", escolhe a conta (prompt=select_account), volta pelo callback `/accounts/google/login/callback/` e entra. Com e-mail em duas empresas, escolhe a empresa. Conta existente com o mesmo e-mail verificado (inclusive superusuário) liga o Google e entra; a senha continua valendo.
- Pessoa fora da lista: vê "Seu e-mail ainda não foi liberado. Peça ao RH da sua empresa para incluir <e-mail>." Nenhuma conta, e-mail social ou registro do e-mail recusado é gravado.
- Contas antigas: "Entrar com e-mail e senha" fica recolhido atrás de um link discreto; ao entrar por senha a lista também é aplicada; `next` continua funcionando.

MODELO
`identity.AllowedEmail`: organization, email (minúsculas, sem espaços), role ∈ {COLLABORATOR, CORPORATE_MANAGER}, added_by (SET_NULL), created_at, updated_at; único por (organization, email); check de papel no banco. O vínculo com a conta Google fica em `socialaccount.SocialAccount` (uid = `sub` do id_token), sem tokens (`SOCIALACCOUNT_STORE_TOKENS = False`).

REGRAS (todas em `identity/eligibility.py`)
- `memberships_for_email(email)` cria ou reativa as Memberships das empresas ATIVAS em que o e-mail está liberado, com o papel da lista; alinha o papel de uma Membership COLLABORATOR/CORPORATE_MANAGER existente ao da lista; nunca mexe em Membership ADMIN nem em superusuário. Nenhuma outra parte do código decide empresa ou papel no cadastro.
- `is_eligible(email)` decide se uma conta nova pode nascer: só com ao menos uma empresa ativa que liberou o e-mail.
- `remove_allowed_email(entry)` apaga a entrada e desativa na hora a Membership correspondente (exceto ADMIN e superusuário).
- `set_allowed_email_role(entry, role)` troca o papel na lista e na Membership existente (exceto ADMIN e superusuário).
- Google: só e-mail com `email_verified = true`; escopos openid/email/profile; vínculo pelo `sub`; sem `/signup` público nem telas padrão do allauth.

ACEITE
1. Dado um e-mail liberado como colaborador na empresa A, quando entra com o Google (simulado), então nasce a conta, uma Membership COLLABORATOR ativa em A e a pessoa cai em `/app/`; liberado como gestor → CORPORATE_MANAGER.
2. Dado um e-mail liberado em duas empresas ativas, quando entra, então existem duas Memberships e aparece a escolha de empresa; se uma empresa está inativa, ela não dá acesso.
3. Dado um e-mail fora de qualquer lista ou com `email_verified = false`, quando volta do Google, então nenhuma conta, SocialAccount ou EmailAddress é criada, o e-mail recusado não é gravado e a tela mostra a mensagem com o e-mail (só no caso fora da lista).
4. Dado um usuário existente (inclusive superusuário) com o mesmo e-mail verificado, quando entra com o Google, então a conta Google é ligada (SocialAccount com `sub`), a senha continua válida e `memberships_for_email` é aplicada.
5. Dado um e-mail removido da lista, então a Membership correspondente fica inativa na hora; Membership ADMIN e superusuário nunca são rebaixados nem desativados.
6. Dado o gestor da empresa A, então não vê nem edita a lista da B (404); colaborador recebe 403 nas ações de Equipe; não superusuário recebe 404 em todo o painel; tudo POST + CSRF.
7. Dado o assistente "Nova empresa" com e-mails separados por vírgula, ponto e vírgula, quebra de linha e espaços, quando conclui, então os válidos entram uma vez, os inválidos e repetidos são relatados e a mensagem para o WhatsApp aparece com o endereço do site.
8. Dado o ambiente sem `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, então o botão some, as rotas do Google respondem 404 e o login por senha funciona; `/signup/` e `/accounts/signup/` não existem.
9. Dado o relatório da empresa, então o topo mostra "E-mails liberados: N" e "Pessoas cadastradas: N" (contagens, sem nomes); `MIN_GROUP` não muda.
10. Dado 390×844 e 1280×800, então login, painel (assistente e lista), Equipe e relatório não têm rolagem horizontal nem erro no console.

INVARIANTES
- Autorização no servidor: painel e ações só para superusuário (404 para os demais); Equipe só para CORPORATE_MANAGER/ADMIN da empresa ativa; toda consulta à lista filtra pela empresa do `resolve_tenant_context` ou pelo id conferido no painel.
- Nenhum segredo no repositório: credenciais do Google só por variável de ambiente; com uma das duas faltando o settings falha alto.
- Logs só com ids (empresa, usuário, entrada), nunca e-mail.
- Scoring, consentimento da avaliação e `MIN_GROUP` intocados.
- Mobile-first: sem scroll horizontal em 390×844; `identity.css` e `tmp/` não são tocados.

FORA DO ESCOPO
Link de empresa, código de acesso, convite novo, domínio por empresa, envio de e-mail, importação de planilha, papel "Operadora Quality" sem superusuário, apagar as rotas e migrações antigas de convite.

RISCO
R2 (auth, tenant, migração).

PERGUNTAS
Nenhuma bloqueante.

## Próximos passos (não fazem parte desta entrega)
- Papel "Operadora Quality" sem superusuário: hoje o painel exige `is_superuser`; um papel próprio permitiria dar o painel a alguém da Quality Life sem acesso ao `/admin/`.
- Planilha `.xlsx`: aceitar o arquivo do RH direto no assistente, em vez de colar a coluna.
- Domínio corporativo: liberar `@empresa.com.br` inteiro em vez de e-mail a e-mail, com `hd` do Google Workspace como reforço.
- Subdomínio por empresa (opcional, só marca): `empresa.quality-life...` apenas para logo e nome; a autorização continua pela lista.
