"""R47 POWERLOSS-SCRATCH-01: product resume after scratch crash debris, end to end on the packaged engine.

Found by the R47 offline campaign (S18, emulated cut under CPU contention): a cut inside the scratch
journal's atomic write left `<day>.journal.json.partial`, and a cut inside the day initialisation left a
partial without journal; the MULTIWORK resume then blocked (ATOMIC_PARTIAL_ALREADY_EXISTS /
SCRATCH_PARTIAL_JOURNAL_PAIR_MISMATCH).  This test plants both debris kinds deterministically after a
cooperative SAFE_STOP and requires a byte-identical result to an uninterrupted control build.
The debris is planted, never produced by a power cut: this is not physical power-loss evidence.
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

CAND = Path(__file__).resolve().parents[1] / 'candidate'


def load_scenarios():
    import importlib.util
    spec = importlib.util.spec_from_file_location('r47_g5_scenarios', CAND / 'g5proof/G5_MULTIWORK_SCENARIOS.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class ScratchPowerlossDebrisEndToEnd(unittest.TestCase):
    def test_resume_discards_debris_and_matches_uninterrupted_control(self):
        M = load_scenarios()
        core, mw, r9 = M.load(CAND)
        offline = os.name != 'nt'
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            if offline:
                os.environ['G5_OFFLINE_STOP_DIR'] = str(t / 'OFFLINE_STOP'); (t / 'OFFLINE_STOP').mkdir()
            control = M.make_fixture(r9, t / 'CONTROL', M.ROW_GROUP_PLAN)
            rc = M.run_engine(core, mw, r9, control, 'R47CTL' + os.urandom(4).hex().upper(), '2', offline=offline)
            self.assertEqual(rc['outcome'], 'PASS', rc.get('error'))
            want = M.containers(control['dest'])
            fx = M.make_fixture(r9, t / 'FX', M.ROW_GROUP_PLAN)
            run_id = 'R47DEB' + os.urandom(4).hex().upper()
            trig = {}

            def watch():
                end = time.monotonic() + 900
                while time.monotonic() < end and not trig.get('done'):
                    path, j = M.scratch_journal(fx['scratch'], M.BIG_DAY)
                    if j and j.get('state') == 'BUILDING' and len(j.get('completed_groups', [])) >= 1:
                        trig['detail'] = M.request_stop_from_other_process(CAND, run_id, offline)
                        return
                    time.sleep(0.02)
            th = threading.Thread(target=watch, daemon=True); th.start()
            r1 = M.run_engine(core, mw, r9, fx, run_id, '1', offline=offline)
            trig['done'] = True; th.join(5)
            self.assertEqual(r1['outcome'], 'COOPERATIVE_SAFE_STOP', r1.get('error'))
            jpath, j = M.scratch_journal(fx['scratch'], M.BIG_DAY)
            self.assertEqual(j['state'], 'BUILDING')
            # W2: torn, uncommitted journal shadow next to the authoritative journal.
            shadow = jpath.with_suffix(jpath.suffix + '.partial')
            shadow.write_bytes(jpath.read_bytes()[:-7])
            # W1: a later day whose initialisation was cut after the partial and before its first journal.
            ns_root = jpath.parents[2]
            published = set(r1['commits'])
            later = [c for c in fx['days'] if c['date_key'] > M.BIG_DAY and c['date_key'] not in published
                     and not (ns_root / c['month_id'] / c['date_key']).exists()]
            self.assertTrue(later)
            c = later[0]
            d = ns_root / c['month_id'] / c['date_key']; d.mkdir(parents=True)
            (d / (c['date_key'] + '.pts2g.partial')).write_bytes(b'PTS2G prefix cut before first journal')
            (d / (c['date_key'] + '.journal.json.partial')).write_bytes(b'{"schema":')
            r2 = M.run_engine(core, mw, r9, fx, run_id, '2', offline=offline)
            self.assertEqual(r2['outcome'], 'PASS', r2.get('error'))
            self.assertTrue(r2['markers']['FINAL_READONLY_RECONCILE=PASS'])
            self.assertEqual(M.containers(fx['dest']), want)
            self.assertEqual(len(r2['commits']), len(fx['days']))
            # Worker stdout is not captured by the harness; the physical state is the evidence.
            self.assertFalse(shadow.exists())
            self.assertFalse((d / (c['date_key'] + '.journal.json.partial')).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
