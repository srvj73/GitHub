# TICKSTORE FULL MULTIWORK RC3

RC3 is the productivity architecture that supersedes RC2R3 before any further production run.
The frozen RC1 transaction engine remains unchanged.

## Why RC3 exists

RC2R3 proved correctness, resume and 22-process coexistence, but the first real production run exposed a throughput defect: workers pre-hashed entire monthly CSVs before useful work and waited on a parent ACK after every staged day. Process count therefore overstated productive concurrency.

RC3 removes both barriers.

## Productive architecture

- `SOURCE_PASS=ONE_PHYSICAL_PASS_PER_MONTH` in the ordinary parallel phase.
- SHA-256 is computed inline while the same pinned file handle scans/parses/builds.
- No `FullSerialMonth`/`PinnedSource.hash_all()` pre-pass is used by the multiwork worker.
- No per-day `DAY_READY -> ACK` barrier exists.
- A worker stages all missing days for its month while continuing forward through the monthly source.
- Canonical publication is prohibited until the worker reaches EOF and the actual monthly SHA-256 equals the homologated ledger SHA-256.
- Canonical publication remains serial and under the single writer lock.
- Parent-owned source pins overlap worker pins and remain open through final reconciliation, so a second final 452 GB source hash pass is unnecessary.
- RC2R3 scratch day pairs are reusable in place after exact oracle validation; they are not deleted or blindly migrated.

## Safety

- source CSV deletion: forbidden;
- source CSV write/rename/delete while pinned: denied by Windows sharing semantics;
- canonical writer: one;
- worker scratch: durable journal per row-group;
- Ctrl+C: cooperative at row-group or scan-chunk boundary;
- scan chunk stop latency: bounded by an 8 MiB read;
- publication before month SHA verification: forbidden;
- unknown/orphan/conflicting scratch: fail-closed;
- productivity stall with active workers and no structured progress for 180 seconds: fail-closed.

## Telemetry

Progress reports distinguish active worker states and source throughput:

`BUILDING`, `SCANNING`, `LAUNCHING`, `SOURCE_PCT`, `SOURCE_MIB_S`, `ROWS_S`, `ETA_SCAN`, RAM and disk free.

`WORKERS=22/22` alone is never treated as proof of productive concurrency.

## Resume compatibility

RC3 first normalizes any canonical FULL_SERIAL transient with the exact FULL release oracle. During parallel work it can resume validated RC2R3 scratch journals because the frozen RC1 oracle is unchanged. RC3 uses a new coordinator namespace and never treats RC2R3 coordinator state as authoritative.
