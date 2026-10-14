import hashlib, json, tempfile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'candidate/control'))
import G5_EVIDENCE_BUILDER as G
contract=json.loads((ROOT/'candidate/control/QUALIFICATION_CONTRACT.json').read_bytes())
with tempfile.TemporaryDirectory(prefix='cdt15_b2_audit_') as t:
 t=Path(t)
 code=t/'CODE_MANIFEST_EMPTY.json';code.write_text(json.dumps({'schema':'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001','files':[]}),encoding='utf-8')
 dig=hashlib.sha256(code.read_bytes()).hexdigest().upper()
 tests=[{'id':x,'status':'PASS'} for x in contract['required_tests']]
 tests.append(dict(tests[0]))
 harness={'schema':'TICKSTORE_CDT15_EXECUTED_DELTA_V001','native_windows':True,'selection':'NATIVE','code_manifest_sha256':dig,'tested_code_unchanged':True,'success':False,'tests':tests,'totals':{'tests_run':0,'failures':0,'errors':0,'skips':0}}
 hp=t/'UNTRUSTED_HARNESS.json';hp.write_text(json.dumps(harness),encoding='utf8')
 fake=t/'SAME_FAKE_PROOF_ALL_SIX.txt';fake.write_text('dummy proof; not a native run',encoding='utf8');fp_sha=hashlib.sha256(fake.read_bytes()).hexdigest().upper()
 proofs={'schema':'TICKSTORE_G5_TARGET_PROOF_INPUT_V001','proofs':{p:{'status':'PASS','source':'same artificial evidence for all proofs','evidence':[{'path':str(fake),'sha256':fp_sha}]} for p in contract['required_target_proofs']}}
 pp=t/'UNTRUSTED_PROOFS.json';pp.write_text(json.dumps(proofs),encoding='utf8')
 c=G.build(harness_result=hp,code_manifest=code,baseline_archive=ROOT/'tests/fixtures/V38_NATIVE_QUALIFICATION_RESULT_ORIGINAL_DC73A8C3.zip',proofs_input=pp,known_blockers=[],out_dir=t/'EVIDENCE')
 out={'test_name':'ADVERSARIAL_SYNTHETIC_FOR_AUDIT_ONLY','status':c['status'],'self_check':c['consumer_self_check'],'blockers':c['known_blockers'],'inputs':{'empty_code_manifest_files':0,'declared_native_without_native_receipt':True,'harness_tests_records':len(tests),'unique_test_ids':len(contract['required_tests']),'harness_total_tests_run_claimed':0,'harness_success':False,'target_proofs_reusing_same_non_native_file':len(contract['required_target_proofs'])},'gate_verdict_issued':c['gate_verdict_issued'],'production_modified':False}
 print(json.dumps(out,indent=2))
 assert c['status']=='COMPLETE' and c['consumer_self_check']=='ACCEPTS' and not c['gate_verdict_issued']
