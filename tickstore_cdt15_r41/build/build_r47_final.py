"""R47 single final successor package (origin R46 consolidated review, Option A RC1R1 recertification).

Usage: python3 -I -B build_r47_final.py <repo_root> <preflight_seg1_dir> <preflight_seg2_dir> <portable_r3_dir>
Everything is read from frozen bytes; the policy reconciliation document is a REQUEST, never a receipt.
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
REV = 'R47'
NAME = 'TICKSTORE_CDT15_%s_PACOTE_FINAL_ENGENHARIA_%s.zip' % (REV, DATE)
WITNESS = 'WITNESS_TICKSTORE_CDT15_%s_PACOTE_FINAL_ENGENHARIA_%s.json' % (REV, DATE)
CONTEXT = 'ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 15'
CORE_RC1 = 'D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0'
CORE_RC1R1 = '749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00'
POLICY_R41 = {'revision': 'R41', 'revision_id': '20261014T085300-0300-B00AF978A2C4728D',
              'master_sha256': 'B00AF978A2C4728D8E12BAC8F56F4F4963032D62FDEA399C1CC7085DD0BCB23C',
              'head_sha256': '0F8127056E9DA3EFB9D69CC96F436AA6D888AD261CC218420D204274CF480590'}
FROZEN = {'R44': '0FBB6C36B840F2EF228DB3B160AA50D733FE5293C80BB4060AFFD4C074F8A48D',
          'R45': 'C0D1921634AE24D068BE7970C587244C7C1AEA10C6B06CB60E1C796139EFC700',
          'R45B': '3155EE11B81EA2E0973B9C525A4399558690DFABCFC8FB3B633D79787615B875',
          'R46': '0CAA565C784A7EA99458E150F878DE7F2BEA78E5C3DCD7F4928DE8337FB69DC2'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def canon(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def final_tree(path):
    with zipfile.ZipFile(path) as z:
        return {n[len('implementation_v001/'):]: z.read(n) for n in z.namelist() if n.startswith('implementation_v001/')}


def physical_diff(old, new, a_label, b_label):
    rows, text = [], io.StringIO()
    for rel in sorted(set(old) | set(new)):
        a, b = old.get(rel), new.get(rel)
        if a == b:
            continue
        rows.append({'path': rel, 'change': 'ADDED' if a is None else 'REMOVED' if b is None else 'CHANGED',
                     a_label + '_sha256': sha(a) if a is not None else None, b_label + '_sha256': sha(b) if b is not None else None})
        if rel.endswith('MANIFEST.json'):
            continue
        try:
            la = a.decode('utf-8').splitlines(True) if a is not None else []
            lb = b.decode('utf-8').splitlines(True) if b is not None else []
        except UnicodeDecodeError:
            text.write('Binary files differ: %s\n' % rel); continue
        text.writelines(difflib.unified_diff(la, lb, a_label + '/' + rel if a is not None else '/dev/null',
                                             b_label + '/' + rel if b is not None else '/dev/null'))
    return rows, text.getvalue().encode('utf-8')


def main(repo, seg1, seg2, portable):
    repo, seg1, seg2, portable = Path(repo), Path(seg1), Path(seg2), Path(portable)
    dist = repo / 'dist'
    for rev, digest in FROZEN.items():
        assert sha((dist / ('TICKSTORE_FULL_FINAL_CDT15_%s_%s.zip' % (rev, DATE))).read_bytes()) == digest, 'FROZEN_' + rev
    fw = json.loads((dist / ('WITNESS_TICKSTORE_FULL_FINAL_CDT15_%s_%s.json' % (REV, DATE))).read_bytes())
    qw = json.loads((dist / ('WITNESS_TICKSTORE_CDT15_%s_QUAL_%s.json' % (REV, DATE))).read_bytes())
    final_path = dist / fw['package_name']
    assert sha(final_path.read_bytes()) == fw['package_sha256'] == qw['final_package_sha256']
    new = final_tree(final_path)
    assert sha(new['candidate/full/tickstore_serial_runner.py']) == CORE_RC1R1
    assert sha(new['tests/fixtures/RC1R1_HISTORICAL/tickstore_serial_runner.RC1_D3A15572.py.txt']) == CORE_RC1
    old = final_tree(dist / ('TICKSTORE_FULL_FINAL_CDT15_R46_%s.zip' % DATE))
    rows, diff = physical_diff(old, new, 'R46', REV)
    successor = json.loads((dist / 'V002R23_RC1R1_SUCCESSOR_IDENTITIES.json').read_bytes())
    assert sha((dist / successor['package_zip']).read_bytes()) == successor['package_zip_sha256']
    assert sha((dist / successor['review_pack']).read_bytes()) == successor['review_pack_sha256']
    ctl = 'candidate/control/'
    binding = json.loads(new[ctl + 'FIRST_ADMISSION_BINDING.json'])
    head_raw = new['tests/fixtures/R40_CAPTURE_NON_AUTHORITATIVE/POLITICA_CANONICA_HEAD.json']
    head = json.loads(head_raw)
    identities = {
        'schema': 'TICKSTORE_CDT15_R47_IDENTITIES_V001', 'revision': REV,
        'final_package': fw['package_name'], 'final_package_sha256': fw['package_sha256'],
        'final_package_bytes': fw['package_bytes'], 'final_package_manifest_sha256': fw['manifest_sha256'],
        'runtime_code_manifest_sha256': fw['runtime_code_manifest_sha256'], 'source_manifest_sha256': fw['source_manifest_sha256'],
        'qual_bundle': qw['qual_zip'], 'qual_bundle_sha256': qw['qual_zip_sha256'], 'qual_manifest_sha256': qw['qual_manifest_sha256'],
        'bootstrap_qual': qw['bootstrap'], 'bootstrap_qual_sha256': qw['bootstrap_sha256'],
        'bootstrap_b07': qw['bootstrap_b07'], 'bootstrap_b07_sha256': qw['bootstrap_b07_sha256'],
        'expected_tests': qw['expected_tests'], 'proofs': qw['proofs'], 'b1_contract_ids': qw['b1_contract_ids'],
        'core_rc1r1_sha256': CORE_RC1R1, 'core_rc1_historical_sha256': CORE_RC1, 'successor_d4': successor,
        'policy_active_named_by_origin': POLICY_R41,
        'first_admission_binding_sha256': sha(new[ctl + 'FIRST_ADMISSION_BINDING.json']),
        'policy_capture_binding_sha256': binding['policy_capture_binding_sha256'], 'wrapper_sha256': binding['wrapper_sha256'],
        'frozen_previous_finals': FROZEN, 'tested_code_equals_packaged_code': 'ENFORCED_BY_CAMPAIGN_EXTRACTION_AND_CLOSED_MANIFEST'}
    request = {
        'schema': 'TICKSTORE_R47_POLICY_RECONCILIATION_REQUEST_V001', 'document_kind': 'REQUEST_TO_ORIGIN_NOT_A_RECEIPT',
        'required_against': {'policy': POLICY_R41, 'rule': 'live hash-bound origin reconciliation against R41 or a later revision; the packaged R40 capture is never authority'},
        'POLICY_RECONCILIATION': 'NOT_ISSUED', 'route': CONTEXT,
        'frozen_bytes': {k: identities[k] for k in ('final_package_sha256', 'runtime_code_manifest_sha256', 'qual_bundle_sha256',
                                                    'core_rc1r1_sha256', 'policy_capture_binding_sha256',
                                                    'first_admission_binding_sha256')},
        'policy_capture_presented': {'master_sha256': head['master_sha256'], 'head_sha256': sha(head_raw),
                                     'revision_id': head['revision_id'], 'custody': 'R40_TEST_FIXTURE_NON_AUTHORITATIVE'},
        'needed_only_for': 'D4 and later stages, close to real authorized use',
        'engineer_statement': 'No reconciliation record, receipt, decision or approval was produced or simulated.'}
    members = []

    def add(name, raw):
        members.append((name, raw))
    for n in ('00_LEIA_PRIMEIRO_R47.md', 'RELATORIO_COMPLETUDE_R47.md', 'DEPENDENCIAS_EXTERNAS_R47.md',
              'RECERTIFICACAO_RC1R1.md', 'RC1R1_MUTATION_EVIDENCE_R47.txt'):
        add(n, (repo / 'r47' / n).read_bytes())
    add('B07_MUTATION_EVIDENCE_R46.txt', (repo / 'r46/B07_MUTATION_EVIDENCE_R46.txt').read_bytes())
    add('HISTORY/LEGACY_ENTRY_ISOLATION_R46.md', (repo / 'r46/LEGACY_ENTRY_ISOLATION.md').read_bytes())
    for n in (successor['package_zip'], successor['review_pack'], 'V002R23_RC1R1_SUCCESSOR_IDENTITIES.json'):
        add('SUCCESSOR_D4/' + n, (dist / n).read_bytes())
    add('LEDGER_INTERNO.md', (repo / 'ledger/INTERNAL_LEDGER.md').read_bytes())
    add('IDENTIDADES_R47.json', canon(identities))
    add('R47_POLICY_RECONCILIATION_REQUEST.json', canon(request))
    add('DIFF/R47_VS_R46_FINAL.diff', diff)
    add('DIFF/R47_VS_R46_FINAL_FILE_DELTA.json', canon({'schema': 'TICKSTORE_R47_FILE_DELTA_V001', 'files': rows}))
    for n in (fw['package_name'], 'WITNESS_TICKSTORE_FULL_FINAL_CDT15_%s_%s.json' % (REV, DATE), qw['qual_zip'],
              'WITNESS_TICKSTORE_CDT15_%s_QUAL_%s.json' % (REV, DATE), qw['bootstrap'], qw['bootstrap_b07'],
              'CHECK_PS51_SYNTAX.ps1', 'TICKSTORE_CDT15_R44D2_DROOT_%s.zip' % DATE, 'RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1',
              'WITNESS_TICKSTORE_CDT15_R44D2_DROOT_%s.json' % DATE):
        add('RUNNERS/' + n, (dist / n).read_bytes())
    for seg, d in (('SEG1_SAFE_STOP', seg1), ('SEG2_RESUME', seg2)):
        for n in ('RUN_LOG.txt', 'QUAL_RECEIPT.json', 'HEARTBEAT.json'):
            add('PREFLIGHT_OFFLINE/%s/%s' % (seg, n), (d / n).read_bytes())
    add('PREFLIGHT_OFFLINE/PORTABLE_R3_106_RESULT.json', (portable / 'RESULT.json').read_bytes())
    manifest = canon({'schema': 'TICKSTORE_CDT15_R47_FINAL_PACKAGE_MANIFEST_V001',
                      'files': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n, b in members]})
    out = dist / NAME
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n, b in members + [('PACKAGE_MANIFEST.json', manifest)]:
            info = zipfile.ZipInfo(n, FIXED_TIME); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16; info.create_system = 0
            z.writestr(info, b, compresslevel=9)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        for f in json.loads(z.read('PACKAGE_MANIFEST.json'))['files']:
            assert sha(z.read(f['path'])) == f['sha256']
    raw = out.read_bytes()
    (dist / WITNESS).write_bytes(canon({
        'schema': 'EXTERNAL_WITNESS_TICKSTORE_CDT15_R47_FINAL_ENGINEERING_PACKAGE_V001', 'zip_filename': NAME,
        'zip_bytes': len(raw), 'zip_sha256': sha(raw), 'members': len(members) + 1, 'manifest_sha256': sha(manifest),
        'r47_final_sha256': fw['package_sha256'], 'r47_qual_sha256': qw['qual_zip_sha256'],
        'r47_bootstrap_qual_sha256': qw['bootstrap_sha256'], 'r47_bootstrap_b07_sha256': qw['bootstrap_b07_sha256'],
        'core_rc1r1_sha256': CORE_RC1R1, 'successor_d4_package_zip_sha256': successor['package_zip_sha256'],
        'POLICY_RECONCILIATION': 'NOT_ISSUED', 'G5': 'INCOMPLETE_PHYSICAL_POWERLOSS_PENDING', 'B06': 'NOT_STARTED',
        'B07': 'PREPARED_NOT_EXECUTED', 'LEGACY_ENTRY': 'CLOSED_IN_CODE_RC1R1_OPTION_A', 'G11': 'CLOSED_IN_CODE',
        'SUCCESSOR_MIGRATION': 'PREPARED_NOT_APPLIED', 'G4': 'INCOMPLETE_NATIVE_R47_CAMPAIGN_PENDING',
        'role': 'ENGINEER_ONLY', 'production_modified': False, 'full_started': False, 'route': CONTEXT}))
    print(sha(raw), NAME, len(raw))
    print('DELTA_FILES=%d' % len(rows))


if __name__ == '__main__':
    main(*sys.argv[1:5])
