# CDT15 G4 — MENU + Installer Guard Merge R1 — SOURCE_ONLY

Engineering delta against `TICKSTORE_CDT15_G4_STAGE_PHYSICAL_NATIVE_SOURCE_ONLY.zip`.

* Replaces only `candidate/menu/MENU.py` with the 63/63 Windows-qualified
  producer/consumer MENU reader (its reader methods also passed 20 local tests).
* Adds an unconditional `-ActivateMenu` fail-closed gate at the START of the
  historical installer `candidate/control/INSTALL_TICKSTORE_FULL.ps1`.
  The old installer must NOT publish `ACTIVE_DEPLOYMENT` alone.
* All other 126 source files remain byte-identical to the parent.
* `ENGINEERING_BINDING.json` records parent, policy, and delta identities.

WARNING: This merged runtime remains INCOMPLETE and SOURCE_ONLY. The real
transaction producer is still a disposable-sandbox prototype and is NOT
connected to the official installer. No release or B06 admission. Do not run
`INSTALL_TICKSTORE_FULL.ps1` from this package on the user's Windows.
No installations, state, journal, production, or policy files were changed.
