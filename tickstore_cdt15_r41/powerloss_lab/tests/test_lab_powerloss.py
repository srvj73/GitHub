"""SOURCE_ONLY tests of the physical power-loss lab tooling (no execution, no hardware)."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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

    def test_13_no_execution_in_source_only(self):
        self.assertEqual(L.main(['arm']), 2)
        st = L.environment_status()
        self.assertEqual((st['status'], st['execution_authorized']), ('BLOCKED', False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
