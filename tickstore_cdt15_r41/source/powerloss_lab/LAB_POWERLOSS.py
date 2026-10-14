"""CHECKPOINT_POWERLOSS_RECOVERY physical lab tooling — SOURCE_ONLY, never run on the production PC.

Origin decision 20261014: physical power loss of the storage is mandatory; process death,
Job Objects, TerminateProcess or VM power-off are NOT equivalent.  This file only prepares
the separate-laboratory experiment.  It never cuts power itself: the cut is performed by
the operator with an EXTERNAL, isolable supply and recorded by an EXTERNAL logger.

Subcommands
  preflight   read-only isolation/risk gate on the LAB machine (refuses the production PC,
              system/production volumes, missing sacrificial sentinel, missing external
              logger declaration and missing SEPARATE user authorization for the cut).
  plan        deterministic, seeded schedule of cut windows + uninterrupted control rounds.
  arm         workload on the sacrificial volume that holds inside the requested transaction
              window and announces READY_TO_CUT (beacon fsync'd); refuses without a PASS preflight.
  inspect     after controlled power-on, read-only inspection BEFORE any resume (NTFS dirty bit,
              outputs, journals, locks, checkpoint, live processes) -> round receipt.
  reconcile   after the product's own resume, compare against the control and classify the round.

Every ambiguity is BLOCKED, never PASS.  Status without an identified lab:
PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

# Production identity observed natively in R43/R44 (QUAL_RECEIPT PRECHECK): the lab must not be this PC.
PRODUCTION_VOLUME_SERIALS = {'C4B23CE5', '7435A171'}
PRODUCTION_PATH_MARKERS = (r'D:\Base CSV', r'\TICKSTORE\ACTIVE_DEPLOYMENT.json')
SENTINEL_NAME = 'TICKSTORE_POWERLOSS_SACRIFICIAL_VOLUME.txt'
SENTINEL_TEXT = 'SACRIFICIAL NTFS VOLUME FOR TICKSTORE PHYSICAL POWERLOSS LAB. ALL DATA MAY BE DESTROYED.'
WINDOWS = ('PRE_COMMIT_WRITE', 'POST_COMMIT_PRE_CHECKPOINT', 'JOURNAL_RECEIPT_UPDATE')
AUTH_SCHEMA = 'TICKSTORE_PHYSICAL_POWERLOSS_USER_AUTHORIZATION_V001'
LOGGER_SCHEMA = 'TICKSTORE_PHYSICAL_POWERLOSS_EXTERNAL_LOGGER_V001'
ROUND_SCHEMA = 'TICKSTORE_PHYSICAL_POWERLOSS_ROUND_RECEIPT_V001'


class LabBlocked(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise LabBlocked(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def canonical(obj):
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, default=str) + '\n').encode('utf-8')


# ----------------------------------------------------------------------------- environment probes (injectable)

class Env:
    """Read-only observations; tests inject a fake."""
    def volumes(self):
        import ctypes, string
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        out = {}
        for letter in string.ascii_uppercase:
            root = letter + ':\\'
            if not os.path.exists(root):
                continue
            fs = ctypes.create_unicode_buffer(261); label = ctypes.create_unicode_buffer(261); serial = ctypes.c_uint32()
            if k.GetVolumeInformationW(root, label, 261, ctypes.byref(serial), None, None, fs, 261):
                out[letter] = {'serial': '%08X' % serial.value, 'filesystem': fs.value, 'label': label.value}
        return out

    def system_drive(self):
        return os.environ.get('SystemDrive', 'C:')[0].upper()

    def pagefile_drives(self):
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management')
            vals = winreg.QueryValueEx(k, 'PagingFiles')[0]
            return {v.strip()[0].upper() for v in vals if v.strip() and v.strip()[1:2] == ':'}
        except OSError:
            return set()

    def read(self, path):
        return Path(path).read_bytes()

    def exists(self, path):
        return os.path.exists(path)


# ----------------------------------------------------------------------------- preflight

def preflight(volume, logger_path, logger_sha, auth_path, auth_sha, env=None, now=None):
    """Return the preflight record; raises LabBlocked on any isolation/authorization gap."""
    env = env or Env()
    now = now or time.time()
    v = str(volume).rstrip(':\\').upper()
    require(re.fullmatch('[A-Z]', v) is not None, 'LAB_VOLUME_LETTER')
    vols = env.volumes()
    require(not (PRODUCTION_VOLUME_SERIALS & {x['serial'] for x in vols.values()}),
            'LAB_IS_PRODUCTION_PC_OR_HAS_PRODUCTION_DISK_ATTACHED')
    require(not any(env.exists(m) for m in PRODUCTION_PATH_MARKERS), 'LAB_HAS_PRODUCTION_TICKSTORE_PATHS')
    require(v in vols, 'LAB_VOLUME_ABSENT')
    require(vols[v]['filesystem'] == 'NTFS', 'LAB_VOLUME_NOT_NTFS')
    require(v != env.system_drive(), 'LAB_VOLUME_IS_SYSTEM_DRIVE')
    require(v not in env.pagefile_drives(), 'LAB_VOLUME_HAS_PAGEFILE')
    require(v not in ('C', 'D'), 'LAB_VOLUME_LETTER_RESERVED_C_D')
    require('TICKSTORE_POWERLOSS' in vols[v]['label'].upper(), 'LAB_VOLUME_LABEL_NOT_SACRIFICIAL')
    sentinel = v + ':\\' + SENTINEL_NAME
    require(env.exists(sentinel) and env.read(sentinel).decode('utf-8', 'replace').strip() == SENTINEL_TEXT,
            'LAB_SACRIFICIAL_SENTINEL_MISSING')
    lraw = env.read(logger_path)
    require(sha(lraw) == logger_sha, 'LAB_LOGGER_DECLARATION_SHA')
    logger = json.loads(lraw)
    require(logger.get('schema') == LOGGER_SCHEMA and logger.get('outside_equipment_under_test') is True
            and logger.get('records') == ['cut_instant', 'restore_instant', 'round_id', 'supply_state'],
            'LAB_EXTERNAL_LOGGER_DECLARATION')
    araw = env.read(auth_path)
    require(sha(araw) == auth_sha, 'LAB_USER_AUTHORIZATION_SHA')
    auth = json.loads(araw)
    require(auth.get('schema') == AUTH_SCHEMA and auth.get('issuer') == 'OWNER_USER'
            and auth.get('authorizes') == 'PHYSICAL_POWER_INTERRUPTION_OF_SEPARATE_LAB_ONLY'
            and auth.get('lab_volume_serial') == vols[v]['serial']
            and auth.get('production_pc') is False, 'PHYSICAL_POWERLOSS_EXECUTION_NOT_AUTHORIZED')
    require(float(auth.get('valid_until_unix', 0)) >= now, 'PHYSICAL_POWERLOSS_AUTHORIZATION_EXPIRED')
    return {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_PREFLIGHT_V001', 'status': 'PASS', 'volume': v,
            'volume_serial': vols[v]['serial'], 'logger_sha256': logger_sha, 'authorization_sha256': auth_sha,
            'volumes_seen': sorted(vols), 'production_serials_absent': True}


# ----------------------------------------------------------------------------- plan

def plan(seed, repetitions=3, controls=2, hold_range=(2.0, 20.0)):
    """Deterministic schedule: every window x repetitions cut rounds, plus uninterrupted controls."""
    rnd = random.Random(int(seed))
    rounds = []
    for w in WINDOWS:
        for i in range(repetitions):
            rounds.append({'round_id': '%s_%02d' % (w, i + 1), 'window': w, 'cut': True,
                           'hold_seconds': round(rnd.uniform(*hold_range), 3), 'fixture_seed': rnd.randrange(1 << 30)})
    for i in range(controls):
        rounds.append({'round_id': 'CONTROL_%02d' % (i + 1), 'window': None, 'cut': False, 'hold_seconds': 0.0,
                       'fixture_seed': rnd.randrange(1 << 30)})
    rnd.shuffle(rounds)
    body = {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_PLAN_V001', 'seed': int(seed), 'windows': list(WINDOWS),
            'rounds': rounds}
    body['plan_sha256'] = sha(canonical({k: v for k, v in body.items() if k != 'plan_sha256'}))
    return body


# ----------------------------------------------------------------------------- inspection / reconciliation

def classify_inspection(obs):
    """Pre-resume state after power-on.  obs: dict from the native inspector (or a test)."""
    reasons = []
    if obs.get('live_tickstore_processes'):
        reasons.append('LIVE_PROCESSES_AFTER_POWER_ON')
    if obs.get('ntfs_dirty') is None:
        reasons.append('NTFS_DIRTY_STATE_UNKNOWN')
    if obs.get('external_logger_cut_recorded') is not True:
        reasons.append('EXTERNAL_CUT_NOT_EVIDENCED')
    if obs.get('round_id') != obs.get('logger_round_id'):
        reasons.append('LOGGER_ROUND_MISMATCH')
    for c in obs.get('containers', []):
        if c.get('status') not in ('COMMITTED_VERIFIED', 'ABSENT', 'PARTIAL_UNCOMMITTED'):
            reasons.append('AMBIGUOUS_CONTAINER:' + str(c.get('date_key')))
    if obs.get('checkpoint_parse') not in ('VALID', 'ABSENT'):
        reasons.append('CHECKPOINT_UNREADABLE_OR_TORN')
    return ('INSPECTED_READY_FOR_PRODUCT_RESUME' if not reasons else 'BLOCKED'), reasons


def reconcile_round(control_containers, resumed_containers, resume_outcome, inspection_status):
    """Final classification after the product's own resume.  Anything not exact is not PASS."""
    reasons = []
    if inspection_status != 'INSPECTED_READY_FOR_PRODUCT_RESUME':
        reasons.append('INSPECTION_NOT_CLEAN')
    if resume_outcome not in ('PASS', 'FAIL_CLOSED_RECONCILIATION_REQUIRED'):
        reasons.append('RESUME_OUTCOME_UNEXPECTED:' + str(resume_outcome))
    if resume_outcome == 'PASS':
        if set(resumed_containers) != set(control_containers):
            reasons.append('CONTAINER_SET_DIFFERS_LOSS_OR_DUPLICATE')
        diff = sorted(k for k in control_containers if resumed_containers.get(k) != control_containers[k])
        if diff:
            reasons.append('CONTAINER_BYTES_DIFFER:' + ','.join(diff[:5]))
    status = 'ROUND_PASS' if not reasons and resume_outcome == 'PASS' else (
        'ROUND_FAIL_CLOSED' if not reasons else 'ROUND_BLOCKED')
    return status, reasons


def round_receipt(plan_body, rnd, preflight_rec, inspection, reconciliation, artifacts):
    return {'schema': ROUND_SCHEMA, 'plan_sha256': plan_body['plan_sha256'], 'round': rnd,
            'preflight_sha256': sha(canonical(preflight_rec)), 'inspection': inspection,
            'reconciliation': reconciliation, 'artifacts': artifacts, 'physical_power_interruption': rnd['cut'],
            'equivalent_to_process_death': False, 'gate_verdict_issued': False}


def environment_status(lab_identified=False):
    return {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_ENVIRONMENT_V001',
            'PHYSICAL_POWERLOSS_ENVIRONMENT': 'IDENTIFIED_PENDING_PREFLIGHT' if lab_identified else 'NOT_AVAILABLE',
            'status': 'BLOCKED', 'execution_authorized': False,
            'reason': 'No isolated laboratory machine with an externally isolable supply and a sacrificial NTFS '
                      'volume has been identified; the origin specification does not authorize execution.'}


# ----------------------------------------------------------------------------- arm / inspect / reconcile (wired)
#
# Methodology: the frozen product engine (MULTIWORK, through the packaged G5 scenario harness)
# runs a seeded synthetic workload inside the sacrificial lab volume.  arm announces READY_TO_CUT
# after the planned hold and keeps an fsync'd BEACON of the observed transaction state every few
# tens of milliseconds, so the window in which the EXTERNAL cut landed is classified afterwards from
# durable evidence (a window not hit is a WINDOW_MISSED round, never a PASS).  inspect is read-only
# and runs BEFORE any resume; reconcile lets the PRODUCT resume by itself and compares the published
# containers byte-for-byte with an uninterrupted control built from the same seed.

LAB_ROOT_NAME = 'TICKSTORE_POWERLOSS_LAB'
BEACON = 'BEACON.jsonl'
ARM_RECORD = 'ARM.json'
INSPECTION = 'INSPECTION.json'
RECEIPT = 'ROUND_RECEIPT.json'
LOGGER_RECORD_SCHEMA = 'TICKSTORE_PHYSICAL_POWERLOSS_LOGGER_RECORD_V001'


def write_new(path, raw):
    with open(path, 'xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())


def lab_root(volume, plan_body):
    return Path(str(volume).rstrip(':\\').upper() + ':\\') / LAB_ROOT_NAME / plan_body['plan_sha256'][:16]


def load_plan(path, plan_sha):
    raw = Path(path).read_bytes()
    body = json.loads(raw)
    require(body.get('schema') == 'TICKSTORE_PHYSICAL_POWERLOSS_PLAN_V001', 'LAB_PLAN_SCHEMA')
    require(body.get('plan_sha256') == plan_sha == sha(canonical({k: v for k, v in body.items() if k != 'plan_sha256'})),
            'LAB_PLAN_SHA')
    return body


def plan_round(plan_body, round_id):
    found = [r for r in plan_body['rounds'] if r['round_id'] == round_id]
    require(len(found) == 1, 'LAB_ROUND_NOT_IN_PLAN')
    return found[0]


def bind_candidate(impl, code_manifest_sha256):
    """TESTED_CODE_EQUALS_PACKAGED_CODE for the lab: every runtime member of the extracted FINAL."""
    impl = Path(impl)
    raw = (impl / 'RUNTIME_CODE_MANIFEST.json').read_bytes()
    require(sha(raw) == code_manifest_sha256, 'LAB_CANDIDATE_MANIFEST_SHA')
    cand = impl / 'candidate'
    for f in json.loads(raw)['files']:
        member = cand / f['path']
        require(member.is_file() and sha(member.read_bytes()) == f['sha256'], 'LAB_CANDIDATE_MEMBER:' + f['path'])
    return cand


def load_scenarios(candidate):
    import importlib.util
    path = Path(candidate) / 'g5proof/G5_MULTIWORK_SCENARIOS.py'
    spec = importlib.util.spec_from_file_location('lab_g5_scenarios', path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def lab_workload(M, scale):
    """Deterministic workload: the packaged row-group plan repeated `scale` times in later months."""
    require(type(scale) is int and 1 <= scale <= 64, 'LAB_SCALE')
    plan_rows = list(M.ROW_GROUP_PLAN)
    for k in range(1, scale):
        year = 2025 + (k // 12); month = 1 + (k % 12)
        plan_rows += [('%04d%02d%02d' % (year, month, 10 + n), rows) for n, (_, rows) in enumerate(M.ROW_GROUP_PLAN)]
    return plan_rows


def observe(dest):
    """Observable transaction state of the destination (names only, no content)."""
    names = [p.name for p in Path(dest).rglob('*') if p.is_file()]
    return {'containers': sum(n.endswith('.pts2g') for n in names),
            'commits': sum(n.endswith('.commit.json') for n in names),
            'payload_partial': sum(n.endswith(('.pts2g.partial', '.journal.json.partial')) for n in names),
            'commit_partial': sum(n.endswith(('.commit.json.partial', '.commit.json.partial.stage')) for n in names),
            'manifest_partial': sum(n == 'TICKSTORE_GLOBAL_MANIFEST.json.partial' for n in names),
            'writer_lock': 'TICKSTORE_WRITER.lock' in names}


def window_of(obs):
    if obs['commit_partial'] or obs['manifest_partial']:
        return 'JOURNAL_RECEIPT_UPDATE'
    if obs['payload_partial']:
        return 'PRE_COMMIT_WRITE'
    if obs['writer_lock'] and obs['commits']:
        return 'POST_COMMIT_PRE_CHECKPOINT'
    return None


def arm(rnd, root, candidate, *, scale=1, offline=False, interval=0.05, max_seconds=3600.0, cut=None,
        plan_sha256='', preflight_rec=None):
    """Start the workload and beacon until power is lost (or `cut` emulates it in tests)."""
    import subprocess
    require(rnd['cut'] is True, 'LAB_CONTROL_ROUNDS_ARE_NOT_ARMED')
    M = load_scenarios(candidate)
    core, mw, r9 = M.load(candidate)
    rdir = Path(root) / rnd['round_id']
    rdir.mkdir(parents=True, exist_ok=False)
    fx = M.make_fixture(r9, rdir / 'ROUND', lab_workload(M, scale))
    meta = {k: (str(v) if isinstance(v, Path) else v) for k, v in fx.items()}
    (fx['root'] / 'FIXTURE.json').write_text(json.dumps(meta, default=str), encoding='utf-8')
    run_id = 'LABPL' + os.urandom(5).hex().upper()
    write_new(rdir / ARM_RECORD, canonical({'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_ARM_V001', 'round': rnd, 'scale': scale,
                                            'run_id': run_id, 'fixture_root': str(fx['root']), 'candidate': str(candidate),
                                            'plan_sha256': plan_sha256, 'preflight': preflight_rec or {},
                                            'started_unix_ns': time.time_ns()}))
    env = dict(os.environ)
    if offline:
        env['G5_OFFLINE'] = '1'
    args = [sys.executable, '-B', str(Path(M.__file__)), '--engine-child', str(candidate), str(fx['root']), run_id, '1',
            str(rdir / 'ENGINE_CHILD.json')] + (['--offline'] if offline else [])
    kw = {'start_new_session': True} if offline else {}
    proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    t0 = time.monotonic(); ready = False; status = 'RUNNING'
    with open(rdir / BEACON, 'ab', buffering=0) as beacon:
        while True:
            obs = observe(fx['dest']); elapsed = time.monotonic() - t0
            alive = proc.poll() is None
            if not ready and elapsed >= rnd['hold_seconds'] and alive:
                ready = True
                print('READY_TO_CUT ROUND=%s RUN_ID=%s' % (rnd['round_id'], run_id), flush=True)
            entry = {'t_unix_ns': time.time_ns(), 'elapsed_s': round(elapsed, 3), 'ready': ready,
                     'child_alive': alive, 'observation': obs, 'window': window_of(obs)}
            beacon.write(json.dumps(entry, sort_keys=True).encode() + b'\n'); os.fsync(beacon.fileno())
            if not alive:
                status = 'WORKLOAD_FINISHED_BEFORE_CUT' if not ready or proc.returncode == 0 else 'WORKLOAD_ENDED'
                break
            if ready and cut is not None:
                cut(proc)  # test-only emulation; physically the power is removed here
                status = 'CUT_EMULATED_FOR_TEST'
                break
            if elapsed > max_seconds:
                status = 'ARM_TIMEOUT'; break
            time.sleep(interval)
    print('ARM_STATUS=' + status, flush=True)
    return status, rdir


def read_beacon(rdir):
    entries, torn = [], 0
    for line in (Path(rdir) / BEACON).read_bytes().splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            torn += 1  # a torn final record is expected after a physical cut
    return entries, torn


def container_status(dest):
    out = []
    dest = Path(dest)
    days = {}
    for p in dest.rglob('*'):
        if p.is_file() and p.name[:8].isdigit():
            days.setdefault((p.parent, p.name[:8]), []).append(p)
    for (parent, key), files in sorted(days.items()):
        names = {f.name for f in files}
        container, commit = parent / (key + '.pts2g'), parent / (key + '.commit.json')
        if commit.name in names:
            try:
                c = json.loads(commit.read_bytes())
                ok = container.is_file() and sha(container.read_bytes()) == c.get('container_sha256')
            except (OSError, ValueError):
                ok = False
            status = 'COMMITTED_VERIFIED' if ok else 'COMMIT_WITHOUT_MATCHING_BYTES'
        else:
            status = 'PARTIAL_UNCOMMITTED'
        out.append({'date_key': key, 'status': status, 'files': sorted(names)})
    return out


class LabProbe(Env):
    """Post-power-on probes (read-only)."""
    def ntfs_dirty(self, volume):
        import subprocess
        r = subprocess.run(['fsutil', 'dirty', 'query', str(volume).rstrip(':\\') + ':'], capture_output=True, text=True)
        text = r.stdout.lower()
        if r.returncode != 0 or ' is ' not in text:
            return None
        return ' not dirty' not in text

    def pid_alive(self, pid):
        import ctypes
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        k.CloseHandle(h)
        return True


def inspect(rdir, volume, logger_record_path, logger_record_sha, env=None):
    """Read-only inspection BEFORE any resume; writes INSPECTION.json and returns it."""
    env = env or LabProbe()
    rdir = Path(rdir)
    arm_rec = json.loads((rdir / ARM_RECORD).read_bytes())
    lraw = env.read(logger_record_path)
    require(sha(lraw) == logger_record_sha, 'LAB_LOGGER_RECORD_SHA')
    lrec = json.loads(lraw)
    require(lrec.get('schema') == LOGGER_RECORD_SCHEMA, 'LAB_LOGGER_RECORD_SCHEMA')
    entries, torn = read_beacon(rdir)
    dest = Path(arm_rec['fixture_root']) / 'dest'
    lock = dest / 'TICKSTORE_WRITER.lock'
    live = []
    if lock.is_file():
        try:
            pid = json.loads(lock.read_bytes()).get('pid')
        except ValueError:
            pid = None
        if pid is None or env.pid_alive(pid):
            live.append({'lock_pid': pid})
    ready = [e for e in entries if e.get('ready')]
    last = entries[-1] if entries else {}
    obs = {'round_id': arm_rec['round']['round_id'], 'logger_round_id': lrec.get('round_id'),
           'external_logger_cut_recorded': bool(lrec.get('cut_instant')) and lrec.get('supply_state') == 'RESTORED',
           'ntfs_dirty': env.ntfs_dirty(volume), 'live_tickstore_processes': live,
           'containers': container_status(dest), 'checkpoint_parse': 'VALID',
           'beacon_records': len(entries), 'beacon_torn_records': torn, 'ready_announced': bool(ready),
           'last_beacon_window': last.get('window'), 'last_beacon_child_alive': last.get('child_alive')}
    for j in Path(arm_rec['fixture_root']).rglob('*.journal.json'):
        try:
            json.loads(j.read_bytes())
        except ValueError:
            obs['checkpoint_parse'] = 'TORN'
    status, reasons = classify_inspection(obs)
    if not ready:
        status, reasons = 'BLOCKED', reasons + ['READY_NEVER_ANNOUNCED']
    if last.get('child_alive') is not True:
        status, reasons = 'BLOCKED', reasons + ['WORKLOAD_NOT_ALIVE_AT_LAST_BEACON']
    record = {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_INSPECTION_V001', 'status': status, 'reasons': reasons,
              'observation': obs, 'logger_record_sha256': logger_record_sha, 'observed_window': last.get('window'),
              'planned_window': arm_rec['round']['window'],
              'window_hit': last.get('window') == arm_rec['round']['window'], 'resume_started_before_inspection': False}
    write_new(rdir / INSPECTION, canonical(record))
    return record


def reconcile(rdir, candidate, *, offline=False):
    """Product resume (never a manual repair of data) + byte comparison with an uninterrupted control."""
    rdir = Path(rdir)
    insp = json.loads((rdir / INSPECTION).read_bytes())
    arm_rec = json.loads((rdir / ARM_RECORD).read_bytes())
    M = load_scenarios(candidate)
    core, mw, r9 = M.load(candidate)
    if offline:  # portable harness seam only (tests); the lab always runs natively
        os.environ.setdefault('G5_OFFLINE_STOP_DIR', str(rdir / 'OFFLINE_STOP'))
        (Path(os.environ['G5_OFFLINE_STOP_DIR'])).mkdir(exist_ok=True)
    fx = json.loads((Path(arm_rec['fixture_root']) / 'FIXTURE.json').read_text())
    for k in ('root', 'source', 'dest', 'scratch'):
        fx[k] = Path(fx[k])
    events = []
    first = M.run_engine(core, mw, r9, fx, arm_rec['run_id'], '2', offline=offline)
    events.append({'attempt': 1, 'outcome': first['outcome'], 'error': str(first.get('error', ''))[:300]})
    resume_outcome, final = first['outcome'], first
    if first['outcome'] == 'ERROR' and 'WRITER_LOCK_EXISTS' in str(first.get('error')):
        resume_outcome = 'FAIL_CLOSED_RECONCILIATION_REQUIRED'
        # Documented reconciliation: allowed only because the inspection proved no live writer.
        require(insp['status'] == 'INSPECTED_READY_FOR_PRODUCT_RESUME' and not insp['observation']['live_tickstore_processes'],
                'LAB_LOCK_RECONCILIATION_WITHOUT_CLEAN_INSPECTION')
        (Path(fx['dest']) / 'TICKSTORE_WRITER.lock').unlink()
        final = M.run_engine(core, mw, r9, fx, arm_rec['run_id'], '2', offline=offline)
        events.append({'attempt': 2, 'after': 'STALE_LOCK_RECONCILED_NO_LIVE_PROCESS', 'outcome': final['outcome'],
                       'error': str(final.get('error', ''))[:300]})
    control = M.make_fixture(r9, rdir / 'CONTROL', lab_workload(M, arm_rec['scale']))
    rc = M.run_engine(core, mw, r9, control, 'LABCT' + os.urandom(5).hex().upper(), '2', offline=offline)
    require(rc['outcome'] == 'PASS', 'LAB_CONTROL_RUN_FAILED')
    want, got = M.containers(control['dest']), M.containers(fx['dest'])
    status, reasons = reconcile_round(want, got, 'PASS' if final['outcome'] == 'PASS' else final['outcome'], insp['status'])
    if status == 'ROUND_PASS' and resume_outcome == 'FAIL_CLOSED_RECONCILIATION_REQUIRED':
        status = 'ROUND_FAIL_CLOSED_RECONCILED'
    if not insp.get('window_hit'):
        status, reasons = 'ROUND_WINDOW_MISSED', reasons + ['OBSERVED_%s_PLANNED_%s' % (insp.get('observed_window'),
                                                                                    insp.get('planned_window'))]
    rec = {'status': status, 'reasons': reasons, 'events': events, 'containers_control': want,
           'containers_after_resume': got, 'final_markers': final.get('markers')}
    arts = []
    for name in (BEACON, ARM_RECORD, INSPECTION):
        arts.append({'path': name, 'sha256': sha((rdir / name).read_bytes())})
    receipt = round_receipt({'plan_sha256': arm_rec.get('plan_sha256', '')}, arm_rec['round'], arm_rec.get('preflight', {}),
                            insp, rec, arts)
    write_new(rdir / RECEIPT, canonical(receipt))
    return receipt


def aggregate(plan_body, root):
    """Coverage summary for the origin (never a G5 verdict)."""
    rows, covered = [], {w: 0 for w in WINDOWS}
    for rnd in plan_body['rounds']:
        p = Path(root) / rnd['round_id'] / RECEIPT
        st = json.loads(p.read_bytes())['reconciliation']['status'] if p.is_file() else ('CONTROL' if not rnd['cut'] else 'NOT_RUN')
        rows.append({'round_id': rnd['round_id'], 'window': rnd['window'], 'status': st})
        if st in ('ROUND_PASS', 'ROUND_FAIL_CLOSED_RECONCILED'):
            covered[rnd['window']] += 1
    complete = all(r['status'] in ('ROUND_PASS', 'ROUND_FAIL_CLOSED_RECONCILED', 'CONTROL') for r in rows)
    return {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_AGGREGATE_V001', 'plan_sha256': plan_body['plan_sha256'],
            'rounds': rows, 'windows_covered': covered,
            'status': 'PROPOSABLE_TO_ORIGIN' if complete else 'INCOMPLETE', 'gate_verdict_issued': False}


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('preflight')
    for k in ('volume', 'logger', 'logger-sha256', 'authorization', 'authorization-sha256', 'out'):
        p.add_argument('--' + k, required=True)
    q = sub.add_parser('plan'); q.add_argument('--seed', required=True, type=int); q.add_argument('--out', required=True)
    s = sub.add_parser('status'); s.add_argument('--out', required=True)
    r = sub.add_parser('arm')
    for k in ('volume', 'logger', 'logger-sha256', 'authorization', 'authorization-sha256', 'plan', 'plan-sha256',
              'round', 'candidate-impl', 'code-manifest-sha256'):
        r.add_argument('--' + k, required=True)
    r.add_argument('--scale', type=int, default=8)
    i = sub.add_parser('inspect')
    for k in ('volume', 'plan', 'plan-sha256', 'round', 'logger-record', 'logger-record-sha256'):
        i.add_argument('--' + k, required=True)
    c = sub.add_parser('reconcile')
    for k in ('volume', 'plan', 'plan-sha256', 'round', 'candidate-impl', 'code-manifest-sha256'):
        c.add_argument('--' + k, required=True)
    g = sub.add_parser('aggregate')
    for k in ('volume', 'plan', 'plan-sha256', 'out'):
        g.add_argument('--' + k, required=True)
    a = ap.parse_args(argv)
    if a.cmd in ('arm', 'inspect', 'reconcile', 'aggregate'):
        try:
            require(os.name == 'nt', 'LAB_WINDOWS_REQUIRED')
            body = load_plan(a.plan, a.plan_sha256)
            root = lab_root(a.volume, body)
            if a.cmd == 'arm':
                pre = preflight(a.volume, a.logger, a.logger_sha256, a.authorization, a.authorization_sha256)
                auth = json.loads(Path(a.authorization).read_bytes())
                require(auth.get('plan_sha256') == body['plan_sha256'], 'LAB_AUTHORIZATION_NOT_FOR_THIS_PLAN')
                cand = bind_candidate(a.candidate_impl, a.code_manifest_sha256)
                status, _ = arm(plan_round(body, a.round), root, cand, scale=a.scale, plan_sha256=body['plan_sha256'],
                                preflight_rec=pre)
                return 0 if status != 'WORKLOAD_FINISHED_BEFORE_CUT' else 3
            if a.cmd == 'inspect':
                plan_round(body, a.round)
                rec = inspect(root / a.round, a.volume, a.logger_record, a.logger_record_sha256)
                print('LAB_INSPECTION=' + rec['status'] + ' WINDOW_HIT=' + str(rec['window_hit']).upper())
                return 0 if rec['status'] == 'INSPECTED_READY_FOR_PRODUCT_RESUME' else 2
            if a.cmd == 'reconcile':
                plan_round(body, a.round)
                cand = bind_candidate(a.candidate_impl, a.code_manifest_sha256)
                rec = reconcile(root / a.round, cand)
                print('LAB_ROUND=' + rec['reconciliation']['status'])
                return 0 if rec['reconciliation']['status'] in ('ROUND_PASS', 'ROUND_FAIL_CLOSED_RECONCILED') else 2
            agg = aggregate(body, root)
            with open(a.out, 'xb') as f:
                f.write(canonical(agg))
            print('LAB_AGGREGATE=' + agg['status']); return 0
        except (LabBlocked, OSError, ValueError, KeyError) as exc:
            print('LAB_BLOCKED=' + type(exc).__name__ + ':' + str(exc)); return 2
    if a.cmd == 'status':
        Path(a.out).write_bytes(canonical(environment_status())); print('PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED')
        return 2
    if a.cmd == 'plan':
        Path(a.out).write_bytes(canonical(plan(a.seed))); print('PLAN_WRITTEN'); return 0
    try:
        rec = preflight(a.volume, a.logger, a.logger_sha256, a.authorization, a.authorization_sha256)
    except (LabBlocked, OSError, ValueError) as exc:
        print('LAB_PREFLIGHT_BLOCKED=' + str(exc)); return 2
    with open(a.out, 'xb') as f:
        f.write(canonical(rec))
    print('LAB_PREFLIGHT=PASS'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
