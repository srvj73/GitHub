"""G5 technical evidence builder (engineering completeness), never a G5 gate verdict.

Assembles, from hash-bound native evidence only:
  * DELTA_QUALIFICATION.json      (TICKSTORE_CDT15_DELTA_QUALIFICATION_V001)
  * ENGINEERING_COMPLETENESS.json (TICKSTORE_ENGINEERING_COMPLETENESS_V002)
  * G5_EVIDENCE_PACK.json         (closed list of every input with SHA-256)
  * G5_STAGE_RECEIPT_DRAFT.json   (status PENDING_ORIGIN_DECISION; never PASS)

The formats are those consumed by D4_FIRST_ADMISSION_TRANSACTION.validate_gates and
FULL_QUALIFICATION_CONTRACT.validate.  The produced completeness is re-validated by
that exact consumer code; status COMPLETE is written only when every mechanical
condition holds and no blocker is known.  Gate decisions (G5, B06, B07) belong to the
ChatGPT origin and the independent auditor, not to this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPLETENESS_SCHEMA = 'TICKSTORE_ENGINEERING_COMPLETENESS_V002'
DELTA_SCHEMA = 'TICKSTORE_CDT15_DELTA_QUALIFICATION_V001'
PACK_SCHEMA = 'TICKSTORE_G5_EVIDENCE_PACK_V001'
PROOF_SCHEMA = 'TICKSTORE_G5_TARGET_PROOF_INPUT_V001'
HARNESS_SCHEMA = 'TICKSTORE_CDT15_EXECUTED_DELTA_V001'
HEX64 = re.compile(r'[0-9A-F]{64}\Z')


class Blocked(RuntimeError):
    pass


def require(cond, why):
    if not cond:
        raise Blocked(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def strict_json(raw: bytes):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'JSON_DUPLICATE_KEY:' + str(k))
            out[k] = v
        return out
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def read_bound(path, expected=None):
    raw = Path(path).read_bytes()
    if expected is not None:
        require(sha(raw) == expected, 'EVIDENCE_SHA256:' + str(path))
    return raw


def load_validator():
    raw = (HERE / 'FULL_QUALIFICATION_CONTRACT.py').read_bytes()
    ns = {'__name__': 'tickstore_qualification_library', '__file__': str(HERE / 'FULL_QUALIFICATION_CONTRACT.py')}
    exec(compile(raw, str(HERE / 'FULL_QUALIFICATION_CONTRACT.py'), 'exec'), ns)
    return ns['validate'], sha(raw)


def build(*, harness_result, code_manifest, baseline_archive, proofs_input, known_blockers, out_dir,
          windows_native=True):
    """Return the completeness object; write all artifacts with no-clobber into out_dir."""
    out_dir = Path(out_dir)
    require(not out_dir.exists(), 'OUTPUT_EXISTS')
    contract_raw = (HERE / 'QUALIFICATION_CONTRACT.json').read_bytes()
    contract = strict_json(contract_raw)
    wanted = contract['required_tests']
    code_raw = read_bound(code_manifest)
    code_sha = sha(code_raw)
    require(strict_json(code_raw).get('schema') == 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001', 'CODE_MANIFEST_SCHEMA')
    blockers = []
    evidence = []

    def bind(label, path):
        raw = read_bound(path)
        evidence.append({'label': label, 'path': str(Path(path).absolute()), 'sha256': sha(raw), 'bytes': len(raw)})
        return raw

    # 1. Delta qualification: exactly the native harness result on these code bytes.
    h = strict_json(bind('harness_result', harness_result))
    require(h.get('schema') == HARNESS_SCHEMA, 'HARNESS_SCHEMA')
    statuses = {t['id']: t['status'] for t in h.get('tests', [])}
    if not (h.get('native_windows') is True and h.get('selection') == 'NATIVE'):
        blockers.append('HARNESS_NOT_NATIVE_WINDOWS_SELECTION')
    if h.get('code_manifest_sha256') != code_sha:
        blockers.append('HARNESS_CODE_MANIFEST_MISMATCH')
    if h.get('tested_code_unchanged') is not True:
        blockers.append('HARNESS_CODE_CHANGED_DURING_RUN')
    if set(statuses) != set(wanted) or len(statuses) != len(wanted):
        blockers.append('HARNESS_ID_SET_NOT_CONTRACT')
    non_pass = sorted(i for i in wanted if statuses.get(i) != 'PASS')
    if non_pass:
        blockers.append('NON_PASS_IDS:' + ','.join(non_pass))
    totals = h.get('totals') or {}
    # 2. Target proofs: every required proof must carry hash-verified native evidence.
    p = strict_json(bind('target_proofs_input', proofs_input))
    require(p.get('schema') == PROOF_SCHEMA, 'PROOF_INPUT_SCHEMA')
    proofs = {}
    for name in contract['required_target_proofs']:
        item = (p.get('proofs') or {}).get(name)
        if not isinstance(item, dict):
            blockers.append('TARGET_PROOF_MISSING:' + name)
            continue
        ev = []
        for e in item.get('evidence', []):
            try:
                raw = read_bound(e['path'], e['sha256'])
                ev.append({'path': str(Path(e['path']).absolute()), 'sha256': sha(raw)})
            except (OSError, KeyError, Blocked) as exc:
                blockers.append('TARGET_PROOF_EVIDENCE:' + name + ':' + type(exc).__name__)
        status = item.get('status')
        if status != 'PASS' or not ev:
            blockers.append('TARGET_PROOF_NOT_PASS:' + name + ':' + str(status))
        proofs[name] = {'status': 'PASS' if status == 'PASS' and ev else str(status), 'evidence': ev,
                        'source': item.get('source', '')}
    unknown = sorted(set(p.get('proofs') or {}) - set(contract['required_target_proofs']))
    if unknown:
        blockers.append('TARGET_PROOF_UNKNOWN:' + ','.join(unknown))
    # 3. Baseline: historical bytes only, never counted as delta.
    base_raw = bind('baseline_archive', baseline_archive)
    if sha(base_raw) != contract['baseline']['archive_sha256']:
        blockers.append('BASELINE_ARCHIVE_SHA256')
    blockers += [str(b) for b in (known_blockers or [])]

    delta = {
        'schema': DELTA_SCHEMA, 'platform': 'WINDOWS_NTFS_PS51' if windows_native else 'NOT_WINDOWS',
        'native_windows': bool(windows_native and h.get('native_windows') is True),
        'code_manifest_sha256': code_sha,
        'tested_code_equals_packaged_code': 'PASS' if (h.get('code_manifest_sha256') == code_sha
                                                       and h.get('tested_code_unchanged') is True) else 'FAIL',
        'production_execution': False,
        'success': not blockers,
        'tests': [{'id': i, 'status': statuses.get(i, 'NOT_RUN')} for i in wanted],
        'target_proofs': proofs,
        'harness_totals': totals,
    }
    out_dir.mkdir(parents=True)
    delta_raw = canonical(delta)
    delta_path = out_dir / 'DELTA_QUALIFICATION.json'
    with open(delta_path, 'xb') as f:
        f.write(delta_raw)
    completeness = {
        'schema': COMPLETENESS_SCHEMA,
        'status': 'COMPLETE' if not blockers else 'INCOMPLETE',
        'known_blockers': sorted(set(blockers)),
        'integration_implemented': True,
        'windows_qualification': 'PASS' if (delta['native_windows'] and not non_pass
                                            and 'HARNESS_NOT_NATIVE_WINDOWS_SELECTION' not in blockers) else 'NOT_PASS',
        'code_manifest_sha256': code_sha,
        'baseline': contract['baseline'],
        'baseline_archive_evidence': {'path': str(Path(baseline_archive).absolute()), 'sha256': sha(base_raw)},
        'delta_qualification': delta,
        'delta_qualification_evidence': {'path': str(delta_path.absolute()), 'sha256': sha(delta_raw)},
        'delta_test_totals': {'run': len(wanted) if not non_pass else len(wanted) - len(non_pass),
                              'failures': sum(1 for i in wanted if statuses.get(i) == 'FAIL'),
                              'errors': sum(1 for i in wanted if statuses.get(i) == 'ERROR'),
                              'skips': sum(1 for i in wanted if statuses.get(i) == 'SKIP')},
        'baseline_results_counted_as_delta': False,
        'qualification_contract_sha256': sha(contract_raw),
        'gate_verdict_issued': False,
        'created_unix_ns': time.time_ns(),
    }
    if not non_pass:
        completeness['delta_test_totals'] = {'run': len(wanted), 'failures': 0, 'errors': 0, 'skips': 0}
    # 4. Self-check with the exact production consumer; any rejection is a blocker.
    validate, validator_sha = load_validator()
    try:
        validate(completeness, contract, delta, code_sha, require)
        consumer = 'ACCEPTS'
    except Blocked as exc:
        consumer = 'REJECTS:' + str(exc)
        if completeness['status'] == 'COMPLETE':
            completeness['status'] = 'INCOMPLETE'
            completeness['known_blockers'] = sorted(set(completeness['known_blockers']) | {'CONSUMER_' + str(exc)})
    completeness['consumer_self_check'] = consumer
    completeness['consumer_validator_sha256'] = validator_sha
    comp_raw = canonical(completeness)
    with open(out_dir / 'ENGINEERING_COMPLETENESS.json', 'xb') as f:
        f.write(comp_raw)
    pack = {'schema': PACK_SCHEMA, 'code_manifest_sha256': code_sha, 'inputs': evidence,
            'outputs': [{'path': 'DELTA_QUALIFICATION.json', 'sha256': sha(delta_raw)},
                        {'path': 'ENGINEERING_COMPLETENESS.json', 'sha256': sha(comp_raw)}],
            'completeness_status': completeness['status'], 'known_blockers': completeness['known_blockers'],
            'consumer_self_check': consumer, 'gate_verdict_issued': False}
    pack_raw = canonical(pack)
    with open(out_dir / 'G5_EVIDENCE_PACK.json', 'xb') as f:
        f.write(pack_raw)
    # Draft only: the release-chain consumer requires status PASS, which this tool never writes.
    draft = {'schema': 'TICKSTORE_STAGE_RECEIPT_V001', 'stage': 'G5', 'status': 'PENDING_ORIGIN_DECISION',
             'environment': 'WINDOWS_PRODUCTION', 'code_manifest_sha256': code_sha,
             'previous_receipt_sha256': None, 'blockers': completeness['known_blockers'],
             'checks': {'features_implemented': None, 'blockers_closed': not completeness['known_blockers'],
                        'tested_equals_packaged': delta['tested_code_equals_packaged_code'] == 'PASS',
                        'adversarial_completeness': None, 'byte_freeze': None},
             'evidence': [{'path': 'G5_EVIDENCE_PACK.json', 'sha256': sha(pack_raw)}],
             'decision_owner': 'CHATGPT_ORIGIN', 'gate_verdict_issued': False}
    with open(out_dir / 'G5_STAGE_RECEIPT_DRAFT.json', 'xb') as f:
        f.write(canonical(draft))
    return completeness


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for k in ('harness-result', 'code-manifest', 'baseline-archive', 'proofs-input', 'out-dir'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--known-blockers', default='')
    a = ap.parse_args(argv)
    try:
        blockers = json.loads(Path(a.known_blockers).read_bytes()) if a.known_blockers else []
        c = build(harness_result=a.harness_result, code_manifest=a.code_manifest, baseline_archive=a.baseline_archive,
                  proofs_input=a.proofs_input, known_blockers=blockers, out_dir=a.out_dir)
        print('G5_EVIDENCE_COMPLETENESS=' + c['status'])
        print('G5_CONSUMER_SELF_CHECK=' + c['consumer_self_check'])
        for b in c['known_blockers']:
            print('G5_BLOCKER=' + b)
        print('G5_GATE_VERDICT_ISSUED=NO')
        return 0 if c['status'] == 'COMPLETE' else 3
    except (Blocked, OSError, KeyError, ValueError) as exc:
        print('G5_EVIDENCE_BUILDER_BLOCKED=' + type(exc).__name__ + ':' + str(exc))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
