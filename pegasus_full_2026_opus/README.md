# PEGASUS FULL 2026 — Engenharia Final V008R13

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R13_20261023.zip` (SHA-256 `2643D628…`, 2.954 membros, manifesto `69C90D16…`), bootstrap PS 5.1 com pins (`5EE03C35…`), recibos externos, `00_START_HERE_PEGASUS_V008R13.md` e a atestação nativa R9 preservada. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R13.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r9/`, `r10_boundary_fix/`, `r11_audit_fixes/`, `r12_origin_fixes/`, `r13_origin_fixes/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r13.py`, `ps_parse_check.ps1`.

## V008R13 — correção da revisão preparatória da origem sobre a R12

A origem inspecionou os bytes R12 e apontou dois bloqueios materiais ainda abertos, ambos corrigidos fail-closed com controle negativo, preservando os avanços da R12 e os PASS anteriores (R9 23/23 `MET`; F01–F04 fechados na R11; R11-ORIGIN-01/02/03 fechados na R12; auditoria independente R10=FAIL preservada):

- **R12-ORIGIN-01** reter handles só até o encerramento do supervisor não é custódia durável → função pura `custody_finalize_decision` + reconciliação custódia-preservada de `Supervision.run`: com árvore viva, o custodiante **permanece VIVO supervisionando até `TREE_EMPTY`** (W04 + Job retidos por TODA a vida da árvore, drenagem cooperativa, NO_KILL, recuperação); produção sem prazo; só a qualificação limitada, ao esgotar `RECONCILE_HOLD_S`, emerge como decisão reservada à origem; nunca finaliza/abandona árvore viva.
- **R12-ORIGIN-02** identidade do neto não temporalmente vinculada → o próprio neto reporta o seu `(pid, creation_time)` via `GetProcessTimes` sobre si mesmo (programa sintético `_JOB_GRANDCHILD`); `grandchild_contained(gpid, gctime, job_idents)` exige esse par **independente** presente e **único** na observação independente do Job; divergência/ausência/ambiguidade recusam a contenção.

Fechamento em `receipts/V008/offline_final/r13_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R13.json`, `all_closed=true`, incl. F01–F04, R11-ORIGIN-01/02/03 e R12-ORIGIN-01/02). Regressões: `CustodyFinalizeDecision` (incl. `test_never_finalizes_live_tree`), `GrandchildContained` reescrita (match/divergente/sem-ctime/ambíguo/ausente).

**tested=packaged=delivered:** M1 (`AC6F6AB9…`) → M2 (`69C90D16…`) difere só por 16 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. Extrato reconfere 2.953/2.953; verify e **100/100** unit sobre os bytes entregues; mutantes do supervisor **31/31**; fronteira do bootstrap 20/20 + 8/8; cadeia V003 19/19; qualificação 17/17 PASS (incl. Q16) + 2 SKIPPED_NON_NATIVE.

Supersede o V008R12 (`EA17EDE3…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

Engenharia completa; auditoria R10 (F01–F04) e revisões da origem R11 (R11-ORIGIN-01/02/03) e R12 (R12-ORIGIN-01/02) fechadas; `native_completeness_evaluation=MET` sobre os bytes R9 (preservada). A reauditoria focal, a selagem formal de `CANDIDATE_COMPLETENESS=PASS`, a prova nativa dirigida (custódia durável/NO_KILL e identidade do neto em processos sintéticos) e o passo `-Mode Install` são do titular/origem. A custódia normativa MASTER/HEAD permanece exclusivamente com o ChatGPT de origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
