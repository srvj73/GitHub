"""R45 origin return package: R44D2 delta, R45 FINAL/QUAL, physical diff, reconciliation REQUEST.

Usage: python3 -I -B build_r45_return.py <repo_root> <offline_preflight_run_dir> <portable_r3_result_dir>
The reconciliation document produced here is a REQUEST bound to the frozen bytes, never a
receipt: POLICY_RECONCILIATION_FOR_R45 stays NOT_ISSUED until the ChatGPT origin issues it.
"""
import difflib
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

DATE = '20261014'
FIXED_TIME = (2026, 10, 14, 0, 0, 0)
NAME = 'TICKSTORE_CDT15_R45_RETORNO_ORIGEM_%s.zip' % DATE
WITNESS = 'WITNESS_TICKSTORE_CDT15_R45_RETORNO_ORIGEM_%s.json' % DATE
CONTEXT = 'ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 15'
CORE_RC1 = 'D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0'


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def canon(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def final_tree(path):
    with zipfile.ZipFile(path) as z:
        return {n[len('implementation_v001/'):]: z.read(n) for n in z.namelist() if n.startswith('implementation_v001/')}


def physical_diff(old, new):
    rows, text = [], io.StringIO()
    for rel in sorted(set(old) | set(new)):
        a, b = old.get(rel), new.get(rel)
        if a == b:
            continue
        kind = 'ADDED' if a is None else 'REMOVED' if b is None else 'CHANGED'
        rows.append({'path': rel, 'change': kind, 'r44_sha256': sha(a) if a is not None else None,
                     'r45_sha256': sha(b) if b is not None else None})
        if rel.endswith(('MANIFEST.json',)):
            continue  # regenerated manifests: identities listed above, body omitted
        try:
            la = a.decode('utf-8').splitlines(True) if a is not None else []
            lb = b.decode('utf-8').splitlines(True) if b is not None else []
        except UnicodeDecodeError:
            text.write('Binary files differ: %s\n' % rel); continue
        text.writelines(difflib.unified_diff(la, lb, 'R44/' + rel if a is not None else '/dev/null',
                                             'R45/' + rel if b is not None else '/dev/null'))
    return rows, text.getvalue().encode('utf-8')


def main(repo, offline_run, portable_dir):
    repo, offline_run, portable_dir = Path(repo), Path(offline_run), Path(portable_dir)
    dist = repo / 'dist'
    fw = json.loads((dist / ('WITNESS_TICKSTORE_FULL_FINAL_CDT15_R45_%s.json' % DATE)).read_bytes())
    qw = json.loads((dist / ('WITNESS_TICKSTORE_CDT15_R45_QUAL_%s.json' % DATE)).read_bytes())
    final_raw = (dist / fw['package_name']).read_bytes()
    assert sha(final_raw) == fw['package_sha256'] == qw['final_package_sha256']
    r44_final = dist / ('TICKSTORE_FULL_FINAL_CDT15_R44_%s.zip' % DATE)
    assert sha(r44_final.read_bytes()) == fw['parent_final_r44_sha256'], 'R44_FINAL_CHANGED'
    old, new = final_tree(r44_final), final_tree(dist / fw['package_name'])
    assert sha(new['candidate/full/tickstore_serial_runner.py']) == CORE_RC1 == sha(old['candidate/full/tickstore_serial_runner.py'])
    rows, diff = physical_diff(old, new)
    ctl = 'candidate/control/'
    binding = json.loads(new[ctl + 'FIRST_ADMISSION_BINDING.json'])
    head = json.loads(new['tests/fixtures/R40_CAPTURE_NON_AUTHORITATIVE/POLITICA_CANONICA_HEAD.json'])
    request = {
        'schema': 'TICKSTORE_R45_POLICY_RECONCILIATION_REQUEST_V001',
        'document_kind': 'REQUEST_TO_ORIGIN_NOT_A_RECEIPT',
        'POLICY_RECONCILIATION_FOR_R45': 'NOT_ISSUED',
        'requested_from': 'CHATGPT_ORIGIN', 'route': CONTEXT,
        'frozen_bytes': {
            'final_package': fw['package_name'], 'final_package_sha256': fw['package_sha256'],
            'final_package_bytes': fw['package_bytes'], 'final_package_manifest_sha256': fw['manifest_sha256'],
            'runtime_code_manifest_sha256': fw['runtime_code_manifest_sha256'],
            'source_manifest_sha256': fw['source_manifest_sha256'],
            'qual_bundle': qw['qual_zip'], 'qual_bundle_sha256': qw['qual_zip_sha256'],
            'qual_bootstrap': qw['bootstrap'], 'qual_bootstrap_sha256': qw['bootstrap_sha256'],
            'core_rc1_sha256': CORE_RC1,
            'policy_capture_binding_sha256': binding['policy_capture_binding_sha256'],
            'first_admission_binding_sha256': sha(new[ctl + 'FIRST_ADMISSION_BINDING.json']),
            'parent_final_r44_sha256': fw['parent_final_r44_sha256']},
        'policy_capture_presented': {
            'custody': 'SNAPSHOT_NON_AUTHORITATIVE_RECONCILE_AT_CHATGPT_ORIGIN',
            'master_filename': head['master_filename'], 'master_sha256': head['master_sha256'],
            'head_sha256': sha(new['tests/fixtures/R40_CAPTURE_NON_AUTHORITATIVE/POLITICA_CANONICA_HEAD.json']),
            'revision_id': head['revision_id'], 'state': head.get('state')},
        'record_the_origin_would_issue': {
            'schema': 'TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001', 'issuer': 'CHATGPT_ORIGIN',
            'status': 'CURRENT_AT_ORIGIN',
            'required_fields': ['policy_master_sha256', 'policy_head_sha256', 'policy_revision',
                                'live_cardinality={master:1,head:1}', 'live_state=FROZEN',
                                'capture_operational_authority=false', 'administrative_owner_gate_required=false',
                                'scope contains D4_FIRST_ADMISSION', 'routing_project', 'routing_thread',
                                'reconciled_at (tz-aware)', 'valid_until (tz-aware, <= 72h after reconciled_at)'],
            'optional_binding_fields_suggested': ['r45_final_package_sha256', 'r45_runtime_code_manifest_sha256'],
            'digest_delivery': 'SHA-256 of the record supplied separately by the operator (never read from the record)',
            'verifier': ctl + 'POLICY_CAPTURE_BINDING.py::verify_capture'},
        'engineer_statement': 'No reconciliation record, receipt or approval was produced or simulated by engineering.',
        'production_modified': False, 'full_started': False, 'b06_started': False, 'b07_executed': False}
    ledger = {
        'schema': 'TICKSTORE_CDT15_R45_LEDGER_V001', 'route': CONTEXT, 'role': 'ENGINEER_ONLY',
        'G4': 'INCOMPLETE', 'G5': 'INCOMPLETE',
        'G5_single_blocker': 'CHECKPOINT_POWERLOSS_RECOVERY:PHYSICAL_PROOF_NOT_SPECIFIED_BY_ORIGIN',
        'POWERLOSS_EMULATED': 'NEVER_SATISFIES_CHECKPOINT_POWERLOSS_RECOVERY',
        'B06': 'NOT_STARTED_INDEPENDENT', 'B07': 'SOURCE_ONLY_EXECUTION_ONLY_AFTER_B06_PASS',
        'POLICY_RECONCILIATION_FOR_R45': 'NOT_ISSUED',
        'R44': {'native_return_sha256': fw['parent_r44_native_return_sha256'], 'contract_ids': '126/126',
                'final_sha256': fw['parent_final_r44_sha256'], 'repeated': False},
        'R44D2': 'BUILT_PENDING_NATIVE_EXECUTION', 'R45': 'BUILT_OFFLINE_PREFLIGHT_PASS_PENDING_NATIVE_EXECUTION',
        'legacy_entry_isolation': 'PACKAGING_QUARANTINE+STATIC_NON_REACHABILITY+DIRECT_ENTRY_NEGATIVES; RESIDUAL_DECLARED',
        'production_modified': False, 'full_started': False, 'power_cut_executed': False,
        'paid_credits_used': False, 'gate_verdict_issued': False}
    members = []

    def add(name, raw):
        members.append((name, raw))
    add('00_LEIA_PRIMEIRO_R45.md', (repo / 'r45/00_LEIA_PRIMEIRO_R45.md').read_bytes())
    add('LEDGER_R45.json', canon(ledger))
    add('R45/R45_POLICY_RECONCILIATION_REQUEST.json', canon(request))
    add('R45/LEGACY_ENTRY_ISOLATION.md', (repo / 'r45/LEGACY_ENTRY_ISOLATION.md').read_bytes())
    add('R45/R45_VS_R44_FINAL.diff', diff)
    add('R45/R45_VS_R44_FINAL_FILE_DELTA.json', canon({'schema': 'TICKSTORE_R45_FILE_DELTA_V001',
                                                       'r44_final_sha256': fw['parent_final_r44_sha256'],
                                                       'r45_final_sha256': fw['package_sha256'], 'files': rows}))
    for n in (fw['package_name'], 'WITNESS_TICKSTORE_FULL_FINAL_CDT15_R45_%s.json' % DATE, qw['qual_zip'],
              'WITNESS_TICKSTORE_CDT15_R45_QUAL_%s.json' % DATE, qw['bootstrap']):
        add('R45/' + n, (dist / n).read_bytes())
    for n in ('RUN_LOG.txt', 'QUAL_RECEIPT.json'):
        add('R45/OFFLINE_PREFLIGHT/' + n, (offline_run / n).read_bytes())
    add('R45/PORTABLE_R3_106/RESULT.json', (portable_dir / 'RESULT.json').read_bytes())
    for n in ('TICKSTORE_CDT15_R44D2_DROOT_%s.zip' % DATE, 'RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1',
              'WITNESS_TICKSTORE_CDT15_R44D2_DROOT_%s.json' % DATE, 'CHECK_PS51_SYNTAX.ps1'):
        add('R44D2/' + n, (dist / n).read_bytes())
    for rel in ('source/qual/R44D2_DROOT_AUDIT.py', 'source/qual/SANDBOX_ADMISSION.py', 'source/qual/QUAL_DRIVER.py',
                'source/tests/test_sandbox_admission.py', 'build/RUN_TICKSTORE_CDT15_QUAL.ps1.template'):
        add('R44D2/source/' + Path(rel).name, (repo / rel).read_bytes())
    manifest = canon({'schema': 'TICKSTORE_CDT15_R45_RETURN_MANIFEST_V001',
                      'files': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n, b in members]})
    out = dist / NAME
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n, b in members + [('RETURN_MANIFEST.json', manifest)]:
            info = zipfile.ZipInfo(n, FIXED_TIME); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16; info.create_system = 0
            z.writestr(info, b, compresslevel=9)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        for f in json.loads(z.read('RETURN_MANIFEST.json'))['files']:
            assert sha(z.read(f['path'])) == f['sha256']
    raw = out.read_bytes()
    (dist / WITNESS).write_bytes(canon({
        'schema': 'EXTERNAL_WITNESS_TICKSTORE_CDT15_R45_RETURN_V001', 'zip_filename': NAME, 'zip_bytes': len(raw),
        'zip_sha256': sha(raw), 'members': len(members) + 1, 'manifest_sha256': sha(manifest),
        'r45_final_sha256': fw['package_sha256'], 'r45_qual_sha256': qw['qual_zip_sha256'],
        'r45_bootstrap_sha256': qw['bootstrap_sha256'], 'reconciliation_request_sha256': sha(canon(request)),
        'POLICY_RECONCILIATION_FOR_R45': 'NOT_ISSUED', 'role': 'ENGINEER_ONLY', 'effects_authorized': False,
        'full_started': False, 'route': CONTEXT}))
    print(sha(raw), NAME, len(raw))
    print('RECONCILIATION_REQUEST_SHA256=' + sha(canon(request)))
    print('DELTA_FILES=%d' % len(rows))


if __name__ == '__main__':
    main(*sys.argv[1:4])
