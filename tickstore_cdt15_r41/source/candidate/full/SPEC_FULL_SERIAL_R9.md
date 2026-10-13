# TICKSTORE R9 FULL_SERIAL RELEASE CANDIDATE RC1

RUNNER_SCHEMA=TICKSTORE_SERIAL_RUNNER_V001R9_FULL_SERIAL_RELEASE_RC1
FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True
FULL_OWNER_GATE_SCHEMA=TICKSTORE_FULL_OWNER_GATE_V001
FULL_SERIAL_CAPABILITY_IN_RELEASE_CANDIDATE=YES
OWNER_AUTHORIZATION_REQUIRED=YES
AUTHORIZED_GATE_INCLUDED=NO
FULL_HISTORY_EXECUTION_AUTHORIZED=NO
AUTOCPU_AUTHORIZED=NO
CSV_DELETION_AUTHORIZED=NO

This release candidate exposes the FULL_SERIAL capability only through --mode FULL_SERIAL.
Execution still requires an external owner gate and its independently supplied trusted
SHA256 to pass every exact release, plan, source, destination, scratch and volume binding.
The package contains no authorized gate, trusted gate digest, automatic gate discovery,
gate generator or fallback. The historical --full-history route remains hard blocked.
Internal helpers accept synthetic fixtures for tests and are not independent execution routes.

## Frozen materials and plan

PTS2G001, ZSTD9 and 262144 ticks/group remain unchanged. Reference, original R8 spec,
ledger, preflight, full-plan contract, Gate B certificate and false gate template are frozen.
The new spec supplies the R9 oracle spec identity; ordinary R8 pilot identity construction
continues to use SPEC_FULL_RUNNER_V001.md, with the current runner hash as before.

The ledger is loaded through R8's same-image canonical ZIP validation. Before source access,
the full contract file must have SHA256
D07217CDB7BB50DC6EECCC1DF7746F412BD71B1E5968CFB133B5A6E06AA3A4D5.
The complete plan must prove 75 months, 1550 unique dates, 7049522162 rows and
452248059942 bytes, from 20200702 through 20260918. Ledger order must already be ascending
for dates and months. Empty dates/months, wrong month membership, noncompatible counters,
invalid ranges and inconsistent per-month totals block before conversion.
Every month is partitioned from byte zero to its exact source_size without gaps/overlaps.

Sequence hashes use UTF-8 of LF.join(keys in ledger order) + LF, exactly one final LF,
no BOM/CRLF/spaces. Expected date hash:
D3A9B48F94A6F67572AA606C8ACD6539CDA3EC67B67EE1F1340D3CC738660FED.
Expected month hash:
92426F11DBCE05505251A4DC3F021F546C6D3A8FE20B69748AF6163D84180CD7.

Full-plan SHA256 is uppercase SHA256 of JSON with sort_keys=True,
separators=(",",":"), ensure_ascii=True, UTF-8, no final newline. Its exact fields are
schema, ledger_sha256, months, days, rows, source_bytes, first_date, last_date,
dates_sorted_ascending, months_sorted_ascending, date_sequence_sha256,
month_sequence_sha256, range_partition_exact, unique_month_source_bytes and
naive_one_month_hash_per_day_bytes. full_plan_sha256 itself is excluded.
Expected full-plan hash:
54CAAEB6D0C54E5509254C1C3CE45290A3FBBFE1E685111512531F482A05900C.

## Owner gate

Use FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json as the R9 field template. It contains
the exact R9 key set with authorized=false. Release-dependent hashes and machine-specific
paths/volumes remain null; known frozen bindings and the R9 schema are included.
The original FULL_OWNER_GATE_TEMPLATE_DO_NOT_USE.json is frozen and unchanged.
An externally prepared gate would require exact keys and values for:

- schema, authorized (boolean true only), runner_schema;
- runner_sha256, reference_sha256, full_spec_sha256 (SPEC_FULL_SERIAL_R9.md);
- full_plan_sha256 and full_plan_contract_sha256 (the complete frozen JSON file digest);
- ledger_sha256, gate_b_certificate_sha256;
- source_root, dest_root, scratch_root (normalized absolute paths);
- source_volume, dest_volume, scratch_volume (the R8 Windows volume-identity objects).

runner_schema and full_plan_contract_sha256 are included in the new R9 template;
the frozen false template is intentionally not rewritten. full_spec_sha256 is the spec
binding; *_volume keys are the volume-identity bindings matching the seed vocabulary.
Duplicate JSON keys, nonobject JSON, nonfinite values, unknown/missing fields, wrong types,
false authorization, any changed binding and missing gate all block.
The caller also supplies --full-gate-sha256 through an independently trusted handoff;
it must match the exact gate byte image before parsing. This detects changes relative to
the externally supplied digest. It is not a digital signature or an independent identity
authentication system. Before any source, destination or ledger access, the gate path and
trusted digest are required and the digest must be exactly 64 hexadecimal characters.
Complete gate parsing and binding validation occurs before FULL_SERIAL dispatch. Only a gate
with authorized=true and every exact binding can reach the execution engine.

Source/destination/scratch directories must already exist, be nonlinked and nonoverlapping.
The Gate B certificate is byte-sealed to
7D142D73D740986FA62219DE6CA0C9BD0AF347A9186D58AC1C8DFB35EFB5DFF7.
Runtime admission retains Windows, Python 3.14+ and native stdlib compression.zstd checks.

## Serial execution and month pin

One TICKSTORE_WRITER.lock covers all days, month transitions and final reconciliation.
A second invocation is rejected; no stale lock is automatically removed.
No pool, threads, processes for conversion, AUTOCPU or source deletion route is introduced.

FULL_SERIAL never loops run_one_day. It calls the already-locked helper around the
unchanged reconcile_or_build engine. run_one_day now calls the same extracted helper;
its verification order, source pin lifetime, per-day lock scope and statuses are unchanged.

Windows FullSerialMonth opens one R8 PinnedSource per month and retains its write/delete
sharing denial throughout that month. Entry performs the canonical full source hash.
Publication-boundary verify_full calls through FullSerialSourceView perform path and
open-handle identity checks. At clean month exit, the original PinnedSource.verify_full
performs the second real whole-month hash before closing. A failed/aborted month need not
finish its final hash and never yields global PASS. Monthly processing still has exactly
two whole-source hashes per successful month, independent of its number of days or REUSED
results. The final global source seal adds one separate hash per month. This optimization
does not apply to ordinary day/pilot execution.

After all 75 months complete, FULL_SOURCE_FINAL_SEAL opens exactly those canonical sources
in ascending month order with secure_open_existing_fd(..., writable=False, source_pin=True).
It retains unbuffered descriptors, with bounded 1 MiB hash reads, rather than 75 buffered
PinnedSource objects. Each source must have the expected size and complete SHA256 and match
the processing-time source_identity: normalized path, size, mtime_ns, and device/file ID
when available. Both path stat and open-handle stat are checked before and after hashing.
Same-content replacement with a different file ID is rejected as well as changed content.

All final-seal descriptors remain open together, denying Windows write/delete sharing,
through global reconciliation and successful writer-lock release. Path/handle bindings
are checked after release; all descriptors must then close successfully before terminal
PASS. A failed close is retained for residual cleanup in finally and blocks PASS. Residual
cleanup never replaces the established failure or KeyboardInterrupt cause. Partial
acquisition failures and interruptions also close all acquired descriptors. The two
monthly hashes are retained; successful completion therefore reads each source fully
three times for hashing, never once per day.

BUILT, REUSED, RESUMED, RESUMED_PUBLICATION and RESUMED_MANIFEST retain their R8 meanings.
RESUMED_COUNT combines the three resumed labels without redefining any of them.
Progress includes DAY=x/total, DATE_KEY, PERCENT, ETA, BUILT_COUNT, REUSED_COUNT,
RESUMED_COUNT and FAILED_COUNT. The sealed production total is 1550; small totals are used
only by synthetic tests. DAY counts proven per-day completions during this invocation;
even 100% is not global success until reconciliation and lock release complete.

## Certified R8 compatibility

Only 20260731 and 20211022 can take the legacy path. The current source identity and exact
ledger day reconstruct an R8 oracle using the certificate's original runner_ids and
r8_code_revision. Exact certified commit hash, container hash/bytes, schema, contract
rows/bytes/semantic/offset hashes, full container parse/decode and reconstructed manifest
record must all agree. Every transient is rejected; this path never repairs or cleans up.
Only then is REUSED returned. Any third R8 day is rejected. A genuine R9 commit for either
date follows ordinary R9 reconciliation instead of acquiring a legacy exemption.

## Stop, restart and terminal reconciliation

The first inconsistency terminates dispatch; earlier published days are retained.
KeyboardInterrupt exits any month pin, releases the invocation lock in finally and emits
SAFE_STOP=YES with exit code 130, without global PASS. If lock cleanup itself fails, the
failure propagates and no success is reported. Day journals remain the sole authority for
unfinished payload/publication; progress counters are not a checkpoint or repair authority.
Restart traverses the same canonical order and independently proves already-published days
as REUSED; unfinished transactions use existing R8 recovery rules.
SIGINT is deferred only across lock acquisition/ownership assignment and lock removal;
it is delivered immediately after those short boundaries, while conversion remains
interruptible. The same short deferral protects final-seal descriptor ownership registration
and cleanup; hashing remains interruptible. The original signal handler is restored.

Final reconciliation is read-only and does not call the directory-creating paths_for_day.
It checks manifest schema/duplicate keys/exact date set, every expected regular/nonlinked
container and commit, no live sidecars, exact current R9 oracle/commit/manifest agreement
or the narrow certified R8 proof, container bytes/hashes and full parse/decode. It walks
only destination artifacts, rejecting links before descent and detecting extra date files
anywhere below destination. Windows directory handles are pinned during enumeration.
The terminal sequence, while the writer lock remains held, is:

1. Validate all 1550 expected pairs against the initial manifest snapshot.
2. Complete the first artifact inventory.
3. Reread the manifest and require exact equality with the initial snapshot.
4. Complete a second artifact inventory.
5. Recheck absence of TICKSTORE_GLOBAL_MANIFEST.json.partial.
6. Read the manifest a third time and require exact equality with the initial snapshot.

No source rehash or cleanup occurs inside this artifact reconciliation; the preceding
FULL_SOURCE_FINAL_SEAL already holds all canonical sources pinned. Terminal success requires,
in order: reconciliation, successful writer-lock release, seal.verify_bindings(), successful
seal.close(), and only then TICKSTORE_FULL_SERIAL_STATUS=PASS plus return 0. A close failure
propagates as FULL_SOURCE_FINAL_SEAL_CLOSE_FAILED after residual cleanup is attempted; it
cannot emit PASS. The RC1 entry point can reach this terminal path only after complete
external owner-gate admission and validation.
The threat model remains cooperating writers using TICKSTORE_WRITER.lock. This does not
claim protection from an arbitrary process deliberately ignoring the lock after validation.

## Validation status

Code and synthetic tests are delivered unexecuted. No compile, test, static scanner,
real preflight, pilot, history run, benchmark, repository hash or release PASS is asserted.
RC1 capability is not owner authorization, and no authorized gate is included.
This is a release candidate for independent audit only. Real history execution remains
prohibited until all of the following are complete:

1. independent audit of this release candidate;
2. final runner and spec hashes;
3. capture of the real paths and volume identities;
4. owner-local creation of an authorized gate outside this package;
5. separate transmission of that gate's SHA256;
6. final pre-execution audit.
