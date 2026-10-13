# 08 — Conferência do diagnóstico v2

OBJETIVO
Provar com testes e um documento legível que o questionário v2, a pontuação "oficial-v1" e o relatório da empresa fazem a conta certa, sem mudar regra nem tela.

ATORES E FLUXO
- Colaborador: entra, autoriza, responde as 101 perguntas pelas telas (GET + POST com CSRF), revisa, conclui, vê o próprio mapa.
- Gestor: abre o relatório executivo; vê só agregados.
- Marcus: mostra `docs/qa/conferencia-diagnostico.md` ao cliente na aprovação da pontuação.

ACEITE
1. Dado `tests/oracle_v2.py` (lê só o JSON), quando 6 perfis (a melhor, b pior, c misto, d "não conta ponto", e opcionais em branco, f exclusivas e "Outro:") respondem pelas telas, então nota e faixa de cada pilar e a geral salvas são iguais ao gabarito (60 comparações).
2. Dada uma obrigatória vazia, então não avança; opcionais (Matrícula, 2.12, 12.3) ficam em branco; exclusiva não combina e substitui as outras; "Outro:" exige texto; texto e múltipla escolha não mudam nota.
3. Dado voltar e trocar uma resposta, então a nota concluída usa a resposta nova; concluir duas vezes não cria segundo resultado.
4. Dada outra pessoa (mesma empresa, outra empresa ou gestor), então não lê nem grava a avaliação (404/403).
5. Dado o relatório: 4 avaliados → sem números; 5 → média geral, média por pilar, distribuição, % afetados, prioridade e ordem iguais à conta do teste; só a última avaliação do período conta; fora do período não conta; revogar consentimento e membro inativo tiram a pessoa.
6. Dado o relatório, então nenhum nome, matrícula, cargo, setor digitado, texto livre, e-mail ou opção de múltipla escolha aparece.
7. Dado o CI, então o documento é gerado em `qa-artifacts/` e o `docs/qa/` commitado é igual ao gerado.

INVARIANTES
Scoring determinístico e intocado; gestor só vê agregado (MIN_GROUP 5); isolamento entre empresas; autorização no servidor.

FORA DO ESCOPO
Corrigir divergências (só documentar), mudar pontuação, faixas, telas ou CI; deploy; merge.

RISCO
R2 (scoring e privacidade), mas só testes e documentação mudam.

PERGUNTAS
Nenhuma bloqueante.
