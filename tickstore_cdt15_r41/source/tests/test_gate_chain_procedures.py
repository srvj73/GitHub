"""R45 completeness: gate-chain procedures without dedicated coverage (audit G2, G10).

G2   FULL_INSTANCE_PREPARE.assemble_chain builds the chain up to B06 (input of the B07 runner)
     or up to B07 (input of D4), and nothing else.
G10  Stage publication branches: D5 certificate readback, FULL_PREP Stage B preparation, FULL_ADMIT
     consumption of the Stage B review (F1 FULL_GO) and full_admission_facts (bindings, census,
     writer lock, root identities, VSS generation).  Synthetic fixtures only; the frozen orchestrator,
     engine and production are never executed.
"""
import base64
import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

R = Path(__file__).resolve().parents[1]
C = R / 'candidate'
sys.path.insert(0, str(C / 'control'))
sys.path.insert(0, str(C / 'full'))
import FULL_STAGE_CONTINUATION as cont  # noqa: E402
import FULL_INSTANCE_PREPARE as prep  # noqa: E402
from FULL_RELEASE_CHAIN import REQUIRED_CHECKS  # noqa: E402


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


class StagePublication(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.d = Path(t.name)

    def call(self, stage, state, results, extra_setup=None):
        sp = self.d / 'STATE.json'; jp = self.d / 'STATE_JOURNAL.jsonl'
        sp.write_bytes(cont.canonical(state)); jp.write_bytes(cont.canonical({'prev_line_sha256': ''}))
        o = types.SimpleNamespace(st=types.SimpleNamespace(sp=sp, jp=jp, d=state, runs=self.d / 'runs',
                                                           inbox=self.d / 'inbox'), rd=self.d, control=self.d / 'control')
        if extra_setup:
            extra_setup(o)
        admit = types.SimpleNamespace(revalidate=lambda: None)
        with patch.object(cont, 'closed_results', return_value=(results, [])), \
                patch.object(cont, 'publish', return_value=('STAGE.json', 'SHA')) as pub, \
                patch.object(cont, 'full_admission_facts', return_value={'generation': 'G', 'vss_profile': 'P',
                                                                         'root_identities': {}}):
            try:
                cont.publish_stage(o, {'immutable_receipt': lambda *a: None},
                                   types.SimpleNamespace(stage=stage, nodes=()), admit)
            except RuntimeError as exc:
                return str(exc), pub
        return None, pub

    def test_01_d5_certificate_readback(self):
        cert = b'canonical certificate bytes'
        state = {'schema': 'TICKSTORE_ORCH_STATE_V001', 'status': 'PASS', 'next_node': 'D6',
                 'canary_canonical_cert': base64.b64encode(cert).decode()}
        err, pub = self.call('D5', state, {'D5': {'cert_sha256': h(cert)}})
        self.assertIsNone(err); self.assertTrue(pub.called)
        self.assertEqual(pub.call_args[0][0], 'D5')
        self.assertEqual(pub.call_args[1]['checks'], {k: True for k in REQUIRED_CHECKS['D5']})
        err, pub = self.call('D5', state, {'D5': {'cert_sha256': h(b'other')}})
        self.assertIn('D5_CERTIFICATE_READBACK', err); self.assertFalse(pub.called)

    def test_02_stage_requires_its_exact_final_state(self):
        state = {'schema': 'TICKSTORE_ORCH_STATE_V001', 'status': 'PASS', 'next_node': 'D5',
                 'canary_canonical_cert': base64.b64encode(b'x').decode()}
        err, pub = self.call('D5', state, {'D5': {'cert_sha256': h(b'x')}})
        self.assertIn('STAGE_FINAL_STATE_READBACK', err); self.assertFalse(pub.called)

    def test_03_full_prep_requires_prepared_stage_b_evidence(self):
        state = {'schema': 'TICKSTORE_ORCH_STATE_V001', 'status': 'PASS', 'next_node': 'F1'}
        pack = {'path': str(self.d / 'pack.zip'), 'sha256': 'A' * 64}
        ok = {'E9': {'evidence_prepared': True, 'review_required': True, 'stage_b_pack': pack,
                     'stage_b_orchestrator_package': dict(pack, sha256='B' * 64)}}
        err, pub = self.call('FULL_PREP', state, {'E9': dict(ok['E9'], evidence_prepared=False)})
        self.assertIn('FULL_PREP_STAGE_B_NOT_PREPARED', err); self.assertFalse(pub.called)

    def test_04_full_admit_consumes_full_go(self):
        state = {'schema': 'TICKSTORE_ORCH_STATE_V001', 'status': 'PASS', 'next_node': 'G3'}

        def setup(o):
            o.st.inbox.mkdir(); o.control.mkdir()
            (o.st.inbox / 'STAGE_B_REVIEW_V001.txt').write_bytes(b'review')
            (o.st.inbox / 'FULL_GO.txt').write_bytes(b'FULL_GO=PASS')
            (o.control / 'PRODUCTION_FREEZE_V004R1.json').write_bytes(b'{}')
        err, pub = self.call('FULL_ADMIT', state, {'F1': {'FULL_GO': 'FAIL'}, 'F2': {'freeze_sha256': h(b'{}')}}, setup)
        self.assertIn('FULL_STAGE_B_REVIEW_NOT_PASSED', err); self.assertFalse(pub.called)

    def test_05_full_admit_positive_binds_review_go_and_freeze(self):
        state = {'schema': 'TICKSTORE_ORCH_STATE_V001', 'status': 'PASS', 'next_node': 'G3'}

        def setup(o):
            o.st.inbox.mkdir(); o.control.mkdir()
            (o.st.inbox / 'STAGE_B_REVIEW_V001.txt').write_bytes(b'review')
            (o.st.inbox / 'FULL_GO.txt').write_bytes(b'FULL_GO=PASS')
            (o.control / 'PRODUCTION_FREEZE_V004R1.json').write_bytes(b'{}')
        err, pub = self.call('FULL_ADMIT', state, {'F1': {'FULL_GO': 'PASS'}, 'F2': {'freeze_sha256': h(b'{}')}}, setup)
        self.assertIsNone(err, err); self.assertEqual(pub.call_args[0][0], 'FULL_ADMISSION')
        names = sorted(Path(e['path']).name for e in pub.call_args[0][5])
        self.assertEqual(names, ['FULL_GO.txt', 'PRODUCTION_FREEZE_V004R1.json', 'STAGE_B_REVIEW_V001.txt'])
        self.assertEqual(pub.call_args[1]['extra']['generation'], 'G')


class FullAdmissionFacts(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.d = Path(t.name)
        self.roots = {k: self.d / k for k in ('source', 'dest', 'scratch')}
        for p in self.roots.values():
            p.mkdir()
        self.bindings = {'source_root': str(self.roots['source']), 'dest_root': str(self.roots['dest']),
                         'scratch_root': str(self.roots['scratch']), 'runner_sha256': 'A' * 64}
        self.census = 0

    def call(self, actual_bindings=None):
        import tickstore_serial_runner as core
        import tickstore_full_multiwork as multi
        inst = {'bindings': dict(self.bindings), 'ledger_path': str(self.d / 'ledger.zip'),
                'resources': {'max_workers': 4, 'ram_target_percent': 60}}
        admission = types.SimpleNamespace(instance=inst, enter_context=lambda x: x)
        handle = types.SimpleNamespace(info=lambda: {'volume': 1, 'index': 2})
        vss = types.SimpleNamespace(assert_present=lambda g: None, close=lambda: None)
        eng = types.SimpleNamespace(recovery_process_census=lambda: {'known_recovery_supervisor_or_workers': self.census},
                                    Win32Store=lambda: types.SimpleNamespace(open=lambda p, directory: handle),
                                    NativeVSS=lambda store, prof: vss)
        o = types.SimpleNamespace(st=types.SimpleNamespace(d={'G_PA': 'GEN', 'pprof': 'PROF'}), eng=eng)
        actual = dict(self.bindings, schema='S', authorized=True) if actual_bindings is None else actual_bindings
        with patch.object(core, 'full_release_materials', return_value=({}, {}, {})), \
                patch.object(core, 'load_ledgers', return_value=([], {}, 'L')), \
                patch.object(core, 'validate_full_plan', return_value=None), \
                patch.object(core, 'full_gate_bindings', return_value=actual), \
                patch.object(multi, 'choose_workers', return_value=4):
            return cont.full_admission_facts(o, admission)

    def test_06_positive_facts(self):
        facts = self.call()
        self.assertEqual((facts['generation'], facts['vss_profile']), ('GEN', 'PROF'))
        self.assertEqual(set(facts['root_identities']), {'source', 'dest', 'scratch'})

    def test_07_binding_drift_census_and_writer_lock_block(self):
        with self.assertRaisesRegex(RuntimeError, 'FULL_PREP_BINDINGS'):
            self.call(dict(self.bindings, runner_sha256='B' * 64))
        self.census = 1
        with self.assertRaisesRegex(RuntimeError, 'FULL_PREP_PROCESS_CENSUS'):
            self.call()
        self.census = 0
        (self.roots['dest'] / 'TICKSTORE_WRITER.lock').write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError, 'FULL_PREP_WRITER_LOCK'):
            self.call()


class InitialChain(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.d = Path(t.name)
        self.instance = self.d / 'INSTANCE.json'; self.instance.write_bytes(b'{"schema":"TICKSTORE_FULL_INSTANCE_V001"}')
        self.manifest = self.d / 'MANIFEST.json'; self.manifest.write_bytes(b'{"files":[]}')
        self.inst_sha, self.code_sha = h(self.instance.read_bytes()), h(self.manifest.read_bytes())

    def receipt(self, stage, previous):
        obj = {'schema': 'TICKSTORE_STAGE_RECEIPT_V001', 'stage': stage, 'status': 'PASS',
               'environment': 'WINDOWS_PRODUCTION', 'code_manifest_sha256': self.code_sha,
               'instance_sha256': self.inst_sha, 'previous_receipt_sha256': previous, 'blockers': [],
               'checks': {k: True for k in REQUIRED_CHECKS[stage]}, 'evidence': [{'path': 'E', 'sha256': 'E' * 64}]}
        if stage == 'B06':
            obj.update(reviewer='INDEPENDENT_FIXTURE', implementation_participant=False)
        raw = json.dumps(obj, sort_keys=True).encode()
        p = self.d / ('STAGE_%s.json' % stage); p.write_bytes(raw)
        return {'path': str(p), 'sha256': h(raw)}

    def spec(self, stages):
        out, prev = {}, None
        for s in stages:
            out[s] = self.receipt(s, prev); prev = out[s]['sha256']
        p = self.d / 'SPEC.json'; p.write_bytes(json.dumps(out).encode())
        return p, out

    def assemble(self, spec, b06, until):
        written = {}

        def write_new(path, raw):
            Path(path).write_bytes(raw); written[str(path)] = raw

        class Chain:
            def __init__(self, *a, **k): self.args, self.kw = a, k
            def __enter__(self): return types.SimpleNamespace(revalidate=lambda: None, read=lambda *a: None)
            def __exit__(self, *e): return False
        with patch.object(prep, 'write_new', write_new), patch.object(prep, 'ReleaseChain', Chain):
            return prep.assemble_chain(self.instance, self.inst_sha, self.manifest, self.code_sha, spec,
                                       self.d / 'CHAIN.json', b06, until), written

    def test_08_chain_until_b06_for_the_b07_runner(self):
        spec, recs = self.spec(('G5', 'B06'))
        result, written = self.assemble(spec, recs['B06']['sha256'], 'B06')
        chain = json.loads((self.d / 'CHAIN.json').read_bytes())
        self.assertEqual(set(chain['receipts']), {'G5', 'B06'})
        self.assertEqual(result['chain_sha256'], h((self.d / 'CHAIN.json').read_bytes()))

    def test_09_stage_set_must_match_until(self):
        spec, recs = self.spec(('G5', 'B06'))
        with self.assertRaisesRegex(RuntimeError, 'INITIAL_CHAIN_REQUIRES_G5_B06_B07'):
            self.assemble(spec, recs['B06']['sha256'], 'B07')
        with self.assertRaisesRegex(RuntimeError, 'INITIAL_CHAIN_UNTIL'):
            self.assemble(spec, recs['B06']['sha256'], 'D4')
        with self.assertRaisesRegex(RuntimeError, 'B06_EXTERNAL_DIGEST_MISMATCH'):
            self.assemble(spec, 'F' * 64, 'B06')


if __name__ == '__main__':
    unittest.main(verbosity=2)
