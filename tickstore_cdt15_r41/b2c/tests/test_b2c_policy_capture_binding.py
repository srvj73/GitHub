"""R44-B2C (SOURCE_ONLY): current-policy binding of the D4/FULL consumers, drift controls.

Runs against a disposable merged tree = source/candidate + b2c/candidate_overlay.
The origin reconciliation records built here are UNIT FIXTURES ONLY: the real record is
issued by the ChatGPT origin and its SHA-256 is supplied separately by the operator.
"""
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
B2C = HERE.parent
TOP = B2C.parent
CAPTURE = B2C / 'fixtures/R40_CAPTURE'
R3_ARCHIVE = TOP / 'b1/r3_inputs/R3_RUNTIME_ORIGINAL_ARCHIVE.zip'
R40_MASTER = '695DCD6495E549B13B13A73E063EA147CF97354C53940A70647EDFD0A0BC7DF5'
R40_HEAD = 'B3B419592DC29651487B1545E1CD7AE66604AB78582202883684E69BCB1FF7EA'
R40_REV = '20261013T070500-0300-695DCD6495E549B1'
MERGED = None
TMP = None


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def setUpModule():
    global MERGED, TMP
    TMP = tempfile.mkdtemp(prefix='b2c_merged_')
    MERGED = Path(TMP) / 'candidate'
    shutil.copytree(TOP / 'source/candidate', MERGED, ignore=shutil.ignore_patterns('__pycache__'))
    for p in (B2C / 'candidate_overlay').rglob('*'):
        if p.is_file():
            dst = MERGED / p.relative_to(B2C / 'candidate_overlay')
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, MERGED / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str((MERGED / rel).parent))
    spec.loader.exec_module(mod)
    return mod


def reader(path, expected=None):
    return Path(path).read_bytes()


class Base(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.t = Path(t.name)
        self.cap = load('b2c_capture', 'control/POLICY_CAPTURE_BINDING.py')
        self.root = self.t / 'POLICY'; shutil.copytree(CAPTURE, self.root)
        self.now = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)
        self.rec = {'schema': 'TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001', 'issuer': 'CHATGPT_ORIGIN',
                    'status': 'CURRENT_AT_ORIGIN', 'policy_master_sha256': R40_MASTER, 'policy_head_sha256': R40_HEAD,
                    'policy_revision': R40_REV, 'live_cardinality': {'master': 1, 'head': 1}, 'live_state': 'FROZEN',
                    'capture_operational_authority': False, 'administrative_owner_gate_required': False,
                    'scope': ['D4_FIRST_ADMISSION', 'FULL_CHAIN'], 'routing_project': 'Base de Dados CSV / Tickstore',
                    'routing_thread': 'Compress\u00e3o De Ticks 15', 'reconciled_at': '2026-10-14T08:00:00-03:00',
                    'valid_until': '2026-10-15T08:00:00-03:00', 'fixture': 'UNIT_FIXTURE_NOT_ORIGIN_EVIDENCE'}

    def verify(self, rec=None, root=None, sha_override=None):
        raw = (json.dumps(rec or self.rec, sort_keys=True) + '\n').encode()
        p = self.t / ('REC_%d.json' % len(list(self.t.glob('REC_*'))))
        p.write_bytes(raw)
        return self.cap.verify_capture(reader, root or self.root, p, sha_override or sha(raw), now=self.now)

    def blocked(self, needle, **kw):
        with self.assertRaisesRegex(self.cap.PolicyBlocked, needle):
            self.verify(**kw)


class CaptureVerification(Base):
    def test_01_r40_capture_with_current_origin_reconciliation(self):
        c = self.verify()
        self.assertEqual((c['master_sha256'], c['head_sha256'], c['revision_id']), (R40_MASTER, R40_HEAD, R40_REV))
        self.assertFalse(c['capture_operational_authority']); self.assertFalse(c['administrative_owner_gate_required'])
        self.assertEqual(c['routing_thread'], 'Compress\u00e3o De Ticks 15')
        # Receipt provenance stays the frozen-engine ABI value, independent of routing.
        self.assertEqual((c['receipt_project'], c['receipt_thread']), ('PEGASUS_TICKSTORE', 'Compress\u00e3o De Ticks 7'))

    def test_02_cardinality_extra_file(self):
        (self.root / 'POLITICA_CANONICA_HEAD_OLD.json').write_bytes(b'{}')
        self.blocked('POLICY_CARDINALITY_1_PLUS_1')

    def test_03_master_drift_after_head(self):
        m = self.root / self.cap.MASTER; m.write_bytes(m.read_bytes() + b'\n')
        self.blocked('POLICY_HEAD_MASTER')

    def test_04_head_not_frozen(self):
        h = self.root / self.cap.HEAD; d = json.loads(h.read_bytes()); d['state'] = 'UNFROZEN'
        h.write_text(json.dumps(d, indent=2) + '\n', encoding='utf-8')
        self.blocked('POLICY_HEAD_NOT_FROZEN')

    def test_05_revision_not_bound_to_master(self):
        h = self.root / self.cap.HEAD; d = json.loads(h.read_bytes()); d['revision_id'] = '20261013T070500-0300-0000000000000000'
        h.write_text(json.dumps(d, indent=2) + '\n', encoding='utf-8')
        self.blocked('POLICY_REVISION_NOT_BOUND_TO_MASTER')

    def test_06_historical_v38_capture_is_never_current(self):
        v38 = self.t / 'V38'; v38.mkdir()
        with zipfile.ZipFile(R3_ARCHIVE) as z:
            for n in (self.cap.MASTER, self.cap.HEAD):
                (v38 / n).write_bytes(z.read('cdt15/work/revision_v38/policy/' + n))
        rec = dict(self.rec, policy_master_sha256=sha((v38 / self.cap.MASTER).read_bytes()),
                   policy_head_sha256=sha((v38 / self.cap.HEAD).read_bytes()),
                   policy_revision='20261012T070600-0300-5B135DA0CA7C3BFE')
        self.blocked('POLICY_HISTORICAL_NOT_CURRENT:V38', rec=rec, root=v38)

    def test_07_reconciliation_digest_supplied_separately_must_match(self):
        self.blocked('POLICY_RECONCILIATION_SHA256', sha_override='0' * 64)

    def test_08_library_moved_after_reconciliation(self):
        self.blocked('POLICY_RECONCILIATION_BINDING', rec=dict(self.rec, policy_head_sha256='F' * 64))

    def test_09_reconciliation_time_window(self):
        self.blocked('EXPIRED_OR_FUTURE', rec=dict(self.rec, valid_until='2026-10-14T08:30:00-03:00'))
        self.blocked('EXPIRED_OR_FUTURE', rec=dict(self.rec, reconciled_at='2026-10-14T10:00:00-03:00'))
        self.blocked('WINDOW_TOO_LONG', rec=dict(self.rec, reconciled_at='2026-10-11T08:00:00-03:00',
                                                 valid_until='2026-10-14T10:00:00-03:00'))
        self.blocked('POLICY_RECONCILIATION_TIMEZONE', rec=dict(self.rec, valid_until='2026-10-15T08:00:00'))

    def test_10_no_authority_claims(self):
        self.blocked('AUTHORITY_FIELDS', rec=dict(self.rec, administrative_owner_gate_required=True))
        self.blocked('AUTHORITY_FIELDS', rec=dict(self.rec, capture_operational_authority=True))
        self.blocked('POLICY_RECONCILIATION_SCHEMA', rec=dict(self.rec, issuer='OPUS_ENGINEER'))
        self.blocked('POLICY_RECONCILIATION_NOT_CURRENT', rec=dict(self.rec, status='DRAFT'))
        self.blocked('POLICY_RECONCILIATION_SCOPE', rec=dict(self.rec, scope=['FULL_CHAIN']))
        h = self.root / self.cap.HEAD; d = json.loads(h.read_bytes()); d['project_local_copy_operational_authority'] = True
        h.write_text(json.dumps(d, indent=2) + '\n', encoding='utf-8')
        self.blocked('POLICY_CAPTURE_CLAIMS_AUTHORITY')

    def test_11_legitimate_future_policy_needs_no_code_change(self):
        new = self.t / 'NEXT'; new.mkdir()
        master = (self.root / self.cap.MASTER).read_bytes() + '\n<!-- synthetic next revision (unit fixture) -->\n'.encode()
        (new / self.cap.MASTER).write_bytes(master)
        head = json.loads((self.root / self.cap.HEAD).read_bytes())
        head.update(master_sha256=sha(master), previous_master_sha256=R40_MASTER,
                    revision_id='20261020T090000-0300-' + sha(master)[:16])
        (new / self.cap.HEAD).write_text(json.dumps(head, indent=2) + '\n', encoding='utf-8')
        rec = dict(self.rec, policy_master_sha256=sha(master), policy_head_sha256=sha((new / self.cap.HEAD).read_bytes()),
                   policy_revision=head['revision_id'])
        c = self.verify(rec=rec, root=new)
        self.assertEqual(c['master_sha256'], sha(master))
        # The R40 reconciliation cannot vouch for the new library state.
        self.blocked('POLICY_RECONCILIATION_BINDING', root=new)


class ConsumersHaveNoPolicyPins(unittest.TestCase):
    PINS = ('5B135DA0CA7C3BFE992F', '2DA2939C88530B089D3E', 'CADAF9068532EACBF488', '4F4D2B6028B291F9BD26',
            '6F9D9E8C4FF360942DBF', 'D3834F992DDF120B08D9', R40_MASTER[:20], R40_HEAD[:20], '695DCD6495E549B1',
            '20260930_110443_935_34868')

    def test_20_no_historical_or_current_policy_literal_in_consumers(self):
        for rel in ('control/D4_FIRST_ADMISSION_TRANSACTION.py', 'control/D4_FIRST_ADMISSION_PREP.py',
                    'control/D4_FIRST_ADMISSION_BOOTSTRAP.py', 'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1',
                    'control/FULL_STAGE_CONTINUATION.py', 'control/FULL_INSTANCE_PREPARE.py', 'control/FULL_RUNNER.py',
                    'control/RUN_TICKSTORE_FULL.ps1'):
            text = (MERGED / rel).read_text(encoding='utf-8')
            for pin in self.PINS:
                self.assertNotIn(pin, text, (rel, pin))
        cap = (MERGED / 'control/POLICY_CAPTURE_BINDING.py').read_text(encoding='utf-8')
        self.assertNotIn(R40_MASTER[:20], cap)  # the current revision is never a literal

    def test_21_first_admission_binding_matches_merged_bytes(self):
        b = json.loads((MERGED / 'control/FIRST_ADMISSION_BINDING.json').read_bytes())
        for key, rel in (('preparation_sha256', 'control/D4_FIRST_ADMISSION_PREP.py'),
                         ('transaction_sha256', 'control/D4_FIRST_ADMISSION_TRANSACTION.py'),
                         ('bootstrap_sha256', 'control/D4_FIRST_ADMISSION_BOOTSTRAP.py'),
                         ('wrapper_sha256', 'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1'),
                         ('predecessor_reconciliation_sha256', 'control/D4_PREDECESSOR_RECONCILIATION.py'),
                         ('policy_capture_binding_sha256', 'control/POLICY_CAPTURE_BINDING.py')):
            self.assertEqual(b[key], sha((MERGED / rel).read_bytes()), key)

    def test_22_frozen_rc1_core_and_legacy_launchers_untouched(self):
        # The legacy FULL_SERIAL/pilot entries live in the frozen RC1 core (SHA pinned by
        # CORE_RC1_FROZEN); B2C must not modify it.  Residual risk is reported to the origin.
        import hashlib as _h
        core = (MERGED / 'full/tickstore_serial_runner.py').read_bytes()
        self.assertEqual(_h.sha256(core).hexdigest().upper(),
                         'D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0')
        self.assertFalse((B2C / 'candidate_overlay/full').exists())


class TransactionConsumesVerifiedCapture(Base):
    def setUp(self):
        super().setUp()
        self.T = load('b2c_transaction', 'control/D4_FIRST_ADMISSION_TRANSACTION.py')
        self.capture = self.verify()
        self.expected = {k: 'A' * 64 for k in ('final_code_manifest_sha256', 'review_pack_sha256', 'base_release_sha256',
                                              'successor_release_sha256', 'successor_candidate_sha256',
                                              'effectful_wrapper_sha256', 'review_verdict_sha256',
                                              'artifact_base_master_sha256')}
        contract = {'schema': 'TICKSTORE_QUALIFICATION_CONTRACT_V001',
                    'baseline': dict(status='PASS_HISTORICAL_BYTES_ONLY', archive_sha256='C' * 64, run_sha256='D' * 64,
                                     tests_sha256='E' * 64, code_manifest_sha256='F' * 64),
                    'required_tests': ['fixture-only'], 'required_target_proofs': ['fixture-proof']}
        delta = dict(schema='TICKSTORE_CDT15_DELTA_QUALIFICATION_V001', platform='WINDOWS_NTFS_PS51', native_windows=True,
                     code_manifest_sha256='A' * 64, tested_code_equals_packaged_code='PASS', production_execution=False,
                     success=True, tests=[dict(id='fixture-only', status='PASS')],
                     target_proofs={'fixture-proof': dict(status='PASS', evidence=[dict(path='fixture-only', sha256='B' * 64)])})
        self.complete = {'schema': 'TICKSTORE_ENGINEERING_COMPLETENESS_V002', 'status': 'COMPLETE', 'known_blockers': [],
                         'integration_implemented': True, 'windows_qualification': 'PASS', 'code_manifest_sha256': 'A' * 64,
                         'baseline': contract['baseline'], 'baseline_results_counted_as_delta': False,
                         'baseline_archive_evidence': dict(path='fixture-only', sha256='C' * 64),
                         'delta_test_totals': dict(run=1, failures=0, errors=0, skips=0), 'delta_qualification': delta}
        self.expected.update(qualification_contract=contract, policy_capture=self.capture,
                             qualification_validator_sha256=sha((MERGED / 'control/FULL_QUALIFICATION_CONTRACT.py').read_bytes()))
        self.review = dict(self.T.REVIEW_CHECKS)
        for field, key in [('REVIEW_PACK_SHA256', 'review_pack_sha256'), ('BASE_RELEASE_SHA256', 'base_release_sha256'),
                           ('SUCCESSOR_RELEASE_SHA256', 'successor_release_sha256'),
                           ('SUCCESSOR_CANDIDATE_SHA256', 'successor_candidate_sha256'),
                           ('EFFECTFUL_WRAPPER_SHA256', 'effectful_wrapper_sha256')]:
            self.review[field] = self.expected[key]
        self.b07 = {'schema': 'TICKSTORE_B07_TECHNICAL_RECEIPT_V001', 'status': 'PASS', 'platform': 'WINDOWS_NTFS_PS51',
                    'code_manifest_sha256': 'A' * 64, 'review_verdict_sha256': 'A' * 64,
                    'checks': dict.fromkeys(self.T.B07_CHECKS, 'PASS')}
        self.policy = {'schema': 'TICKSTORE_D4_POLICY_ADMISSION_RECEIPT_V001', 'status': 'PASS', 'effect_scope': 'D4_ONLY',
                       'policy_source_cardinality': 'PASS_1_MASTER_PLUS_1_HEAD', 'policy_head_state': 'FROZEN',
                       'material_delta_reconciled': 'YES', 'material_delta_blocks_execution': 'NO'}
        self.policy.update(self.cap.expected_receipt_fields(self.capture))
        for key in ('artifact_base_master_sha256', 'review_pack_sha256', 'review_verdict_sha256', 'effectful_wrapper_sha256'):
            self.policy[key] = self.expected[key]

    def gates(self):
        self.T.validate_gates(self.review, self.b07, self.complete, self.policy, self.expected)

    def test_30_receipt_bound_to_verified_capture_accepts(self):
        self.gates()

    def test_31_v38_receipt_rejected(self):
        self.policy.update(active_master_sha256='5B135DA0CA7C3BFE992F364720605522FB939977772C6D5A6FD3811A8288B302')
        with self.assertRaisesRegex(self.T.Blocked, 'POLICY_active_master_sha256'):
            self.gates()
        self.policy.update(self.cap.expected_receipt_fields(self.capture), thread='Compress\u00e3o De Ticks 15')
        with self.assertRaisesRegex(self.T.Blocked, 'POLICY_thread'):
            self.gates()

    def test_32_capture_required_and_reconciliation_bound(self):
        self.policy['origin_policy_reconciliation_sha256'] = '0' * 64
        with self.assertRaisesRegex(self.T.Blocked, 'POLICY_origin_policy_reconciliation_sha256'):
            self.gates()
        del self.expected['policy_capture']
        with self.assertRaisesRegex(self.T.Blocked, 'POLICY_CAPTURE_REQUIRED'):
            self.gates()

    def test_33_capture_claiming_authority_rejected(self):
        self.expected['policy_capture'] = dict(self.capture, administrative_owner_gate_required=True)
        with self.assertRaisesRegex(self.T.Blocked, 'POLICY_CAPTURE_REQUIRED'):
            self.gates()

    def test_34_d4_dispatch_requires_current_reconciliation(self):
        sys.path.insert(0, str(MERGED / 'control'))
        R = load('b2c_full_runner', 'control/FULL_RUNNER.py')
        inst = {'d4_parameters': {k: 'C:\\x\\' + k for k in R.D4_PARAMETERS}}
        os.environ.setdefault('SystemRoot', 'C:\\Windows')
        with self.assertRaises(Exception):
            R.d4_command(inst, MERGED)
        cmd = R.d4_command(inst, MERGED, policy_reconciliation='C:\\rec.json', policy_reconciliation_sha256='A' * 64)
        self.assertEqual(cmd[cmd.index('-OriginCapturePath') + 1], 'C:\\rec.json')
        self.assertEqual(cmd[cmd.index('-OriginReconciliationSha256') + 1], 'A' * 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
