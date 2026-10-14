"""B07 technical receipt producer (SOURCE_ONLY).  Never a gate verdict; never runs before B06 PASS.

Builds TICKSTORE_B07_TECHNICAL_RECEIPT_V001 (the receipt consumed by
D4_FIRST_ADMISSION_TRANSACTION.validate_gates) exclusively from:
  * the closed native B07 RETURN ZIP (same physical checks as the hardened G5 consumer:
    RETURN_MANIFEST, QUAL_RECEIPT native/elevated/PS5.1/NTFS bound to the FINAL ZIP);
  * the FINAL ZIP and its runtime code manifest;
  * the independent B06 verdict file, whose SHA-256 is supplied separately and which must say
    VERDICT=PASS, INDEPENDENT_REVIEW=YES and 0 critical/major findings;
  * the verified current policy capture (R44-B2C).
Each of the 10 B07 checks needs its own typed check receipt (EVIDENCE/B07/<CHECK>/CHECK_RECEIPT.json)
from the packaged runner function, with exactly its required test IDs (each once, PASS) and
required native probes (PASS) and non-empty artifacts.  Anything missing -> status NOT_PASS.
The B07 *stage* receipt (FULL_RELEASE_CHAIN) is NOT produced here: only the origin decision,
bound by ORIGIN_DECISION_BINDER (R44-B2D), can materialize it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECEIPT_SCHEMA = 'TICKSTORE_B07_TECHNICAL_RECEIPT_V001'
CHECK_SCHEMA = 'TICKSTORE_B07_CHECK_RECEIPT_V001'
RUNNER = 'b07/B07_CHECK_RUNNERS.py'
CHECK_PREFIX = 'EVIDENCE/B07/'
TX = 'test_first_admission_transaction.TransactionTests.'
SG = 'tests_delta.StageGuardTests.'
CHECKS = {
    'policyroot_physical_readback': {
        'tests': [], 'probes': ['capture_verified_with_native_protected_reads', 'origin_reconciliation_current',
                                'cardinality_1_plus_1_frozen']},
    'policyroot_mutation_denial': {
        'tests': [], 'probes': ['write_open_denied_while_admitted', 'delete_denied_while_admitted',
                                'rename_denied_while_admitted', 'extra_file_in_policy_root_blocks']},
    'reparse_and_ancestor_controls': {
        'tests': [TX + 'test_reparse_resume_root_rejected',
                  'tests_native_delta.NativeDelta.test_heartbeat_reparse_destination_cannot_modify_target'],
        'probes': ['sandbox_admission_negative_probes']},
    'state_cas_and_continuity': {
        'tests': [SG + n for n in ('test_state_constructor_does_not_rewrite', 'test_missing_state_never_recreated',
                                   'test_changed_config_never_consumed', 'test_config_negative_control_unchanged_buffer',
                                   'test_cannot_skip_to_full', 'test_single_stage_commit_and_native_readback',
                                   'test_d4_default_rejects_post_d4')], 'probes': []},
    'checkpoint_failure_controls': {
        'tests': ['tests_delta.CheckpointFailureTests.test_failed_checkpoint_publish_can_retry_preserving_previous'],
        'probes': []},
    'concurrent_receipt_controls': {
        'tests': [SG + 'test_no_receipt_clobber_under_race',
                  'test_official_writer_effectful.EffectfulWriter.test_22_two_simultaneous_writer_processes_one_winner'],
        'probes': []},
    'g_ca_native_locator': {
        'tests': [TX + 'test_native_locator_negative_blocks_before_creating_files',
                  TX + 'test_locator_wrong_descriptor_and_changed_generation_block'],
        'probes': ['adapter_tests_all_pass']},
    'predecessor_process_locks_lease': {
        'tests': ['test_native_process_control_r41.NativeProcessControl.test_03_full_lease_is_exclusive_and_released',
                  'tests_delta.NativeJobTests.test_admitted_child_executes',
                  'tests_delta.NativeJobTests.test_job_close_contains_survivor'],
        'probes': ['recovery_process_census_lease_absent']},
    'wrapper_safe_stop_exit_propagation': {
        'tests': [], 'probes': ['wrapper_blocks_without_chain_exit_2', 'wrapper_safe_stop_requires_authority_sha',
                                'nested_powershell_exit_code_propagated', 'wrapper_dry_entry_no_d4']},
    'first_admission_transaction': {'tests': ['ALL:' + TX.rstrip('.')], 'probes': []},
}
B07_CHECKS = tuple(CHECKS)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def _canonical(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def load_consumer():
    raw = (HERE / 'FULL_QUALIFICATION_CONTRACT.py').read_bytes()
    ns = {'__name__': 'b07_uses_g5_consumer', '__file__': str(HERE / 'FULL_QUALIFICATION_CONTRACT.py')}
    exec(compile(raw, str(HERE / 'FULL_QUALIFICATION_CONTRACT.py'), 'exec'), ns)
    return ns


def parse_verdict(raw):
    out = {}
    for line in raw.decode('utf-8').splitlines():
        line = line.strip()
        if '=' in line:
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def verdict_findings(raw, supplied_sha):
    f = []
    if _sha(raw) != supplied_sha:
        return ['B06_VERDICT_SHA256_SUPPLIED_SEPARATELY']
    v = parse_verdict(raw)
    for k, want in (('VERDICT', 'PASS'), ('INDEPENDENT_REVIEW', 'YES'), ('CRITICAL_FINDINGS', '0'), ('MAJOR_FINDINGS', '0'),
                    ('TESTED_CODE_EQUALS_PACKAGED_CODE', 'YES')):
        if v.get(k) != want:
            f.append('B06_VERDICT_FIELD:' + k)
    return f


def check_findings(name, receipt, member, rfiles, code_index, final_sha, code_sha, run_id, all_tx_ids=None):
    spec = CHECKS[name]
    f = []
    if not isinstance(receipt, dict):
        return [name + ':RECEIPT_NOT_OBJECT']
    if receipt.get('schema') != CHECK_SCHEMA or receipt.get('check') != name or member != CHECK_PREFIX + name + '/CHECK_RECEIPT.json':
        f.append(name + ':RECEIPT_KIND')
    if receipt.get('status') != 'PASS' or receipt.get('native_windows') is not True:
        f.append(name + ':RECEIPT_STATUS')
    if (receipt.get('code_manifest_sha256'), receipt.get('final_zip_sha256'), receipt.get('run_id')) != (code_sha, final_sha, run_id):
        f.append(name + ':RECEIPT_RUN_BINDING')
    runner = receipt.get('runner') if isinstance(receipt.get('runner'), dict) else {}
    if runner.get('path') != RUNNER or code_index is None or code_index.get(RUNNER) != runner.get('sha256'):
        f.append(name + ':RECEIPT_RUNNER_NOT_PACKAGED')
    tests = receipt.get('tests') if isinstance(receipt.get('tests'), list) else []
    ids = [t.get('id') for t in tests if isinstance(t, dict)]
    want = []
    for t in spec['tests']:
        want += sorted(all_tx_ids or []) if t.startswith('ALL:') else [t]
    t_ok = (sorted(ids) == sorted(want) and len(set(ids)) == len(ids)
            and all(t.get('status') == 'PASS' for t in tests))
    if not t_ok or (spec['tests'] and not want):
        f.append(name + ':RECEIPT_TESTS')
    probes = receipt.get('probes') if isinstance(receipt.get('probes'), dict) else {}
    if set(probes) != set(spec['probes']) or not all(v == 'PASS' for v in probes.values()):
        f.append(name + ':RECEIPT_PROBES')
    arts = receipt.get('artifacts')
    if not isinstance(arts, list) or not arts:
        f.append(name + ':RECEIPT_NO_ARTIFACTS')
    else:
        for a in arts:
            m = a.get('member') if isinstance(a, dict) else None
            body = rfiles.get(m) if isinstance(m, str) else None
            if not isinstance(m, str) or not m.startswith(CHECK_PREFIX + name + '/') or not body or _sha(body) != a.get('sha256'):
                f.append(name + ':RECEIPT_ARTIFACT:' + str(m))
    return f


def build(*, return_zip, final_zip, b06_verdict, b06_verdict_sha256, policy_capture, out_path, transaction_test_ids):
    """Write the B07 technical receipt (no-clobber); status PASS only when every finding list is empty."""
    q = load_consumer()
    rraw, fraw, vraw = Path(return_zip).read_bytes(), Path(final_zip).read_bytes(), Path(b06_verdict).read_bytes()
    final_sha = _sha(fraw)
    code_raw = q['_zip_members'](fraw, 'FINAL')[1].get('implementation_v001/RUNTIME_CODE_MANIFEST.json', b'')
    code_sha = _sha(code_raw)
    findings, code_index = q['final_zip_findings'](fraw, code_sha)
    rf, rfiles = _return_generic(q, rraw)
    findings += rf
    try:
        qr = json.loads(rfiles.get('QUAL_RECEIPT.json', b'{}'))
    except ValueError:
        qr = {}
    findings += q['qual_receipt_findings'](qr, final_sha, code_sha)
    findings += verdict_findings(vraw, b06_verdict_sha256)
    if not (isinstance(policy_capture, dict) and policy_capture.get('schema') == 'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001'):
        findings.append('POLICY_CAPTURE_REQUIRED')
    checks, evidence = {}, []
    for name in B07_CHECKS:
        member = CHECK_PREFIX + name + '/CHECK_RECEIPT.json'
        body = rfiles.get(member)
        if body is None:
            checks[name] = 'NOT_RUN'; findings.append(name + ':CHECK_RECEIPT_MISSING'); continue
        try:
            rec = json.loads(body)
        except ValueError:
            rec = None
        cf = check_findings(name, rec, member, rfiles, code_index, final_sha, code_sha, qr.get('RUN_ID'),
                            all_tx_ids=transaction_test_ids)
        checks[name] = 'PASS' if not cf else 'NOT_PASS'
        findings += cf
        evidence.append({'check': name, 'return_zip_member': member, 'sha256': _sha(body)})
    status = 'PASS' if not findings else 'NOT_PASS'
    receipt = {'schema': RECEIPT_SCHEMA, 'status': status, 'platform': 'WINDOWS_NTFS_PS51' if not any(
                   x.startswith(('QUAL_PRECHECK', 'QUAL_RECEIPT_NOT_NATIVE')) for x in findings) else 'NOT_PROVEN',
               'code_manifest_sha256': code_sha, 'final_zip_sha256': final_sha,
               'review_verdict_sha256': _sha(vraw), 'checks': checks, 'findings': sorted(set(findings)),
               'evidence': evidence, 'return_zip_sha256': _sha(rraw),
               'policy': {k: (policy_capture or {}).get(k) for k in ('master_sha256', 'head_sha256', 'revision_id',
                                                                     'reconciliation_sha256')},
               'produced_after_independent_b06': True, 'gate_verdict_issued': False,
               'stage_receipt_requires_origin_decision': 'R44-B2D ORIGIN_DECISION_BINDER'}
    raw = _canonical(receipt)
    out = Path(out_path)
    if os.path.lexists(out):
        raise RuntimeError('B07_RECEIPT_EXISTS')
    with open(out, 'xb') as fh:
        fh.write(raw); fh.flush(); os.fsync(fh.fileno())
    return receipt


def _return_generic(q, raw):
    """RETURN ZIP integrity + exact RETURN_MANIFEST (without the G5-specific required members)."""
    z, files, f = q['_zip_members'](raw, 'RETURN')
    if z is None:
        return f, {}
    try:
        rm = json.loads(files['RETURN_MANIFEST.json'])
        recs = {r['path']: r for r in rm['files']}
        if rm.get('schema') != q['RETURN_MANIFEST_SCHEMA'] or set(recs) != set(files) - {'RETURN_MANIFEST.json'}:
            f.append('RETURN_MANIFEST_COVERAGE')
        for n, r in recs.items():
            if _sha(files.get(n, b'')) != r['sha256'] or len(files.get(n, b'')) != r['bytes']:
                f.append('RETURN_MANIFEST_MEMBER:' + n)
    except (KeyError, TypeError, ValueError):
        f.append('RETURN_MANIFEST_UNREADABLE')
    return f, files
