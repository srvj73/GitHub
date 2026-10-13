"""First-admission transaction. No automatic repair, replacement or successor.

Caller holds the STATE boundary and native read handles until publish returns.
All gates and observations must be validated before calling materialize().
Only the final create-if-absent RUN_AUTHORITY publishes the instance. Incomplete
support directories survive failures and block future first-admission attempts.
This module contains no D4 dispatch and grants no independent audit verdict.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat

class Blocked(RuntimeError): pass

def require(value, reason):
    if not value: raise Blocked(reason)

def sha(raw): return hashlib.sha256(raw).hexdigest().upper()

def canon(obj): return (json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode('ascii')

POLICY_MASTER='5B135DA0CA7C3BFE992F364720605522FB939977772C6D5A6FD3811A8288B302'
POLICY_HEAD='2DA2939C88530B089D3E6D33418439B38A243EE776DAC151559199C2703B5BA9'
POLICY_REVISION='20261012T070600-0300-5B135DA0CA7C3BFE'
REVIEW_CHECKS={
 'VERDICT':'PASS','INDEPENDENT_REVIEW':'YES','TESTED_CODE_EQUALS_PACKAGED_CODE':'YES',
 'CANDIDATE_RELEASE_FUSE_ONLY':'PASS','CERTIFY_SCRATCH_FINAL_SEMANTICS_PRESERVED':'YES',
 'RESUME_ATTESTATION_AUTHORITY':'PASS','RUNTIME_IDENTITY_BINDING':'PASS','CHECKPOINT_ATOMIC_DURABLE':'PASS',
 'CHECKPOINT_RECONCILIATION':'PASS','COMMITTED_REVALIDATION':'PASS','SAFE_STOP_COOPERATIVE':'PASS',
 'EFFECTFUL_WRAPPER_D4_ONLY':'PASS','RESUME_CHUNK_UNIT':'DATE_KEY','AUTO_KILL_DELTA':'NO',
 'RUN_AUTHORITY_SINGLE_ATOMIC_FILE':'PASS','CTRL_C_STOP_DURABLE':'PASS','LONG_RUNNER_OBSERVABILITY':'PASS',
 'POLICY_ADMISSION_BINDING':'PASS','SUPPORT_TOPOLOGY_REPRODUCIBLE':'PASS','NESTED_EXIT_PROPAGATION':'PASS',
 'THREAD_ROUTING_IDENTITY':'PASS','D4_RESUME_AUTHORIZED':'YES','D5_AUTHORIZED':'NO','FULL_AUTHORIZED':'NO',
 'CRITICAL_FINDINGS':'0','MAJOR_FINDINGS':'0'}
QUALIFICATION_SUITES={'targeted':73,'native_store':4,'native_identity':9,'transaction':22,'bootstrap':9,'wrapper':10}
B07_CHECKS=('policyroot_physical_readback','policyroot_mutation_denial','reparse_and_ancestor_controls',
 'state_cas_and_continuity','checkpoint_failure_controls','concurrent_receipt_controls',
 'g_ca_native_locator','predecessor_process_locks_lease','wrapper_safe_stop_exit_propagation',
 'first_admission_transaction')

def validate_gates(review, b07, completeness, policy, expected):
    """Technical receipt consumer; never writes or manufactures PASS evidence.

    Completeness is required before accepting the B06 result, preventing old
    partial-review verdicts from releasing this implementation. Native evidence
    content is the independent reviewer's responsibility; byte bindings are ours.
    """
    require(completeness.get('schema')=='TICKSTORE_ENGINEERING_COMPLETENESS_V002', 'COMPLETENESS_SCHEMA')
    require(completeness.get('status')=='COMPLETE' and completeness.get('known_blockers')==[], 'INCOMPLETE_CANDIDATE')
    require(completeness.get('integration_implemented') is True and completeness.get('windows_qualification')=='PASS', 'WINDOWS_OR_INTEGRATION_INCOMPLETE')
    require(completeness.get('code_manifest_sha256')==expected['final_code_manifest_sha256'], 'COMPLETENESS_CODE_BINDING')
    validator_path=Path(__file__).with_name('FULL_QUALIFICATION_CONTRACT.py')
    validator_raw=validator_path.read_bytes()
    require(sha(validator_raw)==expected['qualification_validator_sha256'], 'QUALIFICATION_VALIDATOR_SHA')
    namespace={'__name__':'tickstore_qualification_library','__file__':str(validator_path)}
    exec(compile(validator_raw,str(validator_path),'exec'),namespace)
    namespace['validate'](completeness, expected['qualification_contract'],
                           completeness.get('delta_qualification', {}),
                           expected['final_code_manifest_sha256'], require)
    require(review.keys()==REVIEW_CHECKS.keys()|{'REVIEW_PACK_SHA256','BASE_RELEASE_SHA256','SUCCESSOR_RELEASE_SHA256','SUCCESSOR_CANDIDATE_SHA256','EFFECTFUL_WRAPPER_SHA256'}, 'REVIEW_FIELDS')
    for name,value in REVIEW_CHECKS.items(): require(review[name]==value,'REVIEW_'+name)
    for field,key in [('REVIEW_PACK_SHA256','review_pack_sha256'),('BASE_RELEASE_SHA256','base_release_sha256'),
                      ('SUCCESSOR_RELEASE_SHA256','successor_release_sha256'),('SUCCESSOR_CANDIDATE_SHA256','successor_candidate_sha256'),
                      ('EFFECTFUL_WRAPPER_SHA256','effectful_wrapper_sha256')]:
        require(review[field]==expected[key], 'REVIEW_BINDING_'+field)
    require(b07.get('schema')=='TICKSTORE_B07_TECHNICAL_RECEIPT_V001' and b07.get('status')=='PASS', 'B07_REQUIRED')
    require(b07.get('platform')=='WINDOWS_NTFS_PS51', 'B07_NATIVE_PLATFORM')
    require(b07.get('code_manifest_sha256')==expected['final_code_manifest_sha256'] and
            b07.get('review_verdict_sha256')==expected['review_verdict_sha256'], 'B07_BYTES_BINDING')
    require(set(b07.get('checks',{}))==set(B07_CHECKS) and all(b07['checks'][n]=='PASS' for n in B07_CHECKS), 'B07_CHECKS_INCOMPLETE')
    require(policy.get('schema')=='TICKSTORE_D4_POLICY_ADMISSION_RECEIPT_V001' and policy.get('status')=='PASS','POLICY_TECHNICAL_RECEIPT')
    for key,value in [('project','PEGASUS_TICKSTORE'),('thread','Compressão De Ticks 7'),('effect_scope','D4_ONLY'),
                      ('active_master_sha256',POLICY_MASTER),('active_head_sha256',POLICY_HEAD),('active_revision_id',POLICY_REVISION),
                      ('policy_source_cardinality','PASS_1_MASTER_PLUS_1_HEAD'),('policy_head_state','FROZEN'),
                      ('material_delta_reconciled','YES'),('material_delta_blocks_execution','NO')]:
        require(policy.get(key)==value,'POLICY_'+key)
    for key in ('artifact_base_master_sha256','review_pack_sha256','review_verdict_sha256','effectful_wrapper_sha256'):
        require(policy.get(key)==expected[key],'POLICY_BINDING_'+key)

def no_reparse(path):
    p=Path(os.path.abspath(path))
    for q in (p,*p.parents):
        s=os.lstat(q)
        require(not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&0x400,'TRANSACTION_LINK_OR_REPARSE')
    return p

def sync_dir(path):
    if os.name=='nt': return # payloads use FlushFileBuffers via fsync; NTFS rename qualification required
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)

def create_file(path,raw):
    path=Path(path); no_reparse(path.parent)
    with path.open('xb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
        st=os.fstat(f.fileno());created=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)
    require(path.read_bytes()==raw,'TRANSACTION_READBACK:'+str(path))
    sync_dir(path.parent)
    return created

def publish_authority(source,target):
    """No replacement on either platform; never remove an existing winner."""
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes as w
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.MoveFileExW.argtypes=[w.LPCWSTR,w.LPCWSTR,w.DWORD];k.MoveFileExW.restype=w.BOOL
        # WRITE_THROUGH only; REPLACE_EXISTING and COPY_ALLOWED intentionally absent.
        if not k.MoveFileExW(str(source),str(target),8):raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.link(source,target,follow_symlinks=False)
        source.unlink()
    sync_dir(target.parent)

def require_clean_first_admission(resume_root):
    rr=no_reparse(resume_root)
    authority=rr/'authority'
    require(not os.path.lexists(authority/'RUN_AUTHORITY.json'),'EXISTING_RUN_USE_IDENTITY_RECONCILIATION')
    require(not list(rr.glob('admission.*')),'INTERRUPTED_ADMISSION_REQUIRES_DIAGNOSIS')
    for p in (authority,rr/'checkpoint'):
        if os.path.lexists(p):
            no_reparse(p);require(p.is_dir() and not list(p.iterdir()),'FIRST_ADMISSION_DIRECTORY_NOT_EMPTY')
    require(not os.path.lexists(rr/'STOP.request'),'FIRST_ADMISSION_STOP_PRESENT')

def build_instance(run_id,resume_root,gate,binding,locator,artifacts,key_sha,protected_key_b64,state_pin):
    """Pure compilation of actual O.gate output and already-qualified observations."""
    require(re.fullmatch('[0-9A-F]{32}',run_id) is not None,'RUN_ID')
    require(re.fullmatch('[0-9A-F]{64}',key_sha) is not None and protected_key_b64,'KEY_PROTECTION')
    require(gate.get('schema')=='RECOVERY_OWNER_GATE_V004' and gate.get('mode')=='CERTIFY_SCRATCH','DESCRIPTOR_ABI')
    require(gate.get('authorized') is True and gate.get('permissions',{}).get('CERTIFY_SCRATCH') is True,'DESCRIPTOR_MODE_CONSTRAINT')
    require(gate.get('production_recovery_authorized') is False and gate.get('canary_execution_authorized') is False,'DESCRIPTOR_SCOPE')
    require(gate.get('recovery_source_sha256')==binding['frozen_release_sha256']==artifacts['successor_release_sha256'],'DESCRIPTOR_SOURCE')
    require(locator.get('schema')=='TICKSTORE_G_CA_OBSERVATION_V002' and locator.get('status')=='OBSERVED_NOT_ADMITTED','LIVE_LOCATOR_REQUIRED')
    require(locator.get('technical_descriptor_sha256')==sha(canon(gate)),'LOCATOR_DESCRIPTOR_BINDING')
    require(locator.get('historical_generation')==gate['admission_generation'],'GENERATION_DESCRIPTOR_BINDING')
    require(type(state_pin.get('identity')) is list and len(state_pin['identity'])==4 and re.fullmatch('[0-9A-F]{64}',state_pin.get('sha256','')),'INITIAL_STATE_PHYSICAL_PIN')
    rr=Path(resume_root);support=rr/('admission.'+run_id)
    gate_raw=canon(gate);gate_sha=sha(gate_raw)
    per_run=dict(binding,owner_gate_sha256=gate_sha,policy_master_sha256=POLICY_MASTER,policy_head_sha256=POLICY_HEAD,policy_revision_id=POLICY_REVISION)
    receipt={'schema':'TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT_V001','status':'PASS','owner_gate_sha256':gate_sha,
      'stable_identity_parity':True,'shadow_root_open':locator['shadow_root_open'],'shadow_scratch_open':locator['shadow_scratch_open'],
      'snapshot_recreation_required':False,'snapshot_state':locator['snapshot_state'],'persistent':bool(locator['attributes']&1),
      'no_auto_release':bool(locator['attributes']&8),'client_accessible':bool(locator['attributes']&4),
      'original_volume_guid':locator['original_volume_guid'],'generation':locator['generation'],
      'state_status':'FAIL','state_next_node':'D4','canary_scratch_cert':'ABSENT',
      'instance_id':run_id,'technical_descriptor_role':'O_GATE_DATA_NOT_ADMINISTRATIVE_OWNER_APPROVAL'}
    # Current adapter performs the remaining detailed generation/ABI validation at both boundaries.
    files={'TECHNICAL_EXECUTION_DESCRIPTOR.json':gate_raw,'G_CA_RUNTIME_LOCATOR.json':canon(receipt),
           'RUNTIME_LOCATOR_ADAPTER_BINDING.json':canon(per_run)}
    auth=dict(artifacts,schema='TICKSTORE_D4_RUN_AUTHORITY_V005',status='ACTIVE',run_id=run_id,
      protected_key_b64=protected_key_b64,key_sha256=key_sha,effect_scope='D4_ONLY',d5_authorized=False,full_authorized=False,
      owner_gate_path=str(support/'TECHNICAL_EXECUTION_DESCRIPTOR.json'),owner_gate_sha256=gate_sha,
      generation=gate['admission_generation'],gca_recovery_receipt_path=str(support/'G_CA_RUNTIME_LOCATOR.json'),
      gca_recovery_receipt_sha256=sha(files['G_CA_RUNTIME_LOCATOR.json']),
      adapter_binding_path=str(support/'RUNTIME_LOCATOR_ADAPTER_BINDING.json'),adapter_binding_sha256=sha(files['RUNTIME_LOCATOR_ADAPTER_BINDING.json']),
      resume_root=str(rr/'checkpoint'),stop_file=str(rr/'STOP.request'),first_admission_state=state_pin)
    return support,files,auth

def materialize(resume_root,run_id,gate,binding,locator,artifacts,key_sha,protected_key_b64,state_pin,
                review,b07,completeness,policy,revalidate,validate_locator,adapter_files,directory_guard=None,file_guard=None):
    """Publish only after gates, current readback, and caller's held lease.

    No cleanup on failure. Even pre-publication failures remain diagnosable and
    cannot be treated as permission to create a new instance automatically.
    """
    require(os.name != 'nt' or (directory_guard is not None and file_guard is not None), 'NATIVE_DIRECTORY_GUARD_REQUIRED')
    if directory_guard is None: directory_guard = lambda p: contextlib.nullcontext()
    with contextlib.ExitStack() as locks:
        retained=[]
        def write_support(path,raw):
            identity=create_file(path,raw)
            if file_guard is not None:
                handle=locks.enter_context(file_guard(path))
                info=handle.info()
                require(info['volume']==identity[0] and int.from_bytes(bytes.fromhex(info['file_id']),'little')==identity[1]
                        and info['bytes']==identity[2], 'SUPPORT_OPEN_IDENTITY_DRIFT')
                require(handle.read()==raw,'SUPPORT_CONTENT_DRIFT')
                retained.append((path,raw,handle,info))
            else:retained.append((path,raw,None,identity))
        def revalidate_support():
            for path,raw,handle,identity in retained:
                if handle is not None:
                    require(handle.info()==identity and handle.read()==raw,'SUPPORT_HANDLE_DRIFT')
                else:
                    st=os.lstat(path)
                    require((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)==identity and path.read_bytes()==raw,'SUPPORT_CONTENT_DRIFT')
        validate_gates(review,b07,completeness,policy,artifacts)
        locks.enter_context(directory_guard(resume_root))
        require_clean_first_admission(resume_root)
        support,files,auth=build_instance(run_id,resume_root,gate,binding,locator,artifacts,key_sha,protected_key_b64,state_pin)
        validate_locator(json.loads(files['G_CA_RUNTIME_LOCATOR.json']),json.loads(files['RUNTIME_LOCATOR_ADAPTER_BINDING.json']))
        expected_names={'runtime_locator_adapter.py':'adapter_sha256','runtime_locator_orchestrator_entry.py':'orchestrator_entry_sha256',
          'runtime_locator_inline_entry.py':'inline_entry_sha256','INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1':'adapted_loader_sha256',
          'Launch-TickstoreBundle-Adapter.ps1':'adapted_launch_sha256'}
        require(set(adapter_files)==set(expected_names),'ADAPTER_COMPONENT_SET')
        for name,raw in adapter_files.items():
            require(sha(raw)==binding[expected_names[name]],'ADAPTER_COMPONENT_SHA:'+name)
            files[name]=raw
        revalidate()
        support.mkdir(exist_ok=False)
        locks.enter_context(directory_guard(support))
        require(not list(support.iterdir()),'NEW_SUPPORT_DIRECTORY_CHANGED')
        write_support(support/'ADMISSION_INTENT.json',canon({'schema':'TICKSTORE_FIRST_ADMISSION_INTENT_V001','run_id':run_id,
              'initial_state':state_pin,'gate_sha256':auth['owner_gate_sha256'],'no_automatic_retry':True}))
        for name,raw in sorted(files.items()): write_support(support/name,raw)
        manifest={'schema':'TICKSTORE_FIRST_ADMISSION_COMMIT_V001','run_id':run_id,'initial_state':state_pin,
                  'files':{name:sha(raw) for name,raw in sorted(files.items())}}
        mraw=canon(manifest);write_support(support/'ADMISSION_COMMIT.json',mraw)
        auth['first_admission_manifest_path']=str(support/'ADMISSION_COMMIT.json');auth['first_admission_manifest_sha256']=sha(mraw)
        # READY describes support bytes; RUN_AUTHORITY create-if-absent is the sole publication.
        auth_raw=canon(auth);staged=support/'RUN_AUTHORITY.staged.json';create_file(staged,auth_raw)
        revalidate()
        authority=Path(resume_root)/'authority'
        if not authority.exists():authority.mkdir(exist_ok=False)
        locks.enter_context(directory_guard(authority))
        no_reparse(authority)
        require(not list(authority.iterdir()),'AUTHORITY_DIRECTORY_CHANGED')
        revalidate_support()
        publish_authority(staged,authority/'RUN_AUTHORITY.json')
        require((authority/'RUN_AUTHORITY.json').read_bytes()==auth_raw,'AUTHORITY_FINAL_READBACK')
        return {'authority_path':str(authority/'RUN_AUTHORITY.json'),'authority_sha256':sha(auth_raw),
                'adapter_dir':str(support),'binding_sha256':auth['adapter_binding_sha256'],'run_id':run_id}
