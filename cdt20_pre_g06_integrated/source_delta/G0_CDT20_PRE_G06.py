"""CDT20 PRE-G06 native G0: qualify the exact packaged successor before any campaign effect.

No production effects and no policy lookup; hash-verified staging only.

The 20/10 G0 ran `python -E -B <test>` in the operator's ambient context
(default %TEMP%, inherited cwd, user site enabled), whereas the native campaign
that had already passed the same suite runs it with -I, an owned canonical TEMP
and long-path LOCALAPPDATA/USERPROFILE. This G0 qualifies every DELTA suite in
that campaign context through G0_SUITE_RUNNER.py, records each failure's own
traceback, and re-runs the transport suite once in the old ambient context as
a NON-GATING diagnostic so the earlier divergence is evidenced, not assumed.
"""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import zipfile

HERE=Path(__file__).resolve().parent
REAL_SCENARIO_SHA='1715749A48B46F875971B4A623E1E58775DCB040EBB9DB4FAB5B14401711C41B'
CORE_SHA='749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00'
LEGACY_DIAGNOSTIC='test_cdt19_final_transport_closure.py'


class G0Blocked(RuntimeError):pass


def fail(s):raise G0Blocked('CDT20_PRE_G06_G0_'+s)
def sha(b):return hashlib.sha256(b).hexdigest().upper()
def require(x,s):
    if not x:fail(s)
def encoded(obj):return (json.dumps(obj,sort_keys=True,ensure_ascii=True,indent=1)+'\n').encode('ascii')


def safe_members(z):
    names=[r.filename for r in z.infolist()]
    require(len(names)==len({n.casefold() for n in names}),'CASEFOLD_DUPLICATE')
    for item in z.infolist():
        n=item.filename
        require(n and not item.is_dir() and not n.startswith('/') and ':' not in n and '\\' not in n
                and all(c not in ('.','..','') for c in n.split('/')) and ((item.external_attr>>16)&0xF000)!=0xA000,'UNSAFE_ZIP')
    require(z.testzip() is None,'ZIP_CRC')
    return names


def canonical_dir(value):
    """Long-path, reparse-free absolute directory (campaign bootstrap semantics)."""
    value=os.path.abspath(os.path.expandvars(str(value)))
    if os.name=='nt':
        import ctypes
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.GetLongPathNameW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
        k.GetLongPathNameW.restype=ctypes.c_uint32
        buf=ctypes.create_unicode_buffer(32768);n=k.GetLongPathNameW(value,buf,len(buf))
        require(0<n<len(buf),'LONG_PATH:'+value);value=buf.value
    path=Path(value)
    for p in (*reversed(path.parents),path):
        st=p.lstat()
        require(not p.is_symlink() and not (getattr(st,'st_file_attributes',0)&0x400),'REPARSE:'+str(p))
    return path


def primary_failure(result):
    """First failing test and the tail of its own traceback, for console and receipt."""
    for kind in ('errors','failures'):
        for test_id,tb in result.get(kind) or []:
            return kind.upper()[:-1]+':'+test_id+'\n'+'\n'.join(tb.strip().splitlines()[-30:])
    if result.get('crash'):return 'CRASH:'+result['crash']+'\n'+'\n'.join(result.get('traceback','').splitlines()[-30:])
    return None


def log_primary_failure(raw):
    """Same extraction for a plain unittest log (legacy diagnostic)."""
    text=raw.decode('utf8','replace').replace('\r\n','\n')
    m=re.search(r'(?ms)^={20,}\n((?:ERROR|FAIL): .*?)(?=^={20,}|^-{20,}\nRan )',text)
    if m:return '\n'.join(m.group(1).strip().splitlines()[-34:])
    return '\n'.join(text.strip().splitlines()[-20:]) or None


def verify_source(w,data):
    require(sha(data)==w['package_sha256'],'SOURCE_SHA256')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=safe_members(z)
        pm=z.read('PACKAGE_MANIFEST.json');cm=z.read('implementation_v001/RUNTIME_CODE_MANIFEST.json')
        require(sha(pm)==w['manifest_sha256'] and sha(cm)==w['code_manifest_sha256'],'MANIFEST_SHA256')
        entries=json.loads(pm)['files']
        require(len(entries)==len(names)-1 and {e['path'] for e in entries}==set(names)-{'PACKAGE_MANIFEST.json'},'PACKAGE_MEMBER_SET')
        for r in entries:
            b=z.read(r['path'])
            require(sha(b)==r['sha256'] and len(b)==r['bytes'],'PACKAGE_MEMBER_HASH:'+r['path'])
        runtime=json.loads(cm)
        require({r['path'] for r in runtime['files']}=={n[len('implementation_v001/candidate/'):] for n in names
                 if n.startswith('implementation_v001/candidate/')},'RUNTIME_SET')
        for r in runtime['files']:
            b=z.read('implementation_v001/candidate/'+r['path'])
            require(sha(b)==r['sha256'] and len(b)==r['bytes'],'RUNTIME_SOURCE_HASH:'+r['path'])
        require(sha(z.read('implementation_v001/candidate/full/tickstore_serial_runner.py'))==CORE_SHA,'CORE_FROZEN')
        return entries,{n:z.read(n) for n in names}


def run_suite(python,runner,test,candidate,out,temp,env,timeout):
    """Campaign-context suite execution; never raises on a test failure."""
    log=out/('G0_'+test.name+'.log');res=out/('G0_'+test.name+'.result.json')
    temp.mkdir()
    child=dict(env,TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp))
    cmd=[python,'-I','-B',str(runner),'--test',str(test),'--candidate',str(candidate),'--log',str(log),'--result',str(res)]
    try:
        done=subprocess.run(cmd,capture_output=True,timeout=timeout,check=False,cwd=str(out),env=child)
        rc,stray=done.returncode,done.stdout+done.stderr
    except subprocess.TimeoutExpired as exc:
        rc,stray=None,(exc.stdout or b'')+(exc.stderr or b'')
    (out/('G0_'+test.name+'.runner_stdio.log')).write_bytes(stray)
    result=json.loads(res.read_bytes()) if res.exists() else {'status':'NO_RESULT','crash':'RUNNER_EXIT:'+str(rc)+':'+stray.decode('utf8','replace')[-2000:]}
    raw=log.read_bytes() if log.exists() else b''
    counts=re.findall(rb'(?m)^Ran (\d+) tests? in [^\r\n]+\r?$',raw)
    closed=(rc==0 and result.get('status')=='PASS' and len(counts)==1 and int(counts[0])==result.get('tests_run')
            and re.search(rb'(?m)^OK(?: \(skipped=\d+\))?\r?$',raw) is not None and b'FAILED (' not in raw)
    return dict(suite=test.name,status='PASS' if closed else 'FAIL',exit_code=rc,tests_run=result.get('tests_run'),
                skipped=[s[0] for s in result.get('skipped') or []],log=log.name,log_sha256=sha(raw),
                result_file=res.name if res.exists() else None,primary_failure=None if closed else primary_failure(result) or 'LOG_NOT_CLOSED')


def gate_row(row,required):
    """Closure needs required DELTA suites unskipped; diagnostics may skip on Windows."""
    row=dict(row,required_by_completeness=required)
    if row['status']=='PASS' and required and row['skipped']:
        row.update(status='FAIL',primary_failure='REQUIRED_SUITE_SKIPPED:'+','.join(row['skipped']))
    return row


def legacy_diagnostic(python,test,out):
    """The 20/10 invocation, unchanged: ambient env/TEMP/cwd and -E. Never gating."""
    log=out/('G0_LEGACY_CONTEXT_'+test.name+'.log')
    try:
        done=subprocess.run([python,'-E','-B',str(test)],capture_output=True,timeout=300,check=False)
        rc,raw=done.returncode,done.stdout+b'\n'+done.stderr
    except subprocess.TimeoutExpired as exc:
        rc,raw=None,(exc.stdout or b'')+b'\n'+(exc.stderr or b'')
    log.write_bytes(raw)
    passed=rc==0 and re.search(rb'(?m)^OK\r?$',raw) is not None
    return dict(suite=test.name,gating=False,context='AMBIENT_TEMP_INHERITED_CWD_FLAG_E',exit_code=rc,
                status='PASS' if passed else 'FAIL',ambient_temp=os.environ.get('TEMP'),log=log.name,log_sha256=sha(raw),
                primary_failure=None if passed else log_primary_failure(raw))


def qualify(here,native):
    w=json.loads((here/'CDT20_R08Q1_WITNESS.json').read_bytes())
    data=(here/w['package_name']).read_bytes()
    entries,members=verify_source(w,data)
    extraction=here/'G0_SOURCES'
    require(not extraction.exists(),'G0_EXTRACT_PREEXISTING')
    extraction.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as z:z.extractall(extraction)
    src=extraction/'implementation_v001';candidate=src/'candidate'
    for sub in ('full','control','g5proof','adapter'):sys.path.insert(0,str(candidate/sub))
    import PRE_G06_PROOF_PROJECTION as projection
    import PRE_G06_CAMPAIGN as campaign
    import PRE_G06_COMPLETENESS as completeness
    # Immutable historical native G3/G6 summary: the corrected validator must
    # accept it and still reject the four adversarial mutations.
    ref=(here/'G0_HISTORICAL_NATIVE_G3_G6.json').read_bytes()
    require(sha(ref)==REAL_SCENARIO_SHA,'REAL_SCENARIO_SHA')
    actual=json.loads(ref)
    require(len(projection.validate(actual)['scenarios'])==4,'ORIGINAL_NATIVE_SCENARIO_MUST_VALIDATE')
    negatives=[]
    for key,value,name,field in [('GROUP_CRASH_ZERO',0,'GROUP_CRASH','exit_code'),
                                 ('COMMIT_CRASH_ZERO',0,'COMMIT_CRASH','exit_code'),
                                 ('CANCEL_WRONG_ACTION','TERMINATE_OWNED_COORDINATOR','CANCEL_TREE','action'),
                                 ('CANCEL_BOOLEAN_EXIT',False,'CANCEL_TREE','exit_code')]:
        altered=copy.deepcopy(actual)
        next(row['interruption'] for row in altered['results']['scenarios'] if row['name']==name)[field]=value
        try:projection.validate(altered)
        except Exception as exc:negatives.append({'case':key,'rejected':type(exc).__name__+':'+str(exc)})
        else:fail('NEGATIVE_FALSE_PASS:'+key)
    require(set(completeness.REQUIRED_DELTA)<=set(campaign.EXTRA),'REQUIRED_DELTA_NOT_IN_CAMPAIGN')
    # Campaign-equivalent context.
    env=dict(os.environ)
    env['LOCALAPPDATA']=str(canonical_dir(os.environ['LOCALAPPDATA'] if native else here))
    env['USERPROFILE']=str(canonical_dir(os.environ['USERPROFILE'] if native else here))
    temp_root=canonical_dir(here)/'G0_TEMP';temp_root.mkdir()
    out=here/'G0_EVIDENCE';out.mkdir()
    runner=here/'G0_SUITE_RUNNER.py'
    suites=[]
    for n,name in enumerate(campaign.EXTRA):
        row=gate_row(run_suite(sys.executable,runner,src/'tests'/name,candidate,out,temp_root/('%02d'%n),env,900),
                     name in completeness.REQUIRED_DELTA)
        suites.append(row)
        print('G0_SUITE='+name+' STATUS='+row['status']+' TESTS='+str(row['tests_run'])+
              ' SKIPPED='+str(len(row['skipped']))+' LOG_SHA256='+row['log_sha256'],flush=True)
        if row['primary_failure']:
            print('G0_PRIMARY_FAILURE_BEGIN '+name+'\n'+row['primary_failure']+'\nG0_PRIMARY_FAILURE_END',flush=True)
    diagnostic=legacy_diagnostic(sys.executable,src/'tests'/LEGACY_DIAGNOSTIC,out)
    print('G0_LEGACY_CONTEXT_DIAGNOSTIC='+diagnostic['status']+' GATING=NO EXIT='+str(diagnostic['exit_code']),flush=True)
    if diagnostic['primary_failure']:
        print('G0_LEGACY_CONTEXT_FAILURE_BEGIN\n'+diagnostic['primary_failure']+'\nG0_LEGACY_CONTEXT_FAILURE_END',flush=True)
    # Tested == packaged: every extracted member is re-read after the suites ran.
    drift=[r['path'] for r in entries if sha((extraction/r['path']).read_bytes())!=r['sha256']]
    require(not drift,'TESTED_CODE_DRIFT:'+','.join(drift[:5]))
    blocked=[r['suite'] for r in suites if r['status']!='PASS']
    receipt=dict(schema='CDT20_PRE_G06_NATIVE_G0_V002',result='PASS' if not blocked else 'BLOCKED',
                 blocked_suites=blocked,native_windows=native,python=sys.version,
                 package_sha256=w['package_sha256'],code_manifest_sha256=w['code_manifest_sha256'],
                 g0_code_sha256=sha(Path(__file__).read_bytes()),runner_sha256=sha(runner.read_bytes()),
                 historical_scenario_sha256=REAL_SCENARIO_SHA,historical_replay='PASS',negative_controls=negatives,
                 suite_context=dict(flags='-I -B',temp_root=str(temp_root),localappdata=env['LOCALAPPDATA'],
                                    userprofile=env['USERPROFILE'],cwd=str(out)),
                 suites=suites,legacy_context_diagnostic=diagnostic,tested_equals_packaged='PASS',
                 production_modified=False,formal_b06_started=False,full_started=False)
    return receipt


def seal(here,receipt):
    out=here/'G0_EVIDENCE'
    with (here/'G0_RESULT.json').open('xb') as f:
        f.write(encoded(receipt));f.flush();os.fsync(f.fileno())
    files=[here/'G0_RESULT.json']+sorted(p for p in out.iterdir() if p.is_file())
    records=[{'path':p.relative_to(here).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in files]
    proof=here/'G0_RETURN.zip'
    with zipfile.ZipFile(proof,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p,r in zip(files,records):z.write(p,arcname=r['path'])
        z.writestr('G0_RETURN_MANIFEST.json',encoded({'schema':'CDT20_G0_NATIVE_PROOF_TRANSPORT_V002',
            'package_sha256':receipt.get('package_sha256'),'g0_result':receipt.get('result'),'files':records,
            'native_windows':receipt.get('native_windows'),'formal_b06_started':False,'production_modified':False}))
    with zipfile.ZipFile(proof) as z:
        require(z.testzip() is None,'G0_RETURN_ZIP_CRC')
        for r in records:require(sha(z.read(r['path']))==r['sha256'],'G0_RETURN_MEMBER_HASH:'+r['path'])
    print('G0_RETURN='+str(proof)+' SHA256='+sha(proof.read_bytes()),flush=True)
    return proof


def main():
    require(os.name=='nt' and sys.version_info>=(3,14) and struct.calcsize('P')==8,'WIN_PYTHON_314_X64')
    receipt=qualify(HERE,native=True)
    seal(HERE,receipt)
    if receipt['result']!='PASS':
        print('PRE_G06_NATIVE_G0=BLOCKED SUITES='+','.join(receipt['blocked_suites']),flush=True)
        return 2
    print('PRE_G06_NATIVE_G0=PASS; SUITES='+str(len(receipt['suites']))+'; NO_PROTECTED_EFFECTS',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except SystemExit:raise
    except BaseException as e:
        import traceback
        print('PRE_G06_NATIVE_G0=BLOCKED REASON='+type(e).__name__+':'+str(e),flush=True)
        traceback.print_exc(file=sys.stdout)
        raise SystemExit(2)
