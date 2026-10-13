"""Internal isolated engineering probes for CANARY receipt physical publication.

No real STATE or production sources. No auditor verdict. No effectful Windows entrypoint.
"""
from __future__ import annotations
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

CONTROL = pathlib.Path(__file__).resolve().parent.parent / 'candidate' / 'control'
sys.path.insert(0, str(CONTROL))
import FULL_STAGE_CONTINUATION as cont
from FULL_STAGE_EVIDENCE import closed_results
from D4_FIRST_ADMISSION_PREP import Reads, canonical, sha, strict_json

NODES = cont.RANGES['CANARY']

def make_result(node):
    if node == 'D9': return {k: 'PASS' for k in ('R1','R2','R3','R4','R5')}
    if node in ('D6','D7'): return {'PASS': True}
    if node == 'E1': return {'deep': {'POST_FULL_AUDIT': 'PASS', 'days': 1550,
                                    'rows': 7049522162, 'namespace': 3101,
                                    'manifest_sha256': 'A'*64},
                             'independent': {'schema': 'POSTFULL_INDEPENDENT_VERIFIER_V001',
                                             'status': 'PASS', 'days': 1550,
                                             'rows': 7049522162, 'namespace_files': 3101,
                                             'manifest_sha256': 'A'*64}}
    return {'physical_fixture': 'PASS', 'node': node}

class Fixture:
    def __init__(self, root, changes=None):
        self.root = pathlib.Path(root)
        self.runs = self.root / 'runs'; self.runs.mkdir()
        self.out = self.root / 'out'; self.out.mkdir()
        self.sp = self.root / 'STATE.json'; self.jp = self.root / 'STATE_JOURNAL.jsonl'
        self.attempt = 'attempt_001'; (self.runs/self.attempt).mkdir()
        results = {n:make_result(n) for n in NODES}
        if changes:
            for name, value in changes.items(): results[name] = value
        lines = []; prev = ''
        for node in NODES:
            for phase in ('STARTED','FINISHED'):
                rec = {'node':node,'phase':phase,'run_id':self.attempt,'prev_line_sha256':prev}
                if phase == 'FINISHED': rec.update(status='PASS',result_sha256=sha(canonical(results[node])))
                line = canonical(rec).rstrip(b'\n'); lines.append(line);prev = sha(line)
            (self.runs/self.attempt/f'RESULT_{node}.json').write_bytes(canonical(results[node]))
        self.jp.write_bytes(b'\n'.join(lines)+b'\n')
        self.state = {'schema':'TICKSTORE_ORCH_STATE_V001','status':'PASS',
                      'next_node':'E2','completed':['D4','D5',*NODES]}
        self.sp.write_bytes(canonical(self.state))
        self.o = SimpleNamespace(st=SimpleNamespace(sp=self.sp,jp=self.jp,d=self.state,runs=self.runs),rd=self.out)
        self.boundary = SimpleNamespace(stage='CANARY',nodes=NODES)
        self.ns = {'immutable_receipt': self.no_clobber}

    @staticmethod
    def no_clobber(path, data):
        with open(path,'xb') as f:
            f.write(data)
            f.flush()

    def admission(self, reads):
        # Physical reader rechecks all pinned bytes on every publish boundary.
        return SimpleNamespace(descriptor={'code_manifest_sha256':'A'*64,
                  'instance_sha256':'B'*64,'receipts':{'D5':{'path':'baseline'}}},
             receipt_sha='C'*64, read=reads.read, revalidate=reads.revalidate)

    def publish(self):
        with Reads() as reads:
            return cont.publish_stage(self.o,self.ns,self.boundary,self.admission(reads))

class StageCanaryPhysicalPublication(unittest.TestCase):
    def test_physical_positive_snapshot_and_chain(self):
        with tempfile.TemporaryDirectory() as td:
            f = Fixture(td)
            path, digest = f.publish()
            self.assertEqual(digest,sha(path.read_bytes()))
            receipt = strict_json((f.out/'STAGE_CANARY.json').read_bytes())
            chain = strict_json(path.read_bytes())
            self.assertEqual(receipt['status'],'PASS')
            self.assertEqual(receipt['previous_receipt_sha256'],'C'*64)
            self.assertEqual(chain['receipts']['CANARY']['sha256'],sha(canonical(receipt)))
            self.assertEqual((f.out/'STATE_AFTER.json').read_bytes(), f.sp.read_bytes())
            self.assertEqual((f.out/'JOURNAL_AFTER.jsonl').read_bytes(), f.jp.read_bytes())
            self.assertEqual(len(receipt['evidence']),len(NODES)+2)
            self.assertEqual(len({x['path'] for x in receipt['evidence']}),len(receipt['evidence']))
            for item in receipt['evidence']:
                self.assertEqual(sha(pathlib.Path(item['path']).read_bytes()),item['sha256'])

    def test_failure_independent_does_not_publish(self):
        with tempfile.TemporaryDirectory() as td:
            result=make_result('E1');result['independent']['status']='FAIL'
            f = Fixture(td,{'E1':result})
            with self.assertRaisesRegex(RuntimeError,'CANARY_READBACK'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])

    def test_mismatched_manifest_does_not_publish(self):
        with tempfile.TemporaryDirectory() as td:
            result=make_result('E1');result['independent']['manifest_sha256']='B'*64
            f = Fixture(td,{'E1':result})
            with self.assertRaisesRegex(RuntimeError,'CANARY_INDEPENDENT_READBACK_MISMATCH'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])

    def test_journal_result_sha_mismatch_does_not_publish(self):
        with tempfile.TemporaryDirectory() as td:
            f = Fixture(td)
            (f.runs/f.attempt/'RESULT_D8.json').write_bytes(b'{"altered":true}\n')
            with self.assertRaisesRegex(RuntimeError,'STAGE_RESULT_JOURNAL_HASH|SHA_MISMATCH'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])

    def test_unclosed_started_does_not_publish(self):
        with tempfile.TemporaryDirectory() as td:
            f = Fixture(td)
            lines = f.jp.read_bytes().splitlines()
            # E1 STARTED without FINISHED: hash chain remains valid for prior lines.
            f.jp.write_bytes(b'\n'.join(lines[:-1])+b'\n')
            with self.assertRaisesRegex(RuntimeError,'STAGE_UNCLOSED_OR_FAILED'):f.publish()
            self.assertEqual(list(f.out.iterdir()),[])

    def test_snapshot_collision_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            f = Fixture(td)
            (f.out/'STATE_AFTER.json').write_bytes(b'prior')
            with self.assertRaises(FileExistsError):f.publish()
            self.assertEqual((f.out/'STATE_AFTER.json').read_bytes(),b'prior')
            self.assertFalse((f.out/'STAGE_CANARY.json').exists())

    def test_no_duplicate_stage_receipt_publish(self):
        with tempfile.TemporaryDirectory() as td:
            f = Fixture(td)
            f.publish()
            original = (f.out/'STAGE_CANARY.json').read_bytes()
            with self.assertRaises(FileExistsError):f.publish()
            self.assertEqual((f.out/'STAGE_CANARY.json').read_bytes(),original)

if __name__=='__main__': unittest.main(verbosity=2)
