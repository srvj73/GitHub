# TICKSTORE — FULL RUNNER V001R8 GATE B WINDOWS

## Status

This revision preserves the independently PASSed V001R3 implementation and is a separate Gate B Windows pilot package.

Authorization is deliberately narrow:

- `PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True` only after Windows preflight + external owner gate
- `FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False`
- `AUTOCPU_AUTHORIZED=NO`
- one writer only
- `CSV_DELETION=NO`

The package must be independently audited before the first real pilot. After that audit, only the frozen Windows Gate B pilot protocol may read a real source CSV. Full history remains unavailable.

## Frozen physical format

No format change was made:

- PTS2G001
- ZSTD level 9
- row group 262,144 ticks
- streams TIME, MASK, BID, ASK, LAST, F6, F7, FLAGS, OFFSET
- exact audited `pts2g_reference.py`

The reference implementation must remain byte-identical to the P4-B audited code.

## Canonical ledger authority — V001R1 MAJ-01 remediation

The only accepted historical ledger ZIP SHA-256 is:

`27FF5A0FE47F3DDC5FD63F6371CCF0EDA8124E0E5D504A8F0756A4DF0DB9C3CA`

`load_ledgers()`:

1. opens the ledger as a strict regular file;
2. reads it once into one immutable byte image;
3. hashes that byte image;
4. compares the digest with the fixed canonical SHA;
5. parses `ZipFile(io.BytesIO(the_same_bytes))`.

The path is never reopened for parsing after the approved digest.

## Source authority — V001R1 MAJ-02 remediation

Production source access is represented by one `PinnedSource` object held from identity
creation through conversion/reuse and publication.

The same open file object is used for:

- initial full SHA-256;
- tick reads;
- revalidation before publication boundaries.

Identity binds:

- normalized absolute path;
- size;
- mtime_ns;
- st_dev/st_ino when the filesystem exposes them;
- full SHA-256.

### Windows production policy

On Windows the source is opened with `CreateFileW` and:

- `FILE_SHARE_READ` only;
- no write sharing;
- no delete sharing;
- `FILE_FLAG_OPEN_REPARSE_POINT`;
- handle attributes are checked before conversion.

Therefore another normal Windows opener cannot modify, replace or delete the source while
the runner owns the source handle.

The same handle is retained through the transaction.

### Revalidation

`verify_full()` recomputes the SHA on the same open handle and verifies both the open-handle
identity and the current path binding.

The current preparation revision revalidates before expansion of publication authority,
including before final container/commit/manifest publication and before REUSE result.

This is intentionally conservative for the pilot. Full-history optimization is not yet
authorized.

## Destination path policy — V001R1 MAJ-06 + V001R2 MAJ-01 remediation

Static symlink/reparse checks remain fail-closed, but V001R3 no longer relies on a
check-then-reopen path sequence as the mutation boundary.

For regular files used by the runner, multiple hardlinks are rejected before mutation or
publication. A regular file must have exactly one link (`st_nlink == 1` on POSIX;
`nNumberOfLinks == 1` from the opened Windows HANDLE).

POSIX mutation/open policy:

- walk the parent chain one directory handle at a time with `O_DIRECTORY|O_NOFOLLOW`;
- retain the final parent fd as the binding authority;
- open/create the final basename with `dir_fd`;
- perform `replace` using `src_dir_fd` and `dst_dir_fd`;
- compare the post-replace destination identity with the pre-replace source identity.

Therefore swapping a textual ancestor after the parent fd is pinned cannot redirect the
operation into another directory tree.

Windows mutation/open policy:

- reject alternate data stream syntax;
- open files with `CreateFileW(... FILE_FLAG_OPEN_REPARSE_POINT ...)`;
- validate `GetFileInformationByHandle`, including `nNumberOfLinks`;
- validate `GetFinalPathNameByHandleW` against the requested normalized absolute path;
- before path-based replace/unlink, pin every ancestor directory using a HANDLE opened with
  exactly `FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES|SYNCHRONIZE`, sharing READ+WRITE but
  deliberately denying `FILE_SHARE_DELETE`; this is the least-privilege combination proven
  on the target Windows/NTFS machine to block live ancestor rename with WinError 32 until
  HANDLE close;
- revalidate the destination object after replace.

New files still use exclusive creation. No index/payload/truncate operation uses
`Path.open()`.

Required regressions include the former R2 terminal counterexample: a hardlinked
`.pts2g.partial` before index finalization must block before modifying the external alias and
before publishing container/commit/manifest. Ancestor swaps injected immediately before
open and replace must leave external victims unchanged.

Windows runtime homologation remains separate and mandatory before any pilot-enabled
revision. It must include junctions/reparse points, ADS, 8.3 aliases, hardlinks, live
ancestor rename attempts and OneDrive/antivirus locks.

## Journal schema V002 — V001R1 MAJ-03/04 remediation

`TICKSTORE_DAY_JOURNAL_V002`

States:

1. `BUILDING`
2. `VALIDATED_PENDING_PUBLISH`
3. `COMMIT_STAGED`
4. `CONTAINER_PUBLISHED`
5. `COMMIT_PUBLISHED`
6. `MANIFEST_PUBLISHED`

All paths use a central journal validator.

Mandatory invariants include:

- exact schema;
- exact oracle;
- recognized state;
- completed-group cardinality;
- deterministic group/row/source continuity;
- exact stream order;
- exact payload offsets;
- exact `durable_end`;
- raw group re-decode;
- full-day coverage where required.

Once validated, later states additionally require:

- exact container SHA and byte size;
- exact commit-file SHA and byte size after `COMMIT_STAGED`;
- external manifest-record digest after `MANIFEST_PUBLISHED`.

The all-groups branch receives the same validation as the partial resume branch.
A torn/complete index can be deterministically rewritten only after the complete journaled
payload boundary has been re-proved.

Bytes beyond the proven `durable_end` are uncommitted and may be truncated only after that
boundary is validated.

## Publication transaction

Nominal sequence:

1. durable row groups + BUILDING journal;
2. final index/hash rewrite;
3. full P4-B parse/decode;
4. journal -> `VALIDATED_PENDING_PUBLISH`;
5. full source revalidation;
6. durable commit.partial;
7. journal -> `COMMIT_STAGED`, binding commit SHA/size;
8. full source revalidation;
9. container.partial -> container;
10. journal -> `CONTAINER_PUBLISHED`;
11. full source revalidation;
12. commit.partial -> commit;
13. journal -> `COMMIT_PUBLISHED`;
14. full source revalidation;
15. external global manifest publication;
16. journal -> `MANIFEST_PUBLISHED`;
17. final source + container + commit + manifest + journal reconciliation;
18. journal cleanup;
19. terminal success only after writer-lock cleanup.

## Global manifest and repair — V001R1 MAJ-04 remediation

The external manifest binds:

- source identity;
- ledger SHA;
- day-contract SHA;
- code/spec revision;
- format/codec;
- semantic/offset hashes;
- container SHA/size;
- actual commit-file SHA.

Manifest repair is forbidden without an authoritative journal.

For final container + commit with a missing manifest, journal repair authority requires:

- exact V002 schema/oracle;
- all groups and durable boundary valid;
- container SHA/size matching journal;
- commit SHA/size matching journal;
- an allowed post-commit transaction state.

A minimal/fabricated journal cannot authorize repair.

If a manifest already exists and a journal survives, that journal is validated before
cleanup. An incompatible or linked journal blocks.

`container + commit.partial` without an authoritative journal blocks.

## State classification before cleanup — V001R1 MAJ-05 remediation

The entire day state is snapshotted and every existing transaction path is type/link
checked before any cleanup.

A final pair plus any conflicting container/commit partial blocks even if an atomic journal
shadow also exists.

Uncommitted shadows may be discarded only inside a state already classified and validated.

Zero-authority states:

- partial without journal: zero reusable progress; safe rebuild only after full state
  classification and regular-file proof;
- journal without partial: zero reusable output; safe rebuild only after JSON/type proof;
- journal atomic shadow without authoritative journal: never reusable.

No shadow may delete or hide conflicting evidence before classification.

## Orphan states

- final container only -> block;
- final commit only -> block;
- container + commit.partial without journal -> block;
- final pair without manifest and without authoritative journal -> block;
- final pair + valid manifest + no journal -> normal REUSE;
- final pair + surviving journal -> validate journal exactly before cleanup;
- container + valid commit.partial + authoritative journal -> recover publication;
- validated partial + unbound commit.partial -> validate partial, discard unbound sidecar,
  restage deterministically.

## Writer lock

Exactly one writer.

`TICKSTORE_WRITER.lock` is created exclusively.
A pre-existing lock blocks and is never silently deleted as stale.

Terminal success is emitted only after lock cleanup succeeds.

## Space

Required free space is **at least**:

`max(2 * source_day_bytes, 2 GiB) + 512 MiB`

Equality is accepted. This is a dispatch safety reserve, not a compression prediction.

## Status labels

- `BUILT`: new day completed;
- `RESUMED`: incomplete durable day resumed;
- `RESUMED_PUBLICATION`: publication resumed after container rename;
- `RESUMED_MANIFEST`: final pair reconciled and missing manifest repaired from proven journal;
- `REUSED`: already committed day independently reconciled.

## Menu integration

`MENU_MAINTENANCE_INTEGRATION_CONTRACT_V001.md` remains mandatory.

After Gate B and format/runner promotion, the official Base CSV maintenance pipeline must
automatically convert new Genial tick CSV deltas into the promoted TickStore format and
validate before publication.

Until then:

- menu/BAT current behavior is unchanged;
- CSV remains canonical;
- CSV deletion is forbidden.

## V001R8 Windows Gate B execution binding

A real pilot invocation is accepted only when all of the following are true:

1. package hard flag `PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True`;
2. runtime is Windows;
3. runtime is Python 3.14 or newer;
4. `pts2g_reference.require_zstd()` loads native `compression.zstd` and passes its self-test;
5. a Windows preflight report has schema `TICKSTORE_WINDOWS_GATE_B_PREFLIGHT_V005`, status PASS, exact runner/reference/spec/preflight/ledger SHA-256 bindings, complete mandatory result fields, exact frozen pilot date, and source/destination/scratch path + Windows volume bindings;
6. an owner gate JSON is separately created after review and binds authorization to the exact preflight-report SHA-256, exact frozen pilot date, and runner/reference/spec/preflight/ledger identities;
7. immediately before any real CSV read, the runner independently re-executes the audited Windows preflight on the same source/destination/scratch volume and validates the fresh result;
8. source root, destination root, scratch root, date and ledger are explicitly supplied;
9. only frozen Gate B dates `20260731` and `20211022` are accepted.

The package intentionally does not contain an authorized owner gate. The included JSON template has `authorized=false`.
Native codec acceptance additionally requires the exact module `compression.zstd` and an origin inside the active Python 3.14+ standard-library `compression/zstd` package; round-trip or module-name text alone is insufficient.

The preflight report proves only core Windows runtime/filesystem prerequisites. It does not
itself assert the final Gate B verdict. The frozen real-pilot matrix still requires nominal
conversion/decode, REUSE, fault injection, source identity cases, orphan cases, process locks,
OneDrive/antivirus observations and resource instrumentation.

Full-history dispatch remains unavailable regardless of any pilot result.
