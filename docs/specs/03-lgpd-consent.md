# 03 — Consentimento LGPD, páginas legais (minuta) e relatório com período fixo

OBJETIVO
O colaborador só responde à avaliação depois de um consentimento específico e destacado, pode revogá-lo, e qualquer pessoa lê a política de privacidade e os termos (minuta) sem login.

ATORES E FLUXO
- Colaborador: abre "Minha avaliação", lê o bloco de consentimento, marca a caixa (não pré-marcada) e inicia. Em `/app/privacidade/` vê o consentimento ativo e pode revogá-lo (POST + confirmação).
- Gestor/Admin: relatório sempre com os últimos 90 dias até hoje; não vê "Minha avaliação" no menu nem na home.
- Profissional: não vê "Minha avaliação" nem o card de prioridade.
- Visitante: abre `/privacidade/` e `/termos/` sem login, com a faixa "MINUTA — pendente de revisão jurídica".

ACEITE
1. Dado o hub, quando o colaborador envia "Iniciar" sem a caixa, então nada é criado e ele volta ao hub com mensagem; com a caixa, nasce 1 ConsentRecord e 1 avaliação na mesma transação; repetir não duplica o consentimento.
2. Dado consentimento revogado, então start, question, review e complete não gravam nada e redirecionam ao hub.
3. Dado colaborador cujo consentimento mais recente naquela empresa está revogado, então suas avaliações saem do relatório; o consentimento de uma empresa não vale para outra.
4. Dado ConsentRecord salvo, então só `revoked_at` pode ser preenchido, uma única vez; o admin é somente leitura.
5. Dado visitante anônimo, então `/privacidade/` e `/termos/` respondem 200 com "MINUTA" e os dados de `LEGAL_COMPANY_NAME`, `LEGAL_CNPJ`, `LEGAL_DPO_EMAIL` (ou os marcadores padrão).
6. Dado `?inicio=&fim=` na URL do relatório, então o resultado é idêntico ao sem parâmetros e não há formulário de período.
7. Dado cada papel, então menu e home não têm link que responda 403.
8. Dado 390×844, então `/privacidade/`, `/termos/`, `/app/privacidade/` e o hub não têm scroll horizontal.

INVARIANTES
- Autorização no servidor: o portão de consentimento está nas views, não só no template.
- Isolamento: consentimento e revogação filtram por usuário e empresa ativa.
- Agregado: o relatório continua com MIN_GROUP=5; o período deixa de ser livre.
- Scoring intocado.

FORA DO ESCOPO
Ciclos fechados de avaliação, exclusão automática de dados, texto jurídico final, e-mail ao encarregado, reconsentimento em massa ao trocar de versão.

RISCO
R2 (dado de saúde, autorização, migração).

PERGUNTAS
Nenhuma bloqueante. Textos legais são minuta com marcadores para o jurídico.
