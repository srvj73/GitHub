"""Isolated physical publication fixtures for Stage B preparation and FULL H* completion.

Not a release, auditor verdict, D4/Stage B authorization, or effectful run.
"""
from __future__ import annotations
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'candidate'/'control'))
import FULL_STAGE_CONTINUATION as cont
import FULL_LIFECYCLE as life
from D4_FIRST_ADMISSION_PREP import Reads, canonical, sha, strict_json


class Physical:
    def __init__(self, root, stage, *, mutated=None):
        self.base = pathlib.Path(root)
        self.stage = stage
        self.nodes = cont.RANGES[stage]
        self.out = self.base/'out'; self.out.mkdir()
        self.runs = self.base/'runs';self.runs.mkdir()
        self.run_id = 'run_20261012_001';(self.runs/self.run_id).mkdir()
        self.sp = self.base/'STATE.json';self.jp=self.base/'STATE_JOURNAL.jsonl'
        self.content = self.base/'assets';self.content.mkdir()
        results = {}
        for node in self.nodes:
            results[node]={'schema':'SYNTHETIC_TEST_V001','result':'PASS','node':node}
        if stage == 'FULL_PREP':
            pack = self.content/'STAGE_B_PACK.zip';pack.write_bytes(b'fixture-pack-not-a-real-stageb-approval')
            orch = self.content/'STAGE_B_ORCHESTRATOR.zip';orch.write_bytes(b'fixture-orch')
            results['E9']={'evidence_prepared':True,'review_required':True,
                           'stage_b_pack':{'path':str(pack),'sha256':sha(pack.read_bytes())},
                           'stage_b_orchestrator_package':{'path':str(orch),'sha256':sha(orch.read_bytes())}}
        if stage == 'FULL':
            rec = self.content/'RECONCILIATION.json'
            self.rec = {'schema':'TICKSTORE_MULTIWORK_RECONCILIATION_V001',
                        'status':'PASS','days':1550,'rows':7049522162,
                        'manifest_sha256':'A'*64}
            rec.write_bytes(canonical(self.rec))
            meta={'path':str(rec),'sha256':sha(rec.read_bytes())}
            h2 = {'deep': {'POST_FULL_AUDIT':'PASS', 'days':1550,'rows':7049522162,
                           'namespace':3101,'manifest_sha256':'A'*64},
                  'independent': {'schema':'POSTFULL_INDEPENDENT_VERIFIER_V001',
                                  'status':'PASS','days':1550,'rows':7049522162,
                                  'namespace_files':3101,'manifest_sha256':'A'*64}}
            pack=self.content/'FINAL_EVIDENCE.zip';pack.write_bytes(b'fixture-evidence-not-a-real-full')
            results['G3'] = {'FULL':'PASS','reconciliation':meta}
            results['H2'] = h2
            results['H3'] = {'FINAL_VS_POSTFULL':'PASS', 'reconciliation':meta,
                             'manifest_sha256':'A'*64}
            results['H6']={'path':str(pack),'sha256':sha(pack.read_bytes())}
        if mutated: mutated(results)
        self.results=results
        prev='';lines=[]
        for n in self.nodes:
            for phase in ('STARTED','FINISHED'):
                row = {'phase':phase,'node':n,'run_id':self.run_id,'prev_line_sha256':prev}
                if phase=='FINISHED':row.update(status='PASS',result_sha256=sha(canonical(results[n])))
                raw=canonical(row).rstrip(b'\n');lines.append(raw);prev=sha(raw)
            (self.runs/self.run_id/('RESULT_'+n+'.json')).write_bytes(canonical(results[n]))
        self.jp.write_bytes(b'\n'.join(lines)+b'\n')
        self.state = {'schema':'TICKSTORE_ORCH_STATE_V001','status':'PASS',
                      'next_node':cont.NEXT[stage],'completed':['D4','D5',*self.nodes]}
        self.sp.write_bytes(canonical(self.state))
        self.o=SimpleNamespace(st=SimpleNamespace(sp=self.sp,jp=self.jp,d=self.state,runs=self.runs),rd=self.out)
        self.ns={'immutable_receipt':self.no_clobber}
        self.boundary=SimpleNamespace(stage=stage,nodes=self.nodes)

    @staticmethod
    def no_clobber(p,b):
        with open(p,'xb') as f:f.write(b);f.flush()

    def admission(self, reads):
        return SimpleNamespace(descriptor={'code_manifest_sha256':'A'*64,'instance_sha256':'B'*64,
                                           'receipts':{'CANARY':{'path':'source-only-fixture'}}},
                    instance={'run_id':self.run_id}, receipt_sha='C'*64,
                    receipt_hashes={'FULL_ADMISSION':'D'*64},
                    read=reads.read,revalidate=reads.revalidate)

    def publish(self):
        with Reads() as reads:
            if self.stage == 'FULL':
                return life.publish_completion(self.o,self.ns,self.admission(reads),self.nodes)
            return cont.publish_stage(self.o,self.ns,self.boundary,self.admission(reads))


class StageBPhysicalPreparation(unittest.TestCase):
    def test_positive_e9_physical_pack(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL_PREP')
            path,digest=f.publish()
            self.assertEqual(sha(path.read_bytes()),digest)
            receipt=strict_json((f.out/'STAGE_FULL_PREP.json').read_bytes())
            self.assertTrue(receipt['checks']['stage_b_evidence_pack'])
            self.assertEqual(len(receipt['evidence']),len(f.nodes)+4)
            for ev in receipt['evidence']:
                self.assertEqual(sha(pathlib.Path(ev['path']).read_bytes()),ev['sha256'])
    def test_corrupted_stageb_pack_rejected_before_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL_PREP');(f.content/'STAGE_B_PACK.zip').write_bytes(b'adulterated')
            with self.assertRaisesRegex(RuntimeError, 'SHA_MISMATCH'):f.publish()
            self.assertFalse((f.out/'STAGE_FULL_PREP.json').exists())
    def test_missing_e9_evidence_prepared_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL_PREP', mutated=lambda r:r['E9'].update(evidence_prepared=False))
            with self.assertRaisesRegex(RuntimeError,'FULL_PREP_STAGE_B_NOT_PREPARED'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])
    def test_e9_review_required_false_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL_PREP', mutated=lambda r:r['E9'].update(review_required=False))
            with self.assertRaisesRegex(RuntimeError,'FULL_PREP_STAGE_B_NOT_PREPARED'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])
    def test_e9_result_corrupted_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL_PREP')
            (f.runs/f.run_id/'RESULT_E9.json').write_bytes(b'{}\n')
            with self.assertRaisesRegex(RuntimeError,'SHA_MISMATCH|STAGE_RESULT_JOURNAL_HASH'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])


class FullHStarPhysicalCompletion(unittest.TestCase):
    def test_positive_full_final_receipt_and_snapshots(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL')
            path,digest=f.publish()
            self.assertEqual(digest,sha(path.read_bytes()))
            receipt=strict_json(path.read_bytes())
            self.assertEqual(receipt['schema'],'TICKSTORE_FULL_COMPLETION_V001')
            self.assertEqual(receipt['next_node'],'I1')
            self.assertEqual(receipt['full_admission_sha256'],'D'*64)
            self.assertEqual((f.out/'FULL_STATE_AFTER.json').read_bytes(),f.sp.read_bytes())
            self.assertEqual((f.out/'FULL_JOURNAL_AFTER.jsonl').read_bytes(),f.jp.read_bytes())
            for ev in receipt['evidence']:
                self.assertEqual(sha(pathlib.Path(ev['path']).read_bytes()),ev['sha256'])
    def test_full_reconciliation_manifest_divergence_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL',mutated=lambda r:r['H2']['independent'].update(manifest_sha256='B'*64))
            with self.assertRaisesRegex(RuntimeError,'FULL_INDEPENDENT_READBACK_MISMATCH'):f.publish()
            self.assertFalse((f.out/'FULL_COMPLETION.json').exists())
    def test_full_h3_wrong_reconciliation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL',mutated=lambda r:r['H3'].update(reconciliation={'path':'wrong','sha256':'F'*64}))
            with self.assertRaisesRegex(RuntimeError,'FULL_H3_NOT_BOUND'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])
    def test_full_reconciliation_file_changed_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL')
            (f.content/'RECONCILIATION.json').write_bytes(b'{}\n')
            with self.assertRaisesRegex(RuntimeError,'SHA_MISMATCH'):f.publish()
            self.assertFalse((f.out/'FULL_COMPLETION.json').exists())
    def test_full_h6_pack_changed_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL')
            (f.content/'FINAL_EVIDENCE.zip').write_bytes(b'adulterated')
            with self.assertRaisesRegex(RuntimeError,'SHA_MISMATCH'):f.publish()
            self.assertFalse((f.out/'FULL_COMPLETION.json').exists())
    def test_full_open_h6_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL');f.jp.write_bytes(b'\n'.join(f.jp.read_bytes().splitlines()[:-1])+b'\n')
            with self.assertRaisesRegex(RuntimeError,'STAGE_UNCLOSED_OR_FAILED'):f.publish()
            self.assertFalse((f.out/'FULL_COMPLETION.json').exists())
    def test_full_claim_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            f=Physical(td,'FULL');f.publish()
            snapshot=(f.out/'FULL_COMPLETION.json').read_bytes()
            with self.assertRaises(FileExistsError):f.publish()
            self.assertEqual((f.out/'FULL_COMPLETION.json').read_bytes(),snapshot)

if __name__=='__main__':unittest.main(verbosity=2)
