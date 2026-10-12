#!/usr/bin/env python3
# coding: utf-8
"""Static, non-executing review of the recovered R4R9/C2 sources (delta V001).

Never imports or runs the recovered code. Reads bytes, compiles them (compile() only, no
bytecode written), extracts embedded payload literals via ast.literal_eval and scans for
patterns relevant to the captured policy. Output: JSON on stdout.

Usage: python -I -B c2_recovered_static_review.py <delta_root> <inner_extract_root> <r4r8_zip>
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

H = lambda b: hashlib.sha256(b).hexdigest().upper()

# Identities quoted by EVIDENCE_ORIGINAL/Texto colado(20260922-201333).txt (R4R9 local tests wrapper L11-L17).
R4R9_MEMBERS = {
    'perseu_parallel_auto.py': '28DF85A4BF87B859230C931042C493CD6B4E57FE8698135C3D771C56E466E68C',
    'perseu_r4r9_accel.py': '042FA9CB7DB2DE26BD64F82B41B2A1977B05C65509E2038239BDC972E766F2E5',
    'test_parallel_auto.py': '5D3DB8FD5EB532D23DB7F9FF9FCA7A4041447EBE6E66AC674D29CBDB7C74AB7E',
    'test_r4r9_gate.py': 'B8E1417ED0806AA03B3C3C89FACD3A0CDDC856971E76B1152DCD9312F553E8B8',
    'perseu_exploratorio.py': 'A331F308182766C299B067BE2035EB071E01019C28A6C20DD6DF09B1AB92607F',
    'test_perseu_exploratorio.py': '7CC5A79C81B481847AEBA52D4441293305079F766D52CE2D04DCAEACE9C34A80',
    'BASELINE_R4R8/perseu_parallel_auto.py': '8EE1A1B17771ECEB536A233E8319CB574F61F86472F07C2C5229ADC93E0641FB',
}

PATTERNS = {
    'POWERSHELL_INLINE_COMMAND': r'["\']-Command["\']',
    'PY_LAUNCHER_PY_EXE': r'["\']py(\.exe)?["\']\s*,',
    'PYTHON_DASH_C': r'["\']-c["\']\s*,',
    'UNCONDITIONAL_WRITE_TEXT': r'\.write_text\(',
    'EXIT_CODE_10_OR_30': r'SystemExit\((10|30)\)|return 10\b|return 30\b',
    'SHUTIL_RMTREE': r'shutil\.rmtree\(',
    'SHUTIL_MOVE': r'shutil\.move\(',
    'SQLITE_READ_ONLY_URI': r'mode=ro',
    'HARDCODED_D_PERSEURUNS': r'D:\\\\?PerseuRuns',
}


def literal(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def review_py(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    compile(raw, str(path), 'exec', dont_inherit=True)
    tree = ast.parse(text)
    imports = sorted({(n.module if isinstance(n, ast.ImportFrom) else a.name).split('.')[0]
                      for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                      for a in (n.names if isinstance(n, ast.Import) else [n])
                      if (n.module if isinstance(n, ast.ImportFrom) else a.name)})
    out = {'sha256': H(raw), 'bytes': len(raw), 'compile': 'PASS', 'bom': raw.startswith(b'\xef\xbb\xbf'),
           'crlf': b'\r\n' in raw, 'imports': imports,
           'patterns': {k: len(re.findall(p, text)) for k, p in PATTERNS.items()}}
    for name in ('HOTFIX_SOURCE', 'SHIM_TEXT'):
        emb = literal(tree, name)
        if isinstance(emb, str):
            compile(emb, f'{path.name}:{name}', 'exec', dont_inherit=True)
            out['embedded_' + name] = {
                'compile': 'PASS', 'chars': len(emb), 'has_cr': '\r' in emb,
                'sha256_utf8_lf': H(emb.encode('utf-8')),
                'sha256_utf8_crlf': H(emb.replace('\n', '\r\n').encode('utf-8')),
                'imports_local': sorted(set(re.findall(r'^(?:import|from)\s+(perseu_\w+)', emb, re.M))),
                'loads': sorted(set(re.findall(r'["\'](perseu_\w+\.py)["\']', emb)))}
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                v = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
            if isinstance(v, str) and re.fullmatch('[0-9A-F]{64}', v):
                consts[node.targets[0].id] = v
    out['sha_constants'] = consts
    return out


def main(argv):
    delta, inner, r4r8 = Path(argv[1]), Path(argv[2]), Path(argv[3])
    report = {'scope': 'STATIC_ONLY_NO_EXECUTION_OF_RECOVERED_CODE', 'python': sys.version.split()[0], 'files': {}}
    for p in sorted((delta / 'RECOVERED_ORIGINALS').glob('*.py')) + sorted(inner.glob('*/*/*.py')):
        report['files'][p.name] = review_py(p)
    f = report['files']
    r1 = f['PREP_PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R1_V001.py']['embedded_HOTFIX_SOURCE']['sha256_utf8_lf']
    r2 = f['PREP_PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R2_V002.py']
    r3 = f['PREP_PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R3_V003.py']
    report['hotfix_chain'] = {
        'R1_derived': r1, 'R1_expected_by_R2': r2['sha_constants'].get('EXPECTED_R1_HOTFIX'),
        'R2_derived': r2['embedded_HOTFIX_SOURCE']['sha256_utf8_lf'],
        'R2_expected_by_R3': r3['sha_constants'].get('EXPECTED_R2_HOTFIX'),
        'R3_derived': r3['embedded_HOTFIX_SOURCE']['sha256_utf8_lf'],
        'derivation_method': 'HOTFIX_SOURCE.encode(utf-8) written by write_bytes (exact bytes)',
    }
    report['hotfix_chain']['cross_validation'] = (
        'PASS_2_OF_2' if report['hotfix_chain']['R1_derived'] == report['hotfix_chain']['R1_expected_by_R2']
        and report['hotfix_chain']['R2_derived'] == report['hotfix_chain']['R2_expected_by_R3'] else 'FAIL')
    zf = zipfile.ZipFile(r4r8)
    by_sha = {}
    for i in zf.infolist():
        if not i.is_dir():
            by_sha.setdefault(H(zf.read(i)), []).append(i.filename.split('/', 1)[1])
    report['r4r9_members_recoverable_from_r4r8_by_sha_equality'] = {
        k: {'sha256': v, 'r4r8_members_with_equal_bytes': by_sha.get(v, [])} for k, v in R4R9_MEMBERS.items()}
    report['r4r8_zip'] = {'sha256': H(r4r8.read_bytes()), 'infolist_entries': len(zf.infolist()),
                          'directory_entries': sum(i.is_dir() for i in zf.infolist()),
                          'file_members': sum(not i.is_dir() for i in zf.infolist())}
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0 if report['hotfix_chain']['cross_validation'] == 'PASS_2_OF_2' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
