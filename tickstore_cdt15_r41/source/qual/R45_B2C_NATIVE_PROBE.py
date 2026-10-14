"""R45 B2C native probe: current-policy capture verification through the sealed D4 reader.

Runs from the extracted FINAL package (implementation_v001/qual).  Everything happens in a
private scratch directory under %TMP% (the qualification work root); no production path,
no policy library path and no origin record is touched or produced.

The probe deliberately carries NO positive reconciliation record: the origin has not issued
POLICY_RECONCILIATION_FOR_R45, and none is fabricated here.  It proves instead that
  * POLICY_CAPTURE_BINDING is loaded only through the sealed FIRST_ADMISSION_BINDING digest;
  * the R40 capture (non-authoritative snapshot) passes every structural check and is then
    stopped exactly at the reconciliation step (record NOT_ISSUED);
  * the reconciliation digest is mandatory and supplied separately (format, mismatch);
  * historical V38, an extra file in the capture and a tampered MASTER are refused;
  * on native Windows the sealed reader holds the captured MASTER/HEAD against write,
    delete and rename while the verification runs (released afterwards: positive control);
  * the D4 command cannot be formed without a current origin reconciliation.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

IMPL = Path(__file__).resolve().parents[1]
CONTROL = IMPL / 'candidate/control'
FIXTURES = IMPL / 'tests/fixtures'
sys.path.insert(0, str(CONTROL))
import D4_FIRST_ADMISSION_PREP as PREP  # noqa: E402
import FULL_RUNNER  # noqa: E402

NATIVE = os.name == 'nt'
results = {}


def record(name, ok, detail):
    results[name] = {'status': 'PASS' if ok else 'FAIL', 'detail': str(detail)[:400]}
    print('R45_B2C_PROBE %s=%s %s' % (name, results[name]['status'], results[name]['detail']), flush=True)


def blocked(fn):
    try:
        fn()
    except Exception as e:  # PolicyBlocked, PREP.Blocked or OS refusal: all fail closed
        return type(e).__name__ + ':' + str(e)
    return None


def capture(base, src, name):
    d = base / name
    shutil.copytree(FIXTURES / src, d)
    return d


def main():
    work = Path(tempfile.mkdtemp(prefix='R45_B2C_', dir=os.environ.get('TMP') or None))
    manifest = json.loads((CONTROL / 'FIRST_ADMISSION_BINDING.json').read_bytes())
    not_issued = work / 'POLICY_RECONCILIATION_FOR_R45.NOT_ISSUED.json'
    not_issued.write_bytes(json.dumps({'schema': 'TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001', 'status': 'NOT_ISSUED',
                                       'issuer': 'NONE_ENGINEERING_PLACEHOLDER'}, sort_keys=True).encode('utf-8'))
    ni_sha = PREP.sha(not_issued.read_bytes())

    with PREP.Reads() as reads:
        record('reader_mode', (reads.store is not None) == NATIVE, 'WIN32_SEALED_HANDLES' if reads.store is not None
               else 'POSIX_OPTIMISTIC_NOT_NATIVE_EVIDENCE')
        B = PREP.load_policy_binding(reads, manifest)
        record('binding_module_sealed', PREP.sha((CONTROL / 'POLICY_CAPTURE_BINDING.py').read_bytes())
               == manifest['policy_capture_binding_sha256'], manifest['policy_capture_binding_sha256'])
        r40 = capture(work, 'R40_CAPTURE_NON_AUTHORITATIVE', 'r40')
        why = blocked(lambda: B.verify_capture(reads.read, r40, not_issued, ni_sha))
        record('r40_structure_pass_then_reconciliation_not_issued_blocks',
               why is not None and 'POLICY_RECONCILIATION_SCHEMA' in why, why)
        if NATIVE:
            master = r40 / B.MASTER
            denials = {}
            for op, fn in (('write', lambda: open(master, 'ab').close()),
                           ('delete', lambda: os.remove(master)),
                           ('rename', lambda: os.rename(master, r40 / 'renamed.md'))):
                denials[op] = blocked(fn)
            record('held_capture_denies_write_delete_rename', all(denials.values()) and master.is_file(), denials)
            reads.revalidate()
            record('held_capture_revalidates_unchanged', True, 'INPUT_REVALIDATED')

    if NATIVE:
        # Positive control: once the sealed reader is closed the same rename succeeds.
        os.rename(r40 / B.MASTER, r40 / 'renamed.md')
        record('release_positive_control_rename_after_close', (r40 / 'renamed.md').is_file(), 'RENAMED_AFTER_RELEASE')

    with PREP.Reads() as reads:
        r40b = capture(work, 'R40_CAPTURE_NON_AUTHORITATIVE', 'r40b')
        why = blocked(lambda: B.verify_capture(reads.read, r40b, not_issued, ''))
        record('reconciliation_sha_must_be_supplied', why is not None and 'POLICY_RECONCILIATION_SHA_FORMAT' in why, why)
        why = blocked(lambda: B.verify_capture(reads.read, r40b, not_issued, '0' * 64))
        record('reconciliation_sha_mismatch_blocks', why is not None and 'SHA_MISMATCH' in why, why)
        v38 = capture(work, 'V38_CAPTURE_HISTORICAL', 'v38')
        why = blocked(lambda: B.verify_capture(reads.read, v38, not_issued, ni_sha))
        record('historical_v38_refused', why is not None and 'POLICY_HISTORICAL_NOT_CURRENT:V38' in why, why)
        extra = capture(work, 'R40_CAPTURE_NON_AUTHORITATIVE', 'extra')
        (extra / 'POLITICA_CANONICA_HEAD (1).json').write_bytes((extra / B.HEAD).read_bytes())
        why = blocked(lambda: B.verify_capture(reads.read, extra, not_issued, ni_sha))
        record('extra_file_cardinality_refused', why is not None and 'POLICY_CARDINALITY_1_PLUS_1' in why, why)
        tamper = capture(work, 'R40_CAPTURE_NON_AUTHORITATIVE', 'tamper')
        with open(tamper / B.MASTER, 'ab') as f:
            f.write(b'\n')
        why = blocked(lambda: B.verify_capture(reads.read, tamper, not_issued, ni_sha))
        record('tampered_master_refused', why is not None and 'POLICY_HEAD_MASTER' in why, why)

    params = dict.fromkeys(FULL_RUNNER.D4_PARAMETERS, 'X')
    for label, kw in (('absent', {}), ('no_sha', {'policy_reconciliation': str(not_issued)}),
                      ('bad_sha', {'policy_reconciliation': str(not_issued), 'policy_reconciliation_sha256': 'abc'})):
        why = blocked(lambda: FULL_RUNNER.d4_command({'d4_parameters': params}, IMPL / 'candidate', **kw))
        record('d4_command_requires_current_reconciliation_' + label,
               why is not None and 'D4_CURRENT_POLICY_RECONCILIATION_REQUIRED' in why, why)

    shutil.rmtree(work, ignore_errors=True)
    ok = all(v['status'] == 'PASS' for v in results.values())
    print('R45_B2C_NATIVE_PROBE=%s MODE=%s CHECKS=%d' % ('PASS' if ok else 'FAIL', 'NATIVE_WINDOWS' if NATIVE
          else 'PORTABLE', len(results)), flush=True)
    print('POLICY_RECONCILIATION_FOR_R45=NOT_ISSUED', flush=True)
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
