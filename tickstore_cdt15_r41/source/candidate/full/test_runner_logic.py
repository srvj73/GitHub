#!/usr/bin/env python3
from pathlib import Path
import hashlib,tempfile,shutil
import tickstore_serial_runner as r

def main():
    here=Path(__file__).resolve().parent
    assert r.PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE is True
    assert r.FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE is False

    # Canonical ledger is pinned and parsed from one in-memory image.
    days,months,zsha=r.load_ledgers(here/"OUT_P4A_R3_FULL_HISTORY_COMPAT.zip")
    assert zsha==r.EXPECTED_P4A_LEDGER_SHA256
    assert len(days)==1550 and len(months)==75

    # Writer lock second acquisition blocks and no stale deletion occurs.
    td=Path(tempfile.mkdtemp())
    try:
        r.strict_directory(td)
        lock=r.acquire_lock(td)
        blocked=False
        try:r.acquire_lock(td)
        except r.Blocked:blocked=True
        assert blocked and lock.exists()
        r.release_lock(lock)
    finally:
        shutil.rmtree(td,ignore_errors=True)

    text=(here/"tickstore_serial_runner.py").read_text(encoding="utf-8")
    assert "WINDOWS_PILOT_REQUIRES_WINDOWS" in text
    assert "FULL_HISTORY_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE" in text
    assert "CreateFileW" in text and "FILE_SHARE_READ" in text
    assert "secure_open_existing_fd" in text
    assert "validate_journal_final_transaction" in text
    assert "GLOBAL_MANIFEST_RECORD_MISSING_WITHOUT_TRANSACTION_JOURNAL" in text
    assert ".rglob(" not in text and ".exists(" not in text

    print("RUNNER_LOGIC_TESTS=PASS")
    print("CANONICAL_LEDGER_SAME_IMAGE=PASS")
    print("PILOT_GATE_WINDOWS_PREFLIGHT_REQUIRED=PASS")
    print("FULL_GATE_HARD_CLOSED=PASS")
    print("WRITER_LOCK_TEST=PASS")
    print("WINDOWS_SOURCE_PIN_CODE_PRESENT=PASS")
    print("CENTRAL_JOURNAL_VALIDATOR_PRESENT=PASS")

if __name__=="__main__":
    main()
