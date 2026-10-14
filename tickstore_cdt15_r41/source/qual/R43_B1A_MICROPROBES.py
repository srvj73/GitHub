"""R43 B1A microprobes on the ORIGIN-AUTHORIZED derived tests_full_lifecycle fixture.

Separately proves, on the current product bytes (FULL_LIFECYCLE.verify_postfull):
  (a) the derived valid fixture reaches H3 and H6;
  (b) divergent reconciliation.rows -> FULL_POSTVERIFY_MISMATCH:rows (not EXPECTED), H4 not run;
  (c) deep.rows outside the certificate -> FULL_POSTVERIFY_EXPECTED:rows;
  (d) invalid independent.schema blocks (FULL_POSTVERIFY_NOT_PASS);
  (e) divergent independent.namespace_files blocks (FULL_INDEPENDENT_READBACK_MISMATCH).
Loaded from the extracted R3 harness tree with the derived file overlaid; not one of the 126 IDs.
"""
import sys
import unittest

import tests_full_lifecycle as derived  # the overlaid, hash-verified derived copy


class B1AMicroprobes(derived.FullLifecycle):
    def test_a_valid_fixture_reaches_h3_and_h6(self):
        self.assertEqual(self.execute(), 0)
        self.assertIn('H3', self.state.d['completed'])
        self.assertIn('H6', self.executed)
        self.assertEqual(self.state.d['next_node'], 'I1')

    def test_b_reconciliation_rows_mismatch_not_expected_guard(self):
        self.rec['rows'] = 7049522162 + 1
        with self.assertRaises(RuntimeError) as ctx:
            self.execute()
        self.assertIn('FULL_POSTVERIFY_MISMATCH:rows', str(ctx.exception))
        self.assertNotIn('EXPECTED', str(ctx.exception))
        self.assertEqual(self.state.d['next_node'], 'H3')
        self.assertNotIn('H4', self.executed)

    def test_c_deep_rows_outside_certificate_expected_guard(self):
        self.h2['deep']['rows'] = 7049522162 + 1
        with self.assertRaisesRegex(RuntimeError, 'FULL_POSTVERIFY_EXPECTED:rows'):
            self.execute()
        self.assertNotIn('H4', self.executed)

    def test_d_invalid_independent_schema_blocks(self):
        self.h2['independent']['schema'] = 'POSTFULL_INDEPENDENT_VERIFIER_V000'
        with self.assertRaisesRegex(RuntimeError, 'FULL_POSTVERIFY_NOT_PASS'):
            self.execute()
        self.assertNotIn('H4', self.executed)

    def test_e_independent_namespace_mismatch_blocks(self):
        self.h2['independent']['namespace_files'] = 3100
        with self.assertRaisesRegex(RuntimeError, 'FULL_INDEPENDENT_READBACK_MISMATCH'):
            self.execute()
        self.assertNotIn('H4', self.executed)


PROBES = ['test_a_valid_fixture_reaches_h3_and_h6', 'test_b_reconciliation_rows_mismatch_not_expected_guard',
          'test_c_deep_rows_outside_certificate_expected_guard', 'test_d_invalid_independent_schema_blocks',
          'test_e_independent_namespace_mismatch_blocks']


def suite():
    # Only the five probes; the inherited 18 historical methods are not re-run here.
    return unittest.TestSuite(B1AMicroprobes(name) for name in PROBES)


if __name__ == '__main__':
    r = unittest.TextTestRunner(verbosity=2).run(suite())
    sys.exit(0 if r.wasSuccessful() and r.testsRun == 5 else 2)
