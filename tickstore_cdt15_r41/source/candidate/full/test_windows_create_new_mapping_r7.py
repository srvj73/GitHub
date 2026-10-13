from pathlib import Path
import tickstore_serial_runner as r

def text(create_new, err):
    return str(r._windows_createfile_error(Path("X:/fixture.lock"), create_new, err))

assert text(True,80).startswith("SECURE_CREATE_EXISTS:")
assert text(True,183).startswith("SECURE_CREATE_EXISTS:")
assert "WIN_CREATEFILE_FAIL" in text(True,5) and "winerror=5" in text(True,5)
assert "WIN_CREATEFILE_FAIL" in text(False,80) and "winerror=80" in text(False,80)
assert "WIN_CREATEFILE_FAIL" in text(False,183) and "winerror=183" in text(False,183)
print("WINDOWS_CREATE_NEW_ERROR_MAPPING_R7=PASS")
