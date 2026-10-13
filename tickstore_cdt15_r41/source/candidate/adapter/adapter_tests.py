from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import types
import ctypes
import uuid
import unittest
import zipfile

HERE = pathlib.Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


A = load("runtime_locator_adapter_tested", HERE / "runtime_locator_adapter.py")
I = load("runtime_locator_inline_entry_tested", HERE / "runtime_locator_inline_entry.py")
BINDING = json.loads((HERE / "RUNTIME_LOCATOR_ADAPTER_BINDING.json").read_text())

SID = BINDING["target_snapshot_id"]
SETID = "160a587a-e57f-4c83-ba36-92193537a8b1"
PROVIDER = "b5946137-7b9f-4925-af80-51abd60b20d5"
VOLID = 17470648062550843761
VOLGUID = r"\\?\Volume{8019a5f2-2f2f-47c6-8637-a3e352c13f3a}\\"
HIST = {
    "snapshot_id": SID,
    "snapshot_set_id": SETID,
    "provider_id": PROVIDER,
    "device_object": r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy19",
    "volume_identity": VOLID,
    "purpose": "CANARY_ADMISSION",
}
CURRENT = {**HIST, "device_object": r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy15", "volume_guid": VOLGUID, "attributes": 25}

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_text(cls, value):
        return cls.from_buffer_copy(uuid.UUID(str(value)).bytes_le)

    def text(self):
        return str(uuid.UUID(bytes_le=bytes(self)))


class VSS_SNAPSHOT_PROP(ctypes.Structure):
    _fields_ = [("SnapshotId", GUID), ("Status", ctypes.c_int32)]


class _FakeFree:
    def __init__(self):
        self.argtypes = None
        self.calls = 0

    def __call__(self, _ptr):
        self.calls += 1


class _FakeDll:
    def __init__(self):
        self.VssFreeSnapshotPropertiesInternal = _FakeFree()



def receipt(current=None):
    return {
        "schema": A.RECEIPT_SCHEMA,
        "status": "PASS",
        "stable_identity_parity": True,
        "shadow_root_open": True,
        "shadow_scratch_open": True,
        "snapshot_recreation_required": False,
        "snapshot_state": 12,
        "persistent": True,
        "no_auto_release": True,
        "client_accessible": False,
        "original_volume_guid": VOLGUID,
        "state_status": "FAIL",
        "state_next_node": "D4",
        "canary_scratch_cert": "ABSENT",
        "owner_gate_sha256": BINDING["owner_gate_sha256"],
        "generation": dict(current or CURRENT),
    }


class FakeVSS:
    def __init__(self, current=None, status=12):
        self.current = dict(current or CURRENT)
        self.current_status = int(status)
        self.profile = {"volume_guid": VOLGUID, "drive": "D:"}
        self.original_assert_calls = 0
        self.original_shadow_calls = 0
        self.dll = _FakeDll()

    def properties(self, snapshot_id):
        if A.normalize_guid(snapshot_id) != A.normalize_guid(SID):
            raise RuntimeError("unknown snapshot")
        return dict(self.current)

    def call(self, index, args, sid, prop_ptr):
        if index != 42:
            raise RuntimeError("unexpected call")
        prop_ptr._obj.SnapshotId = GUID.from_text(SID)
        prop_ptr._obj.Status = self.current_status
        return 0

    def close(self):
        pass


class AdapterTests(unittest.TestCase):
    def admitted_fixture(self, td):
        gate={"schema":"RECOVERY_OWNER_GATE_V004","authorized":True,"mode":"CERTIFY_SCRATCH",
            "release_id":"UNIT_TEST_NEVER_AUTHORITY","recovery_source_sha256":BINDING["frozen_release_sha256"],
            "admission_generation":dict(HIST),"scratch_root":"unit-test-only"}
        path=pathlib.Path(td)/"owner_fixture.json";path.write_bytes(A.canonical_json_bytes(gate))
        binding=dict(BINDING);binding["owner_gate_sha256"]=A.sha256_bytes(path.read_bytes())
        authority={"schema":"TICKSTORE_D4_RUN_AUTHORITY_V005","status":"ACTIVE","effect_scope":"D4_ONLY",
            "d5_authorized":False,"full_authorized":False,"owner_gate_path":str(path),
            "owner_gate_sha256":binding["owner_gate_sha256"],"successor_release_sha256":binding["frozen_release_sha256"],"generation":dict(HIST)}
        return gate,binding,authority,path

    def test_admitted_gate_retains_sha_across_resume_release_ids(self):
        with tempfile.TemporaryDirectory() as td:
            gate,binding,authority,path=self.admitted_fixture(td)
            for attempt in range(3):
                selected=A.select_admitted_gate({**gate,"release_id":"RANDOM_ATTEMPT_"+str(attempt)},binding,authority)
                self.assertEqual(A.sha256_bytes(A.canonical_json_bytes(selected)),authority["owner_gate_sha256"])
            self.assertEqual(json.loads(path.read_text()),gate)

    def test_admitted_gate_rejects_root_or_scope_drift(self):
        with tempfile.TemporaryDirectory() as td:
            gate,binding,authority,path=self.admitted_fixture(td)
            with self.assertRaisesRegex(A.AdapterBlocked,"REQUEST_DRIFT:scratch_root"):
                A.select_admitted_gate({**gate,"scratch_root":"other"},binding,authority)
            with self.assertRaisesRegex(A.AdapterBlocked,"SCOPE"):
                A.select_admitted_gate(gate,binding,{**authority,"full_authorized":True})

    def test_admitted_gate_rejects_physical_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            gate,binding,authority,path=self.admitted_fixture(td)
            path.write_bytes(path.read_bytes()+b" ")
            with self.assertRaisesRegex(A.AdapterBlocked,"PHYSICAL_SHA"):
                A.select_admitted_gate(gate,binding,authority)

    def test_01_binding_valid(self):
        self.assertEqual(A.validate_binding(dict(BINDING))["schema"], A.BINDING_SCHEMA)

    def test_02_target_generation(self):
        self.assertTrue(A.is_target_generation(HIST, BINDING))
        self.assertFalse(A.is_target_generation({**HIST, "purpose": "OTHER"}, BINDING))

    def test_03_reconcile_changes_only_locator(self):
        v = FakeVSS()
        g = A.reconcile_generation(v, HIST, BINDING)
        self.assertEqual(g["device_object"], CURRENT["device_object"])
        for key in ("snapshot_id", "snapshot_set_id", "provider_id", "volume_identity", "purpose"):
            self.assertEqual(g[key], HIST[key])

    def test_04_set_drift_blocks(self):
        v = FakeVSS({**CURRENT, "snapshot_set_id": "00000000-0000-0000-0000-000000000001"})
        with self.assertRaisesRegex(A.AdapterBlocked, "snapshot_set_id"):
            A.reconcile_generation(v, HIST, BINDING)

    def test_05_provider_drift_blocks(self):
        v = FakeVSS({**CURRENT, "provider_id": "00000000-0000-0000-0000-000000000002"})
        with self.assertRaisesRegex(A.AdapterBlocked, "provider_id"):
            A.reconcile_generation(v, HIST, BINDING)

    def test_06_volume_identity_drift_blocks(self):
        v = FakeVSS({**CURRENT, "volume_identity": VOLID + 1})
        with self.assertRaisesRegex(A.AdapterBlocked, "volume_identity"):
            A.reconcile_generation(v, HIST, BINDING)

    def test_07_bad_locator_grammar_blocks(self):
        v = FakeVSS({**CURRENT, "device_object": r"D:\not-shadow"})
        with self.assertRaisesRegex(A.AdapterBlocked, "DEVICE_OBJECT_GRAMMAR"):
            A.reconcile_generation(v, HIST, BINDING)

    def test_08_fresh_status_created_passes(self):
        v = FakeVSS(status=12)
        g = A.reconcile_generation(v, HIST, BINDING)
        self.assertEqual(g["device_object"], CURRENT["device_object"])
        self.assertEqual(v.dll.VssFreeSnapshotPropertiesInternal.calls, 1)

    def test_09_fresh_status_not_created_blocks(self):
        v = FakeVSS(status=5)
        with self.assertRaisesRegex(A.AdapterBlocked, "STATUS_NOT_CREATED:5"):
            A.reconcile_generation(v, HIST, BINDING)

    def test_10_expected_attributes_missing_blocks(self):
        v = FakeVSS({**CURRENT, "attributes": 1}, status=12)
        with self.assertRaisesRegex(A.AdapterBlocked, "EXPECTED_ATTRIBUTES"):
            A.reconcile_generation(v, HIST, BINDING)

    def test_11_binding_status_contract_blocks(self):
        bad = dict(BINDING)
        bad["expected_snapshot_status"] = 11
        with self.assertRaisesRegex(A.AdapterBlocked, "EXPECTED_SNAPSHOT_STATUS"):
            A.validate_binding(bad)

    def test_12_receipt_valid(self):
        self.assertEqual(A.validate_locator_receipt(receipt(), BINDING)["status"], "PASS")

    def test_13_receipt_negative_proof_blocks(self):
        r = receipt(); r["shadow_scratch_open"] = False
        with self.assertRaisesRegex(A.AdapterBlocked, "SHADOW_SCRATCH"):
            A.validate_locator_receipt(r, BINDING)

    def _engine_ns(self, physical_receipt):
        class N(FakeVSS):
            def assert_present(self, generation):
                self.original_assert_calls += 1
                if generation.get("device_object") != self.current.get("device_object"):
                    raise RuntimeError("legacy mismatch")
            def shadow_root(self, generation, live_root):
                self.original_shadow_calls += 1
                return pathlib.PureWindowsPath(generation["device_object"] + "\\") / pathlib.PureWindowsPath(live_root).relative_to(pathlib.PureWindowsPath(live_root).anchor)
        def read_json(path, label):
            return json.loads(pathlib.Path(path).read_text())
        def frozen_symbol_stub(*args, **kwargs):
            raise AssertionError("B06R1_FIXTURE_FROZEN_SYMBOL_MUST_BE_REPLACED")
        return {"NativeVSS": N, "_d4r_read_json_file": read_json,
                "_d4r_atomic_receipt": frozen_symbol_stub, "_d4r_atomic": frozen_symbol_stub,
                "_d4r_fail": frozen_symbol_stub}

    def test_14_engine_target_assert_uses_fresh_locator(self):
        r = receipt()
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "receipt.json"; p.write_text(json.dumps(r, sort_keys=True) + "\n")
            ns = self._engine_ns(r)
            A.install_engine_namespace(ns, BINDING, r)
            v = ns["NativeVSS"]()
            v.assert_present(CURRENT)
            self.assertEqual(v.original_assert_calls, 0)

    def test_15_engine_preserves_historical_authority_and_resolves_locator(self):
        r = receipt()
        ns = self._engine_ns(r)
        A.install_engine_namespace(ns, BINDING, r, HIST)
        v = ns["NativeVSS"]()
        before = dict(HIST)
        v.assert_present(HIST)
        resolved = v.shadow_root(HIST, pathlib.PureWindowsPath(r"D:\scratch"))
        self.assertIn(CURRENT["device_object"], str(resolved))
        self.assertEqual(HIST, before)

    def test_authority_identity_drift_blocks(self):
        r = receipt(); ns = self._engine_ns(r)
        with self.assertRaisesRegex(A.AdapterBlocked, "AUTHORITY_IDENTITY_DRIFT"):
            A.install_engine_namespace(ns, BINDING, r, {**HIST, "provider_id": "wrong"})

    def test_receipt_view_retains_authenticated_generation(self):
        r = receipt(); ns = self._engine_ns(r)
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "receipt.json"
            p.write_text(json.dumps(r))
            before = p.read_bytes()
            A.install_engine_namespace(ns, BINDING, r, HIST)
            view = ns["_d4r_read_json_file"](p, "G_CA_RECEIPT_PARSE")
            self.assertEqual(view["generation"], HIST)
            self.assertEqual(p.read_bytes(), before)

    def test_16_engine_non_target_delegates(self):
        r = receipt(); ns = self._engine_ns(r); A.install_engine_namespace(ns, BINDING, r)
        v = ns["NativeVSS"]()
        other = {**CURRENT, "snapshot_id": "00000000-0000-0000-0000-000000000099", "purpose": "OTHER"}
        # Legacy fake only compares locator, so this delegates and succeeds.
        v.assert_present(other)
        self.assertEqual(v.original_assert_calls, 1)

    def test_17_engine_receipt_translation_is_in_memory_only(self):
        r = receipt()
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "receipt.json"; p.write_text(json.dumps(r, sort_keys=True) + "\n")
            ns = self._engine_ns(r); A.install_engine_namespace(ns, BINDING, r)
            compat = ns["_d4r_read_json_file"](p, "G_CA_RECEIPT_PARSE")
            self.assertEqual(compat["schema"], "TICKSTORE_G_CA_RECOVERY_RECEIPT_V001")
            self.assertEqual(json.loads(p.read_text())["schema"], A.RECEIPT_SCHEMA)

    def test_18_engine_double_install_blocks(self):
        r = receipt(); ns = self._engine_ns(r); A.install_engine_namespace(ns, BINDING, r)
        with self.assertRaisesRegex(A.AdapterBlocked, "INSTALLATION_DUPLICATE"):
            A.install_engine_namespace(ns, BINDING, r)

    def test_19_original_symbols_preserved(self):
        r = receipt(); ns = self._engine_ns(r); A.install_engine_namespace(ns, BINDING, r)
        originals = ns["_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_ORIGINALS"]
        self.assertTrue(callable(originals["NativeVSS.assert_present"]))
        self.assertTrue(callable(originals["NativeVSS.shadow_root"]))
        self.assertTrue(callable(originals["_d4r_read_json_file"]))

    def test_20_inline_preverify_pass(self):
        frozen = b"# frozen test source\n"
        local_binding = dict(BINDING); local_binding["frozen_release_sha256"] = hashlib.sha256(frozen).hexdigest().upper()
        adapter_raw = (HERE / "runtime_locator_adapter.py").read_bytes()
        local_binding["adapter_sha256"] = hashlib.sha256(adapter_raw).hexdigest().upper()
        members = {
            "tickstore_publisher_recovery_v004.py": frozen,
            "RUNTIME_LOCATOR_ADAPTER.bin": adapter_raw,
            "RUNTIME_LOCATOR_BINDING.json": (json.dumps(local_binding, sort_keys=True) + "\n").encode(),
            "RUNTIME_LOCATOR_RECEIPT.json": (json.dumps(receipt(), sort_keys=True) + "\n").encode(),
            "OWNER_GATE.json": b"{}\n",
        }
        manifest = {"schema": "RELEASE_MANIFEST_V004", "members": {n: {"sha256": hashlib.sha256(b).hexdigest().upper(), "bytes": len(b)} for n,b in sorted(members.items())}}
        mraw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        members["RELEASE_MANIFEST.json"] = mraw
        payload = {"anchor": {"owner_gate_sha256": hashlib.sha256(members["OWNER_GATE.json"]).hexdigest().upper(), "release_manifest_sha256": hashlib.sha256(mraw).hexdigest().upper(), "recovery_source_sha256": hashlib.sha256(frozen).hexdigest().upper()}, "members": {n: base64.b64encode(b).decode() for n,b in members.items()}}
        _, decoded, parsed = I._preverify_payload(payload)
        self.assertEqual(decoded["tickstore_publisher_recovery_v004.py"], frozen)
        self.assertEqual(parsed["adapter_sha256"], local_binding["adapter_sha256"])

    def test_21_inline_tamper_blocks_before_exec(self):
        frozen = b"# frozen test source\n"
        local_binding = dict(BINDING); local_binding["frozen_release_sha256"] = hashlib.sha256(frozen).hexdigest().upper()
        adapter_raw = (HERE / "runtime_locator_adapter.py").read_bytes()
        local_binding["adapter_sha256"] = hashlib.sha256(adapter_raw).hexdigest().upper()
        members = {
            "tickstore_publisher_recovery_v004.py": frozen,
            "RUNTIME_LOCATOR_ADAPTER.bin": adapter_raw + b"#tamper",
            "RUNTIME_LOCATOR_BINDING.json": (json.dumps(local_binding, sort_keys=True) + "\n").encode(),
            "RUNTIME_LOCATOR_RECEIPT.json": (json.dumps(receipt(), sort_keys=True) + "\n").encode(),
            "OWNER_GATE.json": b"{}\n",
        }
        manifest = {"schema": "RELEASE_MANIFEST_V004", "members": {n: {"sha256": hashlib.sha256(b).hexdigest().upper(), "bytes": len(b)} for n,b in sorted(members.items())}}
        mraw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(); members["RELEASE_MANIFEST.json"] = mraw
        payload = {"anchor": {"owner_gate_sha256": hashlib.sha256(members["OWNER_GATE.json"]).hexdigest().upper(), "release_manifest_sha256": hashlib.sha256(mraw).hexdigest().upper(), "recovery_source_sha256": hashlib.sha256(frozen).hexdigest().upper()}, "members": {n: base64.b64encode(b).decode() for n,b in members.items()}}
        with self.assertRaisesRegex(RuntimeError, "ADAPTER_HASH"):
            I._preverify_payload(payload)

    def test_22_orchestrator_bundle_injects_data_only_for_target(self):
        r = receipt()
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            for name in ("runtime_locator_adapter.py", "runtime_locator_inline_entry.py", "Launch-TickstoreBundle-Adapter.ps1", "RUNTIME_LOCATOR_ADAPTER_BINDING.json"):
                (td / name).write_bytes((HERE / name).read_bytes())
            rp = td / "receipt.json"; rp.write_text(json.dumps(r, sort_keys=True) + "\n")
            class O:
                def n_d4(self): return "legacy"
                def bundle(self, name, gate, extra=None, certs=None, deadline=None, noledger=False):
                    self.last_extra = dict(extra or {}); return "bundle", "anchor", gate
                def launch(self, *a, **k): return "legacy-launch"
            ns = {"O": O, "atomj": lambda *a,**k:None, "shab": lambda b:hashlib.sha256(b).hexdigest().upper(), "subprocess": __import__("subprocess")}
            A.install_orchestrator_namespace(ns, BINDING, td, rp)
            o=O(); gate={"mode":"CERTIFY_SCRATCH","admission_generation":CURRENT}
            o.bundle("x",gate)
            self.assertEqual(set(o.last_extra), {"RUNTIME_LOCATOR_ADAPTER.bin","RUNTIME_LOCATOR_BINDING.json","RUNTIME_LOCATOR_RECEIPT.json"})
            o.bundle("x",{"mode":"CERTIFY_CANONICAL","admission_generation":CURRENT})
            self.assertEqual(o.last_extra,{})

    def test_23_loader_is_adapter_source_not_frozen_source(self):
        text=(HERE/"INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$tickstoreAdapterSource",text)
        self.assertIn("Launch($PythonPath,$tickstoreAdapterSource,$tickstorePayload)",text)
        self.assertIn("SOURCE_HASH_MISMATCH",text)

    def test_24_no_effectful_d4_surface_in_adapter_package(self):
        for name in ("runtime_locator_adapter.py","runtime_locator_inline_entry.py","runtime_locator_orchestrator_entry.py","Launch-TickstoreBundle-Adapter.ps1"):
            text=(HERE/name).read_text(encoding="utf-8-sig")
            self.assertNotIn("run -Until D4",text)
            self.assertNotIn("delete_generation(",text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
