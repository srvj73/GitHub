#!/usr/bin/env python3
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
r=(HERE/"tickstore_serial_runner.py").read_text(encoding="utf-8")
ps=(HERE/"run_tickstore_serial.ps1").read_text(encoding="utf-8-sig")
launch=(HERE/"RUN_FROM_DOWNLOADS_PLAN_ONLY.ps1.txt").read_text(encoding="utf-8")
spec=(HERE/"SPEC_FULL_RUNNER_V001.md").read_text(encoding="utf-8")
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest().upper()
checks={
 "RUNNER_SCHEMA_R3": 'RUNNER_SCHEMA="PEGASUS_TICKSTORE_SERIAL_RUNNER_V001R3"' in r,
 "LEDGER_SAME_BYTE_IMAGE": "ZipFile(io.BytesIO(raw))" in r and "zsha=sha256_bytes(raw)" in r,
 "REFERENCE_FROZEN": sha(HERE/"pts2g_reference.py")=="74EE141B014DE7A9F9C401C2B3C5AF6BF72E5D7D80F49E67F9D9032338480165",
 "LEDGER_FROZEN": sha(HERE/"OUT_P4A_R3_FULL_HISTORY_COMPAT.zip")=="27FF5A0FE47F3DDC5FD63F6371CCF0EDA8124E0E5D504A8F0756A4DF0DB9C3CA",
 "PINNED_SOURCE": "class PinnedSource" in r,
 "SOURCE_FULL_REVALIDATION": r.count("source_guard.verify_full()")>=5,
 "CENTRAL_JOURNAL_VALIDATOR": "def validate_journal_structure" in r and "def validate_journal_final_transaction" in r,
 "HARDLINK_FAIL_CLOSED": "MULTIPLE_HARDLINKS_NOT_ALLOWED" in r and "st_nlink" in r and "nNumberOfLinks" in r,
 "POSIX_PARENT_FD_BINDING": "def _posix_parent_fd" in r and "dir_fd=pfd" in r and "src_dir_fd=sfd" in r and "dst_dir_fd=dfd" in r,
 "WINDOWS_FINAL_HANDLE_PATH": "GetFinalPathNameByHandleW" in r and "WIN_HANDLE_PATH_MISMATCH" in r,
 "WINDOWS_ADS_BLOCK": "WIN_ADS_NOT_ALLOWED" in r,
 "WINDOWS_ANCESTOR_PIN": "def _windows_pin_ancestor_chain" in r and "FILE_SHARE_READ|FILE_SHARE_WRITE" in r,
 "NO_PATH_OPEN_RW": '.open("r+b")' not in r,
 "NO_PATH_OPEN_RB": '.open("rb")' not in r,
 "NO_PATHLIB_EXISTS_AUTHORITY": ".exists(" not in r,
 "NO_RGLOB": ".rglob(" not in r,
 "TERMINAL_PASS_AFTER_LOCK": r.find("release_lock(lock)") < r.find('print("TICKSTORE_DAY_RESULT="'),
 "PILOT_HARD_FALSE": "PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False" in r,
 "FULL_HARD_FALSE": "FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False" in r,
 "NO_AUTOCPU": "AUTOCPU" not in r and "Start-Job" not in ps,
 "NO_SOURCE_DELETE": "unlink(src" not in r,
 "LAUNCHER_R3_NAME": "FULL_RUNNER_PREP_V001R3_20260923.zip" in launch,
 "LAUNCHER_INCLUDED_LEDGER": "OUT_P4A_R3_FULL_HISTORY_COMPAT.zip" in launch and "C:\\PATH\\TO" not in launch,
 "SPEC_SPACE_AT_LEAST": "at least" in spec,
 "SPEC_R3_ALIAS_POLICY": "V001R2 MAJ-01 remediation" in spec and "nNumberOfLinks == 1" in spec,
}
bad=[k for k,v in checks.items() if not v]
for k,v in checks.items():print(f"{k}={'PASS' if v else 'FAIL'}")
print("STATIC_R3="+("PASS" if not bad else "FAIL"))
if bad:
 print("FAILED="+",".join(bad));raise SystemExit(2)
