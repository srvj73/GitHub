"""R45 (B2D integrated): origin decision binder never decides, only binds and copies.

Decision records built here are UNIT FIXTURES ONLY (never origin evidence).  The produced
receipts are validated by the unmodified FULL_RELEASE_CHAIN.validate_chain.

R45: the binder verifies the policy capture itself from physical bytes (R40 capture fixture and a
reconciliation UNIT FIXTURE in a private temp dir, marked unit_fixture_not_origin_record).  Off
Windows the reads are optimistic, so receipts carry environment FIXTURE_NOT_NATIVE and are refused
by the operational chain; natively the same inputs yield WINDOWS_PRODUCTION.
"""
import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'candidate/control'))
import ORIGIN_DECISION_BINDER as D  # noqa: E402
from FULL_RELEASE_CHAIN import validate_chain  # noqa: E402
sys.path.insert(0, str(HERE))
from g5_native_fixture import NativeFixture, load_consumer  # noqa: E402

CODE, FINAL, INST, B06 = 'A' * 64, 'B' * 64, 'C' * 64, 'D' * 64
NATIVE = os.name == 'nt'
ENV = 'WINDOWS_PRODUCTION' if NATIVE else 'FIXTURE_NOT_NATIVE'
NOW = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)
R40 = HERE / 'fixtures/R40_CAPTURE_NON_AUTHORITATIVE'


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


QNS = load_consumer()


def native_return(code, final, **receipt_extra):
    """Synthetic closed native RETURN ZIP (UNIT FIXTURE) whose QUAL receipt binds these code/FINAL digests."""
    nf = NativeFixture(QNS)
    nf.receipt_extra = dict({'SOURCE_SHA256': final, 'RUNTIME_CODE_MANIFEST_SHA256': code}, **receipt_extra)
    with tempfile.TemporaryDirectory() as t:
        rz, _fz, _c, _f = nf.make(t)
        raw = rz.read_bytes()
    import zipfile
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        qual = z.read(QNS['MEMBERS']['qual_receipt'])
    return raw, h(qual)


def completeness(code, final, zraw, qual_sha, **over):
    obj = {'schema': 'TICKSTORE_ENGINEERING_COMPLETENESS_V002', 'status': 'COMPLETE', 'known_blockers': [],
           'code_manifest_sha256': code, 'provenance_mode': 'CLOSED_NATIVE_RETURN_ZIP', 'windows_qualification': 'PASS',
           'delta_qualification': {'native_windows': True, 'tested_code_equals_packaged_code': 'PASS',
                                   'native_provenance': {'final_zip': {'sha256': final}, 'return_zip': {'sha256': h(zraw)},
                                                         'qual_receipt_sha256': qual_sha}}}
    obj.update(over)
    return obj


def j(obj):
    return (json.dumps(obj, sort_keys=True) + '\n').encode()


class Binder(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.t = Path(t.name)
        self.policy = self.t / 'policy'
        import shutil; shutil.copytree(R40, self.policy)
        self.rec, self.rec_sha = self.reconciliation()
        hd = json.loads((R40 / 'POLITICA_CANONICA_HEAD.json').read_bytes())
        self.zraw, self.qual_sha = native_return(CODE, FINAL)
        self.capture = {'master_sha256': h((R40 / 'POLITICA_CANONICA_UNIFICADA_OPERACIONAL.md').read_bytes()),
                        'head_sha256': h((R40 / 'POLITICA_CANONICA_HEAD.json').read_bytes()),
                        'revision_id': hd['revision_id'], 'reconciliation_sha256': self.rec_sha}
        files = {
            'G5_EVIDENCE_PACK': j({'schema': 'TICKSTORE_G5_EVIDENCE_PACK_V001', 'completeness_status': 'COMPLETE',
                                   'known_blockers': [], 'consumer_self_check': 'ACCEPTS', 'code_manifest_sha256': CODE,
                                   'gate_verdict_issued': False}),
            'ENGINEERING_COMPLETENESS': j(completeness(CODE, FINAL, self.zraw, self.qual_sha)),
            'NATIVE_RETURN_ZIP': self.zraw,
            'B07_TECHNICAL_RECEIPT': j({'schema': 'TICKSTORE_B07_TECHNICAL_RECEIPT_V001', 'status': 'PASS',
                                        'platform': 'WINDOWS_NTFS_PS51', 'code_manifest_sha256': CODE,
                                        'review_verdict_sha256': B06}),
        }
        self.paths = {}
        for role, raw in files.items():
            p = self.t / (role + '.bin'); p.write_bytes(raw); self.paths[role] = p
        self.n = 0

    def reconciliation(self, name='RECONCILIATION.json', **over):
        hd = json.loads((R40 / 'POLITICA_CANONICA_HEAD.json').read_bytes())
        rec = {'schema': 'TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001', 'issuer': 'CHATGPT_ORIGIN',
               'status': 'CURRENT_AT_ORIGIN', 'unit_fixture_not_origin_record': True,
               'policy_master_sha256': h((R40 / 'POLITICA_CANONICA_UNIFICADA_OPERACIONAL.md').read_bytes()),
               'policy_head_sha256': h((R40 / 'POLITICA_CANONICA_HEAD.json').read_bytes()),
               'policy_revision': hd['revision_id'], 'live_cardinality': {'master': 1, 'head': 1}, 'live_state': 'FROZEN',
               'capture_operational_authority': False, 'administrative_owner_gate_required': False,
               'scope': ['D4_FIRST_ADMISSION'], 'routing_project': 'Base de Dados CSV / Tickstore',
               'routing_thread': 'Compress\u00e3o De Ticks 15', 'reconciled_at': '2026-10-14T00:00:00+00:00',
               'valid_until': '2026-10-15T00:00:00+00:00'}
        rec.update(over)
        p = self.t / name; p.write_bytes(j(rec))
        return p, h(p.read_bytes())

    def decision(self, stage, **over):
        roles = D.REQUIRED_EVIDENCE[stage]
        d = {'schema': D.DECISION_SCHEMA, 'issuer': 'CHATGPT_ORIGIN', 'implementation_participant_is_issuer': False,
             'administrative_owner_gate': False, 'stage': stage, 'decision': 'PASS', 'decision_id': 'FIXTURE-' + stage,
             'code_manifest_sha256': CODE, 'final_package_sha256': FINAL, 'instance_sha256': INST,
             'policy': {k: self.capture[k] for k in ('master_sha256', 'head_sha256', 'revision_id', 'reconciliation_sha256')},
             'predecessors': {}, 'previous_receipt_sha256': None, 'blockers': [],
             'checks': dict.fromkeys(D.REQUIRED_CHECKS[stage], True),
             'evidence': [{'role': r, 'sha256': h(self.paths[r].read_bytes())} for r in roles],
             'fixture': 'UNIT_FIXTURE_NOT_ORIGIN_EVIDENCE'}
        d.update(over)
        return d

    def run_stage(self, stage, d, preds=None, sha=None, out=None, b06=None, evidence=None, rec=None, rec_sha=None,
                  policy=None, b06_verdict=None, b06_receipt=None):
        self.n += 1
        raw = j(d); p = self.t / ('DECISION_%d.json' % self.n); p.write_bytes(raw)
        ev = evidence or {r: self.paths[r] for r in {e['role'] for e in d['evidence']}}
        return D.materialize(p, sha or h(raw), stage=stage, code_sha=CODE, final_package_sha=FINAL, instance_sha=INST,
                             policy_root=policy or self.policy, policy_reconciliation=rec or self.rec,
                             policy_reconciliation_sha256=rec_sha or self.rec_sha,
                             predecessor_hashes=preds if preds is not None else {}, evidence_paths=ev,
                             out_path=out or self.t / ('STAGE_%s_%d.json' % (stage, self.n)), b06_sha=b06,
                             b06_verdict_sha=b06_verdict, b06_receipt_path=b06_receipt, now=NOW)

    def blocked(self, needle, stage='G5', **kw):
        with self.assertRaisesRegex(D.DecisionBlocked, needle):
            self.run_stage(stage, kw.pop('d', None) or self.decision(stage), **kw)

    def test_01_g5_receipt_from_origin_decision_is_chain_valid(self):
        r = self.run_stage('G5', self.decision('G5'))
        obj = json.loads(Path(r['path']).read_bytes())
        self.assertEqual(obj['materialized_by'], 'ORIGIN_DECISION_BINDER_COPY_ONLY')
        self.assertEqual(obj['environment'], ENV); self.assertEqual(r['environment'], ENV)
        self.assertEqual(obj['policy_verification']['verified_by'], 'POLICY_CAPTURE_BINDING.verify_capture')
        validate_chain({'G5': obj}, {'G5': r['sha256']}, code_sha=CODE, instance_sha=INST, b06_sha=B06, until='G5',
                       environment=ENV)
        if not NATIVE:  # a non-native receipt is never consumable by the operational chain
            with self.assertRaisesRegex(Exception, 'G5_ENVIRONMENT'):
                validate_chain({'G5': obj}, {'G5': r['sha256']}, code_sha=CODE, instance_sha=INST, b06_sha=B06, until='G5')

    def b07_setup(self, cite_verdict=True, produced_after=True):
        g5 = self.run_stage('G5', self.decision('G5'))
        verdict = b'B06 INDEPENDENT REVIEW\nVERDICT=PASS\n'; verdict_sha = h(verdict)
        b06 = {'schema': 'TICKSTORE_STAGE_RECEIPT_V001', 'stage': 'B06', 'status': 'PASS', 'environment': ENV,
               'code_manifest_sha256': CODE, 'instance_sha256': INST, 'previous_receipt_sha256': g5['sha256'], 'blockers': [],
               'checks': dict(independent_review=True, final_bytes=True, no_critical_or_major_findings=True),
               'evidence': [{'path': 'B06_VERDICT.txt', 'sha256': verdict_sha if cite_verdict else 'E' * 64}],
               'reviewer': 'INDEPENDENT_FIXTURE', 'implementation_participant': False}
        b06_raw = j(b06); b06_sha = h(b06_raw); b06_path = self.t / ('B06_%d.json' % self.n); b06_path.write_bytes(b06_raw)
        preds = {'G5': g5['sha256'], 'B06': b06_sha}
        self.paths['B07_TECHNICAL_RECEIPT'].write_bytes(j({'schema': 'TICKSTORE_B07_TECHNICAL_RECEIPT_V001', 'status': 'PASS',
                                                            'platform': 'WINDOWS_NTFS_PS51', 'code_manifest_sha256': CODE,
                                                            'review_verdict_sha256': verdict_sha,
                                                            'b06_stage_receipt_sha256': b06_sha,
                                                            'return_zip_sha256': h(self.zraw),
                                                            'produced_after_independent_b06': produced_after}))
        d = self.decision('B07', predecessors=preds, previous_receipt_sha256=b06_sha, b06_receipt_sha256=b06_sha,
                          b06_verdict_sha256=verdict_sha, b06_independent=True)
        return g5, b06, b06_sha, b06_path, verdict_sha, preds, d

    def test_02_b07_binds_g5_b06_chain_and_independent_b06(self):
        g5, b06, b06_sha, b06_path, verdict_sha, preds, d = self.b07_setup()
        r = self.run_stage('B07', d, preds=preds, b06=b06_sha, b06_verdict=verdict_sha, b06_receipt=b06_path)
        obj = json.loads(Path(r['path']).read_bytes())
        self.assertEqual((obj['b06_receipt_sha256'], obj['b06_verdict_sha256']), (b06_sha, verdict_sha))
        receipts = {'G5': json.loads(Path(g5['path']).read_bytes()), 'B06': b06, 'B07': obj}
        validate_chain(receipts, {'G5': g5['sha256'], 'B06': b06_sha, 'B07': r['sha256']}, code_sha=CODE,
                       instance_sha=INST, b06_sha=b06_sha, until='B07', environment=ENV)
        with self.assertRaisesRegex(D.DecisionBlocked, 'DECISION_B06'):
            self.run_stage('B07', dict(d, b06_independent=False), preds=preds, b06=b06_sha, b06_verdict=verdict_sha,
                           b06_receipt=b06_path)

    def test_02b_b06_receipt_and_verdict_digests_are_distinct_and_cross_bound(self):
        g5, b06, b06_sha, b06_path, verdict_sha, preds, d = self.b07_setup()
        kw = dict(preds=preds, b06=b06_sha, b06_verdict=verdict_sha, b06_receipt=b06_path)
        self.blocked('DECISION_B06_VERDICT_BINDING', stage='B07', d=d, **dict(kw, b06_verdict='9' * 64))
        self.blocked('DECISION_B06_RECEIPT_REQUIRED', stage='B07', d=d, **dict(kw, b06_receipt=None))
        other = self.t / 'OTHER_B06.json'; other.write_bytes(b'{}')
        self.blocked('DECISION_B06_RECEIPT_SHA256', stage='B07', d=d, **dict(kw, b06_receipt=other))
        # the old (inconsistent) semantics: verdict digest == B06 receipt digest is refused
        self.blocked('DECISION_B06_VERDICT_BINDING', stage='B07', d=dict(d, b06_verdict_sha256=b06_sha), **kw)

    def test_02c_b06_receipt_must_cite_the_verdict_and_b07_must_follow_b06(self):
        g5, b06, b06_sha, b06_path, verdict_sha, preds, d = self.b07_setup(cite_verdict=False)
        self.blocked('DECISION_B06_RECEIPT_DOES_NOT_CITE_VERDICT', stage='B07', d=d, preds=preds, b06=b06_sha,
                     b06_verdict=verdict_sha, b06_receipt=b06_path)
        g5, b06, b06_sha, b06_path, verdict_sha, preds, d = self.b07_setup(produced_after=False)
        self.blocked('DECISION_EVIDENCE_B07_RECEIPT', stage='B07', d=d, preds=preds, b06=b06_sha,
                     b06_verdict=verdict_sha, b06_receipt=b06_path)

    def test_03_never_without_the_separately_supplied_digest(self):
        self.blocked('DECISION_SHA256_SUPPLIED_SEPARATELY', sha='0' * 64)

    def test_04_reject_or_foreign_issuer_writes_nothing(self):
        out = self.t / 'NEVER.json'
        self.blocked('ORIGIN_DECISION_REJECT', d=self.decision('G5', decision='REJECT'), out=out)
        self.blocked('DECISION_SCHEMA_ISSUER', d=self.decision('G5', issuer='OPUS_ENGINEER'), out=out)
        self.blocked('DECISION_IMPLEMENTER_CANNOT_ISSUE', d=self.decision('G5', implementation_participant_is_issuer=True), out=out)
        self.blocked('DECISION_NO_ADMINISTRATIVE_OWNER_GATE', d=self.decision('G5', administrative_owner_gate=True), out=out)
        self.assertFalse(out.exists())

    def test_05_every_binding_drift_blocks(self):
        for key, needle in (('code_manifest_sha256', 'code_manifest'), ('final_package_sha256', 'final_package'),
                            ('instance_sha256', 'instance')):
            self.blocked('DECISION_BINDING:' + needle, d=self.decision('G5', **{key: 'F' * 64}))
        pol = dict(self.decision('G5')['policy'], reconciliation_sha256='9' * 64)
        self.blocked('DECISION_POLICY_BINDING:reconciliation', d=self.decision('G5', policy=pol))
        d = self.decision('G5'); d['stage'] = 'B07'
        self.blocked('DECISION_STAGE', d=d)
        self.blocked('DECISION_STAGE_NOT_MATERIALIZABLE', stage='D4', d=self.decision('G5'))

    def test_06_blockers_checks_and_predecessors(self):
        self.blocked('DECISION_BLOCKERS', d=self.decision('G5', blockers=['B2-G5-01']))
        checks = dict.fromkeys(D.REQUIRED_CHECKS['G5'], True); checks['byte_freeze'] = False
        self.blocked('DECISION_CHECKS', d=self.decision('G5', checks=checks))
        self.blocked('DECISION_PREVIOUS_RECEIPT', d=self.decision('G5', previous_receipt_sha256='1' * 64))

    def test_07_evidence_is_reread_and_semantically_checked(self):
        d = self.decision('G5')
        self.paths['G5_EVIDENCE_PACK'].write_bytes(b'{}')
        self.blocked('DECISION_EVIDENCE_SHA256:G5_EVIDENCE_PACK', d=d)

    def test_08_incomplete_g5_pack_cannot_be_promoted(self):
        raw = j({'schema': 'TICKSTORE_G5_EVIDENCE_PACK_V001', 'completeness_status': 'INCOMPLETE',
                 'known_blockers': ['CHECKPOINT_POWERLOSS_RECOVERY:PHYSICAL_PROOF_NOT_SPECIFIED_BY_ORIGIN'],
                 'consumer_self_check': 'REJECTS', 'code_manifest_sha256': CODE, 'gate_verdict_issued': False})
        self.paths['G5_EVIDENCE_PACK'].write_bytes(raw)
        self.blocked('DECISION_EVIDENCE_G5_PACK')

    def test_09_missing_or_duplicate_evidence_roles(self):
        d = self.decision('G5'); d['evidence'] = d['evidence'][:1]
        self.blocked('DECISION_EVIDENCE_ROLES', d=d)
        d = self.decision('G5'); d['evidence'].append(dict(d['evidence'][0]))
        self.blocked('DECISION_EVIDENCE_ROLES', d=d)

    def test_10_no_clobber(self):
        out = self.t / 'G5.json'
        self.run_stage('G5', self.decision('G5'), out=out)
        self.blocked('STAGE_RECEIPT_EXISTS', out=out)

    def test_11_binder_source_has_no_pass_shortcut(self):
        src = (HERE.parent / 'candidate/control/ORIGIN_DECISION_BINDER.py').read_text(encoding='utf-8')
        self.assertEqual(src.count("'status': 'PASS'"), 1)  # only inside materialize, after verify_decision
        self.assertNotIn('OWNER_GATE_V', src)

    # ---- R45: policy provenance (analogue of B07-PROVENANCE-01) ---------------------------------
    def test_12_caller_supplied_capture_dictionary_is_refused(self):
        d = self.decision('G5'); raw = j(d); p = self.t / 'D_forged.json'; p.write_bytes(raw)
        forged = {'schema': 'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001', 'master_sha256': '1' * 64, 'head_sha256': '2' * 64,
                  'revision_id': 'R', 'reconciliation_sha256': '3' * 64}
        with self.assertRaises(TypeError):
            D.materialize(p, h(raw), stage='G5', code_sha=CODE, final_package_sha=FINAL, instance_sha=INST,
                          policy_capture=forged, predecessor_hashes={}, evidence_paths={}, out_path=self.t / 'X.json')
        self.assertFalse((self.t / 'X.json').exists())

    def test_13_fictitious_or_unverifiable_policy_blocks_before_reading_the_decision(self):
        out = self.t / 'NEVER.json'
        rec, rec_sha = self.reconciliation('FAKE.json', policy_master_sha256='1' * 64)
        self.blocked('DECISION_POLICY_NOT_VERIFIED:.*POLICY_RECONCILIATION_BINDING', rec=rec, rec_sha=rec_sha, out=out)
        self.blocked('DECISION_POLICY_NOT_VERIFIED:.*SHA_MISMATCH', rec_sha='3' * 64, out=out)
        rec, rec_sha = self.reconciliation('OLD.json', valid_until='2026-10-14T06:00:00+00:00')
        self.blocked('DECISION_POLICY_NOT_VERIFIED:.*EXPIRED', rec=rec, rec_sha=rec_sha, out=out)
        empty = self.t / 'empty'; empty.mkdir()
        self.blocked('DECISION_POLICY_NOT_VERIFIED:.*CARDINALITY', policy=empty, out=out)
        self.assertFalse(out.exists())

    def test_14_decision_policy_must_equal_the_physically_verified_capture(self):
        pol = dict(self.decision('G5')['policy'], master_sha256='1' * 64)
        self.blocked('DECISION_POLICY_BINDING:master', d=self.decision('G5', policy=pol))

    def test_15_operator_cli_hashes_physical_inputs(self):
        d = self.decision('G5', code_manifest_sha256=None, final_package_sha256=None, instance_sha256=None)
        files = {}
        for name in ('code', 'final', 'instance'):
            p = self.t / (name + '.bin'); p.write_bytes(name.encode()); files[name] = p
        d.update(code_manifest_sha256=h(b'code'), final_package_sha256=h(b'final'), instance_sha256=h(b'instance'))
        # The G5 pack is bound to the code manifest digest, so re-derive the evidence for these physical inputs.
        self.paths['G5_EVIDENCE_PACK'].write_bytes(j({'schema': 'TICKSTORE_G5_EVIDENCE_PACK_V001', 'completeness_status': 'COMPLETE',
                                                      'known_blockers': [], 'consumer_self_check': 'ACCEPTS',
                                                      'code_manifest_sha256': h(b'code'), 'gate_verdict_issued': False}))
        zraw, qual_sha = native_return(h(b'code'), h(b'final'))
        self.paths['NATIVE_RETURN_ZIP'].write_bytes(zraw)
        self.paths['ENGINEERING_COMPLETENESS'].write_bytes(j(completeness(h(b'code'), h(b'final'), zraw, qual_sha)))
        d['evidence'] = [{'role': r, 'sha256': h(self.paths[r].read_bytes())} for r in D.REQUIRED_EVIDENCE['G5']]
        raw = j(d); dp = self.t / 'D_cli.json'; dp.write_bytes(raw)
        args = ['--stage', 'G5', '--decision', str(dp), '--decision-sha256', h(raw), '--code-manifest', str(files['code']),
                '--final-zip', str(files['final']), '--instance', str(files['instance']), '--policy-root', str(self.policy),
                '--policy-reconciliation', str(self.rec), '--policy-reconciliation-sha256', self.rec_sha,
                '--out', str(self.t / 'G5_cli.json')]
        for r in D.REQUIRED_EVIDENCE['G5']:
            args += ['--evidence', '%s=%s' % (r, self.paths[r])]
        real = D.verified_policy  # pin the clock of the reconciliation window (deterministic test)
        D.verified_policy = lambda *a, **k: real(*a, **dict(k, now=NOW))
        self.addCleanup(setattr, D, 'verified_policy', real)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = D.main(args)
        self.assertEqual(rc, 0 if NATIVE else 3, buf.getvalue())
        self.assertIn('ORIGIN_DECISION_BINDER=MATERIALIZED STAGE=G5 ENVIRONMENT=' + ENV, buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(D.main(args), 2)  # same --out: no clobber, the CLI fails closed
        self.assertIn('ORIGIN_DECISION_BINDER=BLOCKED', buf.getvalue()); self.assertIn('STAGE_RECEIPT_EXISTS', buf.getvalue())


    # ---- R47 G11: G4 is a deliberate pre-chain stage enforced at G5 materialization ----------------
    def g4_variant(self, zraw=None, comp=None):
        zraw = self.zraw if zraw is None else zraw
        self.paths['NATIVE_RETURN_ZIP'].write_bytes(zraw)
        self.paths['ENGINEERING_COMPLETENESS'].write_bytes(j(comp or completeness(CODE, FINAL, zraw, self.qual_sha)))
        return self.decision('G5')

    def test_16_g5_requires_the_closed_native_g4_return_zip(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.zraw)) as z, zipfile.ZipFile(buf, 'w') as w:
            for n in z.namelist():
                w.writestr(n, z.read(n))
            w.writestr('PLANTED_OUTSIDE_MANIFEST.json', b'{}')
        self.blocked('DECISION_G4_RETURN_ZIP:RETURN_MANIFEST_COVERAGE', d=self.g4_variant(buf.getvalue()))
        self.blocked('DECISION_G4_RETURN_ZIP', d=self.g4_variant(b'PK fixture bytes'))

    def test_17_g5_requires_a_native_qual_receipt_bound_to_these_bytes(self):
        for extra, needle in (({'mode': 'OFFLINE_HARNESS_CHECK'}, 'QUAL_RECEIPT_NOT_NATIVE'),
                              ({'SOURCE_SHA256': '9' * 64}, 'QUAL_RECEIPT_FINAL_ZIP_BINDING'),
                              ({'RUNTIME_CODE_MANIFEST_SHA256': '9' * 64}, 'QUAL_RECEIPT_CODE_MANIFEST_BINDING'),
                              ({'TESTED_CODE_EQUALS_PACKAGED_CODE': 'FAIL'}, 'QUAL_RECEIPT_TESTED_NOT_PACKAGED')):
            with self.subTest(needle=needle):
                zraw, qual_sha = native_return(CODE, FINAL, **extra)
                d = self.g4_variant(zraw, completeness(CODE, FINAL, zraw, qual_sha))
                self.blocked('DECISION_G4_QUAL_RECEIPT:.*' + needle, d=d)

    def test_18_g4_zip_must_be_the_completeness_native_provenance(self):
        other, other_qual = native_return(CODE, FINAL, RUN_ID='OTHER_RUN')
        self.blocked('DECISION_G4_RETURN_ZIP_NOT_THE_COMPLETENESS_PROVENANCE',
                     d=self.g4_variant(other, completeness(CODE, FINAL, self.zraw, self.qual_sha)))
        comp = completeness(CODE, FINAL, self.zraw, other_qual)
        self.blocked('DECISION_G4_QUAL_RECEIPT_NOT_THE_COMPLETENESS_PROVENANCE', d=self.g4_variant(comp=comp))
        comp = completeness(CODE, FINAL, self.zraw, self.qual_sha, windows_qualification='NOT_PASS')
        self.blocked('DECISION_G4_NATIVE_QUALIFICATION_NOT_PASS', d=self.g4_variant(comp=comp))

    def test_19_b07_return_zip_must_be_the_one_its_technical_receipt_names(self):
        g5, b06, b06_sha, b06_path, verdict_sha, preds, d = self.b07_setup()
        other, _ = native_return(CODE, FINAL, RUN_ID='B07_OTHER')
        self.paths['NATIVE_RETURN_ZIP'].write_bytes(other)
        d = self.decision('B07', predecessors=preds, previous_receipt_sha256=b06_sha, b06_receipt_sha256=b06_sha,
                          b06_verdict_sha256=verdict_sha, b06_independent=True)
        self.blocked('DECISION_B07_RETURN_ZIP_NOT_THE_TECHNICAL_RECEIPT_ZIP', stage='B07', d=d, preds=preds,
                     b06=b06_sha, b06_verdict=verdict_sha, b06_receipt=b06_path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
