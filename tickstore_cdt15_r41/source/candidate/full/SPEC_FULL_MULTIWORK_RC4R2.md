# SPEC — FULL MULTIWORK RC4R2

Wrapper schema: `TICKSTORE_R9_FULL_MULTIWORK_RC4R2_V001`.

All RC4 invariants remain: one physical source pass per month, inline monthly SHA-256,
22-process worker ceiling, dedicated canonical single-writer publisher, publication only after
monthly SHA verification, no day ACK barrier, continuous source pins, and final read-only
reconciliation.

Shutdown invariant:
1. first Ctrl+C sets the shared stop event;
2. workers stop at row-group or scan-chunk boundaries; publisher stops at publish-day boundary;
3. additional Ctrl+C is ignored while the parent is cleaning the process tree;
4. cooperative wait is bounded to 60 seconds;
5. survivors are terminated, then killed only if still alive after the grace period;
6. `SAFE_STOP=YES` is forbidden until no worker/publisher process remains;
7. queue feeder threads are detached after process reap so the host PowerShell prompt can return.

Any forced escalation remains resumable via the transactional journal/durable-end contract.
No CSV deletion, format promotion, codec promotion, or legacy full-history authorization.


## RC4R2 namespace closure

New scratch created by this revision is written exclusively under `FULL_MULTIWORK_RC4R2`. Existing compatible RC4, RC3 and RC2R3 pairs may be resumed in place; duplicate revision pairs for one date remain fail-closed.
