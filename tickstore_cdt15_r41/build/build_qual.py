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
REV = 'R43'
FINAL_NAME = 'TICKSTORE_FULL_FINAL_CDT15_%s_%s.zip' % (REV, DATE)
FINAL_WITNESS = 'WITNESS_TICKSTORE_FULL_FINAL_CDT15_%s_%s.json' % (REV, DATE)
QUAL_NAME = 'TICKSTORE_CDT15_%s_QUAL_%s.zip' % (REV, DATE)
QUAL_WITNESS = 'WITNESS_TICKSTORE_CDT15_%s_QUAL_%s.json' % (REV, DATE)
BOOTSTRAP = 'RUN_TICKSTORE_CDT15_%s_QUAL.ps1' % REV
ZIP_PATTERN = 'TICKSTORE_CDT15_%s_QUAL_*.zip' % REV
BASELINE = {
    'handoff_zip_sha256': '2093EB4813C371DCD113C92C55AC1E15FFC24C7D201BDD1581FD9D49367F772C',
    'baseline_source_zip_sha256': '26F783A0B05DA2436DDD56B1CE23FC289FD9A44C8EBF8363419F8C55692CB757',
    'baseline_source_manifest_sha256': '2D6BC4F308F3D3B95D823456F2616FDCC74790096768102F83FF0D10CAAFA56F',
    'parent_source_zip_sha256': '53A86045068E0C7A1899BBEF78CF22FB857B73BF8FBD4CFC1E4F52ED899CBD30',
}
POLICY = {'revision': '20261013T070500-0300-695DCD6495E549B1',
          'master_sha256': '695DCD6495E549B13B13A73E063EA147CF97354C53940A70647EDFD0A0BC7DF5',
          'head_sha256': 'B3B419592DC29651487B1545E1CD7AE66604AB78582202883684E69BCB1FF7EA',
          'custody': 'SNAPSHOT_NON_AUTHORITATIVE_RECONCILE_AT_CHATGPT_ORIGIN'}
SUITES = {
    # Only suites whose code changed since the R42 native PASS (AUTOCPU min rule).
    'S6_MULTIWORK_UNIT': {'files': [{'file': 'candidate/full/test_full_multiwork.py'}],
                          'sys_path': ['candidate/full']},
}
SCRIPTS = {
    'S7_STATIC_MULTIWORK_PREAUDIT': {'script': 'candidate/full/static_multiwork_preaudit.py',
                                     'expect': 'STATIC_MULTIWORK_PREAUDIT=PASS'},
}
SCENARIOS = {}
B1_DIR = Path(__file__).resolve().parent.parent / 'b1'
B1_INPUTS = {'b1/R3_RUNTIME_ORIGINAL_ARCHIVE.zip': B1_DIR / 'r3_inputs/R3_RUNTIME_ORIGINAL_ARCHIVE.zip',
             'b1/QUALIFICATION_CONTRACT_ORIGINAL.json': B1_DIR / 'r3_inputs/QUALIFICATION_CONTRACT_ORIGINAL.json',
             'b1/tests_full_lifecycle.py': B1_DIR / 'derived/tests_full_lifecycle.py'}


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
                  'scenarios': {'R42_' + k: v for k, v in SCENARIOS.items()}, 'revision': REV, 'e2e': False,
                  'b1': {'r3_archive': 'b1/R3_RUNTIME_ORIGINAL_ARCHIVE.zip',
                         'r3_archive_sha256': '2379512BD32CA751E0636EA4186F097035542F851CC51019817DDB5FFC4480E4',
                         'contract': 'b1/QUALIFICATION_CONTRACT_ORIGINAL.json',
                         'contract_sha256': '9AF1C840C1AE519BBD1A36C9C9CA7C2A91E0879D4AE6CEC049A11E2FB1FEF944',
                         'parent_sha256': 'EE30AA9325EE79A1F5FF4876DF72EC0A596AC351E9708447337841E9B43E592D',
                         'derived': 'b1/tests_full_lifecycle.py',
                         'derived_sha256': sha((B1_DIR / 'derived/tests_full_lifecycle.py').read_bytes()),
                         'microprobes': 'qual/R43_B1A_MICROPROBES.py',
                         'microprobes_sha256': sha((source / 'qual/R43_B1A_MICROPROBES.py').read_bytes()),
                         'portable': 106, 'native_only': 20,
                         'predicted_b1b': ['tests_delta.InstallerAndLauncherTests.test_native_ps51_extract_readback_and_collision_preserved',
                                           'tests_delta.InstallerAndLauncherTests.test_file_hash_mismatch_preserves_partial_no_deployment']}})
    qmembers = [('qual/QUAL_DRIVER.py', (source / 'qual/QUAL_DRIVER.py').read_bytes()),
                ('qual/R42_MULTIWORK_E2E.py', (source / 'qual/R42_MULTIWORK_E2E.py').read_bytes()),
                ('qual/R43_B1_RUNNER.py', (source / 'qual/R43_B1_RUNNER.py').read_bytes()),
                ('qual/R43_B1A_MICROPROBES.py', (source / 'qual/R43_B1A_MICROPROBES.py').read_bytes()),
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
    ps = (tpl.replace('@@ZIP_NAME@@', QUAL_NAME).replace('@@ZIP_SHA@@', sha(qual_raw))
             .replace('@@ZIP_BYTES@@', str(len(qual_raw))).replace('@@QUAL_MANIFEST_SHA@@', sha(qmanifest))
             .replace('@@REV@@', REV).replace('@@BOOTSTRAP@@', BOOTSTRAP).replace('@@ZIP_PATTERN@@', ZIP_PATTERN))
    assert '@@' not in ps
    ps_raw = ps.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii')
    (out / BOOTSTRAP).write_bytes(ps_raw)
    # 6. External witness.
    witness = canon({'schema': 'EXTERNAL_WITNESS_TICKSTORE_CDT15_QUAL_V002', 'revision': REV, 'role': 'ENGINEER_ONLY',
                     'qual_zip': QUAL_NAME, 'qual_zip_sha256': sha(qual_raw), 'qual_zip_bytes': len(qual_raw),
                     'qual_manifest_sha256': sha(qmanifest), 'bootstrap': BOOTSTRAP,
                     'bootstrap_sha256': sha(ps_raw), 'bootstrap_bytes': len(ps_raw),
                     'final_package': FINAL_NAME, 'final_package_sha256': sha(final_raw),
                     'final_package_manifest_sha256': sha(pmanifest),
                     'runtime_code_manifest_sha256': runtime_sha,
                     'source_manifest_sha256': sha((source / 'SOURCE_MANIFEST.json').read_bytes()),
                     'policy': POLICY, **BASELINE,
                     'expected_tests': {k: v['expected'] for k, v in suites.items()},
                     'scripts': sorted(SCRIPTS), 'scenarios': sorted(SCENARIOS),
                     'invocation': 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                                   '"C:\\Users\\silvi\\OneDrive\\Downloads\\' + BOOTSTRAP + '"',
                     'production_modified': False, 'full_started': False, 'b06_formal_audit': False,
                     'G4': 'INCOMPLETE', 'G5': 'NOT_PROVEN', 'B06': 'NOT_STARTED'})
    (out / QUAL_WITNESS).write_bytes(witness)
    for name in (QUAL_NAME, BOOTSTRAP, QUAL_WITNESS, FINAL_NAME, FINAL_WITNESS):
        print('%s %s %d' % (sha((out / name).read_bytes()), name, (out / name).stat().st_size))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
