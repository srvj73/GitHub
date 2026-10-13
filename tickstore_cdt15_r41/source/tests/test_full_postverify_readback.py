"""Source-only exact-contract guards. No productive actions, no Windows runtime required."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'candidate'/'control'))
from FULL_LIFECYCLE import verify_postfull


def good():
    reconciliation = {'schema':'TICKSTORE_MULTIWORK_RECONCILIATION_V001','status':'PASS',
                      'days':1550,'rows':7049522162,'manifest_sha256':'A'*64}
    h2={'deep':{'POST_FULL_AUDIT':'PASS','days':1550,'rows':7049522162,'namespace':3101,
                'manifest_sha256':'A'*64},
        'independent':{'schema':'POSTFULL_INDEPENDENT_VERIFIER_V001','status':'PASS',
                       'days':1550,'rows':7049522162,'namespace_files':3101,
                       'manifest_sha256':'A'*64}}
    return reconciliation,h2


class FullPostverifyReadbackTest(unittest.TestCase):
    def assert_denied(self, mutate, reason):
        reconciliation,h2=good()
        mutate(reconciliation,h2)
        with self.assertRaises(RuntimeError) as cm:verify_postfull(reconciliation,h2)
        self.assertIn(reason,str(cm.exception))

    def test_positive(self):
        r,h=good();self.assertEqual(verify_postfull(r,h),
            {'FINAL_VS_POSTFULL':'PASS','manifest_sha256':'A'*64})

    def test_bad_independent_schema(self):
        self.assert_denied(lambda r,h:h['independent'].update(schema='WRONG'), 'FULL_POSTVERIFY_NOT_PASS')
    def test_independent_fail(self):
        self.assert_denied(lambda r,h:h['independent'].update(status='FAIL'),'FULL_POSTVERIFY_NOT_PASS')
    def test_deep_fail(self):
        self.assert_denied(lambda r,h:h['deep'].update(POST_FULL_AUDIT='FAIL'),'FULL_POSTVERIFY_NOT_PASS')
    def test_independent_manifest_mismatch(self):
        self.assert_denied(lambda r,h:h['independent'].update(manifest_sha256='B'*64),'FULL_INDEPENDENT_READBACK_MISMATCH')
    def test_independent_namespace_mismatch(self):
        self.assert_denied(lambda r,h:h['independent'].update(namespace_files=3100),'FULL_INDEPENDENT_READBACK_MISMATCH')
    def test_independent_days_mismatch(self):
        self.assert_denied(lambda r,h:h['independent'].update(days=1549),'FULL_INDEPENDENT_READBACK_MISMATCH')
    def test_independent_rows_mismatch(self):
        self.assert_denied(lambda r,h:h['independent'].update(rows=0),'FULL_INDEPENDENT_READBACK_MISMATCH')
    def test_reconcile_manifest_mismatch(self):
        self.assert_denied(lambda r,h:r.update(manifest_sha256='B'*64),'FULL_POSTVERIFY_MISMATCH:manifest_sha256')
    def test_reconcile_days_mismatch(self):
        self.assert_denied(lambda r,h:r.update(days=1549),'FULL_POSTVERIFY_MISMATCH:days')
    def test_expected_deep_namespace(self):
        self.assert_denied(lambda r,h:h['deep'].update(namespace=3100),'FULL_POSTVERIFY_EXPECTED:namespace')
    def test_expected_deep_rows(self):
        self.assert_denied(lambda r,h:h['deep'].update(rows=7049522161),'FULL_POSTVERIFY_EXPECTED:rows')
    def test_expected_deep_days(self):
        self.assert_denied(lambda r,h:h['deep'].update(days=1551),'FULL_POSTVERIFY_EXPECTED:days')
    def test_wrong_deep_sha_format(self):
        self.assert_denied(lambda r,h:(h['deep'].update(manifest_sha256='Q'*64),r.update(manifest_sha256='Q'*64)),
                           'FULL_POSTVERIFY_MANIFEST_SHA256')
    def test_independent_bool_count(self):
        self.assert_denied(lambda r,h:h['independent'].update(days=True),'FULL_INDEPENDENT_READBACK_MISMATCH')
    def test_deep_bool_count(self):
        self.assert_denied(lambda r,h:h['deep'].update(days=True),'FULL_POSTVERIFY_EXPECTED:days')
    def test_independent_missing_schema(self):
        self.assert_denied(lambda r,h:h['independent'].pop('schema'), 'FULL_POSTVERIFY_NOT_PASS')


if __name__=='__main__':unittest.main(verbosity=2)
