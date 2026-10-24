# PEGASUS FULL 2026 — Engenharia Final V008R15

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R15_20261023.zip` (SHA-256 `75EE96E700408876B4F5509DB2B6397517AE993C29A05BA713480D912C5A1490`, 2.963 membros, manifesto `ABCEB1E6…`), bootstrap PS 5.1 com pins (`036193A3…`), recibos externos, `00_START_HERE_PEGASUS_V008R15.md` e a atestação nativa R9 preservada. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R15.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/` incl. `INTERNAL_AUDIT_R15.md`, `INVARIANTS_AND_EXCEPTIONS_MATRIX_R15.md`, `WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R15.md`; `receipts/V008/` incl. `offline_final/native_campaign_r9/`, `r10_boundary_fix/`, `r11_audit_fixes/`, `r12_origin_fixes/`, `r13_origin_fixes/`, `r14_origin_fixes/`, `r15_origin_fixes/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r15.py`, `ps_parse_check.ps1`.

## V008R15 — convergência integrada única sobre a auditoria preparatória profunda da origem

A origem auditou profundamente o candidato R14 (`PACKAGE_INTEGRITY_R14=PASS`; `MANIFEST=2955/2955`) e exigiu **um único candidato definitivo** que tratasse a implementação como sistema completo e qualificasse a integração por **invariantes e classes de falha** — não mais uma versão por achado isolado. Esta R15 fecha, fail-closed e com controle negativo por família, as deficiências materialmente demonstráveis no escopo autorizado, preservando todos os PASS válidos (R9 23/23 `MET`; F01–F04; R11-ORIGIN-01/02/03; R12-ORIGIN-01/02; R13-ORIGIN-01):

- **A01 — nenhuma exceção pós-spawn encerra a custódia com a árvore viva.** `Supervision` é máquina de estados; toda chamada pós-spawn em `_guard`; `request_stop` estruturado; `observe_tree` tri-estado (`UNKNOWN` nunca libera); `close()` só com árvore **VERIFICADA vazia** (duas observações). `UNSAFE` reproduzido nos bytes R14; `all_safe` nos bytes R15.
- **A02 — sem falsa completude de USN.** `usn_scan_coverage` (pura) prova cobertura até `end_usn`; `w04_verdict` exige o bloco de prova, não só o booleano.
- **A03 — evidência terminal vinculada à tentativa.** `terminal_evidence_verdict` exigido em `completion_verdict`/`safestop_verdict` (caso Q17).
- **A04 — recibo estruturado em todo desfecho.** `persist_run_receipt` canônico; `main()` JSON `FAIL_TECHNICAL`; `PrespawnBlocked=2`.
- **INT + C4 — fronteiras/exceções e isolamento.** `start_failure_disposition` (rollback só do suspenso), `owner_release_plan` (liberação só com `KILL_ON_JOB_CLOSE` removido), `--admission` selado + `plan_isolation_verdict`.

Fechamento em `receipts/V008/offline_final/r15_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R15.json`, `all_closed=true`: A01, A02, A03, A04, INT-FAMILY, C4-ISOLATION, PRIOR_PRESERVED; `FALSE_COMPLETENESS_SEARCH_V008R15.json` = `NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED`). Regressões: `UsnScanCoverage`, `W04UsnCoverageProof`, `TerminalEvidence`, `CompletionTerminalRequired`, `SupervisionCustodyExceptions`, `TreeVerifiedEmpty`, `StartFailureDisposition`, `OwnerDispositionAndRelease`, `PlanIsolation`, `AdmissionSealed` + 9 mutantes R15.

**tested=packaged=delivered:** M1 (`945481B3…`) → M2 (`ABCEB1E6…`) difere só por 18 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. Extrato reconfere 2.962/2.962; verify e **156/156** unit sobre os bytes entregues; mutantes do supervisor **41/41**; fronteira do bootstrap 20/20 + 8/8; cadeia V003 19/19; qualificação **18 PASS** (incl. Q16, Q17) + 2 SKIPPED_NON_NATIVE; probe de convergência `all_safe` nos bytes finais.

Supersede o V008R14 (`012D4347…`). O payload V003 completo está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`
