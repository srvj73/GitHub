# CDT15 G4 — sandbox-only interprocess coordinator

**SOURCE_ONLY; never install this package.** Exact policy R40, CANDIDATE_PRODUCER.

New `candidate/control/MENU_TX_INTERPROCESS_SANDBOX.py` uses a **persistent lock file** with a kernel-managed exclusive, non-blocking lock: `msvcrt.locking` on Windows, `fcntl.flock` on POSIX. It does not delete the lock after release; the kernel releases the OS lock on process termination. Its three gated wrappers serialize `stage`, `begin` and `reconcile` for an exact-name disposable sentinel sandbox, not arbitrary installation targets. The original producer, installer and MENU code remain byte-identical to the parent package.

**Result scope:** targeted new-delta 17 tests locally on POSIX including separate-process termination at PREPARED, MENU write, ACTIVE write and ACTIVE_PUBLISHED, live contention, link/hardlink/drift controls, rollback and idempotency. A native Windows version of these 17 tests is required; local POSIX tests do not establish Windows locking semantics. A test of unsafe symlink creation may instead prove the sandbox OS prohibited creating the symlink (not a Win32 reparse guard execution); prior tests supplied separate link evidence.

**Known unclosed risks:** does not connect the OS lock to *all* paths of the real installer or historical publisher; the underlying original `SandboxedTransaction` can be called outside wrappers. Sandbox guard is not a release-grade handle-pinned Win32 path/ACL verifier. No power-loss or directory-fsync durability claim; no hard-kill/simulated reboot on productive paths; no global atomicity for two files. Native Windows security, coordination of real MENU consumers, recovery across machine restart, and G4/G5/B06 remain pending. Never run the official installer or FULL from this archive.

Portable delta test: `python -I -B -m unittest discover -s tests -p test_menu_tx_interprocess.py -v`.

On Windows only, the SHA-pinned PowerShell diagnostic extracts to a new LocalAppData Temp directory and invokes `native_interprocess_driver.py`, which executes only the 17 new tests in disposable temp sandboxes. No production path is accepted by the driver.
