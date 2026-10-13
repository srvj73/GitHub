# Gate B — mandatory local Windows pilot matrix

This matrix is not authorized for execution by the present package. It is frozen now so
the pilot-enabled revision cannot choose tests after seeing results.

## Nominal and reuse
1. Convert one real low-activity day.
2. Independent full decode vs P4-A semantic/offset oracle.
3. Second run must REUSE without recoding.
4. Container/commit/global-manifest hashes remain deterministic.

## Safe stop / abrupt termination
Inject at:
- before first group payload;
- after a group payload fsync but before journal publication;
- after group journal publication;
- before index finalization;
- after full validation before commit.partial;
- after commit.partial;
- after container rename while commit.partial remains;
- after commit rename before global-manifest publication;
- after manifest before journal cleanup.

Expected:
- no unjournaled group becomes reusable;
- extra unjournaled bytes are truncated on resume;
- committed days are never recoded;
- no PASS is ahead of reconciled state.

## Source identity
- source content change;
- same-length content change;
- restore original mtime after content change;
- normalized path change;
- source replacement between hash and conversion.

All must fail closed unless exact identity matches.

## ENOSPC / I/O
Use fault injection, not real disk filling:
- group section write ENOSPC;
- journal atomic-write failure;
- index write/fsync failure;
- commit.partial failure;
- container rename failure;
- commit rename failure;
- global manifest publication failure.

Previously committed days and source CSV must remain intact.

## Orphans
- final container only;
- commit only;
- journal only;
- partial only;
- final container + valid commit.partial;
- final container + commit.partial of other source/revision;
- final pair + unexpected partial.

## Windows-specific filesystem
- junction/reparse root and entries;
- symlink where permitted;
- ADS;
- 8.3/alternate path spelling;
- file locked by another process;
- OneDrive active synchronization lock;
- antivirus-style transient denial;
- directory enumeration/metadata access denial.

## Resource instrumentation
Use a high-activity real day:
- working set sampled during build and decode;
- temporary bytes;
- output bytes;
- read/write throughput;
- destination free space before/after;
- no worker count > 1.

## Locks
- second writer must block;
- stale lock must not be silently deleted;
- live lock must not be removed.

## Publication
Global manifest and daily commit are external commitments.
Any missing/mismatching manifest record blocks REUSE.

Only after all required pilot cases PASS may Gate B be requested.


## V001R3 mandatory regression additions

Before a pilot-enabled package may be issued, the following counterexamples from the
V001R1 and V001R2 independent audits must remain closed:

1. replace the ledger path after its canonical bytes are read: parsed authority must remain
   the already-hashed immutable byte image;
2. replace the source after initial hashing with same size/mtime: pinned handle/path binding
   must block;
3. mutate source contents with size/mtime restored after full decode and at every publication
   hook: no terminal success and no unjournaled reusable authority;
4. all-groups journal with wrong schema -> block;
5. all-groups journal with wrong durable_end -> block;
6. all-groups partial with unjournaled suffix -> prove boundary, truncate suffix, resume;
7. missing manifest + minimal/fake journal -> block and preserve journal;
8. valid manifest + incompatible surviving journal -> block and preserve journal;
9. container + commit.partial without journal -> block;
10. final pair + conflicting partial + journal atomic shadow -> conflict must remain visible;
11. partial path replaced by symlink before index write -> block before modifying target;
12. symlink/reparse ancestor -> block before directory creation/write;
13. surviving journal symlink -> block and leave target untouched;
14. writer-lock release failure -> no terminal day PASS/result;
15. Windows source handle must demonstrably deny write/delete sharing while conversion is live;
16. hardlinked `.pts2g.partial` before index finalization -> block before alias mutation and
    before container/commit/manifest publication;
17. hardlinked transaction source/destination in writable-open/replace helpers -> block;
18. ancestor swapped after POSIX parent fd pin but before basename open/replace/mkdir ->
    operation stays bound to the original directory object or blocks; external target remains
    untouched.

The Windows pilot must additionally test junctions, reparse points, ADS, 8.3 aliases,
hardlinks, live ancestor rename/delete attempts while replace/unlink is in flight,
OneDrive/antivirus locks and real process-level sharing behavior.

