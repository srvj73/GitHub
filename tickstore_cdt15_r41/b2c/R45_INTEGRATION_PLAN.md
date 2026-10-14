# Plano de integração R45: B2C (fixtures aprovadas) + B2D + B07 nos bytes do candidato

**Estado:** SOURCE_ONLY. Não integrado em `source/candidate`; os bytes R44 (FINAL `0FBB6C36…`) foram preservados para o pacote G5 e para o delta R44D.
**Pré-condição:** o retorno R44D (R44-DROOT-01) deve dar PASS antes de construir o R45. Nenhum sucessor é disparado às cegas.

## Conteúdo do delta de código (runtime)
- B2C (`b2c/candidate_overlay`, 10 arquivos, `R44_B2C_SOURCE_ONLY.diff`):
  - `POLICY_CAPTURE_BINDING.py` (novo);
  - TRANSACTION, PREP, BOOTSTRAP, FULL_STAGE_CONTINUATION, FULL_INSTANCE_PREPARE, FULL_RUNNER e RUN_TICKSTORE_FULL.ps1;
  - wrapper efetivo e `FIRST_ADMISSION_BINDING.json` (regenerado de forma determinística).
- **Excluído do B2C:** a edição de `full/tickstore_serial_runner.py`. O núcleo RC1 é congelado (`D3A15572…`, `CORE_RC1_FROZEN`) e não pode ser alterado. A revogação dos caminhos legados FULL_SERIAL/piloto/full-history, que ainda aceitam gate humano se invocados manualmente fora do FULL_RUNNER, fica como **risco residual para decisão da origem**: quarentena dos lançadores legados no empacotamento ou aceitação como material histórico inalcançável pelo caminho FULL.
- B2D: `control/ORIGIN_DECISION_BINDER.py`.
- B07: `control/B07_TECHNICAL_PRODUCER.py` e `b07/B07_CHECK_RUNNERS.py`. Não são executados antes de B06 independente PASS.

## Fixtures contratuais (aprovadas byte a byte pela origem; não reeditar)
| Alvo na árvore R3 | Pai | Derivado aprovado |
|---|---|---|
| engineering/tests_full_lifecycle.py (B1A) | EE30AA93… | 29981D15… |
| cdt15/tests_delta.py (B1B) | 67B41A04… | 2E95CADE… |
| engineering/test_first_admission_transaction.py (B2C) | original R3 | E74F3701…5A29 |
| engineering/test_bootstrap_contract.py (B2C) | original R3 | 40B396FC…5A24 |

## Prontidão medida (portátil, não é qualificação)
- 106/106 IDs portáteis na árvore mesclada (R44 + B2C + B2D + B07) com as quatro sobreposições (`EVIDENCE/R45_MERGED_PORTABLE_106.json`).
- Descoberta portátil dos testes do pacote: 272, OK (4 skips nativos). `test_full_multiwork` e `test_full_serial_r9` OK, e `static_multiwork_preaudit` PASS.
- Testes SOURCE_ONLY: B2C 19/19, B2D 11/11, B07 7/7, laboratório de queda física 9/9, admissão de sandbox 5/5.

## Qualificação nativa necessária (R45: o código muda, portanto nada é reaproveitado do R44)
1. Os 126 IDs sobre os novos bytes, com as quatro sobreposições aprovadas, elevado, com a admissão física de sandbox já incorporada ao driver e ao bootstrap (R44-DROOT-01).
2. As cinco provas G5 viáveis sobre os novos bytes (os recibos estão vinculados ao FINAL) e o POWERLOSS_EMULATED separado.
3. Provas específicas do B2C:
   - `verify_capture` com leituras nativas protegidas (Win32Store) sobre a captura R40 e uma reconciliação **emitida pela origem**;
   - negação de mutação da PolicyRoot enquanto ela é admitida;
   - drift: captura V38 histórica, extra file e reconciliação expirada;
   - bloqueio do D4 sem reconciliação vigente.
4. Os testes B2D, B07, do laboratório e de admissão como suítes nativas.
5. Em seguida: produtor G5 sobre o RETURN R45. G5 continua INCOMPLETE enquanto `CHECKPOINT_POWERLOSS_RECOVERY` estiver bloqueado (`PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED`).

## Pedido de insumo à origem para o R45
Um registro `TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001` real, emitido pela origem, com validade curta e SHA informado à parte. Ele só é necessário para a prova nativa do B2C. Sem ele, essa prova fica BLOCKED; o engenheiro não fabrica reconciliação.
