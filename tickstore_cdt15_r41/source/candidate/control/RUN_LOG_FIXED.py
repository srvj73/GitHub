"""Owner log rule for operator CLIs invoked directly (R45 G13).

Every operator script logs into a fresh, run-owned folder under a FIXED ABSOLUTE root defined
here, never derived from the current directory, PATH, environment or arguments:

    C:\\Users\\silvi\\OneDrive\\Downloads\\TICKSTORE_RUNS\\<MODE>_<yyyyMMdd_HHmmss_fff>_<PID>\\RUN_LOG.txt

The launchers (RUN_TICKSTORE_FULL.ps1, qualification bootstraps) already create that folder and
pass --log-file; this helper covers direct `python <tool>.py ...` invocations.  `--help` creates
nothing.  Off Windows (portable tests) no folder is created and the run is marked as such.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path

LOG_ROOT = r'C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS'
MODE_RE = re.compile(r'[A-Z0-9_]{1,60}')


class _Tee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text); self.log.write(text); self.log.flush()
        return len(text)

    def flush(self):
        self.stream.flush(); self.log.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def run_dir_name(mode, now=None, pid=None):
    if MODE_RE.fullmatch(mode) is None:
        raise ValueError('RUN_LOG_MODE')
    now = now or dt.datetime.now()
    return '%s_%s_%03d_%d' % (mode, now.strftime('%Y%m%d_%H%M%S'), now.microsecond // 1000, os.getpid() if pid is None else pid)


def wants_fixed_log(argv):
    return not any(a in ('-h', '--help') for a in argv) and not any(a == '--log-file' or a.startswith('--log-file=')
                                                                     for a in argv)


def run_with_fixed_log(mode, entry, argv=None, *, root=None):
    """Run entry() with stdout/stderr teed into the fixed RUN_LOG.txt; returns entry's exit code.

    `root` exists only for unit tests; operators cannot redirect the log.
    """
    argv = sys.argv[1:] if argv is None else argv
    if not wants_fixed_log(argv) or (os.name != 'nt' and root is None):
        if os.name != 'nt' and root is None and wants_fixed_log(argv):
            print('RUN_LOG=NOT_WINDOWS_STDOUT_ONLY', flush=True)
        return entry()
    base = Path(root or LOG_ROOT)
    base.mkdir(parents=True, exist_ok=True)
    run_dir = base / run_dir_name(mode)
    run_dir.mkdir(parents=False, exist_ok=False)  # exclusive: a collision never reuses a folder
    log_path = run_dir / 'RUN_LOG.txt'
    log = open(log_path, 'x', encoding='utf-8', newline='')
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _Tee(out, log), _Tee(err, log)
    try:
        print('RUN_DIR=' + str(run_dir), flush=True)
        print('RUN_LOG=' + str(log_path), flush=True)
        code = entry()
        print('EXIT_CODE=' + str(code), flush=True)
        print('RUN_LOG=' + str(log_path), flush=True)
        return code
    finally:
        sys.stdout.flush(); sys.stderr.flush()
        sys.stdout, sys.stderr = out, err
        log.close()
