# TICKSTORE CDT15 / G4 — official writer contract (SOURCE_ONLY)

This package is an engineering source delta, **not an executable official publisher**.

## Proven

- The parent package `TICKSTORE_CDT15_G4_OFFICIAL_TARGET_READONLY_SOURCE_ONLY_20261013.zip` is anchored by SHA-256 `CF68F345298CA8FB81ACBEC5B2A556F66962993358969EE683502BAB1FAD7F97`.
- The returned Windows read-only target receipt ZIP is anchored by SHA-256 `7384868341F53D10602BBEAF5F348A92BD5434E0EAF9E73FD02A2B0286EC9E4D`.
- `MENU_OFFICIAL_WRITER_CONTRACT_SOURCE_ONLY.py` composes an inert plan from the observed target and independently verified inactive installed intent. It explicitly distinguishes D: MENU backup/pending paths from C: ACTIVE and journal paths.
- It refuses to infer COMMITTED from the two target hashes without the journal phase; incorrect readback or drift blocks.
- The 32 new tests are portable. Native Windows physical readmission under an acquired writer lock, ACLs, power-loss durability, production publication and real recovery are **not tested or authorized**.

## Next engineering

Implement Win32 writer that re-admits targets and source while holding the writer's lock; pins identities, verifies original target backup on D:, persists journal on C:, uses required explicit backup in `ReplaceFileW`, readbacks bytes and phases, and supports external-process reconciliation. Validate all of this in a disposable Windows namespace before allowing a real target, then reconcile to final complete candidate G5 before independent B06.

Do not install this package or assume it gives release authority. Do not alter MENU/BAT or ACTIVE_DEPLOYMENT.
