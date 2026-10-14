"""R45 (B07 integrated, SOURCE_ONLY execution gate): physical binding, B06 verdict binding, per-check receipts.

Synthetic UNIT FIXTURES only.  The produced technical receipt is checked against the unmodified
D4_FIRST_ADMISSION_TRANSACTION.B07_CHECKS contract.

R45 B07-PROVENANCE-01: the producer verifies the policy capture itself from physical bytes (the R40
capture fixture plus a reconciliation UNIT FIXTURE written to a private temp dir and deleted with it;
it is marked unit_fixture_not_origin_record and is never an origin record).  A caller-supplied
capture dictionary is refused.  Off Windows the reader is optimistic, so the only admissible
finding there is POLICY_CAPTURE_READ_NOT_NATIVE_PROTECTED; natively the same evidence yields PASS.
R45 B07-ORDER-01: produced_after_independent_b06 mirrors the verdict verified by the producer.
"""
import datetime as dt
import hashlib
import importlib.util
import io
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
SRC = HERE.parent
sys.path.insert(0, str(SRC / 'tests'))
import g5_native_fixture as FX  # noqa: E402

TMP = None
NATIVE = os.name == 'nt'
NOT_NATIVE = 'POLICY_CAPTURE_READ_NOT_NATIVE_PROTECTED'
R40 = SRC / 'tests/fixtures/R40_CAPTURE_NON_AUTHORITATIVE'
V38 = SRC / 'tests/fixtures/V38_CAPTURE_HISTORICAL'
NOW = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)


def h(b):
    return hashlib.sha256(b).hexdigest().upper()


def setUpModule():
    global TMP, P, T
    TMP = Path(tempfile.mkdtemp(prefix='b07_'))
    ctl = TMP / 'control'; shutil.copytree(SRC / 'candidate/control', ctl, ignore=shutil.ignore_patterns('__pycache__'))
    # The producer under test is the packaged one (its sealed reader needs candidate/recovery/engine).
    sys.path.insert(0, str(SRC / 'candidate/control'))
    import B07_TECHNICAL_PRODUCER as P  # noqa
    import D4_FIRST_ADMISSION_TRANSACTION as T  # noqa
    globals().update(P=P, T=T)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


TX_IDS = ['test_first_admission_transaction.TransactionTests.test_%02d' % i for i in range(22)]
def reconciliation(t, *, master=None, head=None, revision=None, until_hours=24, name='RECONCILIATION.json'):
    hd = json.loads((R40 / 'POLITICA_CANONICA_HEAD.json').read_bytes())
    rec = {'schema': 'TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001', 'issuer': 'CHATGPT_ORIGIN', 'status': 'CURRENT_AT_ORIGIN',
           'unit_fixture_not_origin_record': True,
           'policy_master_sha256': master or h((R40 / 'POLITICA_CANONICA_UNIFICADA_OPERACIONAL.md').read_bytes()),
           'policy_head_sha256': head or h((R40 / 'POLITICA_CANONICA_HEAD.json').read_bytes()),
           'policy_revision': revision or hd['revision_id'], 'live_cardinality': {'master': 1, 'head': 1},
           'live_state': 'FROZEN', 'capture_operational_authority': False, 'administrative_owner_gate_required': False,
           'scope': ['D4_FIRST_ADMISSION'], 'routing_project': 'Base de Dados CSV / Tickstore',
           'routing_thread': 'Compress\u00e3o De Ticks 15', 'reconciled_at': '2026-10-14T00:00:00+00:00',
           'valid_until': (dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc) + dt.timedelta(hours=until_hours)).isoformat()}
    p = t / name; p.write_bytes(json.dumps(rec, sort_keys=True).encode('utf-8'))
    return p, h(p.read_bytes())


VERDICT = b'B06 INDEPENDENT REVIEW\nVERDICT=PASS\nINDEPENDENT_REVIEW=YES\nTESTED_CODE_EQUALS_PACKAGED_CODE=YES\nCRITICAL_FINDINGS=0\nMAJOR_FINDINGS=0\n'
# R44 shape of the forged input the producer must now refuse (B07-PROVENANCE-01 negative control).
FORGED_CAPTURE = {'schema': 'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001', 'master_sha256': '1' * 64, 'head_sha256': '2' * 64,
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
        self.policy = self.t / 'policy'; shutil.copytree(R40, self.policy)
        self.rec, self.rec_sha = reconciliation(self.t)

    def build(self, verdict_sha=None, policy=None, rec=None, rec_sha=None, verdict=None, **extra):
        self.n += 1
        rz, fz, code_sha = self.fx.make(self.t, str(self.n))
        kw = dict(return_zip=rz, final_zip=fz, b06_verdict=verdict or self.verdict,
                  b06_verdict_sha256=verdict_sha or h(VERDICT), policy_root=policy or self.policy,
                  policy_reconciliation=rec or self.rec, policy_reconciliation_sha256=rec_sha or self.rec_sha,
                  out_path=self.t / ('B07_%d.json' % self.n), transaction_test_ids=TX_IDS, now=NOW)
        kw.update(extra)
        return P.build(**kw), code_sha

    def effective(self, r):
        """Findings other than the platform marker that only native protected reads can clear."""
        return [f for f in r['findings'] if not (f == NOT_NATIVE and not NATIVE)]

    def not_pass(self, needle, **kw):
        r, _ = self.build(**kw)
        self.assertEqual(r['status'], 'NOT_PASS')
        self.assertTrue(any(needle in f for f in r['findings']), r['findings'])
        return r

    def policy_not_verified(self, needle, **kw):
        r = self.not_pass('POLICY_CAPTURE_NOT_VERIFIED', **kw)
        self.assertTrue(any(needle in f for f in r['findings']), r['findings'])
        self.assertEqual(r['policy']['verified_by'], 'NOT_VERIFIED')
        self.assertIsNone(r['policy']['master_sha256']); self.assertIsNone(r['policy']['reconciliation_sha256'])
        return r

    def test_01_complete_native_evidence_yields_consumer_shaped_receipt(self):
        r, code_sha = self.build()
        self.assertEqual(self.effective(r), [])
        self.assertEqual(r['status'], 'PASS' if NATIVE else 'NOT_PASS')
        self.assertEqual(set(r['checks']), set(T.B07_CHECKS))
        self.assertFalse(r['gate_verdict_issued'])
        self.assertEqual(r['review_verdict_sha256'], h(VERDICT)); self.assertEqual(r['platform'], 'WINDOWS_NTFS_PS51')
        self.assertTrue(all(v == 'PASS' for v in r['checks'].values()))
        pol = r['policy']
        self.assertEqual((pol['master_sha256'], pol['head_sha256'], pol['reconciliation_sha256']),
                         (h((R40 / 'POLITICA_CANONICA_UNIFICADA_OPERACIONAL.md').read_bytes()),
                          h((R40 / 'POLITICA_CANONICA_HEAD.json').read_bytes()), self.rec_sha))
        self.assertEqual(pol['verified_by'], 'POLICY_CAPTURE_BINDING.verify_capture')
        self.assertEqual(pol['read_mode'], 'WIN32_PROTECTED_HANDLES' if NATIVE else 'POSIX_OPTIMISTIC_NOT_NATIVE')
        self.assertEqual(pol['binding_module_sha256'],
                         json.loads((SRC / 'candidate/control/FIRST_ADMISSION_BINDING.json').read_bytes())['policy_capture_binding_sha256'])
        self.assertIs(r['produced_after_independent_b06'], True); self.assertEqual(r['b06_independent_verdict'], 'VERIFIED_PASS')

    def test_02_b06_verdict_must_be_independent_pass_and_digest_supplied(self):
        r = self.not_pass('B06_VERDICT_SHA256_SUPPLIED_SEPARATELY', verdict_sha='0' * 64)
        self.assertIs(r['produced_after_independent_b06'], False)
        self.verdict.write_bytes(VERDICT.replace(b'INDEPENDENT_REVIEW=YES', b'INDEPENDENT_REVIEW=NO'))
        r = self.not_pass('B06_VERDICT_FIELD:INDEPENDENT_REVIEW', verdict_sha=h(self.verdict.read_bytes()))
        self.assertIs(r['produced_after_independent_b06'], False); self.assertEqual(r['b06_independent_verdict'], 'NOT_VERIFIED')

    def test_02b_order_missing_or_failing_b06_never_claims_after_b06(self):
        """B07-ORDER-01: absent, failing or critical B06 verdicts never yield produced_after_independent_b06."""
        r = self.not_pass('B06_VERDICT_MISSING', verdict=self.t / 'ABSENT_VERDICT.txt')
        self.assertIs(r['produced_after_independent_b06'], False); self.assertIsNone(r['review_verdict_sha256'])
        for old, new, field in ((b'VERDICT=PASS', b'VERDICT=FAIL', 'VERDICT'),
                                (b'CRITICAL_FINDINGS=0', b'CRITICAL_FINDINGS=1', 'CRITICAL_FINDINGS'),
                                (b'MAJOR_FINDINGS=0', b'MAJOR_FINDINGS=2', 'MAJOR_FINDINGS')):
            bad = self.t / ('V_%s.txt' % field); bad.write_bytes(VERDICT.replace(old, new))
            r = self.not_pass('B06_VERDICT_FIELD:' + field, verdict=bad, verdict_sha=h(bad.read_bytes()))
            self.assertIs(r['produced_after_independent_b06'], False)
            self.assertEqual(r['b06_independent_verdict'], 'NOT_VERIFIED')

    def test_02c_order_flag_reflects_b06_state_not_overall_status(self):
        self.fx.drop = {'checkpoint_failure_controls'}
        r = self.not_pass('checkpoint_failure_controls:CHECK_RECEIPT_MISSING')
        self.assertIs(r['produced_after_independent_b06'], True)
        self.assertEqual(r['b06_independent_verdict'], 'VERIFIED_PASS')

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
        self.policy_not_verified('POLICY_CARDINALITY_1_PLUS_1', policy=self.empty_dir())

    def empty_dir(self):
        d = self.t / ('empty_%d' % self.n); d.mkdir(); return d

    def test_05_transaction_check_needs_every_contract_id(self):
        self.fx.over = {'first_admission_transaction': {'tests': [{'id': i, 'status': 'PASS'} for i in TX_IDS[:-1]]}}
        self.not_pass('first_admission_transaction:RECEIPT_TESTS')

    def test_06_no_clobber(self):
        rz, fz, _ = self.fx.make(self.t, 'nc'); out = self.t / 'B07_nc.json'
        kw = dict(return_zip=rz, final_zip=fz, b06_verdict=self.verdict, b06_verdict_sha256=h(VERDICT), policy_root=self.policy,
                  policy_reconciliation=self.rec, policy_reconciliation_sha256=self.rec_sha, out_path=out,
                  transaction_test_ids=TX_IDS, now=NOW)
        P.build(**kw)
        with self.assertRaisesRegex(RuntimeError, 'B07_RECEIPT_EXISTS'):
            P.build(**kw)

    # ---- B07-PROVENANCE-01 adversarial controls -------------------------------------------------
    def test_07_caller_supplied_capture_dictionary_is_refused(self):
        rz, fz, _ = self.fx.make(self.t, 'forged')
        with self.assertRaises(TypeError):
            P.build(return_zip=rz, final_zip=fz, b06_verdict=self.verdict, b06_verdict_sha256=h(VERDICT),
                    policy_capture=FORGED_CAPTURE, out_path=self.t / 'B07_forged.json', transaction_test_ids=TX_IDS)
        self.assertFalse((self.t / 'B07_forged.json').exists())

    def test_08_fictitious_reconciliation_identities_block(self):
        for kw in ({'master': '1' * 64}, {'head': '2' * 64}, {'revision': '20261013T070500-0300-1111111111111111'}):
            rec, rec_sha = reconciliation(self.t, name='FORGED_%d.json' % self.n, **kw)
            self.policy_not_verified('POLICY_RECONCILIATION_BINDING', rec=rec, rec_sha=rec_sha)

    def test_09_reconciliation_digest_supplied_separately(self):
        self.policy_not_verified('SHA_MISMATCH', rec_sha='3' * 64)
        self.policy_not_verified('POLICY_RECONCILIATION_SHA_FORMAT', rec_sha='not-a-digest')
        self.policy_not_verified('', rec=self.t / 'ABSENT_RECONCILIATION.json')

    def test_10_forged_or_historical_capture_bytes_block(self):
        v38 = self.t / 'v38'; shutil.copytree(V38, v38)
        self.policy_not_verified('POLICY_HISTORICAL_NOT_CURRENT:V38', policy=v38)
        tam = self.t / 'tamper'; shutil.copytree(R40, tam)
        with open(tam / 'POLITICA_CANONICA_UNIFICADA_OPERACIONAL.md', 'ab') as f:
            f.write(b'\n')
        self.policy_not_verified('POLICY_HEAD_MASTER', policy=tam)
        extra = self.t / 'extra'; shutil.copytree(R40, extra); (extra / 'NOTE.txt').write_bytes(b'x')
        self.policy_not_verified('POLICY_CARDINALITY_1_PLUS_1', policy=extra)
        ni = self.t / 'NOT_ISSUED.json'
        ni.write_bytes(b'{"schema":"TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001","status":"NOT_ISSUED"}')
        self.policy_not_verified('POLICY_RECONCILIATION_SCHEMA', rec=ni, rec_sha=h(ni.read_bytes()))

    def test_11_expired_or_overlong_reconciliation_blocks(self):
        rec, rec_sha = reconciliation(self.t, until_hours=6, name='SHORT.json')
        self.policy_not_verified('POLICY_RECONCILIATION_EXPIRED_OR_FUTURE', rec=rec, rec_sha=rec_sha)
        rec, rec_sha = reconciliation(self.t, until_hours=96, name='LONG.json')
        self.policy_not_verified('POLICY_RECONCILIATION_WINDOW_TOO_LONG', rec=rec, rec_sha=rec_sha)

    def test_12_verifier_module_admitted_only_by_sealed_digest(self):
        ctl = self.t / 'ctl_tampered'; shutil.copytree(SRC / 'candidate/control', ctl,
                                                        ignore=shutil.ignore_patterns('__pycache__'))
        with open(ctl / 'POLICY_CAPTURE_BINDING.py', 'ab') as f:
            f.write(b'\n# tampered\n')
        spec = importlib.util.spec_from_file_location('b07_tampered_producer', ctl / 'B07_TECHNICAL_PRODUCER.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        capture, mode, findings = mod.verify_policy(self.policy, self.rec, self.rec_sha, now=NOW)
        self.assertIsNone(capture)
        self.assertTrue(any(f.startswith('POLICY_CAPTURE_NOT_VERIFIED:') for f in findings), findings)
        if not NATIVE:
            self.assertTrue(any('SHA_MISMATCH' in f for f in findings), findings)


class RunnerGuard(unittest.TestCase):
    def test_10_runner_refuses_off_windows_and_without_b06_chain(self):
        runner = SRC / 'candidate/b07/B07_CHECK_RUNNERS.py'
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
