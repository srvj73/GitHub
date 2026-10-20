# CDT20 — PRE-G06 integrado — sucessor `CDT20_PRE_G06_INTEGRATED_SOURCE_20261020.zip`

Papel: implementação técnica (não B06). Política normativa: custódia exclusiva da origem; não consultada.

## Identidades

- Pai interno: `40FB01F4DDC152B77B0DD524A7D01239462310B4D97FDA487C0A6693E58207D2` (303 membros).
- Sucessor interno: ver `CDT20_R08Q1_WITNESS.json` (304 membros; núcleo `tickstore_serial_runner.py` congelado `749EEC5D…`).
- Retorno nativo histórico `4A339FE6…` (run `R08_Q1_20261020121927_07996cf20a1e`): 37 commits / 477 referências preservados sob a identidade original; **não revinculados**.

## O que mudou e por quê

1. **G0 (causa da falha de 20/10).** A mesma suíte `test_cdt19_final_transport_closure.py` (versão predecessora) passou nativamente na campanha de 12h19; as 5 regressões novas são puramente em memória. A diferença causal disponível é o contexto: o G0 anterior rodava `python -E -B <teste>` no ambiente do operador (TEMP padrão, cwd herdado, user-site ativo), enquanto a campanha roda com `-I`, TEMP próprio canônico e `LOCALAPPDATA`/`USERPROFILE` em caminho longo. O novo `G0_CDT20_PRE_G06.py` executa **todas as 13 suítes DELTA** pelo `G0_SUITE_RUNNER.py` no contexto da campanha, expõe no console o traceback primário de cada falha, roda uma vez o contexto antigo como **diagnóstico não bloqueante**, e o lançador coleta (somente leitura) o log G0 de 20/10. A causa exata daquela execução só fica comprovada com esses logs; não é afirmada como fato antes disso.
2. **Quatro achados pré-B06** (`STATE_RECREATION`, `CONFIG_TOCTOU`, `CONCURRENT_RECEIPT_OVERWRITE`, `FAILURE_AFTER_CHECKPOINT`): a completude deixa de aceitar a autodeclaração e passa a exigir, nos logs nativos selados, as regressões nominadas de cada achado (`PRE_G06_COMPLETENESS.FINDINGS`), gerando `FINAL_G5/FOUR_PRE_B06_FINDINGS.json`.
3. **Limite do retorno nativo** em `native_zip_members`: 512 MiB → 1,5 GiB descomprimidos (constante explícita; continua aplicado). O namespace G3/G6 sozinho tinha 197 MB em 12h19 e a leitura final nunca havia rodado com um retorno completo.
4. **Observabilidade**: heartbeat por unidade com `ACTIVE_TEST`, `UNIT_ELAPSED_S`, `PROGRESS_COMMITTED`, `UNIT_ETA_S`/`CAMPAIGN_ETA_S` baseados nas durações nativas de 12h19 (ETA `UNKNOWN` quando excedido ou sem base), `ETA_AS_OF`; supervisor a cada 10 s; traceback primário no console.
5. Nova suíte `test_cdt20_pre_g06_integrated_closure.py` (12 testes), exigida nativamente pela completude.

## Execução

Somente pelo lançador `RUN_CDT20_PRE_G06_INTEGRATED_20261020.ps1`, colocado na mesma pasta deste ZIP. Sem `cd`, sem extração manual.

`EXECUTABLE_DELIVERY_READY=NOT_PROVEN` até o retorno nativo. `B06=NOT_STARTED` · `FULL=NOT_STARTED` · `NOT_TESTED_PHYSICAL_POWERLOSS`.
