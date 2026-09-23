# M2: identidade e contexto de organização

O login em `/login/` usa email e senha com sessão Django. O logout aceita somente POST em `/logout/`. Não existe cadastro público nesta milestone; contas e vínculos são criados pelo admin Django ou por operação administrativa controlada.

Em `/app/`, um usuário com uma única membership ativa em organização ativa entra nesse contexto. Com múltiplas memberships, escolhe explicitamente a empresa por POST em `/app/select-organization/`, protegido por CSRF. A seleção fica na sessão. Cada acesso revalida usuário, membership e organização ativos; revogação ou desativação interrompe o acesso imediatamente. O parâmetro enviado pelo navegador nunca concede acesso por si só.

`COLLABORATOR`, `CORPORATE_MANAGER`, `PROFESSIONAL` e `ADMIN` são papéis da aplicação, sempre limitados a uma membership. Nesta milestone, todos veem apenas a página simples do próprio contexto. Não há acesso a dados individuais, dashboard corporativo ou permissão implícita para outras empresas. `ADMIN` não implica `is_staff`. `is_superuser` não contorna o isolamento tenant. O admin Django dos modelos de identidade é reservado a superusers operacionais para desenvolvimento e QA; usuários staff comuns não podem listar nem alterar usuários, empresas ou vínculos.

As rotas de fundação `/` e `/health/` continuam públicas. Nenhuma página autenticada é adicionada ao service worker do protótipo. O banco permanece PostgreSQL, sem fallback SQLite.
