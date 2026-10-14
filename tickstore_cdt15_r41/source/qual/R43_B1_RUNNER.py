"""R43 B1: the 126 contract IDs on the CURRENT candidate bytes (Windows native selection).

Inputs are hash-bound: the origin R3 archive (unchanged), the origin-authorized derived
tests_full_lifecycle.py (parent EE30AA93..., derived hash from the plan), the original
126-ID contract, and the extracted FINAL candidate with its runtime manifest.
Historical PASS is never inherited: every ID is executed here on the current bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()


def require(cond, why):
    if not cond:
        raise RuntimeError(why)


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for k in ('bundle', 'impl', 'work', 'evidence', 'plan'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--offline', action='store_true')
    a = ap.parse_args()
    bundle, impl, work, ev = Path(a.bundle), Path(a.impl), Path(a.work), Path(a.evidence)
    spec = json.loads(Path(a.plan).read_bytes())['b1']
    out = {'schema': 'TICKSTORE_CDT15_R43_B1_RESULT_V001', 'mode': 'OFFLINE_HARNESS_CHECK' if a.offline else 'NATIVE_WINDOWS',
           'baseline_results_counted_as_delta': False, 'production_execution': False}
    try:
        r3zip = bundle / spec['r3_archive']
        require(sha(r3zip) == spec['r3_archive_sha256'], 'R3_ARCHIVE_SHA256')
        contract_path = bundle / spec['contract']
        require(sha(contract_path) == spec['contract_sha256'], 'CONTRACT_SHA256')
        contract = json.loads(contract_path.read_bytes())['required_tests']
        require(len(contract) == 126 and len(set(contract)) == 126, 'CONTRACT_126_UNIQUE')
        cand_contract = impl / 'candidate/control/QUALIFICATION_CONTRACT.json'
        require(sha(cand_contract) == spec['contract_sha256'], 'CANDIDATE_CONTRACT_NOT_ORIGINAL')
        tree = work / 'B1_R3'
        require(not tree.exists(), 'B1_TREE_EXISTS')
        with zipfile.ZipFile(r3zip) as z:
            require(z.testzip() is None, 'R3_ARCHIVE_CRC')
            z.extractall(tree)
        target = tree / 'engineering/tests_full_lifecycle.py'
        require(sha(target) == spec['parent_sha256'], 'R3_PARENT_TEST_SHA256')
        derived = bundle / spec['derived']
        require(sha(derived) == spec['derived_sha256'], 'DERIVED_TEST_SHA256')
        # The extracted R3 copy is a disposable working tree; the R3 archive itself is untouched.
        target.write_bytes(derived.read_bytes())
        require(sha(target) == spec['derived_sha256'], 'DERIVED_OVERLAY_READBACK')
        probes = bundle / spec['microprobes']
        require(sha(probes) == spec['microprobes_sha256'], 'MICROPROBES_SHA256')
        (tree / 'engineering/R43_B1A_MICROPROBES.py').write_bytes(probes.read_bytes())
        out.update(r3_archive_sha256=spec['r3_archive_sha256'], parent_sha256=spec['parent_sha256'],
                   derived_sha256=spec['derived_sha256'], contract_sha256=spec['contract_sha256'])

        cand = impl / 'candidate'
        env = dict(os.environ, TICKSTORE_TEST_CANDIDATE=str(cand),
                   TICKSTORE_TEST_MANIFEST=str(impl / 'RUNTIME_CODE_MANIFEST.json'), PYTHONDONTWRITEBYTECODE='1')
        harness = tree / 'engineering/run_current_delta.py'
        sel = ['--native'] if not a.offline else []
        lst = work / 'B1_IDS.json'
        r = subprocess.run([sys.executable, '-B', str(harness), '--list', '--output', str(lst)] + ['--native'],
                           env=env, capture_output=True, text=True, timeout=300)
        require(r.returncode == 0, 'HARNESS_LIST:' + r.stderr[-2000:])
        ids = json.loads(lst.read_bytes())
        require(len(ids) == 126 and set(ids) == set(contract), 'HARNESS_SELECTION_NOT_CONTRACT')
        out['selection'] = {'ids': 126, 'equals_contract': True, 'portable': spec['portable'], 'native_only': spec['native_only']}

        t0 = time.monotonic()
        res_dir = ev / 'B1_HARNESS'
        r = subprocess.run([sys.executable, '-B', str(harness), '--output', str(res_dir)] + sel,
                           env=env, capture_output=True, text=True, timeout=7200)
        (ev / 'B1_HARNESS_STDIO.txt').write_text(r.stdout[-400000:] + '\n---STDERR---\n' + r.stderr[-100000:],
                                                 encoding='utf-8')
        report = json.loads((res_dir / 'RESULT.json').read_bytes())
        statuses = {t['id']: t['status'] for t in report['tests']}
        out['harness'] = {k: report.get(k) for k in ('native_windows', 'selection', 'code_manifest_sha256',
                          'tested_code_unchanged', 'totals', 'tests_expected', 'tests_not_run', 'tests_interrupted',
                          'interruption', 'byte_revalidation_error', 'success')}
        out['harness']['seconds'] = round(time.monotonic() - t0, 3)
        out['tests'] = [{'id': i, 'status': statuses.get(i, 'NOT_SELECTED_OFFLINE' if a.offline else 'NOT_RUN')}
                        for i in contract]
        out['non_pass'] = [t for t in out['tests'] if t['status'] != 'PASS']
        out['predicted_r43_b1b'] = spec['predicted_b1b']

        pr = subprocess.run([sys.executable, '-B', '-c',
                             'import sys,unittest;sys.path[:0]=[sys.argv[1],sys.argv[2]];'
                             'import R43_B1A_MICROPROBES as m;r=unittest.TextTestRunner(verbosity=2).run(m.suite());'
                             'sys.exit(0 if r.wasSuccessful() and r.testsRun==5 and not r.skipped else 2)',
                             str(tree / 'engineering'), str(tree / 'cdt15')],
                            env=env, capture_output=True, text=True, timeout=600)
        (ev / 'B1A_MICROPROBES.txt').write_text(pr.stdout + '\n---STDERR---\n' + pr.stderr, encoding='utf-8')
        out['microprobes'] = 'PASS_5_OF_5' if pr.returncode == 0 else 'FAIL'
        expected_total = 126 if not a.offline else spec['portable']
        ran_pass = sum(1 for t in out['tests'] if t['status'] == 'PASS')
        out['counts'] = {'pass': ran_pass, 'expected_executed': expected_total,
                         'non_pass': len([t for t in out['non_pass'] if t['status'] != 'NOT_SELECTED_OFFLINE'])}
        ok = (ran_pass == expected_total and out['counts']['non_pass'] == 0 and report.get('tested_code_unchanged') is True
              and out['microprobes'] == 'PASS_5_OF_5')
        out['status'] = ('PASS' if ok else 'FAIL') if not a.offline else ('OFFLINE_HARNESS_PASS' if ok else 'FAIL')
    except BaseException as exc:
        import traceback
        out['status'] = 'ERROR'
        out['error'] = type(exc).__name__ + ':' + str(exc)
        out['traceback'] = traceback.format_exc()[-6000:]
    (ev / 'B1_RESULT.json').write_text(json.dumps(out, indent=1, sort_keys=True), encoding='utf-8')
    np = ' '.join(t['id'].split('.')[-1] + '=' + t['status'] for t in out.get('non_pass', [])
                  if t['status'] != 'NOT_SELECTED_OFFLINE')
    print('R43_B1 status=%s pass=%s/%s microprobes=%s %s' % (out['status'], out.get('counts', {}).get('pass'),
          out.get('counts', {}).get('expected_executed'), out.get('microprobes'), ('NON_PASS: ' + np) if np else ''),
          flush=True)
    return 0 if out['status'] in ('PASS', 'OFFLINE_HARNESS_PASS') else 2


if __name__ == '__main__':
    raise SystemExit(main())
