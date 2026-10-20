"""CDT20 owned Windows engineering bootstrap. Offline; no policy or production authority."""
from __future__ import annotations
import argparse,ctypes,datetime,hashlib,json,multiprocessing as mp,os,re,shutil,struct,sys,time,traceback,uuid,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROUTE='ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressao De Ticks 20'
def require(ok,why):
    if not ok:raise RuntimeError('CDT20_BOOTSTRAP_'+why)
def sha(raw):return hashlib.sha256(raw).hexdigest().upper()
def encoded(obj):return (json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(',',':'))+'\n').encode('ascii')
def read(path):return json.loads(Path(path).read_bytes())
def publish(path,obj):
    raw=encoded(obj)
    with Path(path).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(Path(path).read_bytes()==raw,'PUBLISH_READBACK')
def long_path(value):
    require(os.name=='nt','WINDOWS_REQUIRED')
    value=os.path.abspath(os.path.expandvars(value))
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.GetLongPathNameW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
    k.GetLongPathNameW.restype=ctypes.c_uint32
    buf=ctypes.create_unicode_buffer(32768)
    n=k.GetLongPathNameW(value,buf,len(buf))
    require(0<n<len(buf),'LONG_PATH:'+value)
    return Path(buf.value)
def no_alias(path):
    path=Path(os.path.abspath(path))
    for p in (*reversed(path.parents),path):
        st=p.lstat()
        require(not p.is_symlink() and not (getattr(st,'st_file_attributes',0)&0x400),'REPARSE:'+str(p))
    return path
def safe_names(infos):
    names=[i.filename for i in infos]
    require(len(names)==len(set(n.casefold() for n in names)),'ZIP_DUPLICATE')
    for i in infos:
        n=i.filename;p=Path(n)
        require(n and not n.startswith('/') and '\\' not in n and ':' not in n
                and all(x not in ('','.','..') for x in n.split('/')) and not i.is_dir()
                and ((i.external_attr>>16)&0xF000)!=0xA000,'ZIP_PATH')
    return names
def verify_package(package,witness):
    require(sha(package.read_bytes())==witness['package_sha256'],'PACKAGE_HASH')
    with zipfile.ZipFile(package) as z:
        names=safe_names(z.infolist());require(z.testzip() is None,'PACKAGE_CRC')
        pm=z.read('PACKAGE_MANIFEST.json');cm=z.read('implementation_v001/RUNTIME_CODE_MANIFEST.json')
        require(sha(pm)==witness['manifest_sha256'] and sha(cm)==witness['code_manifest_sha256'],'MANIFEST_BINDING')
        rows=read_json(pm)['files'];require({r['path'] for r in rows}==set(names)-{'PACKAGE_MANIFEST.json'} and len(rows)==len(names)-1,'MEMBER_SET')
        for r in rows:
            raw=z.read(r['path']);require(sha(raw)==r['sha256'] and len(raw)==r['bytes'],'MEMBER_HASH:'+r['path'])
        code=read_json(cm)
        runtime={n.removeprefix('implementation_v001/candidate/') for n in names if n.startswith('implementation_v001/candidate/')}
        require({r['path'] for r in code['files']}==runtime,'RUNTIME_SET')
        for r in code['files']:
            raw=z.read('implementation_v001/candidate/'+r['path'])
            require(sha(raw)==r['sha256'] and len(raw)==r['bytes'],'RUNTIME_HASH')
        require(sha(z.read('implementation_v001/candidate/full/tickstore_serial_runner.py'))==
                '749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00','CORE_FROZEN')
    return code
read_json=json.loads

def load_candidate(candidate):
    for folder in ('full','control','adapter','g5proof'):sys.path.insert(0,str(candidate/folder))

def configure_environment(root,droot):
    local=long_path(os.environ['LOCALAPPDATA']);profile=long_path(os.environ['USERPROFILE'])
    no_alias(local);no_alias(profile)
    os.environ['LOCALAPPDATA']=str(local);os.environ['USERPROFILE']=str(profile)
    for name in ('TEMP','TMP','TMPDIR'):os.environ[name]=str(root/'TEMP')
    import tempfile
    tempfile.tempdir=str(root/'TEMP')
    for parent in (root/'QUAL_C',droot/'WRITER_EFFECTFUL'):parent.mkdir(exist_ok=True);no_alias(parent)
    os.environ['TICKSTORE_QUAL_C_PARENT']=str(root/'QUAL_C')
    os.environ['TICKSTORE_QUAL_D_PARENT']=str(droot/'WRITER_EFFECTFUL')
    return {'localappdata':str(local),'userprofile':str(profile),'temp':str(root/'TEMP'),
            'qual_c_parent':os.environ['TICKSTORE_QUAL_C_PARENT'],'qual_d_parent':os.environ['TICKSTORE_QUAL_D_PARENT']}

def campaign_child(candidate,args):
    load_candidate(Path(candidate))
    import PRE_G06_CAMPAIGN as campaign
    raise SystemExit(campaign.main(args))

def verify_resume_owner(root,droot,package_sha):
    expected={'schema':'CDT19_ENGINEERING_RUN_OWNER_V001','package_sha256':package_sha,'run_id':root.name,'production_authorized':False}
    require(read(root/'OWNER.json')==expected and read(droot/'OWNER.json')==expected,'RESUME_OWNER')
    return expected

def reconcile_processes(root,R):
    # Read-only: same PID plus creation time is required. No process is killed.
    identities={}
    paths=list(root.glob('BOOTSTRAP_OWNER_*.json'))+list(root.glob('CAMPAIGN_PROCESS_*.json'))
    paths+=list((root/'UNITS').glob('*/RESULT.json')) if (root/'UNITS').exists() else []
    for p in paths:
        obj=R.read(p)[0]
        for key in ('process','identity'):
            i=obj.get(key)
            if isinstance(i,dict) and i.get('pid') and i.get('creation_filetime'):identities[(i['pid'],i['creation_filetime'])]=i
    for p in (root/'WORK').rglob('CHILD_*.json'):
        obj=R.read(p)[0];i=obj.get('identity')
        if isinstance(i,dict) and i.get('pid') and i.get('creation_filetime'):identities[(i['pid'],i['creation_filetime'])]=i
    observations=[R.dead(i) for i in identities.values()]
    publish(root/('PROCESS_READBACK_'+uuid.uuid4().hex+'.json'),{'schema':'CDT20_PRIOR_OWNED_PROCESS_READBACK_V001','observations':observations,'killed_processes':[]})

def run(a):
    require(os.name=='nt','WINDOWS_REQUIRED')
    require(sys.version_info>=(3,14) and struct.calcsize('P')==8,'PYTHON_314_X64_REQUIRED')
    no_alias(HERE)
    witness=read(HERE/'CDT20_R08Q1_WITNESS.json')
    require(witness['schema']=='CDT19_R08Q1_ENGINEERING_WITNESS_V001' and witness['production_authorized'] is False,'WITNESS_SCOPE')
    package=HERE/witness['package_name'];verify_package(package,witness)
    review=HERE/'CDT20_SOURCE_REVIEW.json'
    require(read(review)['package_sha256']==witness['package_sha256'],'REVIEW_BINDING')
    local=long_path(os.environ['LOCALAPPDATA']);no_alias(local)
    parent=local/'CDT20_R08';parent.mkdir(exist_ok=True);no_alias(parent)
    dparent=Path('D:/TICKSTORE_CDT19_PRE_G06_LABS');dparent.mkdir(exist_ok=True);no_alias(dparent)
    if a.resume_root:
        root=no_alias(long_path(a.resume_root))
        require(root.parent==parent and re.fullmatch(r'R08_Q1_[0-9]{14}_[0-9a-f]{12}',root.name),'RESUME_SCOPE')
        droot=no_alias(dparent/root.name);verify_resume_owner(root,droot,witness['package_sha256'])
    else:
        run_id='R08_Q1_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')+'_'+uuid.uuid4().hex[:12]
        root=parent/run_id;droot=dparent/run_id
        root.mkdir();droot.mkdir()
        owner={'schema':'CDT19_ENGINEERING_RUN_OWNER_V001','package_sha256':witness['package_sha256'],'run_id':run_id,'production_authorized':False}
        for p in (root,droot):publish(p/'OWNER.json',owner)
    no_alias(root);no_alias(droot)
    for name in ('INPUTS','PACKAGED','TEMP','LOGS','UNITS','WORK','COMMITS','EVIDENCE'):(root/name).mkdir(exist_ok=True)
    env=configure_environment(root,droot)
    for src in (package,HERE/'CDT20_R08Q1_WITNESS.json',review):
        dest=root/'INPUTS'/src.name
        if dest.exists():require(dest.read_bytes()==src.read_bytes(),'INPUT_DRIFT')
        else:
            with dest.open('xb') as f:f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
    extract=root/'PACKAGED/CURRENT_G5_DELTA_R08Q1/EXTRACTED'
    extract.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(package) as z:
        for n in safe_names(z.infolist()):
            dest=extract/n;dest.parent.mkdir(parents=True,exist_ok=True);no_alias(dest.parent)
            raw=z.read(n)
            if dest.exists():no_alias(dest);require(dest.read_bytes()==raw,'EXTRACT_DRIFT:'+n)
            else:
                with dest.open('xb') as f:f.write(raw)
    candidate=extract/'implementation_v001/candidate';load_candidate(candidate)
    import FULL_CRASH_RECOVERY as R
    import PRE_G06_CAMPAIGN as campaign
    import PRE_G06_COMPLETENESS as completeness
    import FULL_G5_COMPLETE_PROOF_GATE as gate
    from FULL_PROCESS_CONTROL import ProcessJob
    for p in (root,droot):require(R.core.windows_volume_identity(p)['filesystem']=='NTFS','NTFS_REQUIRED')
    require(root.drive.upper()!=droot.drive.upper(),'CROSS_VOLUME_REQUIRED')
    R.core.require_windows_pilot_runtime()
    import msvcrt
    lock=root/'CAMPAIGN.lock'
    if not lock.exists():
        with lock.open('xb') as f:f.write(b'0');f.flush();os.fsync(f.fileno())
    no_alias(lock);held=lock.open('r+b');locked=False;job=None;proc=None;code=3
    try:
        held.seek(0);msvcrt.locking(held.fileno(),msvcrt.LK_NBLCK,1);locked=True
        reconcile_processes(root,R)
        publish(root/('BOOTSTRAP_OWNER_'+uuid.uuid4().hex+'.json'),{'process':R.native_process(os.getpid()),'package_sha256':witness['package_sha256']})
        publish(root/('BOOTSTRAP_G0_'+uuid.uuid4().hex+'.json'),dict(env,schema='CDT20_SAFE_STOP_BOOTSTRAP_G0_V001',
            native_windows=True,package_sha256=witness['package_sha256'],code_manifest_sha256=witness['code_manifest_sha256'],
            bootstrap_sha256=sha(Path(__file__).read_bytes()),python=sys.version,python_executable=sys.executable,
            historical_commits_rebound=False))
        print('RUN_ROOT='+str(root)+'\nSAFE_STOP='+str(root/'SAFE_STOP.request'),flush=True)
        print('ESCOPO=ENGENHARIA_ISOLADA_PRE_G06; B06=NOT_STARTED; PRODUCAO=NAO',flush=True)
        native=root/'R08_RETURN.zip';already=False
        if native.exists():
            try:
                cm,members=campaign.verify_package(root/'INPUTS'/package.name)
                index={r['path']:r for r in json.loads(members['implementation_v001/RUNTIME_CODE_MANIFEST.json'])['files']}
                gate.verify_native_campaign(native.read_bytes(),cm,witness['package_sha256'],index,final_members=members)
                already=True
            except gate.G5Incomplete:pass
        if already:print('REUSE_EXACT_NATIVE_PASS=YES',flush=True);code=0
        else:
            require(not (root/'SAFE_STOP.request').exists(),'SAFE_STOP_REQUESTED')
            def admit(p):publish(root/('CAMPAIGN_PROCESS_'+uuid.uuid4().hex+'.json'),{'process':R.native_process(p.pid)})
            job=ProcessJob(before_admit=admit)
            args=['--run-root',str(root),'--package',str(root/'INPUTS'/package.name),
                  '--witness',str(root/'INPUTS/CDT20_R08Q1_WITNESS.json'),'--d-parent',str(droot)]
            proc=job.start(mp.get_context('spawn'),campaign_child,args=(str(candidate),args),name='CDT20_PRE_G06_CAMPAIGN')
            started=time.monotonic()
            while proc.is_alive():
                committed=len(list((root/'COMMITS').glob('*.json')))
                print('SUPERVISOR_HEARTBEAT OWNED_PROCESSES='+str(len(job.memory_snapshot()['processes'])-1)+
                      ' COMMITTED_UNIT_RECEIPTS='+str(committed)+' ELAPSED_S='+str(int(time.monotonic()-started))+
                      ' AS_OF='+datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),flush=True)
                require(time.monotonic()-started<21600,'SUPERVISOR_WATCHDOG')
                proc.join(10)
            proc.join();code=proc.exitcode
            require(not [p for p in job.memory_snapshot()['processes'] if p['pid']!=os.getpid()],'OWNED_DESCENDANTS_REMAIN')
            job.close();job=None
        if code==0:
            status=completeness.close(root/'INPUTS'/package.name,native,root/'INPUTS'/review.name,root)
            require(status.get('engineering_five_part_completeness')=='PASS','FIVE_PART_NOT_PASS')
            publish(root/('COMPLETION_'+uuid.uuid4().hex+'.json'),status)
            print('ENGINEERING_FIVE_PART_COMPLETENESS=PASS; FOUR_PRE_B06_FINDINGS='+str(status.get('four_pre_b06_findings'))+
                  '; ORIGIN_G5=NOT_ISSUED; B06=NOT_STARTED',flush=True)
        else:
            print('ENGINEERING_STATUS=BLOCKED; CHILD_EXIT_CODE='+str(code),flush=True)
            if (root/'ENGINEERING_RESULT.json').exists():
                er=read(root/'ENGINEERING_RESULT.json')
                print('ENGINEERING_RESULT_STATUS='+str(er.get('status'))+'\nENGINEERING_BLOCKERS='+json.dumps(er.get('blockers')),flush=True)
    except BaseException as exc:
        code=130 if isinstance(exc,KeyboardInterrupt) else 3
        traceback.print_exc()
        publish(root/('BOOTSTRAP_FAILURE_'+uuid.uuid4().hex+'.json'),{'error':type(exc).__name__+':'+str(exc),'traceback':traceback.format_exc(),'exit_code':code})
    finally:
        if job is not None:job.close()
        if proc is not None:proc.join(30);require(not proc.is_alive(),'CHILD_CLEANUP')
        if locked:
            try:
                final=campaign.seal_return(root,'CDT20_PRE_G06_RETURN.zip',excluded=('CDT20_PRE_G06_RETURN.zip','CDT20_PRE_G06_RETURN.sha256','R08_RETURN.zip','R08_RETURN.sha256'))
                digest=sha(final.read_bytes());(root/'CDT20_PRE_G06_RETURN.sha256').write_text(digest+'  CDT20_PRE_G06_RETURN.zip\n',encoding='ascii')
                print('RETURN='+str(final)+'\nRETURN_SHA256='+digest+'\nENVIE_O_RETORNO='+str(final),flush=True)
            except BaseException:
                code=3;traceback.print_exc();print('RUN_ROOT_PRESERVED='+str(root),flush=True)
            held.seek(0);msvcrt.locking(held.fileno(),msvcrt.LK_UNLCK,1)
        held.close()
    print('EXIT_CODE='+str(code)+'\nRESULT_RETURN_TO='+ROUTE,flush=True)
    return code

def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--resume-root');a=p.parse_args()
    try:return run(a)
    except BaseException as e:
        print('G0_BLOCKED='+type(e).__name__+':'+str(e),flush=True);traceback.print_exc();return 2
if __name__=='__main__':
    mp.freeze_support();raise SystemExit(main())
