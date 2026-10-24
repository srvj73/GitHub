# Matriz de invariantes × classes de falha — V008R15

Cobertura por **invariante e classe de falha**, não por bug. Cada linha nomeia a guarda, a prova
positiva, o controle negativo e o mutante que a mata. Todos os testes correm offline sobre os
bytes finais; o que depende de Win32 está marcado e remetido ao protocolo dirigido.

## Invariantes de custódia / NO_KILL (C1)

| Invariante | Guarda (função/estado) | Negativo (teste) | Mutante |
|---|---|---|---|
| I1 custódia só libera com árvore VERIFICADA vazia | `tree_verified_empty` (2 observações) | `TreeVerifiedEmpty.test_*` | `tree_verified_empty_accepts_single` |
| I2 nenhuma exceção pós-spawn sai de run() | `Supervision._guard` + `_run_spawned` | `SupervisionCustodyExceptions.test_{stop_raises,observe_raises,revalidate_raises,eta_raises,corrupt_status}` | — (integração) |
| custodiante vivo na reservada; nunca finaliza árvore viva | `reconcile_step_action` | `ReconcileStepAction.*` | `reconcile_step_reserved_finalizes_live_tree` |
| decisão de hold pura nunca mata/abandona | `custody_finalize_decision` | `CustodyFinalizeDecision.*` | `custody_finalize_abandons_live_tree` |
| observação que falha é UNKNOWN, nunca vazio | `WindowsJobCustody.observe_tree` / `PosixCustody.observe_tree` | `SupervisionCustodyExceptions.test_observe_raises_holds` | — (nativo/integração) |
| close() nunca fecha handle com árvore viva | `job_close_plan` + `close` | `JobClosePlan.*`, `JobCloseNoKill.*` | `job_close_plan_closes_live_tree` |
| start: rollback só do próprio filho suspenso que nunca executou | `start_failure_disposition` | `StartFailureDisposition.*` | `start_failure_rolls_back_running_child` |
| disposição do titular só com KILL_ON_JOB_CLOSE removido | `owner_disposition_verdict` + `owner_release_plan` | `OwnerDisposition.*`, `OwnerReleasePlan.*` | `owner_release_plan_releases_without_clear` |
| SAFE_STOP não entregue é erro persistido, não saída | `request_stop` estruturado + loop | `SupervisionCustodyExceptions.test_stop_delivery_failure_holds` | — (integração) |

## Invariantes USN / W04 (C2)

| Invariante | Guarda | Negativo | Mutante |
|---|---|---|---|
| cobertura só completa até end_usn com cursor progressivo | `usn_scan_coverage` | `UsnScanCoverage.test_{nonprogress,eof_before_end,ioctl_fail,malformed,version,frn128,complete,order}` | `usn_coverage_accepts_nonprogress` |
| w04 exige a PROVA de cobertura (não só o booleano) | `w04_verdict` (bloco `coverage`) | `W04Verdict.test_usn_coverage_absent/short` | `w04_ignores_usn_coverage_proof` |
| disarm nunca levanta; falha → W04 BLOCKED | `W04NativeLease.disarm` | (nativo/dirigido) + `W04Verdict.test_usn_incomplete` | — (nativo) |

## Invariantes de evidência terminal / exit (C3)

| Invariante | Guarda | Negativo | Mutante |
|---|---|---|---|
| conclusão exige evidência terminal vinculada à tentativa | `terminal_evidence_verdict` + `completion_verdict` | `TerminalEvidence.*`, `SafeStopCompletion.test_completion_requires_terminal` | `completion_ignores_terminal_evidence` |
| STATUS de outra tentativa (stale) não vale | `terminal_evidence_verdict` (run_instance/pid) | `TerminalEvidence.test_stale_rejected/foreign_pid_rejected` | `terminal_accepts_stale_run_instance` |
| conclusão exige linhagem e JIT provados | `completion_verdict` (lineage/jit) | `TerminalEvidence.test_completion_requires_lineage_jit` | `completion_ignores_lineage` |
| recibo estruturado em todo desfecho; 0/130 só com recibo | `_run_supervised` + `persist_run_receipt` | `NativeNegativesFreshProcess` (já) + integração A04 | — (integração) |
| falha técnica após spawn = 3 com causa; bloqueio pré-spawn = 2 | `PrespawnBlocked` + `_run_supervised` | `ExitClassification.*` | `absent_exit_classified_pass` (já) |

## Invariantes de integração FULL / isolamento (C4)

| Invariante | Guarda | Negativo | Mutante |
|---|---|---|---|
| bloqueio econômico terminal e triplo | `make_run_plan`/`DefaultReleaseAdmission`/`_run_supervised` | Q13a/b/c | `run_plan_allows_economic`, `run_supervised_runs_economic`, `default_admission_returns_plan` (já) |
| `--admission` só aceita o módulo sintético selado | `_load_admission` (caminho + SHA do manifesto) | `AdmissionSealed.*` | `admission_accepts_unsealed_module` |
| argv do plano não econômico não aponta runtime econômico | `plan_isolation_verdict` | `PlanIsolation.*` | `plan_isolation_allows_economic_entry` |

**Provas Windows dirigidas (não offline):** efetividade Win32 de `observe_tree`/`request_stop`/`close` em árvore viva com `KILL_ON_JOB_CLOSE` ativo e removido; leitura USN real com cursor não progressivo e EOF; identidade do neto. Protocolo em `WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R15.md`, com processos sintéticos, hash-bound, sem instalação, sem kill não autorizado.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
