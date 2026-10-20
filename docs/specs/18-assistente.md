# 18 — Assistente Quality (piloto)

OBJETIVO
O colaborador tira dúvidas rápidas de bem-estar no trabalho e de uso do app
num chat com IA, sem que a conversa fique guardada nem identifique a pessoa.

ATORES E FLUXO
Qualquer papel de uma empresa listada em `ASSISTANT_ORGANIZATIONS` (piloto):
menu → Assistente → lê o aviso → escreve → recebe a resposta. Recarregar ou
sair da página apaga a conversa.

ACEITE
1. Sem `GROQ_API_KEY` ou com a empresa fora de `ASSISTANT_ORGANIZATIONS`: página
   e envio respondem 404 e o menu não mostra o item. Anônimo → login; empresa
   forjada → 403.
2. A página avisa que é uma inteligência artificial, que não substitui
   atendimento de saúde, que não se devem escrever dados pessoais ou de saúde,
   que a conversa não fica salva, o limite diário e o CVV (188).
3. A API recebe só o prompt do sistema e as mensagens: nunca nome, e-mail,
   empresa ou questionário. E-mails, telefones/CPF (8+ dígitos) e as palavras
   do nome/e-mail da própria pessoa viram "[removido]" antes do envio.
4. Histórico validado (papéis user/assistant, até 1000 caracteres, última
   mensagem do usuário) e cortado nas últimas 12 mensagens; inválido → 400 sem
   chamar a API.
5. Mensagem sobre suicídio ou se machucar recebe resposta fixa com CVV 188 e
   SAMU 192, sem chamar a API e sem contar no limite.
6. Limite diário por pessoa (`ASSISTANT_DAILY_LIMIT`, padrão 30) → 429. O banco
   guarda só a contagem (`AssistantUsage`: pessoa, dia, número).
7. Falha da API (erro HTTP, rede, tempo, resposta malformada) → 502 com
   mensagem genérica. Logs só com ids e status, nunca o texto.
8. O prompt do sistema traz a data de hoje e a dica da semana/data especial
   (spec 17), para a resposta acompanhar o calendário.
9. Em 390×844 e 1280×800: resposta exibida como texto (sem HTML), sem scroll
   horizontal, sem erro de console; recarregar apaga a conversa.
10. Sugestão sem pedir: ao abrir o Assistente ele cumprimenta com uma sugestão
    do período (manhã, tarde, noite) que leva em conta o dia da semana, a data,
    a hora e a data especial/dica da semana; a Hoje mostra a mesma sugestão num
    cartão "Sugestão do assistente" (só nas empresas com o Assistente ligado).
    O texto é igual para todos no mesmo período (sem dado pessoal), fica em
    cache por período (uma chamada à API por período por worker) e não conta no
    limite diário. Sem resposta da API → 503 e nenhum cartão. Enquanto espera,
    a conversa mostra "digitando" (três pontos animados; parados com
    movimento reduzido) e a resposta aparece aos poucos; itens "• " ficam um
    por linha.

INVARIANTES
Isolamento e autorização no servidor; nada de dado de saúde ou identificação
para fora; sem gravação de conversa; gestor não vê nada do chat.

DECISÕES
- Groq com `openai/gpt-oss-120b` (Marcus testou e preferiu à Kyora local).
  Endpoint compatível com OpenAI: `ASSISTANT_API_URL` pode apontar para um
  servidor próprio (Ollama) no futuro sem mudar o código.
- Exceção à regra "nada na tela menciona IA" (spec 15): aqui a pessoa precisa
  saber que fala com uma IA.
- Contrato do Groq: sem retenção por padrão, exceto registros de abuso por até
  30 dias; ligar o Zero Data Retention no console.

BLOQUEADO (antes de ligar para empresas clientes)
- Política de privacidade com o assistente (envio ao Groq, fora do Brasil) e,
  idealmente, revisão jurídica; aprovação da Quality Life.

FORA DO ESCOPO
Histórico salvo; respostas personalizadas com dados da pessoa; voz.

RISCO
R2 (dado que sai para terceiro; migração aditiva `wellbeing.0006_assistant_usage`).
