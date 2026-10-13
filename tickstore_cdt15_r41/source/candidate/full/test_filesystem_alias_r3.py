from pathlib import Path
import hashlib, os, tempfile, zlib
from unittest.mock import patch
import tickstore_serial_runner as r

class Z:
    @staticmethod
    def compress(b, level=9): return zlib.compress(b, 9)
    @staticmethod
    def decompress(b): return zlib.decompress(b)
z=Z()

def fixture(root,n=12):
    srcroot=root/'src'; srcroot.mkdir(); src=srcroot/'WIN@N_ticks_SYNTH.csv'
    midnight=r.ref.midnight_epoch_from_datekey(20260923)
    sem=hashlib.sha256(r.ref.semantic_preamble(20260923)); off=hashlib.sha256(); starts=[]
    with src.open('wb') as f:
        for i in range(n):
            p=f.tell(); starts.append(p)
            row=((midnight+43200)*1000+i,100000,100005,100010,7,7,i%16,10800)
            line=f"WIN@N;2026.09.23 09:00:00;{row[0]};{row[1]};{row[2]};{row[3]};{row[4]};{row[5]};{row[6]}\n".encode()
            f.write(line); sem.update(r.ref.row_semantic_bytes(row)); off.update(r.ref.offset_bytes(p))
    size=src.stat().st_size
    c={'date_key':'20260923','month_id':'SYNTH','rows':str(n),'first_offset':'0','last_offset':str(starts[-1]),'block_end_offset':str(size),'source_day_bytes':str(size),'semantic_sha256':sem.hexdigest(),'offset_values_sha256':off.hexdigest(),'offset_seconds_first':'10800'}
    m={'source_sha256':r.sha256_file(src),'source_size':str(size)}
    return src,c,m

def expect(cond,msg):
    if not cond: raise AssertionError(msg)

# R2 terminal false-success: hardlinked partial must now block before modification/publication.
with tempfile.TemporaryDirectory() as td:
    root=Path(td); src,c,m=fixture(root); dest=root/'dest'; r.strict_directory(dest,create=True)
    with r.PinnedSource(src,int(m['source_size']),m['source_sha256']) as ps:
        o=r.make_oracle(c,m,dict(ps.identity),r.EXPECTED_P4A_LEDGER_SHA256,r.file_ids(Path(r.__file__).resolve().parent))
        try:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector('BEFORE_INDEX_FINALIZE'))
        except OSError:pass
        pp=r.paths_for_day(dest,c); victim=root/'victim.bin'; os.link(pp['partial'],victim)
        before=victim.read_bytes()
        try:
            r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None))
            raise AssertionError('hardlink resume unexpectedly succeeded')
        except r.Blocked as e:
            expect('MULTIPLE_HARDLINKS_NOT_ALLOWED' in str(e),str(e))
        expect(victim.read_bytes()==before,'hardlink victim modified')
        expect(not pp['container'].exists(),'container published after hardlink block')
        expect(not pp['commit'].exists(),'commit published after hardlink block')
        expect(not r.manifest_path(dest).exists(),'manifest published after hardlink block')
print('R3_HARDLINK_PARTIAL_BLOCK=PASS')

# Swap the textual ancestor after the old parent dir fd has been pinned but immediately
# before the final basename open. dir_fd must keep the operation on the original directory.
if os.name!='nt':
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); safe=root/'safe'; ext=root/'external'; safe.mkdir(); ext.mkdir()
        target=safe/'target.bin'; target.write_bytes(b'SAFE')
        victim=ext/'target.bin'; victim.write_bytes(b'VICTIM')
        real_open=os.open
        fired={'v':False}
        def raced_open(path,flags,*args,**kwargs):
            if str(path)=='target.bin' and kwargs.get('dir_fd') is not None and not fired['v']:
                fired['v']=True
                os.rename(safe,root/'safe_real')
                os.symlink(ext,safe,target_is_directory=True)
            return real_open(path,flags,*args,**kwargs)
        with patch.object(r.os,'open',raced_open):
            with r.secure_open_existing(target,'r+b') as f:
                f.seek(0); f.write(b'X'); f.flush(); os.fsync(f.fileno())
        expect(fired['v'],'open race injection did not fire')
        expect(victim.read_bytes()==b'VICTIM','open race modified external victim')
        expect((root/'safe_real'/'target.bin').read_bytes()==b'XAFE','open did not stay bound to pinned parent')
    print('R3_ANCESTOR_OPEN_DIRFD_BINDING=PASS')

    # Same race at rename time. os.replace receives basename+dir_fd and must stay bound.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); safe=root/'safe'; ext=root/'external'; safe.mkdir(); ext.mkdir()
        src=safe/'stage'; src.write_bytes(b'NEW')
        dst=safe/'final'; dst.write_bytes(b'SAFE')
        (ext/'stage').write_bytes(b'EXTERNAL_STAGE'); victim=ext/'final'; victim.write_bytes(b'VICTIM')
        real_replace=os.replace; fired={'v':False}
        def raced_replace(a,b,*args,**kwargs):
            if kwargs.get('src_dir_fd') is not None and kwargs.get('dst_dir_fd') is not None and not fired['v']:
                fired['v']=True
                os.rename(safe,root/'safe_real')
                os.symlink(ext,safe,target_is_directory=True)
            return real_replace(a,b,*args,**kwargs)
        with patch.object(r.os,'replace',raced_replace):
            r.secure_replace(src,dst)
        expect(fired['v'],'replace race injection did not fire')
        expect(victim.read_bytes()==b'VICTIM','replace race altered external victim')
        expect((ext/'stage').read_bytes()==b'EXTERNAL_STAGE','replace race consumed external source')
        expect((root/'safe_real'/'final').read_bytes()==b'NEW','rename did not stay bound to pinned parent')
        expect(not (root/'safe_real'/'stage').exists(),'original stage not consumed')
    print('R3_ANCESTOR_REPLACE_DIRFD_BINDING=PASS')
else:
    print('R3_POSIX_DIRFD_RACES=SKIPPED_WINDOWS')

# Static Windows proof points: actual handle final path, ADS, nNumberOfLinks and ancestor pins.
code=Path(r.__file__).read_text(encoding='utf-8')
for needle in ('GetFinalPathNameByHandleW','nNumberOfLinks','WIN_ADS_NOT_ALLOWED','_windows_pin_ancestor_chain','FILE_FLAG_OPEN_REPARSE_POINT'):
    expect(needle in code,'missing Windows defense: '+needle)
print('R3_WINDOWS_STATIC_ALIAS_DEFENSES=PASS')
# Generic hardlink defenses must protect helpers used by payload/index/journal/commit/manifest.
with tempfile.TemporaryDirectory() as td:
    root=Path(td); a=root/'a.bin'; a.write_bytes(b'AAAA'); alias=root/'alias.bin'; os.link(a,alias)
    try:
        r.secure_open_existing(a,'r+b')
        raise AssertionError('hardlinked writable open unexpectedly succeeded')
    except r.Blocked as e:
        expect('MULTIPLE_HARDLINKS_NOT_ALLOWED' in str(e),str(e))
    expect(a.read_bytes()==b'AAAA' and alias.read_bytes()==b'AAAA','generic writable-open alias changed')
print('R3_HARDLINK_WRITABLE_OPEN_BLOCK=PASS')

# Directory creation must also stay bound to the directory handle selected before a textual
# ancestor is swapped.
if os.name!='nt':
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); safe=root/'safe'; ext=root/'external'; safe.mkdir(); ext.mkdir()
        real_mkdir=os.mkdir; fired={'v':False}
        def raced_mkdir(path,*args,**kwargs):
            if str(path)=='child' and kwargs.get('dir_fd') is not None and not fired['v']:
                fired['v']=True
                os.rename(safe,root/'safe_real')
                os.symlink(ext,safe,target_is_directory=True)
            return real_mkdir(path,*args,**kwargs)
        with patch.object(r.os,'mkdir',raced_mkdir):
            r.strict_directory(safe/'child',create=True)
        expect(fired['v'],'mkdir race injection did not fire')
        expect((root/'safe_real'/'child').is_dir(),'child not created under pinned original directory')
        expect(not (ext/'child').exists(),'mkdir race created directory in external target')
    print('R3_ANCESTOR_MKDIR_DIRFD_BINDING=PASS')


with tempfile.TemporaryDirectory() as td:
    root=Path(td); src=root/'stage'; src.write_bytes(b'NEW'); alias=root/'alias'; os.link(src,alias); dst=root/'final'; dst.write_bytes(b'OLD')
    try:
        r.secure_replace(src,dst)
        raise AssertionError('hardlinked replace source unexpectedly succeeded')
    except r.Blocked as e:
        expect('MULTIPLE_HARDLINKS_NOT_ALLOWED' in str(e),str(e))
    expect(alias.read_bytes()==b'NEW','replace-source alias modified')
    expect(dst.read_bytes()==b'OLD','destination changed after source hardlink block')
print('R3_HARDLINK_REPLACE_SOURCE_BLOCK=PASS')

with tempfile.TemporaryDirectory() as td:
    root=Path(td); src=root/'stage'; src.write_bytes(b'NEW'); dst=root/'final'; dst.write_bytes(b'OLD'); alias=root/'alias'; os.link(dst,alias)
    try:
        r.secure_replace(src,dst)
        raise AssertionError('hardlinked replace destination unexpectedly succeeded')
    except r.Blocked as e:
        expect('MULTIPLE_HARDLINKS_NOT_ALLOWED' in str(e),str(e))
    expect(alias.read_bytes()==b'OLD' and dst.read_bytes()==b'OLD','hardlinked destination modified')
    expect(src.read_bytes()==b'NEW','source consumed after destination hardlink block')
print('R3_HARDLINK_REPLACE_DEST_BLOCK=PASS')
print('R3_FILESYSTEM_ALIAS_REGRESSION=PASS')
