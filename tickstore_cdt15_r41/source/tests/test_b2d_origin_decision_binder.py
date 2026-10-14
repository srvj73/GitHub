"""R45 (B2D integrated): origin decision binder never decides, only binds and copies.

Decision records built here are UNIT FIXTURES ONLY (never origin evidence).  The produced
receipts are validated by the unmodified FULL_RELEASE_CHAIN.validate_chain.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'candidate/control'))
import ORIGIN_DECISION_BINDER as D  # noqa: E402
from FULL_RELEASE_CHAIN import validate_chain  # noqa: E402

CODE, FINAL, INST, B06 = 'A' * 64, 'B' * 64, 'C' * 64, 'D' * 64


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def j(obj):
    return (json.dumps(obj, sort_keys=True) + '\n').encode()


class Binder(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.t = Path(t.name)
        self.capture = {'schema': 'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001', 'master_sha256': '1' * 64,
                        'head_sha256': '2' * 64, 'revision_id': 'R', 'reconciliation_sha256': '3' * 64}
        files = {
            'G5_EVIDENCE_PACK': j({'schema': 'TICKSTORE_G5_EVIDENCE_PACK_V001', 'completeness_status': 'COMPLETE',
                                   'known_blockers': [], 'consumer_self_check': 'ACCEPTS', 'code_manifest_sha256': CODE,
                                   'gate_verdict_issued': False}),
            'ENGINEERING_COMPLETENESS': j({'schema': 'TICKSTORE_ENGINEERING_COMPLETENESS_V002', 'status': 'COMPLETE',
                                           'known_blockers': [], 'code_manifest_sha256': CODE,
                                           'provenance_mode': 'CLOSED_NATIVE_RETURN_ZIP',
                                           'delta_qualification': {'native_provenance': {'final_zip': {'sha256': FINAL}}}}),
            'NATIVE_RETURN_ZIP': b'PK fixture bytes',
            'B07_TECHNICAL_RECEIPT': j({'schema': 'TICKSTORE_B07_TECHNICAL_RECEIPT_V001', 'status': 'PASS',
                                        'platform': 'WINDOWS_NTFS_PS51', 'code_manifest_sha256': CODE,
                                        'review_verdict_sha256': B06}),
        }
        self.paths = {}
        for role, raw in files.items():
            p = self.t / (role + '.bin'); p.write_bytes(raw); self.paths[role] = p
        self.n = 0

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

    def run_stage(self, stage, d, preds=None, sha=None, out=None, b06=None, evidence=None):
        self.n += 1
        raw = j(d); p = self.t / ('DECISION_%d.json' % self.n); p.write_bytes(raw)
        ev = evidence or {r: self.paths[r] for r in {e['role'] for e in d['evidence']}}
        return D.materialize(p, sha or h(raw), stage=stage, code_sha=CODE, final_package_sha=FINAL, instance_sha=INST,
                             policy_capture=self.capture, predecessor_hashes=preds if preds is not None else {},
                             evidence_paths=ev, out_path=out or self.t / ('STAGE_%s_%d.json' % (stage, self.n)), b06_sha=b06)

    def blocked(self, needle, stage='G5', **kw):
        with self.assertRaisesRegex(D.DecisionBlocked, needle):
            self.run_stage(stage, kw.pop('d', None) or self.decision(stage), **kw)

    def test_01_g5_receipt_from_origin_decision_is_chain_valid(self):
        r = self.run_stage('G5', self.decision('G5'))
        obj = json.loads(Path(r['path']).read_bytes())
        self.assertEqual(obj['materialized_by'], 'ORIGIN_DECISION_BINDER_COPY_ONLY')
        validate_chain({'G5': obj}, {'G5': r['sha256']}, code_sha=CODE, instance_sha=INST, b06_sha=B06, until='G5')

    def test_02_b07_binds_g5_b06_chain_and_independent_b06(self):
        g5 = self.run_stage('G5', self.decision('G5'))
        b06 = {'schema': 'TICKSTORE_STAGE_RECEIPT_V001', 'stage': 'B06', 'status': 'PASS', 'environment': 'WINDOWS_PRODUCTION',
               'code_manifest_sha256': CODE, 'instance_sha256': INST, 'previous_receipt_sha256': g5['sha256'], 'blockers': [],
               'checks': dict(independent_review=True, final_bytes=True, no_critical_or_major_findings=True),
               'evidence': [{'path': 'B06_VERDICT', 'sha256': 'E' * 64}], 'reviewer': 'INDEPENDENT_FIXTURE',
               'implementation_participant': False}
        b06_raw = j(b06); b06_sha = h(b06_raw)
        preds = {'G5': g5['sha256'], 'B06': b06_sha}
        self.paths['B07_TECHNICAL_RECEIPT'].write_bytes(j({'schema': 'TICKSTORE_B07_TECHNICAL_RECEIPT_V001', 'status': 'PASS',
                                                            'platform': 'WINDOWS_NTFS_PS51', 'code_manifest_sha256': CODE,
                                                            'review_verdict_sha256': b06_sha}))
        d = self.decision('B07', predecessors=preds, previous_receipt_sha256=b06_sha, b06_verdict_sha256=b06_sha,
                          b06_independent=True)
        r = self.run_stage('B07', d, preds=preds, b06=b06_sha)
        receipts = {'G5': json.loads(Path(g5['path']).read_bytes()), 'B06': b06,
                    'B07': json.loads(Path(r['path']).read_bytes())}
        validate_chain(receipts, {'G5': g5['sha256'], 'B06': b06_sha, 'B07': r['sha256']}, code_sha=CODE,
                       instance_sha=INST, b06_sha=b06_sha, until='B07')
        with self.assertRaisesRegex(D.DecisionBlocked, 'DECISION_B06'):
            self.run_stage('B07', dict(d, b06_independent=False), preds=preds, b06=b06_sha)

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
