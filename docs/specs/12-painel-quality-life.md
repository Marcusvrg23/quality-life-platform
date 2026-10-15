# 12 — Painel da Quality Life e fim do beco sem saída após o login

OBJETIVO
A equipe da Quality Life (superusuário) cadastra empresas, convida o gestor de cada uma e entra nelas como administradora sem usar o `/admin/`; quem não tem empresa vê uma saída clara em vez de uma página sem ação.

ATORES E FLUXO
- Superusuário: entra em `/login/`. Sem vínculo, `/app/` leva ao painel (`/app/painel/`). Com vínculo, vê o app normal e o link "Painel da Quality Life" no menu. No painel: lista de empresas (nome, ativa, colaboradores ativos, gestores ativos); "Nova empresa" (nome → slug único); por empresa: "Gerar convite de gestor" (link de uso único mostrado uma vez), "Entrar como administrador" (com confirmação), "Desativar/Reativar".
- Gestor convidado: abre `/convite/<token>/`, cria conta ou confirma, e entra como CORPORATE_MANAGER da empresa. Depois convida colaboradores em `/app/equipe/` (só COLLABORATOR).
- Usuário comum sem vínculo: vê "Sua conta ainda não está ligada a uma empresa. Peça um novo convite ao RH da sua empresa.", o botão "Sair" e o e-mail comercial (`QL_SALES_EMAIL`), com status 403.

ACEITE
1. Dado um superusuário sem vínculo, quando abre `/app/`, então recebe 302 para o painel; dado um usuário comum sem vínculo, recebe 403 com o texto novo, "Sair" e o e-mail comercial.
2. Dado quem não é superusuário (colaborador, gestor, admin, staff, sem vínculo), quando abre o painel ou faz POST em qualquer ação, então recebe 404 e nada muda no banco.
3. Dado um superusuário, quando cria empresas com o mesmo nome, então os slugs são únicos (`nome`, `nome-2`, …); nome vazio é recusado.
4. Dado um convite de gestor, quando é aceito, então nasce Membership CORPORATE_MANAGER ativa; o link é de uso único, expira em 7 dias e o banco guarda só o SHA-256 do token.
5. Dado um gestor ou admin, quando gera convites na Equipe (mesmo forjando `role`), então todos são COLLABORATOR; criar convite de gestor sem ser superusuário é recusado no serviço e o banco recusa outros papéis.
6. Dado um superusuário, quando confirma "Entrar como administrador", então só a própria conta ganha (ou reativa) Membership ADMIN nessa empresa e cai no `/app/` dela; sem a confirmação, nada acontece.
7. Dado um superusuário, quando desativa uma empresa, então os membros perdem o acesso e nenhum dado é apagado; reativar devolve o acesso.
8. Dado o gestor da empresa A, então ele não vê membros, convites nem a home da empresa B; o `next` do login continua levando à página pedida.

INVARIANTES
- Autorização no servidor: painel e ações conferem `is_superuser` na view; o link no menu é só conveniência. Não superusuário → 404.
- Isolamento: superusuário não ganha acesso implícito a dados de empresa; só via Membership ADMIN criada por ação explícita e confirmada.
- Token só como hash SHA-256, mostrado uma vez; aceite com `transaction.atomic` + `select_for_update` (já existente).
- Todas as ações são POST com CSRF.
- Mobile-first: sem scroll horizontal em 390×844.

FORA DO ESCOPO
Apagar empresas, editar nome ou slug, listar/revogar convites de gestor pendentes no painel, envio de e-mail, promover um colaborador já existente a gestor, auditoria persistida em banco (fica só o log com ids).

RISCO
R2 (auth, tenant, tokens, migração).

PERGUNTAS
Nenhuma bloqueante.
