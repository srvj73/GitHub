"""Native admission producer for the existing D4 runtime; no D4 dispatch here.

Only --admit-first can materialize an instance and it requires final-code
completeness, independent B06, native B07 and current technical policy receipts.
--validate-existing authenticates the existing identity without replacing it.
No fixture bypass is exposed on the command line.
"""
from __future__ import annotations
import argparse
import base64
import contextlib
import ctypes
import datetime as dt
import hashlib
import io
import zipfile
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import sys
import types
import uuid

RELEASE_SHA='BFC44DA9A375ED565D8DA2DA7E34EC376C25DEAFE15ED2F3C063CE635CEBCD4C'

def sha(b):return hashlib.sha256(b).hexdigest().upper()
def require(v,r):
    if not v:raise RuntimeError(r)
def lib(raw,path):
    ns={'__name__':'tickstore_admission_library_'+Path(path).stem,'__file__':str(path)}
    exec(compile(raw,str(path),'exec'),ns)
    return types.SimpleNamespace(**ns)

def dpapi(data,protect):
    from ctypes import wintypes as w
    class Blob(ctypes.Structure):_fields_=[('size',w.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buf=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    source=Blob(len(data),buf);target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[w.HLOCAL];kernel.LocalFree.restype=w.HLOCAL
    if protect:
        fn=crypt.CryptProtectData
        fn.argtypes=[ctypes.POINTER(Blob),w.LPCWSTR,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(Blob)]
    else:
        fn=crypt.CryptUnprotectData
        fn.argtypes=[ctypes.POINTER(Blob),ctypes.POINTER(w.LPWSTR),ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(Blob)]
    fn.restype=w.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(ctypes.cast(target.data,w.HLOCAL))

def policy_current(reads,root,reconciliation,reconciliation_sha,capture_module):
    """R44-B2C: current policy from physical capture + origin reconciliation; no revision literal."""
    return capture_module.verify_capture(reads.read,root,reconciliation,reconciliation_sha)

def check_native_process_boundary():
    from ctypes import wintypes as w
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenMutexW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR];k.OpenMutexW.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
    ctypes.set_last_error(0)
    h=k.OpenMutexW(0x100000,False,r'Global\TICKSTORE_PUBLISHER_RECOVERY_V004_PROCESS_CENSUS')
    error=ctypes.get_last_error()
    if h:k.CloseHandle(h)
    require(not h and error==2,'RECOVERY_PROCESS_LEASE_PRESENT_OR_UNKNOWN')

def fresh_predecessor(reads,directory,prep,reconcile,state_raw,journal_raw):
    directory=Path(directory)
    obs=prep.strict_json(reads.read(directory/'predecessor_observer/predecessor_evidence/OBSERVATION.json'))
    system=prep.strict_json(reads.read(directory/'predecessor_observer/PREDECESSOR_SYSTEM.json'))
    roots=prep.strict_json(reads.read(directory/'D4_ROOTS_REPORT.json'))
    result=reconcile.reconcile(obs,system,roots)
    require(result['classification']=='PREDECESSOR_TERMINATED_COMPLETION_UNPROVEN','PREDECESSOR_NOT_RECONCILED')
    require(obs['state']['sha256']==sha(state_raw) and obs['journal']['sha256']==sha(journal_raw),'PREDECESSOR_CURRENT_STATE_JOURNAL')
    sampled=dt.datetime.fromisoformat(system['observed_utc'].replace('Z','+00:00'))
    age=(dt.datetime.now(dt.timezone.utc)-sampled).total_seconds()
    require(0<=age<=300,'PREDECESSOR_OBSERVATION_NOT_FRESH_300S')
    check_native_process_boundary()
    return result

def read_code_set(reads,manifest_path,expected_sha,candidate):
    raw=reads.read(manifest_path,expected_sha);manifest=json.loads(raw)
    require(manifest.get('schema')=='TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001','FINAL_CODE_MANIFEST_SCHEMA')
    seen=set()
    for row in manifest['files']:
        name=row['path']
        require(isinstance(name,str) and name and '\\' not in name and ':' not in name
                and not PurePosixPath(name).is_absolute()
                and all(x not in ('','.','..') and not x.endswith((' ','.'))
                        and not re.search(r'[\x00-\x1f<>"|?*]',x)
                        and re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',x) is None
                        for x in name.split('/')), 'FINAL_CODE_MANIFEST_PATH')
        p=Path(candidate).joinpath(*PurePosixPath(name).parts)
        require(name.casefold() not in seen,'FINAL_CODE_MANIFEST_PATH')
        seen.add(name.casefold());data=reads.read(p,row['sha256'])
        require(type(row.get('bytes')) is int and len(data)==row['bytes'],'FINAL_CODE_MANIFEST_SIZE')
    required={'control/D4_FIRST_ADMISSION_BOOTSTRAP.py','control/D4_FIRST_ADMISSION_TRANSACTION.py','control/D4_FIRST_ADMISSION_PREP.py',
      'control/POLICY_CAPTURE_BINDING.py',
      'control/FIRST_ADMISSION_BINDING.json','control/60_EFFECTFUL_WRAPPER_RELEASE.ps1',
      'adapter/runtime_locator_adapter.py','adapter/runtime_locator_orchestrator_entry.py','adapter/runtime_locator_inline_entry.py',
      'adapter/INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1','adapter/Launch-TickstoreBundle-Adapter.ps1',
      'adapter/RUNTIME_LOCATOR_ADAPTER_BINDING.json','recovery/engine/tickstore_publisher_recovery_v004_release.py',
      'recovery/engine/tickstore_publisher_recovery_v004_candidate.py','recovery/modules/orchestrator.py','recovery/config/STAGE_A_SEALED_VALUES_V001.json'}
    required |= {'control/FULL_QUALIFICATION_CONTRACT.py','control/QUALIFICATION_CONTRACT.json',
                 'control/FULL_RUNNER.py','control/FULL_LIFECYCLE.py','control/FULL_STAGE_CONTINUATION.py'}
    require({n.casefold() for n in required}<=seen,'FINAL_CODE_MANIFEST_INCOMPLETE')
    physical={p.relative_to(candidate).as_posix().casefold() for p in Path(candidate).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts}
    require(physical==seen,'FINAL_CODE_CLOSED_FILE_SET')
    return manifest

def validate_review_payload(reads,review_path,manifest_raw):
    """Bind frozen B06 review-pack SHA to these exact operational code bytes."""
    raw=reads.read(review_path)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(z.testzip() is None,'REVIEW_PACK_CRC')
        require(len(z.namelist())==len(set(z.namelist())),'REVIEW_PACK_DUPLICATE_NAMES')
        require(z.read('revision_v38/FINAL_RUNTIME_CODE_MANIFEST.json')==manifest_raw,'REVIEW_FINAL_CODE_MANIFEST')
        for row in json.loads(manifest_raw)['files']:
            require(sha(z.read('implementation_v001/candidate/'+row['path']))==row['sha256'],'REVIEW_CODE_PAYLOAD:'+row['path'])


def run(a):
    require(os.name=='nt','NATIVE_WINDOWS_REQUIRED')
    require(ctypes.WinDLL('shell32').IsUserAnAdmin(),'NATIVE_ELEVATION_REQUIRED')
    home=Path(__file__).parent;candidate=home.parent;package=Path(a.package);adapter_dir=Path(a.adapter_dir)
    # The wrapper executes hashed bootstrap bytes; use the exact frozen release
    # as library only, then retain protected Win32 handles for every input.
    eraw=(package/'engine/tickstore_publisher_recovery_v004_release.py').read_bytes()
    require(sha(eraw)==RELEASE_SHA,'BOOTSTRAP_FROZEN_RELEASE_SHA')
    engine=lib(eraw,package/'engine/tickstore_publisher_recovery_v004_release.py')
    binding_raw=(home/'FIRST_ADMISSION_BINDING.json').read_bytes()
    require(sha(binding_raw)==a.binding_sha,'BOOTSTRAP_BINDING_SHA')
    binding=json.loads(binding_raw)
    modules={}
    for name,key in [('D4_FIRST_ADMISSION_PREP.py','preparation_sha256'),('D4_FIRST_ADMISSION_TRANSACTION.py','transaction_sha256'),
                     ('D4_PREDECESSOR_RECONCILIATION.py','predecessor_reconciliation_sha256'),
                     ('POLICY_CAPTURE_BINDING.py','policy_capture_binding_sha256')]:
        raw=(home/name).read_bytes();require(sha(raw)==binding[key],'BOOTSTRAP_COMPONENT_SHA:'+name);modules[name]=lib(raw,home/name)
    prep=modules['D4_FIRST_ADMISSION_PREP.py'];tx=modules['D4_FIRST_ADMISSION_TRANSACTION.py']
    with prep.Reads(engine.Win32Store()) as reads:
        reads.read(package/'engine/tickstore_publisher_recovery_v004_release.py',RELEASE_SHA)
        frozen={'engine/tickstore_publisher_recovery_v004_candidate.py':'E998032478EA1FAB8BD69FF000D9622749B679058F457A927D5854963208E310',
          'modules/orchestrator.py':'9EB509A2A82C0BE6D4C7AEF315AAF6B41348CECE64AB502061116DFC74419DDA',
          'CODE_MANIFEST.json':'60FE88C92BDBD95884DF3258C739855AF870F4A4D58B40301BF8E5E1786C579D',
          '99_MANIFEST_SHA256.json':'5199C7B03A442F0D33C1250E3E2A68A5A213377E012A902336502453CAAA18D6',
          'TICKSTORE_V004R1_MASTER_ORCHESTRATOR.ps1':'18900BCC198347A5912AA4CEC23F4D9E7A2513FC41EBE393BFD8151F9EEF259A'}
        for name,digest in frozen.items():reads.read(package/name,digest)
        reads.read(a.package_zip,'4BC28843012A059F65237E07780B79D158190A661B16FFD520861A3F092C3062')
        reads.read(home/'FIRST_ADMISSION_BINDING.json',a.binding_sha)
        reads.read(home/'D4_FIRST_ADMISSION_BOOTSTRAP.py',binding['bootstrap_sha256'])
        for name,key in [('D4_FIRST_ADMISSION_PREP.py','preparation_sha256'),('D4_FIRST_ADMISSION_TRANSACTION.py','transaction_sha256'),
                         ('D4_PREDECESSOR_RECONCILIATION.py','predecessor_reconciliation_sha256'),
                         ('POLICY_CAPTURE_BINDING.py','policy_capture_binding_sha256')]:reads.read(home/name,binding[key])
        capmod=modules['POLICY_CAPTURE_BINDING.py']
        capture=policy_current(reads,a.policy_root,a.policy_reconciliation,a.policy_reconciliation_sha256,capmod)
        read_code_set(reads,a.final_code_manifest,a.final_code_sha,candidate)
        validate_review_payload(reads,a.review_pack,reads.read(a.final_code_manifest))
        config_path=package/'config/STAGE_A_SEALED_VALUES_V001.json';cfg=prep.strict_json(reads.read(config_path,prep.CONFIG_SHA))
        reads.read(sys.executable,cfg['python_exe_sha256'])
        state_path=Path(cfg['control_root'])/'state/STATE.json'
        runtime_binding=prep.strict_json(reads.read(adapter_dir/'RUNTIME_LOCATOR_ADAPTER_BINDING.json',binding['runtime_binding_sha256']))
        code={}
        names={'runtime_locator_adapter.py':'adapter_sha256','runtime_locator_orchestrator_entry.py':'orchestrator_entry_sha256',
          'runtime_locator_inline_entry.py':'inline_entry_sha256','INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1':'adapted_loader_sha256',
          'Launch-TickstoreBundle-Adapter.ps1':'adapted_launch_sha256'}
        for n,k in names.items():code[n]=reads.read(adapter_dir/n,runtime_binding[k])
        entry=lib(code['runtime_locator_orchestrator_entry.py'],adapter_dir/'runtime_locator_orchestrator_entry.py')
        release_boundary=entry.acquire_state_boundary(state_path)
        try:
            state_raw=reads.read(state_path);state=prep.strict_json(state_raw)
            journal_raw=reads.read(state_path.with_name('STATE_JOURNAL.jsonl'));prep.validate_journal(journal_raw)
            artifacts={'base_release_sha256':'82FA3A22E6AA7BC306E0544F2FE7EE250B96BBE305A6D1593911E3641CE888C7',
              'artifact_base_master_sha256':'C7697B1798A02DF2CF128B2A28247182C8D36A9924C52A0844BCDDE66B956AE1',
              'final_code_manifest_sha256':a.final_code_sha,'final_code_manifest_path':str(Path(a.final_code_manifest).absolute())}
            bound=[('engine_path','successor_release_sha256',package/'engine/tickstore_publisher_recovery_v004_release.py'),
              ('candidate_path','successor_candidate_sha256',package/'engine/tickstore_publisher_recovery_v004_candidate.py'),
              ('config_path','config_sha256',config_path),('orchestrator_path','orchestrator_sha256',package/'modules/orchestrator.py'),
              ('code_manifest_path','code_manifest_sha256',package/'CODE_MANIFEST.json'),
              ('package_manifest_path','package_manifest_sha256',package/'99_MANIFEST_SHA256.json'),
              ('package_zip_path','package_zip_sha256',Path(a.package_zip)),('review_pack_path','review_pack_sha256',Path(a.review_pack)),
              ('review_verdict_path','review_verdict_sha256',Path(a.review_verdict)),
              ('policy_admission_receipt_path','policy_admission_receipt_sha256',Path(a.policy_receipt)),
              ('effectful_wrapper_path','effectful_wrapper_sha256',home/'60_EFFECTFUL_WRAPPER_RELEASE.ps1'),
              ('b07_receipt_path','b07_receipt_sha256',Path(a.b07)),('completeness_path','completeness_sha256',Path(a.completeness))]
            for pk,hk,p in bound:
                p=p.absolute();raw=reads.read(p);artifacts[pk]=str(p);artifacts[hk]=sha(raw)
            review=engine._d4r_parse_verdict(Path(a.review_verdict))
            b07=prep.strict_json(reads.read(a.b07));complete=prep.strict_json(reads.read(a.completeness));policy=prep.strict_json(reads.read(a.policy_receipt))
            artifacts['policy_capture']=capture
            artifacts['qualification_validator_sha256']=sha(reads.read(home/'FULL_QUALIFICATION_CONTRACT.py'))
            contract_raw=reads.read(home/'QUALIFICATION_CONTRACT.json')
            artifacts['qualification_contract']=prep.strict_json(contract_raw)
            artifacts['qualification_contract_sha256']=sha(contract_raw)
            delta_meta=complete['delta_qualification_evidence']
            delta=prep.strict_json(reads.read(delta_meta['path'],delta_meta['sha256']))
            require(delta==complete.get('delta_qualification'),'DELTA_QUALIFICATION_READBACK')
            baseline_meta=complete['baseline_archive_evidence']
            reads.read(baseline_meta['path'],baseline_meta['sha256'])
            for proof in delta.get('target_proofs',{}).values():
                for evidence in proof.get('evidence',[]): reads.read(evidence['path'],evidence['sha256'])
            tx.validate_gates(review,b07,complete,policy,artifacts)
            adapter=lib(code['runtime_locator_adapter.py'],adapter_dir/'runtime_locator_adapter.py')
            if a.validate_existing:
                ra_path=Path(a.resume_root)/'authority/RUN_AUTHORITY.json';ra_raw=reads.read(ra_path);ra=prep.strict_json(ra_raw)
                for key in artifacts:require(ra.get(key)==artifacts[key],'EXISTING_ADMISSION_DRIFT:'+key)
                key=dpapi(base64.b64decode(ra['protected_key_b64'],validate=True),False)
                require(len(key)==32 and sha(key)==ra['key_sha256'],'EXISTING_KEY_IDENTITY')
                anchor=reads.read(ra['owner_gate_path'],ra['owner_gate_sha256'])
                actual_binding=prep.strict_json(reads.read(ra['adapter_binding_path'],ra['adapter_binding_sha256']))
                receipt=prep.strict_json(reads.read(ra['gca_recovery_receipt_path'],ra['gca_recovery_receipt_sha256']))
                admitted=entry.validate_d4_start(package,sys.executable,ra)
                identity=entry.RunIdentity(ra,ra_raw,anchor)
                entry.reconcile_resume_identity(identity,actual_binding,admitted,receipt,eraw,key.hex())
                entry.validate_first_admission_commit(ra,state_raw,state_path)
                reads.revalidate()
                return {'authority_path':str(ra_path),'authority_sha256':sha(ra_raw),'adapter_dir':str(Path(ra['adapter_binding_path']).parent),
                        'binding_sha256':ra['adapter_binding_sha256'],'run_id':ra['run_id'],'mode':'VALIDATED_EXISTING_NO_WRITES'}
            prep.validate_state(state)
            fresh_predecessor(reads,a.predecessor_evidence,prep,modules['D4_PREDECESSOR_RECONCILIATION.py'],state_raw,journal_raw)
            before=prep.no_first_admission_artifacts(a.resume_root,state['canary']['recovery'],state_path)
            run_id=uuid.uuid4().hex.upper()
            oraw=reads.read(package/'modules/orchestrator.py',prep.ORCH_SHA);orch=lib(oraw,package/'modules/orchestrator.py')
            locator,descriptor=prep.observe_native(reads,engine,orch,adapter,runtime_binding,cfg,state,str(uuid.UUID(run_id)))
            require(before==prep.no_first_admission_artifacts(a.resume_root,state['canary']['recovery'],state_path),'ADMISSION_SCOPE_CHANGED')
            def revalidate():
                reads.revalidate()
                require(policy_current(reads,a.policy_root,a.policy_reconciliation,a.policy_reconciliation_sha256,capmod)==capture,
                        'POLICY_DRIFT_DURING_ADMISSION')
                fresh_predecessor(reads,a.predecessor_evidence,prep,modules['D4_PREDECESSOR_RECONCILIATION.py'],state_raw,journal_raw)
                check_native_process_boundary()
                for p in state['canary'].values():require(not os.path.lexists(Path(p)/'TICKSTORE_WRITER.lock'),'WRITER_LOCK_PRESENT')
            key=os.urandom(32);protected=base64.b64encode(dpapi(key,True)).decode('ascii')
            s=os.lstat(state_path);pin={'sha256':sha(state_raw),'identity':[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]}
            artifacts['policy_root']=str(Path(a.policy_root).absolute())
            for pk,hk,p in [('policy_master_path','policy_master_sha256',Path(a.policy_root)/'POLITICA_CANONICA_UNIFICADA_OPERACIONAL.md'),
                            ('policy_head_path','policy_head_sha256',Path(a.policy_root)/'POLITICA_CANONICA_HEAD.json'),
                            # RA ABI key kept (adapter/closure consumers); it now names the origin reconciliation record.
                            ('origin_witness_path','origin_witness_sha256',Path(a.policy_reconciliation))]:
                artifacts[pk]=str(p.absolute());artifacts[hk]=sha(reads.read(p))
            result=tx.materialize(a.resume_root,run_id,descriptor['legacy_format'],runtime_binding,locator,artifacts,sha(key),protected,pin,
                                  review,b07,complete,policy,revalidate,adapter.validate_locator_receipt,code,
                                  directory_guard=lambda p: reads.store.open(p,directory=True),file_guard=reads.store.open)
            return dict(result,mode='FIRST_ADMISSION_MATERIALIZED_D4_NOT_STARTED')
        finally:release_boundary()

def main(argv=None):
    ap=argparse.ArgumentParser(allow_abbrev=False)
    group=ap.add_mutually_exclusive_group(required=True);group.add_argument('--admit-first',action='store_true');group.add_argument('--validate-existing',action='store_true')
    for n in ('package','package-zip','adapter-dir','resume-root','binding-sha','policy-root','policy-reconciliation',
              'policy-reconciliation-sha256','final-code-manifest','final-code-sha',
              'review-pack','review-verdict','policy-receipt','b07','completeness','predecessor-evidence'):ap.add_argument('--'+n,required=True)
    try:
        result=run(ap.parse_args(argv));print(json.dumps(dict(result,schema='TICKSTORE_FIRST_ADMISSION_BOOTSTRAP_RESULT_V001')));return 0
    except (RuntimeError,OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as e:
        print(json.dumps({'schema':'TICKSTORE_FIRST_ADMISSION_BOOTSTRAP_RESULT_V001','status':'BLOCKED','reason':str(e),'D4_started':False}));return 2
if __name__=='__main__':raise SystemExit(main())
