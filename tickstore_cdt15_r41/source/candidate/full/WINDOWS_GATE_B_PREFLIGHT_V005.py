from __future__ import annotations
from pathlib import Path
import argparse, ctypes, ctypes.wintypes, hashlib, json, os, shutil, subprocess, sys, tempfile, time
import tickstore_serial_runner as r

SCHEMA=r.WINDOWS_PREFLIGHT_SCHEMA

class PreflightBlocked(RuntimeError): pass

def check(cond,msg):
    if not cond: raise PreflightBlocked(msg)

def expect_block(fn, contains=None):
    try:
        fn()
    except r.Blocked as e:
        if contains and contains not in str(e):
            raise PreflightBlocked(f"UNEXPECTED_BLOCK:{e}") from e
        return str(e)
    raise PreflightBlocked("EXPECTED_BLOCK_DID_NOT_OCCUR"+(":"+contains if contains else ""))

def sha(path:Path): return r.sha256_file(path)

def win_createfile(path:Path, access:int, share:int, flags:int=0x80|0x00200000):
    k32=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=k32.CreateFileW
    fn.argtypes=[ctypes.wintypes.LPCWSTR,ctypes.wintypes.DWORD,ctypes.wintypes.DWORD,ctypes.c_void_p,ctypes.wintypes.DWORD,ctypes.wintypes.DWORD,ctypes.wintypes.HANDLE]
    fn.restype=ctypes.wintypes.HANDLE
    h=fn(str(path),access,share,None,3,flags,None)
    invalid=ctypes.wintypes.HANDLE(-1).value
    return k32,h,invalid,ctypes.get_last_error()

def short_path(path:Path):
    k32=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=k32.GetShortPathNameW
    fn.argtypes=[ctypes.wintypes.LPCWSTR,ctypes.wintypes.LPWSTR,ctypes.wintypes.DWORD]
    fn.restype=ctypes.wintypes.DWORD
    n=fn(str(path),None,0)
    if n==0:return None
    buf=ctypes.create_unicode_buffer(n+2)
    n2=fn(str(path),buf,len(buf))
    if n2==0:return None
    return Path(buf.value)

def run(args):
    if os.name!='nt': raise PreflightBlocked('WINDOWS_REQUIRED')
    if sys.version_info < (3,14): raise PreflightBlocked('PYTHON_3_14_REQUIRED:'+sys.version.split()[0])
    zstd=r.require_windows_pilot_runtime()
    base=Path(__file__).resolve().parent
    ledger=Path(args.ledger_zip).resolve()
    r.strict_regular_file(ledger)
    ids=r.file_ids(base)
    ledger_sha=r.sha256_file(ledger)
    check(ledger_sha==r.EXPECTED_P4A_LEDGER_SHA256,'LEDGER_SHA_MISMATCH')
    days,months,zsha=r.load_ledgers(ledger)
    check(zsha==ledger_sha,'LEDGER_LOAD_SHA_MISMATCH')
    check(any(d['date_key']==args.pilot_date for d in days),'PILOT_DATE_NOT_IN_LEDGER')
    check(args.pilot_date in r.FROZEN_PILOT_DATES,'PILOT_DATE_NOT_FROZEN_GATE_B_CASE')
    source_root=Path(args.source_root).resolve()
    dest_root=Path(args.dest_root).resolve()
    scratch_parent=Path(args.scratch_root).resolve()
    r.strict_directory(source_root,create=False)
    source_volume=r.windows_volume_identity(source_root)
    dest_volume=r.windows_volume_identity(dest_root)
    scratch_volume=r.windows_volume_identity(scratch_parent)
    check(len({source_volume['serial'],dest_volume['serial'],scratch_volume['serial']})==1 and len({source_volume['root'],dest_volume['root'],scratch_volume['root']})==1,'SOURCE_DEST_SCRATCH_VOLUME_MISMATCH')
    zproof=r.native_zstd_origin_evidence(zstd)

    r.strict_directory(scratch_parent,create=True)
    root=Path(tempfile.mkdtemp(prefix='TICKSTORE_GATE_B_PREFLIGHT_',dir=str(scratch_parent)))
    results={}
    try:
        # Native zstd round-trip is already performed by require_zstd; add a second deterministic probe.
        probe=(b'TICKSTORE_GATE_B_NATIVE_ZSTD_'*4096)
        enc=zstd.compress(probe,level=9); dec=zstd.decompress(enc)
        check(dec==probe,'NATIVE_ZSTD_ROUNDTRIP_FAIL')
        results['native_zstd_roundtrip']='PASS'

        # Hardlink alias must block before writable access.
        a=root/'hardlink_source.bin'; a.write_bytes(b'AAAA')
        alias=root/'hardlink_alias.bin'; os.link(a,alias)
        before=a.read_bytes()
        expect_block(lambda:r.secure_open_existing(a,'r+b'),'MULTIPLE_HARDLINKS_NOT_ALLOWED')
        check(a.read_bytes()==before and alias.read_bytes()==before,'HARDLINK_VICTIM_CHANGED')
        results['hardlink_alias']='PASS'

        # ADS must be rejected syntactically before any open.
        adsbase=root/'adsbase.bin'; adsbase.write_bytes(b'BASE')
        expect_block(lambda:r.secure_open_existing(Path(str(adsbase)+':tickstore'),'r+b'),'WIN_ADS_NOT_ALLOWED')
        results['ads']='PASS'

        # Junction/reparse directory must be rejected.
        target=root/'junction_target'; target.mkdir(); junction=root/'junction_link'
        cp=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(target)],capture_output=True,text=True)
        check(cp.returncode==0,'JUNCTION_CREATE_FAIL:'+cp.stdout+cp.stderr)
        expect_block(lambda:r.strict_directory(junction),'LINK_OR_REPARSE_NOT_ALLOWED')
        results['junction_reparse']='PASS'

        # Symlink where permitted. Lack of Windows privilege is an explicit N/A, as matrix says "where permitted".
        sym=root/'symlink_link'
        try:
            os.symlink(target,sym,target_is_directory=True)
        except OSError as e:
            results['symlink']='NOT_PERMITTED_WINERROR_'+str(getattr(e,'winerror',None))
        else:
            expect_block(lambda:r.strict_directory(sym),'LINK_OR_REPARSE_NOT_ALLOWED')
            results['symlink']='PASS'

        # 8.3 alias: if the volume exposes one, the handle final-path binding must reject alternate spelling.
        longf=root/'TICKSTORE_LONG_FILENAME_FOR_83_ALIAS_TEST_123456789.bin'; longf.write_bytes(b'LONG')
        sp=short_path(longf)
        if sp is None or r._windows_normalized_path(sp)==r._windows_normalized_path(longf):
            results['alias_8dot3']='NOT_AVAILABLE_ON_VOLUME'
        else:
            expect_block(lambda:r.secure_open_existing(sp,'rb'),'WIN_HANDLE_PATH_MISMATCH')
            results['alias_8dot3']='PASS'

        # Source pin must deny a second writer and path replacement/deletion while live.
        src=root/'source_pin.csv'; src.write_bytes(b'PINNED-SOURCE')
        src_sha=hashlib.sha256(src.read_bytes()).hexdigest().upper(); src_size=src.stat().st_size
        with r.PinnedSource(src,src_size,src_sha):
            GENERIC_WRITE=0x40000000; SHARE_ALL=0x1|0x2|0x4
            k32,h,invalid,err=win_createfile(src,GENERIC_WRITE,SHARE_ALL)
            if h!=invalid:
                k32.CloseHandle(h); raise PreflightBlocked('SOURCE_SHARE_DENIAL_FAIL_SECOND_WRITER_OPENED')
            check(err in (5,32,33),'SOURCE_SHARE_DENIAL_UNEXPECTED_WINERROR:'+str(err))
            repl=root/'replacement.tmp'; repl.write_bytes(b'REPLACEMENT')
            try:
                os.replace(repl,src)
            except OSError:
                pass
            else:
                raise PreflightBlocked('SOURCE_DELETE_SHARE_DENIAL_FAIL_REPLACE_SUCCEEDED')
            check(src.read_bytes()==b'PINNED-SOURCE','PINNED_SOURCE_CHANGED')
        results['createfile_share_denial']='PASS'

        # Pinning ancestors must stop live rename/delete of the directory object.
        anc=root/'ancestor_pin'; anc.mkdir(); (anc/'x').write_bytes(b'X')
        pins=r._windows_pin_ancestor_chain(anc)
        try:
            renamed=root/'ancestor_renamed'
            try: os.rename(anc,renamed)
            except OSError: pass
            else: raise PreflightBlocked('ANCESTOR_RENAME_SUCCEEDED_WHILE_PINNED')
            check(anc.exists(),'ANCESTOR_DISAPPEARED_WHILE_PINNED')
        finally:
            r._windows_unpin(pins)
        os.rename(anc,root/'ancestor_after_unpin')
        results['live_ancestor_rename_denial']='PASS'

        # Process-style contention simulation: exclusive HANDLE must make runner access fail closed; retry after release works.
        locked=root/'transient_lock.bin'; locked.write_bytes(b'LOCK')
        GENERIC_READ=0x80000000;GENERIC_WRITE=0x40000000
        k32,h,invalid,err=win_createfile(locked,GENERIC_READ|GENERIC_WRITE,0)
        check(h!=invalid,'EXCLUSIVE_HANDLE_CREATE_FAIL:'+str(err))
        try:
            expect_block(lambda:r.secure_open_existing(locked,'r+b'),'WIN_CREATEFILE_FAIL')
        finally:
            k32.CloseHandle(h)
        with r.secure_open_existing(locked,'r+b') as f:
            check(f.read()==b'LOCK','POST_LOCK_READ_FAIL')
        results['transient_external_denial']='PASS'

        # Writer lock semantics on the same NTFS destination scratch.
        lock_root=root/'lockroot'; r.strict_directory(lock_root,create=True)
        lock=r.acquire_lock(lock_root)
        try: expect_block(lambda:r.acquire_lock(lock_root),'WRITER_LOCK_EXISTS')
        finally: r.release_lock(lock)
        results['single_writer']='PASS'

        # OneDrive is observational here; actual transient-denial behavior is tested above and must remain fail-closed.
        try:
            tl=subprocess.run(['tasklist','/FI','IMAGENAME eq OneDrive.exe'],capture_output=True,text=True,timeout=15)
            results['onedrive_process_running']='ONEDRIVE.EXE' in tl.stdout.upper()
        except Exception:
            results['onedrive_process_running']='UNKNOWN'

        report={
            'schema':SCHEMA,'status':'PASS','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'windows_runtime':True,'python_version':sys.version.split()[0],'python_3_14_or_newer':True,
            'native_compression_zstd':True,'core_filesystem_tests':'PASS','pilot_date':args.pilot_date,
            'runner_sha256':ids['runner_sha256'],'reference_sha256':ids['reference_sha256'],
            'spec_sha256':ids['spec_sha256'],'preflight_sha256':ids['preflight_sha256'],'ledger_sha256':ledger_sha,
            'source_root':r._norm_binding_path(source_root),'dest_root':r._norm_binding_path(dest_root),
            'scratch_root':r._norm_binding_path(scratch_parent),
            'source_volume':source_volume,'dest_volume':dest_volume,'scratch_volume':scratch_volume,
            'zstd_module':zproof['module'],'zstd_origin':zproof['origin'],'zstd_stdlib_root':zproof['stdlib_root'],
            'results':results,
            'limitations':[
                'This preflight proves core Windows filesystem behavior on the supplied scratch volume.',
                'It does not itself close the full Gate B real-pilot matrix or authorize full history.',
                'OneDrive/antivirus behavior is represented by fail-closed external-lock simulation plus process observation; real pilot evidence remains required.'
            ]
        }
        out=Path(args.report).resolve()
        out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists(): raise PreflightBlocked('REPORT_ALREADY_EXISTS:'+str(out))
        out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        print('TICKSTORE_WINDOWS_GATE_B_PREFLIGHT=PASS')
        print('REPORT='+str(out))
        print('REPORT_SHA256='+hashlib.sha256(out.read_bytes()).hexdigest().upper())
        print('PILOT_DATE='+args.pilot_date)
        print('REAL_PILOT_EXECUTED=NO')
        print('FULL_HISTORY_EXECUTION_AUTHORIZED=NO')
        return 0
    finally:
        # Only the unique scratch child created above can be removed.
        try:
            if root.parent==scratch_parent and root.name.startswith('TICKSTORE_GATE_B_PREFLIGHT_'):
                shutil.rmtree(root)
        except Exception as e:
            print('PREFLIGHT_SCRATCH_CLEANUP_WARNING='+repr(e),file=sys.stderr)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--ledger-zip',required=True)
    ap.add_argument('--scratch-root',required=True)
    ap.add_argument('--report',required=True)
    ap.add_argument('--pilot-date',default='20260731')
    ap.add_argument('--source-root',required=True)
    ap.add_argument('--dest-root',required=True)
    a=ap.parse_args()
    try: raise SystemExit(run(a))
    except (PreflightBlocked,r.Blocked) as e:
        print('TICKSTORE_WINDOWS_GATE_B_PREFLIGHT=BLOCKED')
        print('REASON='+str(e))
        raise SystemExit(2)
