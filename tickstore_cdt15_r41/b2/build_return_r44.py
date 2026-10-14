"""Deterministic origin return package for R44/B2 (sources, deltas, evidence, witnesses)."""
import hashlib
import json
import zipfile
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]
NAME = 'TICKSTORE_CDT15_R44_B2_RETORNO_ORIGEM_20261014.zip'
FIXED = (2026, 10, 14, 0, 0, 0)


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


members = {}
def add(rel, arc=None):
    p = TOP / rel
    if p.is_dir():
        for q in sorted(p.rglob('*')):
            if q.is_file() and '__pycache__' not in q.parts:
                members[(arc or rel) + '/' + q.relative_to(p).as_posix()] = q.read_bytes()
    else:
        members[arc or rel] = p.read_bytes()


add('b2/00_LEIA_RETORNO_R44_B2_ORIGEM.md', '00_LEIA_RETORNO_R44_B2_ORIGEM.md')
add('b2/evidence_r44', 'EVIDENCE')
add('BLOCKER_LEDGER.json')
add('b2/B2_REQUIREMENTS_MATRIX.json')
for rel in ('candidate/control/FULL_QUALIFICATION_CONTRACT.py', 'candidate/control/G5_EVIDENCE_BUILDER.py',
            'candidate/g5proof', 'tests/test_g5_evidence_builder.py', 'tests/g5_native_fixture.py',
            'tests/test_g5_proof_runner_contract.py', 'tests/fixtures/ORIGIN_B2_reproduce_adversarial_completeness.py',
            'qual/QUAL_DRIVER.py', 'qual/R44_B1_RUNNER.py', 'RUNTIME_CODE_MANIFEST.json', 'SOURCE_MANIFEST.json'):
    add('source/' + rel, 'R44_SOURCE/' + rel)
add('build/build_qual.py', 'R44_SOURCE/build/build_qual.py')
add('build/RUN_TICKSTORE_CDT15_QUAL.ps1.template', 'R44_SOURCE/build/RUN_TICKSTORE_CDT15_QUAL.ps1.template')
add('b1/derived', 'R44_SOURCE/b1/derived')
for f in ('WITNESS_TICKSTORE_CDT15_R44_QUAL_20261014.json', 'WITNESS_TICKSTORE_FULL_FINAL_CDT15_R44_20261014.json',
          'RUN_TICKSTORE_CDT15_R44_QUAL.ps1', 'TICKSTORE_FULL_FINAL_CDT15_R44_20261014.zip'):
    add('dist/' + f, 'R44_PACKAGE/' + f)
for d in ('b2c', 'b2d'):
    add(d, d.upper())
manifest = json.dumps({'schema': 'TICKSTORE_CDT15_R44_B2_RETURN_MANIFEST_V001', 'role': 'CANDIDATE_PRODUCER',
                       'gate_issued': False, 'production_modified': False,
                       'files': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n, b in sorted(members.items())]},
                      indent=1, sort_keys=True).encode() + b'\n'
out = TOP / 'dist' / NAME
if out.exists():
    out.unlink()
with zipfile.ZipFile(out, 'x', zipfile.ZIP_DEFLATED) as z:
    for n, b in [('MANIFEST_SHA256.json', manifest)] + sorted(members.items()):
        i = zipfile.ZipInfo(n, FIXED); i.compress_type = zipfile.ZIP_DEFLATED; i.external_attr = 0o100644 << 16
        z.writestr(i, b)
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    listed = json.loads(z.read('MANIFEST_SHA256.json'))['files']
    assert {f['path'] for f in listed} == set(z.namelist()) - {'MANIFEST_SHA256.json'}
    assert all(sha(z.read(f['path'])) == f['sha256'] for f in listed)
raw = out.read_bytes()
w = {'schema': 'EXTERNAL_WITNESS_TICKSTORE_CDT15_R44_B2_RETURN_V001', 'zip_name': NAME, 'zip_sha256': sha(raw),
     'zip_bytes': len(raw), 'members': len(listed) + 1, 'manifest_sha256': sha(manifest), 'role': 'CANDIDATE_PRODUCER',
     'gate_issued': False, 'production_modified': False,
     'result_return_to': 'ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 15'}
(TOP / 'dist' / ('WITNESS_' + NAME.replace('.zip', '.json'))).write_text(json.dumps(w, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(w, indent=1, ensure_ascii=False))
