# CDT15 G4 — Official target identity boundary (SOURCE_ONLY, READ-ONLY)

This delta is derived from TICKSTORE_CDT15_G4_FUSED_TRANSACTION_SOURCE_ONLY_20261013.zip. It does **not** implement, qualify or authorize official MENU publication, D4/D5, B06 or FULL.

* Current target identities are historical pins observed in a previous Windows-only read-only receipt, not claims of current state. The new Windows run must re-observe all of them.
* `candidate/control/MENU_OFFICIAL_ADMISSION_READONLY.py --readonly` accepts no target arguments. It requests Win32 read handles only and has no writer or installer mode.
* It checks exact MENU/BAT paths, SHA256, one hardlink per file, no reparse in target path ancestors and final handle path consistency. It rejects an existing ACTIVE_DEPLOYMENT or MENU_TRANSACTION until independently reconciled.
* The read-only result **cannot be used as a commitment/authority token**. Race/ACL/lease/power-loss durability, installation, and transaction effectful qualification all remain pending.
* Historical policy revision R40 source SHA is for provenance only. Live MASTER+HEAD remain exclusively authoritative in Library, not in Windows.

The module has 16 portable negative controls; Windows native handle proof remains pending. No formal B06 may be sent for this incomplete candidate.
