"""R45B adversarial evidence: the B07 tests must reject the R45 parent and two semantic regressions.

Usage: python3 -I -B b07_mutation_check.py <source_dir> <parent_producer.py> <out_log>
Every mutant runs on a private copy of the source tree; the source tree itself is never modified.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PRODUCER = 'candidate/control/B07_TECHNICAL_PRODUCER.py'
TEST = 'tests/test_b07_technical_producer.py'
MUTANTS = {
    'R45_PARENT_ACCEPTS_CALLER_CAPTURE_DICT': None,  # replaced by the parent bytes
    'ORDER_FLAG_HARDCODED_TRUE': ("'produced_after_independent_b06': b06_verified,",
                                  "'produced_after_independent_b06': True,"),
    'PROVENANCE_BYPASS_FORGED_IDENTITY': (
        "    capture, read_mode, pf = verify_policy(policy_root, policy_reconciliation, policy_reconciliation_sha256, now=now)\n",
        "    capture, read_mode, pf = ({'master_sha256': '1' * 64, 'head_sha256': '2' * 64, 'reconciliation_sha256': '3' * 64},"
        " 'WIN32_PROTECTED_HANDLES', [])\n"),
}


def run(tree):
    r = subprocess.run([sys.executable, '-B', str(tree / TEST)], capture_output=True, text=True, timeout=900)
    tail = [l for l in r.stderr.splitlines() if l.startswith(('FAIL:', 'ERROR:', 'Ran ', 'OK', 'FAILED'))]
    return r.returncode, tail


def main(source, parent, out):
    source, lines, ok = Path(source), [], True
    with tempfile.TemporaryDirectory() as t:
        base = Path(t) / 'clean'
        shutil.copytree(source, base, ignore=shutil.ignore_patterns('__pycache__'))
        rc, tail = run(base)
        lines += ['BASELINE rc=%d' % rc] + tail
        ok &= rc == 0
        for name, edit in MUTANTS.items():
            tree = Path(t) / name
            shutil.copytree(base, tree, ignore=shutil.ignore_patterns('__pycache__'))
            p = tree / PRODUCER
            if edit is None:
                p.write_bytes(Path(parent).read_bytes())
            else:
                s = p.read_text(encoding='utf-8')
                assert s.count(edit[0]) == 1, name
                p.write_text(s.replace(edit[0], edit[1]), encoding='utf-8')
            rc, tail = run(tree)
            killed = rc != 0
            ok &= killed
            lines += ['MUTANT %s rc=%d %s' % (name, rc, 'KILLED' if killed else 'SURVIVED')] + tail
    lines.append('B07_MUTATION_CHECK=' + ('PASS' if ok else 'FAIL'))
    Path(out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:4]))
