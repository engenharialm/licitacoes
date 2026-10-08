# Controle de Licitações — LM

Portal de licitações da LM Construtora: pavimentação asfáltica (com drenagem e terraplenagem quando vêm junto).

- **Atualizar do PNCP** busca as licitações de MG com propostas abertas (concorrências, pregões e dispensas) direto da API pública do PNCP e grava no Firebase do Controle LM (coleções `licitacoes` e `licitacoes_meta`).
- Cada licitação tem o botão **SIM / NÃO** de interesse; as marcadas com SIM vão para o controle (serviços e %, atestados, status, garantia, vencedora e desconto).
- **+ Nova licitação** cadastra concorrências privadas que não estão no PNCP.
- Abrir com `?local` no fim do endereço usa só o navegador atual, para testes, sem mexer nos dados da equipe.
