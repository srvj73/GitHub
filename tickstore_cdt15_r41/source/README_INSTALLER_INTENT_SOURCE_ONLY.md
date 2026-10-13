# CDT15 G4 — Installer to transaction intent bridge (SOURCE_ONLY)

Parent: TICKSTORE_CDT15_G4_MENU_GUARD_MERGE_SOURCE_ONLY_20261013.zip (SHA256 bound in ENGINEERING_BINDING).
Policy: R40, FROZEN. Role: CANDIDATE_PRODUCER. This is **not** a final package, release, B06 request or effectful installer.

New: installer emits `MENU_INSTALL_INTENT.json` only **inside** a newly installed inactive candidate after verifying the exact MENU member and deployment bytes. Request binds witness, manifest, launcher, MENU, deployment and installed root. Independent `MENU_INSTALL_INTENT_VERIFY.py` refuses malformed/changed/non-inert requests; external trusted hashes are mandatory.

Safety: `-ActivateMenu` remains hard-blocked *before any effect*. No official MENU/BAT, STATE, journal, ACTIVE_DEPLOYMENT, D4/D5/CANARY/FULL are touched. The trust boundary for real publication and cross-process locking is still unimplemented; do not run INSTALL_TICKSTORE_FULL.ps1 or dispatch B06.

Tests: `python -m unittest discover -v -s tests -p test_installer_intent.py` (new delta only). Native Windows PowerShell 5.1 parsing is separately pending. Previous 63/63 integrated sandbox Windows tests are historical and not repeated.

Remaining: deliver complete FINAL package + witness, Windows PS5.1 qualification, native writer and lock connected to actual installer, crash recovery across processes, reobserve official MENU/BAT identity, verify tested code equals packaged final code, G4/G5 completion before independent B06.
