"""R44-DROOT-01 delta: read-only physical admission audit of the R44 sandbox roots + negative probes.

Does NOT rerun the 126 contract IDs and does NOT touch the R44 FINAL bytes (the candidate code
identity is unchanged).  It
  1. audits, read-only, the topology the R44 campaign used: every component of
     D:\\TICKSTORE_QUALIFICATION_SANDBOX and of the R44 run directory (reparse attribute,
     final-path resolution, NTFS, volume serial, file index, creation time) and censuses the
     reparse points that remain inside the R44 D: run tree;
  2. proves the admission check used by future runners (SANDBOX_ADMISSION.admit_root /
     revalidate) with native NEGATIVE controls in private probe directories: junction,
     directory symlink, file symlink, ancestor junction, plain file, missing root, swap of the
     admitted root by a junction and by a different directory;
  3. writes a receipt and a closed RETURN ZIP with RETURN_MANIFEST and readback.
Writes only inside its own run-owned probe directories.  No MENU, STATE or production path.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import sys
import time
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import SANDBOX_ADMISSION as A  # noqa: E402

SCHEMA = 'TICKSTORE_CDT15_R44D_DROOT_RECEIPT_V001'
RESULT_CONTEXT = 'ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compress\u00e3o De Ticks 15'
R44_RUN = 'R44_QUAL_20261014_065214_300_41492'
R44_STARTED_LOCAL = dt.datetime(2026, 10, 14, 6, 52, 14)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def canonical(obj):
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, default=str) + '\n').encode('utf-8')


class Tee:
    def __init__(self, stream, path):
        self.stream, self.f = stream, open(path, 'a', encoding='utf-8')

    def write(self, s):
        self.stream.write(s); self.f.write(s); self.f.flush(); return len(s)

    def flush(self):
        self.stream.flush(); self.f.flush()


def verify_bundle(bundle):
    man = json.loads((bundle / 'QUAL_MANIFEST.json').read_bytes())
    listed = {}
    for f in man['files']:
        p = bundle / f['path']
        if not (p.is_file() and p.stat().st_size == f['bytes'] and sha_bytes(p.read_bytes()) == f['sha256']):
            raise RuntimeError('BUNDLE_MEMBER:' + f['path'])
        listed[f['path']] = f
    physical = {p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()} - {'QUAL_MANIFEST.json'}
    if physical != set(listed):
        raise RuntimeError('BUNDLE_CLOSED_SET')
    return sha_bytes((bundle / 'QUAL_MANIFEST.json').read_bytes())


def outcome(fn):
    try:
        return {'result': 'ADMITTED', 'record': fn()}
    except A.AdmissionBlocked as exc:
        return {'result': 'REJECTED', 'reason': str(exc)}
    except OSError as exc:
        return {'result': 'OS_ERROR', 'reason': type(exc).__name__ + ':' + str(exc)}


def birth(path):
    try:
        st = os.stat(path, follow_symlinks=False)
        b = getattr(st, 'st_birthtime', None)
        return dt.datetime.fromtimestamp(b).isoformat() if b else None
    except OSError:
        return None


def audit_existing(d_parent, r44_d, r44_c, r44_log):
    out = {}
    out['d_root'] = outcome(lambda: A.admit_root(d_parent))
    out['d_root']['created_local'] = birth(d_parent)
    out['r44_d_run'] = outcome(lambda: A.admit_root(r44_d))
    out['r44_d_run']['created_local'] = birth(r44_d)
    out['r44_c_work'] = outcome(lambda: A.admit_root(r44_c))
    # The log root lives under OneDrive (Cloud Files reparse folders by design): informative only.
    out['r44_log_dir_onedrive'] = outcome(lambda: A.admit_root(r44_log))
    out['r44_d_tree'] = A.audit_tree(r44_d) if os.path.isdir(r44_d) else {'missing': True}
    inside = []
    for item in out['r44_d_tree'].get('reparse_points', []):
        tgt = str(item.get('target', ''))
        tgt_abs = tgt[4:] if tgt.startswith(('\\\\?\\', '\\??\\')) else tgt
        item['target_within_r44_d_run'] = bool(tgt_abs) and os.path.normcase(os.path.abspath(
            os.path.join(os.path.dirname(item['path']), tgt_abs))).startswith(os.path.normcase(str(r44_d)) + os.sep)
        inside.append(item['target_within_r44_d_run'])
    out['r44_d_tree']['all_reparse_targets_inside_run'] = all(inside)
    created = out['r44_d_run'].get('created_local')
    out['r44_d_run_created_by_r44'] = bool(created) and dt.datetime.fromisoformat(created) >= R44_STARTED_LOCAL
    return out


def negative_probes(root):
    """Admission behaviour on a private, run-owned probe directory (native objects)."""
    import _winapi
    r = {}
    root.mkdir(parents=True)
    target = root / 'TARGET'; target.mkdir()
    plain = root / 'PLAIN'; plain.mkdir()
    r['plain_directory'] = outcome(lambda: A.admit_root(plain))
    j = root / 'JUNCTION'; _winapi.CreateJunction(str(target), str(j))
    r['junction_root'] = outcome(lambda: A.admit_root(j))
    r['child_of_junction'] = outcome(lambda: A.admit_root(j / 'CHILD', must_exist=False))
    ds = root / 'DIR_SYMLINK'; os.symlink(target, ds, target_is_directory=True)
    r['directory_symlink_root'] = outcome(lambda: A.admit_root(ds))
    (target / 'f.txt').write_bytes(b'x')
    fs = root / 'FILE_SYMLINK'; os.symlink(target / 'f.txt', fs)
    r['file_symlink_root'] = outcome(lambda: A.admit_root(fs))
    pf = root / 'PLAIN_FILE'; pf.write_bytes(b'x')
    r['plain_file_root'] = outcome(lambda: A.admit_root(pf))
    r['missing_root'] = outcome(lambda: A.admit_root(root / 'MISSING'))
    r['relative_path'] = outcome(lambda: A.admit_root('relative\\path'))
    # Swap after admission: by a junction, then by a different plain directory.
    sw = root / 'SWAP'; sw.mkdir()
    rec = A.admit_root(sw)
    os.rename(sw, root / 'SWAP_ORIGINAL'); _winapi.CreateJunction(str(target), str(sw))
    r['swap_to_junction_revalidate'] = outcome(lambda: A.revalidate(rec))
    os.rmdir(sw)  # removes the junction itself, never its target
    sw.mkdir()
    r['swap_to_new_directory_revalidate'] = outcome(lambda: A.revalidate(rec))
    shutil.rmtree(sw); os.rename(root / 'SWAP_ORIGINAL', sw)
    r['restored_original_revalidate'] = outcome(lambda: A.revalidate(rec))
    expect = {'plain_directory': 'ADMITTED', 'junction_root': 'REJECTED', 'child_of_junction': 'REJECTED',
              'directory_symlink_root': 'REJECTED', 'file_symlink_root': 'REJECTED', 'plain_file_root': 'REJECTED',
              'missing_root': 'REJECTED', 'relative_path': 'REJECTED', 'swap_to_junction_revalidate': 'REJECTED',
              'swap_to_new_directory_revalidate': 'REJECTED', 'restored_original_revalidate': 'ADMITTED'}
    checks = {k: r[k]['result'] == v for k, v in expect.items()}
    return r, checks


def write_return(run_dir, evidence, receipt_path):
    sys.stdout.flush()
    members = [(receipt_path.name, receipt_path.read_bytes()), ('RUN_LOG.txt', (run_dir / 'RUN_LOG.txt').read_bytes())]
    members += [('EVIDENCE/' + p.relative_to(evidence).as_posix(), p.read_bytes())
                for p in sorted(evidence.rglob('*')) if p.is_file()]
    man = canonical({'schema': 'TICKSTORE_CDT15_RETURN_MANIFEST_V001', 'run_id': run_dir.name,
                     'files': [{'path': n, 'bytes': len(b), 'sha256': sha_bytes(b)} for n, b in members]})
    ret = run_dir / ('QUAL_RETURN_' + run_dir.name + '.zip')
    with zipfile.ZipFile(ret, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, b in members:
            z.writestr(n, b)
        z.writestr('RETURN_MANIFEST.json', man)
    with zipfile.ZipFile(ret) as z:
        assert z.testzip() is None
        listed = json.loads(z.read('RETURN_MANIFEST.json'))['files']
        assert {f['path'] for f in listed} == set(z.namelist()) - {'RETURN_MANIFEST.json'}
        assert all(sha_bytes(z.read(f['path'])) == f['sha256'] for f in listed)
    rsha = sha_bytes(ret.read_bytes())
    (run_dir / (ret.name + '.sha256.txt')).write_text(rsha + '  ' + ret.name + '\n', encoding='ascii')
    return ret, rsha, len(listed) + 1


def main(a):
    run_dir = Path(a.run_dir); work = Path(a.work_root); bundle = Path(a.bundle_dir); d_parent = Path(a.d_parent)
    evidence = run_dir / 'EVIDENCE'; evidence.mkdir()
    sys.stdout = Tee(sys.stdout, run_dir / 'RUN_LOG.txt'); sys.stderr = Tee(sys.stderr, run_dir / 'RUN_LOG.txt')
    app = os.environ.get('LOCALAPPDATA', '')
    receipt = {'schema': SCHEMA, 'RESULT_CONTEXT': RESULT_CONTEXT, 'RUN_ID': run_dir.name, 'audited_run': R44_RUN,
               'mode': 'NATIVE_WINDOWS', 'R44_126_RERUN': False, 'FINAL_BYTES_TOUCHED': False,
               'PRODUCTION_MODIFIED': None, 'FULL_STARTED': False, 'GATE_VERDICT_ISSUED': False, 'BLOCKER': None}
    code = 2
    try:
        if os.name != 'nt':
            raise RuntimeError('NATIVE_WINDOWS_REQUIRED')
        elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
        receipt['PRECHECK'] = {'python': sys.version, 'platform': platform.platform(), 'powershell': a.ps_version,
                               'elevated': elevated}
        if not elevated:
            raise RuntimeError('ELEVATION_REQUIRED_RUN_AS_ADMINISTRATOR')
        receipt['QUAL_MANIFEST_SHA256'] = verify_bundle(bundle)
        print('R44D_IDENTITY=PASS ELEVATED=YES', flush=True)
        r44_d = d_parent / R44_RUN
        r44_c = Path(app) / 'TICKSTORE_QUAL_R44' / R44_RUN
        r44_log = Path(r'C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS') / R44_RUN
        audit = audit_existing(d_parent, r44_d, r44_c, r44_log)
        (evidence / 'R44_TOPOLOGY_AUDIT.json').write_bytes(canonical(audit))
        print('R44D_AUDIT D_ROOT=%s R44_D_RUN=%s R44_C_WORK=%s TREE_REPARSE=%d TARGETS_INSIDE=%s CREATED_BY_R44=%s' % (
            audit['d_root']['result'], audit['r44_d_run']['result'], audit['r44_c_work']['result'],
            len(audit['r44_d_tree'].get('reparse_points', [])), audit['r44_d_tree'].get('all_reparse_targets_inside_run'),
            audit['r44_d_run_created_by_r44']), flush=True)
        probes = {}
        c_probe = work / 'PROBE_C'
        probes['C'], c_checks = negative_probes(c_probe)
        d_checks = {}
        if audit['d_root']['result'] == 'ADMITTED':
            d_probe = d_parent / run_dir.name / 'PROBE_D'
            probes['D'], d_checks = negative_probes(d_probe)
        else:
            probes['D'] = {'skipped': 'D_ROOT_NOT_ADMITTED_NO_WRITE_ON_D'}
        (evidence / 'NEGATIVE_PROBES.json').write_bytes(canonical({'results': probes, 'checks_c': c_checks, 'checks_d': d_checks}))
        for vol, ch in (('C', c_checks), ('D', d_checks)):
            print('R44D_NEGATIVE_PROBES_%s %s' % (vol, ' '.join('%s=%s' % (k, 'PASS' if v else 'FAIL') for k, v in ch.items())),
                  flush=True)
        checks = {
            'd_root_admitted': audit['d_root']['result'] == 'ADMITTED',
            'r44_d_run_admitted': audit['r44_d_run']['result'] == 'ADMITTED',
            'r44_c_work_admitted': audit['r44_c_work']['result'] == 'ADMITTED',
            'r44_d_tree_reparse_targets_inside_run': audit['r44_d_tree'].get('all_reparse_targets_inside_run') is True,
            'negative_probes_c': bool(c_checks) and all(c_checks.values()),
            'negative_probes_d': bool(d_checks) and all(d_checks.values()),
        }
        receipt['CHECKS'] = checks
        receipt['R44_D_RUN_CREATED_BY_R44'] = audit['r44_d_run_created_by_r44']
        receipt['LIMITATION'] = ('Post-hoc evidence: the audit observes the topology now; it proves the R44 roots are plain '
                                 'NTFS directories resolving to themselves at audit time and that no reparse point inside '
                                 'the R44 D: run tree targets outside it. It cannot observe the instant of the R44 run.')
        failed = [k for k, v in checks.items() if not v]
        receipt['BLOCKER'] = ('R44_DROOT_AUDIT_FAIL:' + ','.join(failed)) if failed else None
        receipt['CLASSIFICATION'] = 'R44D_DROOT_AUDIT_PASS' if not failed else 'R44D_DROOT_AUDIT_FAIL'
        code = 0 if not failed else 2
    except BaseException as exc:
        receipt['BLOCKER'] = type(exc).__name__ + ':' + str(exc)
        receipt['CLASSIFICATION'] = 'BLOCKED'
        (evidence / 'DRIVER_TRACEBACK.txt').write_text(traceback.format_exc(), encoding='utf-8')
        print('R44D_BLOCKED=' + receipt['BLOCKER'], flush=True)
    receipt['PRODUCTION_MODIFIED'] = False
    receipt['EXIT_CODE'] = code
    rpath = run_dir / 'QUAL_RECEIPT.json'; rpath.write_bytes(canonical(receipt))
    print('RESULT_CONTEXT=' + RESULT_CONTEXT)
    print('CHECKS=' + ' '.join('%s:%s' % (k, 'PASS' if v else 'FAIL') for k, v in receipt.get('CHECKS', {}).items()))
    print('R44_126_RERUN=NO FINAL_BYTES_TOUCHED=NO PRODUCTION_MODIFIED=FALSE FULL_STARTED=NO GATE_VERDICT_ISSUED=NO')
    print('BLOCKER=' + str(receipt['BLOCKER']))
    print('CLASSIFICATION=' + str(receipt.get('CLASSIFICATION')))
    print('EXIT_CODE=' + str(code))
    try:
        ret, rsha, n = write_return(run_dir, evidence, rpath)
        print('RETURN_ZIP=' + str(ret)); print('RETURN_SHA256=' + rsha); print('RETURN_MEMBERS=%d RETURN_READBACK=PASS' % n)
    except BaseException as exc:
        print('RETURN_ZIP_BLOCKED=' + type(exc).__name__ + ':' + str(exc)); code = 2
    print('RESULT_RETURN_TO=' + RESULT_CONTEXT)
    return code


if __name__ == '__main__':
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for k in ('run-dir', 'work-root', 'bundle-dir'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--d-parent', default='D:\\TICKSTORE_QUALIFICATION_SANDBOX')
    ap.add_argument('--ps-version', default='UNKNOWN')
    raise SystemExit(main(ap.parse_args()))
