"""G5 typed target-proof runners (packaged; isolated native qual, never gate verdict).

Original Opus runtime implementations are exercised on run-owned test data with
real filesystem effects and distinct Windows readback receipts, not operational
D4 or Stage B. A test fixture cannot substitute a native downstream gate.
The runner writes EVIDENCE/PROOFS/<PROOF>/PROOF_RECEIPT.json and sealed artifacts.
The receipt names this file, its SHA-256 and the function, so the consumer
(FULL_QUALIFICATION_CONTRACT) can bind it to the runtime code manifest.

None of these runs is D4, Stage B, CANARY or FULL production.  CHECKPOINT_POWERLOSS_RECOVERY
has no runner: POWERLOSS_EMULATED (abrupt process-tree death) is reported separately and
never counts as physical power-loss evidence.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import multiprocessing as mp
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import types
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent
RECEIPT_SCHEMA = 'TICKSTORE_G5_TARGET_PROOF_RECEIPT_V001'
POWERLOSS_EMULATED_KIND = 'TICKSTORE_G5_POWERLOSS_EMULATED_V001'
KINDS = {
    'PROCESS_TREE_CRASH_CONTAINMENT': ('TICKSTORE_G5_PROOF_PROCESS_TREE_CRASH_V001', 'proof_process_tree_crash'),
    'SAFE_STOP_RESUME_ROW_GROUP': ('TICKSTORE_G5_PROOF_SAFE_STOP_RESUME_V001', 'proof_safe_stop_resume'),
    'PS51_INSTALL_MENU': ('TICKSTORE_G5_PROOF_PS51_INSTALL_MENU_V001', 'proof_ps51_install_menu'),
    'D4_REAL_ISOLATED_PATH_NATIVE': ('TICKSTORE_G5_PROOF_D4_ISOLATED_REAL_CODE_V001', 'proof_d4_isolated_real_code'),
    'STAGE_B_REAL_ISOLATED_PATH_NATIVE': ('TICKSTORE_G5_PROOF_STAGE_B_ISOLATED_REAL_CODE_V001', 'proof_stage_b_isolated_real_code'),
    'POWERLOSS_EMULATED': (POWERLOSS_EMULATED_KIND, 'powerloss_emulated'),
}
PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
REAL_MENU = r'D:\Base CSV\Scripts\Biblioteca\MENU.py'
REAL_BAT = 'D:\\Base CSV\\Manuten\u00e7\u00e3o Base de Dados.bat'
SANDBOX_PREFIX = 'CDT15_R41_WRITER_QUAL_'    # enforced by MENU_OFFICIAL_WRITER QUALIFICATION layout
SENTINEL = b'CDT15_R41_OFFICIAL_WRITER_QUALIFICATION_SANDBOX_ONLY_V001\n'
FIXTURE_MENU = b'# R41 sandbox fixture: historical MENU stand-in\nprint("old menu")\n'
FIXTURE_BAT = b'@echo off\r\nrem R41 sandbox fixture\r\n'
WRITER_REL = 'implementation_v001/candidate/control/MENU_OFFICIAL_WRITER.py'
INSTALLER_REL = 'implementation_v001/candidate/control/INSTALL_TICKSTORE_FULL.ps1'
MENU_REL = 'implementation_v001/candidate/menu/MENU.py'
STAGE_B_SUITES = {'test_stageb_full_physical_closure.py': 12, 'test_stage_canary_physical_publication.py': 7,
                  'test_full_postverify_readback.py': 17, 'test_canary_receipt_readback.py': 13}
D4_SHADOW = r'\\?\GLOBALROOT\Device\G5_SYNTHETIC_NO_SNAPSHOT'


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def sha_file(p):
    return sha_bytes(Path(p).read_bytes())


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=True, default=str) + '\n', encoding='utf-8')


def within(path, root):
    return Path(os.path.abspath(path)).resolve().is_relative_to(Path(os.path.abspath(root)).resolve())


def volume_fs(path):
    if os.name != 'nt':
        return 'POSIX_OFFLINE'
    import ctypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    root = os.path.splitdrive(os.path.abspath(path))[0] + '\\'
    fs = ctypes.create_unicode_buffer(261)
    ok = k.GetVolumeInformationW(ctypes.c_wchar_p(root), None, 0, None, None, None, fs, 261)
    return fs.value if ok else 'UNKNOWN:%d' % ctypes.get_last_error()


def snapshot_real_targets(local_appdata):
    out = {}
    items = {'menu': REAL_MENU, 'bat': REAL_BAT}
    if local_appdata:
        tick = os.path.join(local_appdata, 'TICKSTORE')
        items.update(active=os.path.join(tick, 'ACTIVE_DEPLOYMENT.json'), transaction=os.path.join(tick, 'MENU_TRANSACTION'),
                     writer_lock=os.path.join(tick, 'MENU_WRITER.lock'), candidates=os.path.join(tick, 'Candidates'))
    for key, path in items.items():
        if os.path.isfile(path):
            out[key] = {'status': 'PRESENT', 'sha256': sha_file(path)}
        elif os.path.isdir(path):
            out[key] = {'status': 'PRESENT_DIR', 'entries': sorted(os.listdir(path))}
        else:
            out[key] = {'status': 'ABSENT'}
    return out


# ----------------------------------------------------------------------------- PROCESS_TREE_CRASH_CONTAINMENT

def _tree_child(marker_dir):
    """Job member: starts a grandchild, records both PIDs, then waits to be killed."""
    g = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(900)'])
    tmp = Path(marker_dir) / 'CHILD.json.tmp'
    tmp.write_text(json.dumps({'child_pid': os.getpid(), 'grandchild_pid': g.pid}), encoding='utf-8')
    os.replace(tmp, Path(marker_dir) / 'CHILD.json')
    time.sleep(900)


def tree_coordinator(marker_dir):
    sys.path.insert(0, str(CANDIDATE / 'full'))
    from FULL_PROCESS_CONTROL import ProcessJob
    job = ProcessJob()  # never closed explicitly: the coordinator is killed abruptly
    proc = job.start(mp.get_context('spawn'), _tree_child, args=(str(marker_dir),), name='G5-TREE-CHILD')
    tmp = Path(marker_dir) / 'COORDINATOR.json.tmp'
    tmp.write_text(json.dumps({'coordinator_pid': os.getpid(), 'child_pid': proc.pid}), encoding='utf-8')
    os.replace(tmp, Path(marker_dir) / 'COORDINATOR.json')
    time.sleep(900)
    return 0


def proof_process_tree_crash(a, out):
    import ctypes
    from ctypes import wintypes as w
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; k.WaitForSingleObject.restype = w.DWORD
    k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]; k.IsProcessInJob.restype = w.BOOL
    k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]; k.GetExitCodeProcess.restype = w.BOOL
    k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]; k.TerminateProcess.restype = w.BOOL
    k.CloseHandle.argtypes = [w.HANDLE]
    access = 0x00100000 | 0x1000 | 0x0001  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION | TERMINATE (cleanup only)
    marker = Path(a.work) / 'TREE'; marker.mkdir(parents=True)
    coord = subprocess.Popen([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--tree-coordinator', str(marker)])
    obs = {'proof': 'PROCESS_TREE_CRASH_CONTAINMENT', 'coordinator_pid': coord.pid}
    handles = {}
    try:
        end = time.monotonic() + 120
        while time.monotonic() < end and not ((marker / 'CHILD.json').is_file() and (marker / 'COORDINATOR.json').is_file()):
            if coord.poll() is not None:
                raise RuntimeError('COORDINATOR_EXITED_EARLY:%s' % coord.returncode)
            time.sleep(0.1)
        pids = json.loads((marker / 'CHILD.json').read_text())
        pids.update(json.loads((marker / 'COORDINATOR.json').read_text()))
        obs['pids'] = pids
        alive, in_job = {}, {}
        for role in ('child_pid', 'grandchild_pid'):
            h = k.OpenProcess(access, False, pids[role])
            if not h:
                raise RuntimeError('OPEN_PROCESS:%s:%d' % (role, ctypes.get_last_error()))
            handles[role] = h
            alive[role] = k.WaitForSingleObject(h, 0) == 258
            flag = w.BOOL(0)
            in_job[role] = bool(k.IsProcessInJob(h, None, ctypes.byref(flag)) and flag.value)
        obs['alive_before'] = alive; obs['in_job_before'] = in_job
        t0 = time.monotonic()
        terminated = bool(k.TerminateProcess(w.HANDLE(int(coord._handle)), 99))
        coord.wait(60)
        obs['coordinator_terminate_call'] = terminated; obs['coordinator_exit'] = coord.returncode
        dead, codes = {}, {}
        for role, h in handles.items():
            dead[role] = k.WaitForSingleObject(h, 30000) == 0
            c = w.DWORD(0); k.GetExitCodeProcess(h, ctypes.byref(c)); codes[role] = c.value
        obs['dead_after'] = dead; obs['exit_codes_after'] = codes
        obs['seconds_to_contain'] = round(time.monotonic() - t0, 3)
        checks = {'job_child_alive_before_crash': all(alive.values()) and all(in_job.values()),
                  'coordinator_terminated_abruptly': terminated and coord.returncode == 99,
                  'job_child_dead_after_coordinator_crash': dead.get('child_pid') is True,
                  'no_job_descendant_survives': all(dead.values()),
                  'sandbox_only': within(marker, a.work)}
    finally:
        for role, h in handles.items():
            if k.WaitForSingleObject(h, 0) == 258:
                k.TerminateProcess(h, 98)
                obs.setdefault('cleanup_terminated', []).append(role)
            k.CloseHandle(h)
        if coord.poll() is None:
            coord.kill()
    dump(out / 'TREE_CRASH_OBSERVATION.json', obs)
    return checks, 'Job (KILL_ON_JOB_CLOSE) coordinator with child and grandchild; coordinator killed by TerminateProcess'


# ----------------------------------------------------------------------------- SAFE_STOP_RESUME_ROW_GROUP / POWERLOSS

def proof_safe_stop_resume(a, out):
    sys.path.insert(0, str(HERE))
    import G5_MULTIWORK_SCENARIOS as M
    return M.safe_stop_resume_row_group(CANDIDATE, Path(a.work), out, offline=a.offline)


def powerloss_emulated(a, out):
    sys.path.insert(0, str(HERE))
    import G5_MULTIWORK_SCENARIOS as M
    checks = M.powerloss_emulated(CANDIDATE, Path(a.work), out, offline=a.offline)
    return checks, 'POWERLOSS_EMULATED: seeded abrupt TerminateProcess of the coordinator tree during a synthetic ' \
                   'MULTIWORK run, fail-closed restart, sandbox lock reconciliation and product recovery; ' \
                   'NOT physical power loss'


# ----------------------------------------------------------------------------- PS51_INSTALL_MENU

def _sandbox_pair(d_parent, c_parent, tag):
    d = Path(d_parent) / (SANDBOX_PREFIX + 'D_' + tag)
    c = Path(c_parent) / (SANDBOX_PREFIX + 'C_' + tag)
    for root in (d, c):
        root.mkdir(parents=True)
        (root / 'SANDBOX_ONLY.txt').write_bytes(SENTINEL)
    m = d / 'Base CSV/Scripts/Biblioteca/MENU.py'; m.parent.mkdir(parents=True); m.write_bytes(FIXTURE_MENU)
    (d / 'Base CSV' / 'Manuten\u00e7\u00e3o Base de Dados.bat').write_bytes(FIXTURE_BAT)
    (c / 'TICKSTORE/Candidates').mkdir(parents=True)
    return d, c


def _ps(args, out, label):
    r = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'] + args,
                       capture_output=True, text=True, timeout=900)
    (out / ('PS51_' + label + '.txt')).write_text(r.stdout + '\n---STDERR---\n' + r.stderr, encoding='utf-8')
    return r


def _writer(installed, pkg, witness_sha, d, c, mode, *extra):
    args = [sys.executable, '-I', '-X', 'utf8', '-B', str(Path(installed) / WRITER_REL), '--mode', mode,
            '--d-root', str(d), '--c-root', str(c),
            '--menu-before-sha256', sha_bytes(FIXTURE_MENU), '--bat-sha256', sha_bytes(FIXTURE_BAT)]
    if mode == 'qualification-publish':
        args += ['--installed-root', str(installed), '--package-sha256', pkg, '--witness-sha256', witness_sha]
    return subprocess.run(args + list(extra), capture_output=True, text=True, timeout=300)


def _menu_consumer(installed):
    paths = types.ModuleType('paths')
    paths.PATHS = types.SimpleNamespace(BIBLIOTECA_ROOT=Path(installed), BASE_ROOT=Path(installed))
    orq = types.ModuleType('GERAR_BASE_COMPLETA'); orq.ETAPAS = []
    sys.modules['paths'] = paths; sys.modules['GERAR_BASE_COMPLETA'] = orq
    import importlib.util
    spec = importlib.util.spec_from_file_location('installed_menu_g5', Path(installed) / MENU_REL)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def proof_ps51_install_menu(a, out):
    final = Path(a.final_extract)
    witness = Path(a.witness)
    wsha = sha_file(witness)
    pkg = json.loads(witness.read_bytes())['package_sha256']
    installer = str(final / INSTALLER_REL)
    before = snapshot_real_targets(a.local_appdata)
    e = {}
    v = subprocess.run([PS, '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'],
                       capture_output=True, text=True, timeout=120)
    e['ps_version'] = v.stdout.strip()
    tag = uuid.uuid4().hex[:10].upper()
    d, c = _sandbox_pair(Path(a.d_parent) / 'PS51', Path(a.work) / 'C', tag)
    root = c / 'TICKSTORE/Candidates'; installed = root / pkg
    r = _ps([installer, '-WitnessPath', str(witness), '-InstallRoot', str(root), '-ActivateMenu'], out, 'E1_ACTIVATE_WITHOUT_CHAIN')
    e['E1'] = r.returncode == 2 and 'MENU_ACTIVATION_REQUIRES_RELEASE_CHAIN_THROUGH_B07' in r.stdout and not installed.exists()
    r = _ps([installer, '-WitnessPath', str(witness), '-InstallRoot', str(root), '-ChainFile', 'X', '-ChainSha256', 'A' * 64,
             '-B06Sha256', 'B' * 64], out, 'E2_CHAIN_WITHOUT_ACTIVATE')
    e['E2'] = r.returncode == 2 and 'CHAIN_ARGUMENTS_ONLY_WITH_ACTIVATE_MENU' in r.stdout and not installed.exists()
    r = _ps([installer, '-WitnessPath', str(witness), '-InstallRoot', str(root), '-ActivateMenu', '-ChainFile', 'X',
             '-ChainSha256', 'A' * 64, '-B06Sha256', 'B' * 64], out, 'E2B_ACTIVATE_SANDBOX_ROOT')
    e['E2B'] = r.returncode == 2 and 'MENU_ACTIVATION_REQUIRES_OFFICIAL_INSTALL_ROOT' in r.stdout and not installed.exists()
    r = _ps([installer, '-WitnessPath', str(witness), '-InstallRoot', str(root)], out, 'E3_INACTIVE_INSTALL')
    man = json.loads((final / 'PACKAGE_MANIFEST.json').read_bytes())
    readback = installed.is_dir() and all((installed / f['path']).is_file() and sha_file(installed / f['path']) == f['sha256']
                                          for f in man['files'])
    e['E3'] = (r.returncode == 0 and 'INSTALLATION=PASS_READBACK' in r.stdout
               and 'MENU_ACTIVATION=NOT_REQUESTED_INACTIVE_INSTALL_ONLY' in r.stdout and readback)
    snap = {p.relative_to(installed).as_posix(): sha_file(p) for p in installed.rglob('*') if p.is_file()} if installed.is_dir() else {}
    r = _ps([installer, '-WitnessPath', str(witness), '-InstallRoot', str(root)], out, 'E4_REINSTALL')
    snap2 = {p.relative_to(installed).as_posix(): sha_file(p) for p in installed.rglob('*') if p.is_file()} if installed.is_dir() else {}
    e['E4'] = r.returncode == 2 and 'INSTALLATION_ALREADY_EXISTS_VERIFY_EXISTING' in r.stdout and snap == snap2 and bool(snap)
    r = _writer(installed, pkg, wsha, d, c, 'qualification-publish')
    (out / 'WRITER_E5_PUBLISH.txt').write_text(r.stdout + r.stderr, encoding='utf-8')
    menu = d / 'Base CSV/Scripts/Biblioteca/MENU.py'; active = c / 'TICKSTORE/ACTIVE_DEPLOYMENT.json'
    consumer_ok = False
    if r.returncode == 0:
        try:
            dep = _menu_consumer(installed)._tickstore_committed_deployment(active, menu)
            consumer_ok = dep.get('package_sha256') == pkg and dep.get('installation_root') == str(installed)
        except Exception as exc:
            e['E5_consumer_error'] = repr(exc)
    e['E5'] = (r.returncode == 0 and 'MENU_WRITER_STATUS=COMMITTED' in r.stdout and consumer_ok
               and menu.read_bytes() == (installed / MENU_REL).read_bytes()
               and os.path.splitdrive(str(d))[0].upper() != os.path.splitdrive(str(c))[0].upper())
    tag2 = uuid.uuid4().hex[:10].upper()
    d2, c2 = _sandbox_pair(Path(a.d_parent) / 'PS51', Path(a.work) / 'C', tag2)
    root2 = c2 / 'TICKSTORE/Candidates'; installed2 = root2 / pkg
    steps = [_ps([installer, '-WitnessPath', str(witness), '-InstallRoot', str(root2)], out, 'E6_INSTALL').returncode == 0]
    steps.append(_writer(installed2, pkg, wsha, d2, c2, 'qualification-publish', '--inject',
                         'AFTER_ACTIVE_MOVE_BEFORE_JOURNAL').returncode == 77)
    r = _writer(installed2, pkg, wsha, d2, c2, 'qualification-recover')
    steps.append(r.returncode == 0 and 'MENU_WRITER_STATUS=ROLLED_BACK' in r.stdout)
    steps.append((d2 / 'Base CSV/Scripts/Biblioteca/MENU.py').read_bytes() == FIXTURE_MENU
                 and not (c2 / 'TICKSTORE/ACTIVE_DEPLOYMENT.json').exists())
    steps.append(_writer(installed2, pkg, wsha, d2, c2, 'qualification-archive').returncode == 0)
    r = _writer(installed2, pkg, wsha, d2, c2, 'qualification-publish')
    steps.append(r.returncode == 0 and 'MENU_WRITER_STATUS=COMMITTED' in r.stdout)
    e['E6_steps'] = steps
    after = snapshot_real_targets(a.local_appdata)
    e['real_targets_before'] = before; e['real_targets_after'] = after
    e['sandboxes'] = [str(d), str(c), str(d2), str(c2)]
    dump(out / 'PS51_INSTALL_OBSERVATION.json', e)
    checks = {'ps51_host_version': e['ps_version'].startswith('5.1.'),
              'inactive_install_readback': e['E3'] and e['E4'],
              'menu_not_activated_without_chain': e['E1'] and e['E2'] and e['E2B'],
              'official_menu_untouched': before == after,
              'qualification_layout_writer_committed': e['E5'] and all(steps) and len(steps) == 6,
              'sandbox_only': all(SANDBOX_PREFIX in Path(p).name for p in e['sandboxes'])
              and all(within(p, a.d_parent) or within(p, a.work) for p in e['sandboxes'])}
    return checks, 'Windows PowerShell 5.1 inactive install of the FINAL package into sandbox Candidates roots; ' \
                   'installed writer in QUALIFICATION layout (cross-volume), crash + new-process recovery; ' \
                   'official MENU never activated'


# ----------------------------------------------------------------------------- D4_REAL_ISOLATED_PATH_NATIVE

def _native_real_source_suite(a, out, proof, suites, expected):
    """Execute ORIGINAL effectful test entrypoints over isolated run-owned NTFS paths.

    No fake 1399-day closure or simulated production gate.  The genuine packaged
    module functions are exercised by existing tests, while this receipt is
    explicitly limited to a PRE-B06 isolated code-path qualification.
    """
    root = CANDIDATE.parent
    tests = root / 'tests'
    before = snapshot_real_targets(a.local_appdata)
    # CDT18: WORK/<proof> and EVIDENCE/PROOFS/<proof> are siblings under one run root.
    run_root = Path(os.path.abspath(a.evidence)).parent
    if Path(os.path.commonpath([os.path.abspath(a.work), os.path.abspath(a.evidence)])) != run_root:
        raise RuntimeError('PROOF_RUN_ROOT_TOPOLOGY')
    argv = [sys.executable, '-I', '-X', 'utf8', '-B', str(HERE/'PRE_G06_BOUNDARY_SUITES.py'),
            '--tests', str(tests), '--run-owned', str(a.work), '--output', str(out/'NATIVE_SUITE_RESULT.json'),
            '--suites', json.dumps(suites, sort_keys=True), '--run-root', str(run_root)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', TMP=str(a.work), TEMP=str(a.work))
    r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=900, env=env)
    (out/'NATIVE_SUITE_STDOUT.log').write_text(r.stdout or 'NO_STDOUT\n',encoding='utf-8')
    (out/'NATIVE_SUITE_STDERR.log').write_text(r.stderr or 'NO_STDERR\n',encoding='utf-8')
    receipt = json.loads((out/'NATIVE_SUITE_RESULT.json').read_bytes()) if (out/'NATIVE_SUITE_RESULT.json').exists() else {}
    actual = receipt.get('suites', {})
    # Proof evidence must travel inside the sealed RETURN ZIP, not point only
    # to ephemeral Windows TEMP paths. Copy readback-verified actual test logs
    # into the proof's own artifact namespace without overwriting.
    sealed_logs = []
    (out / 'SEALED_NATIVE_LOGS').mkdir(exist_ok=False)
    for item in receipt.get('physical_artifacts', []):
        original = Path(item['path'])
        if not original.is_file() or not within(original, a.work) or sha_file(original) != item['sha256']:
            raise RuntimeError('RUN_OWNED_LOG_READBACK:' + str(original))
        target = out / 'SEALED_NATIVE_LOGS' / original.name
        with target.open('xb') as f:
            b = original.read_bytes(); f.write(b); f.flush(); os.fsync(f.fileno())
        if sha_file(target) != item['sha256']:
            raise RuntimeError('SEALED_NATIVE_LOG_COPY_READBACK:' + str(target))
        sealed_logs.append({'path': str(target), 'sha256': sha_file(target), 'bytes': target.stat().st_size})
    actual = receipt.get('suites', {})
    checks = {
      'native_original_code_executed': os.name=='nt' and r.returncode==0 and bool(actual)
                                     and all((actual.get(k,{}).get('run')==v if v is not None else actual.get(k,{}).get('run',0)>0) and actual[k].get('failures')==0
                                             and actual[k].get('errors')==0 and actual[k].get('skips')==0
                                             for k,v in expected.items()),
      'physical_run_owned_artifacts': bool(receipt.get('physical_artifacts')) and
             len(sealed_logs)==len(receipt.get('physical_artifacts',[])) and
             all(Path(row['path']).is_file() and sha_file(row['path'])==row['sha256']
                 for row in sealed_logs),
      'production_targets_unchanged': before==snapshot_real_targets(a.local_appdata),
      'run_owned_only': within(a.work,a.work) and not within(a.work,r'D:\Base CSV')
    }
    dump(out/'REAL_BOUNDED_OBSERVATION.json', {'proof':proof, 'native_exit':r.returncode,
         'suites': actual, 'physical_artifacts':sealed_logs,
         'source_only':False, 'production_execution':False,
         'bridge_sha256':sha_file(HERE/'PRE_G06_BOUNDARY_SUITES.py'),
         'not_full_operational_d4_or_stage_b':True})
    return checks, ('Real packaged code-path exercises on run-owned NTFS only; bounded PRE-B06 contract. ' +
                    'Not operational D4, Stage B, CANARY, FULL or physical power loss.')


def proof_d4_isolated_real_code(a, out):
    return _native_real_source_suite(a,out,'D4_ISOLATED_REAL_CODE',
        {'test_pre_g06_d4_real_runtime_isolated.py':4},
        {'test_pre_g06_d4_real_runtime_isolated.py':4})


def proof_stage_b_isolated_real_code(a, out):
    return _native_real_source_suite(a,out,'STAGE_B_ISOLATED_REAL_CODE',
        {'test_stageb_full_physical_closure.py':12,'test_stage_canary_physical_publication.py':7,
         'test_full_postverify_readback.py':17,'test_canary_receipt_readback.py':13},
        {'test_stageb_full_physical_closure.py':12,'test_stage_canary_physical_publication.py':7,
         'test_full_postverify_readback.py':17,'test_canary_receipt_readback.py':13})


# ----------------------------------------------------------------------------- driver

RUNNERS = {'PROCESS_TREE_CRASH_CONTAINMENT': proof_process_tree_crash, 'SAFE_STOP_RESUME_ROW_GROUP': proof_safe_stop_resume,
           'PS51_INSTALL_MENU': proof_ps51_install_menu, 'D4_REAL_ISOLATED_PATH_NATIVE': proof_d4_isolated_real_code,
           'STAGE_B_REAL_ISOLATED_PATH_NATIVE': proof_stage_b_isolated_real_code, 'POWERLOSS_EMULATED': powerloss_emulated}


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--proof', required=True, choices=sorted(RUNNERS))
    for k in ('work', 'evidence', 'run-id', 'final-zip-sha256', 'code-manifest-sha256'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--final-extract', default=''); ap.add_argument('--witness', default='')
    ap.add_argument('--d-parent', default=''); ap.add_argument('--local-appdata', default='')
    ap.add_argument('--offline', action='store_true')
    a = ap.parse_args(argv)
    kind, function = KINDS[a.proof]
    out = Path(a.evidence) / 'PROOFS' / a.proof
    out.mkdir(parents=True, exist_ok=False)
    Path(a.work).mkdir(parents=True, exist_ok=False)
    if a.offline:
        # POSIX dry-run seam only (named-event emulation); a native run never sets it.
        os.environ['G5_OFFLINE_STOP_DIR'] = str(Path(a.work) / 'OFFLINE_STOP')
        Path(os.environ['G5_OFFLINE_STOP_DIR']).mkdir()
    t0 = time.monotonic()
    error = None
    try:
        result = RUNNERS[a.proof](a, out)
        checks, scenario = result if isinstance(result, tuple) else (result, '')
        checks = {k: 'PASS' if v is True else 'FAIL' for k, v in checks.items()}
    except BaseException as exc:
        checks, scenario = {}, ''
        error = type(exc).__name__ + ':' + str(exc)[:2000]
        (out / 'RUNNER_TRACEBACK.txt').write_text(traceback.format_exc(), encoding='utf-8')
    ok = bool(checks) and all(v == 'PASS' for v in checks.values()) and error is None
    native = os.name == 'nt' and not a.offline
    if a.proof == 'POWERLOSS_EMULATED':
        status = ('EMULATED_PASS' if ok else 'EMULATED_FAIL') if native else 'OFFLINE_HARNESS_ONLY'
    else:
        status = ('PASS' if ok else ('ERROR' if error else 'FAIL')) if native else 'OFFLINE_HARNESS_ONLY'
    arts = []
    for p in sorted(out.rglob('*')):
        if p.is_file():
            raw = p.read_bytes()
            arts.append({'member': 'EVIDENCE/PROOFS/%s/%s' % (a.proof, p.relative_to(out).as_posix()),
                         'sha256': sha_bytes(raw), 'bytes': len(raw)})
    me = Path(__file__).resolve()
    receipt = {'schema': RECEIPT_SCHEMA, 'kind': kind, 'proof': a.proof, 'status': status,
               'native_windows': native, 'platform': platform.platform(), 'python': sys.version,
               'production_execution': False, 'boundary_scope':
               ('PRE_B06_ISOLATED_REAL_CODE' if a.proof in ('D4_REAL_ISOLATED_PATH_NATIVE',
                  'STAGE_B_REAL_ISOLATED_PATH_NATIVE') else 'OTHER_SCOPED_PROOF'),
               'code_manifest_sha256': a.code_manifest_sha256,
               'final_zip_sha256': a.final_zip_sha256, 'run_id': a.run_id,
               'runner': {'path': 'g5proof/G5_PROOF_RUNNERS.py', 'function': function, 'sha256': sha_file(me)},
               'scenario': scenario, 'checks': checks, 'artifacts': arts, 'error': error,
               'seconds': round(time.monotonic() - t0, 3), 'gate_verdict_issued': False}
    if a.proof == 'POWERLOSS_EMULATED':
        receipt.update(counts_as='NOT_CHECKPOINT_POWERLOSS_RECOVERY',
                       limitation='Process death with fsync-ed state only; volatile caches and torn sectors of a '
                                  'physical power cut are not exercised.')
    dump(out / 'PROOF_RECEIPT.json', receipt)
    print('G5_PROOF %s=%s %s' % (a.proof, status, ' '.join('%s=%s' % kv for kv in checks.items())), flush=True)
    if error:
        print('G5_PROOF_ERROR %s %s' % (a.proof, error), flush=True)
    return 0 if status in ('PASS', 'EMULATED_PASS') else 2


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--tree-coordinator':
        raise SystemExit(tree_coordinator(sys.argv[2]))
    raise SystemExit(main())
