"""G4 source-only CANARY closure controls. Never executes frozen orchestrator or production."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent / 'candidate'
sys.path.insert(0, str(ROOT / 'control'))
import FULL_STAGE_CONTINUATION as sut


def valid_results():
    return {
        'D9': {k: 'PASS' for k in ('R1', 'R2', 'R3', 'R4', 'R5')},
        'D6': {'PASS': True}, 'D7': {'PASS': True},
        'E1': {
            'deep': {'POST_FULL_AUDIT': 'PASS', 'days': 1550, 'rows': 7049522162,
                     'namespace': 3101, 'manifest_sha256': 'A' * 64},
            'independent': {'schema': 'POSTFULL_INDEPENDENT_VERIFIER_V001',
                            'status': 'PASS', 'days': 1550, 'rows': 7049522162,
                            'namespace_files': 3101, 'manifest_sha256': 'A' * 64}
        }
    }

class CanaryPublishedOnlyWithReconciledProof(unittest.TestCase):
    def call(self, results):
        with tempfile.TemporaryDirectory(prefix='cdt15_canary_sourceonly_') as d:
            d = Path(d)
            state = {'schema': 'TICKSTORE_ORCH_STATE_V001', 'status': 'PASS', 'next_node': 'E2', 'completed': []}
            sp = d / 'STATE.json'; jp = d / 'STATE_JOURNAL.jsonl'
            sp.write_bytes(sut.canonical(state))
            jp.write_bytes(sut.canonical({'prev_line_sha256': ''}))
            o = types.SimpleNamespace(st=types.SimpleNamespace(sp=sp, jp=jp, d=state, runs=d / 'runs'), rd=d)
            ns = {'immutable_receipt': lambda *args: None}
            admit = types.SimpleNamespace(revalidate=lambda: None)
            with patch.object(sut, 'closed_results', return_value=(results, [])), patch.object(sut, 'publish', return_value=('STAGE_CANARY.json', 'SHA')) as pub:
                try:
                    output = sut.publish_stage(o, ns, types.SimpleNamespace(stage='CANARY', nodes=()), admit)
                except Exception as e:
                    return False, str(e), pub.called
                return True, output, pub.called

    def test_positive_exact_consistent_frozen_outputs(self):
        ok, result, called = self.call(valid_results())
        self.assertTrue(ok, result); self.assertTrue(called)

    def assert_blocks(self, data, reason):
        ok, message, called = self.call(data)
        self.assertFalse(ok, 'Inconsistent receipt unexpectedly published')
        self.assertIn(reason, message)
        self.assertFalse(called, 'Must reject before stage receipt publication')

    def test_deep_fail_does_not_publish(self):
        x=valid_results();x['E1']['deep']['POST_FULL_AUDIT']='FAIL';self.assert_blocks(x, 'CANARY_READBACK')
    def test_missing_deep_does_not_publish(self):
        x=valid_results();del x['E1']['deep'];self.assert_blocks(x, 'CANARY_READBACK')
    def test_bad_independent_status_does_not_publish(self):
        x=valid_results();x['E1']['independent']['status']='BLOCKED';self.assert_blocks(x, 'CANARY_READBACK')
    def test_wrong_independent_schema_does_not_publish(self):
        x=valid_results();x['E1']['independent']['schema']='OTHER';self.assert_blocks(x, 'CANARY_READBACK')
    def test_days_mismatch_does_not_publish(self):
        x=valid_results();x['E1']['independent']['days']=1549;self.assert_blocks(x, 'CANARY_INDEPENDENT_READBACK_MISMATCH')
    def test_rows_mismatch_does_not_publish(self):
        x=valid_results();x['E1']['independent']['rows']=1;self.assert_blocks(x, 'CANARY_INDEPENDENT_READBACK_MISMATCH')
    def test_manifest_mismatch_does_not_publish(self):
        x=valid_results();x['E1']['independent']['manifest_sha256']='B'*64;self.assert_blocks(x, 'CANARY_INDEPENDENT_READBACK_MISMATCH')
    def test_namespace_mismatch_does_not_publish(self):
        x=valid_results();x['E1']['independent']['namespace_files']=3100;self.assert_blocks(x, 'CANARY_INDEPENDENT_READBACK_MISMATCH')
    def test_deep_rows_not_native_expected_does_not_publish(self):
        x=valid_results();x['E1']['deep']['rows']=1;x['E1']['independent']['rows']=1;self.assert_blocks(x, 'CANARY_INDEPENDENT_READBACK_MISMATCH')
    def test_bool_as_day_count_does_not_publish(self):
        x=valid_results();x['E1']['deep']['days']=True;self.assert_blocks(x, 'CANARY_INDEPENDENT_READBACK_MISMATCH')
    def test_missing_d9_negative_control_does_not_publish(self):
        x=valid_results();del x['D9']['R3'];self.assert_blocks(x, 'CANARY_CONTROLS_INCOMPLETE')
    def test_d6_not_pass_does_not_publish(self):
        x=valid_results();x['D6']['PASS']=False;self.assert_blocks(x, 'CANARY_PRECHECKS')

if __name__ == '__main__':
    unittest.main(verbosity=2)
