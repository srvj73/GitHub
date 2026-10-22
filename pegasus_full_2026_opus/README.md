# PEGASUS FULL 2026 — Engenharia Final V008R8

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R8_20261022.zip` (SHA-256 `17A9FB12…`, 2.946 membros, manifesto `3BA34A1D…`), bootstrap PS 5.1 com pins (`F499D48C…`), recibos externos e `00_START_HERE_PEGASUS_V008R8.md`. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R8.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r7/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r8.py`, `ps_parse_check.ps1`.
- `probes/` — `pending_causal_probe_v008.py`.

## Convergência das campanhas nativas (R2 → R8)

Cada campanha no Windows do titular, com a fronteira de exit honesta, revelou o próximo defeito físico real — não reproduzível offline — e foi corrigida:

- **R2** fronteira de exit validada nativa (S00/S03 MATCH).
- **R3** ciclo de vida do handle do Job: Q01/Q02 PASS nativos.
- **R4** SAFE_STOP por plataforma: Q01–Q09 e Q12 PASS; parou em Q12b.
- **R5** diagnóstico: reentrega do Ctrl+C não recupera o encrave.
- **R6** janela segura de entrega (ACTIVE>0): **22/23 casos nativos PASS** (Q01–Q15 + W04 Q10a–f, incl. Q03/Q04 SAFE_STOP/retomada e Q12b). Resíduo: Q11 breakaway.
- **R7** contenção de breakaway: o proxy do `CreateProcess` (não lançou ⇒ escapou) é incorreto no Win8+ (jobs aninhados). Q11 passa a verificar a **contenção real** — o PID do neto permanece em `job_pids` (contabilidade do kernel do Job) — e só falha no escape real. `Supervision.run` expõe `job_pids`.
- **R8 (esta entrega)** robustez do census de corroboração: na R7, Q10a (que passara na R6) ficou `BLOCKED` por `CENSUS_TRUNCATED` intermitente, com a prova do kernel íntegra. O census passa a ter até 3 tentativas; se todas truncarem, o W04 continua bloqueando (fail-closed inalterado).

**tested=packaged=delivered:** M1 (`9B5F91DC…`) → M2 (`3BA34A1D…`) difere só por 31 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.945/2.945 arquivos; verify e 71/71 unit sobre os bytes entregues. Offline: mutantes do supervisor 24/24, fronteira do bootstrap 20/20 + 8/8, cadeia V003 19/19, qualificação 16/16 PASS + 2 SKIPPED_NON_NATIVE.

Supersede o V008R7 (`FDFCEDB5…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`CANDIDATE_COMPLETENESS=NOT_PASS` — único bloqueio externo: re-execução nativa que confirme Q10a–f e Q11 na mesma execução (23/23).

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
