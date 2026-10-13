from pathlib import Path
import hashlib,os,tempfile,zlib
from unittest.mock import patch
import tickstore_serial_runner as r

class Z:
    @staticmethod
    def compress(b,level=9):return zlib.compress(b,9)
    @staticmethod
    def decompress(b):return zlib.decompress(b)
z=Z()
BASE=Path(__file__).resolve().parent

def fixture(root,n=12):
    srcroot=root/'src';srcroot.mkdir();src=srcroot/'WIN@N_ticks_SYNTH.csv'
    midnight=r.ref.midnight_epoch_from_datekey(20260923);sem=hashlib.sha256(r.ref.semantic_preamble(20260923));off=hashlib.sha256();starts=[]
    with src.open('wb') as f:
        for i in range(n):
            p=f.tell();starts.append(p);row=((midnight+43200)*1000+i,100000,100005,100010,7,7,i%16,10800)
            line=f'WIN@N;2026.09.23 09:00:00;{row[0]};{row[1]};{row[2]};{row[3]};{row[4]};{row[5]};{row[6]}\n'.encode();f.write(line)
            sem.update(r.ref.row_semantic_bytes(row));off.update(r.ref.offset_bytes(p))
    size=src.stat().st_size
    c={'date_key':'20260923','month_id':'SYNTH','rows':str(n),'first_offset':'0','last_offset':str(starts[-1]),'block_end_offset':str(size),'source_day_bytes':str(size),'semantic_sha256':sem.hexdigest(),'offset_values_sha256':off.hexdigest(),'offset_seconds_first':'10800'}
    m={'source_sha256':r.sha256_file(src),'source_size':str(size)}
    return src,c,m

def ctx(root):
    src,c,m=fixture(root);ps=r.PinnedSource(src,int(m['source_size']),m['source_sha256']);ps.__enter__();dest=root/'dest';r.strict_directory(dest,create=True)
    o=r.make_oracle(c,m,dict(ps.identity),r.EXPECTED_P4A_LEDGER_SHA256,r.file_ids(BASE));return src,c,m,ps,o,dest

def main():
    # Late inode replacement after full validation but before commit.partial must block.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest=ctx(root);st=src.stat();done={'v':False}
        class F:
            def hit(self,p):
                if p=='AFTER_VALIDATE_BEFORE_COMMIT_PARTIAL' and not done['v']:
                    done['v']=True;other=src.with_suffix('.swap');other.write_bytes(src.read_bytes());os.utime(other,ns=(st.st_atime_ns,st.st_mtime_ns));os.replace(other,src)
        try:
            try:r.reconcile_or_build(ps,c,o,dest,z,F());raise AssertionError('late inode swap succeeded')
            except r.Blocked as e:assert 'SOURCE_FILE_ID_CHANGED' in str(e)
            pp=r.paths_for_day(dest,c);assert not pp['container'].exists() and not pp['commit'].exists() and not r.manifest_path(dest).exists()
        finally:ps.__exit__(None,None,None)
    print('R4_LATE_INODE_SWAP=PASS')
    # Poison reserved index bytes after complete journaled payload; resume must deterministically rewrite them.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest=ctx(root)
        try:
            try:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector('BEFORE_INDEX_FINALIZE'))
            except OSError:pass
            pp=r.paths_for_day(dest,c);_,_,index_len,index_off,index_hash_off,_=r.partial_layout(c)
            with r.secure_open_existing(pp['partial'],'r+b') as f:
                f.seek(index_off);f.write(b'\xFF'*index_len);f.seek(index_hash_off);f.write(b'\xEE'*32);f.flush();os.fsync(f.fileno())
            out=r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None));assert out=='RESUMED'
            refout=root/'reference.pts2g';r.ref.encode_day(c,src.parent,refout,z)
            assert refout.read_bytes()==pp['container'].read_bytes()
        finally:ps.__exit__(None,None,None)
    print('R4_INDEX_POISON_REWRITE=PASS')
    print('R3_ADDITIONAL_REGRESSIONS=PASS')
if __name__=='__main__':main()
