"""Bounded native/transaction fixtures. No real data, VSS, or operational entrypoint.

Transaction tests execute the existing engine and actual file primitives. Codec/PREP
authority is a small synthetic adapter; these tests make no full-codec or Job claim.
"""
import ast
import contextlib
import ctypes
import inspect
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tickstore_publisher_recovery_v004 as r

HERE=Path(__file__).resolve().parent
CASE_EVIDENCE=[]


class CrashInjected(RuntimeError):
    pass


class FixtureCase(unittest.TestCase):
    def setUp(self):
        fixtures=HERE/"fixtures";fixtures.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix="native-r2r1-",dir=fixtures)
        self.addCleanup(self.temp.cleanup)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.temp.name);self.store=r.Win32Store()

    def opened_pair(self):
        dest=self.root/"destination";dest.mkdir()
        directory=self.stack.enter_context(self.store.open(dest,directory=True))
        source=self.stack.enter_context(self.store.open(self.root/"source.bin",new=True,mutate=True))
        source.write(b"SYNTHETIC_NATIVE_RENAME\x00\xff\n");source.flush()
        return source,directory

    def record(self,label,**values):
        CASE_EVIDENCE.append({"case":label,**values})


class NativeProbeTests(FixtureCase):
    def test_N1_relative_rootdir_success(self):
        source,directory=self.opened_pair();before=source.info();original_hash=source.hash()
        old=source.path;target=directory.path/"final.bin"
        self.assertFalse(target.exists())
        result=source.rename(directory,target.name)
        self.assertEqual(result["completion"],"COMPLETE_SUCCESS")
        self.assertEqual(result["return_status"]["hex"],"0x00000000")
        self.assertEqual(source.info()["file_id"],before["file_id"])
        self.assertEqual(source.hash(),original_hash);self.assertFalse(old.exists());self.assertTrue(target.exists())
        self.assertEqual(r.norm(source.path.parent),r.norm(directory.path))
        self.record("N1",operation=result)

    def test_N2_no_overwrite_collision(self):
        source,directory=self.opened_pair();before=source.hash();old=source.path
        target=directory.path/"sentinel.bin";sentinel=b"DO_NOT_OVERWRITE\x00\xff"
        target.write_bytes(sentinel)
        with self.assertRaisesRegex(r.Blocked,"COMPLETE_COLLISION.*0xC0000035"):
            source.rename(directory,target.name)
        result=self.store.rename_events[-1]
        self.assertEqual(result["final_status"]["mapped_win32"],183)
        self.assertEqual(target.read_bytes(),sentinel);self.assertTrue(old.exists());self.assertEqual(source.hash(),before)
        self.record("N2",operation=result,target_sha256=r.sha(target.read_bytes()),target_bytes=len(sentinel))

    def test_N3_root_handle_identity(self):
        source,directory=self.opened_pair();before=directory.info()
        result=source.rename(directory,"identity.bin")
        self.assertEqual(directory.info(),before)
        self.assertEqual(source.info()["volume"],before["volume"])
        source.close()
        with self.store.open(directory.path,directory=True) as independently_opened:
            self.assertEqual(independently_opened.info(),before)
        with self.store.open(directory.path/"identity.bin") as independently_opened:
            self.assertEqual(independently_opened.info()["file_id"],result["source_before"]["file_id"])
        self.record("N3",operation=result,directory_before=before,directory_after=directory.info())

    def win32_control(self,absolute):
        source,directory=self.opened_pair();before=source.info();content_hash=source.hash()
        target=directory.path/"control.bin";name=str(target) if absolute else target.name
        raw=name.encode("utf-16-le");size=ctypes.sizeof(r.FILE_RENAME_INFO)+len(raw)
        buffer=ctypes.create_string_buffer(size);info=r.FILE_RENAME_INFO.from_buffer(buffer)
        info.Flags=0;info.RootDirectory=None if absolute else directory.handle;info.FileNameLength=len(raw)
        ctypes.memmove(ctypes.addressof(buffer)+r.FILE_RENAME_INFO.FileName.offset,raw,len(raw))
        ctypes.set_last_error(0)
        ok=self.store.k.SetFileInformationByHandle(source.handle,3,buffer,size)
        error=0 if ok else ctypes.get_last_error()
        if absolute:
            self.assertTrue(ok);source.path=target
            self.assertEqual(source.info()["file_id"],before["file_id"])
            self.assertTrue(target.exists())
        else:
            self.assertFalse(ok);self.assertEqual(error,87);self.assertFalse(target.exists())
        self.assertEqual(source.hash(),content_hash)
        self.record("N5" if absolute else "N4",success=bool(ok),winerror=error,
            root_directory_null=absolute,control_only=True,bytes_hash_preserved=True)

    def test_N4_win32_differential_control(self):
        self.win32_control(False)

    def test_N5_null_absolute_control(self):
        self.win32_control(True)


class PendingTests(FixtureCase):
    def drive(self,source,directory,state):
        result=source.rename(directory,"pending.bin")
        state.update(intent=1,physical_state=1,coordinator=1)
        return result

    def test_S1_pending_not_success_no_advance(self):
        source,directory=self.opened_pair();state=dict(intent=0,physical_state=0,coordinator=0);before=dict(state)
        self.assertEqual(r.classify_native_rename(r.STATUS_PENDING),"PENDING_UNEXPECTED")
        def complete_failure(handle,timeout):
            self.assertEqual(state,before)
            source._rename_inflight.iosb.Status=r.NTSTATUS(0xc0000022).value
            return 0
        with patch.object(self.store.nt,"NtSetInformationFile",return_value=r.STATUS_PENDING),\
             patch.object(self.store.k,"WaitForSingleObject",side_effect=complete_failure):
            with self.assertRaisesRegex(r.Blocked,"COMPLETE_FAILURE"):
                self.drive(source,directory,state)
        self.assertEqual(state,before)
        self.record("S1",transaction_before=before,transaction_after=state,operation=self.store.rename_events[-1])

    def test_S2_pending_lifetime_and_no_resource_reuse(self):
        source,directory=self.opened_pair();state=dict(intent=0,physical_state=0,coordinator=0)
        def observe_pending(handle,timeout):
            op=source._rename_inflight
            self.assertIs(op,directory._rename_inflight);self.assertIn(op,r._unresolved_native_renames)
            self.assertIsNotNone(op.source.handle);self.assertIsNotNone(op.directory.handle)
            self.assertGreater(ctypes.sizeof(op.buffer),24);self.assertEqual(ctypes.sizeof(op.iosb),16)
            for action in (source.close,directory.close,source.flush,source.info,source.hash,lambda:source.write(b"reuse")):
                with self.assertRaisesRegex(r.Blocked,"PENDING_RESOURCE_IN_USE"):action()
            op.iosb.Status=r.NTSTATUS(0xc0000120).value
            return 0
        with patch.object(self.store.nt,"NtSetInformationFile",return_value=r.STATUS_PENDING),\
             patch.object(self.store.k,"WaitForSingleObject",side_effect=observe_pending):
            with self.assertRaisesRegex(r.Blocked,"COMPLETE_FAILURE"):
                self.drive(source,directory,state)
        self.assertIsNone(source._rename_inflight);self.assertIsNone(directory._rename_inflight)
        self.record("S2",all_resources_alive_while_pending=True,reuse_denied=True,transaction_after=state,
            operation=self.store.rename_events[-1])

    def test_S3_pending_to_final_success(self):
        source,directory=self.opened_pair();native_call=self.store.nt.NtSetInformationFile
        state=dict(intent=0,physical_state=0,coordinator=0);before=dict(state)
        def finish_actual_rename(handle,timeout):
            self.assertEqual(state,before);op=source._rename_inflight
            status=native_call(source.handle,ctypes.byref(op.iosb),op.buffer,len(op.buffer),10)
            self.assertEqual(status,0);self.assertEqual(op.iosb.Status,0)
            self.assertEqual(state,before)
            return 0
        with patch.object(self.store.nt,"NtSetInformationFile",return_value=r.STATUS_PENDING),\
             patch.object(self.store.k,"WaitForSingleObject",side_effect=finish_actual_rename):
            result=self.drive(source,directory,state)
        self.assertEqual(result["initial_completion"],"PENDING_UNEXPECTED")
        self.assertEqual(result["completion"],"COMPLETE_SUCCESS")
        self.assertEqual(state,dict(intent=1,physical_state=1,coordinator=1))
        self.record("S3",transaction_before=before,transaction_after=state,operation=result)

    def test_S4_pending_to_final_failure(self):
        source,directory=self.opened_pair();before_hash=source.hash()
        state=dict(intent=0,physical_state=0,coordinator=0)
        def complete_failure(handle,timeout):
            source._rename_inflight.iosb.Status=r.NTSTATUS(0xc0000035).value
            return 0
        with patch.object(self.store.nt,"NtSetInformationFile",return_value=r.STATUS_PENDING),\
             patch.object(self.store.k,"WaitForSingleObject",side_effect=complete_failure):
            with self.assertRaisesRegex(r.Blocked,"COMPLETE_COLLISION"):
                self.drive(source,directory,state)
        self.assertEqual(state,dict(intent=0,physical_state=0,coordinator=0));self.assertEqual(source.hash(),before_hash)
        self.record("S4",transaction_after=state,operation=self.store.rename_events[-1])

    def test_S5_pending_deadline_blocks_and_retains_resources(self):
        source,directory=self.opened_pair();state=dict(intent=0,physical_state=0,coordinator=0)
        self.store.rename_deadline_seconds=1
        with patch.object(self.store.nt,"NtSetInformationFile",return_value=r.STATUS_PENDING),\
             patch.object(r.time,"monotonic",side_effect=(0,2)):
            with self.assertRaisesRegex(r.Blocked,"PENDING_DEADLINE.*PHYSICAL_STATE_CLASSIFICATION_REQUIRED"):
                self.drive(source,directory,state)
        op=source._rename_inflight
        self.assertIn(op,r._unresolved_native_renames);self.assertIs(op,directory._rename_inflight)
        self.assertIsNotNone(source.handle);self.assertIsNotNone(directory.handle);self.assertTrue(self.store.rename_blocked)
        with self.assertRaisesRegex(r.Blocked,"BLOCKED_PHYSICAL_CLASSIFICATION_REQUIRED"):
            source.rename(directory,"another.bin")
        self.record("S5",transaction_after=dict(state),resources_retained_after_deadline=True,
            new_transaction_denied=True,operation=dict(op.record))
        # The injected call never submitted kernel I/O. Simulate proven late cancellation
        # to safely close only this test's fixtures. The store's BLOCK remains sticky.
        op.deadline=r.time.monotonic()+1;op.iosb.Status=r.NTSTATUS(0xc0000120).value
        with patch.object(self.store.k,"WaitForSingleObject",return_value=0):
            self.assertEqual(self.store.resolve_pending_rename(op),"COMPLETE_FAILURE")
        self.assertTrue(self.store.rename_blocked)

    def test_S6_synchronous_handle_contract(self):
        source,directory=self.opened_pair()
        self.assertFalse(source.open_flags & r.FILE_FLAG_OVERLAPPED)
        recorded=[];create=self.store.k.CreateFileW
        def capture(*args):
            recorded.append({"access":args[1],"share":args[2],"flags":args[5]})
            return create(*args)
        with patch.object(self.store.k,"CreateFileW",side_effect=capture):
            with self.store.open(self.root/"another.bin",new=True,mutate=True) as other:
                self.assertFalse(other.open_flags & r.FILE_FLAG_OVERLAPPED)
        source.open_flags |= r.FILE_FLAG_OVERLAPPED
        with patch.object(self.store.nt,"NtSetInformationFile") as native:
            with self.assertRaisesRegex(r.Blocked,"SYNCHRONOUS_HANDLE_REQUIRED"):
                source.rename(directory,"async.bin")
            native.assert_not_called()
        source.open_flags &= ~r.FILE_FLAG_OVERLAPPED
        self.assertTrue(all(not item["flags"] & r.FILE_FLAG_OVERLAPPED for item in recorded))
        self.record("S6",opens=recorded,async_attempt_rejected=True)


class ContractTests(unittest.TestCase):
    def test_ABI_and_explicit_status_classes(self):
        self.assertEqual(r.native_rename_abi()["iosb_size"],16)
        self.assertEqual(r.NTSTATUS(0xc0000035).value,-1073741771)
        expected={0:"COMPLETE_SUCCESS",0x103:"PENDING_UNEXPECTED",0xc0000035:"COMPLETE_COLLISION",
                  0xc0000022:"COMPLETE_FAILURE",0x40000000:"COMPLETE_FAILURE",0x80000005:"COMPLETE_FAILURE"}
        for status,classification in expected.items():
            self.assertEqual(r.classify_native_rename(status),classification)
        CASE_EVIDENCE.append({"case":"ABI",**r.native_rename_abi()})

    def test_five_callers_and_excluded_primitives(self):
        tree=ast.parse((HERE/"tickstore_publisher_recovery_v004.py").read_text(encoding="utf-8"))
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=="rename"]
        self.assertEqual(len(calls),5)
        self.assertNotIn("SetFileInformationByHandle",inspect.getsource(r.ProtectedFile.rename))
        self.assertIn("SetFileInformationByHandle",inspect.getsource(r.ProtectedFile.delete_lock))
        self.assertIn("self.handle,4",inspect.getsource(r.ProtectedFile.delete_lock))
        self.assertNotIn("rename(",inspect.getsource(r.Win32Store.immutable))
        CASE_EVIDENCE.append({"case":"CALLSITES", "count":len(calls),"lines":sorted(node.lineno for node in calls)})

    def test_native_export_missing_fails_closed(self):
        load=r.ctypes.WinDLL
        def unavailable(name,*args,**kwargs):
            return SimpleNamespace() if name=="ntdll.dll" else load(name,*args,**kwargs)
        with patch.object(r.ctypes,"WinDLL",side_effect=unavailable):
            with self.assertRaisesRegex(r.Blocked,"EXPORT_UNAVAILABLE"):r.Win32Store()


class TransactionTests(FixtureCase):
    def engine_fixture(self):
        key="20260901";payload=b"BOUNDED_SYNTHETIC_CONTAINER_BYTES\n"
        dest=self.root/"canonical";work=self.root/"recovery";scratch=self.root/"synthetic_scratch"
        for path in (dest,work,scratch,dest/"WIN@N"/"2026_09"):
            path.mkdir(parents=True,exist_ok=True)
        source=scratch/"day.partial";source.write_bytes(payload)
        manifest=r.parse(r.manifest_bytes({},1));(dest/r.MANIFEST_NAME).write_bytes(r.json_bytes(manifest))
        engine=r.Recovery.__new__(r.Recovery)
        engine.store=self.store;engine.dest=dest;engine.work=work;engine.scratch=scratch
        engine.run_id="a"*32;engine.sequence=0;engine.live={};engine.stop_requested=False;engine.initial_timestamp=1
        engine.days={key:{"date_key":key,"month_id":"2026_09","rows":"3"}}
        engine.c0={"days":{}}
        engine.s0={"days":{key:{"partial":{"path":"day.partial"}}}}
        engine.zstd=None;engine.fault=lambda point:None;engine.watchdog_diagnostics=[]
        engine.deadline_profile={"streaming_by_size_class":{f"B{i}":7200 for i in range(8)},"liveness_fatal_seconds":45}
        oracle={"date_key":key,"fixture_only":True}
        def fresh(date):
            with self.store.open(source) as pin:
                identity=pin.info()
            return {"oracle":oracle,"container_sha256":r.sha(payload),"container_bytes":len(payload),
                    "evidence":{"partial":{"identity":identity}}}
        engine.fresh_prep=fresh
        def record(oracle,h,n,kh):
            return {"date_key":oracle["date_key"],"container_sha256":h,"container_bytes":n,"commit_sha256":kh}
        core=SimpleNamespace(expected_commit=lambda oracle,h,n:{"date_key":key,"container_sha256":h,"container_bytes":n},
                             manifest_record=record)
        def validate(store,root,contract,oracle,zstd):
            _,cp,kp=r.day_paths(root,contract)
            with store.open(cp) as container,store.open(kp) as commit:
                h,n=container.hash();raw=commit.read();obj=r.parse(raw)
                self.assertEqual((h,n),(r.sha(payload),len(payload)))
                self.assertEqual(obj["container_sha256"],h);self.assertEqual(obj["container_bytes"],n)
                kh,kn=commit.hash()
                return {"record":record(oracle,h,n,kh),"published_unix_ns":obj["published_unix_ns"]}
        return engine,key,manifest,core,validate

    def physical_state(self,engine,key):
        _,cp,kp=r.day_paths(engine.dest,engine.days[key]);path=engine.dest/r.MANIFEST_NAME
        present=path.exists();record=key in r.parse(path.read_bytes())["records"] if present else False
        return {"container":cp.exists(),"commit":kp.exists(),"manifest_present":present,"manifest_record":record,
                "coordinators":len(list(engine.work.glob("coordinator.*.json")))}

    def run_boundary(self,boundary,expected):
        engine,key,manifest,core,validate=self.engine_fixture()
        def inject(point):
            if point==boundary:raise CrashInjected(point)
        engine.fault=inject
        with patch.object(r,"frozen_core",return_value=core),patch.object(r,"validate_pair",side_effect=validate):
            with self.assertRaisesRegex(CrashInjected,boundary):engine.publish(key,manifest,"PENDING")
        observed=self.physical_state(engine,key)
        self.assertEqual(observed,expected)
        self.assertEqual((engine.scratch/"day.partial").read_bytes(),b"BOUNDED_SYNTHETIC_CONTAINER_BYTES\n")
        self.record(boundary,physical_after=observed,operations=self.store.rename_events,
            full_codec_validation_mocked=True,real_handle_rename=True)

    def test_T01_before_intent(self):
        self.run_boundary("BEFORE_INTENT",dict(container=False,commit=False,manifest_present=True,manifest_record=False,coordinators=0))
    def test_T02_after_intent(self):
        self.run_boundary("AFTER_INTENT",dict(container=False,commit=False,manifest_present=True,manifest_record=False,coordinators=0))
    def test_T03_after_container(self):
        self.run_boundary("AFTER_CONTAINER_RENAME",dict(container=True,commit=False,manifest_present=True,manifest_record=False,coordinators=0))
    def test_T04_after_commit(self):
        self.run_boundary("AFTER_COMMIT_RENAME",dict(container=True,commit=True,manifest_present=True,manifest_record=False,coordinators=0))
    def test_T05_manifest_pre_moved(self):
        self.run_boundary("MANIFEST_PRE_MOVED",dict(container=True,commit=True,manifest_present=False,manifest_record=False,coordinators=0))
    def test_T06_manifest_post_moved(self):
        self.run_boundary("MANIFEST_POST_MOVED",dict(container=True,commit=True,manifest_present=True,manifest_record=True,coordinators=0))
    def test_T07_before_coordinator(self):
        self.run_boundary("BEFORE_COORDINATOR",dict(container=True,commit=True,manifest_present=True,manifest_record=True,coordinators=0))

    def test_T08_terminal_publish_idempotent_startup(self):
        engine,key,manifest,core,validate=self.engine_fixture()
        with patch.object(r,"frozen_core",return_value=core),patch.object(r,"validate_pair",side_effect=validate):
            final=engine.publish(key,manifest,"PENDING")
        self.assertEqual(self.physical_state(engine,key),dict(container=True,commit=True,manifest_present=True,manifest_record=True,coordinators=1))
        count=len(self.store.rename_events)
        self.assertEqual(engine.startup_manifest(final["records"],final["updated_unix_ns"]),final)
        self.assertEqual(engine.startup_manifest(final["records"],final["updated_unix_ns"]),final)
        self.assertEqual(len(self.store.rename_events),count)
        self.record("TERMINAL_IDEMPOTENCE",operations=self.store.rename_events,repeat_startup_renames=0)

    def test_T09_pending_at_container_never_advances_engine(self):
        engine,key,manifest,core,validate=self.engine_fixture();snapshots=[];points=[]
        engine.fault=points.append
        def pending(handle,iosb,buffer,size,kind):
            snapshots.append({"sequence":engine.sequence,"coordinators":len(list(engine.work.glob("coordinator.*.json")))})
            return r.STATUS_PENDING
        def final_failure(handle,timeout):
            op=next(item for item in r._unresolved_native_renames if item.source.store is self.store)
            self.assertEqual(engine.sequence,snapshots[0]["sequence"])
            self.assertEqual(len(list(engine.work.glob("coordinator.*.json"))),0)
            op.iosb.Status=r.NTSTATUS(0xc0000022).value
            return 0
        with patch.object(r,"frozen_core",return_value=core),patch.object(r,"validate_pair",side_effect=validate),\
             patch.object(self.store.nt,"NtSetInformationFile",side_effect=pending),\
             patch.object(self.store.k,"WaitForSingleObject",side_effect=final_failure):
            with self.assertRaisesRegex(r.Blocked,"COMPLETE_FAILURE"):engine.publish(key,manifest,"PENDING")
        self.assertNotIn("AFTER_CONTAINER_RENAME",points)
        self.assertEqual(engine.sequence,snapshots[0]["sequence"])
        self.assertEqual(self.physical_state(engine,key),dict(container=False,commit=False,manifest_present=True,manifest_record=False,coordinators=0))
        self.record("ENGINE_PENDING_NO_ADVANCE",transaction_before=snapshots[0],transaction_after={"sequence":engine.sequence,"coordinators":0},
            operation=self.store.rename_events[-1])

    def test_T10_stale_coordinator_is_non_authority(self):
        engine,key,manifest,core,validate=self.engine_fixture()
        stale=engine.work/("coordinator."+"d"*32+".00000001.json")
        stale.write_bytes(r.json_bytes({"schema":"COORDINATOR_GENERATION_V004","authority":False,"completed":[key],"rows":999999,"last_date_key":key}))
        before=stale.read_bytes()
        records,timestamp=engine.physical_records()
        restored=engine.startup_manifest(records,timestamp)
        states=engine.classify(restored)
        self.assertEqual(states[key],"PENDING")
        self.assertEqual(stale.read_bytes(),before)
        self.record("STALE_COORDINATOR_NON_AUTHORITY",coordinator_sha256=r.sha(before),state=states[key])

    def test_T99_restore_absent_manifest_callsite(self):
        engine,key,manifest,core,validate=self.engine_fixture()
        target=engine.dest/r.MANIFEST_NAME;target.unlink()  # Only this test's disposable fixture.
        candidate=engine.work/("manifest.post."+"b"*32+"."+"c"*32+".json")
        candidate.write_bytes(r.json_bytes(manifest))
        before_id=None
        with self.store.open(candidate) as pin:before_id=pin.info()["file_id"]
        before_sequence=engine.sequence
        try:
            restored=engine.startup_manifest({},1)
            self.assertEqual(restored,manifest)
            self.assertEqual(target.read_bytes(),r.json_bytes(manifest));self.assertFalse(candidate.exists())
            with self.store.open(target) as pin:self.assertEqual(pin.info()["file_id"],before_id)
            self.assertEqual(engine.sequence,before_sequence)
        finally:
            self.record("RESTORE_ABSENT_MANIFEST",target_present=target.exists(),candidate_present=candidate.exists(),
                operations=self.store.rename_events,transaction_sequence_before=before_sequence,transaction_sequence_after=engine.sequence)
