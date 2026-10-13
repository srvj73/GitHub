# R9 FULL_SERIAL RELEASE CANDIDATE RC1

## Release candidate RC1

- Active identity changed to TICKSTORE_SERIAL_RUNNER_V001R9_FULL_SERIAL_RELEASE_RC1.
- Enabled the package FULL_SERIAL capability only for --mode FULL_SERIAL; the historical
  full-history capability remains false and its route remains blocked.
- Required an explicit owner-gate path and an independently supplied trusted 64-hex SHA256
  before any source, destination or ledger access. Complete exact gate binding validation
  occurs before dispatch to the unchanged FULL_SERIAL engine.
- Updated the gate template only for the RC1 runner identity. It remains authorized=false;
  release-dependent and machine-specific fields remain null. No authorized gate or trusted
  digest is included, and no gate discovery, generator or fallback was added.
- Updated the R9 tests and static scanner for RC1 identity, capability, fail-closed gate
  admission, owner-gate-before-dispatch ordering, launcher parameters and package gate rules.
- Updated the launcher comment for RC1; its six mandatory parameters remain unchanged.

FULL_SERIAL_CAPABILITY_IN_RELEASE_CANDIDATE=YES
OWNER_AUTHORIZATION_REQUIRED=YES
AUTHORIZED_GATE_INCLUDED=NO
FULL_HISTORY_EXECUTION_AUTHORIZED=NO
AUTOCPU_AUTHORIZED=NO
CSV_DELETION_AUTHORIZED=NO

No R8 transaction-core, final-seal or reconciliation behavior changed. No validation command,
runner, launcher, pilot, FULL execution, CSV access, hash generation or Git mutation was run.
RC1 is for independent audit only; its package capability is not owner authorization. Real
history execution remains prohibited pending the RC audit, final runner/spec hashes, real
path and volume capture, owner-local authorized gate creation outside the package, separate
gate-SHA256 transmission and final pre-execution audit.

## Preparation history

- The prior preparation identity was TICKSTORE_SERIAL_RUNNER_V001R9_FULL_SERIAL_PREP.
- Added the then hard-blocked FULL_SERIAL entry point and PowerShell launcher.
- Added sealed full-plan validation, exact sequence/plan serialization and structured
  external gate binding with an independently supplied gate digest.
- Extracted the three operations inside the R8 run_one_day lock into
  _run_day_already_locked: verify_full, reconcile_or_build, verify_full. No transaction
  algorithm, journal schema/state, publication, recovery or day-status behavior changed.
- Added Windows month-scoped source pins with exactly two whole-month hashes during
  monthly processing; day publication boundaries check path and retained-handle identity.
  The remediation below adds a separate final global source seal.
- Added one invocation-wide writer lock, progress, controlled Ctrl+C, deterministic restart
  through R8 journal/reuse behavior, and final read-only global reconciliation.
- Added exact certificate-bound compatibility for the two R8 LOW/HIGH final pairs only.
- Added synthetic R9 tests and a bounded static prohibition scanner for owner-local use.
- Existing tests and all frozen seed files are unchanged. BASELINE_R8 and Gate B staging
  are untouched. No authorized owner gate, commit, push or FULL authorization was created.

All validation commands remain unexecuted in Codex. This changelog is not a release verdict.

## Directed preaudit remediation V001

- MAJOR-01 / FULL_INVOCATION_SOURCE_IDENTITY: added FULL_SOURCE_FINAL_SEAL after all
  months. Canonical month sources are securely opened in order, fully rehashed, and
  compared with captured normalized path, size, mtime and file identity. Lightweight
  write/delete-denying fds stay open through reconciliation and lock release. V003 below
  moves their successful close before terminal PASS. The existing two hashes per monthly
  processing pass remain; the final seal adds exactly one hash per successful month.
  Tests cover post-month mutation, same-content replacement, changed size/SHA/mtime,
  opening failures, Ctrl+C, retained handles at the terminal boundary and cleanup.
- MAJOR-02 / FINAL_RECONCILIATION_TOCTOU: added the second terminal inventory, a final
  global-manifest partial-file check and the third manifest comparison while locked.
  Tests inject a late container and manifest partial after the first inventory.
- MINOR-01 / OWNER GATE TEMPLATE: added FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json
  with the exact R9 field set, authorized=false and null release/machine placeholders.
  The frozen template remains unchanged; spec, README and scanner reference the new one.
- MINOR-02 / LOCAL WHITESPACE CHECK: README now prescribes complete-file no-index
  whitespace checks covering new untracked R9 files, without staging or committing.

No R8 transaction-core behavior or frozen seed file was changed by this remediation.
Tests, scanners and validation commands remained unexecuted in that preparation revision,
where FULL_SERIAL was hard blocked.

## Directed final remediation V003

- NEW_MAJOR_03 / FINAL_SEAL_CLEANUP_FALSE_PASS: moved the successful final-seal close
  before TICKSTORE_FULL_SERIAL_STATUS=PASS and return 0. The exact terminal order is now
  global reconciliation, writer-lock release, seal.verify_bindings, seal.close, PASS.
- Failed descriptors remain registered for a residual finally cleanup. That cleanup tries
  every remaining descriptor and preserves the original close failure or KeyboardInterrupt.
- Added test_final_seal_close_failure_never_emits_global_pass and updated the descriptor
  lifetime test and static scanner to enforce the new completion boundary.

No R8 transaction-core behavior changed. No validation command was executed in that
remediation. AUTOCPU and CSV deletion remain absent.


## FULL MULTIWORK RC2R1 — worker ceiling

- `DEFAULT_MAX_WORKERS`: 12 -> 22.
- AUTO CPU reserve: 4 -> 2 logical CPUs.
- RAM target remains 60%; AUTO may choose fewer than 22 when memory budget requires it.
- RC1 transactional core remains frozen byte-for-byte.


## FULL MULTIWORK RC2R2 — production hardening

- wrapper schema bumped to `TICKSTORE_R9_FULL_MULTIWORK_RC2R2_V001`;
- scratch namespace bumped to `FULL_MULTIWORK_RC2R2`;
- explicit worker counts now obey CPU and RAM budgets;
- dead clean worker without terminal event blocks instead of causing an infinite wait;
- stop/error paths wait cooperatively for children before parent releases pins/lock;
- launcher no longer exits the caller PowerShell host;
- Windows preflight now includes a true 22-process concurrent pin/build/resume synthetic smoke.


RC2R3 (25/09/2026): fecha `JOURNAL_ORACLE_MISMATCH` na ponte de recuperação de transação canônica interrompida pelo FULL_SERIAL RC1. A recuperação passa a usar os `full_release_materials()` ids exatos que criaram o journal; `run_one_day()` genérico é proibido nessa ponte. Core RC1 permanece byte a byte congelado.

## FULL MULTIWORK RC3 — productive concurrency redesign (25/09/2026)

- supersedes RC2R3 for production after real-run utilization evidence showed process-count concurrency without adequate productive concurrency;
- removes worker `FullSerialMonth` pre-hash from ordinary multiwork;
- adds `StreamingMonthSource`: source pin, SHA-256, scan, parse and build share one forward-only source pass;
- removes per-day `DAY_READY -> ACK` coordinator barrier;
- canonical publication is deferred until `MONTH_VERIFIED` proves the complete monthly SHA-256;
- parent source pins stay open through final read-only reconciliation, avoiding a second full-source hash pass;
- preserves compatible RC2R3 scratch journals in place and blocks scratch revision conflicts;
- adds explicit `BUILDING/SCANNING/LAUNCHING`, `SOURCE_MIB_S`, `SOURCE_PCT`, and scan ETA telemetry;
- adds 180-second structured-productivity stall gate;
- core RC1 remains byte-for-byte frozen.
