"""One sealed Windows campaign. No production admission and no policy access.

Each unit runs in a kill-on-close Job and commits an immutable receipt only
after logs, process exit and zero-descendant census agree. A resume verifies
every committed artifact against the same package; it cannot promote a failed
or interrupted unit. Temporary directories are owned by the campaign.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback
import unittest
import uuid
import zipfile

CANDIDATE=Path(__file__).resolve().parents[1]
IMPLEMENTATION=CANDIDATE.parent
EXTRACT=IMPLEMENTATION.parent
for folder in ('full','control','adapter','g5proof'):
    sys.path.insert(0,str(CANDIDATE/folder))
import FULL_CRASH_RECOVERY as R
import FULL_G5_COMPLETE_PROOF_GATE as gate
import G5_FINAL_COMPLETENESS_PRODUCER as producer
from FULL_PROCESS_CONTROL import ProcessJob,StopEvent
from PRE_G06_NATIVE_SCENARIOS import require,no_alias,inside

EXTRA=('test_cdt19_final_completeness_contract.py','test_cdt19_final_transport_closure.py','test_cdt19_integrated_crash_recovery.py','test_cdt19_g6_ownership_closure.py',
       'test_cdt19_native_campaign_contract.py',
       'test_cdt19_durable_barrier_contract.py',
       'test_cdt19_r07_g3_g6_integrated_causality.py','test_cdt19_r06_integrated_contract.py',
       'test_integrated_evidence_contract.py',
       'test_g5_producer_consumer_roundtrip.py','test_cdt18_pre_g06_v003_d4_technical_bridge.py',
       'test_cdt19_r04_preb06_g6.py','test_cdt20_pre_g06_integrated_closure.py')
STAGE_SUITES=('test_stageb_full_physical_closure.py','test_stage_canary_physical_publication.py',
              'test_full_postverify_readback.py','test_canary_receipt_readback.py')


# Observed unit durations (seconds) of the 12:19 native run R08_Q1_20261020121927.
# Only an ETA basis: never evidence, never reused as a result of this package.
UNIT_BASELINE_S={'DELTA_test_cdt18_pre_g06_v003_d4_technical_bridge.py':2,'DELTA_test_cdt19_durable_barrier_contract.py':1,
    'DELTA_test_cdt19_final_completeness_contract.py':13,'DELTA_test_cdt19_final_transport_closure.py':8,
    'DELTA_test_cdt19_g6_ownership_closure.py':1,'DELTA_test_cdt19_integrated_crash_recovery.py':1,
    'DELTA_test_cdt19_native_campaign_contract.py':1,'DELTA_test_cdt19_r04_preb06_g6.py':1,
    'DELTA_test_cdt19_r06_integrated_contract.py':4,'DELTA_test_cdt19_r07_g3_g6_integrated_causality.py':1,
    'DELTA_test_g5_producer_consumer_roundtrip.py':2,'DELTA_test_integrated_evidence_contract.py':1,
    'G3_G6_NATIVE':311,'G5_D4_REAL_ISOLATED_PATH_NATIVE':1,'G5_PS51_INSTALL_MENU':12,
    'G5_STAGE_B_REAL_ISOLATED_PATH_NATIVE':7,'PRE_B06_11_CHAIN':14,'SUITE_adapter_tests.py':1,
    'SUITE_test_b2d_origin_decision_binder.py':8,'SUITE_test_cdt16_delete_share_denial.py':1,
    'SUITE_test_cdt16_held_rename_failure.py':1,'SUITE_test_cdt16_native_pin_contract.py':1,
    'SUITE_test_cdt17_final_g5_complete_proof_gate.py':2,'SUITE_test_cdt18_stage_proof_integrated_reconcile.py':1,
    'SUITE_test_full_multiwork.py':5,'SUITE_test_full_runner_observability_r41.py':1,'SUITE_test_full_serial_r9.py':37,
    'SUITE_test_g5_proof_runner_contract.py':8,'SUITE_test_installer_legacy_activation_prune.py':1,
    'SUITE_test_menu_tx_interprocess.py':3,'SUITE_test_native_process_control_r41.py':2,
    'SUITE_test_official_target_readonly_admission.py':1,'SUITE_test_official_writer_effectful.py':17,
    'SUITE_test_operator_entry_points.py':2,'SUITE_test_publisher_recovery_v004.py':1,
    'SUITE_test_scratch_powerloss_debris.py':237,'SUITE_test_state_cas_recovery.py':1}


def heartbeat_line(key,elapsed,owned,progress,remaining_keys,now_utc):
    """One honest status line: ETA is UNKNOWN once the native baseline is exceeded."""
    base=UNIT_BASELINE_S.get(key)
    if base is None:eta,reason='UNKNOWN','NO_NATIVE_BASELINE'
    elif elapsed>2*base+30:eta,reason='UNKNOWN','UNIT_EXCEEDED_NATIVE_BASELINE'
    else:eta,reason=str(max(0,base-int(elapsed))),'R08_1219_NATIVE_BASELINE'
    rest=[UNIT_BASELINE_S.get(k) for k in remaining_keys]
    unbased=rest.count(None)
    # A unit without an observed native duration is never given an invented one:
    # the campaign ETA is then UNKNOWN and only the observed part is reported.
    known=None if eta=='UNKNOWN' else int(eta)+sum(r for r in rest if r is not None)
    total='UNKNOWN' if known is None or unbased else str(known)
    return ('HEARTBEAT ACTIVE_TEST='+key+' UNIT_ELAPSED_S='+str(int(elapsed))+' OWNED_PIDS='+str(owned)+
            ' PROGRESS_COMMITTED='+progress+' UNIT_ETA_S='+eta+' CAMPAIGN_ETA_S='+total+
            ' CAMPAIGN_ETA_OBSERVED_PART_S='+('UNKNOWN' if known is None else str(known))+
            ' UNITS_WITHOUT_BASELINE='+str(unbased)+
            ' ETA_BASIS='+reason+' ETA_AS_OF='+now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'))


def suite_path(name):
    if name=='adapter_tests.py':return CANDIDATE/'adapter'/name
    if name in ('test_full_multiwork.py','test_full_serial_r9.py'):return CANDIDATE/'full'/name
    if name=='test_publisher_recovery_v004.py':return CANDIDATE/'recovery/tests_release'/name
    return IMPLEMENTATION/'tests'/name


def physical(path,root):
    path=inside(path,root);raw=R.core.secure_read_all(path)
    return {'member':path.relative_to(root).as_posix(),'sha256':R.sha(raw),'bytes':len(raw)}


def read_ref(ref,root):
    require(isinstance(ref,dict) and set(ref)=={'member','sha256','bytes'},'PHYSICAL_REF')
    raw=R.core.secure_read_all(inside(root/ref['member'],root))
    require(len(raw)==ref['bytes'] and R.sha(raw)==ref['sha256'],'PHYSICAL_REF_DRIFT')
    return raw


def verify_package(package):
    code,members=producer.verify_final_zip(package)
    for name,raw in members.items():
        require(R.core.secure_read_all(EXTRACT/name)==raw,'TESTED_BYTES_NE_PACKAGED:'+name)
    frozen=CANDIDATE/'full/tickstore_serial_runner.py'
    require(R.sha(frozen.read_bytes())=='749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00','FROZEN_CORE')
    return code,members


def unit_child(spec):
    root=Path(spec['root']);out=root/'UNITS'/spec['key'];out.mkdir()
    log=root/'LOGS'/(spec['key']+'.log')
    result={'status':'BLOCKED','unit':spec['key'],'native_windows':os.name=='nt'}
    with log.open('x',encoding='utf8',buffering=1) as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try:
            require(os.name=='nt','WINDOWS_REQUIRED')
            result['process']=R.native_process(os.getpid())
            work=root/'WORK'/spec['key'];work.mkdir()
            temp=root/'TEMP'/hashlib.sha256(spec['key'].encode()).hexdigest()[:10]
            temp.mkdir(exist_ok=True)
            for key in ('TEMP','TMP','TMPDIR'):os.environ[key]=str(temp)
            import tempfile
            tempfile.tempdir=str(temp)
            kind=spec['kind']
            if kind=='suite':
                p=suite_path(spec['name']);sys.path.insert(0,str(p.parent))
                suite=unittest.defaultTestLoader.discover(str(p.parent),pattern=p.name,top_level_dir=str(p.parent))
                require(suite.countTestCases()>0,'EMPTY_SUITE')
                ran=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
                result.update(test_count=ran.testsRun,skipped=bool(ran.skipped),
                              failures=len(ran.failures),errors=len(ran.errors),test_source_sha256=R.sha(p.read_bytes()))
                # POSIX-only negative tests deliberately skipped on Windows are
                # permitted solely in extra diagnostics, never required gates.
                require(ran.wasSuccessful() and not ran.expectedFailures and not ran.unexpectedSuccesses,'SUITE_FAILED')
                require(not ran.skipped or spec.get('diagnostic') is True,'REQUIRED_SUITE_SKIPPED')
            elif kind=='consumers':
                import PRE_G06_CONSUMERS as consumers
                evidence=root/'EVIDENCE/CONSUMERS';evidence.mkdir()
                consumers.campaign(CANDIDATE,work,evidence,consumer_evidence_run_id(spec['run_id']))
            elif kind=='g3':
                import PRE_G06_NATIVE_SCENARIOS as native
                native.campaign(CANDIDATE,work)
            elif kind=='proof':
                import G5_PROOF_RUNNERS as proofs
                # Existing proof creates its own directory. The unit TEMP stays
                # separate so admission can require the proof WORK not to exist.
                argv=['--proof',spec['name'],'--run-root',root,'--work',work/'PROOF_WORK',
                      '--evidence',root/'EVIDENCE','--run-id',spec['run_id'],
                      '--final-zip-sha256',spec['package_sha256'],'--code-manifest-sha256',spec['code_sha256'],
                      '--final-extract',EXTRACT,'--witness',spec['witness'],
                      '--d-parent',spec['d_parent'],'--local-appdata',os.environ['LOCALAPPDATA']]
                require(proofs.main(list(map(str,argv)))==0,'NATIVE_PROOF_FAILED')
            else:raise RuntimeError('UNKNOWN_UNIT_KIND')
            result.update(status='PASS',exit_code=0)
        except BaseException as exc:
            result.update(error=type(exc).__name__+':'+str(exc),traceback=traceback.format_exc(),exit_code=2)
            traceback.print_exc()
        finally:
            stream.flush();os.fsync(stream.fileno())
            R.publish(out/'RESULT.json',result)
    raise SystemExit(result['exit_code'])


def run_unit(spec):
    root=Path(spec['root']);key=spec['key'];commit=root/'COMMITS'/(key+'.json')
    if commit.exists():
        obj=R.read(commit)[0]
        require(obj.get('schema')=='CDT19_NATIVE_UNIT_COMMIT_V001'
                and obj.get('result',{}).get('status')=='PASS'
                and obj['result'].get('exit_code')==0 and obj.get('own_descendants_final')==[]
                and isinstance(obj.get('artifacts'),list) and bool(obj['artifacts']), 'COMMITTED_UNIT_NOT_CLOSED')
        require(obj['package_sha256']==spec['package_sha256'] and obj['code_sha256']==spec['code_sha256'],'COMMITTED_INPUT_DRIFT')
        for ref in obj['artifacts']:read_ref(ref,root)
        print('REUSE_COMMITTED '+key,flush=True)
        return obj['result']
    # Interrupted/failed bytes are retained, never overwritten to resemble PASS.
    stale=[root/'UNITS'/key,root/'WORK'/key,root/'LOGS'/(key+'.log')]
    if spec['kind']=='consumers':stale.append(root/'EVIDENCE/CONSUMERS')
    if spec['kind']=='proof':stale.append(root/'EVIDENCE/PROOFS'/spec['name'])
    stale=[p for p in stale if p.exists()]
    if stale:
        archive=root/'INTERRUPTED_ATTEMPTS'/(key+'_'+uuid.uuid4().hex);archive.mkdir(parents=True)
        for n,p in enumerate(stale):
            inside(p,root);shutil.move(str(p),str(archive/(str(n)+'_'+p.name)))
    identity=[]
    def admit(proc):identity.append(R.native_process(proc.pid))
    job=ProcessJob(before_admit=admit);proc=None;last=0;started=time.monotonic();seen={};stopped=False
    try:
        proc=job.start(mp.get_context('spawn'),unit_child,args=(spec,),name='CDT19_'+key)
        while proc.is_alive():
            now=time.monotonic()
            require(now-started<spec.get('timeout',3600),'UNIT_TIMEOUT:'+key)
            if now>=last:
                census=job.memory_snapshot()
                for p in census['processes']:
                    if p['pid']!=os.getpid():seen[(p['pid'],p['creation_filetime'])]=p
                print(heartbeat_line(key,now-started,len(census['processes'])-1,spec.get('progress','?/?'),
                      spec.get('remaining',()),datetime.datetime.now(datetime.timezone.utc)),flush=True)
                last=now+5
            if (root/'SAFE_STOP.request').exists():
                # Request existing owned engine events. Tests without one finish
                # their current bounded unit; the next unit will not begin.
                if not stopped:
                    stopped=True
                    for p in (root/'WORK'/key).rglob('OWNER.json'):
                        obj=R.read(p)[0];run=obj.get('binding',{}).get('run_id')
                        if run:
                            try:event=StopEvent(run,request=True);event.close()
                            except RuntimeError:pass # Event may already be closed.
            time.sleep(.1)
        proc.join()
        require(proc.exitcode==0,'UNIT_PROCESS_EXIT:'+key+':'+str(proc.exitcode))
        census=[p for p in job.memory_snapshot()['processes'] if p['pid']!=os.getpid()]
        require(not census,'UNIT_OWNED_ORPHANS:'+key)
        result=R.read(root/'UNITS'/key/'RESULT.json')[0]
        require(result.get('status')=='PASS' and result.get('exit_code')==0,'UNIT_RESULT_NOT_PASS')
        paths=[root/'UNITS'/key/'RESULT.json',root/'LOGS'/(key+'.log')]
        if spec['kind']=='consumers':paths+=list((root/'EVIDENCE/CONSUMERS').rglob('*'))
        if spec['kind']=='g3':paths+=list((root/'WORK'/key).rglob('*'))
        if spec['kind']=='proof':paths+=list((root/'EVIDENCE/PROOFS'/spec['name']).rglob('*'))
        refs=[physical(p,root) for p in sorted(set(paths)) if p.is_file()]
        R.publish(commit,dict(schema='CDT19_NATIVE_UNIT_COMMIT_V001',package_sha256=spec['package_sha256'],
            code_sha256=spec['code_sha256'],result=result,artifacts=refs,owner=identity,
            own_descendants_final=[],observed_processes=list(seen.values()),
            seconds=round(time.monotonic()-started,3)))
        print('COMMITTED '+key,flush=True)
        return result
    finally:
        job.close()
        if proc is not None:
            proc.join(30);require(not proc.is_alive(),'UNIT_CLEANUP_FAILED')
        for p in seen.values():R.dead(p)


def suite_record(root,key,result):
    p=root/'LOGS'/(key+'.log');raw=p.read_bytes()
    counts=re.findall(rb'(?m)^Ran (\d+) tests? in [^\r\n]+\r?$',raw)
    require(len(counts)==1 and int(counts[0])==result['test_count'] and
            re.search(rb'(?m)^OK\r?$',raw) is not None,'SUITE_LOG_NOT_CLOSED:'+key)
    return dict(status='PASS_NATIVE_SCOPED',exit_code=0,skipped=False,test_count=result['test_count'],
                log=p.name,sha256=R.sha(raw))


def project_consumer_refs(root):
    path=root/'EVIDENCE/CONSUMERS/ELEVEN_CONSUMERS.json';obj=R.read(path)[0]
    # Project native evidence under PRE_B06, the exact namespace consumed
    # by verify_archive_dossier. Child refs are relative to that evidence root;
    # the top-level receipt stays relative to the run root. Preserve originals.
    # Referred JSON documents contain further refs and must be rewritten in a
    # distinct namespace, with parent hashes updated, never edit original proof.
    dest=root/'EVIDENCE/PRE_B06'
    if dest.exists():
        # Never trust a partially published projection on resume. Preserve it;
        # the committed originals are the only input to this deterministic copy.
        archived=root/'INTERRUPTED_ATTEMPTS'/('PROJECTION_'+uuid.uuid4().hex)
        archived.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(dest),str(archived))
    dest.mkdir()
    counter=0
    def convert(ref):
        nonlocal counter
        raw=read_ref(ref,root/'EVIDENCE/CONSUMERS')
        if ref['member'].endswith('.json'):
            value=json.loads(raw)
            def nested(v):
                if isinstance(v,dict):
                    if set(v)=={'member','sha256','bytes'}:
                        return convert(v)
                    return {k:nested(w) for k,w in v.items()}
                if isinstance(v,list):return [nested(w) for w in v]
                return v
            projected=nested(value)
            # Leaf JSON is physical evidence, not metadata to normalize.
            # Its exact formatting can be bound by an enclosing transition.
            if projected != value:raw=R.encoded(projected)
        counter+=1;p=dest/('%04d_'%counter+Path(ref['member']).name)
        with p.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        return physical(p,dest)
    for row in obj['consumers']:
        for key in ('execution_witness','runner_source','negative_controls','internal_branch_execution','code_path_review'):
            row[key]=convert(row[key])
    R.publish(dest/'ELEVEN_CONSUMERS.json',obj)
    return physical(dest/'ELEVEN_CONSUMERS.json',root)


def consumer_evidence_run_id(campaign_run_name):
    """Stable, canonical 32-hex evidence ID for a human-readable run root.

    The evidence schema is unmodified; never pass R08_Q1_* as an ID to a
    verifier whose documented syntax is [0-9a-f]{32}.
    """
    require(isinstance(campaign_run_name, str) and
            re.fullmatch(r'R08_Q1_[0-9]{14}_[0-9a-f]{12}', campaign_run_name) is not None,
            'CONSUMER_RUN_NAME')
    return hashlib.sha256(campaign_run_name.encode('ascii')).hexdigest()[:32]


def preserve_prior_partial(root, temp):
    """On same-package resume retain a failed return, never overwrite it."""
    if not temp.exists():
        return None
    require(temp.is_file() and not temp.is_symlink(), 'RETURN_PARTIAL_TYPE')
    R.core.assert_no_link_chain(temp)
    require(R.read(root / 'OWNER.json')[0]['run_id'] == root.name,
            'RETURN_PARTIAL_FOREIGN_OWNER')
    preserved = root / 'INTERRUPTED_ATTEMPTS' / ('RETURN_'+uuid.uuid4().hex)
    preserved.mkdir(parents=True, exist_ok=False)
    path = preserved / temp.name
    os.replace(temp, path)
    R.publish(preserved/'PRESERVATION.json',
              {'schema':'CDT19_RETURN_PARTIAL_PRESERVATION_V001',
               'previous_partial':temp.name,'new_member':path.relative_to(root).as_posix(),
               'status':'PRESERVED_NO_DELETE','run_id':root.name})
    return path


def seal_return(root,name,excluded=()):
    target=root/name;temp=root/(name+'.partial')
    preserve_prior_partial(root,temp)
    # The launch supervisor holds an exclusive Windows byte-range lock until
    # after this child exits. Reading it inside the return ZIP is forbidden;
    # its omission is explicit, exact-path and evidenced. All other unreadable
    # members still fail closed with the original primary error preserved.
    lock=root/'CAMPAIGN.lock'
    require(lock.is_file() and not lock.is_symlink(), 'CAMPAIGN_LOCK_REQUIRED')
    R.core.assert_no_link_chain(lock)
    lock_scope={
        'schema':'CDT19_RETURN_SEAL_LOCK_EXCLUSION_V001',
        'excluded_member':'CAMPAIGN.lock','scope':'RUN_OWNED_SUPERVISOR_ACTIVE_LOCK',
        'run_id':root.name,'production_modified':False,
        'reason':'WIN_BYTE_RANGE_LOCK_IN_USE_WHILE_SEALING',
        'preserved_in_run_root':True}
    scope_path=root/'RETURN_LOCK_SCOPE.json'
    if scope_path.exists():
        require(R.read(scope_path)[0]==lock_scope,'RETURN_LOCK_SCOPE_DRIFT')
    else:R.publish(scope_path,lock_scope)
    files=[]
    for path in sorted(root.rglob('*')):
        if path.is_file() and path!=target and path!=temp and path.relative_to(root).as_posix() not in excluded:
            rel=path.relative_to(root)
            if rel.parts[0] in ('TEMP','PACKAGED','INPUTS'):continue
            if rel.as_posix()=='CAMPAIGN.lock':
                continue  # One exact active supervisor lock, never wildcard.
            R.core.assert_no_link_chain(path)
            files.append(path)
    with zipfile.ZipFile(temp,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            member = path.relative_to(root).as_posix()
            try:
                archive.write(path, member)
            except OSError as exc:
                detail = ('RETURN_MEMBER_ACCESS:' + member + ':ERRNO=' + str(getattr(exc, 'errno', None))
                          + ':WINERROR=' + str(getattr(exc, 'winerror', None)))
                print(detail, flush=True)
                raise RuntimeError(detail) from exc
    with zipfile.ZipFile(temp) as archive:require(archive.testzip() is None,'RETURN_CRC')
    # Run-owned return file may be replaced on a verified same-package resume.
    os.replace(temp,target)
    return target


def write_terminal(root,result):
    """Enumerate each accounting surface; projected roles are never disk commits."""
    receipts=sorted(p.stem for p in (root/'COMMITS').glob('*.json'))
    contracted=sorted(result['tests'])
    diagnostic=sorted(result['additional_tests'])
    live=dict(status=result['status'],committed_units=len(contracted),
              committed_units_scope='CONTRACTED_EVIDENCE_ROLES_NOT_COMMIT_FILES',
              contracted_evidence_roles=contracted,diagnostic_roles=diagnostic,
              commit_receipts_on_disk_unverified=len(receipts),commit_receipt_keys=receipts,
              roles_without_own_commit=sorted(set(contracted)-set(receipts)),
              commits_outside_contracted_roles=sorted(set(receipts)-set(contracted)),
              updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    for name,obj in [('ENGINEERING_RESULT.json',result),('LIVE_STATUS.json',live)]:
        temp=root/(name+'.new')
        with temp.open('wb') as f:f.write(R.encoded(obj));f.flush();os.fsync(f.fileno())
        os.replace(temp,root/name)


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    for name in ('run-root','package','witness','d-parent'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv);root=no_alias(a.run_root)
    result={'schema':'CDT19_PRE_B06_NATIVE_ENGINEERING_V002','status':'BLOCKED','tests':{},'additional_tests':{},
        'production_modified':False,'full_started':False,'b06':'NOT_STARTED','g5_final':'NOT_ISSUED',
        'native_proofs_are_sandbox_experiments':False,'synthetic_d4_stage_b_substitute':False,
        'qualification_scope':'REAL_PACKAGED_CODE_OWNED_ISOLATED_NTFS_PRE_B06',
        'physical_powerloss':'NOT_TESTED_PHYSICAL_POWERLOSS','blockers':[]}
    code=2
    try:
        require(os.name=='nt','WINDOWS_REQUIRED')
        require(root.is_relative_to(no_alias(os.environ['LOCALAPPDATA'])),'LOCALAPPDATA_OWNED_RUN')
        require(root.name.startswith('R08_'),'RUN_NAME')
        require(Path(os.environ['TEMP'])==root/'TEMP' and '%' not in str(root),'CANONICAL_TEMP_REQUIRED')
        require(R.core.windows_volume_identity(root)['filesystem']=='NTFS','NTFS_REQUIRED')
        code_sha,members=verify_package(Path(a.package));pack_sha=R.sha(Path(a.package).read_bytes())
        witness=R.read(a.witness)[0]
        require(witness['package_sha256']==pack_sha and witness['manifest_sha256']==R.sha(members['PACKAGE_MANIFEST.json']),
                'WITNESS_BINDING')
        droot=no_alias(a.d_parent)
        require(droot.drive.upper()!=root.drive.upper() and droot.name==root.name
                and droot.parent.name=='TICKSTORE_CDT19_PRE_G06_LABS','CROSS_VOLUME_OWNED_LAB')
        require(R.core.windows_volume_identity(droot)['filesystem']=='NTFS','D_LAB_NTFS')
        owner=R.read(root/'OWNER.json')[0]
        require(owner['package_sha256']==pack_sha and owner['run_id']==root.name,'RUN_OWNER')
        require(R.read(droot/'OWNER.json')[0]==owner,'D_LAB_OWNER')
        for name in ('LOGS','UNITS','COMMITS','EVIDENCE','WORK'):(root/name).mkdir(exist_ok=True)
        probe=root/'TEMP/G0_HANDLE_IDENTITY.json'
        if not probe.exists():R.publish(probe,{'identity':'canonical native handle readback'})
        R.read(probe)
        R.core.require_windows_pilot_runtime()
        result.update(code_manifest_sha256=code_sha,final_zip_sha256=pack_sha,run_id=root.name)
        base=dict(root=str(root),run_id=root.name,package_sha256=pack_sha,code_sha256=code_sha,
                  witness=a.witness,d_parent=a.d_parent)
        plan=(['G5_'+n for n in ('PS51_INSTALL_MENU','STAGE_B_REAL_ISOLATED_PATH_NATIVE','D4_REAL_ISOLATED_PATH_NATIVE')]+
              ['SUITE_'+n for n in gate.SUITES if n not in STAGE_SUITES]+['DELTA_'+n for n in EXTRA]+
              ['PRE_B06_11_CHAIN','G3_G6_NATIVE'])
        def unit(kind,key,**kw):
            require(not (root/'SAFE_STOP.request').exists(),'SAFE_STOP_REQUESTED')
            verify_package(Path(a.package))
            done=len([k for k in plan if (root/'COMMITS'/(k+'.json')).exists()])
            return run_unit(dict(base,kind=kind,key=key,progress=str(done)+'/'+str(len(plan)),
                                 remaining=tuple(plan[plan.index(key)+1:]),**kw))
        # Stage-B proof already runs four required suites; use their exact logs
        # below rather than run their unchanged tests a second time.
        for name in ('PS51_INSTALL_MENU','STAGE_B_REAL_ISOLATED_PATH_NATIVE','D4_REAL_ISOLATED_PATH_NATIVE'):
            unit('proof','G5_'+name,name=name)
            result['tests']['G5_'+name]={'status':'PASS_NATIVE_SCOPED','exit_code':0}
        stage=root/'EVIDENCE/PROOFS/STAGE_B_REAL_ISOLATED_PATH_NATIVE/SEALED_NATIVE_LOGS'
        observation=R.read(root/'EVIDENCE/PROOFS/STAGE_B_REAL_ISOLATED_PATH_NATIVE/REAL_BOUNDED_OBSERVATION.json')[0]
        for name in gate.SUITES:
            key='SUITE_'+name
            if name in STAGE_SUITES:
                raw=(stage/(name+'.tests.log')).read_bytes();dest=root/'LOGS'/(key+'.log')
                if dest.exists():require(dest.read_bytes()==raw,'REUSED_LOG_DRIFT')
                else:
                    with dest.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
                test={'test_count':observation['suites'][name]['run']}
            else:test=unit('suite',key,name=name)
            result['tests'][key]=suite_record(root,key,test)
        for name in EXTRA:
            key='DELTA_'+name;test=unit('suite',key,name=name,diagnostic=True)
            result['additional_tests'][key]=test
        unit('consumers','PRE_B06_11_CHAIN')
        ref=project_consumer_refs(root)
        import PRE_B06_ENGINEERING_GATE as consumer_gate
        consumer_gate.verify_dossier(R.read(root/ref['member'])[0],CANDIDATE,
                                    root/'EVIDENCE/PRE_B06',native_required=True)
        result.update(pre_b06_11_receipt=ref,pre_b06_11_evidence_class='ENGINEERING_READINESS_NOT_PRODUCTION')
        result['tests']['PRE_B06_11_CHAIN']={'status':'PASS_PRE_B06_ENGINEERING','exit_code':0,'receipt':ref}
        unit('g3','G3_G6_NATIVE',timeout=10800)
        import PRE_G06_PROOF_PROJECTION as projection
        projection.produce(root,code_sha,pack_sha)
        for name in ('PROCESS_TREE_CRASH_CONTAINMENT','SAFE_STOP_RESUME_ROW_GROUP','POWERLOSS_EMULATED'):
            result['tests']['G5_'+name]={'status':'PASS_NATIVE_SCOPED','exit_code':0}
        verify_package(Path(a.package))
        result['status']='PASS_NATIVE_INTEGRATED_PRE_B06';code=0
    except BaseException as exc:
        stopped=isinstance(exc,KeyboardInterrupt) or 'SAFE_STOP_REQUESTED' in str(exc)
        # The bootstrap has already created an owned run root, extracted code
        # and admitted native evidence effects; non-PASS cannot claim the
        # no-effects status. SAFE_STOP is a distinct terminal condition.
        code=130 if stopped else 3
        result.update(status='SAFE_STOP' if stopped else 'BLOCKED',
                      blockers=[type(exc).__name__+':'+str(exc)],
                      partial_effect_scope='RUN_OWNED_LAB_ONLY',
                      traceback=traceback.format_exc())
        print(result['blockers'][0],flush=True)
        print('PRIMARY_TRACEBACK_BEGIN\n'+result['traceback']+'PRIMARY_TRACEBACK_END',flush=True)
    finally:
        write_terminal(root,result)
        archive=None
        try:
            archive=seal_return(root,'R08_RETURN.zip',excluded=('R08_RETURN.zip','R08_RETURN.sha256'))
            if code==0:
                with zipfile.ZipFile(archive) as sealed:
                    infos=sealed.infolist()
                    print('RETURN_MEMBERS='+str(len(infos))+' RETURN_UNCOMPRESSED_BYTES='+
                          str(sum(i.file_size for i in infos))+' BOUND='+str(gate.NATIVE_ZIP_MAX_UNCOMPRESSED),flush=True)
                code_sha,members=verify_package(Path(a.package))
                index={r['path']:r for r in json.loads(members['implementation_v001/RUNTIME_CODE_MANIFEST.json'])['files']}
                try:
                    gate.verify_native_campaign(archive.read_bytes(),code_sha,result['final_zip_sha256'],index,final_members=members)
                except BaseException as exc:
                    code=3
                    result.update(status='BLOCKED',blockers=['FINAL_READBACK:'+str(exc)],traceback=traceback.format_exc())
                    print('FINAL_READBACK_BLOCKED='+str(exc)+'\nPRIMARY_TRACEBACK_BEGIN\n'+result['traceback']+'PRIMARY_TRACEBACK_END',flush=True)
                    write_terminal(root,result)
                    archive=None
                    archive=seal_return(root,'R08_RETURN.zip',excluded=('R08_RETURN.zip','R08_RETURN.sha256'))
        except BaseException as seal_exc:
            print('PRIMARY_ENGINEERING_STATUS='+result['status'],flush=True)
            print('PRIMARY_ENGINEERING_BLOCKERS='+repr(result.get('blockers')),flush=True)
            print('RETURN_SEAL_SECONDARY_ERROR='+type(seal_exc).__name__+':'+str(seal_exc),flush=True)
            print('RETURN_PARTIAL_PRESERVED='+str(root/'R08_RETURN.zip.partial'),flush=True)
            print('RUN_ROOT_PRESERVED='+str(root),flush=True)
            archive=None;code=3
        if archive is not None:
            (root/'R08_RETURN.sha256').write_text(R.sha(archive.read_bytes())+'  R08_RETURN.zip\n',encoding='ascii')
            print('RESULT='+result['status']+'\nRETURN='+str(archive)+'\nRETURN_SHA256='+R.sha(archive.read_bytes()),flush=True)

    return code


if __name__=='__main__':
    mp.freeze_support()
    raise SystemExit(main())
