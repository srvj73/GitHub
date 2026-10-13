"""Mandatory pre-canary completeness tests. Disposable fixtures only; no production roots."""
import contextlib
import base64
import hashlib
import ntpath
import stat
import types
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tickstore_publisher_recovery_v004 as r

HERE=Path(__file__).resolve().parent
GEN={"snapshot_id":"fixture-snapshot-1","snapshot_set_id":"fixture-set-1",
     "provider_id":"fixture-provider","device_object":r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999",
     "volume_identity":"fixture-volume","volume_guid":r"\\?\Volume{00000000-0000-0000-0000-000000000999}\\",
     "creation_timestamp":1,"attributes":25,"purpose":"SAFE_STOP"}


def s0_fixture_one():
    key="20260901";ns=r.NAMESPACES[0]
    entry={"namespace":ns,"contract":{"date_key":key,"proof":"fixture"},
           "journal":{"path":f"{ns}/fixture/{key}/{key}.journal.json","sha256":"A"*64,"bytes":32},
           "partial":{"path":f"{ns}/fixture/{key}/{key}.pts2g.partial","sha256":"B"*64,"bytes":32}}
    return key,{"days":{key:entry}}


class PureCompletenessTests(unittest.TestCase):
    def test_implementation_fuse_stays_false_until_complete_release_gate(self):
        self.assertFalse(r.IMPLEMENTATION_READY)

    def test_size_classes_exact_boundaries(self):
        mib=1024*1024
        self.assertEqual(r.size_class(1),"B0")
        self.assertEqual(r.size_class(64*mib),"B0")
        self.assertEqual(r.size_class(64*mib+1),"B1")
        self.assertEqual(r.size_class(4096*mib),"B6")
        self.assertEqual(r.size_class(4096*mib+1),"B7")
        with self.assertRaises(r.Blocked):r.size_class(0)

    def test_canary_deadline_contract_is_exact_and_180_is_diagnostic_only(self):
        exact={"heartbeat_target_seconds":5,"liveness_fatal_seconds":45,"streaming_hard_deadline_seconds":7200,
               "metadata_hard_deadline_seconds":900,"cooperative_shutdown_ceiling_seconds":900,
               "terminate_wait_seconds":120,"kill_wait_seconds":60,"no_progress_diagnostic_seconds":180}
        profile=r.deadline_contract({"production_recovery_authorized":False,"bootstrap_deadlines":exact},{})
        self.assertEqual(profile["streaming_by_size_class"],{f"B{i}":7200 for i in range(8)})
        bad=dict(exact);bad["no_progress_diagnostic_seconds"]=181
        with self.assertRaises(r.Blocked):r.deadline_contract({"production_recovery_authorized":False,"bootstrap_deadlines":bad},{})

    def test_production_deadline_profile_requires_all_size_classes(self):
        profile={"schema":"DEADLINE_PROFILE_V004","heartbeat_target_seconds":5,"liveness_fatal_seconds":45,
                 "no_progress_diagnostic_seconds":180,"metadata_hard_deadline_seconds":120,
                 "cooperative_shutdown_ceiling_seconds":900,"terminate_wait_seconds":120,"kill_wait_seconds":60,
                 "streaming_by_size_class":{f"B{i}":900+i for i in range(8)}}
        raw=r.json_bytes(profile);gate={"production_recovery_authorized":True}
        self.assertEqual(r.deadline_contract(gate,{"DEADLINE_PROFILE.json":raw}),profile)
        broken=copy.deepcopy(profile);broken["streaming_by_size_class"].pop("B7")
        with self.assertRaisesRegex(r.Blocked,"SIZE_CLASSES"):
            r.deadline_contract(gate,{"DEADLINE_PROFILE.json":r.json_bytes(broken)})

    def test_prepare_all_is_supervisor_backed_and_records_diagnostics(self):
        engine=r.Recovery.__new__(r.Recovery)
        key,s0=s0_fixture_one()
        engine.source_bytes=b"source";engine.deadline_profile={"fixture":True};engine.config={"prep_workers":1}
        engine.scratch=Path("fixture");engine.days={key:{"date_key":key,"month_id":"2026_09"}}
        engine.months={"2026_09":{}};engine.s0=s0;engine.stop_requested=False;engine.live={}
        captured=[];engine.metadata=lambda kind,obj:captured.append((kind,obj))
        class FakeSupervisor:
            def __init__(self,*args,**kwargs):self.diagnostics=[{"diagnostic":"fixture"}]
            def run(self):return {key:{"date_key":key,"evidence":{}}}
        with patch.object(r,"PrepSupervisor",FakeSupervisor):engine.prepare_all()
        self.assertEqual(set(engine.live),{key})
        self.assertEqual(engine.prep_diagnostics,[{"diagnostic":"fixture"}])
        self.assertEqual(captured[0][0],"prep_complete")

    def test_safe_stop_fixture_uses_one_vss_generation_for_canonical_and_s0(self):
        # Reuse full synthetic S0 fixture from existing test module to exercise the actual 1399/1399 gate.
        import test_publisher_recovery_v004 as old
        cert,objects=old.s0_fixture()
        engine=r.Recovery.__new__(r.Recovery)
        class FakeVSS:
            def create(self,purpose):
                self.purpose=purpose;return dict(GEN)
            def shadow_root(self,generation,root):
                self.shadow_generation=generation;return Path("shadow")
            def assert_present(self,generation):self.asserted=generation
        engine.vss=FakeVSS();engine.scratch=Path("live");engine.s0={"generation":dict(GEN),"days":cert["days"]}
        engine.config={"scratch_admission_cert_sha256":"C"*64};engine.lock=object();engine.store=object()
        captured=[];engine.metadata=lambda kind,obj:captured.append((kind,obj));engine.release=lambda:None
        engine.audit_snapshot=lambda generation:{"pass":True,"generation":generation}
        with patch.object(r,"job_members",return_value={os.getpid()}),patch.object(r,"scan_s0",return_value=objects):
            rc=engine.safe_stop()
        self.assertEqual(rc,130);self.assertEqual(captured[-1][0],"safe_stop")
        result=captured[-1][1];self.assertEqual(result["SAFE_STOP"],"YES")
        self.assertTrue(r.generation_equal(result["canonical"]["generation"],result["s0"]["generation"]))

    def test_vss_startup_probe_mock_requires_cleanup_and_shadow_roots(self):
        class DummyOpen:
            def __enter__(self):return self
            def __exit__(self,*exc):return False
        class DummyStore:
            def __init__(self):self.opened=[]
            def open(self,path,directory=False):self.opened.append((str(path),directory));return DummyOpen()
        fake=object.__new__(r.NativeVSS);fake.store=DummyStore();fake.profile={"drive":"D:"}
        generation={**GEN,"snapshot_id":"00000000-0000-0000-0000-000000000001","snapshot_set_id":"00000000-0000-0000-0000-000000000002"}
        fake.create=lambda purpose:generation
        fake.shadow_root=lambda gen,root:Path("shadow")/Path(str(root).replace(":",""))
        def call(index,args,*values):
            self.assertEqual(index,39);values[-2]._obj.value=1
        fake.call=call
        fake.properties=lambda sid:(_ for _ in ()).throw(r.Blocked("VSS_HRESULT:0x80042308"))
        fake.startup_probe(r"D:\TICKSTORE",r"D:\TICKSTORE_GATE_B_SCRATCH")
        self.assertEqual(len(fake.store.opened),2)

    def test_vss_startup_probe_mock_cleanup_failure_blocks(self):
        class DummyOpen:
            def __enter__(self):return self
            def __exit__(self,*exc):return False
        fake=object.__new__(r.NativeVSS);fake.store=type("Store",(),{"open":lambda self,path,directory=False:DummyOpen()})()
        fake.profile={"drive":"D:"};generation={**GEN,"snapshot_id":"00000000-0000-0000-0000-000000000001","snapshot_set_id":"00000000-0000-0000-0000-000000000002"};fake.create=lambda purpose:generation
        fake.shadow_root=lambda gen,root:Path("shadow")
        fake.call=lambda index,args,*values:None
        with self.assertRaisesRegex(r.Blocked,"VSS_PROBE_CLEANUP_FAILED"):
            fake.startup_probe(r"D:\TICKSTORE",r"D:\TICKSTORE_GATE_B_SCRATCH")

    def test_T_E6_authorization_dag_rejects_cycles_and_production_code_drift(self):
        source=b"# fixture\n"
        base={"schema":"RECOVERY_OWNER_GATE_V004","authorized":True,"mode":"RECOVER","permissions":{"RECOVER":True},
              "spec_sha256":r.SPEC_SHA,"recovery_source_sha256":r.sha(source),"python_exe_sha256":"1"*64,
              "python_version":"3.14.7","release_id":"fixture","rescan_authorized":False,"csv_deletion_authorized":False,
              "format_promotion_authorized":False,"codec_promotion_authorized":False,"canary_execution_authorized":True,
              "production_recovery_authorized":False,"canary_recovery_source_sha256":r.sha(source),
              "safe_stop_event_name":r"Global\TICKSTORE_V004R1_STOP_"+"E"*32}
        def material(g):
            members={"tickstore_publisher_recovery_v004.py":source,"OWNER_GATE.json":r.json_bytes(g)}
            man={"schema":"RELEASE_MANIFEST_V004","members":{n:{"sha256":r.sha(b),"bytes":len(b)} for n,b in members.items()}}
            members["RELEASE_MANIFEST.json"]=r.json_bytes(man)
            anchor={**{k:g[k] for k in ("spec_sha256","recovery_source_sha256","python_exe_sha256","python_version","release_id")},
                    "inline_root_loader_revision":"INLINE_ROOT_LOADER_V004_R1","release_manifest_sha256":r.sha(members["RELEASE_MANIFEST.json"]),
                    "owner_gate_sha256":r.sha(members["OWNER_GATE.json"])}
            return anchor,members
        # T-E6: positive fixture contains safe_stop_event_name; negative fixture proves it is mandatory.
        anchor,members=material(base);self.assertEqual(r.admit_bundle(anchor,members),base)
        missing=dict(base);missing.pop("safe_stop_event_name");anchor,members=material(missing)
        with self.assertRaisesRegex(r.Blocked,"SAFE_STOP_EVENT_NAME_INVALID"):r.admit_bundle(anchor,members)
        cyc={**base,"external_anchor_sha256":"A"*64};anchor,members=material(cyc)
        with self.assertRaisesRegex(r.Blocked,"CYCLIC_OWNER_GATE"):r.admit_bundle(anchor,members)
        drift={**base,"canary_recovery_source_sha256":"F"*64};anchor,members=material(drift)
        with self.assertRaisesRegex(r.Blocked,"CANARY_PRODUCTION_CODE_CHANGED"):r.admit_bundle(anchor,members)


    def test_vss_globalroot_parent_floor_is_shadow_volume(self):
        target=r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE_GATE_B_SCRATCH\WIN@N"
        floor=r.vss_shadow_volume_root(target)
        self.assertEqual(str(floor),r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999")
        self.assertIsNone(r.vss_shadow_volume_root(r"D:\TICKSTORE"))
        self.assertIsNone(r.vss_shadow_volume_root(r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopyX\TICKSTORE"))
        self.assertFalse(r.protected_parent_is_real(target,r"\\?\GLOBALROOT"))
        self.assertFalse(r.protected_parent_is_real(target,r"\\?\GLOBALROOT\Device"))
        self.assertTrue(r.protected_parent_is_real(target,r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999"))
        self.assertTrue(r.protected_parent_is_real(target,r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE_GATE_B_SCRATCH"))

    def test_vss_parent_floor_preserves_ordinary_parent_pinning(self):
        target=r"D:\TICKSTORE\WIN@N\2026_09"
        for parent in (r"D:\\",r"D:\TICKSTORE",r"D:\TICKSTORE\WIN@N"):
            with self.subTest(parent=parent):
                self.assertTrue(r.protected_parent_is_real(target,parent))



    def test_vss_shadow_device_root_directory_open_gets_one_trailing_backslash(self):
        root=r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999"
        self.assertEqual(r.vss_directory_open_path(root,True),root+"\\")
        self.assertEqual(r.vss_directory_open_path(root+"\\",True),root+"\\")
        self.assertEqual(r.vss_directory_open_path(root,False),root)

    def test_vss_shadow_subdir_and_ordinary_directory_open_paths_are_unchanged(self):
        shadow=r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE"
        ordinary=r"D:\TICKSTORE"
        self.assertEqual(r.vss_directory_open_path(shadow,True),shadow)
        self.assertEqual(r.vss_directory_open_path(ordinary,True),ordinary)
        self.assertEqual(r.vss_directory_open_path(ordinary,False),ordinary)



    def test_vss_final_path_uses_nt_volume_name_and_compares_device_identity(self):
        path=r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE\WIN@N"
        self.assertEqual(r.final_path_query_flags(path),0x2)
        expected,actual=r.comparable_final_path(
            path,r"\Device\HarddiskVolumeShadowCopy999\TICKSTORE\WIN@N")
        self.assertEqual(actual,expected)

    def test_ordinary_final_path_keeps_dos_query_contract(self):
        path=r"D:\TICKSTORE\WIN@N"
        self.assertEqual(r.final_path_query_flags(path),0)
        expected,actual=r.comparable_final_path(path,r"\\?\D:\TICKSTORE\WIN@N")
        self.assertEqual(actual,expected)



    def test_T_V1_core_vss_adapter_delegates_live_paths_exactly(self):
        class Sentinel(RuntimeError):pass
        calls=[]
        def original_final(k32,h,path):
            calls.append(("final",str(path)))
            if "raise" in str(path):raise Sentinel("live-final")
            return "LIVE-FINAL"
        def original_chain(path,allow_missing_tail=False):
            calls.append(("chain",str(path),allow_missing_tail))
            if "raise" in str(path):raise Sentinel("live-chain")
            return "LIVE-CHAIN"
        core=types.SimpleNamespace(_windows_final_handle_path=original_final,assert_no_link_chain=original_chain)
        r._install_core_vss_io_adapter(core)
        self.assertEqual(core._windows_final_handle_path(None,None,Path(r"D:\live\file")),"LIVE-FINAL")
        self.assertEqual(core.assert_no_link_chain(Path(r"D:\live\dir"),True),"LIVE-CHAIN")
        with self.assertRaisesRegex(Sentinel,"live-final"):core._windows_final_handle_path(None,None,Path(r"D:\raise\file"))
        with self.assertRaisesRegex(Sentinel,"live-chain"):core.assert_no_link_chain(Path(r"D:\raise\dir"),False)

    def test_T_V2_shadow_core_final_path_uses_only_nt_flag_and_validates(self):
        core=r.frozen_core();path=Path(r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE\day.pts2g");calls=[]
        class Final:
            def __call__(self,h,buf,size,flags):
                calls.append(flags);value=r"\Device\HarddiskVolumeShadowCopy999\TICKSTORE\day.pts2g";buf.value=value;return len(value)
        k32=types.SimpleNamespace(GetFinalPathNameByHandleW=Final())
        info=types.SimpleNamespace(dwFileAttributes=0,nNumberOfLinks=1);norm=lambda p:ntpath.normcase(ntpath.normpath(str(p)))
        with patch.object(core,"_windows_handle_info",return_value=info),patch.object(core,"_windows_normalized_path",side_effect=norm):
            out=core._windows_validate_handle(k32,1,path,expect_directory=False,require_single_link=True)
        self.assertIs(out,info);self.assertEqual(calls,[0x2])

    def test_T_V3_shadow_core_final_path_rejects_other_device_or_path(self):
        core=r.frozen_core();path=Path(r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE\day.pts2g")
        class Other:
            def __call__(self,h,buf,size,flags):value=r"\Device\HarddiskVolumeShadowCopy998\TICKSTORE\day.pts2g";buf.value=value;return len(value)
        with self.assertRaisesRegex(core.Blocked,"SHADOW_DEVICE_MISMATCH"):
            core._windows_final_handle_path(types.SimpleNamespace(GetFinalPathNameByHandleW=Other()),1,path)
        class Wrong:
            def __call__(self,h,buf,size,flags):value=r"\Device\HarddiskVolumeShadowCopy999\TICKSTORE\other.pts2g";buf.value=value;return len(value)
        k32=types.SimpleNamespace(GetFinalPathNameByHandleW=Wrong());info=types.SimpleNamespace(dwFileAttributes=0,nNumberOfLinks=1);norm=lambda p:ntpath.normcase(ntpath.normpath(str(p)))
        with patch.object(core,"_windows_handle_info",return_value=info),patch.object(core,"_windows_normalized_path",side_effect=norm),self.assertRaisesRegex(core.Blocked,"WIN_HANDLE_PATH_MISMATCH"):
            core._windows_validate_handle(k32,1,path,False,True)

    def test_T_V4_shadow_core_nt_query_failure_has_flags_and_winerror(self):
        core=r.frozen_core();path=Path(r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE\day.pts2g")
        class Fail:
            def __call__(self,h,buf,size,flags):return 0
        with patch.object(r.ctypes,"get_last_error",return_value=3,create=True),self.assertRaisesRegex(core.Blocked,r"FLAGS=0x2:WINERROR=3"):
            core._windows_final_handle_path(types.SimpleNamespace(GetFinalPathNameByHandleW=Fail()),1,path)

    def test_T_V5_shadow_core_link_chain_starts_at_floor_and_preserves_missing_tail(self):
        core=r.frozen_core();path=Path(r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy999\TICKSTORE\WIN@N\2026_09");calls=[]
        ds=types.SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0)
        def fake(value):
            text=str(value);calls.append(text)
            if text.endswith(r"\2026_09"):raise FileNotFoundError(text)
            return ds
        with patch.object(core.os,"lstat",side_effect=fake),patch.object(core,"_reject_link_or_reparse",return_value=None):core.assert_no_link_chain(path,True)
        self.assertTrue(calls[0].endswith("HarddiskVolumeShadowCopy999\\"));self.assertFalse(any(x.casefold() in (r"\\?\globalroot",r"\\?\globalroot\device") for x in calls))
        with patch.object(core.os,"lstat",side_effect=fake),patch.object(core,"_reject_link_or_reparse",return_value=None),self.assertRaisesRegex(core.Blocked,"PATH_CHAIN_MISSING"):core.assert_no_link_chain(path,False)
        checked=[]
        def reject(p,st):
            checked.append(str(p))
            if str(p).endswith(r"\WIN@N"):raise core.Blocked("LINK_OR_REPARSE_NOT_ALLOWED:"+str(p))
        with patch.object(core.os,"lstat",return_value=ds),patch.object(core,"_reject_link_or_reparse",side_effect=reject),self.assertRaisesRegex(core.Blocked,"LINK_OR_REPARSE_NOT_ALLOWED"):core.assert_no_link_chain(path,False)
        self.assertTrue(any(x.endswith(r"\WIN@N") for x in checked))

    def test_T_V6_embedded_hashes_unchanged_and_adapter_installed_once(self):
        self.assertEqual(hashlib.sha256(base64.b64decode(r.CORE_B64)).hexdigest().upper(),r.CORE_SHA);self.assertEqual(hashlib.sha256(base64.b64decode(r.REFERENCE_B64)).hexdigest().upper(),r.REFERENCE_SHA)
        core=r.frozen_core();f=core._windows_final_handle_path;c=core.assert_no_link_chain;of=core._tickstore_original_windows_final_handle_path;oc=core._tickstore_original_assert_no_link_chain
        r._install_core_vss_io_adapter(core)
        self.assertIs(core._windows_final_handle_path,f);self.assertIs(core.assert_no_link_chain,c);self.assertIs(core._tickstore_original_windows_final_handle_path,of);self.assertIs(core._tickstore_original_assert_no_link_chain,oc)

    def test_T_V7_startup_probe_failure_cleans_exact_generation_and_preserves_primary(self):
        generation={**GEN,"snapshot_id":"00000000-0000-0000-0000-000000000111","snapshot_set_id":"00000000-0000-0000-0000-000000000222"}
        class DummyStore:
            def open(self,*args,**kwargs):raise r.Blocked("PRIMARY_OPEN_FAILURE")
        fake=object.__new__(r.NativeVSS);fake.store=DummyStore();fake.profile={"drive":"D:"};fake.create=lambda purpose:generation;fake.shadow_root=lambda gen,root:Path("shadow");deleted=[];fake.delete_generation=lambda gen,label="VSS_PROBE":deleted.append((gen["snapshot_id"],label))
        with self.assertRaisesRegex(r.Blocked,"PRIMARY_OPEN_FAILURE") as cm:fake.startup_probe(r"D:\TICKSTORE",r"D:\TICKSTORE_GATE_B_SCRATCH")
        self.assertEqual(deleted,[(generation["snapshot_id"],"VSS_PROBE")]);self.assertEqual(str(cm.exception),"PRIMARY_OPEN_FAILURE")

    def test_T_V8_oracle_provenance_contract_accepts_frozen_rc1_and_rejects_unknown(self):
        oracle={"source_identity":{"sha256":"A"*64,"size":123},"runner_ids":{"runner_sha256":r.CORE_SHA,"reference_sha256":r.REFERENCE_SHA},"fixture":"oracle"}
        fake=types.SimpleNamespace(make_oracle=lambda contract,month,identity,ledger,runner_ids:oracle);month={"source_sha256":"A"*64,"source_size":123}
        with patch.object(r,"frozen_core",return_value=fake):self.assertIs(r.oracle_contract(oracle,{"date_key":"20260901"},month),oracle)
        bad={**oracle,"runner_ids":{**oracle["runner_ids"],"runner_sha256":"F"*64}};fake_bad=types.SimpleNamespace(make_oracle=lambda contract,month,identity,ledger,runner_ids:bad)
        with patch.object(r,"frozen_core",return_value=fake_bad),self.assertRaisesRegex(r.Blocked,"ORACLE_FROZEN_RC1_OR_R8_PROVENANCE"):r.oracle_contract(bad,{"date_key":"20260901"},month)

    def test_T_P1_exact_certified_r8_provenance_is_accepted_for_both_frozen_pilot_dates(self):
        month={"source_sha256":"A"*64,"source_size":123}
        for key in sorted(r.R8_CERTIFIED_DATES):
            oracle={"source_identity":{"sha256":"A"*64,"size":123},"runner_ids":dict(r.R8_CERTIFIED_RUNNER_IDS),"fixture":"oracle"}
            fake=types.SimpleNamespace(make_oracle=lambda contract,month,identity,ledger,runner_ids,o=oracle:o)
            with self.subTest(date_key=key),patch.object(r,"frozen_core",return_value=fake):
                self.assertIs(r.oracle_contract(oracle,{"date_key":key},month),oracle)

    def test_T_P2_r8_provenance_is_rejected_outside_the_two_certified_dates(self):
        month={"source_sha256":"A"*64,"source_size":123}
        oracle={"source_identity":{"sha256":"A"*64,"size":123},"runner_ids":dict(r.R8_CERTIFIED_RUNNER_IDS),"fixture":"oracle"}
        fake=types.SimpleNamespace(make_oracle=lambda contract,month,identity,ledger,runner_ids:oracle)
        with patch.object(r,"frozen_core",return_value=fake),self.assertRaisesRegex(r.Blocked,"ORACLE_R8_CERTIFIED_DATE"):
            r.oracle_contract(oracle,{"date_key":"20260901"},month)

    def test_T_P3_r8_provenance_requires_the_exact_certified_id_object(self):
        month={"source_sha256":"A"*64,"source_size":123}
        ids=dict(r.R8_CERTIFIED_RUNNER_IDS);ids["spec_sha256"]="F"*64
        oracle={"source_identity":{"sha256":"A"*64,"size":123},"runner_ids":ids,"fixture":"oracle"}
        fake=types.SimpleNamespace(make_oracle=lambda contract,month,identity,ledger,runner_ids:oracle)
        with patch.object(r,"frozen_core",return_value=fake),self.assertRaisesRegex(r.Blocked,"ORACLE_R8_CERTIFIED_PROVENANCE"):
            r.oracle_contract(oracle,{"date_key":"20211022"},month)

    def test_vss_shadow_root_and_generation_binding_fixture(self):
        v=object.__new__(r.NativeVSS);v.profile={"drive":"D:"}
        generation=dict(GEN)
        shadow=v.shadow_root(generation,r"D:\TICKSTORE_GATE_B_SCRATCH")
        self.assertIn("HarddiskVolumeShadowCopy999",str(shadow))
        v.properties=lambda sid:dict(generation)
        v.assert_present(generation)
        changed=dict(generation);changed["provider_id"]="different"
        v.properties=lambda sid:changed
        with self.assertRaisesRegex(r.Blocked,"GENERATION_LOST_OR_CHANGED"):v.assert_present(generation)

    def test_monitored_operation_hard_deadline_is_fatal_even_when_io_thread_is_stuck(self):
        import time
        def operation(update):
            time.sleep(0.15);return "late"
        def fatal(label):
            raise r.Blocked("TEST_FATAL:"+label)
        with self.assertRaisesRegex(r.Blocked,"CALIBRATED_OPERATION_DEADLINE"):
            r.monitored_operation("fixture",0.05,1.0,0.01,operation,fatal=fatal)

    def test_monitored_operation_heartbeat_is_not_progress(self):
        import time
        progress={"bytes":0}
        def operation(update):
            time.sleep(0.03);update(progress);time.sleep(0.03);return "ok"
        result,diagnostics=r.monitored_operation("fixture",1.0,1.0,0.01,operation,lambda:dict(progress),fatal=lambda label:None)
        self.assertEqual(result,"ok");self.assertEqual(diagnostics,[])

    def test_prep_ipc_auth_secret_is_not_in_worker_command_line(self):
        import inspect
        launch=inspect.getsource(r.PrepSupervisor._launch);worker=inspect.getsource(r.prep_worker_main)
        self.assertIn("--prep-auth-handle",launch);self.assertNotIn("--prep-auth=",launch)
        self.assertIn("open_osfhandle",worker);self.assertIn("handle_list",launch)

    def test_streaming_copy_and_prep_paths_reference_watchdog(self):
        import inspect
        publish=inspect.getsource(r.Recovery.publish)
        prepare=inspect.getsource(r.Recovery.prepare_all)
        supervisor=inspect.getsource(r.PrepSupervisor.run)
        self.assertIn("monitored_operation",publish)
        self.assertIn("PrepSupervisor",prepare)
        self.assertIn("NO_PROGRESS_DIAGNOSTIC",supervisor)
        self.assertIn("liveness_fatal_seconds",supervisor)


@unittest.skipUnless(os.name=="nt","Win32 required")
class WindowsCompletenessTests(unittest.TestCase):
    _job_handle=None

    @classmethod
    def setUpClass(cls):
        # Disposable unit-test job. It intentionally has no KILL_ON_CLOSE; the root-loader test covers that exact policy.
        k=r.ctypes.WinDLL("kernel32",use_last_error=True)
        k.CreateJobObjectW.restype=r.HANDLE;k.AssignProcessToJobObject.argtypes=[r.HANDLE,r.HANDLE]
        k.GetCurrentProcess.restype=r.HANDLE
        h=k.CreateJobObjectW(None,None)
        if not h:raise OSError(r.ctypes.get_last_error(),"CreateJobObjectW")
        if not k.AssignProcessToJobObject(h,k.GetCurrentProcess()):
            err=r.ctypes.get_last_error()
            # If test runner is already in an enclosing job, keep it and close unused handle.
            k.CloseHandle(h);h=None
            if os.getpid() not in r.job_members():raise OSError(err,"AssignProcessToJobObject")
        cls._job_handle=h

    @classmethod
    def tearDownClass(cls):
        if cls._job_handle:
            r.ctypes.WinDLL("kernel32",use_last_error=True).CloseHandle(cls._job_handle);cls._job_handle=None

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="precanary-v005-")
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_process_census_global_lease_rejects_second_supervisor(self):
        with r.RecoveryProcessLease():
            with self.assertRaisesRegex(r.Blocked,"LIVE_SUPERVISOR"):r.RecoveryProcessLease()

    def test_process_census_detects_same_runtime_child(self):
        import subprocess,sys,time
        flags=int(getattr(subprocess,"CREATE_NO_WINDOW",0))
        proc=subprocess.Popen([sys.executable,"-I","-S","-c","import time;time.sleep(30)"],creationflags=flags)
        try:
            deadline=time.time()+10;found=False
            while time.time()<deadline:
                result=r.recovery_process_census()
                found=any(item["pid"]==proc.pid for item in result["known_recovery_candidates"])
                if found:break
                time.sleep(0.1)
            self.assertTrue(found)
        finally:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)

    def test_prep_supervisor_spawns_22_concurrent_job_bound_workers(self):
        s0={"days":{}}
        for i in range(22):
            key=f"202609{i+1:02d}"
            s0["days"][key]={"partial":{"bytes":1}}
        profile={"heartbeat_target_seconds":0.2,"liveness_fatal_seconds":5,"terminate_wait_seconds":2,"kill_wait_seconds":2,
                 "streaming_by_size_class":{f"B{i}":5 for i in range(8)}}
        sup=r.PrepSupervisor(Path(r.__file__).read_bytes(),self.root/"scratch",{}, {},s0,profile,22)
        try:
            sup._launch();pids={p.pid for p in sup.processes.values()}
            self.assertEqual(len(pids),22);self.assertTrue(pids<=r.job_members())
            identities={wid:dict(value) for wid,value in sup.owned_process_identities.items()}
            self.assertEqual(len(identities),22)
        finally:
            sup.close()
        final=set(r.job_members())
        for identity in identities.values():
            pid=identity["pid"];created=identity["process_creation_time"]
            if pid in final:self.assertNotEqual(r.process_creation_time(pid),created)
        self.assertEqual(sup.diagnostics[-1]["owned_residuals"],[])

    def test_prep_worker_real_ipc_job_identity_and_cleanup_on_expected_task_error(self):
        key,s0=s0_fixture_one();scratch=self.root/"scratch";scratch.mkdir()
        days={key:{"date_key":key,"month_id":"2026_09"}};months={"2026_09":{}}
        profile={"heartbeat_target_seconds":0.2,"liveness_fatal_seconds":5,"terminate_wait_seconds":2,"kill_wait_seconds":2,
                 "streaming_by_size_class":{f"B{i}":5 for i in range(8)}}
        source=Path(r.__file__).read_bytes()
        sup=r.PrepSupervisor(source,scratch,days,months,s0,profile,1)
        with self.assertRaisesRegex(r.Blocked,"PREP_WORKER_ERROR"):sup.run()
        final=set(r.job_members())
        for identity in sup.owned_process_identities.values():
            pid=identity["pid"];created=identity["process_creation_time"]
            if pid in final:self.assertNotEqual(r.process_creation_time(pid),created)
        self.assertEqual(sup.diagnostics[-1]["owned_residuals"],[])

    def test_root_binding_rejects_fileid_substitution(self):
        store=r.Win32Store();dest=self.root/"dest";scratch=self.root/"scratch";work=self.root/"work"
        for x in (dest,scratch,work):x.mkdir()
        bindings={}
        for name,path in (("dest_root",dest),("scratch_root",scratch),("recovery_root",work)):
            with store.open(path,directory=True) as f:bindings[name]=f.info()
        old=dest.with_name("dest-old");dest.rename(old);dest.mkdir()
        gate={"dest_root":str(dest),"scratch_root":str(scratch),"recovery_root":str(work),"root_bindings":bindings,"production_recovery_authorized":True}
        with self.assertRaisesRegex(r.Blocked,"ROOT_BINDING:dest_root"):r.validate_roots(store,gate)

    def test_reparse_path_is_rejected(self):
        import subprocess
        store=r.Win32Store();target=self.root/"target";target.mkdir();(target/"fixture.bin").write_bytes(b"fixture")
        link=self.root/"link"
        # Directory junction is a reparse point and does not require SeCreateSymbolicLinkPrivilege.
        cmd=os.environ.get("COMSPEC",r"C:\Windows\System32\cmd.exe")
        proc=subprocess.run([cmd,"/d","/c","mklink","/J",str(link),str(target)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,"MANDATORY_REPARSE_FIXTURE_UNAVAILABLE:"+proc.stderr+proc.stdout)
        with self.assertRaisesRegex(r.Blocked,"REPARSE"):store.open(link,directory=True)

    def test_stale_lock_clear_records_process_census_and_is_terminal(self):
        store=r.Win32Store();dest=self.root/"dest";work=self.root/"work";dest.mkdir();work.mkdir()
        path=dest/"TICKSTORE_WRITER.lock"
        with store.open(path,new=True,mutate=True) as lock:
            lock.write(r.json_bytes({"run_id":"old","pid":99999999,"process_creation_time":1,"anchor_sha256":"A"*64}));lock.flush()
        gate={"stale_lock_clear_authorized":True}
        census={"current_pid":os.getpid(),"python_executable":r.sys.executable,"known_recovery_candidates":[],"known_recovery_supervisor_or_workers":0}
        with r.RecoveryProcessLease(),patch.object(r,"process_creation_time",return_value=None),patch.object(r,"recovery_process_census",return_value=census),patch.object(r,"job_members",return_value={os.getpid()}):
            self.assertEqual(r.audit_stale_lock(store,dest,work,gate),0)
        self.assertFalse(path.exists())
        evidence=list(work.glob("stale_lock.*.json"));self.assertEqual(len(evidence),1)
        obj=r.parse(evidence[0].read_bytes())
        self.assertEqual(obj["process_census"]["known_recovery_supervisor_or_workers"],0)
        self.assertEqual(obj["process_census"]["current_job_members"],[os.getpid()])


if __name__=="__main__":unittest.main(verbosity=2)
