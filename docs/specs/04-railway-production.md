# 04 — Produção no Railway

OBJETIVO        Repositório pronto para subir no Railway com health check verde, logs de erro visíveis, release idempotente e textos legais corretos.

ATORES E FLUXO  Admin (Marcus) configura o serviço seguindo `docs/DEPLOY_RAILWAY.md`; o Railway roda build (`collectstatic`), pre-deploy (`release`) e start (`gunicorn`); o health check bate em `/health/`.

ACEITE
- Dado settings de produção, quando o Railway chama `/health/` por HTTP com Host `healthcheck.railway.app`, então responde 200; outra rota por HTTP responde 301 para HTTPS.
- Dado DEBUG=False em produção, quando ocorre erro em `django.request`, então o traceback sai no stdout.
- Dado `DJANGO_SUPERUSER_EMAIL` e `DJANGO_SUPERUSER_PASSWORD`, quando `ensure_superuser` roda, então cria o superusuário uma vez, nunca altera senha existente, ignora variáveis ausentes, recusa senha fraca e nunca imprime a senha.
- Dado um banco novo, quando `release` roda duas vezes, então migra, carrega o questionário oficial ("já carregado" na segunda) e garante o superusuário, sem rodar o seed demo; qualquer erro gera código de saída diferente de zero.
- Dado `collectstatic` com `CompressedManifestStaticFilesStorage` e DEBUG=False, quando as telas principais são abertas, então todas respondem 200 sem erro de manifest.
- A política de privacidade não diz que coletamos nome.

INVARIANTES     Segurança de produção inalterada (exceto isenção de redirect só para `health/`); nenhum segredo no repositório; senha nunca em log; seed demo nunca roda em produção; questionário publicado continua imutável.

FORA DO ESCOPO  Deploy, criação de conta, domínio próprio, e-mail transacional, mudança no scoring ou no questionário.

RISCO           R2 (auth/superusuário, configuração de segurança de produção, LGPD).

PERGUNTAS       Nenhuma bloqueante.
