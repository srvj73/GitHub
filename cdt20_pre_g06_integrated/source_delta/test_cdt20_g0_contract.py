"""Sandbox contract tests of the CDT20 PRE-G06 G0 and suite runner. NOT native evidence.

Usage: python -I -B test_cdt20_g0_contract.py <staging-dir-with-transport-members>
"""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

STAGE=Path(sys.argv.pop(1)).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cdt20_g0',STAGE/'G0_CDT20_PRE_G06.py')
G0=importlib.util.module_from_spec(spec);spec.loader.exec_module(G0)

FAILING=b'''import unittest
class T(unittest.TestCase):
    def test_ok(self):pass
    def test_bad(self):self.assertEqual('expected','observed-primary-cause')
if __name__=='__main__':unittest.main()
'''
SKIPPING=b'''import unittest
class T(unittest.TestCase):
    def test_skip(self):self.skipTest('platform')
if __name__=='__main__':unittest.main()
'''
PASSING=b'''import unittest
class T(unittest.TestCase):
    def test_ok(self):pass
if __name__=='__main__':unittest.main()
'''


class G0Contract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cand=self.root/'candidate'
        for f in ('full','control','adapter','g5proof'):(self.cand/f).mkdir(parents=True)
        self.out=self.root/'out';self.out.mkdir()

    def suite(self,name,body):
        p=self.root/'tests'/name;p.parent.mkdir(exist_ok=True);p.write_bytes(body);return p

    def run_suite(self,test,tag):
        return G0.run_suite(sys.executable,STAGE/'G0_SUITE_RUNNER.py',test,self.cand,self.out,self.root/('T_'+tag),{},120)

    def test_failing_suite_exposes_primary_cause_not_only_log_path(self):
        row=self.run_suite(self.suite('test_fail.py',FAILING),'f')
        self.assertEqual(row['status'],'FAIL');self.assertEqual(row['exit_code'],1)
        self.assertIn('test_fail.T.test_bad',row['primary_failure'])
        self.assertIn('observed-primary-cause',row['primary_failure'])

    def test_passing_suite_closed(self):
        row=self.run_suite(self.suite('test_pass.py',PASSING),'p')
        self.assertEqual((row['status'],row['tests_run'],row['skipped']),('PASS',1,[]))
        result=json.loads((self.out/row['result_file']).read_bytes())
        self.assertEqual(result['flags_isolated'],1)
        self.assertEqual(Path(result['temp']),self.root/'T_p')

    def test_runner_crash_is_not_pass(self):
        row=self.run_suite(self.root/'tests/test_absent.py','c')
        self.assertEqual(row['status'],'FAIL');self.assertTrue(row['primary_failure'])

    def test_required_suite_cannot_skip_but_diagnostic_may(self):
        row=self.run_suite(self.suite('test_skip.py',SKIPPING),'s')
        self.assertEqual(row['status'],'PASS');self.assertEqual(len(row['skipped']),1)
        self.assertEqual(G0.gate_row(row,False)['status'],'PASS')
        gated=G0.gate_row(row,True)
        self.assertEqual(gated['status'],'FAIL');self.assertIn('REQUIRED_SUITE_SKIPPED',gated['primary_failure'])

    def test_log_preexisting_is_never_overwritten(self):
        test=self.suite('test_pass.py',PASSING);(self.out/'G0_test_pass.py.log').write_bytes(b'PRIOR')
        row=self.run_suite(test,'x')
        self.assertEqual(row['status'],'FAIL');self.assertEqual((self.out/'G0_test_pass.py.log').read_bytes(),b'PRIOR')

    def test_legacy_diagnostic_reports_cause(self):
        row=G0.legacy_diagnostic(sys.executable,self.suite('test_fail.py',FAILING),self.out)
        self.assertFalse(row['gating']);self.assertEqual(row['status'],'FAIL')
        self.assertIn('observed-primary-cause',row['primary_failure'])

    def stage_copy(self):
        dest=self.root/'stage';dest.mkdir()
        w=json.loads((STAGE/'CDT20_R08Q1_WITNESS.json').read_bytes())
        for name in ('G0_CDT20_PRE_G06.py','G0_SUITE_RUNNER.py','G0_HISTORICAL_NATIVE_G3_G6.json',
                     'CDT20_R08Q1_WITNESS.json',w['package_name']):
            shutil.copy2(STAGE/name,dest/name)
        return dest,w

    def test_tampered_package_blocks_before_extraction(self):
        dest,w=self.stage_copy();p=dest/w['package_name'];raw=bytearray(p.read_bytes());raw[-30]^=1;p.write_bytes(bytes(raw))
        with self.assertRaisesRegex(G0.G0Blocked,'SOURCE_SHA256'):G0.qualify(dest,native=False)
        self.assertFalse((dest/'G0_SOURCES').exists())

    def test_wrong_code_manifest_binding_blocks(self):
        dest,w=self.stage_copy();w['code_manifest_sha256']='F'*64
        (dest/'CDT20_R08Q1_WITNESS.json').write_text(json.dumps(w))
        with self.assertRaisesRegex(G0.G0Blocked,'MANIFEST_SHA256'):G0.qualify(dest,native=False)

    def test_preexisting_extraction_blocks(self):
        dest,_=self.stage_copy();(dest/'G0_SOURCES').mkdir()
        with self.assertRaisesRegex(G0.G0Blocked,'G0_EXTRACT_PREEXISTING'):G0.qualify(dest,native=False)

    def test_historical_fixture_tamper_blocks(self):
        dest,_=self.stage_copy();p=dest/'G0_HISTORICAL_NATIVE_G3_G6.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(G0.G0Blocked,'REAL_SCENARIO_SHA'):G0.qualify(dest,native=False)

    def test_main_refuses_non_windows(self):
        if G0.os.name=='nt':self.skipTest('POSIX negative only')
        with self.assertRaisesRegex(G0.G0Blocked,'WIN_PYTHON_314_X64'):G0.main()


if __name__=='__main__':unittest.main(verbosity=2)
