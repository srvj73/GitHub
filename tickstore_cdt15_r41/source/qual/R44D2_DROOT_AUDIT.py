"""R44D2 (successor of R44D, origin finding R44D-ORIGIN-01): fail-closed sandbox admission audit.

Differences from R44D (kept byte-identical for the record):
  * D:\\TICKSTORE_QUALIFICATION_SANDBOX is NEVER created: it must already exist and is admitted
    (no reparse component, resolves to itself, NTFS) and HELD (handles on every component,
    no FILE_SHARE_DELETE, opened on the object itself) BEFORE the first write on D:.
  * The run directory on D: is created exclusively under the held root (pre-existing or
    reparse names refuse), then held; its identity is verified before and after the probes.
  * Every directory this driver creates is journaled with a sequence number, so the receipt
    shows that no D: write precedes the D: admission.
  * Adversarial admission controls (native objects, private trees on C: and inside the held
    D: run dir): redirected ancestor, root junction, absent root (not created), pre-existing
    run dir, pre-existing junction run dir, rename/delete of a held root, swap detection.
Read-only towards everything outside its own run directories.  No 126 rerun; R44 FINAL untouched.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import SANDBOX_ADMISSION as A  # noqa: E402
import R44D_DROOT_AUDIT as R1  # noqa: E402  (read-only helpers: bundle check, audit, return zip)

SCHEMA = 'TICKSTORE_CDT15_R44D2_DROOT_RECEIPT_V001'
WRITES = []


def journal(op, path, *, after_d_admission):
    WRITES.append({'seq': len(WRITES) + 1, 'op': op, 'path': str(path), 'after_d_admission': after_d_admission,
                   'unix_ns': time.time_ns()})


def outcome(fn):
    try:
        v = fn()
        rec = getattr(v, 'identity', None) or getattr(getattr(v, 'leaf', None), 'identity', None) or v
        if hasattr(v, 'close'):
            v.close()  # never leak a hold acquired by an (unexpectedly) admitted probe
        return {'result': 'ADMITTED', 'record': rec}
    except A.AdmissionBlocked as exc:
        return {'result': 'REJECTED', 'reason': str(exc)}
    except OSError as exc:
        return {'result': 'OS_REFUSED', 'reason': type(exc).__name__ + ':' + str(exc)[:200]}


def snapshot(root):
    return sorted((str(p.relative_to(root)), p.is_dir()) for p in Path(root).rglob('*')) if os.path.isdir(root) else None


def negative_probes(root, held_parent):
    """Reparse/identity probes inside a probe root created exclusively under a held parent."""
    import _winapi
    probe = A.create_run_dir_exclusive(held_parent, 'PROBE')
    journal('mkdir', probe.path, after_d_admission=True)
    root = Path(probe.path)
    before = probe.identity
    r = {}
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
    sw = root / 'SWAP'; sw.mkdir()
    rec = A.admit_root(sw)
    os.rename(sw, root / 'SWAP_ORIGINAL'); _winapi.CreateJunction(str(target), str(sw))
    r['swap_to_junction_revalidate'] = outcome(lambda: A.revalidate(rec))
    os.rmdir(sw); sw.mkdir()
    r['swap_to_new_directory_revalidate'] = outcome(lambda: A.revalidate(rec))
    shutil.rmtree(sw); os.rename(root / 'SWAP_ORIGINAL', sw)
    r['restored_original_revalidate'] = outcome(lambda: A.revalidate(rec))
    # Handle binding: a held directory can be neither renamed nor deleted.
    hb = root / 'HELD'; hb.mkdir()
    with A.HeldDirectory(hb) as held:
        r['rename_of_held_directory'] = outcome(lambda: os.rename(hb, root / 'HELD_MOVED'))
        r['delete_of_held_directory'] = outcome(lambda: os.rmdir(hb))
        r['held_identity_stable'] = outcome(held.verify)
    after = probe.read_identity()
    probe.verify()
    probe.close()
    expect = {'plain_directory': 'ADMITTED', 'junction_root': 'REJECTED', 'child_of_junction': 'REJECTED',
              'directory_symlink_root': 'REJECTED', 'file_symlink_root': 'REJECTED', 'plain_file_root': 'REJECTED',
              'missing_root': 'REJECTED', 'relative_path': 'REJECTED', 'swap_to_junction_revalidate': 'REJECTED',
              'swap_to_new_directory_revalidate': 'REJECTED', 'restored_original_revalidate': 'ADMITTED',
              'rename_of_held_directory': 'OS_REFUSED', 'delete_of_held_directory': 'OS_REFUSED',
              'held_identity_stable': 'ADMITTED'}
    checks = {k: r[k]['result'] == v for k, v in expect.items()}
    checks['probe_root_identity_before_equals_after'] = before == after
    return {'probe_root': str(root), 'identity_before': before, 'identity_after': after, 'results': r}, checks


def adversarial_admission(base_chain):
    """Fail-closed admission against hostile layouts built inside a private, held tree."""
    import _winapi
    adv = A.create_run_dir_exclusive(base_chain, 'ADVERSARIAL')
    journal('mkdir', adv.path, after_d_admission=True)
    base = Path(adv.path)
    real = base / 'REAL'; (real / 'DROOT').mkdir(parents=True)
    other = base / 'ELSEWHERE'; other.mkdir()
    r, checks = {}, {}
    # a) redirected ancestor: <base>\J -> REAL ; admission of J\DROOT must refuse and write nothing.
    _winapi.CreateJunction(str(real), str(base / 'J'))
    pre = snapshot(real)
    r['redirected_ancestor'] = outcome(lambda: A.HeldChain(base / 'J' / 'DROOT'))
    checks['redirected_ancestor_refused_no_write'] = (r['redirected_ancestor']['result'] == 'REJECTED'
                                                     and snapshot(real) == pre)
    # b) root itself a junction.
    _winapi.CreateJunction(str(other), str(base / 'JROOT'))
    pre = snapshot(other)
    r['root_is_junction'] = outcome(lambda: A.HeldChain(base / 'JROOT'))
    checks['root_junction_refused_no_write'] = r['root_is_junction']['result'] == 'REJECTED' and snapshot(other) == pre
    # c) absent root is never created.
    r['root_absent'] = outcome(lambda: A.HeldChain(base / 'ABSENT'))
    checks['absent_root_refused_not_created'] = (r['root_absent']['result'] == 'REJECTED'
                                                 and not os.path.lexists(base / 'ABSENT'))
    # d) pre-existing plain run dir, e) pre-existing junction run dir: exclusive creation refuses.
    with A.HeldChain(real / 'DROOT') as chain:
        (real / 'DROOT' / 'RUN_PRE').mkdir(); (real / 'DROOT' / 'RUN_PRE' / 'keep.txt').write_bytes(b'k')
        pre = snapshot(real / 'DROOT')
        r['run_dir_preexisting'] = outcome(lambda: A.create_run_dir_exclusive(chain, 'RUN_PRE'))
        checks['preexisting_run_dir_refused_unchanged'] = (r['run_dir_preexisting']['result'] == 'REJECTED'
                                                           and snapshot(real / 'DROOT') == pre)
        _winapi.CreateJunction(str(other), str(real / 'DROOT' / 'RUN_J'))
        pre_other = snapshot(other)
        r['run_dir_preexisting_junction'] = outcome(lambda: A.create_run_dir_exclusive(chain, 'RUN_J'))
        checks['junction_run_dir_refused_target_unchanged'] = (r['run_dir_preexisting_junction']['result'] == 'REJECTED'
                                                               and snapshot(other) == pre_other)
        # f) the held root cannot be renamed or deleted while held; g) happy path keeps identity.
        r['rename_held_root'] = outcome(lambda: os.rename(real / 'DROOT', real / 'DROOT_MOVED'))
        checks['held_root_rename_refused'] = r['rename_held_root']['result'] == 'OS_REFUSED'
        ok = A.create_run_dir_exclusive(chain, 'RUN_OK')
        before = ok.identity
        r['happy_path_verify'] = outcome(ok.verify)
        checks['happy_path_identity_stable'] = r['happy_path_verify']['result'] == 'ADMITTED' and ok.read_identity() == before
        ok.close()
        chain.verify()
    adv.verify(); adv.close()
    return r, checks


def main(a):
    run_dir = Path(a.run_dir); work = Path(a.work_root); bundle = Path(a.bundle_dir); d_parent = Path(a.d_parent)
    evidence = run_dir / 'EVIDENCE'; evidence.mkdir()
    sys.stdout = R1.Tee(sys.stdout, run_dir / 'RUN_LOG.txt'); sys.stderr = R1.Tee(sys.stderr, run_dir / 'RUN_LOG.txt')
    app = os.environ.get('LOCALAPPDATA', '')
    receipt = {'schema': SCHEMA, 'RESULT_CONTEXT': R1.RESULT_CONTEXT, 'RUN_ID': run_dir.name, 'audited_run': R1.R44_RUN,
               'supersedes': 'R44D (0AED17FA... / 80A3B678...) not executed per origin R44D-ORIGIN-01',
               'mode': 'NATIVE_WINDOWS', 'R44_126_RERUN': False, 'FINAL_BYTES_TOUCHED': False,
               'PRODUCTION_MODIFIED': None, 'FULL_STARTED': False, 'GATE_VERDICT_ISSUED': False, 'BLOCKER': None}
    code = 2
    chains = []
    try:
        if os.name != 'nt':
            raise RuntimeError('NATIVE_WINDOWS_REQUIRED')
        elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
        receipt['PRECHECK'] = {'python': sys.version, 'platform': platform.platform(), 'powershell': a.ps_version,
                               'elevated': elevated, 'bootstrap_sha256': a.bootstrap_sha256}
        if not elevated:
            raise RuntimeError('ELEVATION_REQUIRED_RUN_AS_ADMINISTRATOR')
        receipt['QUAL_MANIFEST_SHA256'] = R1.verify_bundle(bundle)
        receipt['TESTED_EQUALS_PACKAGED'] = {p.name: R1.sha_bytes(p.read_bytes()) for p in sorted((bundle / 'qual').glob('*.py'))}
        # 1. Read-only retrospective audit (no write anywhere).
        audit = R1.audit_existing(d_parent, d_parent / R1.R44_RUN, Path(app) / 'TICKSTORE_QUAL_R44' / R1.R44_RUN,
                                  Path(r'C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS') / R1.R44_RUN)
        (evidence / 'R44_TOPOLOGY_AUDIT.json').write_bytes(R1.canonical(audit))
        print('R44D2_AUDIT D_ROOT=%s R44_D_RUN=%s R44_C_WORK=%s TREE_REPARSE=%d TARGETS_INSIDE=%s' % (
            audit['d_root']['result'], audit['r44_d_run']['result'], audit['r44_c_work']['result'],
            len(audit['r44_d_tree'].get('reparse_points', [])), audit['r44_d_tree'].get('all_reparse_targets_inside_run')),
            flush=True)
        # 2. C: private work root (created by the bootstrap under LOCALAPPDATA) admitted and held.
        c_chain = A.HeldChain(work); chains.append(c_chain)
        c_probe = negative_probes(work, c_chain)
        c_adv = adversarial_admission(c_chain)
        # 3. D: admission + hold BEFORE the first D: write; root never created.
        d_res = {'admission': outcome(lambda: A.admit_root(d_parent))}
        d_checks, d_adv_checks = {}, {}
        if d_res['admission']['result'] == 'ADMITTED':
            d_chain = A.HeldChain(d_parent); chains.append(d_chain)
            d_res['held_identity_before'] = d_chain.leaf.identity
            run_hold = A.create_run_dir_exclusive(d_chain, run_dir.name)
            journal('mkdir', run_hold.path, after_d_admission=True)
            run_chain = A.HeldChain(run_hold.path); chains.append(run_chain); run_hold.close()
            d_probe, d_checks = negative_probes(run_chain.record['path'], run_chain)
            d_adv, d_adv_checks = adversarial_admission(run_chain)
            d_res.update(probe=d_probe, adversarial=d_adv)
            run_chain.verify(); d_chain.verify()
            d_res['held_identity_after'] = d_chain.leaf.read_identity()
        (evidence / 'ADMISSION_PROBES.json').write_bytes(R1.canonical({'C': {'probe': c_probe[0], 'adversarial': c_adv[0]},
                                                                       'D': d_res}))
        (evidence / 'WRITE_JOURNAL.json').write_bytes(R1.canonical(WRITES))
        d_writes = [w for w in WRITES if str(w['path']).upper().startswith(str(d_parent).upper())]
        checks = {
            'd_root_admitted_and_held': d_res['admission']['result'] == 'ADMITTED',
            'no_d_write_before_d_admission': bool(d_writes) and all(w['after_d_admission'] for w in d_writes),
            'd_root_identity_before_equals_after': d_res.get('held_identity_before') == d_res.get('held_identity_after'),
            'r44_d_run_admitted': audit['r44_d_run']['result'] == 'ADMITTED',
            'r44_c_work_admitted': audit['r44_c_work']['result'] == 'ADMITTED',
            'r44_d_tree_reparse_targets_inside_run': audit['r44_d_tree'].get('all_reparse_targets_inside_run') is True,
            'negative_probes_c': all(c_probe[1].values()),
            'negative_probes_d': bool(d_checks) and all(d_checks.values()),
            'adversarial_admission_c': all(c_adv[1].values()),
            'adversarial_admission_d': bool(d_adv_checks) and all(d_adv_checks.values()),
        }
        for vol, ch in (('C_PROBES', c_probe[1]), ('C_ADVERSARIAL', c_adv[1]), ('D_PROBES', d_checks), ('D_ADVERSARIAL', d_adv_checks)):
            print('R44D2_%s %s' % (vol, ' '.join('%s=%s' % (k, 'PASS' if v else 'FAIL') for k, v in ch.items())), flush=True)
        for c in chains:
            c.verify()
        receipt['CHECKS'] = checks
        receipt['LIMITATION'] = ('Retrospective diagnostic: proves the R44 roots now and the fail-closed admission '
                                 'mechanism natively; it cannot certify the D: topology at the instant of the R44 run. '
                                 'R45 performs this admission just-in-time in the same attempt.')
        failed = [k for k, v in checks.items() if not v]
        receipt['BLOCKER'] = ('R44D2_FAIL:' + ','.join(failed)) if failed else None
        receipt['CLASSIFICATION'] = 'R44D2_DROOT_ADMISSION_PASS' if not failed else 'R44D2_DROOT_ADMISSION_FAIL'
        code = 0 if not failed else 2
    except BaseException as exc:
        receipt['BLOCKER'] = type(exc).__name__ + ':' + str(exc)
        receipt['CLASSIFICATION'] = 'BLOCKED'
        (evidence / 'DRIVER_TRACEBACK.txt').write_text(traceback.format_exc(), encoding='utf-8')
        print('R44D2_BLOCKED=' + receipt['BLOCKER'], flush=True)
        code = 2
    finally:
        for c in reversed(chains):
            c.close()
    receipt['WRITE_JOURNAL_ENTRIES'] = len(WRITES)
    receipt['PRODUCTION_MODIFIED'] = False
    receipt['EXIT_CODE'] = code
    rpath = run_dir / 'QUAL_RECEIPT.json'; rpath.write_bytes(R1.canonical(receipt))
    print('RESULT_CONTEXT=' + R1.RESULT_CONTEXT)
    print('CHECKS=' + ' '.join('%s:%s' % (k, 'PASS' if v else 'FAIL') for k, v in receipt.get('CHECKS', {}).items()))
    print('R44_126_RERUN=NO FINAL_BYTES_TOUCHED=NO PRODUCTION_MODIFIED=FALSE FULL_STARTED=NO GATE_VERDICT_ISSUED=NO')
    print('BLOCKER=' + str(receipt['BLOCKER']))
    print('CLASSIFICATION=' + str(receipt.get('CLASSIFICATION')))
    print('EXIT_CODE=' + str(code))
    try:
        ret, rsha, n = R1.write_return(run_dir, evidence, rpath)
        print('RETURN_ZIP=' + str(ret)); print('RETURN_SHA256=' + rsha); print('RETURN_MEMBERS=%d RETURN_READBACK=PASS' % n)
    except BaseException as exc:
        print('RETURN_ZIP_BLOCKED=' + type(exc).__name__ + ':' + str(exc)); code = 2
    print('RESULT_RETURN_TO=' + R1.RESULT_CONTEXT)
    return code


if __name__ == '__main__':
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for k in ('run-dir', 'work-root', 'bundle-dir'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--d-parent', default='D:\\TICKSTORE_QUALIFICATION_SANDBOX')
    ap.add_argument('--ps-version', default='UNKNOWN')
    ap.add_argument('--bootstrap-sha256', default='UNKNOWN')
    raise SystemExit(main(ap.parse_args()))
