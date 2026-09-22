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

## PWA e service worker

O service worker do protótipo não será migrado nem modificado na M0. Antes de habilitar PWA nas páginas autenticadas ou dinâmicas, a estratégia de cache deverá passar por revisão de segurança. Conteúdo privado, personalizado ou sujeito a atualização não poderá ser armazenado ou servido como dado stale de forma indevida; logout, invalidação e uso em dispositivo compartilhado também deverão ser testados.

## IA futura

A IA será opcional e não fará parte do core. Ela nunca poderá alterar score nem ser necessária para o funcionamento do produto. Uma integração futura deverá acessar apenas operações e dados explicitamente autorizados, com escopo de tenant, minimização e auditoria; modelos ou agentes não terão credenciais de banco nem acesso irrestrito a consultas. Dados sensíveis não poderão ser enviados a provedores sem base legal, contrato, consentimento quando aplicável e controles de retenção definidos.
