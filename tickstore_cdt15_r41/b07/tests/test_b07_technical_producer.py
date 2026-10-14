"""B07 technical producer (SOURCE_ONLY): physical binding, B06 verdict binding, per-check receipts.

Synthetic UNIT FIXTURES only.  The produced technical receipt is checked against the unmodified
D4_FIRST_ADMISSION_TRANSACTION.B07_CHECKS contract.
"""
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOP = HERE.parents[1]
SRC = TOP / 'source'
sys.path.insert(0, str(SRC / 'tests'))
import g5_native_fixture as FX  # noqa: E402

TMP = None


def h(b):
    return hashlib.sha256(b).hexdigest().upper()


def setUpModule():
    global TMP, P, T
    TMP = Path(tempfile.mkdtemp(prefix='b07_'))
    ctl = TMP / 'control'; shutil.copytree(SRC / 'candidate/control', ctl, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(HERE.parent / 'candidate_overlay/control/B07_TECHNICAL_PRODUCER.py', ctl)
    sys.path.insert(0, str(ctl))
    import B07_TECHNICAL_PRODUCER as P  # noqa
    import D4_FIRST_ADMISSION_TRANSACTION as T  # noqa
    globals().update(P=P, T=T)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


TX_IDS = ['test_first_admission_transaction.TransactionTests.test_%02d' % i for i in range(22)]
VERDICT = b'B06 INDEPENDENT REVIEW\nVERDICT=PASS\nINDEPENDENT_REVIEW=YES\nTESTED_CODE_EQUALS_PACKAGED_CODE=YES\nCRITICAL_FINDINGS=0\nMAJOR_FINDINGS=0\n'
CAPTURE = {'schema': 'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001', 'master_sha256': '1' * 64, 'head_sha256': '2' * 64,
           'revision_id': 'R', 'reconciliation_sha256': '3' * 64}


class Fixture:
    def __init__(self):
        self.q = FX.load_consumer()
        self.code = {'control/EXAMPLE.py': b'x\n', 'b07/B07_CHECK_RUNNERS.py': b'# runner (fixture)\n'}
        self.over = {}
        self.drop = set()

    def make(self, t, tag):
        fx = FX.NativeFixture(self.q); fx.code = dict(self.code)
        final_raw, code_sha = fx.final_zip(); final_sha = h(final_raw)
        run_id = 'B07_RUN_FIXTURE'
        qr = {'schema': 'TICKSTORE_CDT15_WINDOWS_QUALIFICATION_RECEIPT_V003', 'mode': 'NATIVE_WINDOWS', 'RUN_ID': run_id,
              'SOURCE_SHA256': final_sha, 'RUNTIME_CODE_MANIFEST_SHA256': code_sha,
              'TESTED_CODE_EQUALS_PACKAGED_CODE': 'PASS_TESTS_EXECUTED_FROM_EXTRACTED_FINAL_PACKAGE',
              'PRODUCTION_MODIFIED': False, 'FULL_STARTED': False, 'PRECHECK': dict(fx.precheck)}
        members = {'QUAL_RECEIPT.json': FX.j(qr)}
        for name, spec in P.CHECKS.items():
            if name in self.drop:
                continue
            ids = []
            for x in spec['tests']:
                ids += TX_IDS if x.startswith('ALL:') else [x]
            art = 'EVIDENCE/B07/%s/CHECK_LOG.txt' % name; body = ('log ' + name).encode()
            rec = {'schema': P.CHECK_SCHEMA, 'check': name, 'status': 'PASS', 'native_windows': True,
                   'code_manifest_sha256': code_sha, 'final_zip_sha256': final_sha, 'run_id': run_id,
                   'runner': {'path': P.RUNNER, 'sha256': h(self.code['b07/B07_CHECK_RUNNERS.py'])},
                   'tests': [{'id': i, 'status': 'PASS'} for i in ids], 'probes': dict.fromkeys(spec['probes'], 'PASS'),
                   'artifacts': [{'member': art, 'sha256': h(body)}]}
            rec.update(self.over.get(name, {}))
            members['EVIDENCE/B07/%s/CHECK_RECEIPT.json' % name] = FX.j(rec); members[art] = body
        members['RETURN_MANIFEST.json'] = FX.j({'schema': self.q['RETURN_MANIFEST_SCHEMA'],
            'files': [{'path': n, 'bytes': len(b), 'sha256': h(b)} for n, b in sorted(members.items())]})
        rz = t / ('B07_RETURN_%s.zip' % tag); rz.write_bytes(FX.zip_bytes(members))
        fz = t / ('FINAL_%s.zip' % tag); fz.write_bytes(final_raw)
        return rz, fz, code_sha


class Producer(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.t = Path(t.name)
        self.fx = Fixture(); self.n = 0
        self.verdict = self.t / 'B06_VERDICT.txt'; self.verdict.write_bytes(VERDICT)

    def build(self, verdict_sha=None, capture=CAPTURE):
        self.n += 1
        rz, fz, code_sha = self.fx.make(self.t, str(self.n))
        return P.build(return_zip=rz, final_zip=fz, b06_verdict=self.verdict, b06_verdict_sha256=verdict_sha or h(VERDICT),
                       policy_capture=capture, out_path=self.t / ('B07_%d.json' % self.n), transaction_test_ids=TX_IDS), code_sha

    def not_pass(self, needle, **kw):
        r, _ = self.build(**kw)
        self.assertEqual(r['status'], 'NOT_PASS')
        self.assertTrue(any(needle in f for f in r['findings']), r['findings'])
        return r

    def test_01_complete_native_evidence_yields_consumer_shaped_receipt(self):
        r, code_sha = self.build()
        self.assertEqual(r['findings'], []); self.assertEqual(r['status'], 'PASS')
        self.assertEqual(set(r['checks']), set(T.B07_CHECKS))
        self.assertFalse(r['gate_verdict_issued'])
        self.assertEqual(r['review_verdict_sha256'], h(VERDICT)); self.assertEqual(r['platform'], 'WINDOWS_NTFS_PS51')
        self.assertTrue(all(v == 'PASS' for v in r['checks'].values()))

    def test_02_b06_verdict_must_be_independent_pass_and_digest_supplied(self):
        self.not_pass('B06_VERDICT_SHA256_SUPPLIED_SEPARATELY', verdict_sha='0' * 64)
        self.verdict.write_bytes(VERDICT.replace(b'INDEPENDENT_REVIEW=YES', b'INDEPENDENT_REVIEW=NO'))
        self.not_pass('B06_VERDICT_FIELD:INDEPENDENT_REVIEW', verdict_sha=h(self.verdict.read_bytes()))

    def test_03_missing_check_or_failed_test_or_probe(self):
        self.fx.drop = {'policyroot_mutation_denial'}
        self.not_pass('policyroot_mutation_denial:CHECK_RECEIPT_MISSING')
        self.fx.drop = set()
        self.fx.over = {'state_cas_and_continuity': {'tests': [{'id': 'x', 'status': 'PASS'}]}}
        self.not_pass('state_cas_and_continuity:RECEIPT_TESTS')
        self.fx.over = {'wrapper_safe_stop_exit_propagation': {'probes': {'wrapper_blocks_without_chain_exit_2': 'FAIL'}}}
        self.not_pass('wrapper_safe_stop_exit_propagation:RECEIPT_PROBES')

    def test_04_binding_runner_and_policy(self):
        self.fx.over = {'g_ca_native_locator': {'run_id': 'OTHER'}}
        self.not_pass('g_ca_native_locator:RECEIPT_RUN_BINDING')
        self.fx.over = {'checkpoint_failure_controls': {'runner': {'path': 'elsewhere.py', 'sha256': 'A' * 64}}}
        self.not_pass('checkpoint_failure_controls:RECEIPT_RUNNER_NOT_PACKAGED')
        self.fx.over = {}
        self.not_pass('POLICY_CAPTURE_REQUIRED', capture=None)

    def test_05_transaction_check_needs_every_contract_id(self):
        self.fx.over = {'first_admission_transaction': {'tests': [{'id': i, 'status': 'PASS'} for i in TX_IDS[:-1]]}}
        self.not_pass('first_admission_transaction:RECEIPT_TESTS')

    def test_06_no_clobber(self):
        rz, fz, _ = self.fx.make(self.t, 'nc'); out = self.t / 'B07_nc.json'
        kw = dict(return_zip=rz, final_zip=fz, b06_verdict=self.verdict, b06_verdict_sha256=h(VERDICT), policy_capture=CAPTURE,
                  out_path=out, transaction_test_ids=TX_IDS)
        P.build(**kw)
        with self.assertRaisesRegex(RuntimeError, 'B07_RECEIPT_EXISTS'):
            P.build(**kw)


class RunnerGuard(unittest.TestCase):
    def test_10_runner_refuses_off_windows_and_without_b06_chain(self):
        runner = HERE.parent / 'candidate_overlay/b07/B07_CHECK_RUNNERS.py'
        args = []
        for k in ('chain-file', 'chain-sha256', 'b06-sha256', 'evidence', 'work', 'run-id', 'final-zip-sha256',
                  'code-manifest-sha256', 'policy-root', 'policy-reconciliation', 'policy-reconciliation-sha256',
                  'r3-tree', 'tests-dir', 'qual-dir'):
            args += ['--' + k, 'X']
        work = TMP / 'cand'; (work / 'b07').mkdir(parents=True, exist_ok=True)
        shutil.copy2(runner, work / 'b07'); shutil.copytree(TMP / 'control', work / 'control', dirs_exist_ok=True)
        r = subprocess.run([sys.executable, '-B', str(work / 'b07/B07_CHECK_RUNNERS.py')] + args, capture_output=True,
                           text=True, timeout=120)
        self.assertEqual(r.returncode, 2)
        self.assertIn('B07_BLOCKED=', r.stdout)
        src = runner.read_text(encoding='utf-8')
        self.assertIn("until='B06'", src)
        self.assertLess(src.index('require_b06_pass(a.chain_file'), src.index('for name, spec in P.CHECKS.items()'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
