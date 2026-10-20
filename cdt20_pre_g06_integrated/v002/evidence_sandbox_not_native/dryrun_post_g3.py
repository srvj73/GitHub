"""SANDBOX-ONLY dry run of the post-G3 chain on real 12:19 bytes REBOUND in scratch.
Output is SYNTHETIC_REBIND, never native evidence, never delivered as proof."""
import sys,json,shutil,types,zipfile,os
from pathlib import Path
from unittest import mock
p2,extract,package,review_src,work=map(Path,sys.argv[1:6])
cand=extract/'implementation_v001/candidate'
for f in ('full','control','adapter','g5proof'):sys.path.insert(0,str(cand/f))
import FULL_CRASH_RECOVERY as R, PRE_G06_CAMPAIGN as C, FULL_G5_COMPLETE_PROOF_GATE as gate
import PRE_G06_PROOF_PROJECTION as P, PRE_G06_COMPLETENESS as completeness, G5_FINAL_COMPLETENESS_PRODUCER as producer
run='R08_Q1_20261020121927_07996cf20a1e'
root=work/run
if work.exists():shutil.rmtree(work)
shutil.copytree(p2,root)
work=work.resolve()
code,members=producer.verify_final_zip(package);pack=producer.hash_path(package)
def rw(p,fn):
    obj=json.loads(p.read_bytes());fn(obj);p.write_bytes(R.encoded(obj))
tests_dir='implementation_v001/tests/'
# Units absent from 12:19 (new suites): run in SANDBOX via the G0 runner, labelled synthetic.
import subprocess,hashlib
for name in C.EXTRA:
    key='DELTA_'+name
    if (root/'UNITS'/key).exists():continue
    (root/'UNITS'/key).mkdir(parents=True);log=root/'LOGS'/(key+'.log');res=work/(key+'.result.json')
    t=work/('T_'+key);t.mkdir()
    subprocess.run([sys.executable,'-I','-B',sys.argv[6],'--test',str(extract/'implementation_v001/tests'/name),
                    '--candidate',str(cand),'--log',str(log),'--result',str(res)],check=True,env=dict(os.environ,TEMP=str(t)))
    r=json.loads(res.read_bytes())
    unit={'status':'PASS','unit':key,'native_windows':False,'process':{'pid':1,'creation_filetime':1,'state':'SANDBOX'},
          'test_count':r['tests_run'],'skipped':bool(r['skipped']),'failures':0,'errors':0,'exit_code':0,
          'test_source_sha256':R.sha(members[tests_dir+name]),'SYNTHETIC_SANDBOX':True}
    R.publish(root/'UNITS'/key/'RESULT.json',unit)
    R.publish(root/'COMMITS'/(key+'.json'),dict(schema='CDT19_NATIVE_UNIT_COMMIT_V001',package_sha256=pack,code_sha256=code,
        result=unit,artifacts=[C.physical(root/'UNITS'/key/'RESULT.json',root),C.physical(log,root)],owner=[],
        own_descendants_final=[],observed_processes=[],seconds=0))
    print('DRYRUN_SYNTHETIC_UNIT',key)
for p in (root/'COMMITS').glob('*.json'):
    def f(o):
        o['package_sha256']=pack;o['code_sha256']=code
        if o['result'].get('test_source_sha256'):
            name=p.stem.split('_',1)[1]
            o['result']['test_source_sha256']=R.sha(members[tests_dir+name]) if tests_dir+name in members else o['result']['test_source_sha256']
    rw(p,f)
for p in (root/'UNITS').glob('*/RESULT.json'):
    def f(o):
        if o.get('test_source_sha256'):
            name=p.parent.name.split('_',1)[1]
            if tests_dir+name in members:o['test_source_sha256']=R.sha(members[tests_dir+name])
    rw(p,f)
for p in (root/'COMMITS').glob('*.json'):
    def f(o):
        o['result']=R.read(root/'UNITS'/p.stem/'RESULT.json')[0]
        o['artifacts']=[C.physical(root/a['member'],root) if a['member'].startswith('UNITS/') else a for a in o['artifacts']]
    rw(p,f)
rw(root/'EVIDENCE/CONSUMERS/ELEVEN_CONSUMERS.json',lambda o:o.update(code_manifest_sha256=code))
for n in ('PS51_INSTALL_MENU','STAGE_B_REAL_ISOLATED_PATH_NATIVE','D4_REAL_ISOLATED_PATH_NATIVE'):
    rw(root/'EVIDENCE/PROOFS'/n/'PROOF_RECEIPT.json',lambda o:o.update(code_manifest_sha256=code,final_zip_sha256=pack))
for n in ('ENGINEERING_RESULT.json','LIVE_STATUS.json'):(root/n).unlink()
(root/'CAMPAIGN.lock').write_bytes(b'0')
result={'schema':'CDT19_PRE_B06_NATIVE_ENGINEERING_V002','status':'BLOCKED','tests':{},'additional_tests':{},
    'production_modified':False,'full_started':False,'b06':'NOT_STARTED','g5_final':'NOT_ISSUED',
    'native_proofs_are_sandbox_experiments':False,'synthetic_d4_stage_b_substitute':False,
    'qualification_scope':'REAL_PACKAGED_CODE_OWNED_ISOLATED_NTFS_PRE_B06',
    'physical_powerloss':'NOT_TESTED_PHYSICAL_POWERLOSS','blockers':[]}
result.update(code_manifest_sha256=code,final_zip_sha256=pack,run_id=run)
for name in ('PS51_INSTALL_MENU','STAGE_B_REAL_ISOLATED_PATH_NATIVE','D4_REAL_ISOLATED_PATH_NATIVE'):
    result['tests']['G5_'+name]={'status':'PASS_NATIVE_SCOPED','exit_code':0}
obs=R.read(root/'EVIDENCE/PROOFS/STAGE_B_REAL_ISOLATED_PATH_NATIVE/REAL_BOUNDED_OBSERVATION.json')[0]
for name in gate.SUITES:
    key='SUITE_'+name
    test={'test_count':obs['suites'][name]['run']} if name in C.STAGE_SUITES else R.read(root/'UNITS'/key/'RESULT.json')[0]
    result['tests'][key]=C.suite_record(root,key,test)
for name in C.EXTRA:
    key='DELTA_'+name
    if (root/'UNITS'/key/'RESULT.json').exists():result['additional_tests'][key]=R.read(root/'UNITS'/key/'RESULT.json')[0]
    else:print('DRYRUN_MISSING_DELTA_UNIT',key)
ref=C.project_consumer_refs(root)
import PRE_B06_ENGINEERING_GATE as cg
cg.verify_dossier(R.read(root/ref['member'])[0],cand,root/'EVIDENCE/PRE_B06',native_required=False)
result.update(pre_b06_11_receipt=ref,pre_b06_11_evidence_class='ENGINEERING_READINESS_NOT_PRODUCTION')
result['tests']['PRE_B06_11_CHAIN']={'status':'PASS_PRE_B06_ENGINEERING','exit_code':0,'receipt':ref}
with mock.patch.object(P,'os',types.SimpleNamespace(name='nt')):P.produce(root,code,pack)
for name in ('PROCESS_TREE_CRASH_CONTAINMENT','SAFE_STOP_RESUME_ROW_GROUP','POWERLOSS_EMULATED'):
    result['tests']['G5_'+name]={'status':'PASS_NATIVE_SCOPED','exit_code':0}
result['status']='PASS_NATIVE_INTEGRATED_PRE_B06'
C.write_terminal(root,result)
archive=C.seal_return(root,'R08_RETURN.zip',excluded=('R08_RETURN.zip','R08_RETURN.sha256'))
index={r['path']:r for r in json.loads(members['implementation_v001/RUNTIME_CODE_MANIFEST.json'])['files']}
gate.verify_native_campaign(archive.read_bytes(),code,pack,index,final_members=members)
print('DRYRUN_VERIFY_NATIVE_CAMPAIGN=PASS SIZE='+str(archive.stat().st_size))
review=json.loads(review_src.read_bytes());review.update(package_sha256=pack,code_manifest_sha256=code)
rv=work/'REVIEW.json';rv.write_bytes(R.encoded(review))
status=completeness.close(package,archive,rv,root)
print('DRYRUN_COMPLETENESS='+status.get('engineering_five_part_completeness','?'))
print(json.dumps(status,indent=1)[:3000])
