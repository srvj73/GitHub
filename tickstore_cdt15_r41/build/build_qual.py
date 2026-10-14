"""Deterministic CDT15 qualification build: manifests, FINAL package, QUAL bundle, bootstrap, witness.

Usage: python3 -I -B build_r41.py <source_dir> <out_dir>
No network, no execution of packaged code (test counts come from unittest loading).
"""
import hashlib
import importlib.util
import json
import sys
import unittest
import zipfile
from pathlib import Path

DATE = '20261014'
FIXED_TIME = (2026, 10, 13, 0, 0, 0)
REV = 'R46'
FINAL_NAME = 'TICKSTORE_FULL_FINAL_CDT15_%s_%s.zip' % (REV, DATE)
FINAL_WITNESS = 'WITNESS_TICKSTORE_FULL_FINAL_CDT15_%s_%s.json' % (REV, DATE)
QUAL_NAME = 'TICKSTORE_CDT15_%s_QUAL_%s.zip' % (REV, DATE)
QUAL_WITNESS = 'WITNESS_TICKSTORE_CDT15_%s_QUAL_%s.json' % (REV, DATE)
BOOTSTRAP = 'RUN_TICKSTORE_CDT15_%s_QUAL.ps1' % REV
BOOTSTRAP_B07 = 'RUN_TICKSTORE_CDT15_%s_B07.ps1' % REV
ZIP_PATTERN = 'TICKSTORE_CDT15_%s_QUAL_*.zip' % REV
BASELINE = {
    'handoff_zip_sha256': '2093EB4813C371DCD113C92C55AC1E15FFC24C7D201BDD1581FD9D49367F772C',
    'baseline_source_zip_sha256': '26F783A0B05DA2436DDD56B1CE23FC289FD9A44C8EBF8363419F8C55692CB757',
    'baseline_source_manifest_sha256': '2D6BC4F308F3D3B95D823456F2616FDCC74790096768102F83FF0D10CAAFA56F',
    'parent_source_zip_sha256': '53A86045068E0C7A1899BBEF78CF22FB857B73BF8FBD4CFC1E4F52ED899CBD30',
    # R45 parent: the R44 FINAL qualified natively (126/126, RETURN 02036B1E...); never rebuilt here.
    'parent_final_r44_sha256': '0FBB6C36B840F2EF228DB3B160AA50D733FE5293C80BB4060AFFD4C074F8A48D',
    'parent_r44_native_return_sha256': '02036B1EA45370BE570865E281F8F5FC4C5D1C5364171680E2EE493EC7C5BB6D',
    # R45 FINAL audited by the origin (SOURCE_PASS, native held for B07-PROVENANCE-01/ORDER-01).
    'parent_final_r45_sha256': 'C0D1921634AE24D068BE7970C587244C7C1AEA10C6B06CB60E1C796139EFC700',
    # R46 parent: R45B internal candidate (B07 fixes), superseded by the completeness campaign.
    'parent_final_r45b_sha256': '3155EE11B81EA2E0973B9C525A4399558690DFABCFC8FB3B633D79787615B875',
}
POLICY = {'revision': '20261013T070500-0300-695DCD6495E549B1',
          'master_sha256': '695DCD6495E549B13B13A73E063EA147CF97354C53940A70647EDFD0A0BC7DF5',
          'head_sha256': 'B3B419592DC29651487B1545E1CD7AE66604AB78582202883684E69BCB1FF7EA',
          'custody': 'SNAPSHOT_NON_AUTHORITATIVE_RECONCILE_AT_CHATGPT_ORIGIN',
          'POLICY_RECONCILIATION_FOR_R45': 'NOT_ISSUED'}
SUITES = {
    # B2-G5-01 producer/consumer controls and the runner/consumer contract (new in R44).
    'S8_G5_EVIDENCE_BUILDER': {'files': [{'file': 'tests/test_g5_evidence_builder.py'}], 'sys_path': ['tests']},
    'S9_G5_PROOF_RUNNER_CONTRACT': {'files': [{'file': 'tests/test_g5_proof_runner_contract.py'}], 'sys_path': ['tests']},
    # R45: B2C/B2D/B07 integrated into the candidate, held sandbox admission, legacy entry isolation.
    'S10_B2C_POLICY_CAPTURE_BINDING': {'files': [{'file': 'tests/test_b2c_policy_capture_binding.py'}], 'sys_path': ['tests']},
    'S11_B2D_ORIGIN_DECISION_BINDER': {'files': [{'file': 'tests/test_b2d_origin_decision_binder.py'}], 'sys_path': ['tests']},
    'S12_B07_TECHNICAL_PRODUCER': {'files': [{'file': 'tests/test_b07_technical_producer.py'}], 'sys_path': ['tests']},
    'S13_SANDBOX_ADMISSION': {'files': [{'file': 'tests/test_sandbox_admission.py'}], 'sys_path': ['tests']},
    'S14_LEGACY_ENTRY_ISOLATION': {'files': [{'file': 'tests/test_legacy_entry_isolation.py'}], 'sys_path': ['tests']},
    # R46 completeness: operator entries (MENU, D4 Ctrl+C, continuation retry, wrapper elevation),
    # gate-chain procedures (chain until B06, D5/FULL_PREP/FULL_ADMIT publication, admission facts),
    # STATE CAS recovery decision table.
    'S15_OPERATOR_ENTRY_POINTS': {'files': [{'file': 'tests/test_operator_entry_points.py'}], 'sys_path': ['tests']},
    'S16_GATE_CHAIN_PROCEDURES': {'files': [{'file': 'tests/test_gate_chain_procedures.py'}], 'sys_path': ['tests']},
    'S17_STATE_CAS_RECOVERY': {'files': [{'file': 'tests/test_state_cas_recovery.py'}], 'sys_path': ['tests']},
    # Physical power-loss lab tooling (preflight/plan/arm/inspect/reconcile/aggregate) on the packaged
    # engine with an EMULATED cut; never physical evidence (that runs only in a separate lab).
    'S18_POWERLOSS_LAB_TOOLING': {'files': [{'file': 'tests/test_lab_powerloss.py'}], 'sys_path': ['tests'], 'timeout': 7200},
}
SCRIPTS = {
    'R45_B2C_NATIVE_PROBE': {'script': 'qual/R45_B2C_NATIVE_PROBE.py', 'isolated': True, 'timeout': 600,
                             'expect': ['R45_B2C_NATIVE_PROBE=PASS', 'POLICY_RECONCILIATION_FOR_R45=NOT_ISSUED']},
}
PROOFS = {
    # Order matters only for readability of the log; every proof uses its own sandbox.
    'PROCESS_TREE_CRASH_CONTAINMENT': {'timeout': 600},
    'STAGE_B_FULL_CHAIN_NATIVE': {'timeout': 1800},
    'D4_CLOSURE_NATIVE_1399': {'timeout': 3600, 'volume': 'D'},
    'PS51_INSTALL_MENU': {'timeout': 3600},
    'SAFE_STOP_RESUME_ROW_GROUP': {'timeout': 5400, 'volume': 'D'},
    'POWERLOSS_EMULATED': {'timeout': 7200, 'volume': 'D'},
}
B1_DIR = Path(__file__).resolve().parent.parent / 'b1'
B2C_FIX = Path(__file__).resolve().parent.parent / 'b2c/proposed_contract_fixture'
# Origin-approved exact bytes (R44 G5 origin decision): never re-derived at build time.
B2C_APPROVED = {'test_first_admission_transaction.py': 'E74F37015B55FBA5A139A225A4FC4BCFA0EC1747FA9B8F8982C4340A69A73E29',
                'test_bootstrap_contract.py': '40B396FC30656CFDDA0ACA16BE19ED5CB653CF2C4ED7FB36CC6AC26874295A24'}
B1_INPUTS = {'b1/R3_RUNTIME_ORIGINAL_ARCHIVE.zip': B1_DIR / 'r3_inputs/R3_RUNTIME_ORIGINAL_ARCHIVE.zip',
             'b1/QUALIFICATION_CONTRACT_ORIGINAL.json': B1_DIR / 'r3_inputs/QUALIFICATION_CONTRACT_ORIGINAL.json',
             'b1/tests_full_lifecycle.py': B1_DIR / 'derived/tests_full_lifecycle.py',
             'b1/tests_delta.py': B1_DIR / 'derived/tests_delta.py',
             'b1/test_first_admission_transaction.py': B2C_FIX / 'test_first_admission_transaction.py',
             'b1/test_bootstrap_contract.py': B2C_FIX / 'test_bootstrap_contract.py'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def canon(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def files_under(root, exclude=()):
    out = []
    for p in sorted(Path(root).rglob('*')):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and '__pycache__' not in p.parts and rel not in exclude:
            out.append((rel, p.read_bytes()))
    return out


def record(rel, raw):
    return {'path': rel, 'bytes': len(raw), 'sha256': sha(raw)}


def write_zip(path, members):
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in members:
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 0
            z.writestr(info, raw, compresslevel=9)


def count_tests(source, spec):
    total = 0
    for extra in spec.get('sys_path', []):
        sys.path.insert(0, str(source / extra))
    for i, item in enumerate(spec['files']):
        path = source / item['file']
        name = 'r41build_%d_%s' % (i, path.stem)
        ms = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(ms); sys.modules[name] = mod; ms.loader.exec_module(mod)
        suite = unittest.TestLoader().loadTestsFromModule(mod)
        flat = []
        def walk(s):
            for t in s:
                walk(t) if isinstance(t, unittest.TestSuite) else flat.append(t)
        walk(suite)
        if item.get('only'):
            flat = [t for t in flat if '.'.join(t.id().split('.')[-2:]) in set(item['only'])]
            assert len(flat) == len(item['only']), item
        total += len(flat)
    return total


def main(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    for name, digest in B2C_APPROVED.items():
        assert sha((B2C_FIX / name).read_bytes()) == digest, 'B2C_APPROVED_FIXTURE_DRIFT:' + name
    assert REV not in ('R44', 'R45', 'R45B'), 'PREVIOUS_FINALS_ARE_FROZEN_NEVER_REBUILT'
    import re as _re
    menu_pin = _re.search(r"CANDIDATE_MENU_SHA = '([0-9A-F]{64})'",
                          (source / 'candidate/control/MENU_OFFICIAL_ADMISSION_READONLY.py').read_text(encoding='utf-8'))
    assert menu_pin and menu_pin.group(1) == sha((source / 'candidate/menu/MENU.py').read_bytes()), 'CANDIDATE_MENU_PIN_DRIFT'
    out.mkdir(parents=True, exist_ok=True)
    # 1. Runtime code manifest (outside the candidate root: ReleaseChain closed set).
    code = files_under(source / 'candidate')
    runtime = {'schema': 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001', 'revision': 'CDT15_' + REV,
               'root': 'implementation_v001/candidate', 'files': [record(r, b) for r, b in code]}
    (source / 'RUNTIME_CODE_MANIFEST.json').write_bytes(canon(runtime))
    runtime_sha = sha((source / 'RUNTIME_CODE_MANIFEST.json').read_bytes())
    # 2. Source manifest of the whole implementation tree.
    src = files_under(source, exclude=('SOURCE_MANIFEST.json',))
    smanifest = {'schema': 'SOURCE_FILE_MANIFEST_SHA256_V001', 'revision': 'CDT15_' + REV,
                 'file_count': len(src), 'files': [record(r, b) for r, b in src]}
    (source / 'SOURCE_MANIFEST.json').write_bytes(canon(smanifest))
    src = files_under(source)
    # 3. FINAL package in the installer's format.
    members = [('implementation_v001/' + r, b) for r, b in src]
    pmanifest = canon({'schema': 'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001', 'revision': 'CDT15_' + REV,
                       'files': [record(n, b) for n, b in members]})
    # The installer and verifier require member records with exactly path/bytes/sha256.
    final_path = out / FINAL_NAME
    if final_path.exists(): final_path.unlink()
    write_zip(final_path, [('PACKAGE_MANIFEST.json', pmanifest)] + members)
    final_raw = final_path.read_bytes()
    fwitness = canon({'schema': 'TICKSTORE_FINAL_PACKAGE_WITNESS_V001', 'package_name': FINAL_NAME,
                      'package_sha256': sha(final_raw), 'package_bytes': len(final_raw),
                      'manifest_sha256': sha(pmanifest), 'runtime_code_manifest_sha256': runtime_sha,
                      'source_manifest_sha256': sha((source / 'SOURCE_MANIFEST.json').read_bytes()),
                      'status': 'SOURCE_CANDIDATE_NOT_RELEASED', 'production_authorized': False,
                      'full_started': False, **BASELINE})
    (out / FINAL_WITNESS).write_bytes(fwitness)
    # 4. QUAL plan with exact expected cardinalities.
    suites = {}
    for name, spec in SUITES.items():
        suites[name] = dict(spec, expected=count_tests(source, spec))
    plan = canon({'schema': 'TICKSTORE_CDT15_R41_QUAL_PLAN_V001', 'final_package_name': FINAL_NAME,
                  'final_package_sha256': sha(final_raw), 'final_witness_name': FINAL_WITNESS,
                  'runtime_code_manifest_sha256': runtime_sha, 'suites': suites, 'scripts': SCRIPTS,
                  'proofs': PROOFS, 'revision': REV,
                  'b1': {'r3_archive': 'b1/R3_RUNTIME_ORIGINAL_ARCHIVE.zip',
                         'r3_archive_sha256': '2379512BD32CA751E0636EA4186F097035542F851CC51019817DDB5FFC4480E4',
                         'contract': 'b1/QUALIFICATION_CONTRACT_ORIGINAL.json',
                         'contract_sha256': '9AF1C840C1AE519BBD1A36C9C9CA7C2A91E0879D4AE6CEC049A11E2FB1FEF944',
                         'overlays': [
                             {'target': 'engineering/tests_full_lifecycle.py', 'approval': 'R43_B1A_ORIGIN_APPROVED',
                              'parent_sha256': 'EE30AA9325EE79A1F5FF4876DF72EC0A596AC351E9708447337841E9B43E592D',
                              'derived': 'b1/tests_full_lifecycle.py',
                              'derived_sha256': sha((B1_DIR / 'derived/tests_full_lifecycle.py').read_bytes())},
                             {'target': 'cdt15/tests_delta.py', 'approval': 'R43_B1B_ORIGIN_APPROVED_PATCH_84E32FA3',
                              'parent_sha256': '67B41A04787A2BEB3CB1CA7AE1CF79286E034F81B50ADEAC4C536956972FAD1D',
                              'derived': 'b1/tests_delta.py',
                              'derived_sha256': sha((B1_DIR / 'derived/tests_delta.py').read_bytes())},
                             {'target': 'engineering/test_first_admission_transaction.py',
                              'approval': 'R44_G5_ORIGIN_DECISION_B2C_FIXTURE_APPROVED_EXACT_BYTES',
                              'parent_sha256': '993F323F761A40C1BE32301B17A57D73CE6C7E633657D538507E42F5339E4C9C',
                              'derived': 'b1/test_first_admission_transaction.py',
                              'derived_sha256': B2C_APPROVED['test_first_admission_transaction.py']},
                             {'target': 'engineering/test_bootstrap_contract.py',
                              'approval': 'R44_G5_ORIGIN_DECISION_B2C_FIXTURE_APPROVED_EXACT_BYTES',
                              'parent_sha256': 'AC22516AB7EEF28BDC380352C5E6AB73CC035942B8A3BB4F905771055AAA89ED',
                              'derived': 'b1/test_bootstrap_contract.py',
                              'derived_sha256': B2C_APPROVED['test_bootstrap_contract.py']}],
                         'microprobes': 'qual/R43_B1A_MICROPROBES.py',
                         'microprobes_sha256': sha((source / 'qual/R43_B1A_MICROPROBES.py').read_bytes()),
                         'portable': 106, 'native_only': 20}})
    qmembers = [('qual/QUAL_DRIVER.py', (source / 'qual/QUAL_DRIVER.py').read_bytes()),
                ('qual/R44_B1_RUNNER.py', (source / 'qual/R44_B1_RUNNER.py').read_bytes()),
                ('qual/R43_B1A_MICROPROBES.py', (source / 'qual/R43_B1A_MICROPROBES.py').read_bytes()),
                # QUAL_DRIVER imports the held-admission module from its own bundle directory.
                ('qual/SANDBOX_ADMISSION.py', (source / 'qual/SANDBOX_ADMISSION.py').read_bytes()),
               ] + [(k, v.read_bytes()) for k, v in B1_INPUTS.items()] + [
                ('qual/QUAL_PLAN.json', plan), ('FINAL/' + FINAL_NAME, final_raw), ('FINAL/' + FINAL_WITNESS, fwitness)]
    qmanifest = canon({'schema': 'TICKSTORE_CDT15_R41_QUAL_BUNDLE_MANIFEST_V001',
                       'files': [record(n, b) for n, b in qmembers]})
    qual_path = out / QUAL_NAME
    if qual_path.exists(): qual_path.unlink()
    write_zip(qual_path, [('QUAL_MANIFEST.json', qmanifest)] + qmembers)
    qual_raw = qual_path.read_bytes()
    # 5. Bootstrap (ASCII, CRLF) with embedded pins.
    tpl = (Path(__file__).parent / 'RUN_TICKSTORE_CDT15_QUAL.ps1.template').read_text(encoding='ascii')
    boot = {}
    for mode, name in (('QUAL', BOOTSTRAP), ('B07', BOOTSTRAP_B07)):
        ps = (tpl.replace('@@ZIP_NAME@@', QUAL_NAME).replace('@@ZIP_SHA@@', sha(qual_raw))
                 .replace('@@ZIP_BYTES@@', str(len(qual_raw))).replace('@@QUAL_MANIFEST_SHA@@', sha(qmanifest))
                 .replace('@@REV@@', REV).replace('@@BOOTSTRAP@@', name).replace('@@MODE@@', mode)
                 .replace('@@DRIVER@@', 'qual\\QUAL_DRIVER.py').replace('@@ZIP_PATTERN@@', ZIP_PATTERN))
        assert '@@' not in ps
        boot[mode] = ps.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii')
        (out / name).write_bytes(boot[mode])
    ps_raw = boot['QUAL']
    # 6. External witness.
    witness = canon({'schema': 'EXTERNAL_WITNESS_TICKSTORE_CDT15_QUAL_V002', 'revision': REV, 'role': 'ENGINEER_ONLY',
                     'qual_zip': QUAL_NAME, 'qual_zip_sha256': sha(qual_raw), 'qual_zip_bytes': len(qual_raw),
                     'qual_manifest_sha256': sha(qmanifest), 'bootstrap': BOOTSTRAP,
                     'bootstrap_sha256': sha(ps_raw), 'bootstrap_bytes': len(ps_raw),
                     'bootstrap_b07': BOOTSTRAP_B07, 'bootstrap_b07_sha256': sha(boot['B07']),
                     'bootstrap_b07_bytes': len(boot['B07']),
                     'b07_mode': 'ONLY_AFTER_INDEPENDENT_B06_PASS_CHAIN_UNTIL_B06_REQUIRED',
                     'final_package': FINAL_NAME, 'final_package_sha256': sha(final_raw),
                     'final_package_manifest_sha256': sha(pmanifest),
                     'runtime_code_manifest_sha256': runtime_sha,
                     'source_manifest_sha256': sha((source / 'SOURCE_MANIFEST.json').read_bytes()),
                     'policy': POLICY, **BASELINE,
                     'expected_tests': {k: v['expected'] for k, v in suites.items()},
                     'scripts': sorted(SCRIPTS), 'proofs': sorted(PROOFS), 'b1_contract_ids': 126,
                     'elevation_required': True,
                     'invocation': 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                                   '"C:\\Users\\silvi\\OneDrive\\Downloads\\' + BOOTSTRAP + '"',
                     'production_modified': False, 'full_started': False, 'b06_formal_audit': False,
                     'G4': 'INCOMPLETE', 'G5': 'INCOMPLETE_CHECKPOINT_POWERLOSS_RECOVERY_PHYSICAL_PROOF_PENDING',
                     'B06': 'NOT_STARTED', 'B07': 'NOT_STARTED_SOURCE_ONLY_AFTER_B06',
                     'gate_verdict_issued': False})
    (out / QUAL_WITNESS).write_bytes(witness)
    for name in (QUAL_NAME, BOOTSTRAP, BOOTSTRAP_B07, QUAL_WITNESS, FINAL_NAME, FINAL_WITNESS):
        print('%s %s %d' % (sha((out / name).read_bytes()), name, (out / name).stat().st_size))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
