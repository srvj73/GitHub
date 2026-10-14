# V002R23 — RC1R1 CORE RECERTIFICATION (ORIGIN DECISION OPTION A)

Parent package: TICKSTORE_V004R1_D4_RESUMABLE_V002R22
Parent package ZIP SHA256: 4BC28843012A059F65237E07780B79D158190A661B16FFD520861A3F092C3062
Parent 99_MANIFEST SHA256: 5199C7B03A442F0D33C1250E3E2A68A5A213377E012A902336502453CAAA18D6
(preserved byte-identical in `history/V002R22/99_MANIFEST_SHA256.json`)

Cause:
- R46 origin completeness review: LEGACY-ENTRY. The frozen RC1 core
  (D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0) still accepted, through its
  direct CLI, a human-forged FULL_SERIAL owner gate bound to the current bindings.
- The origin decided Option A: recertify CORE_RC1. FULL runs only through MULTIWORK and the technical
  FULL_RELEASE_CHAIN.

Correction (core RC1R1):
- FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False and PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False:
  the legacy CLI routes fail closed on the package capability before any gate, ledger, source or
  destination access, even with a forged binding-exact gate.
- Historical provenance: final pairs published by RC1 are reconciled with an oracle rebuilt from the
  commit's own RC1 runner ids and must match the ledger contract and the frozen reference exactly.
- S0 scratch days validated by RC1 (VALIDATED_PENDING_PUBLISH) are published by MULTIWORK under their
  RC1 oracle (the payload producer); an unfinished RC1 build is never continued by RC1R1
  (FULL_RC1_HISTORICAL_SCRATCH_NOT_VALIDATED), and a canonical RC1 transient transaction is refused
  (FULL_RC1_HISTORICAL_TRANSIENT_TRANSACTION).
- Build, validation, publication and compression code paths are unchanged: the top-level AST delta
  RC1 -> RC1R1 is exactly the two capability flags, `reconcile_full_readonly`, the RC1 constant and four
  new provenance helpers (tests/test_rc1r1_recertification.py in the FINAL tree).

Correction (this package):
- release and candidate engines: CORE_B64/CORE_SHA = RC1R1; `oracle_contract()` accepts RC1R1 and the
  historical RC1 runner with the same reference check; R8 provenance unchanged; unknown runners fail closed.
- postfull_verifier: same dual RC1/RC1R1 rule; R8 rule unchanged.
- candidate/release remain fuse-only (IMPLEMENTATION_READY is the only line that differs).
- config: core_sha256, delta_release_source_sha256, delta_candidate_source_sha256,
  postfull_verifier_sha256 and code_manifest_sha256 updated; every other sealed value unchanged.
- REFERENCE_B64/REFERENCE_SHA, orchestrator, master script, loader, tests and test hashes unchanged.

Not carried forward:
- 37 documentary/review files of V002R22 (docs, policy history, review prompts and patches,
  README_EXECUCAO.md, BUILD_AUDIT.json) are not executed by any node and were not available to this
  build. Their SHA-256 remain recorded in the preserved V002R22 manifest; the installed V002R22 package
  is kept as a backup by the migration tool, never deleted.

Gates:
- B06 independent review must cover these exact bytes; the D4 review verdict schema remains
  `TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R22` (format identifier read by the engine).
- B07, D4, D5, canary and FULL stay mandatory in the canonical order. No effect is authorized by this
  document.
