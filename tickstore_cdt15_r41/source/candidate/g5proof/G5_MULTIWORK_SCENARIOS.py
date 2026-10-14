"""G5 synthetic MULTIWORK scenarios on the exact packaged coordinator (sandbox only).

Derived from qual/R42_MULTIWORK_E2E.py.  Runs tickstore_full_multiwork._execute_admitted_multiwork
with real workers, dedicated publisher, Job, lease, named StopEvent and native zstd over a
disposable synthetic source in the production CSV format.  Only three parent-process seams
are replaced because the frozen 1550-day plan and ledger cannot describe a synthetic history:
  core.full_release_materials, core.load_ledgers, core.validate_full_plan.
The admission object is a technical stub; nothing here is a D4, CANARY or FULL execution.

ROW_GROUP fixture: one day holds more than four 262,144-row groups, so SAFE_STOP lands
inside a day with completed, durable row groups (BUILDING journal) and resume continues
that same day from the durable groups.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

BIG_ROWS = 1_100_000          # 4 full groups of 262,144 rows + 51,424
SMALL_ROWS = 1_500


def load(candidate):
    full = Path(candidate) / 'full'
    if str(full) not in sys.path:
        sys.path.insert(0, str(full))
    import tickstore_serial_runner as core
    import tickstore_full_multiwork as mw
    import test_full_serial_r9 as r9
    return core, mw, r9


def make_fixture(r9, root, plan):
    """plan: list of (date_key, rows).  Deterministic bytes for identical plans."""
    r, ref = r9.r, r9.r.ref
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    source = root / 'source'; source.mkdir()
    dest = root / 'dest'; dest.mkdir()
    scratch = root / 'scratch'; scratch.mkdir()
    days, months = [], {}
    by_month = {}
    for key, rows in plan:
        by_month.setdefault(key[:4] + '_' + key[4:6], []).append((key, rows))
    for month_id in sorted(by_month):
        path = source / ('WIN@N_ticks_%s.csv' % month_id)
        items = []
        with path.open('wb') as stream:
            for key, rows in sorted(by_month[month_id]):
                start = stream.tell()
                sem = hashlib.sha256(ref.semantic_preamble(int(key))); off = hashlib.sha256()
                midnight = ref.midnight_epoch_from_datekey(int(key))
                stamp = key[:4] + '.' + key[4:6] + '.' + key[6:]
                buf, pos, last = [], start, start
                for i in range(rows):
                    s, ms = divmod(i, 1000)
                    msc = (midnight + 43200 + s) * 1000 + ms
                    hh, rem = divmod(9 * 3600 + s, 3600); mm, ss = divmod(rem, 60)
                    line = ('WIN@N;%s %02d:%02d:%02d;%d;100000;100005;100010;7;7;%d\n'
                            % (stamp, hh, mm, ss, msc, i)).encode()
                    sem.update(ref.row_semantic_bytes((msc, 100000, 100005, 100010, 7, 7, i, 10800)))
                    off.update(ref.offset_bytes(pos))
                    last = pos
                    pos += len(line)
                    buf.append(line)
                stream.write(b''.join(buf))
                end = stream.tell()
                c = {'date_key': key, 'month_id': month_id, 'rows': str(rows), 'first_offset': str(start),
                     'last_offset': str(last), 'block_end_offset': str(end), 'source_day_bytes': str(end - start),
                     'semantic_sha256': sem.hexdigest(), 'offset_values_sha256': off.hexdigest(),
                     'offset_seconds_first': '10800', **{f: '0' for f in r9.COMPAT_FIELDS}}
                items.append(c); days.append(c)
        months[month_id] = {'month_id': month_id, 'source_sha256': r.sha256_file(path),
                            'source_size': str(path.stat().st_size), 'rows': str(sum(int(c['rows']) for c in items)),
                            'days': str(len(items)), 'core_codec_compatible': 'YES', 'p1e_lexical_compatible': 'YES',
                            'seal_integrity': 'PASS', 'summary_ledger_crosscheck': 'PASS'}
    days.sort(key=lambda c: c['date_key'])
    contract = {'schema': 'TICKSTORE_FULL_PLAN_CONTRACT_V001', 'ledger_sha256': r9.LEDGER_SHA,
                'days': len(days), 'months': len(months), 'rows': sum(int(c['rows']) for c in days),
                'source_bytes': sum(int(m['source_size']) for m in months.values()),
                'unique_month_source_bytes': sum(int(m['source_size']) for m in months.values()),
                'first_date': days[0]['date_key'], 'last_date': days[-1]['date_key'],
                'date_sequence_sha256': r.sha256_bytes(('\n'.join(c['date_key'] for c in days) + '\n').encode()),
                'month_sequence_sha256': r.sha256_bytes(('\n'.join(sorted(months)) + '\n').encode()),
                'naive_one_month_hash_per_day_bytes': sum(int(months[c['month_id']]['source_size']) for c in days),
                'dates_sorted_ascending': True, 'months_sorted_ascending': True, 'range_partition_exact': True}
    contract['full_plan_sha256'] = r.sha256_bytes(r.stable_json(contract))
    ids = {'runner_sha256': 'SYNTHETIC_G5', 'reference_sha256': 'SYNTHETIC_REFERENCE', 'spec_sha256': 'SYNTHETIC_SPEC'}
    cert = json.loads((r9.BASE / 'TICKSTORE_GATE_B_R8_FINAL_CERTIFICATE_20260924.json').read_text())
    return dict(root=root, source=source, dest=dest, scratch=scratch, days=days, months=months,
                contract=contract, ids=ids, cert=cert)


BIG_DAY = '20240110'
ROW_GROUP_PLAN = [('20231211', SMALL_ROWS), ('20231212', SMALL_ROWS), ('20240109', SMALL_ROWS), ('20240110', BIG_ROWS), ('20240111', SMALL_ROWS),
                  ('20240212', SMALL_ROWS), ('20240313', SMALL_ROWS)]


class Admission:
    """Technical stub: identity data only, no authority, records validate_full."""
    def __init__(self, run_id, bindings, max_workers, ram):
        self.instance = {'run_id': run_id, 'bindings': dict(bindings),
                         'resources': {'max_workers': max_workers, 'ram_target_percent': ram}}
        self.descriptor = {'code_manifest_sha256': 'G5' + '0' * 62, 'instance_sha256': 'G5' + '1' * 62}
        self.validated = []

    def validate_full(self, bindings, workers, max_workers, ram):
        self.validated.append({'workers': workers, 'max_workers': max_workers, 'ram': ram})

    def revalidate(self):
        return True


class Tee(io.TextIOBase):
    def __init__(self, a, b):
        self.a, self.b = a, b

    def write(self, s):
        self.a.write(s); self.b.write(s); return len(s)

    def flush(self):
        self.a.flush()


def published_commits(dest):
    return sorted(p.relative_to(dest).as_posix() for p in Path(dest).rglob('*.commit.json'))


def containers(dest):
    """Published day containers (row payload), keyed by relative path."""
    return {p.relative_to(dest).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest().upper()
            for p in sorted(Path(dest).rglob('*.pts2g')) if p.is_file()}


def scratch_journal(scratch, date_key):
    found = sorted(Path(scratch).rglob(date_key + '.journal.json'))
    if len(found) != 1:
        return None, None
    for _ in range(50):
        try:
            return found[0], json.loads(found[0].read_bytes())
        except (OSError, ValueError):
            time.sleep(0.02)
    return found[0], None


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
        def __init__(self, run_id, request=False):
            self.path = Path(os.environ['G5_OFFLINE_STOP_DIR']) / run_id; self.owner = not request
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


def run_engine(core, mw, r9, fx, run_id, workers, max_workers=22, ram=60, *, offline=False):
    patches = [
        (core, 'full_release_materials', lambda base: (fx['contract'], fx['cert'], fx['ids'])),
        (core, 'load_ledgers', lambda path: (fx['days'], fx['months'], r9.LEDGER_SHA)),
        (core, 'validate_full_plan', lambda days, months, ledger_sha, contract: days),
    ]
    if offline:
        patches += offline_patches(core, mw)
    saved = [(o, n, getattr(o, n)) for o, n, _ in patches]
    for o, n, v in patches:
        setattr(o, n, v)
    out = io.StringIO()
    result = {'run_id': run_id, 'workers_requested': workers}
    completions = []
    t0 = time.monotonic()
    try:
        bindings = core.full_gate_bindings(fx['source'], fx['dest'], fx['scratch'], fx['ids'], fx['contract'])
        admission = Admission(run_id, {k: v for k, v in bindings.items() if k not in ('schema', 'authorized')},
                              max_workers, ram)
        with contextlib.redirect_stdout(Tee(sys.stdout, out)):
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
    finally:
        for o, n, v in reversed(saved):
            setattr(o, n, v)
    text = out.getvalue()
    result['seconds'] = round(time.monotonic() - t0, 3)
    result['completions'] = completions
    result['stdout_tail'] = text[-8000:]
    result['markers'] = {m: (m in text) for m in (
        'SAFE_STOP=YES', 'SAFE_STOP_PROCESS_TREE=PASS', 'RESUME=YES', 'FINAL_READONLY_RECONCILE=PASS',
        'FULL_SOURCE_CONTINUOUS_PIN_SEAL=PASS', 'PRE_MULTIWORK_RECOVERY=PASS')}
    for line in text.splitlines():
        if line.startswith(('WORKERS_EFFECTIVE=', 'CPU_AVAILABLE_TO_PROCESS=')):
            k, v = line.split('=', 1); result[k] = v
    counts = [l for l in text.splitlines() if 'RESUMED=' in l and 'REUSED=' in l]
    if counts:
        last = dict(x.split('=', 1) for x in counts[-1].split() if '=' in x)
        result['final_counts'] = {k: last.get(k) for k in ('BUILT', 'REUSED', 'RESUMED')}
    result['commits'] = published_commits(fx['dest'])
    result['writer_lock_present'] = (Path(fx['dest']) / 'TICKSTORE_WRITER.lock').exists()
    result['children_alive'] = [p.name for p in mp.active_children()]
    return result


def request_stop_from_other_process(candidate, run_id, offline):
    if offline:
        (Path(os.environ['G5_OFFLINE_STOP_DIR']) / run_id).write_text('x')
        return {'returncode': 0, 'stdout': 'OFFLINE_FILE_STOP'}
    code = ('import sys;sys.path.insert(0,sys.argv[1]);from FULL_PROCESS_CONTROL import StopEvent;'
            'e=StopEvent(sys.argv[2],request=True);e.close();print("STOP_REQUESTED")')
    r = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(Path(candidate) / 'full'), run_id],
                       capture_output=True, text=True, timeout=60)
    return {'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}


def safe_stop_resume_row_group(candidate, work, artifacts, offline=False):
    """Named SAFE_STOP from another process inside a multi-group day; resume with other workers."""
    core, mw, r9 = load(candidate)
    work = Path(work); artifacts = Path(artifacts)
    big = BIG_DAY
    control = make_fixture(r9, work / 'CONTROL', ROW_GROUP_PLAN)
    rc = run_engine(core, mw, r9, control, 'G5CTL' + os.urandom(5).hex().upper(), '2', offline=offline)
    control_containers = containers(control['dest'])
    fx = make_fixture(r9, work / 'STOP_RESUME', ROW_GROUP_PLAN)
    run_id = 'G5SSR' + os.urandom(5).hex().upper()
    trig = {'fired': False}

    def watch():
        end = time.monotonic() + 1800
        while time.monotonic() < end and not trig.get('done'):
            path, j = scratch_journal(fx['scratch'], big)
            if j and j.get('state') == 'BUILDING' and len(j.get('completed_groups', [])) >= 1:
                trig['groups_at_request'] = len(j['completed_groups'])
                trig['commits_at_request'] = published_commits(fx['dest'])
                trig['detail'] = request_stop_from_other_process(candidate, run_id, offline)
                trig['fired'] = True
                return
            time.sleep(0.02)
    t = threading.Thread(target=watch, daemon=True); t.start()
    r1 = run_engine(core, mw, r9, fx, run_id, '1', offline=offline)
    trig['done'] = True; t.join(5)
    jpath, j_after = scratch_journal(fx['scratch'], big)
    if jpath is not None:
        (artifacts / 'JOURNAL_AT_SAFE_STOP.json').write_bytes(jpath.read_bytes())
    partial = next(iter(sorted(Path(fx['scratch']).rglob(big + '.pts2g.partial'))), None)
    partial_size = partial.stat().st_size if partial is not None else None
    before = list(r1['commits'])
    r2 = run_engine(core, mw, r9, fx, run_id, '2', offline=offline)
    resumed = containers(fx['dest'])
    groups_total = -(-BIG_ROWS // 262_144)
    durable = (j_after or {}).get('durable_end')
    checks = {
        'named_stop_honoured': bool(trig['fired'] and (trig.get('detail') or {}).get('returncode') == 0
                                    and r1['outcome'] == 'COOPERATIVE_SAFE_STOP' and r1['markers']['SAFE_STOP=YES']
                                    and r1['markers']['SAFE_STOP_PROCESS_TREE=PASS']),
        'partial_day_preserved': bool(j_after and j_after.get('state') == 'BUILDING'
                                      and 1 <= len(j_after.get('completed_groups', [])) < groups_total
                                      and isinstance(durable, int) and partial_size is not None
                                      and partial_size >= durable > 0),
        'resume_reused_completed_days': bool(before and int((r2.get('final_counts') or {}).get('REUSED') or 0)
                                             >= len(before)),
        'resume_completed_partial_day': bool(r2['outcome'] == 'PASS' and r2.get('code') == 0
                                             and int((r2.get('final_counts') or {}).get('RESUMED') or 0) >= 1
                                             and r2['markers']['FINAL_READONLY_RECONCILE=PASS']),
        'no_duplicate_or_lost_rows': bool(rc['outcome'] == 'PASS' and control_containers
                                          and resumed == control_containers
                                          and len(r2['commits']) == len(fx['days']) and set(before) <= set(r2['commits'])),
        'resume_worker_count_changed': bool(r1.get('WORKERS_EFFECTIVE') and r2.get('WORKERS_EFFECTIVE')
                                            and r1['WORKERS_EFFECTIVE'] != r2['WORKERS_EFFECTIVE']),
        'sandbox_only': all(Path(p).resolve().is_relative_to(work.resolve())
                            for p in (fx['source'], fx['dest'], fx['scratch'], control['dest'])),
    }
    obs = {'proof': 'SAFE_STOP_RESUME_ROW_GROUP', 'big_day': big, 'big_day_rows': BIG_ROWS, 'groups_total': groups_total,
           'trigger': {k: v for k, v in trig.items() if k != 'done'}, 'journal_after_stop_state': (j_after or {}).get('state'),
           'groups_durable_after_stop': len((j_after or {}).get('completed_groups', [])), 'durable_end': durable,
           'partial_size_after_stop': partial_size, 'commits_after_stop': before,
           'control': {k: rc.get(k) for k in ('outcome', 'seconds', 'WORKERS_EFFECTIVE')},
           'control_containers': control_containers, 'resumed_containers': resumed,
           'stop_run': {k: r1.get(k) for k in ('outcome', 'seconds', 'WORKERS_EFFECTIVE', 'final_counts', 'markers',
                                                'error', 'writer_lock_present', 'children_alive')},
           'resume_run': {k: r2.get(k) for k in ('outcome', 'seconds', 'WORKERS_EFFECTIVE', 'final_counts', 'markers',
                                                  'error', 'writer_lock_present', 'children_alive')}}
    (artifacts / 'SAFE_STOP_RESUME_OBSERVATION.json').write_text(json.dumps(obs, indent=1, sort_keys=True, default=str),
                                                                 encoding='utf-8')
    (artifacts / 'STOP_RUN_STDOUT_TAIL.txt').write_text(r1['stdout_tail'], encoding='utf-8')
    (artifacts / 'RESUME_RUN_STDOUT_TAIL.txt').write_text(r2['stdout_tail'], encoding='utf-8')
    return checks, 'SAFE_STOP named event from another process while day %s (%d rows, %d groups) is BUILDING; ' \
                   'resume with 2 workers vs 1; containers byte-equal to an uninterrupted control build' % (
                       big, BIG_ROWS, groups_total)


def engine_child(candidate, fixture_root, run_id, workers, out, offline):
    """One coordinator run in its own process (killed abruptly by the parent)."""
    core, mw, r9 = load(candidate)
    fx = json.loads((Path(fixture_root) / 'FIXTURE.json').read_text())
    for k in ('root', 'source', 'dest', 'scratch'):
        fx[k] = Path(fx[k])
    r = run_engine(core, mw, r9, fx, run_id, workers, offline=offline)
    Path(out).write_text(json.dumps(r, default=str), encoding='utf-8')
    return 0 if r['outcome'] == 'PASS' else 3


def _kill_tree(proc, offline):
    if offline:
        import signal
        os.killpg(proc.pid, signal.SIGKILL)
    else:
        import ctypes
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        if not k.TerminateProcess(ctypes.c_void_p(int(proc._handle)), 99):
            raise OSError('TERMINATE_PROCESS:%d' % ctypes.get_last_error())
    proc.wait(60)


def powerloss_emulated(candidate, work, artifacts, offline=False, kills=6, seed=44):
    """Abrupt death of the whole coordinator tree at seeded moments, then product recovery.

    POWERLOSS_EMULATED: process death with fsync'd state only.  Volatile disk caches and
    torn sectors of a physical power cut are NOT exercised; this never satisfies
    CHECKPOINT_POWERLOSS_RECOVERY.
    """
    import random
    core, mw, r9 = load(candidate)
    work = Path(work); artifacts = Path(artifacts)
    rnd = random.Random(seed)
    control = make_fixture(r9, work / 'CONTROL', ROW_GROUP_PLAN)
    rc = run_engine(core, mw, r9, control, 'G5PCT' + os.urandom(5).hex().upper(), '2', offline=offline)
    want = containers(control['dest'])
    fx = make_fixture(r9, work / 'KILLED', ROW_GROUP_PLAN)
    meta = {k: (str(v) if isinstance(v, Path) else v) for k, v in fx.items()}
    (fx['root'] / 'FIXTURE.json').write_text(json.dumps(meta, default=str), encoding='utf-8')
    run_id = 'G5PLE' + os.urandom(5).hex().upper()
    budget = max(4.0, float(rc.get('seconds') or 10.0))
    events = []
    env = dict(os.environ)
    if offline:
        env['G5_OFFLINE'] = '1'
    for i in range(kills):
        delay = rnd.uniform(0.15, 0.9) * budget
        out = work / ('CHILD_%02d.json' % i)
        args = [sys.executable, '-B', str(Path(__file__).resolve()), '--engine-child', str(candidate), str(fx['root']),
                run_id, rnd.choice(['1', '2']), str(out)] + (['--offline'] if offline else [])
        kw = {'start_new_session': True} if offline else {}
        proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        t0 = time.monotonic()
        while proc.poll() is None and time.monotonic() - t0 < delay:
            time.sleep(0.05)
        ev = {'iteration': i, 'delay_s': round(delay, 3), 'finished_before_kill': proc.poll() is not None}
        if proc.poll() is None:
            _kill_tree(proc, offline)
            ev['killed'] = True
        ev['exit'] = proc.returncode
        ev['commits_after'] = len(published_commits(fx['dest']))
        lock = Path(fx['dest']) / 'TICKSTORE_WRITER.lock'
        ev['writer_lock_after_kill'] = lock.exists()
        if lock.exists():
            # Product contract: forced termination is non-resumable until the operator
            # reconciles (FULL_WRITER_LOCK_RECONCILIATION_REQUIRED).  Prove the next start
            # fails closed, then emulate the reconciliation in the sandbox only.
            probe = run_engine(core, mw, r9, fx, run_id, '1', offline=offline)
            ev['restart_with_stale_lock'] = probe['outcome'] + ':' + str(probe.get('error', ''))[:200]
            ev['restart_failed_closed'] = probe['outcome'] == 'ERROR' and 'WRITER_LOCK_EXISTS' in str(probe.get('error'))
            lock.unlink()
            ev['reconciliation'] = 'SANDBOX_STALE_LOCK_REMOVED_AFTER_NO_LIVE_PROCESS'
        ev['transients'] = sorted(p.name for p in Path(fx['dest']).rglob('*') if p.name.endswith(('.partial', '.tmp')))
        events.append(ev)
        if ev['finished_before_kill']:
            break
    final = run_engine(core, mw, r9, fx, run_id, '2', offline=offline)
    got = containers(fx['dest'])
    killed = [e for e in events if e.get('killed')]
    checks = {
        'abrupt_tree_kills_executed': len(killed) >= 1,
        'stale_lock_fails_closed': all(e.get('restart_failed_closed', True) for e in killed),
        'recovery_completes': final['outcome'] == 'PASS' and final['markers']['FINAL_READONLY_RECONCILE=PASS'],
        'containers_equal_uninterrupted_control': bool(want) and got == want,
        'sandbox_only': Path(fx['dest']).resolve().is_relative_to(work.resolve()),
    }
    obs = {'proof': 'POWERLOSS_EMULATED', 'not_physical_power_loss': True, 'seed': seed, 'events': events,
           'control_seconds': rc.get('seconds'), 'final': {k: final.get(k) for k in (
               'outcome', 'error', 'seconds', 'final_counts', 'markers')},
           'containers_control': want, 'containers_after_recovery': got}
    (artifacts / 'POWERLOSS_EMULATED_OBSERVATION.json').write_text(
        json.dumps(obs, indent=1, sort_keys=True, default=str), encoding='utf-8')
    return checks


if __name__ == '__main__':
    if len(sys.argv) >= 7 and sys.argv[1] == '--engine-child':
        off = '--offline' in sys.argv
        if off:
            os.environ.setdefault('G5_OFFLINE_STOP_DIR', str(Path(sys.argv[3]) / 'OFFLINE_STOP'))
        raise SystemExit(engine_child(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], off))
    raise SystemExit('G5_MULTIWORK_SCENARIOS: library; use G5_PROOF_RUNNERS.py')
