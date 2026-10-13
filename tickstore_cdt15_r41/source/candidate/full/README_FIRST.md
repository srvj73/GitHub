# README FIRST — TICKSTORE FULL RUNNER V001R8 GATE B WINDOWS

This package is the corrected Gate B revision after two fail-closed Windows preflight blockers were proven on the target machine.
It preserves the independently PASSed V001R3 transaction engine and the R5 authorization/runtime-proof fixes. R6 closed the real-Windows ancestor-rename blocker with the least-privilege directory access proven on the target NTFS; R8 closes the subsequent writer-lock error-classification blocker by normalizing Win32 CREATE_NEW existing-target errors 80/183 to the same `SECURE_CREATE_EXISTS` semantic used by POSIX O_EXCL.

```text
PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True
FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False
AUTOCPU_AUTHORIZED=NO
CSV_DELETION=NO
REAL_PILOT_EXECUTED=NO
```

A real pilot is still impossible without: Windows + Python 3.14+ stdlib `compression.zstd`, a V005 preflight bound to the exact package/date/paths/volume, a separately reviewed owner-gate JSON bound to that exact report, and a fresh in-run preflight replay.

Only the frozen Gate B dates are accepted: low `20260731`, high `20211022`.
The package includes no authorized owner gate. Read `GATE_B_WINDOWS_PILOT_PROTOCOL_V005.md` first.


RC2R2: multiwork produtivo com teto AUTO de 22 workers; reserva 2 CPUs lógicas, mantém alvo RAM 60%, impede override explícito acima do orçamento de RAM/CPU e adiciona prova física de 22 workers concorrentes no Windows.


RC2R3 (25/09/2026): fecha `JOURNAL_ORACLE_MISMATCH` na ponte de recuperação de transação canônica interrompida pelo FULL_SERIAL RC1. A recuperação passa a usar os `full_release_materials()` ids exatos que criaram o journal; `run_one_day()` genérico é proibido nessa ponte. Core RC1 permanece byte a byte congelado.

RC3 (25/09/2026): productive concurrency redesign. Ordinary month workers no longer pre-hash source files or wait for a per-day ACK. Monthly SHA-256 is computed inline during a single forward source pass; all staged days remain noncanonical until the complete month SHA is verified. RC2R3 scratch remains resumable after exact oracle validation. RC3 exposes real worker states and source MiB/s, and blocks a 180-second no-progress stall.

RC4 (26/09/2026): addresses the RC3 production observation where the parent process spent long intervals validating/publishing a verified month while newly spawned replacement workers waited for START. RC4 opens the parent source pin and classifies canonical state before worker spawn, prequeues START, and moves canonical publication to one dedicated single-writer process. The parent event loop can therefore keep admitting replacement month workers while publication proceeds independently. RC4 reuses exactly one valid scratch pair from RC4, RC3 or RC2R3 and blocks revision conflicts. Production remains blocked pending the RC4 Windows preflight and a bounded real-source canary.

Current candidate: RC4R2. New scratch namespace is FULL_MULTIWORK_RC4R2.
