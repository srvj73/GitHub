"""SOURCE_ONLY tests of the physical power-loss lab tooling (no execution, no hardware)."""
import hashlib
import json
import os
import shutil
import signal
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'powerloss_lab'))
import LAB_POWERLOSS as L  # noqa: E402


def h(b):
    return hashlib.sha256(b).hexdigest().upper()


class FakeEnv:
    def __init__(self):
        self.vols = {'C': {'serial': '11111111', 'filesystem': 'NTFS', 'label': 'OS'},
                     'X': {'serial': 'ABCDEF01', 'filesystem': 'NTFS', 'label': 'TICKSTORE_POWERLOSS_LAB'}}
        self.files = {'X:\\' + L.SENTINEL_NAME: L.SENTINEL_TEXT.encode()}
        self.logger = json.dumps({'schema': L.LOGGER_SCHEMA, 'outside_equipment_under_test': True,
                                  'records': ['cut_instant', 'restore_instant', 'round_id', 'supply_state']}).encode()
        self.auth = json.dumps({'schema': L.AUTH_SCHEMA, 'issuer': 'OWNER_USER',
                                'authorizes': 'PHYSICAL_POWER_INTERRUPTION_OF_SEPARATE_LAB_ONLY',
                                'lab_volume_serial': 'ABCDEF01', 'production_pc': False,
                                'valid_until_unix': 2_000_000_000}).encode()
        self.files['logger.json'] = self.logger; self.files['auth.json'] = self.auth
        self.pagefile = {'C'}

    def volumes(self): return self.vols
    def system_drive(self): return 'C'
    def pagefile_drives(self): return self.pagefile
    def read(self, p): return self.files[str(p)]
    def exists(self, p): return str(p) in self.files


class Preflight(unittest.TestCase):
    def run_pf(self, env, **kw):
        args = dict(volume='X', logger_path='logger.json', logger_sha=h(env.files['logger.json']),
                    auth_path='auth.json', auth_sha=h(env.files['auth.json']), env=env, now=1_800_000_000)
        args.update(kw)
        return L.preflight(**args)

    def blocked(self, needle, env, **kw):
        with self.assertRaisesRegex(L.LabBlocked, needle):
            self.run_pf(env, **kw)

    def test_01_isolated_lab_with_authorization_passes(self):
        self.assertEqual(self.run_pf(FakeEnv())['status'], 'PASS')

    def test_02_production_pc_refused(self):
        e = FakeEnv(); e.vols['D'] = {'serial': '7435A171', 'filesystem': 'NTFS', 'label': 'DATA'}
        self.blocked('LAB_IS_PRODUCTION_PC', e)
        e = FakeEnv(); e.files['D:\\Base CSV'] = b''
        self.blocked('PRODUCTION_TICKSTORE_PATHS', e)

    def test_03_system_pagefile_reserved_or_unlabelled_volume_refused(self):
        self.blocked('SYSTEM_DRIVE', FakeEnv(), volume='C')
        e = FakeEnv(); e.pagefile.add('X'); self.blocked('PAGEFILE', e)
        e = FakeEnv(); e.vols['X']['label'] = 'DATA'; self.blocked('LABEL_NOT_SACRIFICIAL', e)
        e = FakeEnv(); e.vols['X']['filesystem'] = 'exFAT'; self.blocked('NOT_NTFS', e)
        e = FakeEnv(); del e.files['X:\\' + L.SENTINEL_NAME]; self.blocked('SENTINEL', e)

    def test_04_separate_user_authorization_required(self):
        self.blocked('LAB_USER_AUTHORIZATION_SHA', FakeEnv(), auth_sha='0' * 64)
        e = FakeEnv(); a = json.loads(e.auth); a['production_pc'] = True; e.files['auth.json'] = json.dumps(a).encode()
        self.blocked('NOT_AUTHORIZED', e)
        e = FakeEnv(); a = json.loads(e.auth); a['lab_volume_serial'] = 'FFFFFFFF'; e.files['auth.json'] = json.dumps(a).encode()
        self.blocked('NOT_AUTHORIZED', e)
        e = FakeEnv(); a = json.loads(e.auth); a['valid_until_unix'] = 1; e.files['auth.json'] = json.dumps(a).encode()
        self.blocked('EXPIRED', e)

    def test_05_external_logger_required(self):
        e = FakeEnv(); lg = json.loads(e.logger); lg['outside_equipment_under_test'] = False
        e.files['logger.json'] = json.dumps(lg).encode()
        self.blocked('EXTERNAL_LOGGER', e)


class PlanAndClassification(unittest.TestCase):
    def test_10_plan_deterministic_all_windows_with_controls(self):
        a, b = L.plan(44), L.plan(44)
        self.assertEqual(a, b)
        self.assertEqual({r['window'] for r in a['rounds'] if r['cut']}, set(L.WINDOWS))
        self.assertEqual(sum(1 for r in a['rounds'] if not r['cut']), 2)
        self.assertNotEqual(L.plan(45)['plan_sha256'], a['plan_sha256'])

    def test_11_inspection_ambiguity_blocks(self):
        ok = {'live_tickstore_processes': [], 'ntfs_dirty': True, 'external_logger_cut_recorded': True,
              'round_id': 'R', 'logger_round_id': 'R', 'containers': [{'date_key': '1', 'status': 'PARTIAL_UNCOMMITTED'}],
              'checkpoint_parse': 'VALID'}
        self.assertEqual(L.classify_inspection(ok)[0], 'INSPECTED_READY_FOR_PRODUCT_RESUME')
        for change in ({'external_logger_cut_recorded': False}, {'checkpoint_parse': 'TORN'}, {'ntfs_dirty': None},
                       {'containers': [{'date_key': '1', 'status': 'UNKNOWN'}]}, {'logger_round_id': 'X'},
                       {'live_tickstore_processes': [123]}):
            self.assertEqual(L.classify_inspection(dict(ok, **change))[0], 'BLOCKED', change)

    def test_12_reconciliation_requires_exact_containers(self):
        ctl = {'a': '1', 'b': '2'}
        self.assertEqual(L.reconcile_round(ctl, dict(ctl), 'PASS', 'INSPECTED_READY_FOR_PRODUCT_RESUME')[0], 'ROUND_PASS')
        self.assertEqual(L.reconcile_round(ctl, {'a': '1'}, 'PASS', 'INSPECTED_READY_FOR_PRODUCT_RESUME')[0], 'ROUND_BLOCKED')
        self.assertEqual(L.reconcile_round(ctl, {'a': '1', 'b': 'X'}, 'PASS', 'INSPECTED_READY_FOR_PRODUCT_RESUME')[0],
                         'ROUND_BLOCKED')
        self.assertEqual(L.reconcile_round(ctl, {}, 'FAIL_CLOSED_RECONCILIATION_REQUIRED',
                                           'INSPECTED_READY_FOR_PRODUCT_RESUME')[0], 'ROUND_FAIL_CLOSED')
        self.assertEqual(L.reconcile_round(ctl, dict(ctl), 'PASS', 'BLOCKED')[0], 'ROUND_BLOCKED')

    def test_13_no_execution_off_windows_or_without_preflight(self):
        args = ['arm', '--volume', 'X', '--logger', 'l', '--logger-sha256', 'A' * 64, '--authorization', 'a',
                '--authorization-sha256', 'A' * 64, '--plan', 'p', '--plan-sha256', 'A' * 64, '--round', 'R',
                '--candidate-impl', 'c', '--code-manifest-sha256', 'A' * 64]
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = L.main(args)
        self.assertEqual(rc, 2)
        self.assertIn('LAB_BLOCKED=' + ('LabBlocked:LAB_WINDOWS_REQUIRED' if os.name != 'nt' else ''), buf.getvalue())
        st = L.environment_status()
        self.assertEqual((st['status'], st['execution_authorized']), ('BLOCKED', False))



SRC = Path(__file__).resolve().parents[1]


class LabRoundEndToEnd(unittest.TestCase):
    """Real packaged engine on a synthetic workload; the cut is EMULATED here only to exercise the
    wiring off the lab (process-tree kill).  This is never physical evidence."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='lab_round_'))
        cls.cand = SRC / 'candidate'
        cls.offline = os.name != 'nt'
        cls.rnd = {'round_id': 'PRE_COMMIT_WRITE_01', 'window': 'PRE_COMMIT_WRITE', 'cut': True, 'hold_seconds': 0.3,
                   'fixture_seed': 1}

        def cut(proc):
            if cls.offline:
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait(60)
        cls.status, cls.rdir = L.arm(cls.rnd, cls.tmp, cls.cand, scale=1, offline=cls.offline, interval=0.02, cut=cut,
                                     plan_sha256='P' * 64, preflight_rec={'status': 'PASS'})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def logger(self, **over):
        rec = {'schema': L.LOGGER_RECORD_SCHEMA, 'round_id': self.rnd['round_id'], 'cut_instant': '2026-10-14T12:00:00Z',
               'restore_instant': '2026-10-14T12:01:00Z', 'supply_state': 'RESTORED'}
        rec.update(over)
        raw = json.dumps(rec).encode()
        p = self.tmp / ('LOGGER_%d.json' % len(list(self.tmp.glob('LOGGER_*'))))
        p.write_bytes(raw)
        return str(p), h(raw)

    class Probe(L.LabProbe):
        def __init__(self, dirty=False, alive=False): self.dirty, self.alive = dirty, alive
        def ntfs_dirty(self, volume): return self.dirty
        def pid_alive(self, pid): return self.alive
        def read(self, p): return Path(p).read_bytes()

    def test_20_arm_beacons_ready_and_durable_state(self):
        self.assertEqual(self.status, 'CUT_EMULATED_FOR_TEST')
        entries, torn = L.read_beacon(self.rdir)
        self.assertTrue(any(e['ready'] for e in entries)); self.assertEqual(torn, 0)
        self.assertTrue(entries[-1]['child_alive'])
        arm = json.loads((self.rdir / L.ARM_RECORD).read_bytes())
        self.assertEqual((arm['plan_sha256'], arm['preflight']), ('P' * 64, {'status': 'PASS'}))

    def test_21_inspection_then_product_resume_matches_control(self):
        path, digest = self.logger()
        insp = L.inspect(self.rdir, 'X', path, digest, env=self.Probe())
        self.assertEqual(insp['status'], 'INSPECTED_READY_FOR_PRODUCT_RESUME', insp['reasons'])
        self.assertFalse(insp['resume_started_before_inspection'])
        rec = L.reconcile(self.rdir, self.cand, offline=self.offline)
        r = rec['reconciliation']
        self.assertEqual(r['containers_after_resume'], r['containers_control'])
        self.assertTrue(r['containers_control'])
        if insp['window_hit']:
            self.assertIn(r['status'], ('ROUND_PASS', 'ROUND_FAIL_CLOSED_RECONCILED'))
        else:
            self.assertEqual(r['status'], 'ROUND_WINDOW_MISSED')
        self.assertTrue((self.rdir / L.RECEIPT).is_file())
        self.assertFalse(rec['equivalent_to_process_death'])
        with self.assertRaises(FileExistsError):  # receipts are never overwritten
            L.reconcile(self.rdir, self.cand, offline=self.offline)

    def test_22_inspection_blocks_on_ambiguity(self):
        d = self.tmp / 'COPY_ROUND'
        if not d.exists():
            shutil.copytree(self.rdir, d, ignore=shutil.ignore_patterns(L.INSPECTION, L.RECEIPT))
        for kw, probe, needle in (({'round_id': 'OTHER'}, self.Probe(), 'LOGGER_ROUND_MISMATCH'),
                                  ({'supply_state': 'OFF'}, self.Probe(), 'EXTERNAL_CUT_NOT_EVIDENCED'),
                                  ({}, self.Probe(dirty=None), 'NTFS_DIRTY_STATE_UNKNOWN')):
            for p in d.glob(L.INSPECTION):
                p.unlink()
            path, digest = self.logger(**kw)
            rec = L.inspect(d, 'X', path, digest, env=probe)
            self.assertEqual(rec['status'], 'BLOCKED'); self.assertIn(needle, rec['reasons'])
        path, digest = self.logger()
        with self.assertRaisesRegex(L.LabBlocked, 'LAB_LOGGER_RECORD_SHA'):
            L.inspect(d, 'X', path, '0' * 64, env=self.Probe())

    def test_23_reconcile_requires_inspection_and_candidate_binding(self):
        d = self.tmp / 'NO_INSPECTION'
        if not d.exists():
            shutil.copytree(self.rdir, d, ignore=shutil.ignore_patterns(L.INSPECTION, L.RECEIPT))
        with self.assertRaises(FileNotFoundError):
            L.reconcile(d, self.cand, offline=self.offline)
        with self.assertRaisesRegex(L.LabBlocked, 'LAB_CANDIDATE_MANIFEST_SHA'):
            L.bind_candidate(SRC, '0' * 64)

    def test_24_aggregate_never_claims_more_than_the_receipts(self):
        body = {'plan_sha256': 'P' * 64, 'rounds': [dict(self.rnd), {'round_id': 'CONTROL_01', 'window': None, 'cut': False},
                                                    {'round_id': 'JOURNAL_RECEIPT_UPDATE_01', 'window': 'JOURNAL_RECEIPT_UPDATE',
                                                     'cut': True}]}
        agg = L.aggregate(body, self.tmp)
        self.assertEqual(agg['status'], 'INCOMPLETE'); self.assertFalse(agg['gate_verdict_issued'])

    def test_25_window_classification(self):
        base = {'containers': 0, 'commits': 0, 'payload_partial': 0, 'commit_partial': 0, 'manifest_partial': 0,
                'writer_lock': True}
        self.assertEqual(L.window_of(dict(base, payload_partial=1)), 'PRE_COMMIT_WRITE')
        self.assertEqual(L.window_of(dict(base, commit_partial=1)), 'JOURNAL_RECEIPT_UPDATE')
        self.assertEqual(L.window_of(dict(base, commits=2)), 'POST_COMMIT_PRE_CHECKPOINT')
        self.assertIsNone(L.window_of(dict(base, writer_lock=False)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
