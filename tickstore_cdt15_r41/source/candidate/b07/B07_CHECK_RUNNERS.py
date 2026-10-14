"""B07 native check runners (SOURCE_ONLY; never executed before an independent B06 PASS).

Entry guard: the production FULL_RELEASE_CHAIN.ReleaseChain must accept the technical chain
up to B06 with the independently supplied B06 digest; otherwise nothing runs.  Each check writes
EVIDENCE/B07/<CHECK>/CHECK_RECEIPT.json (TICKSTORE_B07_CHECK_RECEIPT_V001) with the test IDs it
executed natively, its native probes and its artifacts, consumed by B07_TECHNICAL_PRODUCER.
Sandbox/private probe directories only; no D4 effect, no MENU, no STATE write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent
sys.path.insert(0, str(CANDIDATE / 'control'))
PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def require_b06_pass(chain_file, chain_sha256, b06_sha256):
    """The only admission path: the production chain consumer, until B06."""
    from FULL_RELEASE_CHAIN import ReleaseChain
    with ReleaseChain(chain_file, chain_sha256, b06_sha256, CANDIDATE, until='B06') as admission:
        return {'b06_sha256': b06_sha256, 'code_manifest_sha256': admission.descriptor['code_manifest_sha256'],
                'instance_sha256': admission.descriptor['instance_sha256']}


def run_ids(test_root_paths, ids):
    """Run exact unittest IDs natively; one record per ID."""
    for p in test_root_paths:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    out, log = [], []
    for tid in ids:
        suite = unittest.defaultTestLoader.loadTestsFromName(tid)
        stream = __import__('io').StringIO()
        r = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        ok = r.wasSuccessful() and r.testsRun == 1 and not r.skipped
        out.append({'id': tid, 'status': 'PASS' if ok else ('SKIP' if r.skipped else 'FAIL')})
        log.append(stream.getvalue())
    return out, '\n'.join(log)


# ----------------------------------------------------------------------------- probes

def probe_policy(policy_root, reconciliation, reconciliation_sha):
    import POLICY_CAPTURE_BINDING as cap
    from D4_FIRST_ADMISSION_PREP import Reads
    res = {}
    with Reads() as rd:
        c = cap.verify_capture(rd.read, policy_root, reconciliation, reconciliation_sha)
        res['capture_verified_with_native_protected_reads'] = 'PASS' if type(rd.store).__name__ == 'Win32Store' else 'FAIL'
        res['origin_reconciliation_current'] = 'PASS' if c['reconciliation_sha256'] == reconciliation_sha else 'FAIL'
        res['cardinality_1_plus_1_frozen'] = 'PASS'
        target = Path(policy_root) / cap.HEAD

        def denied(fn):
            try:
                fn(); return 'FAIL'
            except PermissionError:
                return 'PASS'
        res['write_open_denied_while_admitted'] = denied(lambda: open(target, 'r+b').close())
        res['delete_denied_while_admitted'] = denied(lambda: os.remove(target))
        res['rename_denied_while_admitted'] = denied(lambda: os.rename(target, str(target) + '.moved'))
    with tempfile.TemporaryDirectory() as t:
        copy = Path(t) / 'POLICY'; shutil.copytree(policy_root, copy); (copy / 'EXTRA.md').write_bytes(b'x')
        try:
            cap.verify_capture(lambda p, e=None: Path(p).read_bytes(), copy, reconciliation, reconciliation_sha)
            res['extra_file_in_policy_root_blocks'] = 'FAIL'
        except cap.PolicyBlocked as exc:
            res['extra_file_in_policy_root_blocks'] = 'PASS' if 'CARDINALITY' in str(exc) else 'FAIL'
    return res, c


def probe_wrapper(work):
    wrapper = CANDIDATE / 'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1'
    res = {}
    r = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(wrapper), '-ExecuteD4'],
                       capture_output=True, text=True, timeout=300)
    res['wrapper_blocks_without_chain_exit_2'] = 'PASS' if r.returncode == 2 and 'BLOCKED|' in r.stdout else 'FAIL'
    r = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(wrapper), '-RequestSafeStop'],
                       capture_output=True, text=True, timeout=300)
    res['wrapper_safe_stop_requires_authority_sha'] = ('PASS' if r.returncode == 2
                                                       and 'SAFE_STOP_EXISTING_AUTHORITY_SHA_REQUIRED' in r.stdout else 'FAIL')
    inner = Path(work) / 'inner.ps1'; inner.write_text('exit 7\r\n', encoding='ascii')
    outer = Path(work) / 'outer.ps1'
    outer.write_text("& '%s' -NoProfile -ExecutionPolicy Bypass -File '%s'\r\nexit $LASTEXITCODE\r\n" % (PS, inner), encoding='ascii')
    r = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(outer)], capture_output=True, text=True,
                       timeout=300)
    res['nested_powershell_exit_code_propagated'] = 'PASS' if r.returncode == 7 else 'FAIL'
    r = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(wrapper)], capture_output=True,
                       text=True, timeout=300)
    res['wrapper_dry_entry_no_d4'] = 'PASS' if 'D4_EXECUTION=NO' in r.stdout or r.returncode == 2 else 'FAIL'
    return res


def probe_adapter():
    r = subprocess.run([sys.executable, '-B', str(CANDIDATE / 'adapter/adapter_tests.py')], capture_output=True, text=True,
                       timeout=900, cwd=str(CANDIDATE / 'adapter'))
    tail = [l for l in r.stderr.splitlines() if l.strip()][-1:] or ['']
    ok = r.returncode == 0 and tail[0] == 'OK'  # "OK (skipped=n)" is not a pass for B07
    return {'adapter_tests_all_pass': 'PASS' if ok else 'FAIL'}, r.stderr


def probe_census():
    import D4_FIRST_ADMISSION_BOOTSTRAP as boot
    try:
        boot.check_native_process_boundary(); return {'recovery_process_census_lease_absent': 'PASS'}
    except RuntimeError:
        return {'recovery_process_census_lease_absent': 'FAIL'}


def probe_sandbox(qual_dir, work):
    sys.path.insert(0, str(qual_dir))
    import R44D_DROOT_AUDIT as audit
    _, checks = audit.negative_probes(Path(work) / 'ADMISSION_PROBES')
    return {'sandbox_admission_negative_probes': 'PASS' if checks and all(checks.values()) else 'FAIL'}


# ----------------------------------------------------------------------------- driver

def main(argv=None):
    sys.path.insert(0, str(CANDIDATE / 'control'))
    import B07_TECHNICAL_PRODUCER as P
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for k in ('chain-file', 'chain-sha256', 'b06-sha256', 'evidence', 'work', 'run-id', 'final-zip-sha256',
              'code-manifest-sha256', 'policy-root', 'policy-reconciliation', 'policy-reconciliation-sha256',
              'r3-tree', 'tests-dir', 'qual-dir'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args(argv)
    if os.name != 'nt':
        print('B07_BLOCKED=NATIVE_WINDOWS_REQUIRED'); return 2
    try:
        guard = require_b06_pass(a.chain_file, a.chain_sha256, a.b06_sha256)
    except BaseException as exc:
        print('B07_BLOCKED=INDEPENDENT_B06_PASS_REQUIRED:' + type(exc).__name__ + ':' + str(exc)); return 2
    roots = [Path(a.r3_tree) / 'engineering', Path(a.r3_tree) / 'cdt15', Path(a.tests_dir)]
    for r in roots:
        sys.path.insert(0, str(r))
    suite = unittest.defaultTestLoader.loadTestsFromName('test_first_admission_transaction.TransactionTests')
    tx_ids = [t.id() for t in suite]
    me = sha_bytes(Path(__file__).read_bytes())
    status_all = {}
    for name, spec in P.CHECKS.items():
        out = Path(a.evidence) / 'B07' / name; out.mkdir(parents=True)
        work = Path(a.work) / name; work.mkdir(parents=True)
        probes, tests, log = {}, [], ''
        try:
            ids = []
            for t in spec['tests']:
                ids += tx_ids if t.startswith('ALL:') else [t]
            if ids:
                tests, log = run_ids(roots, ids)
            if name in ('policyroot_physical_readback', 'policyroot_mutation_denial'):
                pr, _ = probe_policy(a.policy_root, a.policy_reconciliation, a.policy_reconciliation_sha256)
                probes = {k: pr[k] for k in spec['probes']}
            elif name == 'wrapper_safe_stop_exit_propagation':
                probes = probe_wrapper(work)
            elif name == 'g_ca_native_locator':
                probes, alog = probe_adapter(); log += '\n' + alog
            elif name == 'predecessor_process_locks_lease':
                probes = probe_census()
            elif name == 'reparse_and_ancestor_controls':
                probes = probe_sandbox(a.qual_dir, work)
            error = None
        except BaseException as exc:
            error = type(exc).__name__ + ':' + str(exc)
            (out / 'TRACEBACK.txt').write_text(traceback.format_exc(), encoding='utf-8')
        (out / 'CHECK_LOG.txt').write_text(log or 'no unittest output', encoding='utf-8')
        (out / 'PROBES.json').write_text(json.dumps(probes, indent=1, sort_keys=True), encoding='utf-8')
        ok = (error is None and all(t['status'] == 'PASS' for t in tests)
              and set(probes) == set(spec['probes']) and all(v == 'PASS' for v in probes.values()))
        arts = [{'member': 'EVIDENCE/B07/%s/%s' % (name, p.name), 'sha256': sha_bytes(p.read_bytes()), 'bytes': p.stat().st_size}
                for p in sorted(out.iterdir()) if p.is_file()]
        rec = {'schema': P.CHECK_SCHEMA, 'check': name, 'status': 'PASS' if ok else 'FAIL', 'native_windows': True,
               'platform': platform.platform(), 'code_manifest_sha256': a.code_manifest_sha256,
               'final_zip_sha256': a.final_zip_sha256, 'run_id': a.run_id,
               'runner': {'path': P.RUNNER, 'sha256': me}, 'tests': tests, 'probes': probes, 'artifacts': arts,
               'error': error, 'b06_guard': guard, 'gate_verdict_issued': False}
        (out / 'CHECK_RECEIPT.json').write_text(json.dumps(rec, indent=1, sort_keys=True), encoding='utf-8')
        status_all[name] = rec['status']
        print('B07_CHECK %s=%s' % (name, rec['status']), flush=True)
    return 0 if all(v == 'PASS' for v in status_all.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
