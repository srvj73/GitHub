"""R45 completeness: operator entry points (MENU, FULL_RUNNER D4 dispatch, continuation retry).

G4  MENU offers Monitor and passes the CURRENT origin policy reconciliation (path + separately
    typed SHA-256) to every effectful stage; malformed or missing input blocks before launching.
G7  Ctrl+C while the D4 wrapper runs never kills the wrapper from the parent (the wrapper owns
    the cooperative SAFE_STOP); the parent handler is restored afterwards.
G8  An interrupted continuation node is recorded FAIL and is retryable by re-running the same
    stage (journal/state reconciliation), never silently advanced.
"""
import ast
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = R / 'candidate'
sys.path.insert(0, str(C / 'control'))
import FULL_RUNNER as runner  # noqa: E402

MENU_SRC = (C / 'menu/MENU.py').read_text(encoding='utf-8')
LAUNCHER_SRC = (C / 'control/RUN_TICKSTORE_FULL.ps1').read_text(encoding='utf-8')


def menu_namespace(answers, deploy, calls):
    """Execute only the TICKSTORE entry of MENU.py with controlled collaborators."""
    tree = ast.parse(MENU_SRC)
    keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == 'rodar_tickstore_full')
            or (isinstance(n, ast.Assign) and any(getattr(t, 'id', '').startswith('TICKSTORE_') for t in n.targets))]
    feed = iter(answers)
    ns = {'__file__': str(C / 'menu/MENU.py'), 'Path': Path, 'os': os, 're': re, 'hashlib': hashlib, 'input': lambda prompt='': next(feed),
          '_tickstore_committed_deployment': lambda receipt, menu: deploy,
          '_reject_deployment_reparse': lambda p: None, 'rodar': lambda cmd: calls.append(cmd) or 0}
    exec(compile(ast.fix_missing_locations(ast.Module(body=keep, type_ignores=[])), str(C / 'menu/MENU.py'), 'exec'), ns)
    return ns


class MenuEntry(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.t = Path(t.name)
        self.local = self.t / 'LOCALAPPDATA'
        pkg = 'A' * 64
        self.release = self.local / 'TICKSTORE/Candidates' / pkg
        launcher = self.release / 'implementation_v001/candidate/control/RUN_TICKSTORE_FULL.ps1'
        launcher.parent.mkdir(parents=True); launcher.write_bytes(b'# launcher\r\n')
        self.deploy = {'schema': 'TICKSTORE_DEPLOYMENT_V001', 'installation_root': str(self.release), 'package_sha256': pkg,
                       'launcher_sha256': hashlib.sha256(launcher.read_bytes()).hexdigest().upper()}
        self.env = dict(os.environ, LOCALAPPDATA=str(self.local), SystemRoot=str(self.t / 'Windows'))

    def run_menu(self, answers):
        calls = []
        ns = menu_namespace(answers, self.deploy, calls)
        old = dict(os.environ)
        os.environ.update(self.env)
        try:
            rc = ns['rodar_tickstore_full'](self.t)
        finally:
            os.environ.clear(); os.environ.update(old)
        return rc, calls, ns

    def test_01_stage_sets_match_the_launcher(self):
        ns = menu_namespace([], self.deploy, [])
        validate = re.search(r"\[ValidateSet\(([^)]*)\)\]\[string\]\$Stage", LAUNCHER_SRC).group(1)
        launcher_stages = tuple(x.strip().strip("'") for x in validate.split(','))
        self.assertEqual(set(ns['TICKSTORE_STAGES']), set(launcher_stages))
        self.assertEqual(set(ns['TICKSTORE_POLICY_STAGES']), set(runner.REQUIRED_PREFIX) - {'D4Close', 'Stop'} | {'FULL_READMIT'})

    def test_02_effectful_stage_passes_reconciliation_and_digest(self):
        sha = 'C' * 64
        for stage in ('D4', 'D5', 'CANARY', 'FULL_PREP', 'FULL_ADMIT', 'FULL_READMIT', 'FULL'):
            answers = [stage, r'C:\chain.json', 'A' * 64, 'B' * 64, r'C:\REC.json', sha.lower(), 'n', 'n']
            rc, calls, _ = self.run_menu(answers)
            self.assertEqual(rc, 0, stage)
            cmd = calls[0]
            i = cmd.index('-PolicyReconciliation')
            self.assertEqual(cmd[i + 1:i + 4], [r'C:\REC.json', '-PolicyReconciliationSha256', sha], stage)

    def test_03_missing_or_malformed_reconciliation_blocks_before_launch(self):
        for rec, sha in (('', 'C' * 64), (r'C:\REC.json', 'XYZ'), (r'C:\REC.json', '')):
            rc, calls, _ = self.run_menu(['D4', r'C:\chain.json', 'A' * 64, 'B' * 64, rec, sha])
            self.assertEqual(rc, 2); self.assertEqual(calls, [])

    def test_04_read_only_stages_need_no_reconciliation(self):
        for stage in ('Check', 'Monitor', 'D4Close', 'Stop'):
            rc, calls, _ = self.run_menu([stage, r'C:\chain.json', 'A' * 64, 'B' * 64])
            self.assertEqual(rc, 0, stage)
            self.assertNotIn('-PolicyReconciliation', calls[0]); self.assertIn(stage, calls[0])

    def test_05_launcher_drift_blocks(self):
        self.deploy['launcher_sha256'] = 'F' * 64
        rc, calls, _ = self.run_menu(['Check'])
        self.assertEqual(rc, 2); self.assertEqual(calls, [])


class D4Dispatch(unittest.TestCase):
    def test_06_parent_ignores_ctrl_c_while_wrapper_runs_and_restores(self):
        seen = {}

        def fake_call(cmd):
            seen['handler'] = signal.getsignal(signal.SIGINT)
            return 7
        real = runner.subprocess.call
        runner.subprocess.call = fake_call
        try:
            self.assertEqual(runner.run_wrapper_cooperatively(['x']), 7)
        finally:
            runner.subprocess.call = real
        self.assertIs(seen['handler'], signal.SIG_IGN)
        self.assertIs(signal.getsignal(signal.SIGINT), signal.default_int_handler)

    def test_07_real_child_survives_ctrl_c_and_its_code_is_returned(self):
        child = [sys.executable, '-c', 'import time,sys; time.sleep(1.5); sys.exit(5)']
        timer = threading.Timer(0.4, signal.raise_signal, (signal.SIGINT,))
        timer.start()
        try:
            t0 = time.monotonic()
            self.assertEqual(runner.run_wrapper_cooperatively(child), 5)
            self.assertGreaterEqual(time.monotonic() - t0, 1.2)
        finally:
            timer.cancel()
        self.assertIs(signal.getsignal(signal.SIGINT), signal.default_int_handler)

    def test_08_d4_dispatch_uses_the_cooperative_wait(self):
        src = (C / 'control/FULL_RUNNER.py').read_text(encoding='utf-8')
        self.assertIn('code = run_wrapper_cooperatively(command)', src)
        self.assertEqual(len(re.findall(r'^\s+return subprocess\.call\(command\)$', src, re.M)), 1)
        self.assertNotIn('code = subprocess.call(', src)


class WrapperElevation(unittest.TestCase):
    """G6: the D4 wrapper never self-elevates; a non-elevated ExecuteD4 blocks before any effect."""
    SRC = (C / 'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1').read_text(encoding='utf-8-sig')

    def test_10_elevation_checked_before_admission_boundary(self):
        early = self.SRC.index('BLOCKED|ELEVATION_REQUIRED_USE_RUN_TICKSTORE_FULL_PS1')
        self.assertLess(early, self.SRC.index('Invoke-FirstAdmissionBoundary}'))
        self.assertLess(early, self.SRC.index('function Invoke-FirstAdmissionBoundary'))
        self.assertNotIn("' -ExecuteD4 -ElevatedChild", self.SRC)  # the broken D4 self-relaunch is gone
        self.assertNotIn('ELEVATED_CHILD_RESULT_MISSING', self.SRC)

    def test_11_binding_pins_the_current_wrapper(self):
        b = json.loads((C / 'control/FIRST_ADMISSION_BINDING.json').read_bytes())
        self.assertEqual(b['wrapper_sha256'],
                         hashlib.sha256((C / 'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1').read_bytes()).hexdigest().upper())


class ContinuationRetry(unittest.TestCase):
    def journal(self, records):
        import D4_FIRST_ADMISSION_PREP as prep
        lines, prev = [], ''
        for r in records:
            line = json.dumps(dict(r, prev_line_sha256=prev), sort_keys=True).encode('utf-8')
            lines.append(line); prev = prep.sha(line)
        return b'\n'.join(lines) + b'\n'

    def test_09_interrupted_node_is_fail_and_retryable(self):
        import FULL_STAGE_CONTINUATION as cont
        boundary = cont.StageBoundary('CANARY')
        state = {'schema': 'TICKSTORE_ORCH_STATE_V001', 'status': 'FAIL', 'next_node': 'D7',
                 'completed': ['D4', 'D5', 'D6'], 'canary_scratch_cert': 'X'}
        raw = self.journal([{'node': 'D6', 'phase': 'STARTED', 'run_id': 'R1'},
                            {'node': 'D6', 'phase': 'FINISHED', 'status': 'PASS', 'run_id': 'R1'},
                            {'node': 'D7', 'phase': 'STARTED', 'run_id': 'R1'},
                            {'node': 'D7', 'phase': 'FINISHED', 'status': 'FAIL', 'run_id': 'R1',
                             'error': 'KeyboardInterrupt:'}])
        boundary.validate(state)
        cont.validate_stage_history(raw, boundary, state)  # accepted: the stage can be re-run from D7
        unclosed = self.journal([{'node': 'D6', 'phase': 'STARTED', 'run_id': 'R1'},
                                 {'node': 'D6', 'phase': 'FINISHED', 'status': 'PASS', 'run_id': 'R1'},
                                 {'node': 'D7', 'phase': 'STARTED', 'run_id': 'R1'}])
        with self.assertRaisesRegex(RuntimeError, 'CONTINUATION_UNCLOSED_STARTED'):
            cont.validate_stage_history(unclosed, boundary, state)
        advanced = dict(state, completed=state['completed'] + ['D7'], next_node='D8', status='PASS')
        with self.assertRaisesRegex(RuntimeError, 'CONTINUATION_JOURNAL_STATE_RECONCILIATION'):
            cont.validate_stage_history(raw, boundary, advanced)


if __name__ == '__main__':
    unittest.main(verbosity=2)
