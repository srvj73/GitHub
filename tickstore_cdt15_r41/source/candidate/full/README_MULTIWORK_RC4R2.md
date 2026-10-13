# TICKSTORE R9 FULL MULTIWORK RC4R2

RC4R2 preserves the RC4 dedicated publisher architecture and hardens shutdown lifecycle.

Key additions:
- bounded cooperative SAFE_STOP wait (60 s);
- second Ctrl+C is masked while cleanup is active;
- bounded terminate/kill escalation for genuinely stuck child processes;
- `SAFE_STOP=YES` is printed only after the process tree is clean;
- multiprocessing queues are closed/cancelled after child reap so PowerShell can regain the prompt;
- scratch compatibility is RC4R2 -> RC4 -> RC3 -> RC2R3, fail-closed on conflicts.

Production remains unauthorized until Windows preflight and real-source canary PASS.


## RC4R2 namespace closure

New scratch created by this revision is written exclusively under `FULL_MULTIWORK_RC4R2`. Existing compatible RC4, RC3 and RC2R3 pairs may be resumed in place; duplicate revision pairs for one date remain fail-closed.
