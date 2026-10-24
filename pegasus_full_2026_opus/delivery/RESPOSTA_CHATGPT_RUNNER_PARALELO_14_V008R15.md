# PEGASUS FULL 2026 — Devolução V008R15 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 24/10/2026

## 1. Objeto

Atendo à **missão de convergência integrada**: a auditoria preparatória profunda da origem sobre o candidato R14 (`PACKAGE_INTEGRITY_R14=PASS`; `MANIFEST=2955/2955`) pediu um **único candidato definitivo** que tratasse a implementação como sistema completo, não mais uma versão que só resolvesse o último achado. Esta R15 corrige internamente, por **famílias causais e classes de falha**, todas as deficiências materialmente demonstráveis no escopo autorizado, qualifica a integração e congela os bytes vinculados por hash. Preserva os PASS válidos (R9 23/23 `MET`; F01–F04; R11-ORIGIN-01/02/03; R12-ORIGIN-01/02; R13-ORIGIN-01). V003, backend de census e fronteiras econômicas intocados. Não li, baixei nem revalidei política/MASTER/HEAD.

## 2. Convergência por família causal (com controle negativo em cada uma)

- **A01 — nenhuma exceção pós-spawn encerra a custódia com a árvore viva.** `Supervision` é máquina de estados; toda chamada pós-spawn em `_guard`; `request_stop` estruturado (helper nonzero/timeout mantém o hold); `observe_tree` tri-estado (`UNKNOWN` nunca libera); `close()` só com árvore **VERIFICADA vazia** (duas observações). Controles: `SupervisionCustodyExceptions` (stop levanta/estruturado falho/observe levanta/telemetria corrompida/revalidate levanta → sempre `closed_while_live==0`), `TreeVerifiedEmpty`, mutantes `tree_verified_empty_accepts_single`, `start_failure_rolls_back_running_child`, `owner_release_plan_releases_without_clear`.
- **A02 — sem falsa completude de USN.** `usn_scan_coverage` (pura) + `w04_verdict` exigindo a prova de cobertura. Controles: `UsnScanCoverage` (progressão/EOF/IOCTL/malformado/versão/FRN128/ordem), `W04UsnCoverageProof`, mutantes `usn_coverage_accepts_nonprogress`, `w04_ignores_usn_coverage_short`.
- **A03 — evidência terminal vinculada à tentativa.** `terminal_evidence_verdict` + exigência em `completion_verdict`/`safestop_verdict`. Controles: `TerminalEvidence`, `CompletionTerminalRequired`, Q17, mutantes `completion_ignores_terminal_evidence`, `terminal_accepts_stale_run_instance`.
- **A04 — recibo estruturado em todo desfecho.** `persist_run_receipt` (canônico; nunca levanta) + `main()` JSON `FAIL_TECHNICAL` + `PrespawnBlocked=2`. Controles: `ExitClassification` (incl. `test_main_technical_failure_exits_3_not_1`), mutante `technical_failure_exits_zero`.
- **INT + C4 — fronteiras/exceções e isolamento.** `start_failure_disposition` (rollback só do suspenso que nunca executou), `owner_disposition_verdict`/`owner_release_plan` (liberação só com `KILL_ON_JOB_CLOSE` removido), `_load_admission` selado + `plan_isolation_verdict`. Controles: `StartFailureDisposition`, `OwnerDispositionAndRelease`, `AdmissionSealed`, `PlanIsolation`, mutantes `admission_accepts_unsealed_module`, `plan_isolation_allows_economic_entry`.

Fechamento vinculado aos bytes em `receipts/V008/offline_final/r15_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R15.json` (`all_closed=true`: A01, A02, A03, A04, INT-FAMILY, C4-ISOLATION, PRIOR_PRESERVED) + `FALSE_COMPLETENESS_SEARCH_V008R15.json` (`NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED`). O probe de convergência confirma `all_safe` nos bytes R15 e `UNSAFE` (A01) reproduzido nos bytes R14.

## 3. Qualificação e preservação

Offline sobre os bytes finais: cadeia V003 **19/19**; qualificação integrada **18 PASS** (incl. Q16 e Q17) **+ 2 SKIPPED_NON_NATIVE**; unit **156/156**; mutantes do supervisor **41/41**; fronteira do bootstrap **20/20** + **8/8**. A campanha nativa R9 (23/23, `MET`, bytes `2C3F39EB…`), a auditoria R10=FAIL (F01–F04) e as correções R10/R11/R12/R13/R14 estão preservadas em `native_campaign_r9/`, `r10_boundary_fix/`, `r11_audit_fixes/`, `r12_origin_fixes/`, `r13_origin_fixes/` e `r14_origin_fixes/`. Não reconstruí a base, não fragmentei, não revalidei MASTER/HEAD e não repeti indiscriminadamente os 23 testes nativos.

## 4. Candidato definitivo (V008R15)

| Artefato | SHA-256 |
|---|---|
| ZIP (2.963 membros, 87.487.724 bytes) | `75EE96E700408876B4F5509DB2B6397517AE993C29A05BA713480D912C5A1490` |
| Manifesto final (M2) | `ABCEB1E67F0242127211B15B7DCA6DAC1D17C07F24A82A4D9136AEB5B7E380EC` |
| Bootstrap PS 5.1 | `036193A34F931F6C083AB64E2CF74FC058DAD79C4C8CA3E76C35680E1DE3E150` |

tested=packaged=delivered: M1 `945481B3…` → M2 `ABCEB1E6…` só +18 arquivos de evidência; extrato reconfere 2.962/2.962; verify e 156/156 unit sobre os bytes entregues. Supersede V008R14.

## 5. O que fica com a origem (eixos separados, nenhum inferido de outro)

- **ENGINEERING_COMPLETE:** sim — A01–A04 + família INT + C4-ISOLATION fechados; F01–F04 e R11/R12/R13-ORIGIN preservados.
- **NATIVE_QUALIFICATION:** `MET` sobre os bytes R9; re-execução nativa confirmatória sobre os bytes R15 pendente.
- **CANDIDATE_COMPLETENESS:** engenharia completa; a **selagem formal** `=PASS` é da origem.
- **INDEPENDENT_AUDIT:** **pendente** — reauditoria formal independente pelo mesmo auditor/thread.
- **RUN_RELEASED:** `NO` — G0 desligado; nenhuma corrida liberada.

Sob autorização e salvaguardas, com processos sintéticos: a **prova nativa dirigida** das propriedades A01/A02/A03 e de `KILL_ON_JOB_CLOSE` ativo/removido conforme `WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R15.md`. Fronteiras preservadas: `G4=FROZEN · QS4=NO · PHASE_B/C_ECONOMIC=NO · FULL_ECONOMIC=NO · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · Install/Rollback não executados`. Não iniciei auditoria formal, instalação produtiva, QS4, Phase B/C econômicas nem FULL econômico. Não revalidei nem consultei política/MASTER/HEAD; a custódia permanece na origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
