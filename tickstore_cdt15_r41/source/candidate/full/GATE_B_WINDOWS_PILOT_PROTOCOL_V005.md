# TICKSTORE — Windows Gate B Pilot Protocol V005

## Hard state
```text
PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True
FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False
AUTOCPU_AUTHORIZED=NO
CSV_DELETION=NO
```

## Mandatory order
1. PLAN.
2. Revalidate D: free space and protected trees.
3. Run `PREFLIGHT_LOW` on Windows/Python 3.14+ with stdlib-native `compression.zstd`, canonical source root, destination and scratch on the same volume.
4. Return the complete V005 preflight JSON for independent review.
5. Only after review, create a separate owner-gate JSON with `authorized=true` bound to the exact preflight SHA-256, date and package identities. The package contains only a `false` template.
6. Run `PILOT_LOW` for `20260731`. The runner re-runs a fresh core preflight before reading the real source.
7. Independently decode/reconcile vs P4-A/P4-B and invoke again for REUSE; then execute the frozen crash/ENOSPC/orphan/source/lock matrix.
8. After low-day PASS, run a new `PREFLIGHT_HIGH`, independently review it, create a new high-date owner gate, then run `PILOT_HIGH` for `20211022` with resource instrumentation.
9. Produce final Gate B verdict. Full history remains blocked regardless.

## Runtime proof
The V005 preflight proves hardlink, ADS, junction/reparse, optional symlink, 8.3 when available, CreateFileW share denial, live ancestor rename denial, transient external lock and single-writer behavior. It records exact source/destination/scratch paths and volume identity plus runner/reference/spec/preflight/ledger hashes and native-zstd stdlib origin.

A stored report is owner-review evidence, not sufficient runtime authority: the runner executes the same audited preflight again immediately before real pilot processing.

## Frozen dates
```text
LOW_ACTIVITY_DATE=20260731
LOW_ACTIVITY_ROWS=1476406
LOW_ACTIVITY_SOURCE_DAY_BYTES=94731823
HIGH_ACTIVITY_DATE=20211022
HIGH_ACTIVITY_ROWS=9607342
HIGH_ACTIVITY_SOURCE_DAY_BYTES=616509791
```
