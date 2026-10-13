# CDT15 G4 — source-only intent-to-sandbox transaction bridge

Policy R40 MASTER SHA256 695DCD6495E549B13B13A73E063EA147CF97354C53940A70647EDFD0A0BC7DF5; HEAD SHA256 B3B419592DC29651487B1545E1CD7AE66604AB78582202883684E69BCB1FF7EA.

The original INSTALL_TICKSTORE_FULL.ps1 and MENU.py remain BYTE-IDENTICAL. New MENU_INTENT_TO_TX_SANDBOX.py joins verified inert MENU_INSTALL_INTENT.json from a simulated installed instance with the original 2-file producer, using an exact-name sentinel sandbox and external package+witness pins. Successful sandbox COMMITTED is consumed by the real MENU guard extracted as AST in the tests. It **does not** grant release authority, change the official MENU/BAT, install, write ACTIVE_DEPLOYMENT, or execute FULL. No CLI for production.

Test only the material new delta: python -I -B -m unittest discover -s tests -p test_intent_to_transaction_sandbox.py -v

State: PORTABLE_SANDBOX_ONLY, 16/16 PASS. Windows native integrated test and actual producer/installer coupling are still pending. Native durability, lease/mutual exclusion, ACL, bound final witness, crash between processes, tested=packaged=delivered release and B06 independence remain BLOCKED/NOT_PROVEN. Do NOT activate. Source-only archive is not the final deliverable.

Parent source-only package SHA256: 2FFB0662EA2F689F56F8E9A438DF6C81B8EE9F6BD7D4090AABC04D2CA2E68DA1
Windows PS5.1 parent parser-only receipt SHA256: C5B406A4BC669E93B4A88D378B00BFA161FCF8008D1441312E9C2079256358ED
