"""Single menu/PowerShell entry into qualified D4, continuation and MULTIWORK."""
from __future__ import annotations
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from D4_FIRST_ADMISSION_PREP import require, strict_json
from FULL_RELEASE_CHAIN import ReleaseChain, STAGES

REQUIRED_PREFIX = {'D4': 'B07', 'D4Close': 'B07', 'D5': 'D4', 'CANARY': 'D5',
                   'FULL_PREP': 'CANARY', 'FULL_ADMIT': 'FULL_PREP', 'FULL': 'FULL_ADMISSION', 'FULL_READMIT': 'FULL_ADMISSION', 'Stop': 'FULL_ADMISSION'}
D4_PARAMETERS = {
    'FinalCodeManifestPath', 'FinalCodeManifestSha', 'CompletenessReceiptPath',
    'B07ReceiptPath', 'FirstAdmissionReviewPackPath', 'PredecessorEvidenceDir',
    'PolicyRoot', 'OriginCapturePath', 'PreparationBindingSha',
    'ReviewVerdictPath', 'PolicyAdmissionReceiptPath', 'AdapterDir',
}


def d4_command(instance, candidate, *, resume=False, policy_reconciliation='', policy_reconciliation_sha256=''):
    params = instance.get('d4_parameters')
    require(isinstance(params, dict) and set(params) == D4_PARAMETERS, 'D4_PARAMETER_SET')
    # R44-B2C: the D4 effect needs the CURRENT origin policy reconciliation of this stage
    # invocation; the record named at instance preparation is provenance only.
    require(isinstance(policy_reconciliation, str) and bool(policy_reconciliation)
            and re.fullmatch('[0-9A-F]{64}', str(policy_reconciliation_sha256)) is not None,
            'D4_CURRENT_POLICY_RECONCILIATION_REQUIRED')
    params = dict(params, OriginCapturePath=policy_reconciliation)
    command = [str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),
               '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
               str(candidate/'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1'),
               '-ResumeAdmittedRun' if resume else '-FirstAdmission', '-ExecuteD4']
    if resume: command.append('-ResumeAfterSafeStop')
    for name in sorted(params):
        value = params[name]
        require(isinstance(value, str) and bool(value) and '\x00' not in value, 'D4_PARAMETER:' + name)
        command.extend(['-' + name, value])
    command.extend(['-OriginReconciliationSha256', policy_reconciliation_sha256])
    return command


def run_wrapper_cooperatively(command):
    """Run the D4 wrapper and return ITS outcome, also across Ctrl+C (R45 G7).

    The wrapper shares this console, so Ctrl+C reaches it directly and drives its own durable
    SAFE_STOP (STOP file, child result).  If this parent also took the KeyboardInterrupt,
    subprocess.call() would kill the wrapper 0.25 s later and cut that path; so the parent
    ignores SIGINT only while the wrapper runs (the CRT-level ignore is not inherited by the
    child) and restores its handler afterwards.
    """
    import signal
    import threading
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        return subprocess.call(command)
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


class _Tee:
    """Mirror console output into the run-owned RUN_LOG.txt (append, flushed per write)."""
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text); self.log.write(text); self.log.flush()
        return len(text)

    def flush(self):
        self.stream.flush(); self.log.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


MONITOR_STALE_FACTOR = 3
MONITOR_LOOP_STALL_SECONDS = 600


def _heartbeats(instance):
    """Read-only discovery of this instance's heartbeat files; never creates anything."""
    found = []
    scratch = Path(instance['bindings']['scratch_root'])/'RUN_INSTANCES'/instance['run_id']
    runs = Path(instance['state_path']).parent.parent/'runs'
    candidates = list(scratch.glob('HEARTBEAT_*.json')) if scratch.is_dir() else []
    candidates += list(runs.glob('*/STAGE_HEARTBEAT.json')) if runs.is_dir() else []
    for path in candidates:
        try:
            item = json.loads(path.read_bytes().decode('utf-8'))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(item, dict) and item.get('run_id') == instance['run_id']:
            found.append((int(item.get('observed_unix_ns') or 0), str(path), item))
    return sorted(found)


def monitor_line(item, now_ns):
    """One transparent progress line plus heartbeat/loop watchdog verdicts."""
    import FULL_OBSERVABILITY as obs
    age = max(0.0, (now_ns - int(item.get('observed_unix_ns') or 0)) / 1e9)
    interval = 5.0
    status = item.get('status')
    watchdog = 'OK'
    if status == 'RUNNING' and age > MONITOR_STALE_FACTOR * interval + 5:
        watchdog = 'HEARTBEAT_STALE'
    tick = item.get('loop_tick_unix_ns')
    loop_age = (now_ns - int(tick)) / 1e9 if isinstance(tick, int) else None
    if status == 'RUNNING' and item.get('phase') == 'PIPELINE' and loop_age is not None \
            and loop_age > MONITOR_LOOP_STALL_SECONDS:
        watchdog = 'MAIN_LOOP_STALL'
    pct = item.get('committed_percent')
    return ('MONITOR ' + obs.bar(pct) + ' PCT=' + ('%7.3f%%' % pct if isinstance(pct, (int, float)) else 'UNKNOWN')
            + ' PHASE=' + str(item.get('phase')) + ' STATUS=' + str(status)
            + ' ROWS=' + str(item.get('committed_rows')) + '/' + str(item.get('total_rows'))
            + ' DAYS=' + str(item.get('committed_days')) + ' MONTHS=' + str(item.get('months_published'))
            + '/' + str(item.get('total_months'))
            + ' WORKERS=' + str(item.get('active_workers')) + '/' + str(item.get('worker_limit'))
            + ' ELAPSED=' + str(item.get('elapsed_dhms')) + ' ETA=' + str(item.get('eta_dhms', 'UNKNOWN'))
            + ' HEARTBEAT_AGE_S=' + str(int(age))
            + ' LOOP_AGE_S=' + (str(int(loop_age)) if loop_age is not None else 'NA')
            + ' WATCHDOG=' + watchdog), watchdog


def monitor(a):
    """Read-only: hash-bound chain/instance discovery, then heartbeat polling."""
    import time
    from D4_FIRST_ADMISSION_PREP import Reads
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'full'))
    with Reads() as reads:
        d = strict_json(reads.read(a.chain_file, a.chain_sha256))
        require(d.get('schema') == 'TICKSTORE_EXECUTION_CHAIN_V001', 'MONITOR_CHAIN_SCHEMA')
        instance = strict_json(reads.read(d['instance_path'], d['instance_sha256']))
    require(instance.get('schema') == 'TICKSTORE_FULL_INSTANCE_V001', 'MONITOR_INSTANCE_SCHEMA')
    print('MONITOR_RUN_ID=' + instance['run_id'] + ' AUTHORITY=NONE READ_ONLY=YES', flush=True)
    while True:
        beats = _heartbeats(instance)
        if not beats:
            print('MONITOR=NO_HEARTBEAT_YET', flush=True)
        else:
            _, path, item = beats[-1]
            line, verdict = monitor_line(item, time.time_ns())
            print(line + ' FILE=' + path, flush=True)
            if item.get('status') != 'RUNNING':
                print('MONITOR_FINAL_STATUS=' + str(item.get('status')), flush=True)
                return 0
        if a.monitor_once:
            return 0
        time.sleep(max(2, int(a.monitor_interval)))


def run(a):
    root = Path(__file__).resolve().parent.parent
    if a.stage == 'Monitor':
        return monitor(a)
    if a.stage in ('D5', 'CANARY', 'FULL_PREP', 'FULL_ADMIT', 'FULL', 'FULL_READMIT'):
        import FULL_STAGE_CONTINUATION as continuation
        return continuation.run(a)
    until = REQUIRED_PREFIX.get(a.stage)
    if a.stage == 'Check':
        # Discovery is bounded to the descriptor whose digest is supplied separately.
        from D4_FIRST_ADMISSION_PREP import Reads, sha
        with Reads() as reads:
            d = strict_json(reads.read(a.chain_file, a.chain_sha256))
            present = tuple(k for k in STAGES if k in d.get('receipts', {}))
            require(present and present == STAGES[:len(present)], 'CHAIN_PREFIX_GAP')
            until = present[-1]
    require(until is not None, 'RUNNER_STAGE')
    with ReleaseChain(a.chain_file, a.chain_sha256, a.b06_sha256, root, until=until) as admission:
        i = admission.instance
        if a.stage == 'Check':
            print(json.dumps({'schema': 'TICKSTORE_FULL_CHECK_V001', 'status': 'PASS_READ_ONLY',
                  'last_proven_stage': until, 'production_started': False,
                  'code_manifest_sha256': admission.descriptor['code_manifest_sha256']}))
            return 0
        if a.stage in ('D4', 'D4Close'):
            from FULL_D4_CLOSURE import close_d4
            if a.stage == 'D4Close':
                close_d4(admission)
                return 0
            command = d4_command(i, root, resume=a.resume, policy_reconciliation=a.policy_reconciliation,
                                 policy_reconciliation_sha256=a.policy_reconciliation_sha256)
            admission.revalidate()
            # Existing qualified wrapper owns DPAPI/HMAC, first admission and D4_ONLY dispatch.
            code = run_wrapper_cooperatively(command)
            if code == 0:
                close_d4(admission)
            return code
        sys.path.insert(0, str(root/'full'))
        if a.stage == 'Stop':
            from FULL_PROCESS_CONTROL import StopEvent
            event = StopEvent(i['run_id'], request=True)
            event.close()
            print('SAFE_STOP_REQUESTED=YES; COMPLETION_REQUIRES_RUNNER_RECEIPT', flush=True)
            return 0
        require(False, 'RUNNER_UNDISPATCHED_STAGE')


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--stage', required=True, choices=('Check', 'Monitor', *REQUIRED_PREFIX))
    for name in ('chain-file', 'chain-sha256', 'b06-sha256'): ap.add_argument('--' + name, required=True)
    # R44-B2C: current origin policy reconciliation (record + SHA-256 supplied separately).
    ap.add_argument('--policy-reconciliation', default='')
    ap.add_argument('--policy-reconciliation-sha256', default='')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--close-only', action='store_true')
    ap.add_argument('--workers', default='AUTO')
    ap.add_argument('--log-file', default='')
    ap.add_argument('--monitor-interval', type=int, default=10)
    ap.add_argument('--monitor-once', action='store_true')
    a = ap.parse_args(argv)
    log = None
    if a.log_file:
        # The launcher creates a fresh run-owned folder at a fixed absolute root.
        log = open(a.log_file, 'a', encoding='utf-8', newline='')
        sys.stdout = _Tee(sys.stdout, log); sys.stderr = _Tee(sys.stderr, log)
    try:
        return _main(a)
    finally:
        if log is not None:
            sys.stdout.flush(); sys.stderr.flush()
            sys.stdout, sys.stderr = sys.stdout.stream, sys.stderr.stream
            log.close()


def _main(a):
    try:
        require(not a.close_only or a.stage in ('D5','CANARY','FULL_PREP','FULL_ADMIT','FULL'), 'CLOSE_ONLY_STAGE')
        require(not a.resume or a.stage == 'D4', 'RESUME_SWITCH_D4_ONLY')
        return run(a)
    except KeyboardInterrupt:
        print('FULL_RUNNER_INTERRUPTED=YES', flush=True); return 130
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print('FULL_RUNNER_BLOCKED=' + str(exc), flush=True); return 2


if __name__ == '__main__':
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log('FULL_RUNNER', main))
