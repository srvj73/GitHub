"""G5 technical evidence builder: positive path and one negative control per condition."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'candidate/control'))
import G5_EVIDENCE_BUILDER as G  # noqa: E402

BASELINE = R / 'tests/fixtures/V38_NATIVE_QUALIFICATION_RESULT_ORIGINAL_DC73A8C3.zip'
CONTRACT = json.loads((R / 'candidate/control/QUALIFICATION_CONTRACT.json').read_bytes())


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


class Builder(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.t = Path(t.name)
        self.code = self.t / 'CODE.json'
        self.code.write_bytes(json.dumps({'schema': 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001', 'files': []}).encode())
        self.code_sha = h(self.code.read_bytes())
        self.harness = {'schema': 'TICKSTORE_CDT15_EXECUTED_DELTA_V001', 'native_windows': True, 'selection': 'NATIVE',
                        'code_manifest_sha256': self.code_sha, 'tested_code_unchanged': True, 'success': True,
                        'tests': [{'id': i, 'status': 'PASS'} for i in CONTRACT['required_tests']],
                        'totals': {'tests_run': 126, 'failures': 0, 'errors': 0, 'skips': 0}}
        ev = self.t / 'proof_evidence.json'; ev.write_bytes(b'{"native":true}\n')
        self.proofs = {'schema': 'TICKSTORE_G5_TARGET_PROOF_INPUT_V001', 'proofs': {
            n: {'status': 'PASS', 'source': 'fixture', 'evidence': [{'path': str(ev), 'sha256': h(ev.read_bytes())}]}
            for n in CONTRACT['required_target_proofs']}}
        self.n = 0

    def run_build(self, blockers=None):
        self.n += 1
        hp = self.t / ('H%d.json' % self.n); hp.write_bytes(json.dumps(self.harness).encode())
        pp = self.t / ('P%d.json' % self.n); pp.write_bytes(json.dumps(self.proofs).encode())
        out = self.t / ('OUT%d' % self.n)
        c = G.build(harness_result=hp, code_manifest=self.code, baseline_archive=BASELINE, proofs_input=pp,
                    known_blockers=blockers or [], out_dir=out)
        return c, out

    def assert_incomplete(self, c, needle):
        self.assertEqual(c['status'], 'INCOMPLETE')
        self.assertTrue(any(needle in b for b in c['known_blockers']), c['known_blockers'])

    def test_01_complete_only_when_consumer_accepts(self):
        c, out = self.run_build()
        self.assertEqual(c['status'], 'COMPLETE'); self.assertEqual(c['consumer_self_check'], 'ACCEPTS')
        self.assertEqual(c['known_blockers'], []); self.assertEqual(c['windows_qualification'], 'PASS')
        self.assertEqual(c['delta_test_totals'], {'run': 126, 'failures': 0, 'errors': 0, 'skips': 0})
        self.assertEqual(c['baseline_archive_evidence']['sha256'], CONTRACT['baseline']['archive_sha256'])
        # Disk artifacts are bound to each other.
        delta_raw = (out / 'DELTA_QUALIFICATION.json').read_bytes()
        self.assertEqual(c['delta_qualification_evidence']['sha256'], h(delta_raw))
        pack = json.loads((out / 'G5_EVIDENCE_PACK.json').read_bytes())
        self.assertEqual(pack['outputs'][1]['sha256'], h((out / 'ENGINEERING_COMPLETENESS.json').read_bytes()))

    def test_02_never_issues_a_gate_pass(self):
        c, out = self.run_build()
        draft = json.loads((out / 'G5_STAGE_RECEIPT_DRAFT.json').read_bytes())
        self.assertEqual(draft['status'], 'PENDING_ORIGIN_DECISION')
        self.assertFalse(draft['gate_verdict_issued']); self.assertFalse(c['gate_verdict_issued'])
        self.assertIsNone(draft['checks']['features_implemented'])
        self.assertIsNone(draft['checks']['adversarial_completeness']); self.assertIsNone(draft['checks']['byte_freeze'])
        for p in out.iterdir():
            self.assertNotIn(b'"status":"PASS","stage"', p.read_bytes())
        sys.path.insert(0, str(R / 'candidate/control'))
        from FULL_RELEASE_CHAIN import validate_chain
        with self.assertRaises(Exception):
            validate_chain({'G5': draft}, {'G5': 'A' * 64}, code_sha=self.code_sha, instance_sha='B' * 64,
                           b06_sha='C' * 64, until='G5')

    def test_03_one_non_pass_id_blocks(self):
        self.harness['tests'][7]['status'] = 'FAIL'
        c, _ = self.run_build()
        self.assert_incomplete(c, 'NON_PASS_IDS:' + CONTRACT['required_tests'][7])
        self.assertEqual(c['windows_qualification'], 'NOT_PASS')

    def test_04_skip_is_not_pass(self):
        self.harness['tests'][0]['status'] = 'SKIP'
        c, _ = self.run_build(); self.assert_incomplete(c, 'NON_PASS_IDS')

    def test_05_missing_id_blocks(self):
        del self.harness['tests'][3]
        c, _ = self.run_build(); self.assert_incomplete(c, 'HARNESS_ID_SET_NOT_CONTRACT')

    def test_06_portable_selection_cannot_qualify(self):
        self.harness['native_windows'] = False; self.harness['selection'] = 'PORTABLE'
        c, _ = self.run_build(); self.assert_incomplete(c, 'HARNESS_NOT_NATIVE_WINDOWS_SELECTION')

    def test_07_other_code_bytes_block(self):
        self.harness['code_manifest_sha256'] = 'F' * 64
        c, _ = self.run_build(); self.assert_incomplete(c, 'HARNESS_CODE_MANIFEST_MISMATCH')
        self.assertEqual(c['delta_qualification']['tested_code_equals_packaged_code'], 'FAIL')

    def test_08_code_changed_during_run_blocks(self):
        self.harness['tested_code_unchanged'] = False
        c, _ = self.run_build(); self.assert_incomplete(c, 'HARNESS_CODE_CHANGED_DURING_RUN')

    def test_09_missing_target_proof_blocks(self):
        del self.proofs['proofs']['CHECKPOINT_POWERLOSS_RECOVERY']
        c, _ = self.run_build(); self.assert_incomplete(c, 'TARGET_PROOF_MISSING:CHECKPOINT_POWERLOSS_RECOVERY')

    def test_10_tampered_proof_evidence_blocks(self):
        self.proofs['proofs']['PS51_INSTALL_MENU']['evidence'][0]['sha256'] = '0' * 64
        c, _ = self.run_build(); self.assert_incomplete(c, 'TARGET_PROOF_EVIDENCE:PS51_INSTALL_MENU')

    def test_11_proof_without_pass_blocks(self):
        self.proofs['proofs']['D4_CLOSURE_NATIVE_1399']['status'] = 'PENDING'
        c, _ = self.run_build(); self.assert_incomplete(c, 'TARGET_PROOF_NOT_PASS:D4_CLOSURE_NATIVE_1399')

    def test_12_unknown_proof_name_blocks(self):
        self.proofs['proofs']['INVENTED_PROOF'] = copy.deepcopy(self.proofs['proofs']['PS51_INSTALL_MENU'])
        c, _ = self.run_build(); self.assert_incomplete(c, 'TARGET_PROOF_UNKNOWN:INVENTED_PROOF')

    def test_13_known_blocker_prevents_complete(self):
        c, _ = self.run_build(['R43-B1B'])
        self.assert_incomplete(c, 'R43-B1B')

    def test_14_wrong_baseline_archive_blocks(self):
        other = self.t / 'other.zip'; other.write_bytes(b'not the baseline')
        hp = self.t / 'H.json'; hp.write_bytes(json.dumps(self.harness).encode())
        pp = self.t / 'P.json'; pp.write_bytes(json.dumps(self.proofs).encode())
        c = G.build(harness_result=hp, code_manifest=self.code, baseline_archive=other, proofs_input=pp,
                    known_blockers=[], out_dir=self.t / 'OUTB')
        self.assert_incomplete(c, 'BASELINE_ARCHIVE_SHA256')

    def test_15_no_clobber_of_previous_output(self):
        _, out = self.run_build()
        hp = self.t / 'H1.json'; pp = self.t / 'P1.json'
        with self.assertRaisesRegex(G.Blocked, 'OUTPUT_EXISTS'):
            G.build(harness_result=hp, code_manifest=self.code, baseline_archive=BASELINE, proofs_input=pp,
                    known_blockers=[], out_dir=out)

    def test_16_wrong_harness_schema_rejected(self):
        self.harness['schema'] = 'SOMETHING_ELSE'
        with self.assertRaisesRegex(G.Blocked, 'HARNESS_SCHEMA'):
            self.run_build()


if __name__ == '__main__':
    unittest.main(verbosity=2)
