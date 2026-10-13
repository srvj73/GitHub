#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import contextlib,copy,csv,hashlib,io,json,os,shutil,tempfile,zipfile,zlib
from unittest.mock import patch
import tickstore_serial_runner as r

BASE=Path(__file__).resolve().parent
RESULTS=[]

class TestZstd:
    """Control-flow test backend only; NOT evidence for ZSTD codec promotion."""
    @staticmethod
    def compress(b,level=9): return zlib.compress(b,9)
    @staticmethod
    def decompress(b): return zlib.decompress(b)
z=TestZstd()

def rec(name,**kw):
    x={"name":name,**kw};RESULTS.append(x);print(json.dumps(x,sort_keys=True),flush=True)

def attempt(fn):
    try:return {"return":fn()}
    except Exception as e:return {"error":type(e).__name__+":"+str(e)}

def fixture(root:Path,n=12):
    srcroot=root/"src";srcroot.mkdir(parents=True)
    src=srcroot/"WIN@N_ticks_SYNTH.csv"
    midnight=r.ref.midnight_epoch_from_datekey(20260923)
    sem=hashlib.sha256(r.ref.semantic_preamble(20260923));oh=hashlib.sha256();offs=[]
    with src.open("wb") as f:
        for i in range(n):
            pos=f.tell();offs.append(pos)
            row=((midnight+43200)*1000+(i//2 if n<1000 else 0),
                 100000 if i%3 else 0,100005 if i%4 else 0,100010 if i%5 else 0,
                 7,8 if i%7==0 else 7,i%16,10800)
            line=f"WIN@N;2026.09.23 09:00:00;{row[0]};{row[1]};{row[2]};{row[3]};{row[4]};{row[5]};{row[6]}\n".encode()
            f.write(line);sem.update(r.ref.row_semantic_bytes(row));oh.update(r.ref.offset_bytes(pos))
    size=src.stat().st_size
    c={"date_key":"20260923","month_id":"SYNTH","rows":str(n),"first_offset":"0",
       "last_offset":str(offs[-1]),"block_end_offset":str(size),"source_day_bytes":str(size),
       "semantic_sha256":sem.hexdigest(),"offset_values_sha256":oh.hexdigest(),
       "offset_seconds_first":"10800"}
    m={"source_sha256":r.sha256_file(src),"source_size":str(size)}
    return src,c,m

def context(root:Path,n=12):
    src,c,m=fixture(root,n)
    ps=r.PinnedSource(src,int(m["source_size"]),m["source_sha256"]);ps.__enter__()
    oracle=r.make_oracle(c,m,dict(ps.identity),r.EXPECTED_P4A_LEDGER_SHA256,r.file_ids(BASE))
    dest=root/"dest";r.strict_directory(dest,create=True)
    return src,c,m,ps,oracle,dest

def test_ledger_same_image():
    source=BASE/"OUT_P4A_R3_FULL_HISTORY_COMPAT.zip"
    with zipfile.ZipFile(source) as q:
        members={n:q.read(n) for n in q.namelist()}
    rows=list(csv.DictReader(io.StringIO(members["P4A_ALL_DAYS.csv"].decode("utf-8-sig"))))
    original=rows[0]["semantic_sha256"];rows[0]["semantic_sha256"]="0"*64
    s=io.StringIO();w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    members["P4A_ALL_DAYS.csv"]=s.getvalue().encode()
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"ledger.zip";p.write_bytes(source.read_bytes())
        real=r.secure_read_all
        def swap(path):
            raw=real(path)
            if Path(path)==p:
                with zipfile.ZipFile(p,"w",compression=zipfile.ZIP_DEFLATED) as zf:
                    for n,b in members.items():zf.writestr(n,b)
            return raw
        with patch.object(r,"secure_read_all",swap):
            days,months,reported=r.load_ledgers(p)
        rec("ledger_swap_after_read",semantic=days[0]["semantic_sha256"],original=original,
            reported=reported,actual=r.sha256_file(p),
            pass_closed=(days[0]["semantic_sha256"]==original and reported!=r.sha256_file(p)))

def test_source_binding():
    # Same inode mutation, size/mtime restored, injected after full validation.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest=context(root)
        st=src.stat()
        class F:
            def hit(self,point):
                if point=="AFTER_VALIDATE_BEFORE_COMMIT_PARTIAL":
                    data=src.read_bytes().replace(b"100000",b"100005",1)
                    src.write_bytes(data);os.utime(src,ns=(st.st_atime_ns,st.st_mtime_ns))
        try:
            out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,F()))
            pp=r.paths_for_day(dest,c)
            rec("source_mutate_restore_metadata",**out,
                final_pair=pp["container"].exists() or pp["commit"].exists(),
                manifest=r.manifest_path(dest).exists())
        finally:ps.__exit__(None,None,None)

    # Replacement after hashing same handle must fail path binding.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m=fixture(root);st=src.stat();real=r.PinnedSource.hash_all;fired=False
        def swap(self):
            nonlocal fired
            d=real(self)
            if not fired:
                fired=True
                other=src.with_suffix(".replacement")
                other.write_bytes(src.read_bytes().replace(b"09:00:00",b"+9:00:00"))
                os.utime(other,ns=(st.st_atime_ns,st.st_mtime_ns));os.replace(other,src)
            return d
        with patch.object(r.PinnedSource,"hash_all",swap):
            out=attempt(lambda:r.PinnedSource(src,int(m["source_size"]),m["source_sha256"]).__enter__())
        rec("source_replace_during_identity",**out)

def test_journal_all_groups():
    for variant in ("durable_zero","schema_wrong","trailing_suffix"):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src,c,m,ps,o,dest=context(root)
            try:
                attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector("BEFORE_INDEX_FINALIZE")))
                pp=r.paths_for_day(dest,c);j=r.read_json_strict(pp["journal"])
                if variant=="durable_zero":
                    j["durable_end"]=0;pp["journal"].write_bytes(r.stable_json(j)+b"\n")
                elif variant=="schema_wrong":
                    j["schema"]="WRONG";pp["journal"].write_bytes(r.stable_json(j)+b"\n")
                else:
                    with pp["partial"].open("ab") as f:f.write(b"UNJOURNALED")
                out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
                rec("all_groups_"+variant,**out)
            finally:ps.__exit__(None,None,None)

def built(root:Path):
    src,c,m,ps,o,dest=context(root)
    result=r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None))
    return src,c,m,ps,o,dest,r.paths_for_day(dest,c),result

def test_manifest_orphans():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest,pp,_=built(root)
        try:
            r.safe_unlink_regular(r.manifest_path(dest))
            fake={"schema":"WRONG","state":"VALIDATED_PENDING_PUBLISH","oracle":o,
                  "completed_groups":[],"durable_end":0,"container_sha256":"0"*64,"container_bytes":1}
            r.atomic_write_json(pp["journal"],fake)
            out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            rec("manifest_missing_invalid_journal",**out,journal_remains=pp["journal"].exists(),
                manifest_created=r.manifest_path(dest).exists())
        finally:ps.__exit__(None,None,None)

    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest,pp,_=built(root)
        try:
            fake={"schema":"WRONG","state":"BUILDING","oracle":{"other":True},
                  "completed_groups":[],"durable_end":0}
            r.atomic_write_json(pp["journal"],fake)
            out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            rec("manifest_present_incompatible_journal",**out,journal_remains=pp["journal"].exists())
        finally:ps.__exit__(None,None,None)

    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest,pp,_=built(root)
        try:
            r.safe_unlink_regular(r.manifest_path(dest));r.secure_replace(pp["commit"],pp["commit_partial"])
            out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            rec("container_commit_partial_no_journal",**out)
        finally:ps.__exit__(None,None,None)

def test_conflict_before_cleanup():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest,pp,_=built(root)
        try:
            pp["partial"].write_bytes(b"foreign");pp["journal_atomic"].write_bytes(b"shadow")
            out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            rec("final_pair_partial_plus_shadow",**out,
                partial_remains=pp["partial"].exists(),shadow_remains=pp["journal_atomic"].exists())
        finally:ps.__exit__(None,None,None)

def test_symlinks():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest=context(root)
        try:
            attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector("BEFORE_INDEX_FINALIZE")))
            pp=r.paths_for_day(dest,c);victim=root/"victim.bin"
            r.secure_replace(pp["partial"],victim);before=r.sha256_file(victim)
            try:pp["partial"].symlink_to(victim)
            except OSError:
                rec("symlink_partial","SKIP_ENVIRONMENT");return
            out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            rec("symlink_partial",**out,victim_unchanged=(r.sha256_file(victim)==before))
        finally:ps.__exit__(None,None,None)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);target=root/"target";target.mkdir();link=root/"link"
        try:link.symlink_to(target,target_is_directory=True)
        except OSError:
            rec("symlink_ancestor","SKIP_ENVIRONMENT");return
        out=attempt(lambda:r.strict_directory(link/"dest",create=True))
        rec("symlink_ancestor",**out,target_dest_created=(target/"dest").exists())

def test_crash_matrix():
    points=["BEFORE_GROUP_0_PAYLOAD","GROUP_0_SECTION_0_ENOSPC",
            "AFTER_GROUP_0_PAYLOAD_BEFORE_JOURNAL","AFTER_GROUP_0_JOURNAL",
            "BEFORE_INDEX_FINALIZE","AFTER_VALIDATE_BEFORE_COMMIT_PARTIAL",
            "AFTER_COMMIT_PARTIAL","AFTER_CONTAINER_RENAME",
            "AFTER_COMMIT_RENAME_BEFORE_MANIFEST","AFTER_MANIFEST_BEFORE_JOURNAL_CLEANUP"]
    for point in points:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src,c,m,ps,o,dest=context(root)
            try:
                first=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(point)))
                second=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
                rec("crash_"+point,first=first,resumed=second)
            finally:ps.__exit__(None,None,None)

def test_two_groups():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest=context(root,262146)
        try:
            first=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector("AFTER_GROUP_0_JOURNAL")))
            pp=r.paths_for_day(dest,c)
            with pp["partial"].open("ab") as f:f.write(b"UNJOURNALED_SUFFIX")
            resumed=r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None))
            refout=root/"reference.pts2g";r.ref.encode_day(c,src.parent,refout,z)
            rec("two_group_resume",first=first,resumed=resumed,
                byte_identical=(refout.read_bytes()==pp["container"].read_bytes()))
        finally:ps.__exit__(None,None,None)

def test_lock_terminal_status():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m=fixture(root);dest=root/"dest";cap=io.StringIO()
        with patch.object(r.ref,"require_zstd",lambda:z),\
             patch.object(r,"load_ledgers",lambda p:([c],{"SYNTH":m},r.EXPECTED_P4A_LEDGER_SHA256)),\
             patch.object(r,"release_lock",side_effect=r.Blocked("WRITER_LOCK_REMOVE_FAIL")),\
             contextlib.redirect_stdout(cap):
            out=attempt(lambda:r.run_one_day(src.parent,dest,BASE/"OUT_P4A_R3_FULL_HISTORY_COMPAT.zip",c["date_key"],None))
        text=cap.getvalue()
        rec("lock_release_failure_terminal_status",**out,
            terminal_success_present=("TICKSTORE_RUNNER_STATUS=PASS" in text),
            day_result_present=("TICKSTORE_DAY_RESULT=" in text))


def test_source_mutation_publication_points():
    for point in ("AFTER_COMMIT_PARTIAL","AFTER_CONTAINER_RENAME",
                  "AFTER_COMMIT_RENAME_BEFORE_MANIFEST","AFTER_MANIFEST_BEFORE_JOURNAL_CLEANUP"):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src,c,m,ps,o,dest=context(root);st=src.stat()
            class F:
                def __init__(self):self.done=False
                def hit(self,p):
                    if p==point and not self.done:
                        self.done=True
                        data=src.read_bytes().replace(b"100000",b"100005",1)
                        src.write_bytes(data);os.utime(src,ns=(st.st_atime_ns,st.st_mtime_ns))
            try:
                out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,F()))
                pp=r.paths_for_day(dest,c)
                rec("source_mutation_"+point,**out,container=pp["container"].exists(),
                    commit=pp["commit"].exists(),manifest=r.manifest_path(dest).exists(),
                    journal=pp["journal"].exists())
            finally:ps.__exit__(None,None,None)

def test_surviving_journal_symlink():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src,c,m,ps,o,dest,pp,_=built(root)
        try:
            outside=root/"outside.json";outside.write_text("leave-me",encoding="utf-8")
            try:pp["journal"].symlink_to(outside)
            except OSError:
                rec("surviving_journal_symlink","SKIP_ENVIRONMENT");return
            out=attempt(lambda:r.reconcile_or_build(ps,c,o,dest,z,r.FaultInjector(None)))
            rec("surviving_journal_symlink",**out,outside_unchanged=(outside.read_text()=="leave-me"),
                symlink_remains=pp["journal"].is_symlink())
        finally:ps.__exit__(None,None,None)


def main():
    for fn in [test_ledger_same_image,test_source_binding,test_journal_all_groups,
               test_manifest_orphans,test_conflict_before_cleanup,test_symlinks,
               test_source_mutation_publication_points,test_surviving_journal_symlink,
               test_crash_matrix,test_two_groups,test_lock_terminal_status]:
        fn()
    # Mandatory expectations.
    by={x["name"]:x for x in RESULTS}
    assert by["ledger_swap_after_read"]["pass_closed"] is True
    assert "SOURCE_OPEN_HANDLE_SHA_CHANGED" in by["source_mutate_restore_metadata"]["error"]
    assert by["source_mutate_restore_metadata"]["final_pair"] is False
    assert "SOURCE_FILE_ID_CHANGED" in by["source_replace_during_identity"]["error"]
    assert "PARTIAL_SHORTER_THAN_JOURNAL" in by["all_groups_durable_zero"]["error"]
    assert "JOURNAL_SCHEMA" in by["all_groups_schema_wrong"]["error"]
    assert by["all_groups_trailing_suffix"]["return"]=="RESUMED"
    assert "JOURNAL_SCHEMA" in by["manifest_missing_invalid_journal"]["error"]
    assert by["manifest_missing_invalid_journal"]["journal_remains"] is True
    assert "JOURNAL_SCHEMA" in by["manifest_present_incompatible_journal"]["error"]
    assert "UNPROVEN" in by["container_commit_partial_no_journal"]["error"]
    assert "CONFLICTING_FINAL_AND_PARTIAL_STATE" in by["final_pair_partial_plus_shadow"]["error"]
    assert by["final_pair_partial_plus_shadow"]["partial_remains"] is True
    if "error" in by["symlink_partial"]:
        assert by["symlink_partial"]["victim_unchanged"] is True
    if "error" in by["symlink_ancestor"]:
        assert by["symlink_ancestor"]["target_dest_created"] is False
    for k,v in by.items():
        if k.startswith("crash_"):
            assert "error" in v["first"]
            assert v["resumed"].get("return") in ("RESUMED","RESUMED_PUBLICATION","RESUMED_MANIFEST","REUSED")
    assert by["two_group_resume"]["resumed"]=="RESUMED"
    assert by["two_group_resume"]["byte_identical"] is True
    assert by["lock_release_failure_terminal_status"]["terminal_success_present"] is False
    assert by["lock_release_failure_terminal_status"]["day_result_present"] is False
    for point in ("AFTER_COMMIT_PARTIAL","AFTER_CONTAINER_RENAME","AFTER_COMMIT_RENAME_BEFORE_MANIFEST","AFTER_MANIFEST_BEFORE_JOURNAL_CLEANUP"):
        assert "SOURCE_OPEN_HANDLE_SHA_CHANGED" in by["source_mutation_"+point]["error"]
        assert by["source_mutation_"+point]["journal"] is True
    if "error" in by["surviving_journal_symlink"]:
        assert "LINK_OR_REPARSE_NOT_ALLOWED" in by["surviving_journal_symlink"]["error"]
        assert by["surviving_journal_symlink"]["outside_unchanged"] is True
    print("FULL_RUNNER_R3_ADVERSARIAL=PASS")
    print(f"OBSERVATIONS={len(RESULTS)}")
    print("CODEC_BACKEND_FOR_SYNTHETIC_CONTROL_TESTS=ZLIB_TEST_ONLY")
    print("REAL_CSV_READ=NO")
    print("REAL_PILOT=NO")
    print("FULL_HISTORY=NO")

if __name__=="__main__":
    main()
