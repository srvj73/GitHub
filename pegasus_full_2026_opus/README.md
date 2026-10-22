# PEGASUS FULL 2026 — Engenharia Final V008R7

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R7_20261022.zip` (SHA-256 `FDFCEDB5…`, 2.947 membros, manifesto `055A9276…`), bootstrap PS 5.1 com pins (`D9079913…`), recibos externos e `00_START_HERE_PEGASUS_V008R7.md`. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R7.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r6/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r7.py`, `ps_parse_check.ps1`.
- `probes/` — `pending_causal_probe_v008.py`.

## Convergência das campanhas nativas (R2 → R7)

Cada campanha no Windows do titular, com a fronteira de exit honesta, revelou o próximo defeito físico real — não reproduzível offline — e foi corrigida:

- **R2** fronteira de exit validada nativa (S00/S03 MATCH).
- **R3** ciclo de vida do handle do Job: Q01/Q02 PASS nativos.
- **R4** SAFE_STOP por plataforma: Q01–Q09 e Q12 PASS; parou em Q12b.
- **R5** diagnóstico: reentrega do Ctrl+C não recupera o encrave.
- **R6** janela segura de entrega (ACTIVE>0): **22/23 casos nativos PASS** (Q01–Q15 + W04 Q10a–f, incl. Q03/Q04 SAFE_STOP/retomada e Q12b). Resíduo: Q11 breakaway.
- **R7 (esta entrega)** contenção de breakaway: o proxy do `CreateProcess` (não lançou ⇒ escapou) é incorreto no Win8+ (jobs aninhados). Q11 passa a verificar a **contenção real** — o PID do neto permanece em `job_pids` (contabilidade do kernel do Job) — e só falha no escape real. `Supervision.run` expõe `job_pids`.

**tested=packaged=delivered:** M1 (`1F841501…`) → M2 (`055A9276…`) difere só por 32 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato do ZIP reconfere 2.946/2.946 arquivos e roda 71/71 unit. Qualificação offline: unit 71/71, mutantes do supervisor 24/24, fronteira do bootstrap 20/20 + mutantes 8/8 (template inalterado `B5CECF29…`), cadeia V003 19/19 imutável, qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.

Supersede o V008R6 (`4B8DF8B9…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`CANDIDATE_COMPLETENESS=NOT_PASS` — único bloqueio externo: re-execução nativa que confirme Q11 → 23/23 nativos.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
