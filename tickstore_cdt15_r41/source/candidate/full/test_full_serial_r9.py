"""Owner-local synthetic R9 tests. No real CSV or production destination is used.

The zlib backend tests transaction control only. It does not certify ZSTD9.
Portable tests explicitly replace only the Windows admission check for tiny fixtures;
the Windows sharing test uses the real pin and is skipped elsewhere.
"""
from pathlib import Path
import contextlib
import builtins
import copy
import hashlib
import io
import json
import os
import signal
import tempfile
import unittest
import zlib
from unittest.mock import Mock,patch

import tickstore_serial_runner as r

BASE=Path(__file__).resolve().parent
LEDGER_SHA=r.EXPECTED_P4A_LEDGER_SHA256
COMPAT_FIELDS=("time_msc_decrease_rows","price_negative_rows","negative_unsupported_rows",
               "price_not_multiple_5_rows","offset_seconds_change_rows","f6_f7_numeric_diff_rows",
               "f6_f7_lexical_diff_rows","f6_noncanonical_lexical_rows","f7_noncanonical_lexical_rows")


class SyntheticCodec:
    @staticmethod
    def compress(data,level=9): return zlib.compress(data,9)
    @staticmethod
    def decompress(data): return zlib.decompress(data)


def fixture(root,dates=("20260730","20260731","20260803")):
    source=root/"source";source.mkdir()
    dest=root/"dest";dest.mkdir()
    days=[];months={}
    for month_id in sorted({d[:4]+"_"+d[4:6] for d in dates}):
        path=source/f"WIN@N_ticks_{month_id}.csv"
        items=[]
        with path.open("wb") as stream:
            for key in sorted(d for d in dates if d[:4]+"_"+d[4:6]==month_id):
                start=stream.tell();sem=hashlib.sha256(r.ref.semantic_preamble(int(key)));off=hashlib.sha256()
                midnight=r.ref.midnight_epoch_from_datekey(int(key))
                for i in range(3):
                    last=stream.tell()
                    row=((midnight+43200)*1000+i,100000,100005,100010,7,7,i,10800)
                    stamp=key[:4]+"."+key[4:6]+"."+key[6:]
                    stream.write(f"WIN@N;{stamp} 09:00:00;{row[0]};100000;100005;100010;7;7;{i}\n".encode())
                    sem.update(r.ref.row_semantic_bytes(row));off.update(r.ref.offset_bytes(last))
                end=stream.tell()
                c={"date_key":key,"month_id":month_id,"rows":"3","first_offset":str(start),
                   "last_offset":str(last),"block_end_offset":str(end),"source_day_bytes":str(end-start),
                   "semantic_sha256":sem.hexdigest(),"offset_values_sha256":off.hexdigest(),
                   "offset_seconds_first":"10800",**{field:"0" for field in COMPAT_FIELDS}}
                items.append(c);days.append(c)
        months[month_id]={"month_id":month_id,"source_sha256":r.sha256_file(path),
                          "source_size":str(path.stat().st_size),"rows":str(len(items)*3),"days":str(len(items)),
                          "core_codec_compatible":"YES","p1e_lexical_compatible":"YES",
                          "seal_integrity":"PASS","summary_ledger_crosscheck":"PASS"}
    days.sort(key=lambda c:c["date_key"])
    contract={"schema":"TICKSTORE_FULL_PLAN_CONTRACT_V001","ledger_sha256":LEDGER_SHA,
              "days":len(days),"months":len(months),"rows":len(days)*3,
              "source_bytes":sum(int(m["source_size"]) for m in months.values()),
              "unique_month_source_bytes":sum(int(m["source_size"]) for m in months.values()),
              "first_date":days[0]["date_key"],"last_date":days[-1]["date_key"],
              "date_sequence_sha256":r.sha256_bytes(("\n".join(c["date_key"] for c in days)+"\n").encode()),
              "month_sequence_sha256":r.sha256_bytes(("\n".join(sorted(months))+"\n").encode()),
              "naive_one_month_hash_per_day_bytes":sum(int(months[c["month_id"]]["source_size"]) for c in days),
              "dates_sorted_ascending":True,
              "months_sorted_ascending":True,"range_partition_exact":True}
    contract["full_plan_sha256"]=r.sha256_bytes(r.stable_json(contract))
    ids={"runner_sha256":"SYNTHETIC_R9","reference_sha256":"SYNTHETIC_REFERENCE","spec_sha256":"SYNTHETIC_SPEC"}
    cert=json.loads((BASE/"TICKSTORE_GATE_B_R8_FINAL_CERTIFICATE_20260924.json").read_text())
    return source,dest,days,months,contract,ids,cert


class FullSerialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source,self.dest,self.days,self.months,self.contract,self.ids,self.cert=fixture(self.root)
        self.codec=SyntheticCodec()

    def execute(self,fault=None):
        capture=io.StringIO()
        with patch.object(r,"_require_full_serial_windows"),contextlib.redirect_stdout(capture):
            result=r._execute_full_serial(self.source,self.dest,self.days,self.months,LEDGER_SHA,
                                          self.ids,self.cert,self.codec,fault)
        return result,capture.getvalue()

    def reconcile(self):
        identities={}
        for key,m in self.months.items():
            with r.PinnedSource(self.source/f"WIN@N_ticks_{key}.csv",int(m["source_size"]),m["source_sha256"]) as pin:
                identities[key]=dict(pin.identity)
        return r.reconcile_full_readonly(self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,identities,self.codec)

    def release_gate_bindings(self):
        expected={"schema":r.FULL_OWNER_GATE_SCHEMA,"authorized":True,"runner_schema":r.RUNNER_SCHEMA,
                  "runner_sha256":"1"*64,"reference_sha256":r.FROZEN_REFERENCE_SHA256,
                  "full_spec_sha256":"2"*64,"full_plan_sha256":self.contract["full_plan_sha256"],
                  "full_plan_contract_sha256":r.FULL_PLAN_CONTRACT_SHA256,
                  "ledger_sha256":LEDGER_SHA,"gate_b_certificate_sha256":r.GATE_B_CERTIFICATE_SHA256}
        for name in ("source","dest","scratch"):
            expected[name+"_root"]=name
            expected[name+"_volume"]={"root":"D:\\","serial":name.upper(),"filesystem":"NTFS"}
        return expected

    def call_release_route(self,gate,trusted_sha,dispatch):
        raw=r.stable_json(gate)
        expected=self.release_gate_bindings()
        scratch=self.root/"scratch"
        with patch.object(r,"_require_full_serial_windows"),\
             patch.object(r,"require_windows_pilot_runtime",return_value=self.codec),\
             patch.object(r,"full_release_materials",return_value=(self.contract,self.cert,self.ids)),\
             patch.object(r,"load_ledgers",return_value=(self.days,self.months,LEDGER_SHA)),\
             patch.object(r,"validate_full_plan",return_value=self.days),\
             patch.object(r,"full_gate_bindings",return_value=expected),\
             patch.object(r,"secure_read_all",return_value=raw),\
             patch.object(r,"_execute_full_serial",dispatch):
            return r.run_full_serial(self.source,self.dest,scratch,Path("synthetic-ledger.zip"),
                                     Path("synthetic-owner-gate.json"),trusted_sha)

    def test_canonical_sealed_plan(self):
        contract,cert,ids=r.full_release_materials(BASE)
        days,months,sha=r.load_ledgers(BASE/"OUT_P4A_R3_FULL_HISTORY_COMPAT.zip")
        ordered=r.validate_full_plan(days,months,sha,contract)
        self.assertEqual(len(ordered),1550);self.assertEqual(len(months),75)
        self.assertEqual(ordered[0]["date_key"],"20200702")
        self.assertEqual(ordered[-1]["date_key"],"20260918")
        self.assertEqual(ids["reference_sha256"],r.FROZEN_REFERENCE_SHA256)

    def test_plan_deterministic_and_every_contract_dimension(self):
        self.assertEqual(r.validate_full_plan(self.days,self.months,LEDGER_SHA,self.contract),self.days)
        with self.assertRaises(r.Blocked):r.validate_full_plan(list(reversed(self.days)),self.months,LEDGER_SHA,self.contract)
        with self.assertRaises(r.Blocked):r.validate_full_plan(self.days,dict(reversed(list(self.months.items()))),LEDGER_SHA,self.contract)
        for field in self.contract:
            with self.subTest(field=field):
                bad=copy.deepcopy(self.contract)
                value=bad[field]
                bad[field]=False if value is True else value+1 if isinstance(value,int) else "WRONG"
                with self.assertRaises(r.Blocked):r.validate_full_plan(self.days,self.months,LEDGER_SHA,bad)
        mutations=[lambda d:d.pop(),lambda d:d.append(copy.deepcopy(d[0])),
                   lambda d:d[0].update(date_key=""),lambda d:d[0].update(month_id="2026_08"),
                   lambda d:d[1].update(first_offset="1"),lambda d:d[0].update(last_offset="9999999"),
                   lambda d:d[0].update(source_day_bytes="1"),lambda d:d[0].update(rows="0"),
                   lambda d:d[0].update(semantic_sha256="invalid")]
        mutations.extend((lambda d,f=f:d[0].update({f:"1"})) for f in COMPAT_FIELDS)
        for mutate in mutations:
            d=copy.deepcopy(self.days);mutate(d)
            with self.assertRaises(r.Blocked):r.validate_full_plan(d,self.months,LEDGER_SHA,self.contract)
        for field in ("source_size","rows","days","month_id","core_codec_compatible",
                      "p1e_lexical_compatible","seal_integrity","summary_ledger_crosscheck"):
            with self.subTest(month_field=field):
                months=copy.deepcopy(self.months);months["2026_07"][field]="0"
                with self.assertRaises(r.Blocked):r.validate_full_plan(self.days,months,LEDGER_SHA,self.contract)

    def test_multiday_multimonth_zero_then_all_reused_and_two_hashes(self):
        real=r.PinnedSource.hash_all;calls={}
        real_seal_hash=r.FullSourceFinalSeal.hash_fd;seal_hashes=[]
        def counted(pin):
            calls[str(pin.path)]=calls.get(str(pin.path),0)+1
            return real(pin)
        def counted_seal(seal,fd):
            seal_hashes.append(next(key for key,(_,value,_) in seal.handles.items() if value==fd))
            return real_seal_hash(seal,fd)
        with patch.object(r.PinnedSource,"hash_all",counted),patch.object(r.FullSourceFinalSeal,"hash_fd",counted_seal):
            rc,out=self.execute()
        self.assertEqual(rc,0);self.assertEqual(list(calls.values()),[2,2])
        self.assertEqual(seal_hashes,sorted(self.months))
        self.assertIn("DAY=0/3",out);self.assertIn("BUILT_COUNT=3",out)
        self.assertIn("TICKSTORE_FULL_SERIAL_STATUS=PASS",out)
        before={str(p):p.read_bytes() for p in self.dest.glob("WIN@N/*/*.pts2g")}
        calls.clear();seal_hashes.clear()
        with patch.object(r.PinnedSource,"hash_all",counted),patch.object(r.FullSourceFinalSeal,"hash_fd",counted_seal):rc,out=self.execute()
        self.assertEqual(list(calls.values()),[2,2]);self.assertIn("REUSED_COUNT=3",out)
        self.assertEqual(seal_hashes,sorted(self.months))
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.dest.glob("WIN@N/*/*.pts2g")})

    def _assert_seal_handles_closed(self,seals,fds):
        self.assertEqual(len(seals),1)
        self.assertEqual(seals[0].handles,{})
        self.assertIs(seals[0].ready,False)
        for fd in fds:
            with self.assertRaises(OSError):os.fstat(fd)

    def _post_month_change(self,variant,reason):
        first_month=sorted(self.months)[0]
        path=self.source/f"WIN@N_ticks_{first_month}.csv"
        if variant=="replace" and not path.stat().st_ino:
            self.skipTest("File identity is not exposed by this filesystem")
        closed=[];seals=[];fds=[];mutations=[];out=io.StringIO()
        real_exit=r.FullSerialMonth.__exit__;real_seal=r.FullSourceFinalSeal.open_all
        def month_exit(month,kind,value,tb):
            result=real_exit(month,kind,value,tb)
            if kind is None:
                self.assertIsNone(month.pin.file)
                closed.append(month.pin.path)
            return result
        def track_seal(seal):
            seals.append(seal)
            try:return real_seal(seal)
            finally:fds.extend(fd for _,fd,_ in seal.handles.values())
        class Change:
            def hit(inner,point):
                if point!="BEFORE_DAY:20260803":return
                self.assertIn(path,closed)  # The first month passed its clean final hash.
                before=path.stat();raw=path.read_bytes()
                if variant=="replace":
                    replacement=path.with_suffix(".replacement")
                    replacement.write_bytes(raw)
                    os.utime(replacement,ns=(before.st_atime_ns,before.st_mtime_ns))
                    self.assertNotEqual(replacement.stat().st_ino,before.st_ino)
                    os.replace(replacement,path)
                elif variant=="size":
                    path.write_bytes(raw+b"EXTRA")
                    os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
                elif variant=="mtime":
                    os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns+2_000_000_000))
                else:
                    changed=raw.replace(b"100000",b"100005",1)
                    self.assertNotEqual(changed,raw);self.assertEqual(len(changed),len(raw))
                    path.write_bytes(changed)
                    os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
                mutations.append(point)
        with patch.object(r,"_require_full_serial_windows"),patch.object(r.FullSerialMonth,"__exit__",month_exit),\
             patch.object(r.FullSourceFinalSeal,"open_all",track_seal),contextlib.redirect_stdout(out),\
             self.assertRaisesRegex(r.Blocked,reason):
            r._execute_full_serial(self.source,self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,self.codec,Change())
        self.assertEqual(mutations,["BEFORE_DAY:20260803"])
        self.assertEqual(len(closed),len(self.months))  # Execution reached the final seal.
        self.assertIn("FULL_SOURCE_FINAL_SEAL=START",out.getvalue())
        self.assertNotIn("TICKSTORE_FULL_SERIAL_STATUS=PASS",out.getvalue())
        self.assertFalse((self.dest/"TICKSTORE_WRITER.lock").exists())
        self._assert_seal_handles_closed(seals,fds)

    def test_post_month_source_mutation_blocks_global_pass(self):
        # Same size/mtime/inode: only the required third full SHA pass can detect it.
        self._post_month_change("sha","FULL_SOURCE_FINAL_SEAL_SHA256_MISMATCH")

    def test_final_seal_same_content_different_file_identity_blocks(self):
        self._post_month_change("replace","FULL_SOURCE_FINAL_SEAL_FILE_ID_MISMATCH")

    def test_final_seal_size_mismatch_blocks(self):
        self._post_month_change("size","FULL_SOURCE_FINAL_SEAL_SIZE_MISMATCH")

    def test_final_seal_mtime_mismatch_blocks(self):
        self._post_month_change("mtime","FULL_SOURCE_FINAL_SEAL_MTIME_MISMATCH")

    def test_final_seal_open_failure_closes_every_prior_handle(self):
        for fail_index in range(len(self.months)):
            with self.subTest(fail_index=fail_index),tempfile.TemporaryDirectory() as td:
                source,dest,days,months,contract,ids,cert=fixture(Path(td))
                fail_path=source/f"WIN@N_ticks_{sorted(months)[fail_index]}.csv"
                seals=[];fds=[];opened=[];active=[False];out=io.StringIO()
                real_open=r.secure_open_existing_fd;real_seal=r.FullSourceFinalSeal.open_all
                def track_seal(seal):
                    seals.append(seal);active[0]=True
                    try:return real_seal(seal)
                    finally:active[0]=False
                def fail_open(path,*args,**kwargs):
                    if active[0]:
                        opened.append(Path(path))
                        self.assertIs(kwargs.get("source_pin"),True)
                        self.assertIs(kwargs.get("writable"),False)
                        if Path(path)==fail_path:raise r.Blocked("SYNTHETIC_SEAL_OPEN_FAILURE")
                    fd=real_open(path,*args,**kwargs)
                    if active[0]:fds.append(fd)
                    return fd
                with patch.object(r,"_require_full_serial_windows"),patch.object(r.FullSourceFinalSeal,"open_all",track_seal),\
                     patch.object(r,"secure_open_existing_fd",fail_open),contextlib.redirect_stdout(out),\
                     self.assertRaisesRegex(r.Blocked,"SYNTHETIC_SEAL_OPEN_FAILURE"):
                    r._execute_full_serial(source,dest,days,months,LEDGER_SHA,ids,cert,self.codec)
                self.assertEqual(opened,[source/f"WIN@N_ticks_{key}.csv" for key in sorted(months)[:fail_index+1]])
                self.assertEqual(len(fds),fail_index)
                self.assertNotIn("TICKSTORE_FULL_SERIAL_STATUS=PASS",out.getvalue())
                self.assertFalse((dest/"TICKSTORE_WRITER.lock").exists())
                self._assert_seal_handles_closed(seals,fds)

    def test_ctrl_c_during_final_seal_closes_all_handles(self):
        seals=[];fds=[];out=io.StringIO();real_hash=r.FullSourceFinalSeal.hash_fd
        def interrupt(seal,fd):
            if not seals:seals.append(seal)
            fds.append(fd)
            if len(fds)==2:raise KeyboardInterrupt()
            return real_hash(seal,fd)
        with patch.object(r,"_require_full_serial_windows"),patch.object(r.FullSourceFinalSeal,"hash_fd",interrupt),\
             contextlib.redirect_stdout(out):
            rc=r._execute_full_serial(self.source,self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,self.codec)
        self.assertEqual(rc,130);self.assertEqual(len(fds),2)
        self.assertIn("SAFE_STOP=YES",out.getvalue())
        self.assertNotIn("TICKSTORE_FULL_SERIAL_STATUS=PASS",out.getvalue())
        self.assertFalse((self.dest/"TICKSTORE_WRITER.lock").exists())
        self._assert_seal_handles_closed(seals,fds)

    def test_final_seal_handles_live_through_unlock_then_close_before_terminal_print(self):
        seals=[];fds=[];events=[]
        real_seal=r.FullSourceFinalSeal.open_all;real_release=r.release_lock
        real_verify=r.FullSourceFinalSeal.verify_bindings;real_close=r.FullSourceFinalSeal.close
        real_print=builtins.print
        def track_seal(seal):
            seals.append(seal);result=real_seal(seal)
            fds.extend(fd for _,fd,_ in seal.handles.values())
            return result
        def assert_live():
            self.assertEqual(len(seals[0].handles),len(self.months))
            self.assertTrue(seals[0].ready)
            for fd in fds:os.fstat(fd)
        def release(lock):
            assert_live();events.append("release")
            result=real_release(lock)
            assert_live()
            return result
        def verify(seal):
            if not (self.dest/"TICKSTORE_WRITER.lock").exists():
                assert_live();events.append("verify")
            return real_verify(seal)
        def close(seal):
            self.assertEqual(events,["release","verify"])
            assert_live();events.append("close")
            result=real_close(seal)
            self._assert_seal_handles_closed(seals,fds)
            return result
        def capture(*args,**kwargs):
            if args and args[0]=="TICKSTORE_FULL_SERIAL_STATUS=PASS":
                self._assert_seal_handles_closed(seals,fds)
                events.append("terminal")
                self.assertFalse((self.dest/"TICKSTORE_WRITER.lock").exists())
            return real_print(*args,**kwargs)
        with patch.object(r.FullSourceFinalSeal,"open_all",track_seal),patch.object(r,"release_lock",release),\
             patch.object(r.FullSourceFinalSeal,"verify_bindings",verify),\
             patch.object(r.FullSourceFinalSeal,"close",close),patch.object(builtins,"print",capture):rc,out=self.execute()
        self.assertEqual(rc,0);self.assertEqual(events,["release","verify","close","terminal"])
        self._assert_seal_handles_closed(seals,fds)

    def test_final_seal_close_failure_never_emits_global_pass(self):
        seals=[];fds=[];close_attempts=[];out=io.StringIO();injected=[False]
        real_seal=r.FullSourceFinalSeal.open_all;real_os_close=r.os.close
        def track_seal(seal):
            seals.append(seal);result=real_seal(seal)
            fds.extend(fd for _,fd,_ in seal.handles.values())
            return result
        def fail_one_final_seal_close(fd):
            if fds and fd==fds[0]:
                close_attempts.append(fd)
                if not injected[0]:
                    injected[0]=True
                    raise OSError("synthetic final-seal close failure")
            return real_os_close(fd)
        with patch.object(r,"_require_full_serial_windows"),\
             patch.object(r.FullSourceFinalSeal,"open_all",track_seal),\
             patch.object(r.os,"close",fail_one_final_seal_close),contextlib.redirect_stdout(out),\
             self.assertRaisesRegex(r.Blocked,"FULL_SOURCE_FINAL_SEAL_CLOSE_FAILED"):
            r._execute_full_serial(self.source,self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,self.codec)
        self.assertTrue(injected[0])
        self.assertEqual(close_attempts,[fds[0],fds[0]])  # Explicit close + residual finally cleanup.
        self.assertNotIn("TICKSTORE_FULL_SERIAL_STATUS=PASS",out.getvalue())
        self.assertFalse((self.dest/"TICKSTORE_WRITER.lock").exists())
        self._assert_seal_handles_closed(seals,fds)

    def _late_inventory_change(self,manifest_partial=False):
        self.execute()
        real_inventory=r._full_artifact_inventory;calls=[];out=io.StringIO()
        path=(r.manifest_path(self.dest).with_suffix(".json.partial") if manifest_partial
              else self.dest/"LATE_EXTRA.pts2g")
        seals=[];fds=[];real_seal=r.FullSourceFinalSeal.open_all
        def track_seal(seal):
            seals.append(seal);result=real_seal(seal)
            fds.extend(fd for _,fd,_ in seal.handles.values())
            return result
        def late(dest,expected):
            calls.append(len(calls)+1)
            self.assertTrue((dest/"TICKSTORE_WRITER.lock").exists())
            result=real_inventory(dest,expected)
            if len(calls)==1:path.write_bytes(b"INJECTED_AFTER_FIRST_INVENTORY")
            return result
        with patch.object(r,"_require_full_serial_windows"),patch.object(r,"_full_artifact_inventory",late),\
             patch.object(r.FullSourceFinalSeal,"open_all",track_seal),contextlib.redirect_stdout(out),self.assertRaises(r.Blocked):
            r._execute_full_serial(self.source,self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,self.codec)
        self.assertEqual(calls,[1,2]);self.assertTrue(path.exists())
        self.assertNotIn("TICKSTORE_FULL_SERIAL_STATUS=PASS",out.getvalue())
        self.assertFalse((self.dest/"TICKSTORE_WRITER.lock").exists())
        self._assert_seal_handles_closed(seals,fds)

    def test_late_artifact_after_first_inventory_blocks(self):
        self._late_inventory_change()

    def test_late_manifest_partial_after_first_inventory_blocks(self):
        self._late_inventory_change(manifest_partial=True)

    def test_interrupt_between_days_some_reused_restart(self):
        class Stop:
            def hit(self,point):
                if point=="AFTER_DAY:20260730": raise KeyboardInterrupt()
        rc,out=self.execute(Stop())
        self.assertEqual(rc,130);self.assertIn("SAFE_STOP=YES",out);self.assertNotIn("STATUS=PASS",out)
        self.assertFalse((self.dest/"TICKSTORE_WRITER.lock").exists())
        first=r._full_day_paths(self.dest,self.days[0])["container"].read_bytes()
        rc,out=self.execute()
        self.assertIn("REUSED_COUNT=1",out);self.assertIn("BUILT_COUNT=2",out)
        self.assertEqual(first,r._full_day_paths(self.dest,self.days[0])["container"].read_bytes())

    def test_interrupt_inside_day_journal_resume(self):
        class Stop:
            def hit(self,point):
                if point=="AFTER_GROUP_0_JOURNAL": raise KeyboardInterrupt()
        rc,out=self.execute(Stop())
        self.assertEqual(rc,130);self.assertNotIn("STATUS=PASS",out)
        pp=r._full_day_paths(self.dest,self.days[0])
        self.assertTrue(pp["journal"].exists());self.assertFalse(pp["container"].exists())
        rc,out=self.execute();self.assertEqual(rc,0);self.assertIn("RESUMED_COUNT=1",out)

    def test_first_middle_last_failure_preserves_prior_days(self):
        for index in range(3):
            with self.subTest(index=index),tempfile.TemporaryDirectory() as td:
                source,dest,days,months,contract,ids,cert=fixture(Path(td))
                class Fail:
                    current=None
                    def hit(self,point):
                        if point.startswith("BEFORE_DAY:"):self.current=point.split(":",1)[1]
                        if self.current==days[index]["date_key"] and point=="AFTER_GROUP_0_JOURNAL":
                            raise r.Blocked("SYNTHETIC_FAILURE")
                out=io.StringIO()
                with patch.object(r,"_require_full_serial_windows"),contextlib.redirect_stdout(out),self.assertRaises(r.Blocked):
                    r._execute_full_serial(source,dest,days,months,LEDGER_SHA,ids,cert,self.codec,Fail())
                self.assertNotIn("STATUS=PASS",out.getvalue());self.assertIn("FAILED_COUNT=1",out.getvalue())
                self.assertFalse((dest/"TICKSTORE_WRITER.lock").exists())
                for j,c in enumerate(days): self.assertEqual(r._full_day_paths(dest,c)["container"].exists(),j<index)
                self.assertTrue(r._full_day_paths(dest,days[index])["journal"].exists())

    def test_invocation_lock_blocks_between_days(self):
        observed=[];dest=self.dest
        class Probe:
            def hit(inner,point):
                if point.startswith("AFTER_DAY:"):
                    with self.assertRaises(r.Blocked):r.acquire_lock(dest)
                    observed.append(point)
        self.execute(Probe());self.assertEqual(len(observed),3)
        lock=r.acquire_lock(self.dest)
        try:
            with self.assertRaises(r.Blocked):self.execute()
            self.assertTrue(lock.exists())
        finally:r.release_lock(lock)

    def test_sigint_at_acquire_and_release_restores_handler_and_removes_lock(self):
        for operation in ("acquire_lock","release_lock"):
            with self.subTest(operation=operation),tempfile.TemporaryDirectory() as td:
                source,dest,days,months,contract,ids,cert=fixture(Path(td));out=io.StringIO()
                real=getattr(r,operation);previous=signal.getsignal(signal.SIGINT)
                def interrupted(*args):
                    result=real(*args)
                    # Deliver through the installed handler at the otherwise unsafe boundary.
                    signal.getsignal(signal.SIGINT)(signal.SIGINT,None)
                    return result
                with patch.object(r,"_require_full_serial_windows"),patch.object(r,operation,interrupted),contextlib.redirect_stdout(out):
                    rc=r._execute_full_serial(source,dest,days,months,LEDGER_SHA,ids,cert,self.codec)
                self.assertEqual(rc,130);self.assertIn("SAFE_STOP=YES",out.getvalue())
                self.assertNotIn("STATUS=PASS",out.getvalue())
                self.assertFalse((dest/"TICKSTORE_WRITER.lock").exists())
                self.assertIs(signal.getsignal(signal.SIGINT),previous)

    def test_r8_day_wrapper_retains_full_verification_and_reuse(self):
        real=r.PinnedSource.hash_all;calls=[];out=io.StringIO()
        def counted(pin):calls.append(pin.path);return real(pin)
        with patch.object(r.ref,"require_zstd",return_value=self.codec),\
             patch.object(r,"load_ledgers",return_value=(self.days,self.months,LEDGER_SHA)),\
             patch.object(r,"file_ids",return_value=self.ids),patch.object(r.PinnedSource,"hash_all",counted),\
             contextlib.redirect_stdout(out):
            rc=r.run_one_day(self.source,self.dest,Path("synthetic-ledger"),self.days[0]["date_key"],None)
        self.assertEqual(rc,0);self.assertGreater(len(calls),2)
        self.assertIn("TICKSTORE_DAY_RESULT=BUILT",out.getvalue())
        out=io.StringIO()
        with patch.object(r.ref,"require_zstd",return_value=self.codec),\
             patch.object(r,"load_ledgers",return_value=(self.days,self.months,LEDGER_SHA)),\
             patch.object(r,"file_ids",return_value=self.ids),contextlib.redirect_stdout(out):
            r.run_one_day(self.source,self.dest,Path("synthetic-ledger"),self.days[0]["date_key"],None)
        self.assertIn("TICKSTORE_DAY_RESULT=REUSED",out.getvalue())

    def test_real_extra_after_last_day_blocks_global_pass(self):
        dest=self.dest
        class Extra:
            def hit(self,point):
                if point=="AFTER_DAY:20260803": (dest/"20990101.pts2g").write_bytes(b"EXTRA")
        out=io.StringIO()
        with patch.object(r,"_require_full_serial_windows"),contextlib.redirect_stdout(out),self.assertRaises(r.Blocked):
            r._execute_full_serial(self.source,self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,self.codec,Extra())
        self.assertNotIn("STATUS=PASS",out.getvalue())
        self.assertEqual(len(list(self.dest.glob("WIN@N/*/*.pts2g"))),3)

    def test_release_failure_and_reconciliation_failure_never_pass(self):
        for operation in ("release_lock","reconcile_full_readonly"):
            with self.subTest(operation=operation),tempfile.TemporaryDirectory() as td:
                source,dest,days,months,contract,ids,cert=fixture(Path(td));out=io.StringIO()
                with patch.object(r,"_require_full_serial_windows"),contextlib.redirect_stdout(out),\
                     patch.object(r,operation,side_effect=r.Blocked("SYNTHETIC_FAILURE")),self.assertRaises(r.Blocked):
                    r._execute_full_serial(source,dest,days,months,LEDGER_SHA,ids,cert,self.codec)
                self.assertNotIn("STATUS=PASS",out.getvalue())

    def test_manifest_missing_extra_duplicate_and_wrong_date(self):
        self.execute();path=r.manifest_path(self.dest);original=path.read_bytes();m=json.loads(original)
        variants=[]
        bad=copy.deepcopy(m);bad["records"].pop(self.days[0]["date_key"]);variants.append(json.dumps(bad).encode())
        bad=copy.deepcopy(m);bad["records"]["20990101"]={"date_key":"20990101"};variants.append(json.dumps(bad).encode())
        bad=copy.deepcopy(m);bad["records"][self.days[0]["date_key"]]["date_key"]="20200101";variants.append(json.dumps(bad).encode())
        key=self.days[0]["date_key"];rec=json.dumps(m["records"][key])
        variants.append(('{"schema":"'+r.MANIFEST_SCHEMA+'","records":{"'+key+'":'+rec+',"'+key+'":'+rec+'}}').encode())
        for raw in variants:
            path.write_bytes(raw)
            with self.assertRaises(r.Blocked):self.reconcile()
        path.unlink()
        with self.assertRaises(r.Blocked):self.reconcile()
        path.write_bytes(original)

    def test_extra_container_commit_and_transients_readonly(self):
        self.execute()
        for name in ("20990101.pts2g","20990101.commit.json","20990101.journal.json",
                     "20260730.pts2g.partial","20260730.commit.json.partial.stage"):
            path=self.dest/"WIN@N"/"2026_07"/name;path.write_bytes(b"SYNTHETIC_EXTRA")
            before={str(p):p.read_bytes() for p in self.dest.glob("WIN@N/*/*") if p.is_file()}
            with self.assertRaises(r.Blocked):self.reconcile()
            self.assertEqual(before,{str(p):p.read_bytes() for p in self.dest.glob("WIN@N/*/*") if p.is_file()})
            path.unlink()

    def test_missing_altered_artifact_and_oracle_rejected(self):
        self.execute();pp=r._full_day_paths(self.dest,self.days[0])
        for name in ("container","commit"):
            path=pp[name];raw=path.read_bytes()
            path.unlink()
            with self.assertRaises(r.Blocked):self.reconcile()
            path.write_bytes(raw+b"altered")
            with self.assertRaises(r.Blocked):self.reconcile()
            path.write_bytes(raw)
        obj=json.loads(pp["commit"].read_bytes());obj["oracle"]["codec_id"]="WRONG"
        pp["commit"].write_text(json.dumps(obj))
        with self.assertRaises(r.Blocked):self.reconcile()

    def test_final_reconciliation_has_no_mutation_or_source_hash(self):
        self.execute()
        identities={}
        for key,m in self.months.items():
            with r.PinnedSource(self.source/f"WIN@N_ticks_{key}.csv",int(m["source_size"]),m["source_sha256"]) as pin:
                identities[key]=dict(pin.identity)
        with contextlib.ExitStack() as stack:
            for name in ("paths_for_day","safe_unlink_regular","secure_replace","secure_create_new_fd",
                         "update_manifest","atomic_write_json"):
                stack.enter_context(patch.object(r,name,side_effect=AssertionError("reconciliation must be read-only")))
            stack.enter_context(patch.object(r.PinnedSource,"hash_all",side_effect=AssertionError("no final source rehash")))
            r.reconcile_full_readonly(self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,identities,self.codec)

    def test_publication_boundaries_check_binding(self):
        real=r.FullSerialSourceView.verify_path_binding;seen=[]
        def check(view):
            seen.append(view.pinned.path.name)
            return real(view)
        with patch.object(r.FullSerialSourceView,"verify_path_binding",check):self.execute()
        self.assertGreaterEqual(len(seen),9*len(self.days))
        for point in ("AFTER_COMMIT_PARTIAL","AFTER_CONTAINER_RENAME",
                      "AFTER_COMMIT_RENAME_BEFORE_MANIFEST","AFTER_MANIFEST_BEFORE_JOURNAL_CLEANUP"):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as td:
                source,dest,days,months,contract,ids,cert=fixture(Path(td));changed=[False]
                class Fault:
                    def hit(self,p):
                        if p==point: changed[0]=True
                def fail_binding(view):
                    if changed[0]: raise r.Blocked("SYNTHETIC_BINDING_CHANGED")
                    return real(view)
                with patch.object(r,"_require_full_serial_windows"),\
                     patch.object(r.FullSerialSourceView,"verify_path_binding",fail_binding),self.assertRaises(r.Blocked):
                    r._execute_full_serial(source,dest,days,months,LEDGER_SHA,ids,cert,self.codec,Fault())
                self.assertTrue(r._full_day_paths(dest,days[0])["journal"].exists())

    def test_clean_month_final_hash_failure_no_global_pass(self):
        real=r.PinnedSource.hash_all;calls=[0];out=io.StringIO()
        def changed(pin):
            calls[0]+=1
            return "0"*64 if calls[0]==2 else real(pin)
        with patch.object(r.PinnedSource,"hash_all",changed),patch.object(r,"_require_full_serial_windows"),\
             contextlib.redirect_stdout(out),self.assertRaises(r.Blocked):
            r._execute_full_serial(self.source,self.dest,self.days,self.months,LEDGER_SHA,self.ids,self.cert,self.codec)
        self.assertNotIn("STATUS=PASS",out.getvalue());self.assertFalse((self.dest/"TICKSTORE_WRITER.lock").exists())

    @unittest.skipUnless(os.name=="nt","Actual Windows sharing proof requires Windows")
    def test_windows_source_mutation_while_pin_open_is_denied(self):
        key=sorted(self.months)[0];path=self.source/f"WIN@N_ticks_{key}.csv";original=path.read_bytes()
        with r.FullSerialMonth(path,self.months[key]) as view:
            with self.assertRaises(OSError):
                with path.open("r+b") as f:f.write(b"X")
            with self.assertRaises(OSError):path.unlink()
            view.verify_full()
        self.assertEqual(path.read_bytes(),original)

    def test_release_identity_capability_and_legacy_full_history_block(self):
        self.assertEqual(r.RUNNER_SCHEMA,"TICKSTORE_SERIAL_RUNNER_V001R9_FULL_SERIAL_RELEASE_RC1")
        self.assertIs(r.FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE,True)
        self.assertIs(r.FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE,False)
        with patch("sys.argv",["runner","--ledger-zip","synthetic-ledger.zip","--full-history"]),\
             self.assertRaisesRegex(r.Blocked,"FULL_HISTORY_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE"):
            r.main()

    def test_full_serial_gate_syntax_blocks_before_any_io_or_dispatch(self):
        argv_cases=(
            (["runner","--mode","FULL_SERIAL"],"FULL_OWNER_GATE_REQUIRED"),
            (["runner","--mode","FULL_SERIAL","--full-gate-file","gate.json"],
             "FULL_OWNER_GATE_TRUSTED_SHA256_REQUIRED"),
            (["runner","--mode","FULL_SERIAL","--full-gate-file","gate.json",
              "--full-gate-sha256","A"*63],"FULL_OWNER_GATE_TRUSTED_SHA256_REQUIRED"),
            (["runner","--mode","FULL_SERIAL","--full-gate-file","gate.json",
              "--full-gate-sha256","G"*64],"FULL_OWNER_GATE_TRUSTED_SHA256_REQUIRED"),
        )
        with patch.object(r,"_require_full_serial_windows",side_effect=AssertionError("runtime access")),\
             patch.object(r,"full_release_materials",side_effect=AssertionError("release file access")),\
             patch.object(r,"load_ledgers",side_effect=AssertionError("ledger access")),\
             patch.object(r,"full_gate_bindings",side_effect=AssertionError("path/volume access")),\
             patch.object(r,"_execute_full_serial",side_effect=AssertionError("dispatch")) as dispatch:
            for argv,reason in argv_cases:
                with self.subTest(argv=argv),patch("sys.argv",argv),self.assertRaisesRegex(r.Blocked,reason):
                    r.main()
            dispatch.assert_not_called()

    def test_release_owner_gate_controls_dispatch_for_every_binding(self):
        valid=self.release_gate_bindings();valid_raw=r.stable_json(valid)
        valid_digest=r.sha256_bytes(valid_raw)

        dispatch=Mock(return_value="AUTHENTICATED_ROUTE_SENTINEL")
        result=self.call_release_route(valid,valid_digest,dispatch)
        self.assertEqual(result,"AUTHENTICATED_ROUTE_SENTINEL")
        dispatch.assert_called_once()

        invalid=[]
        false_gate=copy.deepcopy(valid);false_gate["authorized"]=False
        invalid.append(("authorized_false",false_gate,r.sha256_bytes(r.stable_json(false_gate))))
        invalid.append(("incorrect_digest",valid,"0"*64))
        tampered=copy.deepcopy(valid);tampered["source_root"]="tampered"
        invalid.append(("tampered_after_trusted_digest",tampered,valid_digest))
        missing=copy.deepcopy(valid);missing.pop("scratch_volume")
        invalid.append(("missing_field",missing,r.sha256_bytes(r.stable_json(missing))))
        extra=copy.deepcopy(valid);extra["unexpected"]="field"
        invalid.append(("extra_field",extra,r.sha256_bytes(r.stable_json(extra))))
        for key in valid:
            if key=="authorized":continue
            wrong=copy.deepcopy(valid)
            wrong[key]={"wrong":"binding"} if key.endswith("_volume") else "WRONG"
            invalid.append(("wrong_binding_"+key,wrong,r.sha256_bytes(r.stable_json(wrong))))

        for name,gate,digest in invalid:
            with self.subTest(name=name):
                blocked_dispatch=Mock(return_value="MUST_NOT_REACH")
                with self.assertRaises(r.Blocked):
                    self.call_release_route(gate,digest,blocked_dispatch)
                blocked_dispatch.assert_not_called()

    def test_package_contains_no_authorized_owner_gate(self):
        template=json.loads((BASE/"FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json").read_text(encoding="utf-8"))
        self.assertIs(template["authorized"],False)
        self.assertEqual(template["runner_schema"],r.RUNNER_SCHEMA)
        for path in BASE.rglob("*.json"):
            obj=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj,dict):self.assertIsNot(obj.get("authorized"),True,path.name)

    def test_owner_gate_every_binding_and_malformed_tampered_absent(self):
        # Authorized objects exist only in memory; never write a true gate file.
        expected={"schema":r.FULL_OWNER_GATE_SCHEMA,"authorized":True,"runner_schema":r.RUNNER_SCHEMA,
                  "runner_sha256":"1"*64,"reference_sha256":"2"*64,"full_spec_sha256":"3"*64,
                  "full_plan_sha256":"4"*64,"full_plan_contract_sha256":"5"*64,
                  "ledger_sha256":"6"*64,"gate_b_certificate_sha256":"7"*64}
        for name in ("source","dest","scratch"):
            expected[name+"_root"]=name
            expected[name+"_volume"]={"root":"D:\\","serial":"12345678","filesystem":"NTFS"}
        def validate(obj,claimed=None):
            raw=r.stable_json(obj)
            with patch.object(r,"secure_read_all",return_value=raw):
                return r.validate_full_owner_gate(Path("memory-only.json"),expected,claimed or r.sha256_bytes(raw))
        self.assertEqual(validate(expected),expected)
        for key in expected:
            with self.subTest(key=key):
                bad=copy.deepcopy(expected)
                bad[key]=False if key=="authorized" else {"wrong":"volume"} if key.endswith("_volume") else "WRONG"
                with self.assertRaises(r.Blocked):validate(bad)
        with self.assertRaises(r.Blocked):validate(expected,"0"*64)
        with self.assertRaises(r.Blocked):r.validate_full_owner_gate(None,expected,"0"*64)
        with self.assertRaises(r.Blocked):r.validate_full_owner_gate(self.root/"absent.json",expected,"0"*64)
        with self.assertRaises(r.Blocked):r.validate_full_owner_gate(Path("unused"),expected,None)
        for raw in (b"[",b"[]",b'{"authorized":true,"authorized":false}',b'{"x":NaN}'):
            with patch.object(r,"secure_read_all",return_value=raw),self.assertRaises(r.Blocked):
                r.validate_full_owner_gate(Path("memory-only"),expected,r.sha256_bytes(raw))

    def test_seals_detect_any_changed_contract_or_certificate(self):
        for filename,sha in (("TICKSTORE_FULL_PLAN_CONTRACT_V001.json",r.FULL_PLAN_CONTRACT_SHA256),
                             ("TICKSTORE_GATE_B_R8_FINAL_CERTIFICATE_20260924.json",r.GATE_B_CERTIFICATE_SHA256)):
            raw=(BASE/filename).read_bytes()
            with patch.object(r,"secure_read_all",return_value=raw+b" "),self.assertRaises(r.Blocked):
                r._sealed_full_json(Path(filename),sha)

    def test_gate_bindings_use_current_paths_volumes_and_reject_overlap(self):
        scratch=self.root/"scratch";scratch.mkdir()
        def volume(path):return {"root":str(path.anchor),"serial":path.name,"filesystem":"NTFS"}
        with patch.object(r,"windows_volume_identity",side_effect=volume):
            expected=r.full_gate_bindings(self.source,self.dest,scratch,self.ids,self.contract)
            template=json.loads((BASE/"FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json").read_text(encoding="utf-8"))
            self.assertEqual(set(template),set(expected))
            self.assertIs(template["authorized"],False)
            self.assertEqual(template["schema"],expected["schema"])
            self.assertEqual(template["runner_schema"],expected["runner_schema"])
            for key in ("runner_sha256","full_spec_sha256","source_root","dest_root","scratch_root",
                        "source_volume","dest_volume","scratch_volume"):
                self.assertIsNone(template[key])
            for key,path in (("source",self.source),("dest",self.dest),("scratch",scratch)):
                self.assertEqual(expected[key+"_root"],r._norm_binding_path(path))
                self.assertEqual(expected[key+"_volume"],volume(path))
            self.assertEqual(expected["runner_schema"],r.RUNNER_SCHEMA)
            self.assertEqual(expected["gate_b_certificate_sha256"],r.GATE_B_CERTIFICATE_SHA256)
            with self.assertRaisesRegex(r.Blocked,"ROOTS_OVERLAP"):
                r.full_gate_bindings(self.source,self.dest,self.source,self.ids,self.contract)

    def test_closed_view_cannot_authorize_publication(self):
        key=sorted(self.months)[0];path=self.source/f"WIN@N_ticks_{key}.csv"
        with patch.object(r,"_require_full_serial_windows"):
            with r.FullSerialMonth(path,self.months[key]) as view:view.verify_full()
        with self.assertRaisesRegex(r.Blocked,"PIN_CLOSED"):view.verify_full()

    def test_no_autocpu_or_csv_deletion_routes(self):
        import static_runner_preaudit_r9
        with contextlib.redirect_stdout(io.StringIO()):static_runner_preaudit_r9.scan()


class CertifiedCompatibilityTests(unittest.TestCase):
    def test_two_synthetic_certified_pairs_reused_and_alterations_rejected(self):
        # Miniature artifacts with the actual R8 identity; synthetic certificate hashes
        # exist only in memory. The production certificate file is never modified.
        for key in ("20260731","20211022"):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as td:
                source,dest,days,months,contract,ids,cert=fixture(Path(td),(key,))
                c=days[0];m=months[c["month_id"]];codec=SyntheticCodec()
                with r.PinnedSource(r.source_for(source,c),int(m["source_size"]),m["source_sha256"]) as pin:
                    oracle=r.make_oracle(c,m,dict(pin.identity),LEDGER_SHA,cert["r8_ids"])
                    lock=r.acquire_lock(dest)
                    try:r._run_day_already_locked(pin,c,oracle,dest,codec,r.FaultInjector(None))
                    finally:r.release_lock(lock)
                    pp=r._full_day_paths(dest,c);label="low" if key=="20260731" else "high"
                    cert[label]={"date_key":key,"container_sha256":r.sha256_file(pp["container"]),
                                 "commit_sha256":r.sha256_file(pp["commit"]),"container_bytes":pp["container"].stat().st_size,
                                 **{k:oracle[k] for k in ("rows","source_day_bytes","semantic_sha256","offset_sha256")}}
                    rec=r.load_manifest(dest)["records"][key]
                    def check():return r.validate_certified_r8_day(pp,c,m,dict(pin.identity),LEDGER_SHA,cert,dest,codec,rec)
                    self.assertEqual(check(),"REUSED")
                    for name in ("container","commit"):
                        raw=pp[name].read_bytes();pp[name].write_bytes(raw+b"changed")
                        with self.assertRaises(r.Blocked):check()
                        pp[name].write_bytes(raw)
                    for name in ("partial","journal","journal_atomic","commit_partial","commit_stage"):
                        pp[name].write_bytes(b"transient")
                        with self.assertRaises(r.Blocked):check()
                        pp[name].unlink()
                    bad=copy.deepcopy(c);bad["date_key"]="20260730"
                    with self.assertRaisesRegex(r.Blocked,"NOT_CERTIFIED"):
                        r.validate_certified_r8_day(pp,bad,m,dict(pin.identity),LEDGER_SHA,cert,dest,codec,rec)
                    saved=copy.deepcopy(rec);rec["codec_id"]="WRONG"
                    with self.assertRaises(r.Blocked):check()
                    rec.clear();rec.update(saved)
                with patch.object(r,"_require_full_serial_windows"),contextlib.redirect_stdout(io.StringIO()) as output:
                    rc=r._execute_full_serial(source,dest,days,months,LEDGER_SHA,ids,cert,codec)
                self.assertEqual(rc,0);self.assertIn("REUSED_COUNT=1",output.getvalue())

    def test_arbitrary_third_r8_day_rejected_by_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            source,dest,days,months,contract,ids,cert=fixture(Path(td),("20260730",))
            c=days[0];m=months[c["month_id"]];codec=SyntheticCodec()
            with r.PinnedSource(r.source_for(source,c),int(m["source_size"]),m["source_sha256"]) as pin:
                oracle=r.make_oracle(c,m,dict(pin.identity),LEDGER_SHA,cert["r8_ids"])
                lock=r.acquire_lock(dest)
                try:r._run_day_already_locked(pin,c,oracle,dest,codec,r.FaultInjector(None))
                finally:r.release_lock(lock)
            with patch.object(r,"_require_full_serial_windows"),self.assertRaisesRegex(r.Blocked,"NOT_CERTIFIED"):
                r._execute_full_serial(source,dest,days,months,LEDGER_SHA,ids,cert,codec)


if __name__=="__main__":unittest.main(verbosity=2)
