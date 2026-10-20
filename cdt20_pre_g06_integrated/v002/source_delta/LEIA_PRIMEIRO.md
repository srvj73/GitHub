# CDT20 — PRE-G06 integrado V002 — `CDT20_PRE_G06_INTEGRATED_SOURCE_V002_20261020.zip`

Papel: implementação técnica (não B06). Política normativa: custódia exclusiva da origem; não consultada.

## Origem da mudança

Autorização expressa do titular, emissor G5, em 20/10/2026 nesta conversa:

> "Confirmo: como titular e emissor G5, autorizo alterar o ORIGIN_DECISION_BINDER.py para aceitar declaração explícita do titular com qualquer data válida (EXPLICIT_OWNER_DECLARATION_CHAT_AAAAMMDD), mantendo os demais bloqueios, e gerar o pacote V002 com nova execução Windows."

O parecer técnico anterior (`NOT_DEFECT`) continua válido para o V001. Esta mudança é decisão de governança do titular, não correção de defeito.

## Identidades

- Pai: `CDT20_PRE_G06_INTEGRATED_SOURCE_20261020.zip`, `6C952BD9…C064`. Tem PASS nativo: run `R08_Q1_20261020145036_6735ed63d3a4`, retorno `9B565CF3…F205`, 38 commits, 479 referências. Esses resultados ficam preservados sob a identidade do pai e **não são revinculados** ao V002.
- V002: ver `CDT20_R08Q1_WITNESS.json` (304 membros; núcleo `749EEC5D…` congelado).

## Delta (2 membros)

1. `candidate/control/ORIGIN_DECISION_BINDER.py`: `issuer_basis` aceita `EXPLICIT_OWNER_DECLARATION_CHAT_AAAAMMDD` com data de calendário válida e somente dígitos ASCII. Antes, só `…_20261016` era aceito.
   - **Mantidos:** recusa de rótulos arbitrários; `owner_is_independent_b06_auditor is False`; emissor `OWNER_RELEASE_AUTHORITY`; implementador nunca emissor; sem OWNER_GATE administrativo; vínculos de hash atuais (código, pacote final, instância, política); SHA da decisão por segundo canal; checks; evidências; bloqueadores vazios.
2. `tests/test_cdt20_pre_g06_integrated_closure.py`: +5 testes (17 no total). Cobrem positivo atual e histórico, 11 bases malformadas, guardas inalteradas e pacote antigo/pino errado.

## Execução

Somente pelo lançador `RUN_CDT20_PRE_G06_INTEGRATED_V002_20261020.ps1`, na mesma pasta deste ZIP. Uma nova campanha nativa é necessária porque o binder está vinculado por hash ao pacote e à evidência FINAL_G5.

`EXECUTABLE_DELIVERY_READY=NOT_PROVEN` até o retorno nativo do V002. `G5=NOT_ISSUED` · `B06=NOT_STARTED` · `FULL=NOT_STARTED` · `NOT_TESTED_PHYSICAL_POWERLOSS`.
