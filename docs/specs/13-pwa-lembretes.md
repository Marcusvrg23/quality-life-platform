# 13 — App instalável (PWA) e lembretes de pausa

OBJETIVO
O colaborador instala o Quality Life na tela inicial do celular a partir do navegador e recebe, enquanto o app estiver aberto, um lembrete de pausa para a Ginástica Laboral no horário que escolheu.

ATORES E FLUXO
- Qualquer pessoa logada (inclusive no painel, sem empresa): menu → "Instalar o app" (`/app/instalar/`). No Android/Chrome, o botão "Adicionar à tela inicial" aparece só quando o navegador oferece a instalação (`beforeinstallprompt`). No iPhone, segue o passo a passo do Safari "Compartilhar → Adicionar à Tela de Início". Aberto pela tela inicial, vê "O app já está na sua tela inicial.". A tela sempre diz "Apps na App Store e no Google Play: em breve.".
- Membro de uma empresa (colaborador, gestor ou admin): menu → "Lembretes" (`/app/lembretes/`). Escolhe intervalo (60, 90 ou 120 min), início e fim do expediente (padrão 08:00–18:00) e dias (padrão seg–sex) e toca "Ativar lembretes"; só nesse clique o navegador pede permissão de notificação. Depois pode salvar alterações ou desativar. Cada ação confirma com "Lembretes ativados.", "Alterações salvas." ou "Lembretes desativados." (`role="status"`).
- Entrega: em qualquer página do app aberta (aba ou app da tela inicial), o JS busca a própria agenda (`/app/lembretes/agenda/`), agenda o próximo horário e mostra a notificação "Hora da pausa. Que tal alguns minutos de Ginástica Laboral?" via `registration.showNotification`; o clique abre `/app/ginastica/`. Sem permissão ou sem suporte, o mesmo texto aparece como aviso dentro da página, no mesmo horário.

ACEITE
1. Dado qualquer visitante, quando pede `/manifest.webmanifest`, então recebe 200 `application/manifest+json` com name "Quality Life", start_url "/app/", display "standalone", cores do `brand.css` e ícones 192/512 oficiais.
2. Dado qualquer visitante, quando pede `/sw.js`, então recebe 200 `text/javascript` com `Cache-Control: no-cache`; o worker guarda só a página offline (`/offline/`, "Sem conexão. Tente de novo."), o ícone e arquivos de `/static/` com hash no nome; nunca HTML do `/app/`, respostas autenticadas ou requisições que não sejam GET.
3. Dado o app_shell, o login e as telas de `auth_base`, então todos têm o link do manifest e registram o service worker; o painel (`tenant = None`) continua abrindo e não mostra "Lembretes".
4. Dado `/app/instalar/`, então o botão de instalação só aparece com `beforeinstallprompt`, o passo a passo do iPhone está visível, o modo standalone mostra "O app já está na sua tela inicial." e não há selo, logo ou texto sugerindo que o app já está nas lojas.
5. Dado um membro, quando salva os lembretes, então só a própria Membership é gravada; ele relê os mesmos valores; outro usuário e o gestor não veem nem alteram lembretes dele; empresa forjada na sessão → 403; intervalo, dias ou horários fora das opções → 400 e nada muda.
6. Dado `/app/instalar/` e `/app/lembretes/` em 390×844 e 1280×800, então não há rolagem horizontal nem erro no console, e nenhuma permissão é pedida antes do clique em "Ativar lembretes".
7. Dado lembrete ativo de 60 min, 08:00–18:00, seg–sex, e o relógio simulado numa segunda às 09:59:50, quando o relógio chega a 10:00, então o aviso aparece (sem permissão de notificação, dentro da página).
8. Dado o iPhone (Safari envia o horário como "HH:MM", "HH:MM:SS" ou "HH:MM:SS.mmm"), quando o membro troca os horários e salva, então qualquer horário válido é aceito e gravado como hora:minuto; recusado, a tela mostra a mensagem do campo ("Horário de início inválido.", "Escolha pelo menos um dia." etc.).
9. Dado lembretes ativos, quando o membro toca "Desativar lembretes", então eles são desativados mesmo com campos inválidos na tela (formulário próprio, só CSRF + `action=deactivate`), e as escolhas salvas são mantidas.
10. Dado o turno da noite 22:00–06:00 de 60 min às segundas, então os avisos saem segunda às 23:00 e terça às 00:00 … 05:00; nada na madrugada de segunda (turno de domingo) nem na noite de terça. Início = fim ou intervalo ≥ duração → 400.
11. Dado 390×844 no iPhone, então os campos de horário ficam dentro do cartão.

INVARIANTES
- Dado de saúde nunca vai para o cache: o worker não intercepta POST e não grava navegação; só a página offline pública, o ícone e static com hash.
- Isolamento e autorização no servidor: lembrete é lido e alterado só pelo dono, na empresa de `resolve_tenant_context`; o id da Membership nunca vem do cliente; POST com CSRF.
- Gestor não vê lembretes de ninguém (não há tela nem endpoint que liste lembretes).
- Mobile-first: sem rolagem horizontal em 390×844.

DECISÕES
- Modelo `wellbeing.ReminderSetting` (1:1 com Membership): `active`, `interval_minutes` ∈ {60, 90, 120}, `workday_start` ≠ `workday_end` (restrição `wellbeing_reminder_workday_distinct`, migração 0003, que substituiu `workday_start` < `workday_end`), `weekdays` como dígitos ISO ordenados ("12345" = seg–sex), com restrições no banco.
- Horários são do relógio do aparelho. Avisos nos instantes início + k × intervalo estritamente entre início e fim (08:00–18:00 / 60 min → 09:00 … 17:00). O expediente precisa ser maior que o intervalo.
- Turno da noite: fim ≤ início termina no dia seguinte (duração entre 1 min e 24 h, sempre > intervalo). O turno pertence ao dia em que começa: "dias" se refere ao início. O status diz "das 22:00 às 06:00 (dia seguinte)".
- Horários aceitos no POST: "%H:%M", "%H:%M:%S" e "%H:%M:%S.%f"; segundos e frações são descartados. Os campos usam `step="60"`.
- Uma aba por horário: várias abas abertas não repetem o aviso do mesmo horário (marca em `localStorage`, best effort).
- A URL `/app/ginastica/` vai nos dados da notificação; o `sw.js` não contém `/app/`.
- Os arquivos PWA antigos da raiz (`manifest.webmanifest`, `sw.js`, `index.html`…) não são usados nem alterados.

FORA DO ESCOPO
Push com o app fechado (exige chaves VAPID e biblioteca de push); funcionamento offline das telas do app; metas; apps nas lojas; lembretes para outros tipos de prática; relatório agregado de lembretes.

RISCO
R2 (migração, dado por pessoa, tenant, service worker em páginas autenticadas).

PERGUNTAS
Nenhuma bloqueante.

PLANO (fatias)
1. Manifest + sw.js + /offline/ + head do PWA no shell e logins — testes de resposta e de cache (aceite 1–3).
2. Modelo + migração + /app/lembretes/ + agenda JSON — testes de dono, gestor, tenant forjado e valores inválidos (aceite 5).
3. reminders.js no shell (notificação ou aviso) + botão "Ativar lembretes" — Playwright com `page.clock` (aceite 6–7).
4. /app/instalar/ + install.js + itens no menu — testes de servidor e Playwright (aceite 4, 6).
— linha de corte — teste de notificação real com permissão concedida (fica para QA manual no celular).
