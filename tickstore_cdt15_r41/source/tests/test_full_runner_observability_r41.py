"""R41: transparent ETA d.h.m.s, progress bar, heartbeat/loop watchdog, monitor, run log."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'candidate/control'))
sys.path.insert(0, str(R / 'candidate/full'))
import FULL_OBSERVABILITY as obs  # noqa: E402
import FULL_RUNNER as runner  # noqa: E402


def canon(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':')) + '\n').encode()


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


class Dhms(unittest.TestCase):
    def test_01_format(self):
        self.assertEqual(obs.dhms(0), '0.00.00.00')
        self.assertEqual(obs.dhms(90061), '1.01.01.01')
        self.assertEqual(obs.dhms(59.2), '0.00.01.00')  # never rounds remaining time down to zero

    def test_02_bar_never_full_before_completion(self):
        self.assertEqual(obs.bar(100.0, 10), '[##########]')
        self.assertEqual(obs.bar(99.999, 10), '[#########-]')
        self.assertEqual(obs.bar(None, 4), '[????]')

    def test_03_heartbeat_sample_has_human_eta(self):
        hb = obs.Heartbeat(Path('x'), lambda p, s: None, {'run_id': 'R'}, interval=1)
        hb.started -= 100
        hb.update(phase='PIPELINE', total_rows=1000, committed_rows=250)
        s = hb.sample()
        self.assertRegex(s['eta_dhms'], r'^0\.00\.0[45]\.\d\d$')
        self.assertEqual(s['progress_bar'].count('#'), 8)
        hb.update(phase='FINAL_RECONCILIATION', committed_rows=1000)
        self.assertEqual(hb.sample()['eta_dhms'], 'UNKNOWN')  # no fake zero ETA after rows


class MonitorVerdicts(unittest.TestCase):
    def item(self, **kw):
        now = time.time_ns()
        base = dict(run_id='R', status='RUNNING', phase='PIPELINE', observed_unix_ns=now,
                    loop_tick_unix_ns=now, committed_percent=12.5, eta_dhms='0.01.00.00')
        base.update(kw)
        return base

    def test_10_ok(self):
        line, verdict = runner.monitor_line(self.item(), time.time_ns())
        self.assertEqual(verdict, 'OK'); self.assertIn('ETA=0.01.00.00', line); self.assertIn('PCT= 12.500%', line)

    def test_11_stale_heartbeat(self):
        old = time.time_ns() - 60 * 10**9
        self.assertEqual(runner.monitor_line(self.item(observed_unix_ns=old), time.time_ns())[1], 'HEARTBEAT_STALE')

    def test_12_main_loop_stall(self):
        old = time.time_ns() - 700 * 10**9
        self.assertEqual(runner.monitor_line(self.item(loop_tick_unix_ns=old), time.time_ns())[1], 'MAIN_LOOP_STALL')

    def test_13_terminal_status_is_not_stale(self):
        old = time.time_ns() - 3600 * 10**9
        self.assertEqual(runner.monitor_line(self.item(status='SAFE_STOP', observed_unix_ns=old),
                                             time.time_ns())[1], 'OK')


class MonitorEndToEnd(unittest.TestCase):
    def test_20_monitor_reads_hash_bound_instance_and_stops_on_terminal(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            scratch = t / 'scratch'; hb_dir = scratch / 'RUN_INSTANCES' / 'RUNX'; hb_dir.mkdir(parents=True)
            instance = {'schema': 'TICKSTORE_FULL_INSTANCE_V001', 'run_id': 'RUNX',
                        'bindings': {'scratch_root': str(scratch)}, 'state_path': str(t / 'ctl/state/STATE.json')}
            ip = t / 'INSTANCE.json'; ip.write_bytes(canon(instance))
            chain = {'schema': 'TICKSTORE_EXECUTION_CHAIN_V001', 'instance_path': str(ip),
                     'instance_sha256': h(canon(instance))}
            cp = t / 'CHAIN.json'; cp.write_bytes(canon(chain))
            (hb_dir / 'HEARTBEAT_A.json').write_bytes(canon(dict(
                run_id='RUNX', status='SAFE_STOP', phase='STOPPED', observed_unix_ns=time.time_ns(),
                committed_percent=40.0, eta_dhms='UNKNOWN')))
            (hb_dir / 'HEARTBEAT_FOREIGN.json').write_bytes(canon(dict(
                run_id='OTHER', status='RUNNING', observed_unix_ns=time.time_ns() + 10**12)))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = runner.main(['--stage', 'Monitor', '--chain-file', str(cp),
                                    '--chain-sha256', h(canon(chain)), '--b06-sha256', 'B' * 64])
            self.assertEqual(code, 0)
            self.assertIn('MONITOR_FINAL_STATUS=SAFE_STOP', out.getvalue())
            self.assertIn('AUTHORITY=NONE READ_ONLY=YES', out.getvalue())
            self.assertNotIn('OTHER', out.getvalue())

    def test_21_monitor_rejects_wrong_chain_digest(self):
        with tempfile.TemporaryDirectory() as t:
            cp = Path(t) / 'CHAIN.json'; cp.write_bytes(b'{}\n')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = runner.main(['--stage', 'Monitor', '--chain-file', str(cp),
                                    '--chain-sha256', 'A' * 64, '--b06-sha256', 'B' * 64])
            self.assertEqual(code, 2)
            self.assertIn('FULL_RUNNER_BLOCKED=', out.getvalue())

    def test_22_log_file_mirrors_console(self):
        with tempfile.TemporaryDirectory() as t:
            log = Path(t) / 'RUN_LOG.txt'
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = runner.main(['--stage', 'Monitor', '--chain-file', str(Path(t) / 'missing.json'),
                                    '--chain-sha256', 'A' * 64, '--b06-sha256', 'B' * 64, '--log-file', str(log)])
            self.assertEqual(code, 2)
            self.assertIn('FULL_RUNNER_BLOCKED=', log.read_text(encoding='utf-8'))
            self.assertIn('FULL_RUNNER_BLOCKED=', out.getvalue())


class LauncherContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (R / 'candidate/control/RUN_TICKSTORE_FULL.ps1').read_text(encoding='utf-8')

    def test_30_stop_is_elevated_monitor_is_not(self):
        self.assertIn("$Stage -notin @('Check','Monitor','D4Close')", self.text)

    def test_31_elevated_window_visible(self):
        self.assertIn('-WindowStyle Normal', self.text)
        self.assertNotIn('-WindowStyle Hidden', self.text)

    def test_32_fixed_absolute_log_root_never_cwd(self):
        self.assertIn("$LogRoot='C:\\Users\\silvi\\OneDrive\\Downloads\\TICKSTORE_RUNS'", self.text)
        for token in ('Get-Location', '$PWD', 'Set-Location', '.\\'):
            self.assertNotIn(token, self.text)
        self.assertIn("'--log-file',(Join-Path $script:RunDir 'RUN_LOG.txt')", self.text)

    def test_33_elevated_child_only_accepts_run_owned_dir(self):
        self.assertIn("'RUN_DIR_NOT_RUN_OWNED'", self.text)
        self.assertIn("'UAC_CODE_DRIFT'", self.text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
