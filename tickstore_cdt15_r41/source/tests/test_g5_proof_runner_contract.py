"""Packaged G5 proof runners emit exactly what the hardened consumer requires (and nothing offline passes)."""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'tests'))
import g5_native_fixture as FX  # noqa: E402

RUNNERS = R / 'candidate/g5proof/G5_PROOF_RUNNERS.py'
SCENARIOS = R / 'candidate/g5proof/G5_MULTIWORK_SCENARIOS.py'


def check_keys(path, function):
    """Keys of the dict literal assigned to `checks` inside `function`."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'checks' for t in sub.targets)
                        and isinstance(sub.value, ast.Dict)):
                    return {k.value for k in sub.value.keys}
    return None


def runner_ns():
    ns = {'__name__': 'g5_runner_static', '__file__': str(RUNNERS)}
    exec(compile(RUNNERS.read_bytes(), str(RUNNERS), 'exec'), ns)
    return ns


class RunnerConsumerContract(unittest.TestCase):
    def setUp(self):
        self.q = FX.load_consumer()
        self.r = runner_ns()

    def test_01_kinds_and_functions_match_consumer(self):
        for name, spec in self.q['TYPED_PROOFS'].items():
            if spec['function'] is None:
                self.assertNotIn(name, self.r['KINDS'], 'no runner may claim the physical power-loss proof')
                continue
            self.assertEqual(self.r['KINDS'][name], (spec['kind'], spec['function']), name)
        self.assertEqual(self.r['KINDS']['POWERLOSS_EMULATED'][0], self.q['POWERLOSS_EMULATED_KIND'])
        self.assertEqual(self.r['RECEIPT_SCHEMA'], self.q['PROOF_RECEIPT_SCHEMA'])
        self.assertEqual('g5proof/G5_PROOF_RUNNERS.py', self.q['PROOF_RUNNER'])

    def test_02_check_names_match_consumer_exactly(self):
        where = {'proof_safe_stop_resume': (SCENARIOS, 'safe_stop_resume_row_group')}
        for name, spec in self.q['TYPED_PROOFS'].items():
            if spec['function'] is None:
                continue
            path, fn = where.get(spec['function'], (RUNNERS, spec['function']))
            self.assertEqual(check_keys(path, fn), set(spec['checks']), name)

    def test_03_offline_receipt_never_satisfies_the_consumer(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            r = subprocess.run([sys.executable, '-B', str(RUNNERS), '--proof', 'STAGE_B_FULL_CHAIN_NATIVE', '--work',
                                str(t / 'W'), '--evidence', str(t / 'EV'), '--run-id', 'RUNX', '--final-zip-sha256',
                                'A' * 64, '--code-manifest-sha256', 'B' * 64, '--offline'],
                               capture_output=True, text=True, timeout=900)
            self.assertNotEqual(r.returncode, 0)
            body = (t / 'EV/PROOFS/STAGE_B_FULL_CHAIN_NATIVE/PROOF_RECEIPT.json').read_bytes()
            rec = json.loads(body)
            self.assertEqual(rec['status'], 'OFFLINE_HARNESS_ONLY'); self.assertFalse(rec['native_windows'])
            rfiles = {a['member']: (t / 'EV/PROOFS/STAGE_B_FULL_CHAIN_NATIVE' / a['member'].split('/', 3)[3]).read_bytes()
                      for a in rec['artifacts']}
            idx = {'g5proof/G5_PROOF_RUNNERS.py': rec['runner']['sha256']}
            f = self.q['proof_receipt_findings']('STAGE_B_FULL_CHAIN_NATIVE', rec,
                                                 'EVIDENCE/PROOFS/STAGE_B_FULL_CHAIN_NATIVE/PROOF_RECEIPT.json',
                                                 rfiles, idx, 'A' * 64, 'B' * 64, 'RUNX')
            self.assertIn('STAGE_B_FULL_CHAIN_NATIVE:RECEIPT_STATUS:OFFLINE_HARNESS_ONLY', f)
            self.assertIn('STAGE_B_FULL_CHAIN_NATIVE:RECEIPT_NOT_NATIVE', f)
            self.assertNotIn('STAGE_B_FULL_CHAIN_NATIVE:RECEIPT_RUNNER_NOT_PACKAGED', f)
            self.assertNotIn('STAGE_B_FULL_CHAIN_NATIVE:RECEIPT_ARTIFACT', ' '.join(f))


if __name__ == '__main__':
    unittest.main(verbosity=2)
