"""Small local fixtures only. No production paths, snapshots, or historical CSV reads."""
import ast
import contextlib
import copy
import csv
import io
import inspect
import itertools
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import tickstore_publisher_recovery_v004 as r

HERE=Path(__file__).resolve().parent
GEN={"snapshot_id":"fixture-snapshot-1","snapshot_set_id":"fixture-set-1",
     "provider_id":"fixture-provider","device_object":"fixture-shadow","volume_identity":"fixture-volume"}


def s0_fixture():
    days={};objects=[]
    for i in range(1399):
        key=f"{20000000+i:08d}"
        namespace=r.NAMESPACES[0]
        entry={"namespace":namespace,"contract":{"date_key":key,"proof":"synthetic-semantic-fixture"}}
        for kind,suffix in (("journal","journal.json"),("partial","pts2g.partial")):
            obj={"date_key":key,"kind":kind,"namespace":namespace,"path":f"{namespace}/fixture/{key}/{key}.{suffix}",
                 "sha256":r.sha((key+kind).encode()),"bytes":32,"reparse":False,"links":1}
            if kind=="journal":obj["contract"]=entry["contract"]
            entry[kind]={k:obj[k] for k in ("path","sha256","bytes")};objects.append(obj)
        days[key]=entry
    return {"days":days},objects


class DomainTests(unittest.TestCase):
    def test_candidate_remains_blocked_before_any_io(self):
        with patch.object(r,"Win32Store",side_effect=AssertionError("No runtime I/O admitted")):
            with self.assertRaisesRegex(r.Blocked,"REQUIRED_SUITE_AND_IMPLEMENTATION_COMPLETENESS_GATE"):
                r.dispatch_bootstrap({})
            with self.assertRaisesRegex(r.Blocked,"REQUIRED_SUITE_AND_IMPLEMENTATION_COMPLETENESS_GATE"):
                r.main()

    def test_frozen_bytes_and_pure_serializer(self):
        core=r.frozen_core()
        self.assertEqual(core.stable_json({"b":1,"a":"é"}),r.stable({"a":"é","b":1}))
        self.assertEqual(core.EXPECTED_P4A_LEDGER_SHA256,r.LEDGER_SHA)

    def test_json_duplicate_nonfinite_and_determinism(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}'):
            with self.subTest(raw=raw),self.assertRaises(r.Blocked):r.parse(raw)
        self.assertEqual(r.json_bytes({"b":2,"a":1}),b'{"a":1,"b":2}\n')

    def test_all_eight_physical_states(self):
        valid={(0,0,0):"PENDING",(1,0,0):"CONTAINER_ONLY",(1,1,0):"CONTAINER_COMMIT",(1,1,1):"TERMINAL"}
        for bits in itertools.product((0,1),repeat=3):
            if bits in valid:self.assertEqual(r.classify_day(*bits),valid[bits])
            else:
                with self.assertRaises(r.Blocked):r.classify_day(*bits)

    def test_at_most_one_partial_and_c0_terminal(self):
        r.classify_set({"a":"TERMINAL","b":"CONTAINER_ONLY"},{"a"})
        for states in ({"a":"PENDING"},{"a":"TERMINAL","b":"CONTAINER_ONLY","c":"CONTAINER_COMMIT"}):
            with self.assertRaises(r.Blocked):r.classify_set(states,{"a"})

    def test_manifest_absent_zero_one_two_candidates(self):
        expected=r.manifest_bytes({"x":{"date_key":"x"}},123)
        self.assertEqual(r.manifest_candidate([("pre",expected),("bad",b"bad")],expected),"pre")
        for candidates in ([],[("pre",expected),("post",expected)]):
            with self.assertRaises(r.Blocked):r.manifest_candidate(candidates,expected)

    def test_manifest_rederivation_preserves_timestamp(self):
        records={"x":{"date_key":"x"}};raw=r.manifest_bytes(records,123)
        self.assertEqual(r.rederive_manifest(raw,records),raw)
        with self.assertRaises(r.Blocked):r.rederive_manifest(raw,{})
        with self.assertRaises(r.Blocked):r.manifest_bytes(records,None)

    def test_all_14_corrected_safe_stop_cases(self):
        with (HERE/"baseline"/"06_SAFE_STOP_DECISION_TABLE_V004R1R1.csv").open(newline="",encoding="utf-8") as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),14)
        for row in rows:
            with self.subTest(case=row["case"]):
                values={key:int(value) for key,value in row.items() if key not in ("case","expected_safe_stop")}
                canonical={"pass":bool(values.pop("canonical_gate_pass")),"generation":GEN}
                same=values.pop("same_snapshot_generation")
                values["generation"]=GEN if same else {**GEN,"snapshot_id":"different"}
                values["pass"]=all(values[k]==0 for k in ("missing","divergent","duplicate_date","orphan_journal","orphan_partial","unexpected_grammar","reparse","hardlink")) and values["cert_match"]==1399
                self.assertEqual(r.safe_stop_decision(canonical,values),row["expected_safe_stop"])

    def test_safe_stop_rejects_missing_typed_counters(self):
        cert,objects=s0_fixture();good=r.s0_inventory_gate(cert,objects,GEN)
        for key in ("missing","cert_match","required_s0"):
            bad=copy.deepcopy(good);bad[key]=False
            self.assertEqual(r.safe_stop_decision({"pass":True,"generation":GEN},bad),"NO")

    def test_s0_complete_and_deterministic_inventory(self):
        cert,objects=s0_fixture()
        forward=r.s0_inventory_gate(cert,objects,GEN)
        reverse=r.s0_inventory_gate(cert,list(reversed(objects)),GEN)
        self.assertEqual(forward,reverse);self.assertTrue(forward["pass"])
        self.assertEqual(r.safe_stop_decision({"pass":True,"generation":GEN},forward),"YES")

    def test_s0_missing_orphans_include_terminal_R(self):
        cert,objects=s0_fixture()
        for index,orphan in ((0,"orphan_partial"),(1,"orphan_journal")):
            changed=copy.deepcopy(objects);changed.pop(index)
            result=r.s0_inventory_gate(cert,changed,GEN)
            self.assertEqual(result[orphan],1);self.assertEqual(result["missing"],1)
            self.assertFalse(result["pass"])

    def test_s0_mutation_swap_duplicate_extra_links(self):
        cert,objects=s0_fixture()
        for mutation in ("sha256","contract","path","namespace","duplicate","extra","reparse","links","swap"):
            with self.subTest(mutation=mutation):
                changed=copy.deepcopy(objects)
                if mutation=="duplicate":changed.append(copy.deepcopy(changed[0]))
                elif mutation=="extra":
                    extra=copy.deepcopy(changed[0]);extra["date_key"]="99999999";extra["path"]="unexpected";changed.append(extra)
                elif mutation=="swap":changed[0]["contract"],changed[2]["contract"]=changed[2]["contract"],changed[0]["contract"]
                else:changed[0][mutation]=2 if mutation=="links" else True if mutation=="reparse" else "changed"
                self.assertFalse(r.s0_inventory_gate(cert,changed,GEN)["pass"])

    def test_snapshot_fixture_is_immutable_but_resume_detects_live_mutation(self):
        cert,live=s0_fixture();shadow=copy.deepcopy(live)
        live[1]["sha256"]="0"*64
        self.assertTrue(r.s0_inventory_gate(cert,shadow,GEN)["pass"])
        self.assertFalse(r.s0_inventory_gate(cert,live,GEN)["pass"])

    def test_generation_binding_every_field(self):
        cert,objects=s0_fixture();good=r.s0_inventory_gate(cert,objects,GEN)
        for key in GEN:
            other={**GEN,key:"different"}
            self.assertEqual(r.safe_stop_decision({"pass":True,"generation":other},good),"NO")

    def test_watchdog_healthy_over_180_seconds(self):
        watch=r.Watchdog(0,7200)
        for now in range(0,301,5):watch.observe(now,{"bytes":0})
        self.assertEqual(watch.check(300),"NO_PROGRESS_DIAGNOSTIC")
        watch.observe(305,{"bytes":10});self.assertEqual(watch.check(305),"HEALTHY")

    def test_watchdog_heartbeat_spam_cannot_extend_deadline(self):
        watch=r.Watchdog(0,900)
        for now in range(0,1001,5):watch.observe(now,{"bytes":0})
        with self.assertRaisesRegex(r.Blocked,"DEADLINE"):watch.check(1000)

    def test_watchdog_liveness_io_and_monotonic(self):
        with self.assertRaisesRegex(r.Blocked,"LIVENESS"):r.Watchdog(0,900).check(46)
        with self.assertRaisesRegex(r.Blocked,"IO_ERROR"):r.Watchdog(0,900).check(5,io_error=True)
        watch=r.Watchdog(0,900);watch.observe(1,{"bytes":20})
        with self.assertRaises(r.Blocked):watch.observe(2,{"bytes":19})
        with self.assertRaises(r.Blocked):watch.observe(2,{})

    def test_promotion_requires_fresh_exact_snapshot(self):
        final={"pass":True,"generation":GEN,"inventory":["fixture"],"manifest_sha256":"A"*64}
        fresh={**final,"generation":{**GEN,"snapshot_id":"fresh"}}
        self.assertTrue(r.promotion_gate(final,fresh)["pass"])
        with self.assertRaises(r.Blocked):r.promotion_gate(final,final)
        with self.assertRaises(r.Blocked):r.promotion_gate(final,{**fresh,"inventory":["changed"]})

    def test_bundle_trust_tamper_and_no_self_hash(self):
        source=b"# authenticated test fixture only\n"
        gate={"schema":"RECOVERY_OWNER_GATE_V004","authorized":True,"mode":"LIVE_EQUALITY","permissions":{"LIVE_EQUALITY":True},
              "spec_sha256":r.SPEC_SHA,"recovery_source_sha256":r.sha(source),"python_exe_sha256":"1"*64,
              "python_version":"3.14.7","release_id":"fixture","rescan_authorized":False,"csv_deletion_authorized":False,
              "format_promotion_authorized":False,"codec_promotion_authorized":False}
        def bundle(g):
            members={"tickstore_publisher_recovery_v004.py":source,"OWNER_GATE.json":r.json_bytes(g)}
            manifest={"schema":"RELEASE_MANIFEST_V004","members":{n:{"sha256":r.sha(b),"bytes":len(b)} for n,b in members.items()}}
            members["RELEASE_MANIFEST.json"]=r.json_bytes(manifest)
            anchor={**{k:g[k] for k in ("spec_sha256","recovery_source_sha256","python_exe_sha256","python_version","release_id")},
                    "inline_root_loader_revision":"INLINE_ROOT_LOADER_V004_R1","release_manifest_sha256":r.sha(members["RELEASE_MANIFEST.json"]),
                    "owner_gate_sha256":r.sha(members["OWNER_GATE.json"])}
            return anchor,members
        anchor,members=bundle(gate);self.assertEqual(r.admit_bundle(anchor,members),gate)
        for member in members:
            changed=dict(members);changed[member]+=b" "
            with self.assertRaises(r.Blocked):r.admit_bundle(anchor,changed)
        anchor,members=bundle({**gate,"release_bundle_sha256":"0"*64})
        with self.assertRaisesRegex(r.Blocked,"CYCLIC"):r.admit_bundle(anchor,members)



    def test_T_E1_safe_stop_admission_contract_by_mode(self):
        """T-E1: RECOVER requires a valid event; non-RECOVER modes do not."""
        source=b"# T-E1 fixture\n"
        def material(g):
            members={"tickstore_publisher_recovery_v004.py":source,"OWNER_GATE.json":r.json_bytes(g)}
            manifest={"schema":"RELEASE_MANIFEST_V004","members":{n:{"sha256":r.sha(b),"bytes":len(b)} for n,b in members.items()}}
            members["RELEASE_MANIFEST.json"]=r.json_bytes(manifest)
            anchor={**{k:g[k] for k in ("spec_sha256","recovery_source_sha256","python_exe_sha256","python_version","release_id")},
                    "inline_root_loader_revision":"INLINE_ROOT_LOADER_V004_R1",
                    "release_manifest_sha256":r.sha(members["RELEASE_MANIFEST.json"]),
                    "owner_gate_sha256":r.sha(members["OWNER_GATE.json"])}
            return anchor,members
        common={"schema":"RECOVERY_OWNER_GATE_V004","authorized":True,"spec_sha256":r.SPEC_SHA,
                "recovery_source_sha256":r.sha(source),"python_exe_sha256":"1"*64,"python_version":"3.14.7",
                "release_id":"fixture","rescan_authorized":False,"csv_deletion_authorized":False,
                "format_promotion_authorized":False,"codec_promotion_authorized":False}
        recover={**common,"mode":"RECOVER","permissions":{"RECOVER":True},"canary_execution_authorized":True,
                 "production_recovery_authorized":False,"canary_recovery_source_sha256":r.sha(source)}
        anchor,members=material(recover)
        with self.assertRaisesRegex(r.Blocked,"SAFE_STOP_EVENT_NAME_INVALID"):
            r.admit_bundle(anchor,members)
        valid=r"Global\TICKSTORE_V004R1_STOP_"+"A"*32
        recover_ok={**recover,"safe_stop_event_name":valid}
        anchor,members=material(recover_ok)
        self.assertEqual(r.admit_bundle(anchor,members),recover_ok)
        readonly={**common,"mode":"LIVE_EQUALITY","permissions":{"LIVE_EQUALITY":True}}
        anchor,members=material(readonly)
        self.assertEqual(r.admit_bundle(anchor,members),readonly)

    def test_T_E2_missing_event_blocks_before_writer_lock(self):
        """T-E2: OpenEventW -> NULL blocks before acquire() is called."""
        class Fn:
            def __init__(self,fn): self.fn=fn; self.argtypes=None; self.restype=None
            def __call__(self,*a): return self.fn(*a)
        class K:
            def __init__(self):
                self.OpenEventW=Fn(lambda *a:0)
                self.WaitForSingleObject=Fn(lambda *a:258)
                self.CloseHandle=Fn(lambda *a:1)
        rec=object.__new__(r.Recovery)
        rec.config={"safe_stop_event_name":r"Global\TICKSTORE_V004R1_STOP_"+"B"*32}
        rec.acquire=Mock(side_effect=AssertionError("acquire must not run"))
        with patch.object(r,"job_members",return_value={os.getpid()}), \
             patch.object(r.os,"name","nt"), \
             patch.object(r.ctypes,"WinDLL",return_value=K(),create=True):
            with self.assertRaisesRegex(r.Blocked,"SAFE_STOP_EVENT_NOT_FOUND"):
                r.Recovery.run(rec)
        rec.acquire.assert_not_called()

    def test_T_E3_wait_signal_sets_stop_requested(self):
        """T-E3: WAIT_OBJECT_0 reaches on_signal and sets the stop flag."""
        class Fn:
            def __init__(self,fn): self.fn=fn; self.argtypes=None; self.restype=None
            def __call__(self,*a): return self.fn(*a)
        calls={"close":0}
        class K:
            def __init__(self):
                self.OpenEventW=Fn(lambda *a:123)
                self.WaitForSingleObject=Fn(lambda *a:0)
                self.CloseHandle=Fn(self._close)
            def _close(self,*a): calls["close"]+=1; return 1
        flag=r.threading.Event()
        with patch.object(r.os,"name","nt"),patch.object(r.ctypes,"WinDLL",return_value=K(),create=True):
            watcher=r.NamedStopEvent(r"Global\TICKSTORE_V004R1_STOP_"+"C"*32,flag.set)
            watcher.start()
            self.assertTrue(flag.wait(1.0))
            watcher.close()
        self.assertEqual(calls["close"],1)

    def test_T_E4_close_is_idempotent_and_joins_thread(self):
        """T-E4: close is idempotent, joins watcher, closes handle exactly once."""
        class Fn:
            def __init__(self,fn): self.fn=fn; self.argtypes=None; self.restype=None
            def __call__(self,*a): return self.fn(*a)
        calls={"close":0}
        class K:
            def __init__(self):
                self.OpenEventW=Fn(lambda *a:456)
                self.WaitForSingleObject=Fn(lambda *a:258)
                self.CloseHandle=Fn(self._close)
            def _close(self,*a): calls["close"]+=1; return 1
        with patch.object(r.os,"name","nt"),patch.object(r.ctypes,"WinDLL",return_value=K(),create=True):
            watcher=r.NamedStopEvent(r"Global\TICKSTORE_V004R1_STOP_"+"D"*32,lambda:None)
            watcher.start()
            watcher.close()
            self.assertIsNone(watcher.thread)
            watcher.close()
        self.assertEqual(calls["close"],1)

    def test_T_E5_safe_stop_event_regex_vectors(self):
        """T-E5: exactly Global\\ + prefix + 32 uppercase HEX is admitted."""
        valid=r"Global\TICKSTORE_V004R1_STOP_"+"A"*32
        self.assertEqual(r.safe_stop_event_name(valid),valid)
        bad=(
            r"Global\\TICKSTORE_V004R1_STOP_"+"A"*32,
            r"Local\TICKSTORE_V004R1_STOP_"+"A"*32,
            r"Global\TICKSTORE_V004R1_STOP_"+"a"*32,
            r"Global\TICKSTORE_V004R1_STOP_"+"A"*31,
            r"Global\TICKSTORE_V004R1_STOP_"+"A"*33,
            valid+"\n","",None,
        )
        for value in bad:
            with self.subTest(value=value),self.assertRaisesRegex(r.Blocked,"SAFE_STOP_EVENT_NAME_INVALID"):
                r.safe_stop_event_name(value)


@unittest.skipUnless(os.name=="nt","Win32 required")
class NativeHandleTests(unittest.TestCase):
    def setUp(self):
        fixtures=HERE/"fixtures";fixtures.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix="recovery-unit-",dir=fixtures)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=r.Win32Store()

    def test_read_pin_denies_write_delete_and_detects_hardlink(self):
        path=self.root/"source.bin";path.write_bytes(b"fixture")
        with self.store.open(path) as pin:
            self.assertEqual(pin.hash(),(r.sha(b"fixture"),7))
            with self.assertRaises(OSError):path.write_bytes(b"changed")
            with self.assertRaises(OSError):path.unlink()
        other=self.root/"alias.bin";os.link(path,other)
        with self.assertRaisesRegex(r.Blocked,"HARDLINK"):self.store.open(path)

    def test_rename_no_overwrite_same_identity(self):
        dest=self.root/"dest";dest.mkdir()
        with self.store.open(dest,directory=True) as directory:
            with self.store.open(self.root/"stage.bin",new=True,mutate=True) as stage:
                stage.write(b"fixture");stage.flush();before=stage.info()
                stage.rename(directory,"final.bin")
                self.assertEqual(stage.info()["file_id"],before["file_id"])
                self.assertEqual(stage.hash(),(r.sha(b"fixture"),7))
        with self.store.open(dest,directory=True) as directory:
            with self.store.open(self.root/"collision.bin",new=True,mutate=True) as stage:
                stage.write(b"other");stage.flush()
                with self.assertRaisesRegex(r.Blocked,"RENAME_NO_OVERWRITE"):stage.rename(directory,"final.bin")
        self.assertEqual((dest/"final.bin").read_bytes(),b"fixture")

    def test_immutable_metadata_and_flush_failure(self):
        self.store.immutable(self.root,"coordinator.fixture.0001.json",b"{}\n")
        with self.assertRaisesRegex(r.Blocked,"CREATE_NEW"):
            self.store.immutable(self.root,"coordinator.fixture.0001.json",b"overwrite")
        with patch.object(self.store.k,"FlushFileBuffers",return_value=0):
            with self.assertRaisesRegex(r.Blocked,"FLUSH"):
                self.store.immutable(self.root,"failed-flush.json",b"{}\n")

    def test_live_lock_denies_second_holder_and_same_handle_release(self):
        path=self.root/"TICKSTORE_WRITER.lock"
        with self.store.open(path,new=True,mutate=True) as lock:
            lock.write(b"fixture");lock.flush()
            with self.assertRaises(r.Blocked):self.store.open(path,mutate=True)
            with self.assertRaises(r.Blocked):self.store.open(path,new=True,mutate=True)
            lock.delete_lock()
        self.assertFalse(path.exists())

    def test_parent_path_substitution_denied(self):
        folder=self.root/"parent";folder.mkdir();(folder/"file.bin").write_bytes(b"fixture")
        with self.store.open(folder/"file.bin"):
            with self.assertRaises(OSError):folder.rename(self.root/"replaced")


if __name__=="__main__":
    unittest.main(verbosity=2)
