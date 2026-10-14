# TICKSTORE R9 — FULL MULTIWORK RC3

## Status

PREAUDIT ONLY. Real production execution is not authorized by this package.

## Invariants

1. Frozen core SHA-256 is RC1R1 `749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00` (recertified from RC1 `D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0` by origin decision Option A: the legacy FULL_SERIAL and PILOT CLI routes are disabled in code; final pairs published by RC1 keep their RC1 provenance).
2. Source root remains read-only.
3. Canonical destination publication is single-writer and protected by the RC1 writer lock.
4. `AUTO` is bounded by 22 workers, CPU budget, and RAM target 60%.
5. No CSV deletion, codec promotion, format promotion, or legacy full-history route is authorized.

## Single-pass source contract

For an ordinary month worker:

- open one source handle with `source_pin=True`;
- capture size/mtime/file identity and bind the oracle to the ledger-expected SHA-256;
- never seek backwards;
- hash every source byte exactly once on that handle while scanning gaps and parsing/building required days;
- stage output only in scratch while the monthly hash is unproven;
- at EOF require byte count == expected monthly size and SHA-256 == homologated monthly SHA-256;
- only after that event may the parent validate existing canonical days and publish staged days.

A crash or Ctrl+C before monthly SHA verification leaves only scratch authority. No scratch from an unverified month can be promoted canonically.

## Publication decoupling

There is no daily ACK barrier. A worker continues to the next day after atomically journaling/finalizing its current scratch day. A terminal `MONTH_VERIFIED` event contains the complete staged-day set. The parent validates the set against the preclassified missing-day set before publication.

Publication remains serial. Other workers continue scanning/building while the parent publishes a verified month.

## Continuous source pin seal

When a worker opens a monthly source, the parent opens an overlapping source-pin handle before issuing START. The worker proves the full SHA on its own pinned handle. After worker exit, the parent pin remains open through canonical publication and global read-only reconciliation. Final success requires all 75 verified source identities and all 75 parent pins to remain binding-valid. The pins close only after writer-lock release and final binding checks.

This replaces a second full-source rehash pass without weakening mutation exclusion during the run.

## RC2R3 scratch compatibility

For a date missing canonically, RC3 checks the RC3 scratch namespace and then the RC2R3 namespace. Exactly one complete partial+journal pair may exist. Pair mismatch or simultaneous pairs block. A legacy RC2R3 pair is resumed in place only through the unchanged RC1 oracle validation. No automatic deletion or coercion is allowed.

## SAFE_STOP

- worker scan loops poll the stop event at each <=8 MiB scan chunk;
- build loops poll at each row-group boundary;
- workers blocked before START receive an explicit STOP command;
- no canonical publication begins for an unverified month;
- durable scratch journals are the resume authority.

## Productivity gate

The runtime emits source bytes scanned and real worker states. A 180-second interval with active workers and no OPENED/SCAN/GROUP/DAY_STAGED/MONTH_VERIFIED/MONTH_STOPPED event blocks as `PRODUCTIVITY_STALL_NO_WORKER_PROGRESS`.

Windows preflight must prove:

- 15/15 RC3 multiwork unit tests;
- frozen RC1 Windows suite 39/39, zero skip;
- 22 concurrent worker processes alive and source-pinned;
- inline monthly source SHA verification;
- no daily ACK barrier;
- build and restart/resume scratch equivalence;
- RC1 -> RC3 canonical recovery bridge;
- no real production destination write.
