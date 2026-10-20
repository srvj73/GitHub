# CDT20 — PRE-G06 integrado — relatório do implementador (20/10/2026)

Papel: implementador técnico. **Não** é B06 nem homologação. Política normativa não consultada (custódia exclusiva da origem; `ORIGEM_CUSTODIA_NAO_CONSUMIR/` não foi aberto nem hasheado).

## 1. Entradas conferidas

| Item | SHA-256 | Resultado |
|---|---|---|
| Parte 1 | `5B3EB13E…0D48` | confere com a testemunha |
| Parte 2 | `6373D867…0971` | confere com a testemunha |
| Membros técnicos da Parte 1 (14) | manifesto do handoff | 14/14 OK |
| Candidato G0 bloqueado | `B91EEF39…39C3` | OK; interno `40FB01F4…07D2`, 303 membros |

## 2. Causa da falha do G0 de 20/10 — análise

- A versão predecessora de `test_cdt19_final_transport_closure.py` (SHA `65FF1BB9…`, 15 testes) **passou nativamente** na campanha de 12h19 (`LOGS/DELTA_test_cdt19_final_transport_closure.py.log`, `OK`).
- O sucessor muda apenas o fixture e acrescenta 5 regressões **puramente em memória** sobre `validate()`; o código exercitado pelas classes de sistema de arquivos (`ElevenArchive`, `ReturnClosure`) é byte-idêntico ao que passou.
- Logo, a diferença causal disponível é o **contexto de execução**: o G0 rodava `python -E -B <teste>` no ambiente do operador (TEMP padrão do usuário, cwd herdado, user-site ativo); a campanha roda o mesmo teste com `-I`, TEMP próprio canônico e `LOCALAPPDATA`/`USERPROFILE` normalizados por `GetLongPathNameW`. As guardas de cadeia de caminho (`assert_no_link_chain`, pinagem de ancestrais, comparação de caminho final do handle) são sensíveis exatamente a isso.
- **Não declaro a causa exata como fato**: o log primário não foi anexado. O novo lançador o coleta somente-leitura e o novo G0 reexecuta o contexto antigo como diagnóstico não bloqueante — a causa fica provada no mesmo retorno, sem rodada extra.

## 3. Correções integradas (sucessor `6C952BD9…C064`, 304 membros)

| Arquivo | Mudança |
|---|---|
| `G0_CDT20_PRE_G06.py` + `G0_SUITE_RUNNER.py` (transporte) | G0 qualifica **todas as 13 suítes DELTA** no contexto da campanha; traceback primário de cada falha no console e no recibo; continua após falha para reunir todas; diagnóstico do contexto antigo; tested==packaged re-hasheado após as suítes |
| `PRE_G06_COMPLETENESS.py` | quatro achados pré-B06 verificados fisicamente nos logs nativos selados (`FINDINGS`, `FOUR_PRE_B06_FINDINGS.json`); `REQUIRED_DELTA` único compartilhado com o G0 |
| `FULL_G5_COMPLETE_PROOF_GATE.py` | limite do retorno nativo 512 MiB → 1,5 GiB (constante; continua aplicado). G3/G6 sozinho tinha 197 MB em 12h19 e a leitura final nunca havia rodado com retorno completo |
| `PRE_G06_CAMPAIGN.py` | heartbeat ≤5 s com `ACTIVE_TEST`, `UNIT_ELAPSED_S`, `PROGRESS_COMMITTED`, ETA por linha de base nativa (UNKNOWN quando excedida ou inexistente), `ETA_AS_OF`; traceback primário no console; tamanho do retorno antes da leitura final; nova suíte em `EXTRA` |
| `RUN_CDT20_R08Q1.py` (transporte) | supervisor a cada 10 s com contagem de recibos; bloqueadores do `ENGINEERING_RESULT` no console |
| `test_cdt20_pre_g06_integrated_closure.py` (novo, 12 testes) e `test_cdt19_final_completeness_contract.py` (6 testes) | positivos e negativos dos itens acima |

Núcleo `tickstore_serial_runner.py` congelado (`749EEC5D…`). Consumidores, G3/G6, SAFE_STOP e MULTIWORK: código byte-idêntico ao que passou nativamente em 12h19.

## 4. Qualificação no sandbox (Linux, **não nativa**)

- Regressão completa sobre os bytes **extraídos do pacote**: nenhuma falha nova face ao pai; as falhas preexistentes (POSIX, fora do conjunto da campanha) são idênticas.
- Cadeia pós-G3 (projeção → `verify_native_campaign` → `completeness.close`) executada sobre os **bytes reais de 12h19** revinculados apenas em scratch: PASS; quatro achados PASS contra os logs nativos reais.
- G0: 13/13 suítes; 11 controles negativos do G0; 12 do bootstrap.
- Lançador: lint PS 5.1 PASS; 11 cenários funcionais em pwsh 7.4 (sucesso, G0 recusando não-Windows, SHA adulterado, transporte ausente, membro adulterado, membro inseguro, membro extra, coleta somente-leitura, reentrância, SAFE_STOP 130, saída 0 sem recibo).

## 5. O que falta (exige o Windows do titular)

Uma execução do lançador integrado. Até o retorno: `EXECUTABLE_DELIVERY_READY=NOT_PROVEN`, `TARGET_RUNTIME_PENDING`, `PRE_G06=NOT_COMPLETE`. `B06/B07/D4-D5 produtivos/canário/FULL=NOT_STARTED`; `NOT_TESTED_PHYSICAL_POWERLOSS`.
