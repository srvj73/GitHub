"""CDT18 PRE-G06 original FULL successor — bounded integrated Windows qualification.

NOT a G5/B06/production gate. Executes only genuine packaged code paths in an owned
sandbox, never synthesizes an operational D4/Stage B success or an origin decision.
"""
from __future__ import annotations
import datetime as dt,hashlib,json,os,pathlib,stat,sys,time,traceback,uuid,zipfile,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
CANDIDATE_SHA='E52551379852089F5253405F749328A18E691040B7E6D5A8FFA4CBB062A23BB9'
PREV_SHA='C8AE6FF0EF3FA1752168EAD865EE85EC2DCA82DC093DA3B826C5C5703A1CF490'
PYTHON_SHA='4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
LEGACY=('adapter/INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1','adapter/runtime_locator_adapter.py',
'adapter/runtime_locator_inline_entry.py','adapter/runtime_locator_orchestrator_entry.py',
'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1','control/D4_FIRST_ADMISSION_TRANSACTION.py',
'control/D4_ROOTS_EVIDENCE.py','recovery/engine/tickstore_publisher_recovery_v004_candidate.py',
'recovery/engine/tickstore_publisher_recovery_v004_release.py',
'recovery/loader/INLINE_ROOT_LOADER_V004_R1R1.ps1','recovery/modules/orchestrator.py')
NATIVE_UNITS=('SOURCE_AND_ORIGINAL_OPUS_INHERITED_BYTES','NEW_G5_REAL_CODE_CONTRACT',
 'D4_ISOLATED_REAL_CODE_NATIVE','STAGE_B_ISOLATED_REAL_CODE_NATIVE',
 'NATIVE_ADVERSARIAL_FALSE_COMPLETENESS')

def now():return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec='milliseconds')
def sha(raw):return hashlib.sha256(raw).hexdigest().upper()
def hashfile(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for buf in iter(lambda:f.read(1024*1024),b''):h.update(buf)
 return h.hexdigest().upper()
def req(cond,reason):
 if not cond:raise RuntimeError(reason)
def canon(obj):return (json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=True)+'\n').encode('ascii')
def atom(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);raw=obj if isinstance(obj,bytes) else canon(obj)
 tmp=p.with_name(p.name+'.atomic.'+uuid.uuid4().hex)
 with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
 req(p.read_bytes()==raw,'ATOMIC_READBACK:'+p.name)
def zip_verified(path):
 with zipfile.ZipFile(path) as z:
  infos=z.infolist();name=[x.filename for x in infos];req(len(name)==len({n.casefold() for n in name}),'ZIP_DUPLICATE')
  req(all(n and not n.startswith('/') and '\\' not in n and ':' not in n and all(y not in ('','.','..') for y in n.split('/'))
    and not x.is_dir() and ((x.external_attr>>16)&0o170000)!=0o120000 for x,n in zip(infos,name)),'ZIP_UNSAFE_MEMBER')
  req(z.testzip() is None,'ZIP_BAD_CRC')
  return {n:z.read(n) for n in name}
def prepare():
 path=ROOT/'FINAL_CANDIDATE.zip';req(path.is_file(),'CANDIDATE_MISSING')
 req(hashfile(path)==CANDIDATE_SHA,'FINAL_CANDIDATE_SHA_MISMATCH')
 files=zip_verified(path);req('PACKAGE_MANIFEST.json' in files and 'implementation_v001/RUNTIME_CODE_MANIFEST.json' in files,'PACKAGE_ROOT')
 m=json.loads(files['PACKAGE_MANIFEST.json']);req(m.get('schema')=='TICKSTORE_FINAL_PACKAGE_MANIFEST_V001','PACKAGE_SCHEMA')
 rows=m.get('files',[]);req(len(rows)+1==len(files) and {r['path'] for r in rows}==set(files)-{'PACKAGE_MANIFEST.json'},'PACKAGE_SET')
 for r in rows:req(sha(files[r['path']])==r['sha256'] and len(files[r['path']])==r['bytes'],'PACKAGE_ITEM:'+r['path'])
 cm=json.loads(files['implementation_v001/RUNTIME_CODE_MANIFEST.json']);idx={r['path']:r for r in cm['files']}
 req(len(idx)==151 and len(idx)==len(cm['files']),'RUNTIME_MEMBER_COUNT_151')
 names={n.removeprefix('implementation_v001/candidate/') for n in files if n.startswith('implementation_v001/candidate/')}
 req(names==set(idx),'RUNTIME_EXPECTED_SET')
 for key,ref in idx.items():
  b=files['implementation_v001/candidate/'+key];req(sha(b)==ref['sha256'] and len(b)==ref['bytes'],'RUNTIME_MEMBER:'+key)
 for member in LEGACY:req(member in idx,'LEGACY_MISSING:'+member)
 source=ROOT/'SOURCE';req(not source.exists(),'SOURCE_EXISTS_NO_REPEAT')
 source.mkdir()
 with zipfile.ZipFile(path) as z:z.extractall(source)
 for member,ref in idx.items():req(hashfile(source/'implementation_v001/candidate'/member)==ref['sha256'],'AFTER_EXTRACTION_DRIFT:'+member)
 old=ROOT/'PREVIOUS_NATIVE_RETURN.zip';req(old.is_file() and hashfile(old)==PREV_SHA,'PREVIOUS_NATIVE_7_7_RETURN_IDENTITY')
 old_z=zip_verified(old);require_json=json.loads(old_z['PRE_G06_NATIVE_RESULT.json'])
 req(require_json.get('committed')==7 and require_json.get('total')==7 and
     require_json.get('status','').startswith('PASS') and require_json.get('g5_final')=='NOT_ISSUED', 'PRIOR_NATIVE_SCOPE_NOT_7_7')
 obj={'schema':'CDT18_PRE_G06_REAL_CODE_SOURCE_PREFLIGHT_V001','status':'PASS_SCOPE_ONLY',
      'runtime_count':len(idx),'legacy_count':len(LEGACY),'final_zip_sha256':CANDIDATE_SHA,
      'code_manifest_sha256':sha(files['implementation_v001/RUNTIME_CODE_MANIFEST.json']),
      'previous_native_return_sha256':PREV_SHA,'historical_7_7_reused_without_rerun':True,
      'python':sys.version,'original_full_basis':'OPUS_R47_C6_LINEAGE_FROM_CDT17_SEALED_PARENT',
      'original_opus_zip_rehashed_in_this_run':False}
 atom(ROOT/'SOURCE_PREFLIGHT.json',obj)
 return obj

def main():
 import argparse
 ap=argparse.ArgumentParser(allow_abbrev=False)
 ap.add_argument('mode',choices=['prepare','qualify'])
 a=ap.parse_args();status='BLOCKED';code=2
 rec={'schema':'CDT18_PRE_G06_REAL_CODE_NATIVE_V001','started_at':now(),
      'mode':a.mode,'candidate_sha256':CANDIDATE_SHA,'commit':0,'total':len(NATIVE_UNITS),
      'unit_results':{},'b06':'NOT_STARTED','g5_final':'NOT_ISSUED','full_started':False,
      'candidate_completeness':'NOT_PROVEN','legacy_11_integrated':'NOT_PROVEN',
      'five_part_completeness':{k:'NOT_PROVEN' for k in ('integrated','blockers_closed','tested_packaged','adversarial','frozen')},
      'error':None}
 try:
  if a.mode=='prepare':
   obj=prepare();print('SOURCE_PREFLIGHT=PASS RUNTIME=151/151 LEGACY_11_IDENTITIES=PASS',flush=True);return 0
  req(os.name=='nt','WINDOWS_NATIVE_ONLY');req(hashfile(sys.executable)==PYTHON_SHA,'PYTHON_EXACT_SHA')
  root=ROOT/'SOURCE/implementation_v001';req(root.is_dir(),'SOURCE_NOT_PREPARED')
  pre=json.loads((ROOT/'SOURCE_PREFLIGHT.json').read_bytes());req(pre['final_zip_sha256']==CANDIDATE_SHA,'PREFLIGHT_BYTES_DRIFT')
  # Base status preserves 7/7. The next units are NEW changed byte paths only.
  from unit_supervisor import run,QualificationStopped
  logs=ROOT/'LOGS';logs.mkdir(exist_ok=False)
  prog=ROOT/'LIVE_STATUS.json'
  def persist(unit,phase,elapsed=0):
   atom(prog,{'unit':unit,'phase':phase,'committed':rec['commit'],'total':rec['total'],
         'pct':round(rec['commit']*100/rec['total'],2),'elapsed_s':round(elapsed,2),
         'eta':'UNKNOWN','eta_reason':'NOT_ESTIMABLE_FIRST_NATIVE_PROOF', 'eta_as_of':now(),'updated_at':now()})
  def store(name,body):
   rec['unit_results'][name]=body
   atom(logs/(name+'.RECEIPT.json'),body)
   req((logs/(name+'.RECEIPT.json')).read_bytes()==canon(body),'RECEIPT_READBACK')
   rec['commit']+=1
   print('UNIT='+name+' STATUS=PASS_SCOPED_COMMITTED COMMITTED='+str(rec['commit'])+'/'+str(rec['total']),flush=True)
   persist(name,'COMMITTED')
  def supervise(name,cmd,timeout):
   log=logs/(name+'.log')
   persist(name,'RUNNING')
   def beat(s):
    elapsed=s.get('elapsed_s',0)
    persist(name,'RUNNING',elapsed)
    print('UNIT='+name+' PHASE=RUNNING COMMITTED='+str(rec['commit'])+'/'+str(rec['total'])+
      ' PROGRESS_PCT='+str(round(rec['commit']*100/rec['total'],2))+' ELAPSED_S='+str(elapsed)+
      ' ETA=UNKNOWN ETA_AS_OF='+now(),flush=True)
   process=run(cmd,cwd=ROOT,log=log,process_control_dir=root/'candidate/full',heartbeat=beat,
        timeout=timeout,interval=2,stop_requested=lambda:(ROOT/'STOP.request').exists(),environment=dict(os.environ,
        PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',TMP=str(ROOT/'WORK'),TEMP=str(ROOT/'WORK')))
   atom(logs/(name+'.PROCESS_RECONCILIATION.json'),process)
   req(process['exit_code']==0 and process['tree_reconciled'] is True,'CHILD_EXIT_NONZERO:'+str(process['exit_code']))
   return {'code':0,'process_sha256':hashfile(logs/(name+'.PROCESS_RECONCILIATION.json')),
           'log_sha256':hashfile(log),'native_job_zero_final_members':True}
  w=ROOT/'WORK';w.mkdir(exist_ok=False)
  cm=pre['code_manifest_sha256'];idx=json.loads((root/'RUNTIME_CODE_MANIFEST.json').read_bytes())['files'];idx={x['path']:x for x in idx}
  req(len(idx)==151 and all((root/'candidate'/l).exists() for l in LEGACY),'SOURCE_DRIFT_ON_RUN')
  store(NATIVE_UNITS[0],{'status':'PASS_NATIVE_SOURCE_IDENTITY_ONLY','sha256':sha(canon({k:idx[k] for k in LEGACY})),
                       'integrated_effectful_execution':False})
  # Runners execute changed G5 source/consumer identities only, not old FULL history.
  cmd=[sys.executable,'-I','-B',str(root/'tests/test_g5_proof_runner_contract.py')]
  store(NATIVE_UNITS[1],supervise(NATIVE_UNITS[1],cmd,180))
  engine=root/'candidate/g5proof/G5_PROOF_RUNNERS.py'
  evidence=ROOT/'EVIDENCE';evidence.mkdir(exist_ok=False)
  for name,proof in ((NATIVE_UNITS[2],'D4_REAL_ISOLATED_PATH_NATIVE'),(NATIVE_UNITS[3],'STAGE_B_REAL_ISOLATED_PATH_NATIVE')):
   args=[sys.executable,'-I','-B',str(engine),'--proof',proof,'--work',str(w/proof),
        '--evidence',str(evidence),'--run-id',ROOT.name,'--final-zip-sha256',CANDIDATE_SHA,
        '--code-manifest-sha256',cm,'--local-appdata',os.environ.get('LOCALAPPDATA','')]
   cr=supervise(name,args,1200)
   receipt=evidence/'PROOFS'/proof/'PROOF_RECEIPT.json';req(receipt.is_file(),'TYPED_PROOF_RECEIPT_MISSING')
   p=json.loads(receipt.read_bytes());req(p['status']=='PASS' and p['native_windows'] is True
     and p['production_execution'] is False and all(v=='PASS' for v in p['checks'].values()),
     'TYPED_PROOF_NOT_NATIVE_PASS:'+proof)
   cr.update(typed_receipt_sha256=hashfile(receipt),scope='REAL_CODE_ISOLATED_NOT_OPERATIONAL_D4_OR_STAGE_B')
   store(name,cr)
  store(NATIVE_UNITS[4],supervise(NATIVE_UNITS[4],
    [sys.executable,'-I','-B',str(root/'tests/test_cdt17_final_g5_complete_proof_gate.py')],180))
  req(hashfile(ROOT/'FINAL_CANDIDATE.zip')==CANDIDATE_SHA,'SOURCE_CHANGED_AFTER_TEST')
  rec['candidate_tested_equals_packaged']='PASS_FOR_TESTED_NEW_CODE_BYTES_NOT_COMPLETE_G5'
  rec['scoped_g5_real_code_native']='PASS_TWO_BOUNDED_CODEPATHS'
  rec['status']='PASS_NATIVE_REAL_CODE_BOUNDED_NOT_PRE_G06_FINAL';status=rec['status'];code=0
 except BaseException as e:
  rec['error']=type(e).__name__+':'+str(e);rec['status']='BLOCKED';print('NATIVE_SOURCE_ERROR='+rec['error'],file=sys.stderr,flush=True)
  if 'QualificationStopped' in type(e).__name__:
   try:atom(ROOT/'CHILD_ERROR_PROCESS_RECONCILIATION.json',e.report)
   except Exception:pass
 finally:
  if a.mode=='qualify':
   rec['finished_at']=now()
   try:
    atom(ROOT/'PRE_G06_NATIVE_RESULT.json',rec)
    # Return evidence exact files and small logs only. Large source remains locally in the run root.
    out=ROOT/'PRE_G06_NATIVE_RETURN.zip'
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
     include=[ROOT/'PRE_G06_NATIVE_RESULT.json', ROOT/'SOURCE_PREFLIGHT.json']
     if (ROOT/'PS51_PARSE_RECEIPT.json').is_file():include.append(ROOT/'PS51_PARSE_RECEIPT.json')
     if (ROOT/'LIVE_STATUS.json').is_file():include.append(ROOT/'LIVE_STATUS.json')
     include += [p for p in (ROOT/'LOGS').rglob('*') if p.is_file()] if (ROOT/'LOGS').exists() else []
     include += [p for p in (ROOT/'EVIDENCE').rglob('*') if p.is_file()] if (ROOT/'EVIDENCE').exists() else []
     if (ROOT/'CHILD_ERROR_PROCESS_RECONCILIATION.json').exists():include.append(ROOT/'CHILD_ERROR_PROCESS_RECONCILIATION.json')
     for p in include:z.write(p,p.relative_to(ROOT).as_posix())
    print('RESULT_JSON='+str(ROOT/'PRE_G06_NATIVE_RESULT.json')+' SHA256='+hashfile(ROOT/'PRE_G06_NATIVE_RESULT.json'),flush=True)
    print('RETURN_ZIP='+str(out)+' SHA256='+hashfile(out),flush=True)
   except BaseException as error:
    print('EVIDENCE_CLOSE_FAILED='+str(error),file=sys.stderr,flush=True);code=3
   print('NATIVE_STATUS='+str(rec.get('status'))+' LEGACY_11_FULL_CHAIN=NOT_PROVEN G5_FINAL=NOT_ISSUED B06=NOT_STARTED FULL_STARTED=NO',flush=True)
 return code

if __name__=='__main__':raise SystemExit(main())
