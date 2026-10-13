# V001R9 — B6X R8 HISTORICAL ORACLE PROVENANCE FIX

Parent package: V001R8 CORE VSS ADAPTER
Parent package SHA256: 2371960F87E87E87894558BF054239109B3CB5A1A45347CFB68128287A962555

Physical Windows failure:
- A0..B8 PASS
- B6X FAIL at C0_THREE_DAYS with ORACLE_FROZEN_RC1_PROVENANCE
- B6X own-generation cleanup PASS
- VSS before/after set preserved: 5/5, extra=0, missing=0
- C1/canary/full not started

Cause:
- SPEC preserves historical oracles.
- C0 includes two R8-certified preexisting pairs: 20211022 and 20260731.
- `oracle_contract()` incorrectly required every oracle runner SHA to equal the RC1 CORE_SHA.
- Frozen core itself contains an explicit R8 reuse path for those two dates.

Correction:
- RC1 provenance remains accepted exactly as before.
- R8 provenance is admitted only when the full `runner_ids` object exactly equals the certified R8 IDs and date_key is exactly 20211022 or 20260731.
- Unknown runner, mutated R8 IDs, or R8 provenance on any other date fail closed.
- postfull_verifier uses the same dual-provenance rule.
- CORE_B64/CORE_SHA and REFERENCE_B64/REFERENCE_SHA are unchanged.
- candidate/release remain fuse-only apart from the same shared V005R1 correction.
- physical tests target 92 candidate + 92 release.
- external review target becomes V005R1 and remains mandatory before C1.
