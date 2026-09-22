# Regras permanentes

- Leia `docs/QUALITY_LIFE_V2.md` e inspecione o código afetado antes de editar.
- Preserve a identidade visual, os mascotes e os assets aprovados; migre-os seletivamente.
- Faça mudanças pequenas e delimitadas, sem refatoração oportunista.
- O backend é a fonte de verdade. O scoring deve ser determinístico, testável e nunca alterado por IA.
- Garanta isolamento entre empresas e autorização server-side em todo acesso a dados.
- Não exponha dados individuais ou sensíveis à diretoria; use somente agregados autorizados.
- Desenvolva mobile-first e não introduza scroll horizontal em `390x844`.
- Adicione ou atualize testes para todo comportamento alterado.
- Não faça deploy sem solicitação explícita.
- Nunca adicione secrets ao repositório; use variáveis de ambiente.
