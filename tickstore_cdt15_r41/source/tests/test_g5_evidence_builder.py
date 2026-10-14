"""G5 producer/consumer after B2-G5-01: physical provenance, negative controls, never a gate PASS.

The positive fixture is synthetic (see g5_native_fixture); it proves only the mechanics.
Every adversarial condition reproduced by the origin must block in BOTH the producer
(G5_EVIDENCE_BUILDER.build) and the consumer (FULL_QUALIFICATION_CONTRACT.validate).
"""
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'candidate/control'))
sys.path.insert(0, str(R / 'tests'))
import G5_EVIDENCE_BUILDER as G  # noqa: E402
import g5_native_fixture as FX  # noqa: E402

BASELINE = R / 'tests/fixtures/V38_NATIVE_QUALIFICATION_RESULT_ORIGINAL_DC73A8C3.zip'
ADVERSARIAL = R / 'tests/fixtures/ORIGIN_B2_reproduce_adversarial_completeness.py'
ADVERSARIAL_SHA = '1AB624048C66F73EA60EEE7624DA442AD82BFE823442AFC3D2C5328C46ADB8F8'
CONTRACT = FX.CONTRACT
POWER = 'CHECKPOINT_POWERLOSS_RECOVERY:PHYSICAL_PROOF_NOT_SPECIFIED_BY_ORIGIN'


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


class Base(unittest.TestCase):
    hypothetical = False

    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.t = Path(t.name)
        self.ns = FX.with_physical_powerloss_spec() if self.hypothetical else FX.load_consumer()
        self.fx = FX.NativeFixture(self.ns)
        self.n = 0

    def build(self, blockers=(), baseline=BASELINE):
        self.n += 1
        rz, fz, code_sha, final_sha = self.fx.make(self.t, 'F%d' % self.n)
        out = self.t / ('OUT%d' % self.n)
        sha = h((R / 'candidate/control/FULL_QUALIFICATION_CONTRACT.py').read_bytes())
        with mock.patch.object(G, 'load_consumer', return_value=(self.ns, sha)):
            c = G.build(return_zip=rz, final_zip=fz, baseline_archive=baseline, known_blockers=list(blockers),
                        out_dir=out)
        return c, out

    def consume(self, c):
        def require(cond, why):
            if not cond:
                raise G.Blocked(why)
        self.ns['validate'](c, CONTRACT, c['delta_qualification'], c['code_manifest_sha256'], require)

    def assert_blocks(self, needle):
        c, out = self.build()
        self.assertEqual(c['status'], 'INCOMPLETE')
        self.assertTrue(any(needle in b for b in c['known_blockers']), c['known_blockers'])
        self.assertTrue(c['consumer_self_check'].startswith('REJECTS'), c['consumer_self_check'])
        with self.assertRaises(G.Blocked):
            self.consume(c)
        return c, out


class MechanicsAcceptWithHypotheticalPhysicalSpec(Base):
    hypothetical = True

    def setUp(self):
        super().setUp()
        self.fx.proofs['CHECKPOINT_POWERLOSS_RECOVERY'] = {}

    def test_01_closed_native_return_zip_is_accepted_by_both(self):
        c, out = self.build()
        self.assertEqual(c['known_blockers'], [])
        self.assertEqual(c['status'], 'COMPLETE'); self.assertEqual(c['consumer_self_check'], 'ACCEPTS')
        self.assertEqual(c['windows_qualification'], 'PASS'); self.assertEqual(c['provenance_mode'], 'CLOSED_NATIVE_RETURN_ZIP')
        self.assertEqual(c['delta_test_totals'], {'run': 126, 'failures': 0, 'errors': 0, 'skips': 0})
        self.consume(c)
        delta_raw = (out / 'DELTA_QUALIFICATION.json').read_bytes()
        self.assertEqual(c['delta_qualification_evidence']['sha256'], h(delta_raw))
        prov = c['delta_qualification']['native_provenance']
        self.assertEqual(prov['code_manifest_files'], 2)
        self.assertEqual(h((out / prov['return_zip']['pack_relative']).read_bytes()), prov['return_zip']['sha256'])

    def test_02_pack_is_relocatable_but_bytes_stay_bound(self):
        c, out = self.build()
        moved = self.t / 'MOVED'; shutil.move(str(out), str(moved))
        c2 = json.loads((moved / 'ENGINEERING_COMPLETENESS.json').read_bytes())
        c2['delta_qualification_evidence']['path'] = str(moved / 'DELTA_QUALIFICATION.json')
        for e in c2['delta_qualification']['target_proofs'].values():
            e['evidence'][0]['path'] = str(self.t / 'gone.json')
        for k in ('return_zip', 'final_zip'):
            c2['delta_qualification']['native_provenance'][k]['path'] = str(self.t / 'gone.zip')
        self.consume(c2)
        z = moved / c2['delta_qualification']['native_provenance']['return_zip']['pack_relative']
        z.write_bytes(z.read_bytes() + b'x')
        with self.assertRaisesRegex(G.Blocked, 'PROVENANCE_RETURN_ZIP_SHA256'):
            self.consume(c2)

    def test_03_consumer_rejects_delta_tests_not_from_physical_harness(self):
        c, _ = self.build()
        d = c['delta_qualification']
        d['tests'] = list(reversed(d['tests']))
        with self.assertRaisesRegex(G.Blocked, 'DELTA_TESTS_NOT_PHYSICAL_HARNESS'):
            self.consume(c)

    def test_04_consumer_rejects_hand_written_delta_without_provenance(self):
        c, _ = self.build()
        del c['delta_qualification']['native_provenance']
        with self.assertRaisesRegex(G.Blocked, 'NATIVE_PROVENANCE_MISSING'):
            self.consume(c)


class RealContractNeverCompleteWithoutPhysicalPowerloss(Base):
    def test_05_only_physical_powerloss_remains_pending(self):
        c, out = self.build()
        self.assertEqual(c['status'], 'INCOMPLETE')
        self.assertEqual([b for b in c['known_blockers'] if not b.startswith('CONSUMER_')], [POWER])
        self.assertEqual(c['windows_qualification'], 'PASS')
        self.assertEqual(c['delta_qualification']['target_proofs']['CHECKPOINT_POWERLOSS_RECOVERY']['status'],
                         'PENDING_NO_TYPED_RECEIPT')

    def test_06_powerloss_emulated_never_satisfies_physical_proof(self):
        rec, arts = self.fx.receipt('PROCESS_TREE_CRASH_CONTAINMENT', 'X', 'Y')
        emu = dict(rec, kind=self.ns['POWERLOSS_EMULATED_KIND'], proof='CHECKPOINT_POWERLOSS_RECOVERY',
                   status='EMULATED_PASS')
        self.fx.proofs['CHECKPOINT_POWERLOSS_RECOVERY'] = {}
        self.fx.proof_override['CHECKPOINT_POWERLOSS_RECOVERY'] = emu
        c, _ = self.assert_blocks('POWERLOSS_EMULATED_IS_NOT_PHYSICAL_POWERLOSS')
        self.assertIn(POWER, c['known_blockers'])

    def test_07_emulated_receipt_reported_separately_never_as_proof(self):
        emu = FX.j({'kind': self.ns['POWERLOSS_EMULATED_KIND'], 'status': 'EMULATED_PASS'})
        self.fx.extra_return[self.ns['PROOF_PREFIX'] + 'POWERLOSS_EMULATED/PROOF_RECEIPT.json'] = emu
        c, _ = self.build()
        self.assertEqual(c['powerloss_emulated']['counts_as'], 'NOT_CHECKPOINT_POWERLOSS_RECOVERY')
        self.assertIn(POWER, c['known_blockers'])

    def test_08_never_issues_a_gate_pass(self):
        c, out = self.build()
        draft = json.loads((out / 'G5_STAGE_RECEIPT_DRAFT.json').read_bytes())
        self.assertEqual(draft['status'], 'PENDING_ORIGIN_DECISION')
        self.assertFalse(draft['gate_verdict_issued']); self.assertFalse(c['gate_verdict_issued'])
        for p in out.rglob('*.json'):
            self.assertNotIn(b'"status":"PASS","stage"', p.read_bytes())
        from FULL_RELEASE_CHAIN import validate_chain
        with self.assertRaises(Exception):
            validate_chain({'G5': draft}, {'G5': 'A' * 64}, code_sha=c['code_manifest_sha256'],
                           instance_sha='B' * 64, b06_sha='C' * 64, until='G5')


class OriginAdversarialControls(Base):
    """B2-G5-01 conditions, one by one, on the closed native interface."""
    hypothetical = True

    def setUp(self):
        super().setUp()
        self.fx.proofs['CHECKPOINT_POWERLOSS_RECOVERY'] = {}

    def test_10_empty_code_manifest(self):
        self.fx.empty_code_manifest = True
        self.assert_blocks('FINAL_RUNTIME_MANIFEST_EMPTY')

    def test_11_127_records_for_126_ids(self):
        self.fx.harness['tests'].append(dict(self.fx.harness['tests'][0]))
        self.assert_blocks('HARNESS_DUPLICATE_RECORDS:' + CONTRACT['required_tests'][0])

    def test_12_harness_success_false(self):
        self.fx.harness['success'] = False
        self.assert_blocks('HARNESS_SUCCESS_NOT_TRUE')

    def test_13_harness_tests_run_zero(self):
        self.fx.harness['totals'] = {'tests_run': 0, 'failures': 0, 'errors': 0, 'skips': 0}
        self.assert_blocks('HARNESS_TOTALS')

    def test_14_declared_native_without_windows_evidence(self):
        self.fx.harness.update(platform='Linux-6.18-x86_64', python='3.14.0 [GCC 14]')
        self.fx.precheck.update(platform='Linux-6.18-x86_64', powershell='7.5.0')
        c, _ = self.assert_blocks('HARNESS_PLATFORM_NOT_WINDOWS')
        self.assertEqual(c['windows_qualification'], 'NOT_PASS')
        self.assertFalse(c['delta_qualification']['native_windows'])
        self.assertIn('QUAL_PRECHECK_PS51', c['known_blockers'])

    def test_15_same_receipt_for_all_proofs(self):
        rec, _ = self.fx.receipt('PROCESS_TREE_CRASH_CONTAINMENT', 'X', 'Y')
        for name in CONTRACT['required_target_proofs']:
            self.fx.proof_override[name] = rec
        c, _ = self.assert_blocks('EVIDENCE_REUSED_FROM')
        self.assertTrue(any('RECEIPT_PROOF_NAME' in b for b in c['known_blockers']))

    def test_16_generic_receipt_without_named_checks(self):
        self.fx.proofs['SAFE_STOP_RESUME_ROW_GROUP'] = {'checks': {'generic': 'PASS'}}
        self.assert_blocks('SAFE_STOP_RESUME_ROW_GROUP:RECEIPT_CHECKS')

    def test_17_receipt_without_artifacts(self):
        self.fx.proofs['PS51_INSTALL_MENU'] = {'artifacts': []}
        self.assert_blocks('PS51_INSTALL_MENU:RECEIPT_NO_ARTIFACTS')

    def test_18_receipt_artifact_not_in_return_zip(self):
        self.fx.proofs['D4_CLOSURE_NATIVE_1399'] = {
            'artifacts': [{'member': 'EVIDENCE/PROOFS/D4_CLOSURE_NATIVE_1399/missing.json', 'sha256': 'A' * 64}]}
        self.assert_blocks('D4_CLOSURE_NATIVE_1399:RECEIPT_ARTIFACT')

    def test_19_runner_not_the_packaged_runner(self):
        self.fx.proofs['STAGE_B_FULL_CHAIN_NATIVE'] = {
            'runner': {'path': 'somewhere/else.py', 'function': 'proof_stage_b_synthetic_chain', 'sha256': 'A' * 64}}
        self.assert_blocks('STAGE_B_FULL_CHAIN_NATIVE:RECEIPT_RUNNER_NOT_PACKAGED')

    def test_20_receipt_from_another_run_or_bytes(self):
        self.fx.proofs['PROCESS_TREE_CRASH_CONTAINMENT'] = {'run_id': 'OTHER_RUN'}
        self.assert_blocks('PROCESS_TREE_CRASH_CONTAINMENT:RECEIPT_RUN_BINDING')

    def test_21_receipt_status_not_pass(self):
        self.fx.proofs['PROCESS_TREE_CRASH_CONTAINMENT'] = {'status': 'FAIL'}
        self.assert_blocks('PROCESS_TREE_CRASH_CONTAINMENT:RECEIPT_STATUS:FAIL')

    def test_22_missing_typed_receipt(self):
        del self.fx.proofs['PS51_INSTALL_MENU']
        self.assert_blocks('PS51_INSTALL_MENU:EVIDENCE_NOT_SINGLE_TYPED_RECEIPT')

    def test_23_final_zip_member_tampered(self):
        self.fx.tamper_final_member = True
        self.assert_blocks('FINAL_RUNTIME_MEMBER:control/EXAMPLE.py')

    def test_24_return_member_outside_return_manifest(self):
        self.fx.extra_return['EVIDENCE/INJECTED.txt'] = b'x'
        self.fx.drop_manifest_entry = 'EVIDENCE/INJECTED.txt'
        self.assert_blocks('RETURN_MANIFEST_COVERAGE')

    def test_25_tests_log_missing_one_id(self):
        self.fx.log_ids = self.fx.log_ids[1:]
        self.assert_blocks('TESTS_LOG_RECORDS:1')

    def test_26_tests_log_failed(self):
        self.fx.log_tail = '\nRan 126 tests in 1.0s\n\nFAILED (failures=1)\n'
        self.assert_blocks('TESTS_LOG_NOT_OK')

    def test_27_receipt_bound_to_other_final_zip(self):
        self.fx.receipt_extra = {'SOURCE_SHA256': 'F' * 64}
        self.assert_blocks('QUAL_RECEIPT_FINAL_ZIP_BINDING')

    def test_28_not_elevated(self):
        self.fx.precheck['elevated'] = False
        self.assert_blocks('QUAL_PRECHECK_ELEVATION_SYMLINK')

    def test_29_harness_bound_to_other_code(self):
        self.fx.harness['code_manifest_sha256'] = 'F' * 64
        c, _ = self.assert_blocks('HARNESS_CODE_MANIFEST_MISMATCH')
        self.assertEqual(c['delta_qualification']['tested_code_equals_packaged_code'], 'FAIL')

    def test_30_one_non_pass_id(self):
        self.fx.harness['tests'][7]['status'] = 'FAIL'
        c, _ = self.assert_blocks('NON_PASS_IDS:' + CONTRACT['required_tests'][7])
        self.assertEqual(c['windows_qualification'], 'NOT_PASS')

    def test_31_known_blocker_and_wrong_baseline(self):
        c, _ = self.build(blockers=['R44-B2C'])
        self.assertIn('R44-B2C', c['known_blockers']); self.assertEqual(c['status'], 'INCOMPLETE')
        other = self.t / 'other.zip'; other.write_bytes(b'not the baseline')
        c, _ = self.build(baseline=other)
        self.assertIn('BASELINE_ARCHIVE_SHA256', c['known_blockers'])

    def test_32_no_clobber(self):
        _, out = self.build()
        rz, fz, _, _ = self.fx.make(self.t, 'NC')
        with self.assertRaisesRegex(G.Blocked, 'OUTPUT_EXISTS'):
            G.build(return_zip=rz, final_zip=fz, baseline_archive=BASELINE, known_blockers=[], out_dir=out)


class GenericConsumerHardening(unittest.TestCase):
    def test_40_same_evidence_cannot_prove_two_requirements(self):
        ns = FX.load_consumer()
        contract = {'schema': 'TICKSTORE_QUALIFICATION_CONTRACT_V001',
                    'baseline': dict(status='PASS_HISTORICAL_BYTES_ONLY', archive_sha256='C' * 64, run_sha256='D' * 64,
                                     tests_sha256='E' * 64, code_manifest_sha256='F' * 64),
                    'required_tests': ['t'], 'required_target_proofs': ['p1', 'p2']}
        ev = [{'path': 'same', 'sha256': 'B' * 64}]
        delta = dict(schema='TICKSTORE_CDT15_DELTA_QUALIFICATION_V001', platform='WINDOWS_NTFS_PS51',
                     native_windows=True, code_manifest_sha256='A' * 64, tested_code_equals_packaged_code='PASS',
                     production_execution=False, success=True, tests=[{'id': 't', 'status': 'PASS'}],
                     target_proofs={'p1': {'status': 'PASS', 'evidence': ev}, 'p2': {'status': 'PASS', 'evidence': ev}})
        complete = {'baseline': contract['baseline'], 'baseline_archive_evidence': {'path': 'x', 'sha256': 'C' * 64},
                    'delta_test_totals': {'run': 1, 'failures': 0, 'errors': 0, 'skips': 0},
                    'baseline_results_counted_as_delta': False}

        def require(cond, why):
            if not cond:
                raise G.Blocked(why)
        with self.assertRaisesRegex(G.Blocked, 'DELTA_TARGET_EVIDENCE_REUSED'):
            ns['validate'](complete, contract, delta, 'A' * 64, require)
        delta['target_proofs']['p2'] = {'status': 'PASS', 'evidence': [{'path': 'other', 'sha256': 'C' * 64}]}
        ns['validate'](complete, contract, delta, 'A' * 64, require)
        delta['harness_totals'] = {'tests_run': 0, 'failures': 0, 'errors': 0, 'skips': 0}
        with self.assertRaisesRegex(G.Blocked, 'DELTA_HARNESS_TOTALS'):
            ns['validate'](complete, contract, delta, 'A' * 64, require)

    def test_41_real_contract_requires_typed_provenance(self):
        ns = FX.load_consumer()
        self.assertEqual(set(CONTRACT['required_target_proofs']), set(ns['TYPED_PROOFS']))


class OriginAdversarialScript(unittest.TestCase):
    """The origin's own reproducer, byte-exact, against the current producer and consumer."""

    def test_50_origin_reproducer_now_incomplete_and_rejected(self):
        self.assertEqual(h(ADVERSARIAL.read_bytes()), ADVERSARIAL_SHA)
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            shutil.copytree(R / 'candidate/control', t / 'candidate/control',
                            ignore=shutil.ignore_patterns('__pycache__'))
            (t / 'tests/fixtures').mkdir(parents=True)
            shutil.copy2(BASELINE, t / 'tests/fixtures' / BASELINE.name)
            shutil.copy2(ADVERSARIAL, t / 'reproduce.py')
            r = subprocess.run([sys.executable, '-B', str(t / 'reproduce.py')], capture_output=True, text=True,
                               timeout=300, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        # The reproducer asserts the old false positive; it must now fail that assertion.
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn('AssertionError', r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out['status'], 'INCOMPLETE')
        self.assertTrue(out['self_check'].startswith('REJECTS'))
        for needle in ('NATIVE_PROVENANCE_UNBOUND', 'CODE_MANIFEST_EMPTY', 'HARNESS_RECORD_COUNT:127!=126',
                       'HARNESS_DUPLICATE_RECORDS', 'HARNESS_SUCCESS_NOT_TRUE', 'HARNESS_TOTALS',
                       'HARNESS_PLATFORM_NOT_WINDOWS', 'TARGET_PROOF_EVIDENCE_REUSED', 'TARGET_PROOF_NOT_TYPED_RECEIPT'):
            self.assertTrue(any(needle in b for b in out['blockers']), (needle, out['blockers']))
        self.assertFalse(out['gate_verdict_issued'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
