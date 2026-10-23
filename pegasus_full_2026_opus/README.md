# PEGASUS FULL 2026 — Engenharia Final V008R12

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R12_20261023.zip` (SHA-256 `EA17EDE3…`, 2.952 membros, manifesto `D49A54D8…`), bootstrap PS 5.1 com pins (`1A63EE3A…`), recibos externos, `00_START_HERE_PEGASUS_V008R12.md` e a atestação nativa R9 preservada. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R12.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r9/`, `r10_boundary_fix/`, `r11_audit_fixes/`, `r12_origin_fixes/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r12.py`, `ps_parse_check.ps1`.

## V008R12 — correção da revisão preparatória da origem sobre a R11

A origem inspecionou os bytes R11 e apontou três pontos ainda abertos, todos corrigidos fail-closed com controle negivo, preservando os PASS anteriores (R9 23/23 `MET`; F01–F04 fechados na R11; auditoria independente R10=FAIL preservada):

- **R11-ORIGIN-01** `close()` fechava o handle do Job com árvore viva antes do `raise` (kill podia disparar) e liberava W04 com o filho vivo → `job_close_plan`: com árvore viva o supervisor **nunca fecha o handle nem mata**; retém Job + W04; `close()` não levanta; decisão reservada à origem registrada.
- **R11-ORIGIN-02** Q11 casava por PID histórico → `grandchild_contained` exige `(pid, creation_time)` único e resolvido.
- **R11-ORIGIN-03** `cust.close()` não garantido em pré-spawn falho → `arm`/pré-spawn/`start` dentro do `try`; `finally: cust.close()` roda exatamente uma vez.

Fechamento em `receipts/V008/offline_final/r12_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R12.json`, `all_closed=true`, incl. F01–F04 e R11-ORIGIN-01/02/03). Regressões: `JobClosePlan`, `GrandchildContained`, `SupervisionPrespawnLifecycle`.

**tested=packaged=delivered:** M1 (`BEDEFC7A…`) → M2 (`D49A54D8…`) difere só por 16 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. Extrato reconfere 2.951/2.951; verify e **94/94** unit sobre os bytes entregues; mutantes do supervisor **30/30**; fronteira do bootstrap 20/20 + 8/8; cadeia V003 19/19; qualificação 17/17 PASS (incl. Q16) + 2 SKIPPED_NON_NATIVE.

Supersede o V008R11 (`DD1B3432…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

Engenharia completa; auditoria R10 (F01–F04) e revisão da origem R11 (R11-ORIGIN-01/02/03) fechadas; `native_completeness_evaluation=MET` sobre os bytes R9 (preservada). A reauditoria focal, a selagem formal de `CANDIDATE_COMPLETENESS=PASS`, a prova nativa dirigida de timeout/kill e o passo `-Mode Install` são do titular/origem. A custódia normativa MASTER/HEAD permanece exclusivamente com o ChatGPT de origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
