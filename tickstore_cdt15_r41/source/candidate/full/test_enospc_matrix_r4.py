from pathlib import Path
import errno,hashlib,os,tempfile,zlib
from unittest.mock import patch
import tickstore_serial_runner as r

class Z:
    @staticmethod
    def compress(b,level=9):return zlib.compress(b,9)
    @staticmethod
    def decompress(b):return zlib.decompress(b)
z=Z();BASE=Path(__file__).resolve().parent

def fixture(root,n=12):
    srcroot=root/'src';srcroot.mkdir();src=srcroot/'WIN@N_ticks_SYNTH.csv'
    midnight=r.ref.midnight_epoch_from_datekey(20260923);sem=hashlib.sha256(r.ref.semantic_preamble(20260923));off=hashlib.sha256();starts=[]
    with src.open('wb') as f:
        for i in range(n):
            p=f.tell();starts.append(p);row=((midnight+43200)*1000+i,100000,100005,100010,7,7,i%16,10800)
            line=f'WIN@N;2026.09.23 09:00:00;{row[0]};{row[1]};{row[2]};{row[3]};{row[4]};{row[5]};{row[6]}\n'.encode();f.write(line);sem.update(r.ref.row_semantic_bytes(row));off.update(r.ref.offset_bytes(p))
    size=src.stat().st_size;c={'date_key':'20260923','month_id':'SYNTH','rows':str(n),'first_offset':'0','last_offset':str(starts[-1]),'block_end_offset':str(size),'source_day_bytes':str(size),'semantic_sha256':sem.hexdigest(),'offset_values_sha256':off.hexdigest(),'offset_seconds_first':'10800'};m={'source_sha256':r.sha256_file(src),'source_size':str(size)}
    return src,c,m

def context(root):
    src,c,m=fixture(root);ps=r.PinnedSource(src,int(m['source_size']),m['source_sha256']);ps.__enter__();dest=root/'dest';r.strict_directory(dest,create=True);o=r.make_oracle(c,m,dict(ps.identity),r.EXPECTED_P4A_LEDGER_SHA256,r.file_ids(BASE));return src,c,m,ps,o,dest

def fail(fn):
    try:fn()
    except OSError as e:return e
    raise AssertionError('expected OSError')

def resume_and_check(src,c,ps,o,dest,before):
    out=r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None));assert out in ('RESUMED','RESUMED_PUBLICATION','RESUMED_MANIFEST','REUSED')
    assert src.read_bytes()==before
    pp=r.paths_for_day(dest,c);assert pp['container'].exists() and pp['commit'].exists() and r.manifest_path(dest).exists()

def stage(root,point):
    src,c,m,ps,o,dest=context(root);before=src.read_bytes()
    try:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(point))
    except OSError:pass
    else:raise AssertionError('setup fault not triggered:'+point)
    return src,c,ps,o,dest,before

def main():
    # 1. Group section write ENOSPC.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest=context(root);before=src.read_bytes()
        try:
            e=fail(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector('GROUP_0_SECTION_0_ENOSPC')));assert e.errno==errno.ENOSPC
            resume_and_check(src,c,ps,o,dest,before)
        finally:ps.__exit__(None,None,None)
    print('ENOSPC_GROUP_SECTION=PASS')

    # 2. Journal atomic write ENOSPC after payload fsync, before group authority publication.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest=context(root);before=src.read_bytes();real=r.atomic_journal;calls={'n':0}
        def flaky(path,obj):
            calls['n']+=1
            if calls['n']==2:raise OSError(errno.ENOSPC,'journal injected')
            return real(path,obj)
        try:
            with patch.object(r,'atomic_journal',flaky):e=fail(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            assert e.errno==errno.ENOSPC;resume_and_check(src,c,ps,o,dest,before)
        finally:ps.__exit__(None,None,None)
    print('ENOSPC_JOURNAL_ATOMIC=PASS')

    # 3. Index fsync ENOSPC after full journaled payload.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,ps,o,dest,before=stage(root,'BEFORE_INDEX_FINALIZE');real=r.os.fsync;fired={'v':False}
        def flaky(fd):
            if not fired['v']:
                fired['v']=True;raise OSError(errno.ENOSPC,'index fsync injected')
            return real(fd)
        try:
            with patch.object(r.os,'fsync',flaky):e=fail(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            assert fired['v'] and e.errno==errno.ENOSPC;resume_and_check(src,c,ps,o,dest,before)
        finally:ps.__exit__(None,None,None)
    print('ENOSPC_INDEX_FSYNC=PASS')

    # 4. commit.partial creation/write failure.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,ps,o,dest,before=stage(root,'AFTER_VALIDATE_BEFORE_COMMIT_PARTIAL');real=r.write_transaction_json
        def flaky(path,obj):
            if Path(path).name.endswith('.commit.json.partial'):raise OSError(errno.ENOSPC,'commit partial injected')
            return real(path,obj)
        try:
            with patch.object(r,'write_transaction_json',flaky):e=fail(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            assert e.errno==errno.ENOSPC;resume_and_check(src,c,ps,o,dest,before)
        finally:ps.__exit__(None,None,None)
    print('ENOSPC_COMMIT_PARTIAL=PASS')

    # 5. Container rename failure.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,ps,o,dest,before=stage(root,'AFTER_COMMIT_PARTIAL');pp=r.paths_for_day(dest,c);real=r.secure_replace;fired={'v':False}
        def flaky(a,b):
            if Path(a)==pp['partial'] and Path(b)==pp['container'] and not fired['v']:
                fired['v']=True;raise OSError(errno.ENOSPC,'container rename injected')
            return real(a,b)
        try:
            with patch.object(r,'secure_replace',flaky):e=fail(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            assert fired['v'] and e.errno==errno.ENOSPC;resume_and_check(src,c,ps,o,dest,before)
        finally:ps.__exit__(None,None,None)
    print('ENOSPC_CONTAINER_RENAME=PASS')

    # 6. Commit rename failure.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,ps,o,dest,before=stage(root,'AFTER_CONTAINER_RENAME');pp=r.paths_for_day(dest,c);real=r.secure_replace;fired={'v':False}
        def flaky(a,b):
            if Path(a)==pp['commit_partial'] and Path(b)==pp['commit'] and not fired['v']:
                fired['v']=True;raise OSError(errno.ENOSPC,'commit rename injected')
            return real(a,b)
        try:
            with patch.object(r,'secure_replace',flaky):e=fail(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            assert fired['v'] and e.errno==errno.ENOSPC;resume_and_check(src,c,ps,o,dest,before)
        finally:ps.__exit__(None,None,None)
    print('ENOSPC_COMMIT_RENAME=PASS')

    # 7. Global manifest publication failure.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,ps,o,dest,before=stage(root,'AFTER_COMMIT_RENAME_BEFORE_MANIFEST');real=r.update_manifest;fired={'v':False}
        def flaky(a,b):
            if not fired['v']:
                fired['v']=True;raise OSError(errno.ENOSPC,'manifest injected')
            return real(a,b)
        try:
            with patch.object(r,'update_manifest',flaky):e=fail(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            assert fired['v'] and e.errno==errno.ENOSPC;resume_and_check(src,c,ps,o,dest,before)
        finally:ps.__exit__(None,None,None)
    print('ENOSPC_GLOBAL_MANIFEST=PASS')
    print('ENOSPC_MATRIX_R4=PASS')
    print('SOURCE_CSV_MUTATION=NO')
if __name__=='__main__':main()
