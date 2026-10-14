"""TICKSTORE CDT15 R41 Windows qualification driver (sandbox only; no production effect).

Launched by RUN_TICKSTORE_CDT15_R41_QUAL.ps1 after the outer ZIP was located,
privately copied, hash-verified and extracted.  This driver:

1. pins identity (Python, OS, volumes, resources) and snapshots the REAL targets
   read-only (MENU, BAT, ACTIVE, MENU_TRANSACTION, writer lock);
2. verifies the inner FINAL package (witness, ZIP SHA, CRC, manifest, closed set)
   and extracts it; every test runs from those exact packaged bytes;
3. runs the affected/new suites in isolated child interpreters with exact
   cardinality and zero failure/error/skip;
4. runs the native PS 5.1 installer -> installed writer E2E in disposable D:/C:
   sandboxes, including abrupt crash and recovery by a new process;
5. re-snapshots the real targets (PRODUCTION_MODIFIED must be False), writes an
   immutable receipt and a small RETURN ZIP.  It never launches a successor.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import types
import unittest
import uuid
import zipfile
from pathlib import Path

DRIVER_SCHEMA = 'TICKSTORE_CDT15_WINDOWS_QUALIFICATION_RECEIPT_V002'
RESULT_CONTEXT = 'ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compress\u00e3o De Ticks 15'
REAL_MENU = r'D:\Base CSV\Scripts\Biblioteca\MENU.py'
REAL_BAT = 'D:\\Base CSV\\Manuten\u00e7\u00e3o Base de Dados.bat'
SANDBOX_PREFIX = 'CDT15_R41_WRITER_QUAL_'
SENTINEL = b'CDT15_R41_OFFICIAL_WRITER_QUALIFICATION_SANDBOX_ONLY_V001\n'
FIXTURE_MENU = b'# R41 sandbox fixture: historical MENU stand-in\nprint("old menu")\n'
FIXTURE_BAT = b'@echo off\r\nrem R41 sandbox fixture\r\n'
PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
WRITER_REL = 'implementation_v001/candidate/control/MENU_OFFICIAL_WRITER.py'
INSTALLER_REL = 'implementation_v001/candidate/control/INSTALL_TICKSTORE_FULL.ps1'
MENU_REL = 'implementation_v001/candidate/menu/MENU.py'


class Blocked(RuntimeError):
    pass


def require(cond, why):
    if not cond:
        raise Blocked(why)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest().upper()


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def dhms(seconds):
    t = max(0, int(-(-float(seconds) // 1)))
    d, r = divmod(t, 86400); h, r = divmod(r, 3600); m, s = divmod(r, 60)
    return '%d.%02d.%02d.%02d' % (d, h, m, s)


class Tee:
    def __init__(self, stream, path):
        self.stream = stream
        self.log = open(path, 'a', encoding='utf-8', newline='')

    def write(self, text):
        self.stream.write(text); self.log.write(text); self.log.flush()
        return len(text)

    def flush(self):
        self.stream.flush(); self.log.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


class Progress:
    """Weighted step progress with transparent elapsed/ETA in d.hh.mm.ss."""
    def __init__(self, steps):
        self.steps = steps; self.total = sum(w for _, w in steps); self.done = 0
        self.started = time.monotonic(); self.index = 0

    def begin(self, name):
        self.index += 1
        elapsed = time.monotonic() - self.started
        pct = 100.0 * self.done / self.total
        eta = 'UNKNOWN' if self.done == 0 else dhms(elapsed * (self.total - self.done) / self.done)
        filled = min(29, int(30 * pct / 100))
        print('QUAL_PROGRESS [%s%s] %6.2f%% STEP=%d/%d %s ELAPSED=%s ETA=%s' % (
            '#' * filled, '-' * (30 - filled), pct, self.index, len(self.steps), name, dhms(elapsed), eta), flush=True)

    def end(self, name):
        self.done += dict(self.steps)[name]


# ----------------------------------------------------------------------------- identity

def volume_info(root):
    if os.name != 'nt':
        return {'root': root, 'filesystem': 'POSIX_OFFLINE'}
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    name = ctypes.create_unicode_buffer(261); fs = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_uint32(); maxlen = ctypes.c_uint32(); flags = ctypes.c_uint32()
    ok = k.GetVolumeInformationW(ctypes.c_wchar_p(root), name, 261, ctypes.byref(serial), ctypes.byref(maxlen),
                                 ctypes.byref(flags), fs, 261)
    require(ok, 'VOLUME_INFORMATION:' + root + ':' + str(ctypes.get_last_error()))
    usage = shutil.disk_usage(root)
    return {'root': root, 'filesystem': fs.value, 'serial': '%08X' % serial.value,
            'free_bytes': usage.free, 'total_bytes': usage.total}


def snapshot_real_targets(local_appdata):
    """Read-only observation of the real targets; opens nothing for write."""
    out = {}
    tick = os.path.join(local_appdata, 'TICKSTORE') if local_appdata else None
    items = {'menu': REAL_MENU, 'bat': REAL_BAT}
    if tick:
        items.update(active=os.path.join(tick, 'ACTIVE_DEPLOYMENT.json'),
                     transaction=os.path.join(tick, 'MENU_TRANSACTION'),
                     writer_lock=os.path.join(tick, 'MENU_WRITER.lock'),
                     candidates=os.path.join(tick, 'Candidates'))
    for key, path in items.items():
        if os.path.isfile(path):
            out[key] = {'path': path, 'status': 'PRESENT', 'sha256': sha_file(path)}
        elif os.path.isdir(path):
            names = sorted(os.listdir(path))
            out[key] = {'path': path, 'status': 'PRESENT_DIR', 'entries': names}
        else:
            out[key] = {'path': path, 'status': 'ABSENT'}
    return out


# ----------------------------------------------------------------------------- package

def verify_closed_manifest(root, manifest_name, schema):
    root = Path(root)
    raw = (root / manifest_name).read_bytes()
    man = json.loads(raw)
    require(man.get('schema') == schema, 'MANIFEST_SCHEMA:' + manifest_name)
    listed = {}
    for f in man['files']:
        require(set(f) == {'path', 'bytes', 'sha256'} and f['path'] not in listed, 'MANIFEST_RECORD')
        listed[f['path']] = f
        p = root / f['path']
        require(p.is_file() and p.stat().st_size == f['bytes'] and sha_file(p) == f['sha256'],
                'MANIFEST_MEMBER:' + f['path'])
    physical = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} - {manifest_name}
    require(physical == set(listed), 'MANIFEST_CLOSED_SET:' + manifest_name)
    return man, sha_bytes(raw)


def verify_and_extract_final(bundle, work):
    plan = json.loads((Path(bundle) / 'qual/QUAL_PLAN.json').read_bytes())
    wpath = Path(bundle) / 'FINAL' / plan['final_witness_name']
    witness_raw = wpath.read_bytes(); w = json.loads(witness_raw)
    require(w.get('schema') == 'TICKSTORE_FINAL_PACKAGE_WITNESS_V001', 'FINAL_WITNESS_SCHEMA')
    zpath = Path(bundle) / 'FINAL' / w['package_name']
    require(sha_file(zpath) == w['package_sha256'] == plan['final_package_sha256'], 'FINAL_PACKAGE_SHA256')
    with zipfile.ZipFile(zpath) as z:
        require(z.testzip() is None, 'FINAL_PACKAGE_CRC')
        names = z.namelist()
        require(len(names) == len(set(n.casefold() for n in names)), 'FINAL_PACKAGE_DUPLICATE')
        for n in names:
            require(not n.startswith('/') and '\\' not in n and ':' not in n and '..' not in n.split('/'),
                    'FINAL_PACKAGE_MEMBER_PATH')
        mraw = z.read('PACKAGE_MANIFEST.json')
        require(sha_bytes(mraw) == w['manifest_sha256'], 'FINAL_PACKAGE_MANIFEST_SHA256')
        dest = Path(work) / 'FINAL_EXTRACT'
        require(not dest.exists(), 'FINAL_EXTRACT_EXISTS')
        z.extractall(dest)
    man, msha = verify_closed_manifest(dest, 'PACKAGE_MANIFEST.json', 'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001')
    require(len(man['files']) == len(names) - 1, 'FINAL_PACKAGE_CARDINALITY')
    return dict(plan=plan, witness=w, witness_path=str(wpath), witness_sha256=sha_bytes(witness_raw),
                package_path=str(zpath), extract=str(dest), manifest_sha256=msha, members=len(man['files']))


# ----------------------------------------------------------------------------- suites

class Recorder(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.records = []

    def addSuccess(self, test):
        super().addSuccess(test); self.records.append({'id': test.id(), 'status': 'PASS'})

    def addFailure(self, test, err):
        super().addFailure(test, err); self.records.append({'id': test.id(), 'status': 'FAIL'})

    def addError(self, test, err):
        super().addError(test, err); self.records.append({'id': test.id(), 'status': 'ERROR'})

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self.records.append({'id': test.id(), 'status': 'SKIP', 'reason': reason})

    def addSubTest(self, test, subtest, outcome):
        super().addSubTest(test, subtest, outcome)
        if outcome is not None:
            self.records.append({'id': subtest.id(), 'status': 'FAIL_SUBTEST'})


def run_suite_child(impl, spec_json, out):
    """Executed in an isolated child interpreter: load by file, record per test."""
    spec = json.loads(spec_json)
    impl = Path(impl)
    for extra in spec.get('sys_path', []):
        sys.path.insert(0, str(impl / extra))
    loader = unittest.TestLoader(); suite = unittest.TestSuite()
    for i, item in enumerate(spec['files']):
        path = impl / item['file']
        mod_name = 'r41q_%d_%s' % (i, path.stem)
        mspec = importlib.util.spec_from_file_location(mod_name, path)
        mod = importlib.util.module_from_spec(mspec); sys.modules[mod_name] = mod
        mspec.loader.exec_module(mod)
        loaded = loader.loadTestsFromModule(mod)
        if item.get('only'):
            wanted = set(item['only'])
            flat = []
            def walk(s):
                for t in s:
                    walk(t) if isinstance(t, unittest.TestSuite) else flat.append(t)
            walk(loaded)
            loaded = unittest.TestSuite([t for t in flat if t.id().split('.')[-2:] and
                                         '.'.join(t.id().split('.')[-2:]) in wanted])
        suite.addTests(loaded)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Recorder).run(suite)
    Path(out).write_bytes(canonical({'run': result.testsRun, 'failures': len(result.failures),
                                     'errors': len(result.errors), 'skips': len(result.skipped),
                                     'records': result.records, 'log': stream.getvalue()}))
    return 0


def run_suite(name, spec, impl, env, evidence, python):
    out = Path(evidence) / ('SUITE_' + name + '.json')
    t0 = time.monotonic()
    r = subprocess.run([python, '-I', '-X', 'utf8', '-B', str(Path(__file__).resolve()), '--run-suite-child',
                        '--impl', str(impl), '--spec', json.dumps(spec), '--out', str(out)],
                       env=env, capture_output=True, text=True, timeout=spec.get('timeout', 3600))
    (Path(evidence) / ('SUITE_' + name + '_STDIO.txt')).write_text(r.stdout + '\n---STDERR---\n' + r.stderr,
                                                                 encoding='utf-8')
    require(out.is_file(), 'SUITE_NO_RESULT:' + name + ':exit=' + str(r.returncode))
    res = json.loads(out.read_bytes())
    ok = (r.returncode == 0 and res['run'] == spec['expected'] and res['failures'] == 0 and res['errors'] == 0
          and res['skips'] == 0 and not any(x['status'] != 'PASS' for x in res['records']))
    summary = {'suite': name, 'status': 'PASS' if ok else 'FAIL', 'expected': spec['expected'], 'run': res['run'],
               'failures': res['failures'], 'errors': res['errors'], 'skips': res['skips'],
               'seconds': round(time.monotonic() - t0, 3), 'result_sha256': sha_file(out),
               'non_pass': [x for x in res['records'] if x['status'] != 'PASS']}
    print('QUAL_SUITE %s=%s RUN=%d/%d FAIL=%d ERROR=%d SKIP=%d' % (
        name, summary['status'], res['run'], spec['expected'], res['failures'], res['errors'], res['skips']), flush=True)
    if not ok:
        print(res['log'][-6000:], flush=True)
    return summary


def run_script(name, script, impl, env, evidence, python, expect_token, isolated=True, timeout=600):
    # Historical smokes import their sibling modules: they need the script directory on
    # sys.path, so they run with -E -s (no env/user site) instead of -I (which implies -P).
    flags = ['-I'] if isolated else ['-E', '-s']
    r = subprocess.run([python] + flags + ['-X', 'utf8', '-B', str(Path(impl) / script)], env=env,
                       capture_output=True, text=True, timeout=timeout)
    (Path(evidence) / ('SCRIPT_' + name + '.txt')).write_text(r.stdout + '\n---STDERR---\n' + r.stderr, encoding='utf-8')
    tokens = expect_token if isinstance(expect_token, list) else [expect_token]
    ok = r.returncode == 0 and all(t in r.stdout for t in tokens)
    print('QUAL_SCRIPT %s=%s EXIT=%d' % (name, 'PASS' if ok else 'FAIL', r.returncode), flush=True)
    return {'suite': name, 'status': 'PASS' if ok else 'FAIL', 'exit': r.returncode}


def run_scenario(name, spec, bundle, impl, work, env, evidence, python, native):
    out = Path(evidence) / ('SCENARIO_' + name + '.json')
    wdir = Path(work) / ('SCN_' + name)
    args = [python, '-I', '-X', 'utf8', '-B', str(bundle / spec['runner']), '--impl', str(impl),
            '--work', str(wdir), '--scenario', spec['scenario'], '--out', str(out)]
    if not native:
        args.append('--offline')
    t0 = time.monotonic()
    r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=spec.get('timeout', 1800))
    (Path(evidence) / ('SCENARIO_' + name + '_STDIO.txt')).write_text(
        r.stdout[-200000:] + '\n---STDERR---\n' + r.stderr[-50000:], encoding='utf-8')
    res = json.loads(out.read_bytes()) if out.is_file() else {'status': 'NO_RESULT'}
    ok = r.returncode == 0 and res.get('status') == 'PASS'
    status = 'PASS' if ok else 'FAIL'
    if ok and not native:
        status = 'OFFLINE_HARNESS_PASS'
    line = next((l for l in r.stdout.splitlines() if l.startswith('R42_SCENARIO ')), 'R42_SCENARIO ' + name + '=NO_LINE')
    print(line, flush=True)
    return {'suite': name, 'status': status, 'seconds': round(time.monotonic() - t0, 3),
            'checks': res.get('checks', {}), 'error': res.get('error')}


def run_b1(bundle, impl, work, env, evidence, python, native):
    args = [python, '-I', '-X', 'utf8', '-B', str(bundle / 'qual/R43_B1_RUNNER.py'), '--bundle', str(bundle),
            '--impl', str(impl), '--work', str(work), '--evidence', str(evidence),
            '--plan', str(bundle / 'qual/QUAL_PLAN.json')]
    if not native:
        args.append('--offline')
    t0 = time.monotonic()
    r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10800)
    (Path(evidence) / 'B1_RUNNER_STDIO.txt').write_text(r.stdout[-100000:] + '\n---STDERR---\n' + r.stderr[-50000:],
                                                       encoding='utf-8')
    res_path = Path(evidence) / 'B1_RESULT.json'
    res = json.loads(res_path.read_bytes()) if res_path.is_file() else {'status': 'NO_RESULT'}
    line = next((l for l in r.stdout.splitlines() if l.startswith('R43_B1 ')), 'R43_B1 status=NO_LINE')
    print(line, flush=True)
    return {'suite': 'B1_126_CONTRACT_IDS', 'status': res.get('status', 'NO_RESULT'),
            'counts': res.get('counts'), 'microprobes': res.get('microprobes'),
            'non_pass': res.get('non_pass'), 'error': res.get('error'),
            'seconds': round(time.monotonic() - t0, 3)}


# ----------------------------------------------------------------------------- E2E

def make_sandbox_pair(d_parent, c_parent, tag):
    d = Path(d_parent) / (SANDBOX_PREFIX + 'D_' + tag)
    c = Path(c_parent) / (SANDBOX_PREFIX + 'C_' + tag)
    for root in (d, c):
        root.mkdir(parents=True)
        (root / 'SANDBOX_ONLY.txt').write_bytes(SENTINEL)
    m = d / 'Base CSV/Scripts/Biblioteca/MENU.py'; m.parent.mkdir(parents=True); m.write_bytes(FIXTURE_MENU)
    (d / 'Base CSV' / 'Manuten\u00e7\u00e3o Base de Dados.bat').write_bytes(FIXTURE_BAT)
    (c / 'TICKSTORE/Candidates').mkdir(parents=True)
    return d, c


def powershell(args, evidence, label, env):
    r = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'] + args,
                       capture_output=True, text=True, timeout=900, env=env)
    (Path(evidence) / ('E2E_' + label + '.txt')).write_text(r.stdout + '\n---STDERR---\n' + r.stderr, encoding='utf-8')
    return r


def writer(python, installed, final, d, c, mode, env, *extra):
    args = [python, '-I', '-X', 'utf8', '-B', str(Path(installed) / WRITER_REL), '--mode', mode,
            '--d-root', str(d), '--c-root', str(c),
            '--menu-before-sha256', sha_bytes(FIXTURE_MENU), '--bat-sha256', sha_bytes(FIXTURE_BAT)]
    if mode == 'qualification-publish':
        args += ['--installed-root', str(installed), '--package-sha256', final['witness']['package_sha256'],
                 '--witness-sha256', final['witness_sha256']]
    return subprocess.run(args + list(extra), capture_output=True, text=True, timeout=300, env=env)


def menu_consumer(installed):
    paths = types.ModuleType('paths')
    paths.PATHS = types.SimpleNamespace(BIBLIOTECA_ROOT=Path(installed), BASE_ROOT=Path(installed))
    orq = types.ModuleType('GERAR_BASE_COMPLETA'); orq.ETAPAS = []
    sys.modules['paths'] = paths; sys.modules['GERAR_BASE_COMPLETA'] = orq
    spec = importlib.util.spec_from_file_location('installed_menu_r41', Path(installed) / MENU_REL)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def e2e(final, python, work, d_parent, evidence, env, native):
    checks = {}
    installer = str(Path(final['extract']) / INSTALLER_REL)
    tag = uuid.uuid4().hex[:10].upper()
    d, c = make_sandbox_pair(Path(d_parent) / 'E2E', Path(work) / 'E2E_C', tag)
    root = c / 'TICKSTORE/Candidates'
    pkg = final['witness']['package_sha256']
    installed = root / pkg
    if not native:
        return {'status': 'NOT_NATIVE_SKIPPED_OFFLINE', 'checks': {}}
    # E1/E2: argument gates fail before any witness read or write.
    r = powershell([installer, '-WitnessPath', final['witness_path'], '-InstallRoot', str(root), '-ActivateMenu'],
                   evidence, 'E1_ACTIVATE_WITHOUT_CHAIN', env)
    checks['E1_ACTIVATE_WITHOUT_CHAIN_BLOCKS'] = (r.returncode == 2 and
        'MENU_ACTIVATION_REQUIRES_RELEASE_CHAIN_THROUGH_B07' in r.stdout and not installed.exists())
    r = powershell([installer, '-WitnessPath', final['witness_path'], '-InstallRoot', str(root),
                    '-ChainFile', 'X', '-ChainSha256', 'A' * 64, '-B06Sha256', 'B' * 64],
                   evidence, 'E2_CHAIN_WITHOUT_ACTIVATE', env)
    checks['E2_CHAIN_WITHOUT_ACTIVATE_BLOCKS'] = (r.returncode == 2 and
        'CHAIN_ARGUMENTS_ONLY_WITH_ACTIVATE_MENU' in r.stdout and not installed.exists())
    r = powershell([installer, '-WitnessPath', final['witness_path'], '-InstallRoot', str(root), '-ActivateMenu',
                    '-ChainFile', 'X', '-ChainSha256', 'A' * 64, '-B06Sha256', 'B' * 64],
                   evidence, 'E2B_ACTIVATE_SANDBOX_ROOT', env)
    checks['E2B_ACTIVATE_REQUIRES_OFFICIAL_ROOT'] = (r.returncode == 2 and
        'MENU_ACTIVATION_REQUIRES_OFFICIAL_INSTALL_ROOT' in r.stdout and not installed.exists())
    # E3: native PS 5.1 inactive install into the sandbox Candidates root.
    r = powershell([installer, '-WitnessPath', final['witness_path'], '-InstallRoot', str(root)],
                   evidence, 'E3_INACTIVE_INSTALL', env)
    man = json.loads((Path(final['extract']) / 'PACKAGE_MANIFEST.json').read_bytes())
    readback = installed.is_dir() and all(
        (installed / f['path']).is_file() and sha_file(installed / f['path']) == f['sha256'] for f in man['files'])
    checks['E3_PS51_INACTIVE_INSTALL_READBACK'] = (r.returncode == 0 and 'INSTALLATION=PASS_READBACK' in r.stdout
        and 'MENU_ACTIVATION=NOT_REQUESTED_INACTIVE_INSTALL_ONLY' in r.stdout and readback)
    before = {p.relative_to(installed).as_posix(): sha_file(p) for p in installed.rglob('*') if p.is_file()}
    r = powershell([installer, '-WitnessPath', final['witness_path'], '-InstallRoot', str(root)],
                   evidence, 'E4_REINSTALL', env)
    after = {p.relative_to(installed).as_posix(): sha_file(p) for p in installed.rglob('*') if p.is_file()}
    checks['E4_REINSTALL_REFUSED_UNCHANGED'] = (r.returncode == 2 and
        'INSTALLATION_ALREADY_EXISTS_VERIFY_EXISTING' in r.stdout and before == after)
    # E5: installed writer bytes publish in the cross-volume sandbox; installed MENU consumes.
    r = writer(python, installed, final, d, c, 'qualification-publish', env)
    (Path(evidence) / 'E2E_E5_WRITER_PUBLISH.txt').write_text(r.stdout + r.stderr, encoding='utf-8')
    menu = d / 'Base CSV/Scripts/Biblioteca/MENU.py'; active = c / 'TICKSTORE/ACTIVE_DEPLOYMENT.json'
    consumer_ok = False
    if r.returncode == 0:
        try:
            dep = menu_consumer(installed)._tickstore_committed_deployment(active, menu)
            consumer_ok = dep.get('package_sha256') == pkg and dep.get('installation_root') == str(installed)
        except Exception as exc:  # recorded, not hidden
            (Path(evidence) / 'E2E_E5_CONSUMER_ERROR.txt').write_text(repr(exc), encoding='utf-8')
    checks['E5_INSTALLED_WRITER_COMMITS_CROSS_VOLUME'] = (r.returncode == 0 and
        'MENU_WRITER_STATUS=COMMITTED' in r.stdout and menu.read_bytes() == (installed / MENU_REL).read_bytes())
    checks['E5_INSTALLED_MENU_CONSUMER_ACCEPTS_COMMITTED'] = consumer_ok
    checks['E5_CROSS_VOLUME'] = (os.path.splitdrive(str(d))[0].upper() != os.path.splitdrive(str(c))[0].upper())
    # E6: abrupt death of the installed writer, recovery by a new process, archive, retry.
    tag2 = uuid.uuid4().hex[:10].upper()
    d2, c2 = make_sandbox_pair(Path(d_parent) / 'E2E', Path(work) / 'E2E_C', tag2)
    root2 = c2 / 'TICKSTORE/Candidates'; installed2 = root2 / pkg
    r = powershell([installer, '-WitnessPath', final['witness_path'], '-InstallRoot', str(root2)],
                   evidence, 'E6_INSTALL', env)
    steps = [r.returncode == 0]
    r = writer(python, installed2, final, d2, c2, 'qualification-publish', env, '--inject', 'AFTER_ACTIVE_MOVE_BEFORE_JOURNAL')
    steps.append(r.returncode == 77)
    r = writer(python, installed2, final, d2, c2, 'qualification-recover', env)
    steps.append(r.returncode == 0 and 'MENU_WRITER_STATUS=ROLLED_BACK' in r.stdout)
    menu2 = d2 / 'Base CSV/Scripts/Biblioteca/MENU.py'
    steps.append(menu2.read_bytes() == FIXTURE_MENU and not (c2 / 'TICKSTORE/ACTIVE_DEPLOYMENT.json').exists())
    r = writer(python, installed2, final, d2, c2, 'qualification-archive', env)
    steps.append(r.returncode == 0)
    r = writer(python, installed2, final, d2, c2, 'qualification-publish', env)
    steps.append(r.returncode == 0 and 'MENU_WRITER_STATUS=COMMITTED' in r.stdout)
    (Path(evidence) / 'E2E_E6_STEPS.json').write_text(json.dumps(steps), encoding='utf-8')
    checks['E6_CRASH_NEW_PROCESS_RECOVERY_ARCHIVE_RETRY'] = all(steps) and len(steps) == 6
    status = 'PASS' if all(checks.values()) else 'FAIL'
    print('QUAL_E2E=%s %s' % (status, ' '.join('%s=%s' % (k, 'PASS' if v else 'FAIL') for k, v in checks.items())),
          flush=True)
    return {'status': status, 'checks': {k: bool(v) for k, v in checks.items()},
            'sandboxes': [str(d), str(c), str(d2), str(c2)]}


# ----------------------------------------------------------------------------- main

def main(a):
    run_dir = Path(a.run_dir); work = Path(a.work_root); bundle = Path(a.bundle_dir)
    evidence = run_dir / 'EVIDENCE'; evidence.mkdir(parents=False, exist_ok=False)
    sys.stdout = Tee(sys.stdout, run_dir / 'RUN_LOG.txt'); sys.stderr = Tee(sys.stderr, run_dir / 'RUN_LOG.txt')
    native = os.name == 'nt' and not a.offline_preflight
    receipt = dict(schema=DRIVER_SCHEMA, RESULT_CONTEXT=RESULT_CONTEXT, mode='NATIVE_WINDOWS' if native else 'OFFLINE_PREFLIGHT',
                   PRODUCTION_MODIFIED=None, FULL_STARTED=False, B06='NOT_STARTED', G4='INCOMPLETE',
                   G5='NOT_PROVEN', BLOCKER=None, started_unix_ns=time.time_ns())
    steps = [('IDENTITY', 2), ('FINAL_PACKAGE', 3), ('SUITES', 70), ('E2E', 20), ('POSTCHECK', 2), ('RETURN', 3)]
    prog = Progress(steps)
    code = 2
    try:
        prog.begin('IDENTITY')
        app = os.environ.get('LOCALAPPDATA', '') if native else ''
        if native:
            require(sys.version_info[:3] == (3, 14, 7) and sys.maxsize > 2**32, 'PYTHON_3147_64BIT_REQUIRED')
            import re
            require(re.fullmatch(r'[A-Za-z]:\\[^%]+', app) is not None and not app.endswith('\\'), 'LOCALAPPDATA_INVALID')
            require(Path('D:\\').is_dir(), 'D_VOLUME_ABSENT')
        vols = {k: volume_info(v) for k, v in (('C', 'C:\\'), ('D', 'D:\\'))} if native else {}
        if native:
            for k, v in vols.items():
                require(v['filesystem'] == 'NTFS', 'VOLUME_NOT_NTFS:' + k)
                require(v['free_bytes'] >= 4 * 1024**3, 'VOLUME_FREE_SPACE_BELOW_4GIB:' + k)  # core free_space_gate needs 2.5 GiB
        cpu_avail = getattr(os, 'process_cpu_count', os.cpu_count)()
        receipt['PRECHECK'] = dict(python=sys.version, python_sha256=sha_file(sys.executable),
                                   platform=platform.platform(), cpu_logical=os.cpu_count(), cpu_available=cpu_avail,
                                   volumes=vols, powershell=a.ps_version, local_appdata=app)
        before = snapshot_real_targets(app) if native else {}
        (evidence / 'REAL_TARGETS_BEFORE.json').write_bytes(canonical(before))
        qman, qsha = verify_closed_manifest(bundle, 'QUAL_MANIFEST.json', 'TICKSTORE_CDT15_R41_QUAL_BUNDLE_MANIFEST_V001')
        receipt['QUAL_MANIFEST_SHA256'] = qsha
        print('QUAL_IDENTITY=PASS PYTHON=%s CPU=%s/%s' % (sys.version.split()[0], cpu_avail, os.cpu_count()), flush=True)
        prog.end('IDENTITY')

        prog.begin('FINAL_PACKAGE')
        final = verify_and_extract_final(bundle, work)
        receipt['SOURCE_SHA256'] = final['witness']['package_sha256']
        receipt['MANIFEST'] = final['manifest_sha256']
        receipt['RUNTIME_CODE_MANIFEST_SHA256'] = final['plan']['runtime_code_manifest_sha256']
        receipt['TESTED_CODE_EQUALS_PACKAGED_CODE'] = 'PASS_TESTS_EXECUTED_FROM_EXTRACTED_FINAL_PACKAGE'
        print('QUAL_FINAL_PACKAGE=PASS SHA256=%s MEMBERS=%d' % (receipt['SOURCE_SHA256'], final['members']), flush=True)
        prog.end('FINAL_PACKAGE')

        prog.begin('SUITES')
        impl = Path(final['extract']) / 'implementation_v001'
        tmp = work / 'TMP'; tmp.mkdir(parents=True, exist_ok=False)
        env = dict(os.environ, TMP=str(tmp), TEMP=str(tmp), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
        env.pop('PYTHONPATH', None)
        d_parent = Path(a.d_parent) / run_dir.name if native else work / 'D_PARENT'
        suites = []
        for name, spec in final['plan']['suites'].items():
            senv = dict(env)
            if spec.get('writer_sandboxes'):
                senv['TICKSTORE_QUAL_D_PARENT'] = str(d_parent / name)
                senv['TICKSTORE_QUAL_C_PARENT'] = str(work / ('C_' + name))
                if not native:
                    senv.pop('TICKSTORE_QUAL_D_PARENT'); senv.pop('TICKSTORE_QUAL_C_PARENT')
            if spec.get('native_only') and not native:
                suites.append({'suite': name, 'status': 'NOT_NATIVE_SKIPPED_OFFLINE'}); continue
            suites.append(run_suite(name, spec, impl, senv, evidence, sys.executable))
        for name, spec in final['plan']['scripts'].items():
            if spec.get('native_only') and not native:
                suites.append({'suite': name, 'status': 'NOT_NATIVE_SKIPPED_OFFLINE'}); continue
            suites.append(run_script(name, spec['script'], impl, env, evidence, sys.executable, spec['expect'],
                                     isolated=spec.get('isolated', True), timeout=spec.get('timeout', 600)))
        for name, spec in final['plan'].get('scenarios', {}).items():
            suites.append(run_scenario(name, spec, Path(bundle), impl, work, env, evidence, sys.executable, native))
        if 'b1' in final['plan']:
            suites.append(run_b1(Path(bundle), impl, work, env, evidence, sys.executable, native))
        receipt['TESTS'] = suites
        prog.end('SUITES')

        prog.begin('E2E')
        receipt['E2E'] = (e2e(final, sys.executable, work, d_parent, evidence, env, native)
                          if final['plan'].get('e2e', True) else {'status': 'NOT_IN_PLAN_UNCHANGED_SINCE_R42'})
        prog.end('E2E')

        prog.begin('POSTCHECK')
        after = snapshot_real_targets(app) if native else {}
        (evidence / 'REAL_TARGETS_AFTER.json').write_bytes(canonical(after))
        receipt['PRODUCTION_MODIFIED'] = (before != after) if native else False
        receipt['REAL_TARGETS_BEFORE_SHA256'] = sha_bytes(canonical(before))
        failed = [s['suite'] for s in suites if s['status'] not in ('PASS', 'NOT_NATIVE_SKIPPED_OFFLINE', 'OFFLINE_HARNESS_PASS')]
        e2e_ok = receipt['E2E']['status'] in ('PASS', 'NOT_NATIVE_SKIPPED_OFFLINE', 'NOT_IN_PLAN_UNCHANGED_SINCE_R42')
        if receipt['PRODUCTION_MODIFIED']:
            receipt['BLOCKER'] = 'REAL_TARGET_CHANGED_DURING_QUALIFICATION'
        elif failed or not e2e_ok:
            receipt['BLOCKER'] = 'QUALIFICATION_FAIL:' + ','.join(failed + ([] if e2e_ok else ['E2E']))
        passed = receipt['BLOCKER'] is None
        rev = final['plan'].get('revision', 'R41')
        receipt['REVISION'] = rev
        receipt['CLASSIFICATION'] = ((rev + '_WINDOWS_SANDBOX_QUALIFICATION_PASS' if native else 'OFFLINE_PREFLIGHT_ONLY')
                                     if passed else rev + '_WINDOWS_SANDBOX_QUALIFICATION_FAIL')
        receipt['SCOPE'] = ('Native PS5.1/Python 3.14.7 sandbox evidence for the ' + rev + ' delta only. Not G4/G5/B06/B07, '
                            'not production admission, not power-loss durability (process death only).')
        code = 0 if passed else 2
        prog.end('POSTCHECK')
    except KeyboardInterrupt:
        receipt['BLOCKER'] = 'INTERRUPTED_BY_OPERATOR'; receipt['CLASSIFICATION'] = 'INTERRUPTED'; code = 130
    except BaseException as exc:
        receipt['BLOCKER'] = type(exc).__name__ + ':' + str(exc)
        receipt['CLASSIFICATION'] = 'BLOCKED'
        (evidence / 'DRIVER_TRACEBACK.txt').write_text(traceback.format_exc(), encoding='utf-8')
        print('QUAL_BLOCKED=' + receipt['BLOCKER'], flush=True)
        code = 2
    prog.begin('RETURN')
    receipt['EXIT_CODE'] = code
    receipt['finished_unix_ns'] = time.time_ns()
    rpath = run_dir / 'QUAL_RECEIPT.json'
    rpath.write_bytes(canonical(receipt))
    ret = run_dir / ('QUAL_RETURN_' + run_dir.name + '.zip')
    with zipfile.ZipFile(ret, 'x', zipfile.ZIP_DEFLATED) as z:
        z.write(rpath, rpath.name)
        # Recursive: harness RESULT.json/TESTS.log and native artifacts live in subfolders.
        for p in sorted(evidence.rglob('*')):
            if p.is_file():
                z.write(p, 'EVIDENCE/' + p.relative_to(evidence).as_posix())
        sys.stdout.flush()
        z.write(run_dir / 'RUN_LOG.txt', 'RUN_LOG.txt')
    rsha = sha_file(ret)
    prog.end('RETURN')
    print('')
    print('RESULT_CONTEXT=' + RESULT_CONTEXT)
    print('SOURCE_SHA256=' + str(receipt.get('SOURCE_SHA256')))
    print('MANIFEST=' + str(receipt.get('MANIFEST')))
    print('TESTS=' + ' '.join('%s:%s' % (s['suite'], s['status']) for s in receipt.get('TESTS', [])))
    print('E2E=' + str(receipt.get('E2E', {}).get('status')))
    print('PRECHECK=' + ('PASS' if 'PRECHECK' in receipt else 'NOT_REACHED'))
    print('EXIT_CODE=' + str(code))
    print('RETURN_ZIP=' + str(ret))
    print('RETURN_SHA256=' + rsha)
    print('PRODUCTION_MODIFIED=' + str(receipt['PRODUCTION_MODIFIED']).upper())
    print('FULL_STARTED=NO')
    print('BLOCKER=' + str(receipt['BLOCKER']))
    print('CLASSIFICATION=' + str(receipt.get('CLASSIFICATION')))
    print('RESULT_RETURN_TO=' + RESULT_CONTEXT)
    return code


if __name__ == '__main__':
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--run-suite-child', action='store_true')
    ap.add_argument('--impl'); ap.add_argument('--spec'); ap.add_argument('--out')
    ap.add_argument('--run-dir'); ap.add_argument('--work-root'); ap.add_argument('--bundle-dir')
    ap.add_argument('--d-parent', default='D:\\TICKSTORE_QUALIFICATION_SANDBOX')
    ap.add_argument('--ps-version', default='UNKNOWN')
    ap.add_argument('--offline-preflight', action='store_true')
    args = ap.parse_args()
    if args.run_suite_child:
        raise SystemExit(run_suite_child(args.impl, args.spec, args.out))
    raise SystemExit(main(args))
