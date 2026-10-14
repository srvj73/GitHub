"""G5 technical evidence builder (engineering completeness), never a G5 gate verdict.

Assembles, from the closed native RETURN ZIP and the FINAL package ZIP only:
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


def load_consumer():
    """The exact production consumer bytes; the builder reuses its checks (single source)."""
    raw = (HERE / 'FULL_QUALIFICATION_CONTRACT.py').read_bytes()
    ns = {'__name__': 'tickstore_qualification_library', '__file__': str(HERE / 'FULL_QUALIFICATION_CONTRACT.py')}
    exec(compile(raw, str(HERE / 'FULL_QUALIFICATION_CONTRACT.py'), 'exec'), ns)
    return ns, sha(raw)


def _write_new(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'xb') as f:
        f.write(raw)
    require(path.read_bytes() == raw, 'READBACK:' + str(path))
    return path


def _loose_findings(qual, contract, harness_result, code_manifest, proofs_input):
    """Legacy loose JSON inputs: report every content defect, never accept them as provenance."""
    wanted = contract['required_tests']
    f = ['NATIVE_PROVENANCE_UNBOUND:LOOSE_JSON_INPUTS_NOT_CLOSED_RETURN_ZIP']
    code_raw = Path(code_manifest).read_bytes()
    code_sha = sha(code_raw)
    m = strict_json(code_raw)
    require(m.get('schema') == 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001', 'CODE_MANIFEST_SCHEMA')
    if not m.get('files'):
        f.append('CODE_MANIFEST_EMPTY')
    f.append('CODE_MANIFEST_FILES_NOT_VERIFIED_AGAINST_FINAL_ZIP')
    h = strict_json(Path(harness_result).read_bytes())
    require(h.get('schema') == HARNESS_SCHEMA, 'HARNESS_SCHEMA')
    f += qual['harness_findings'](h, wanted, code_sha)
    p = strict_json(Path(proofs_input).read_bytes())
    require(p.get('schema') == PROOF_SCHEMA, 'PROOF_INPUT_SCHEMA')
    seen = {}
    for name in contract['required_target_proofs']:
        item = (p.get('proofs') or {}).get(name)
        if not isinstance(item, dict):
            f.append('TARGET_PROOF_MISSING:' + name)
            continue
        f.append('TARGET_PROOF_NOT_TYPED_RECEIPT:' + name)
        for e in item.get('evidence', []):
            try:
                digest = sha(read_bound(e['path'], e['sha256']))
            except (OSError, KeyError, TypeError, Blocked) as exc:
                f.append('TARGET_PROOF_EVIDENCE:' + name + ':' + type(exc).__name__)
                continue
            if seen.setdefault(digest, name) != name:
                f.append('TARGET_PROOF_EVIDENCE_REUSED:' + name + ':' + seen[digest])
    unknown = sorted(set(p.get('proofs') or {}) - set(contract['required_target_proofs']))
    if unknown:
        f.append('TARGET_PROOF_UNKNOWN:' + ','.join(unknown))
    tests = h.get('tests') if isinstance(h.get('tests'), list) else []
    statuses = {t.get('id'): t.get('status') for t in tests if isinstance(t, dict)}
    return f, code_sha, statuses, h.get('totals')


def build(*, out_dir, baseline_archive, known_blockers=(), return_zip=None, final_zip=None,
          harness_result=None, code_manifest=None, proofs_input=None):
    """Return the completeness object; write all artifacts with no-clobber into out_dir.

    The only accepted provenance is the closed native RETURN ZIP plus the FINAL package
    ZIP.  Loose JSON inputs (the B2 draft interface) are still analysed so that every
    defect is reported, but they can never yield COMPLETE (B2-G5-01).
    """
    out_dir = Path(out_dir)
    require(not out_dir.exists(), 'OUTPUT_EXISTS')
    contract_raw = (HERE / 'QUALIFICATION_CONTRACT.json').read_bytes()
    contract = strict_json(contract_raw)
    wanted = contract['required_tests']
    qual, validator_sha = load_consumer()
    native_mode = return_zip is not None or final_zip is not None
    require(native_mode != (harness_result is not None or code_manifest is not None or proofs_input is not None),
            'BUILDER_INPUT_MODE')
    out_dir.mkdir(parents=True)
    evidence = []
    proofs = {}
    powerloss_emulated = None
    provenance = None
    if native_mode:
        require(return_zip is not None and final_zip is not None, 'BUILDER_NEEDS_RETURN_AND_FINAL_ZIP')
        packed = {}
        for key, src in (('return_zip', return_zip), ('final_zip', final_zip)):
            raw = Path(src).read_bytes()
            rel = 'INPUTS/' + Path(src).name
            dst = _write_new(out_dir / rel, raw)
            packed[key] = {'path': str(dst.absolute()), 'pack_relative': rel, 'sha256': sha(raw), 'bytes': len(raw),
                           'source_path': str(Path(src).absolute())}
            evidence.append({'label': key, 'path': rel, 'sha256': sha(raw), 'bytes': len(raw)})
        final_raw = (out_dir / packed['final_zip']['pack_relative']).read_bytes()
        rfindings, rfiles = qual['return_zip_findings']((out_dir / packed['return_zip']['pack_relative']).read_bytes())
        code_raw = qual['_zip_members'](final_raw, 'FINAL')[1].get('implementation_v001/RUNTIME_CODE_MANIFEST.json', b'')
        code_sha = sha(code_raw)
        _, code_index = qual['final_zip_findings'](final_raw, code_sha)
        members = qual['MEMBERS']

        def member_json(key):
            try:
                obj = strict_json(rfiles[members[key]])
                return obj if isinstance(obj, dict) else {}
            except (KeyError, ValueError, Blocked):
                return {}
        h = member_json('harness_result')
        q = member_json('qual_receipt')
        b1 = member_json('b1_result')
        tests = h.get('tests') if isinstance(h.get('tests'), list) else []
        statuses = {t.get('id'): t.get('status') for t in tests if isinstance(t, dict)}
        totals = h.get('totals')
        provenance = {'schema': qual['PROVENANCE_SCHEMA'],
                      'return_zip': {k: packed['return_zip'][k] for k in ('path', 'pack_relative', 'sha256', 'bytes')},
                      'final_zip': {k: packed['final_zip'][k] for k in ('path', 'pack_relative', 'sha256', 'bytes')},
                      'code_manifest_files': len(code_index) if code_index else 0,
                      'run_id': q.get('RUN_ID'), 'derived_tests': b1.get('derived'),
                      'members': dict(members)}
        for key in ('qual_receipt', 'harness_result', 'tests_log', 'b1_result'):
            provenance[key + '_sha256'] = sha(rfiles[members[key]]) if members[key] in rfiles else None
        seen = {}
        for name in contract['required_target_proofs']:
            member = qual['PROOF_PREFIX'] + name + '/PROOF_RECEIPT.json'
            body = rfiles.get(member)
            if body is None:
                proofs[name] = {'status': 'PENDING_NO_TYPED_RECEIPT', 'evidence': [], 'source': 'NONE'}
                continue
            dst = _write_new(out_dir / 'PROOF_RECEIPTS' / (name + '.json'), body)
            try:
                receipt = strict_json(body)
            except (ValueError, Blocked):
                receipt = {}
            receipt = receipt if isinstance(receipt, dict) else {}
            digest = sha(body)
            item = {'path': str(dst.absolute()), 'pack_relative': 'PROOF_RECEIPTS/' + name + '.json',
                    'sha256': digest, 'kind': receipt.get('kind'), 'return_zip_member': member}
            seen.setdefault(digest, name)
            proofs[name] = {'status': str(receipt.get('status')), 'evidence': [item],
                            'source': '%s::%s' % ((receipt.get('runner') or {}).get('path'),
                                                  (receipt.get('runner') or {}).get('function'))}
        emu = rfiles.get(qual['PROOF_PREFIX'] + 'POWERLOSS_EMULATED/PROOF_RECEIPT.json')
        if emu is not None:
            try:
                er = strict_json(emu)
            except (ValueError, Blocked):
                er = {}
            powerloss_emulated = {'member': qual['PROOF_PREFIX'] + 'POWERLOSS_EMULATED/PROOF_RECEIPT.json',
                                  'sha256': sha(emu), 'kind': er.get('kind'), 'status': er.get('status'),
                                  'counts_as': 'NOT_CHECKPOINT_POWERLOSS_RECOVERY'}
        loose = []
    else:
        loose, code_sha, statuses, totals = _loose_findings(qual, contract, harness_result, code_manifest,
                                                            proofs_input)
        for name in contract['required_target_proofs']:
            proofs[name] = {'status': 'PENDING_NO_TYPED_RECEIPT', 'evidence': [], 'source': 'LOOSE_INPUT_REJECTED'}
        rfindings = []
    non_pass = sorted(i for i in wanted if statuses.get(i) != 'PASS')
    base_raw = Path(baseline_archive).read_bytes()
    evidence.append({'label': 'baseline_archive', 'path': str(Path(baseline_archive).absolute()),
                     'sha256': sha(base_raw), 'bytes': len(base_raw)})
    delta = {
        'schema': DELTA_SCHEMA, 'platform': 'NOT_PROVEN_WINDOWS', 'native_windows': False,
        'code_manifest_sha256': code_sha, 'tested_code_equals_packaged_code': 'FAIL',
        'production_execution': False, 'success': False,
        'tests': [{'id': i, 'status': statuses.get(i, 'NOT_RUN')} for i in wanted],
        'target_proofs': proofs, 'harness_totals': totals,
    }
    if provenance is not None:
        delta['native_provenance'] = provenance
        findings = qual['physical_findings'](delta, contract, code_sha, out_dir)
    else:
        findings = loose
    native_markers = ('HARNESS_NOT_NATIVE', 'HARNESS_PLATFORM', 'HARNESS_PYTHON', 'QUAL_PRECHECK', 'QUAL_RECEIPT',
                      'TESTS_LOG', 'RETURN_', 'PROVENANCE_', 'NATIVE_PROVENANCE')
    native_proven = provenance is not None and not any(x.startswith(native_markers) for x in findings)
    bytes_markers = ('HARNESS_CODE_', 'FINAL_', 'QUAL_RECEIPT_FINAL', 'QUAL_RECEIPT_CODE', 'QUAL_RECEIPT_TESTED',
                     'PROVENANCE_', 'CODE_MANIFEST', 'NATIVE_PROVENANCE')
    if native_proven:
        delta.update(platform='WINDOWS_NTFS_PS51', native_windows=True)
    if provenance is not None and not any(x.startswith(bytes_markers) for x in findings):
        delta['tested_code_equals_packaged_code'] = 'PASS'
    blockers = list(findings)
    if sha(base_raw) != contract['baseline']['archive_sha256']:
        blockers.append('BASELINE_ARCHIVE_SHA256')
    blockers += [str(b) for b in (known_blockers or [])]
    delta['success'] = not blockers
    delta_raw = canonical(delta)
    delta_path = _write_new(out_dir / 'DELTA_QUALIFICATION.json', delta_raw)
    harness_clean = not any(x.startswith(('HARNESS_', 'NON_PASS_IDS', 'TESTS_LOG')) for x in findings)
    completeness = {
        'schema': COMPLETENESS_SCHEMA,
        'status': 'COMPLETE' if not blockers else 'INCOMPLETE',
        'known_blockers': sorted(set(blockers)),
        'integration_implemented': True,
        'windows_qualification': 'PASS' if (native_proven and harness_clean and not non_pass) else 'NOT_PASS',
        'code_manifest_sha256': code_sha,
        'baseline': contract['baseline'],
        'baseline_archive_evidence': {'path': str(Path(baseline_archive).absolute()), 'sha256': sha(base_raw)},
        'delta_qualification': delta,
        'delta_qualification_evidence': {'path': str(delta_path.absolute()), 'sha256': sha(delta_raw)},
        'delta_test_totals': {'run': len(wanted) - len(non_pass) if non_pass else len(wanted),
                              'failures': sum(1 for i in wanted if statuses.get(i) == 'FAIL'),
                              'errors': sum(1 for i in wanted if statuses.get(i) == 'ERROR'),
                              'skips': sum(1 for i in wanted if statuses.get(i) == 'SKIP')},
        'baseline_results_counted_as_delta': False,
        'qualification_contract_sha256': sha(contract_raw),
        'provenance_mode': 'CLOSED_NATIVE_RETURN_ZIP' if provenance is not None else 'LOOSE_JSON_REJECTED',
        'powerloss_emulated': powerloss_emulated,
        'gate_verdict_issued': False,
        'created_unix_ns': time.time_ns(),
    }
    # Self-check with the exact production consumer; any rejection is a blocker.
    try:
        qual['validate'](completeness, contract, delta, code_sha, require)
        consumer = 'ACCEPTS'
    except Blocked as exc:
        consumer = 'REJECTS:' + str(exc)[:600]
        if completeness['status'] == 'COMPLETE':
            completeness['status'] = 'INCOMPLETE'
            completeness['known_blockers'] = sorted(set(completeness['known_blockers']) | {'CONSUMER_' + str(exc)})
    completeness['consumer_self_check'] = consumer
    completeness['consumer_validator_sha256'] = validator_sha
    comp_raw = canonical(completeness)
    _write_new(out_dir / 'ENGINEERING_COMPLETENESS.json', comp_raw)
    pack = {'schema': PACK_SCHEMA, 'code_manifest_sha256': code_sha, 'inputs': evidence,
            'outputs': [{'path': 'DELTA_QUALIFICATION.json', 'sha256': sha(delta_raw)},
                        {'path': 'ENGINEERING_COMPLETENESS.json', 'sha256': sha(comp_raw)}],
            'completeness_status': completeness['status'], 'known_blockers': completeness['known_blockers'],
            'consumer_self_check': consumer, 'powerloss_emulated': powerloss_emulated, 'gate_verdict_issued': False}
    pack_raw = canonical(pack)
    _write_new(out_dir / 'G5_EVIDENCE_PACK.json', pack_raw)
    # Draft only: the release-chain consumer requires status PASS, which this tool never writes.
    draft = {'schema': 'TICKSTORE_STAGE_RECEIPT_V001', 'stage': 'G5', 'status': 'PENDING_ORIGIN_DECISION',
             'environment': 'WINDOWS_PRODUCTION', 'code_manifest_sha256': code_sha,
             'previous_receipt_sha256': None, 'blockers': completeness['known_blockers'],
             'checks': {'features_implemented': None, 'blockers_closed': not completeness['known_blockers'],
                        'tested_equals_packaged': delta['tested_code_equals_packaged_code'] == 'PASS',
                        'adversarial_completeness': None, 'byte_freeze': None},
             'evidence': [{'path': 'G5_EVIDENCE_PACK.json', 'sha256': sha(pack_raw)}],
             'decision_owner': 'CHATGPT_ORIGIN', 'gate_verdict_issued': False}
    _write_new(out_dir / 'G5_STAGE_RECEIPT_DRAFT.json', canonical(draft))
    return completeness


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for k in ('return-zip', 'final-zip', 'baseline-archive', 'out-dir'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--known-blockers', default='')
    a = ap.parse_args(argv)
    try:
        blockers = json.loads(Path(a.known_blockers).read_bytes()) if a.known_blockers else []
        c = build(return_zip=a.return_zip, final_zip=a.final_zip, baseline_archive=a.baseline_archive,
                  known_blockers=blockers, out_dir=a.out_dir)
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
