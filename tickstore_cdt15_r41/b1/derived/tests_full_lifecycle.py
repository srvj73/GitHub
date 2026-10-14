"""Directed orchestration tests, isolated fixtures; never Windows qualification."""
from pathlib import Path
import sys, unittest, tempfile, types, json, copy, os
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'cdt15'))
import tests_delta as prior
from D4_FIRST_ADMISSION_PREP import Reads, canonical, sha, strict_json
import FULL_LIFECYCLE as life
import FULL_STAGE_CONTINUATION as cont
import FULL_RUNNER as runner
import tickstore_full_multiwork as mw
from FULL_STAGE_EVIDENCE import closed_results

class FullLifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
  self.ns=cont.load((prior.ROOT/'recovery/modules/orchestrator.py').read_bytes(),prior.ROOT/'recovery/modules/orchestrator.py')
  self.boundary=cont.StageBoundary('FULL'); self.state=self.ns['State'](self.root)
  self.state.d=dict(schema='TICKSTORE_ORCH_STATE_V001',next_node='G3',status='PASS',completed=['D4','G2'],canary_scratch_cert='fixture')
  self.ns['atomj'](self.state.sp,self.state.d)
  self.state.log('G2','STARTED',run_id='predecessor');self.state.log('G2','FINISHED',status='PASS',result_sha256='F'*64)
  self.rd=self.state.runs/'attempt';self.rd.mkdir()
  self.a=Reads();self.addCleanup(self.a.close)
  self.a.instance=dict(run_id='same_instance',bindings=dict(source_root=str(self.root/'source'),dest_root=str(self.root/'dest'),scratch_root=str(self.root/'scratch')),resources=dict(max_workers=4,ram_target_percent=50),ledger_path=str(self.root/'ledger'))
  self.a.descriptor=dict(instance_sha256='A'*64,code_manifest_sha256='B'*64,receipts={})
  self.a.receipt_hashes={'FULL_ADMISSION':'C'*64}
  self.rec=dict(schema='TICKSTORE_MULTIWORK_RECONCILIATION_V001',status='PASS',days=1550,rows=7049522162,manifest_sha256='D'*64,run_id='same_instance',instance_sha256='A'*64,code_manifest_sha256='B'*64)
  self.h2=dict(deep=dict(POST_FULL_AUDIT='PASS',days=1550,rows=7049522162,namespace=3101,manifest_sha256='D'*64),independent=dict(schema='POSTFULL_INDEPENDENT_VERIFIER_V001',status='PASS',days=1550,rows=7049522162,namespace_files=3101,manifest_sha256='D'*64))
  self.pack=self.root/'pack.zip';self.pack.write_bytes(b'fixture pack')
  self.executed=[]
  def runnode(n):
   self.executed.append(n)
   if n=='H2':self.state.d['postfull_h2']=copy.deepcopy(self.h2);return self.state.d['postfull_h2']
   if n=='H6':return dict(path=str(self.pack),sha256=sha(self.pack.read_bytes()))
   return dict(PASS=True)
  self.o=types.SimpleNamespace(st=self.state,id='attempt',rd=self.rd,control=self.root,runnode=runnode,cfg={'production_dest_root':str(self.root/'dest')},eng=types.SimpleNamespace(recovery_process_census=lambda:{'known_recovery_supervisor_or_workers':0}))
  self.ns['immutable_receipt']=self.writer
  def finish(*a,**kw):
   before=strict_json(self.state.sp.read_bytes()); original(*a,**kw);self.boundary.transition(before,self.state.d)
  original=self.state.finish;self.state.finish=finish
  life.install(self.o,self.ns,self.a,'AUTO')
 def writer(self,p,raw):
  with Path(p).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 def engine(self,*args,completion=None,**kw):completion(copy.deepcopy(self.rec));return 0
 def execute(self):
  with patch.object(mw,'_execute_admitted_multiwork',side_effect=self.engine):return cont.execute_nodes(self.o,self.ns,self.boundary,self.a.revalidate)
 def test_full_requires_h6_and_final_receipt(self):
  self.assertEqual(self.execute(),0);self.assertEqual(self.state.d['next_node'],'I1')
  self.assertIn('H6',self.executed);self.assertFalse((self.rd/'FULL_COMPLETION.json').exists())
  p,h=life.publish_completion(self.o,self.ns,self.a,self.boundary.nodes)
  self.assertEqual(sha(p.read_bytes()),h);self.assertEqual(strict_json(p.read_bytes())['full_admission_sha256'],'C'*64)
 def test_engine_zero_without_reconciliation_cannot_advance(self):
  with patch.object(mw,'_execute_admitted_multiwork',return_value=0),self.assertRaisesRegex(RuntimeError,'RECEIPT_MISSING'):
   cont.execute_nodes(self.o,self.ns,self.boundary,self.a.revalidate)
  self.assertEqual(self.state.d['next_node'],'G3');self.assertEqual(self.state.d['status'],'FAIL')
 def test_cooperative_stop_keeps_g3_and_exact_instance(self):
  with patch.object(mw,'_execute_admitted_multiwork',side_effect=mw.CooperativeSafeStop('fixture')):
   self.assertEqual(cont.execute_nodes(self.o,self.ns,self.boundary,self.a.revalidate),130)
  self.assertEqual(self.state.d['next_node'],'G3');self.assertEqual(self.state.d['status'],'SAFE_STOP');self.assertEqual(self.a.instance['run_id'],'same_instance');self.assertNotIn('G3',self.state.d['completed'])
 def test_unproven_interrupt_is_not_safe_stop(self):
  with patch.object(mw,'_execute_admitted_multiwork',side_effect=KeyboardInterrupt()),self.assertRaises(KeyboardInterrupt):
   cont.execute_nodes(self.o,self.ns,self.boundary,self.a.revalidate)
  self.assertEqual(self.state.d['status'],'FAIL');self.assertNotIn('G3',self.state.d['completed'])
 def test_h2_counts_mismatch_blocks_h3(self):
  self.rec['rows']=7049522161
  with self.assertRaisesRegex(RuntimeError,'POSTVERIFY_MISMATCH:rows'):self.execute()
  self.assertEqual(self.state.d['next_node'],'H3');self.assertNotIn('H4',self.executed)
 def test_h2_independent_failure_blocks_h3(self):
  self.h2['independent']['status']='FAIL'
  with self.assertRaisesRegex(RuntimeError,'POSTVERIFY_NOT_PASS'):self.execute()
 def test_foreign_reconciliation_blocks(self):
  self.rec['run_id']='foreign'
  with self.assertRaisesRegex(RuntimeError,'RECONCILIATION_INSTANCE'):self.execute()
 def test_post_h6_closure_retry_does_not_rerun_full(self):
  self.execute();boundary=cont.StageBoundary('FULL',close_only=True);boundary.validate(self.state.d)
  other=self.state.runs/'closure';other.mkdir();self.o.rd=other
  with patch.object(mw,'_execute_admitted_multiwork',side_effect=AssertionError('must not run')):
   p,h=life.publish_completion(self.o,self.ns,self.a,boundary.nodes)
  self.assertTrue(p.exists());self.assertEqual(self.state.d['next_node'],'I1')
 def test_close_before_h6_blocks(self):
  with self.assertRaisesRegex(RuntimeError,'FINAL_STATE'):life.publish_completion(self.o,self.ns,self.a,self.boundary.nodes)
 def test_close_cannot_mutate_state(self):
  self.execute();b=cont.StageBoundary('FULL',close_only=True)
  with self.assertRaisesRegex(RuntimeError,'CANNOT_MUTATE'):b.transition(self.state.d,self.state.d)
 def test_legacy_g5_engine_cannot_run(self):
  self.state.d['full_safe_stop']=True
  with self.assertRaisesRegex(RuntimeError,'REENTER_G3'):self.o.runnode('G5')
 def test_g6_stale_lock_blocks_without_legacy_launch(self):
  dest=self.root/'dest';dest.mkdir();(dest/'TICKSTORE_WRITER.lock').write_bytes(b'fixture')
  with self.assertRaisesRegex(RuntimeError,'LOCK_RECONCILIATION_REQUIRED'):self.o.runnode('G6')
 def test_live_process_blocks_g6(self):
  self.o.eng.recovery_process_census=lambda:{'known_recovery_supervisor_or_workers':1}
  with self.assertRaisesRegex(RuntimeError,'PROCESS_RECONCILIATION_REQUIRED'):self.o.runnode('G6')
 def test_stage_router_uses_bounded_full_lifecycle(self):
  a=types.SimpleNamespace(stage='FULL')
  with patch.object(cont,'run',return_value=91) as call:self.assertEqual(runner.run(a),91)
  call.assert_called_once_with(a)
 def test_readmission_router_uses_bounded_lifecycle(self):
  a=types.SimpleNamespace(stage='FULL_READMIT')
  with patch.object(cont,'run',return_value=92) as call:self.assertEqual(runner.run(a),92)
  call.assert_called_once_with(a)
 def test_g7_does_not_publish_full_complete_before_h6(self):
  result=self.o.runnode('G7')
  self.assertFalse(result['full_complete']);self.assertNotIn('G7',self.executed)
  self.assertFalse((self.root/'FULL_COMPLETE.json').exists())
 def test_failed_heartbeat_blocks_pass_commit(self):
  def fail():raise RuntimeError('DURABLE_HEARTBEAT_FAILED')
  h=types.SimpleNamespace(update=lambda **kw:None,check=fail)
  with patch.object(mw,'_execute_admitted_multiwork',side_effect=self.engine),self.assertRaisesRegex(RuntimeError,'HEARTBEAT_FAILED'):
   cont.execute_nodes(self.o,self.ns,self.boundary,self.a.revalidate,h)
  self.assertEqual(self.state.d['next_node'],'G3');self.assertEqual(self.state.d['status'],'FAIL')
  self.assertFalse((self.rd/'RESULT_G3.json').exists())

class Readmission(FullLifecycle):
 # Inherit fixture only, not the full test list through explicit suite below.
 def test_refresh_preserves_instance_predecessor_and_prior_receipt(self):
  old=self.root/'old.json';old.write_bytes(b'prior receipt')
  self.a.descriptor['receipts']={'FULL_PREP':{'path':'prep','sha256':'E'*64},'FULL_ADMISSION':{'path':str(old),'sha256':sha(old.read_bytes())}}
  self.a.receipt_hashes['FULL_PREP']='E'*64
  self.a.receipts={'FULL_ADMISSION':{'evidence':[]}}
  p,h=life.refresh_admission(self.o,self.ns,self.a,{'generation':{'id':'same'}},self.boundary.nodes)
  descriptor=strict_json(p.read_bytes());receipt=strict_json(Path(descriptor['receipts']['FULL_ADMISSION']['path']).read_bytes())
  self.assertEqual(receipt['previous_receipt_sha256'],'E'*64);self.assertEqual(receipt['readmission_of_sha256'],sha(old.read_bytes()));self.assertEqual(receipt['run_id'],'same_instance')
  self.assertEqual(self.a.descriptor['receipts']['FULL_ADMISSION']['path'],str(old));self.assertEqual(old.read_bytes(),b'prior receipt')
  self.assertIn({'path':str(old),'sha256':sha(old.read_bytes())},receipt['evidence'])

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(FullLifecycle)
 suite.addTest(Readmission('test_refresh_preserves_instance_predecessor_and_prior_receipt'))
 result=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(not result.wasSuccessful())
