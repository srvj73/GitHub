"""R42: native end-to-end of the real MULTIWORK coordinator on synthetic data.

Runs ``tickstore_full_multiwork._execute_admitted_multiwork`` (the exact packaged
bytes) with real workers, real dedicated publisher, real Job/lease/StopEvent and
native zstd, over a disposable synthetic source in the production CSV format.

Only three parent-process seams are replaced, because the frozen 1550-day plan
and ledger cannot describe a synthetic history:
  core.full_release_materials -> (synthetic contract, frozen Gate B cert, synthetic ids)
  core.load_ledgers           -> (synthetic days, months, canonical ledger digest)
  core.validate_full_plan     -> identity on the synthetic plan
The admission object is a technical stub (no B06/chain authority is simulated);
everything after admission is the unmodified coordinator.

Scenarios (one per process):
  NOMINAL     AUTO workers, complete run, final read-only reconciliation PASS.
  STOP_RESUME native SAFE_STOP requested by ANOTHER process mid-run, then resume
              with a different worker count; no day published twice.
  WATCHDOG    main loop stalled on purpose; watchdog requests cooperative stop.
  RAM         RAM pressure decision forces the cooperative resource stop path.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path


def load(impl):
    full = Path(impl) / 'candidate/full'
    sys.path.insert(0, str(full))
    import tickstore_serial_runner as core
    import tickstore_full_multiwork as mw
    from test_full_serial_r9 import fixture, LEDGER_SHA
    return core, mw, fixture, LEDGER_SHA


def month_dates(n_months, days_per_month):
    out, year, month = [], 2024, 1
    for _ in range(n_months):
        for d in range(days_per_month):
            out.append('%04d%02d%02d' % (year, month, 10 + d))
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return tuple(out)


class Admission:
    """Technical stub: identity data only, no authority, records validate_full."""
    def __init__(self, run_id, bindings, max_workers, ram):
        self.instance = {'run_id': run_id, 'bindings': dict(bindings),
                         'resources': {'max_workers': max_workers, 'ram_target_percent': ram}}
        self.descriptor = {'code_manifest_sha256': 'R42' + '0' * 61, 'instance_sha256': 'R42' + '1' * 61}
        self.validated = []

    def validate_full(self, bindings, workers, max_workers, ram):
        self.validated.append({'workers': workers, 'max_workers': max_workers, 'ram': ram})

    def revalidate(self):
        return True


def build_fixture(fixture, root, n_months, days_per_month):
    root.mkdir(parents=True, exist_ok=False)
    source, dest, days, months, contract, ids, cert = fixture(root, dates=month_dates(n_months, days_per_month))
    scratch = root / 'scratch'
    scratch.mkdir()
    return dict(source=source, dest=dest, scratch=scratch, days=days, months=months,
                contract=contract, ids=ids, cert=cert)


def published_commits(dest):
    return sorted(str(p.relative_to(dest)) for p in Path(dest).rglob('*') if p.is_file() and p.name.endswith('.commit.json'))


def heartbeats(scratch, run_id):
    root = Path(scratch) / 'RUN_INSTANCES' / run_id
    out = []
    for p in sorted(root.glob('HEARTBEAT_*.json')):
        try:
            out.append(json.loads(p.read_bytes()))
        except ValueError:
            out.append({'unreadable': str(p)})
    return out


def run_engine(core, mw, LEDGER_SHA, fx, run_id, workers, max_workers, ram, *, hooks=None, offline=False):
    """Execute the real coordinator once; return a structured observation."""
    patches = [
        (core, 'full_release_materials', lambda base: (fx['contract'], fx['cert'], fx['ids'])),
        (core, 'load_ledgers', lambda path: (fx['days'], fx['months'], LEDGER_SHA)),
        (core, 'validate_full_plan', lambda days, months, ledger_sha, contract: days),
    ]
    if offline:
        patches += offline_patches(core, mw)
    for obj, name, value in (hooks or []):
        patches.append((obj, name, value))
    saved = [(o, n, getattr(o, n)) for o, n, _ in patches]
    for o, n, v in patches:
        setattr(o, n, v)
    bindings = None
    out = io.StringIO()
    result = {'run_id': run_id, 'workers_requested': workers}
    completions = []
    t0 = time.monotonic()
    try:
        bindings = core.full_gate_bindings(fx['source'], fx['dest'], fx['scratch'], fx['ids'], fx['contract'])
        admission = Admission(run_id, {k: v for k, v in bindings.items() if k not in ('schema', 'authorized')},
                              max_workers, ram)
        tee = Tee(sys.stdout, out)
        with contextlib.redirect_stdout(tee):
            try:
                code = mw._execute_admitted_multiwork(fx['source'], fx['dest'], fx['scratch'],
                                                      Path('SYNTHETIC_LEDGER.zip'), workers, max_workers, ram,
                                                      admission, completion=completions.append)
                result.update(outcome='PASS', code=code)
            except mw.CooperativeSafeStop:
                result.update(outcome='COOPERATIVE_SAFE_STOP')
            except BaseException as exc:
                result.update(outcome='ERROR', error=type(exc).__name__ + ':' + str(exc)[:2000],
                              traceback=traceback.format_exc()[-4000:])
        result['admission_validated'] = admission.validated
    finally:
        for o, n, v in reversed(saved):
            setattr(o, n, v)
    text = out.getvalue()
    result['seconds'] = round(time.monotonic() - t0, 3)
    result['completions'] = completions
    result['stdout_tail'] = text[-6000:]
    result['markers'] = {m: (m in text) for m in (
        'SAFE_STOP=YES', 'SAFE_STOP_PROCESS_TREE=PASS', 'RESUME=YES', 'FINAL_READONLY_RECONCILE=PASS',
        'FULL_SOURCE_CONTINUOUS_PIN_SEAL=PASS', 'TICKSTORE_FULL_MULTIWORK_STATUS=PASS',
        'SAFE_STOP_REASON=WATCHDOG_MAIN_LOOP_STALL', 'SAFE_STOP_REASON=RAM_PRESSURE', 'PUBLISHER_READY=YES')}
    for line in text.splitlines():
        if line.startswith(('WORKERS_EFFECTIVE=', 'CPU_AVAILABLE_TO_PROCESS=', 'CPU_LOGICAL=')):
            k, v = line.split('=', 1); result[k] = v
    result['progress_lines'] = sum(1 for l in text.splitlines() if l.startswith('PROGRESS ['))
    result['commits'] = published_commits(fx['dest'])
    result['writer_lock_present'] = (Path(fx['dest']) / 'TICKSTORE_WRITER.lock').exists()
    result['heartbeats'] = heartbeats(fx['scratch'], run_id)
    result['children_alive'] = [p.name for p in mp.active_children()]
    return result


class Tee(io.TextIOBase):
    def __init__(self, a, b):
        self.a, self.b = a, b

    def write(self, s):
        self.a.write(s); self.b.write(s); return len(s)

    def flush(self):
        self.a.flush()


# ----------------------------------------------------------------------------- offline harness check

def offline_patches(core, mw):
    """POSIX-only seams so the harness logic can be dry-run off Windows (never a PASS)."""
    import zlib

    class Codec:
        @staticmethod
        def compress(d, level=9): return zlib.compress(d, 9)
        @staticmethod
        def decompress(d): return zlib.decompress(d)

    class Lease:
        def __init__(self, dest): self.identity = {'pid': os.getpid(), 'creation_filetime': 0}
        def close(self): pass

    class Stop:
        # Named-event emulation: the object disappears when its creator closes it.
        def __init__(self, run_id, request=False):
            self.path = Path(os.environ['R42_OFFLINE_STOP_DIR']) / run_id; self.owner = not request
            if request: self.path.write_text('x')
        def requested(self): return self.path.exists()
        def close(self):
            if self.owner and self.path.exists(): self.path.unlink()

    class Job:
        def start(self, ctx, target, *, args=(), kwargs=None, name=None):
            p = ctx.Process(target=target, args=args, kwargs=kwargs or {}, name=name); p.start(); return p
        def memory_snapshot(self): return {'processes': [], 'working_set_bytes': 1, 'private_bytes': 1}
        def close(self): pass

    fork = mp.get_context('fork')

    class OsAsNt:
        name = 'nt'
        def __getattr__(self, attr): return getattr(os, attr)
    return [(mw, 'os', OsAsNt()), (core, 'require_windows_pilot_runtime', lambda: Codec), (mw, 'FullProcessLease', Lease),
            (mw, 'StopEvent', Stop), (mw, 'ProcessJob', Job),
            (mw.mp, 'get_context', lambda method=None: fork),
            (mw, 'windows_memory_status', lambda: {'total': 64 * 1024**3, 'available': 48 * 1024**3, 'load_percent': 25}),
            (core, 'windows_volume_identity', lambda p: {'serial': 'OFFLINE'})]


# ----------------------------------------------------------------------------- scenarios

def request_stop_from_other_process(impl, run_id, offline):
    if offline:
        (Path(os.environ['R42_OFFLINE_STOP_DIR']) / run_id).write_text('x')
        return {'returncode': 0, 'stdout': 'OFFLINE_FILE_STOP'}
    code = ('import sys;sys.path.insert(0,sys.argv[1]);from FULL_PROCESS_CONTROL import StopEvent;'
            'e=StopEvent(sys.argv[2],request=True);e.close();print("STOP_REQUESTED")')
    r = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(Path(impl) / 'candidate/full'), run_id],
                       capture_output=True, text=True, timeout=60)
    return {'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}


def after_first_commit(dest, action, timeout=600):
    """Background trigger: fire once the first canonical day is durable."""
    state = {'fired': False, 'commits_at_fire': None, 'detail': None}

    def run():
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            c = published_commits(dest)
            if c:
                state['commits_at_fire'] = len(c)
                state['detail'] = action()
                state['fired'] = True
                return
            time.sleep(0.05)
    t = threading.Thread(target=run, daemon=True); t.start()
    return state, t


def check(cond, name, checks):
    checks[name] = bool(cond)


def common_clean(r, checks, prefix):
    check(not r['children_alive'], prefix + '_NO_RESIDUAL_CHILDREN', checks)
    check(not r['writer_lock_present'], prefix + '_WRITER_LOCK_RELEASED', checks)


def scenario_nominal(core, mw, L, impl, work, offline):
    fx = build_fixture(FIXTURE, work / 'NOMINAL', n_months=8, days_per_month=2)
    r = run_engine(core, mw, L, fx, 'R42NOM' + uuid.uuid4().hex[:10].upper(), 'AUTO', 22, 60, offline=offline)
    checks = {}
    total = len(fx['days'])
    check(r['outcome'] == 'PASS' and r.get('code') == 0, 'NOMINAL_ENGINE_PASS', checks)
    check(len(r['completions']) == 1 and r['completions'][0]['status'] == 'PASS'
          and r['completions'][0]['days'] == total, 'NOMINAL_RECONCILIATION_RECEIPT', checks)
    check(r['markers']['FINAL_READONLY_RECONCILE=PASS'] and r['markers']['FULL_SOURCE_CONTINUOUS_PIN_SEAL=PASS'],
          'NOMINAL_FINAL_RECONCILE_AND_PIN_SEAL', checks)
    check(len(r['commits']) == total, 'NOMINAL_ALL_DAYS_PUBLISHED_ONCE', checks)
    eff = int(r.get('WORKERS_EFFECTIVE', 0)); avail = int(r.get('CPU_AVAILABLE_TO_PROCESS', 0))
    check(1 <= eff <= max(1, avail - 2) and eff <= 8, 'NOMINAL_AUTOCPU_BOUNDED', checks)
    hb = [h for h in r['heartbeats'] if h.get('status')]
    check(hb and hb[-1].get('status') == 'ENGINE_PASS_PENDING_POSTFULL' and 'eta_dhms' in hb[-1]
          and hb[-1].get('pipeline_complete') is False, 'NOMINAL_HEARTBEAT_FINAL_STATE', checks)
    check(r['progress_lines'] >= 2, 'NOMINAL_PROGRESS_BAR_EMITTED', checks)
    common_clean(r, checks, 'NOMINAL')
    return {'checks': checks, 'runs': [r]}


def scenario_stop_resume(core, mw, L, impl, work, offline):
    fx = build_fixture(FIXTURE, work / 'STOP_RESUME', n_months=16, days_per_month=1)
    run_id = 'R42SSR' + uuid.uuid4().hex[:10].upper()
    trig, t = after_first_commit(fx['dest'], lambda: request_stop_from_other_process(impl, run_id, offline))
    r1 = run_engine(core, mw, L, fx, run_id, '1', 22, 60, offline=offline)
    t.join(5)
    before = list(r1['commits'])
    r2 = run_engine(core, mw, L, fx, run_id, '2', 22, 60, offline=offline)
    checks = {}
    total = len(fx['days'])
    check(trig['fired'] and (trig['detail'] or {}).get('returncode') == 0, 'STOP_REQUESTED_BY_OTHER_PROCESS', checks)
    check(r1['outcome'] == 'COOPERATIVE_SAFE_STOP', 'STOP_COOPERATIVE_SAFE_STOP', checks)
    check(r1['markers']['SAFE_STOP=YES'] and r1['markers']['SAFE_STOP_PROCESS_TREE=PASS']
          and r1['markers']['RESUME=YES'], 'STOP_MARKERS_AFTER_CLEAN_TREE', checks)
    check(0 < len(before) < total, 'STOP_LANDED_MID_RUN', checks)
    check(not r1['completions'], 'STOP_NO_COMPLETION_RECEIPT', checks)
    hb1 = [h for h in r1['heartbeats'] if h.get('status') == 'SAFE_STOP']
    check(bool(hb1), 'STOP_HEARTBEAT_SAFE_STOP', checks)
    common_clean(r1, checks, 'STOP')
    check(r2['outcome'] == 'PASS' and len(r2['completions']) == 1, 'RESUME_ENGINE_PASS', checks)
    check(set(before) <= set(r2['commits']) and len(r2['commits']) == total, 'RESUME_NO_DUPLICATE_NO_LOSS', checks)
    reused = 'REUSED=' + str(len(before)) in r2['stdout_tail'] or any(
        ('REUSED=%d' % len(before)) in l for l in r2['stdout_tail'].splitlines())
    check(reused, 'RESUME_PREVIOUS_DAYS_REUSED_NOT_REBUILT', checks)
    check(r2.get('WORKERS_EFFECTIVE') != r1.get('WORKERS_EFFECTIVE'), 'RESUME_DIFFERENT_WORKER_COUNT', checks)
    common_clean(r2, checks, 'RESUME')
    return {'checks': checks, 'runs': [r1, r2], 'trigger': trig}


def scenario_watchdog(core, mw, L, impl, work, offline):
    fx = build_fixture(FIXTURE, work / 'WATCHDOG', n_months=12, days_per_month=1)
    armed = threading.Event()
    trig, t = after_first_commit(fx['dest'], lambda: armed.set() or {'armed': True})

    class FastWatchdog(mw.MainLoopWatchdog):
        def __init__(self, stop_event):
            super().__init__(stop_event, limit_seconds=2.0, poll_seconds=0.2)
    real = mw.windows_memory_status if not offline else (lambda: {'total': 64 * 1024**3, 'available': 48 * 1024**3, 'load_percent': 25})

    def stalling():
        if armed.is_set() and not getattr(stalling, 'done', False):
            stalling.done = True
            time.sleep(4.0)  # main loop stops ticking longer than the 2 s limit
        return real()
    r = run_engine(core, mw, L, fx, 'R42WDG' + uuid.uuid4().hex[:10].upper(), '1', 22, 60, offline=offline,
                   hooks=[(mw, 'MainLoopWatchdog', FastWatchdog), (mw, 'windows_memory_status', stalling)])
    checks = {}
    check(trig['fired'], 'WATCHDOG_STALL_INJECTED_MID_RUN', checks)
    check(r['outcome'] == 'COOPERATIVE_SAFE_STOP', 'WATCHDOG_COOPERATIVE_SAFE_STOP', checks)
    check(r['markers']['SAFE_STOP_REASON=WATCHDOG_MAIN_LOOP_STALL'], 'WATCHDOG_REASON_REPORTED', checks)
    check('WATCHDOG=MAIN_LOOP_STALL' in r['stdout_tail'] or r['markers']['SAFE_STOP_REASON=WATCHDOG_MAIN_LOOP_STALL'],
          'WATCHDOG_STALL_LINE', checks)
    common_clean(r, checks, 'WATCHDOG')
    return {'checks': checks, 'runs': [r]}


def scenario_ram(core, mw, L, impl, work, offline):
    fx = build_fixture(FIXTURE, work / 'RAM', n_months=12, days_per_month=1)
    armed = threading.Event()
    trig, t = after_first_commit(fx['dest'], lambda: armed.set() or {'armed': True})
    real = mw.memory_decision

    def decision(snapshot, memory, target):
        return 'SAFE_STOP' if armed.is_set() else real(snapshot, memory, target)
    r = run_engine(core, mw, L, fx, 'R42RAM' + uuid.uuid4().hex[:10].upper(), '1', 22, 60, offline=offline,
                   hooks=[(mw, 'memory_decision', decision)])
    checks = {}
    check(trig['fired'], 'RAM_PRESSURE_INJECTED_MID_RUN', checks)
    check(r['outcome'] == 'COOPERATIVE_SAFE_STOP', 'RAM_COOPERATIVE_SAFE_STOP', checks)
    check(r['markers']['SAFE_STOP_REASON=RAM_PRESSURE'], 'RAM_REASON_REPORTED', checks)
    common_clean(r, checks, 'RAM')
    return {'checks': checks, 'runs': [r]}


SCENARIOS = {'NOMINAL': scenario_nominal, 'STOP_RESUME': scenario_stop_resume,
             'WATCHDOG': scenario_watchdog, 'RAM': scenario_ram}
FIXTURE = None


def main():
    global FIXTURE
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--impl', required=True); ap.add_argument('--work', required=True)
    ap.add_argument('--scenario', required=True, choices=sorted(SCENARIOS)); ap.add_argument('--out', required=True)
    ap.add_argument('--offline', action='store_true')
    a = ap.parse_args()
    if not a.offline and os.name != 'nt':
        raise SystemExit('R42_WINDOWS_REQUIRED')
    if a.offline:
        os.environ['R42_OFFLINE_STOP_DIR'] = str(Path(a.work) / 'OFFLINE_STOP')
        Path(os.environ['R42_OFFLINE_STOP_DIR']).mkdir(parents=True, exist_ok=True)
    core, mw, FIXTURE, L = load(a.impl)
    try:
        res = SCENARIOS[a.scenario](core, mw, L, a.impl, Path(a.work), a.offline)
        res['status'] = 'PASS' if res['checks'] and all(res['checks'].values()) else 'FAIL'
    except BaseException as exc:
        res = {'status': 'ERROR', 'error': type(exc).__name__ + ':' + str(exc), 'traceback': traceback.format_exc()}
    res['scenario'] = a.scenario
    res['mode'] = 'OFFLINE_HARNESS_CHECK' if a.offline else 'NATIVE_WINDOWS'
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True, default=str), encoding='utf-8')
    print('R42_SCENARIO %s=%s %s' % (a.scenario, res['status'],
          ' '.join('%s=%s' % (k, 'PASS' if v else 'FAIL') for k, v in res.get('checks', {}).items())), flush=True)
    return 0 if res['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
