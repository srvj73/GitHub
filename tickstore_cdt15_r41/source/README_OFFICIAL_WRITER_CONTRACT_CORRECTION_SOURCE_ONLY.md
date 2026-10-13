# G4 official writer contract — correction SOURCE_ONLY

Changed only `MENU_OFFICIAL_WRITER_CONTRACT_SOURCE_ONLY.py` and its targeted test file against the parent source package.

The `recovery_decision` helper now rejects malformed and degenerate plans that previously could permit a synthetic COMMITTED classification. This does NOT implement an effectful official writer or qualify the Windows target.

The updated 40 targeted tests passed in the local sandbox; the new bytes have not passed native Windows qualification. The unmodified 162 files from the parent (other than its manifest) retain their exact hashes.

No production writes, official MENU changes, D4/D5/CANARY/FULL initiation or B06 audit were performed.
