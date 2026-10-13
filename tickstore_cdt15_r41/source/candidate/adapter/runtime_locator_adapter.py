from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import re
from copy import deepcopy

ADAPTER_SCHEMA = "TICKSTORE_G_CA_RUNTIME_LOCATOR_ADAPTER_V002"
RECEIPT_SCHEMA = "TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT_V001"
BINDING_SCHEMA = "TICKSTORE_G_CA_RUNTIME_LOCATOR_ADAPTER_BINDING_V002"
_TARGET_FIELDS = ("snapshot_id", "snapshot_set_id", "provider_id", "volume_identity")


class AdapterBlocked(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AdapterBlocked(reason)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def sha256_file(path: os.PathLike[str] | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def canonical_json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def normalize_guid(value: object) -> str:
    return str(value or "").strip().strip("{}").lower()


def normalize_path(value: object) -> str:
    return str(value or "").rstrip("\\/").lower()


def validate_binding(binding: dict) -> dict:
    require(isinstance(binding, dict), "ADAPTER_BINDING_TYPE")
    require(binding.get("schema") == BINDING_SCHEMA, "ADAPTER_BINDING_SCHEMA")
    for key in (
        "frozen_release_sha256",
        "frozen_orchestrator_sha256",
        "adapter_sha256",
        "inline_entry_sha256",
        "adapted_loader_sha256",
        "adapted_launch_sha256",
    ):
        value = str(binding.get(key, "")).upper()
        require(re.fullmatch(r"[0-9A-F]{64}", value) is not None, "ADAPTER_BINDING_HASH:" + key)
    require(normalize_guid(binding.get("target_snapshot_id")), "ADAPTER_TARGET_SNAPSHOT_ID")
    require(binding.get("target_purpose") == "CANARY_ADMISSION", "ADAPTER_TARGET_PURPOSE")
    require(binding.get("locator_receipt_schema") == RECEIPT_SCHEMA, "ADAPTER_RECEIPT_SCHEMA_BINDING")
    require(str(binding.get("expected_volume_guid", "")).lower().startswith("\\\\?\\volume{"), "ADAPTER_EXPECTED_VOLUME_GUID")
    require(isinstance(binding.get("expected_volume_identity"), int), "ADAPTER_EXPECTED_VOLUME_IDENTITY")
    require(binding.get("expected_snapshot_status") == 12, "ADAPTER_EXPECTED_SNAPSHOT_STATUS")
    require(binding.get("expected_attributes_mask") == 25, "ADAPTER_EXPECTED_ATTRIBUTES_MASK")
    return binding


def is_target_generation(generation: object, binding: dict) -> bool:
    if not isinstance(generation, dict):
        return False
    return (
        normalize_guid(generation.get("snapshot_id")) == normalize_guid(binding["target_snapshot_id"])
        and generation.get("purpose") == binding["target_purpose"]
    )


def _validate_stable_identity(current: dict, generation: dict, vss: object, binding: dict) -> None:
    for key in _TARGET_FIELDS:
        if key == "snapshot_id":
            ok = normalize_guid(current.get(key)) == normalize_guid(generation.get(key))
        elif key in ("snapshot_set_id", "provider_id"):
            ok = normalize_guid(current.get(key)) == normalize_guid(generation.get(key))
        else:
            ok = current.get(key) == generation.get(key)
        require(ok, "RUNTIME_LOCATOR_STABLE_IDENTITY_DRIFT:" + key)
    profile = getattr(vss, "profile", {})
    if isinstance(profile, dict) and profile.get("volume_guid") is not None and current.get("volume_guid") is not None:
        require(
            normalize_path(current.get("volume_guid")) == normalize_path(profile.get("volume_guid")),
            "RUNTIME_LOCATOR_VOLUME_GUID_DRIFT",
        )
    attributes = current.get("attributes")
    mask = binding["expected_attributes_mask"]
    require(
        isinstance(attributes, int) and (attributes & mask) == mask,
        "RUNTIME_LOCATOR_EXPECTED_ATTRIBUTES",
    )
    require(
        re.fullmatch(r"\\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy[0-9]+", str(current.get("device_object", "")))
        is not None,
        "RUNTIME_LOCATOR_DEVICE_OBJECT_GRAMMAR",
    )


def _query_fresh_snapshot_status(vss: object, snapshot_id: str) -> int:
    # Frozen V002R22 NativeVSS.properties() obtains VSS_SNAPSHOT_PROP but drops Status.
    # Query exactly that native property again, using the frozen class ABI symbols.
    properties_fn = getattr(type(vss), "properties", None)
    native_globals = getattr(properties_fn, "__globals__", {})
    Prop = native_globals.get("VSS_SNAPSHOT_PROP")
    Guid = native_globals.get("GUID")
    ctypes_mod = native_globals.get("ctypes")
    require(Prop is not None and Guid is not None and ctypes_mod is not None, "RUNTIME_LOCATOR_STATUS_NATIVE_SYMBOLS")
    require(callable(getattr(Guid, "from_text", None)), "RUNTIME_LOCATOR_STATUS_GUID_FACTORY")
    prop = Prop()
    sid = Guid.from_text(snapshot_id)
    vss.call(42, [Guid, ctypes_mod.POINTER(Prop)], sid, ctypes_mod.byref(prop))
    try:
        require(
            normalize_guid(prop.SnapshotId.text()) == normalize_guid(snapshot_id),
            "RUNTIME_LOCATOR_STATUS_SNAPSHOT_ID",
        )
        return int(prop.Status)
    finally:
        free = vss.dll.VssFreeSnapshotPropertiesInternal
        free.argtypes = [ctypes_mod.POINTER(Prop)]
        free(ctypes_mod.byref(prop))


def reconcile_generation(vss: object, historical_or_runtime_generation: dict, binding: dict) -> dict:
    require(is_target_generation(historical_or_runtime_generation, binding), "RUNTIME_LOCATOR_TARGET_GENERATION")
    current = vss.properties(historical_or_runtime_generation["snapshot_id"])
    require(isinstance(current, dict), "RUNTIME_LOCATOR_PROPERTIES_TYPE")
    _validate_stable_identity(current, historical_or_runtime_generation, vss, binding)
    fresh_status = _query_fresh_snapshot_status(vss, historical_or_runtime_generation["snapshot_id"])
    require(
        fresh_status == binding["expected_snapshot_status"],
        "RUNTIME_LOCATOR_STATUS_NOT_CREATED:" + str(fresh_status),
    )
    result = dict(historical_or_runtime_generation)
    result["device_object"] = current["device_object"]
    result["purpose"] = historical_or_runtime_generation["purpose"]
    return result

def validate_locator_receipt(receipt: dict, binding: dict) -> dict:
    require(isinstance(receipt, dict), "LOCATOR_RECEIPT_TYPE")
    require(receipt.get("schema") == RECEIPT_SCHEMA, "LOCATOR_RECEIPT_SCHEMA")
    require(receipt.get("status") == "PASS", "LOCATOR_RECEIPT_STATUS")
    require(receipt.get("stable_identity_parity") is True, "LOCATOR_RECEIPT_STABLE_IDENTITY")
    require(receipt.get("shadow_root_open") is True, "LOCATOR_RECEIPT_SHADOW_ROOT")
    require(receipt.get("shadow_scratch_open") is True, "LOCATOR_RECEIPT_SHADOW_SCRATCH")
    require(receipt.get("snapshot_recreation_required") is False, "LOCATOR_RECEIPT_RECREATE")
    require(receipt.get("snapshot_state") == 12, "LOCATOR_RECEIPT_SNAPSHOT_STATE")
    require(receipt.get("persistent") is True, "LOCATOR_RECEIPT_PERSISTENT")
    require(receipt.get("no_auto_release") is True, "LOCATOR_RECEIPT_NO_AUTO_RELEASE")
    require(receipt.get("client_accessible") is False, "LOCATOR_RECEIPT_CLIENT_ACCESSIBLE")
    require(normalize_path(receipt.get("original_volume_guid")) == normalize_path(binding["expected_volume_guid"]), "LOCATOR_RECEIPT_VOLUME_GUID")
    require(receipt.get("state_status") == "FAIL", "LOCATOR_RECEIPT_STATE_STATUS")
    require(receipt.get("state_next_node") == "D4", "LOCATOR_RECEIPT_NEXT_NODE")
    require(receipt.get("canary_scratch_cert") == "ABSENT", "LOCATOR_RECEIPT_CERT")
    require(str(receipt.get("owner_gate_sha256", "")).upper() == str(binding["owner_gate_sha256"]).upper(), "LOCATOR_RECEIPT_OWNER")
    generation = receipt.get("generation")
    require(is_target_generation(generation, binding), "LOCATOR_RECEIPT_GENERATION_TARGET")
    for key in (*_TARGET_FIELDS, "device_object", "purpose"):
        require(str(generation.get(key, "")) != "", "LOCATOR_RECEIPT_GENERATION_FIELD:" + key)
    require(generation.get("volume_identity") == binding["expected_volume_identity"], "LOCATOR_RECEIPT_VOLUME_IDENTITY")
    require(
        re.fullmatch(r"\\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy[0-9]+", str(generation.get("device_object", "")))
        is not None,
        "LOCATOR_RECEIPT_DEVICE_OBJECT_GRAMMAR",
    )
    return receipt


def _receipt_compatibility_view(receipt: dict) -> dict:
    return {
        "schema": "TICKSTORE_G_CA_RECOVERY_RECEIPT_V001",
        "status": "PASS",
        "owner_gate_sha256": receipt["owner_gate_sha256"],
        "generation": receipt["generation"],
        "state_status": receipt["state_status"],
        "state_next_node": receipt["state_next_node"],
        "canary_scratch_cert": receipt["canary_scratch_cert"],
        "runtime_adapter_translation": ADAPTER_SCHEMA,
    }


_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_link_or_reparse(st: os.stat_result) -> bool:
    import stat as _stat
    return _stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _fsync_directory(directory: pathlib.Path) -> None:
    try:
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, PermissionError):
        pass


def make_no_clobber_receipt_writer(fail):
    """B06-03: immutable receipt publication with create-if-absent semantics.

    os.link never replaces an existing directory entry (POSIX link(2), Win32
    CreateHardLinkW). A receipt, link or reparse point that appears at any time
    before publication is preserved and the writer fails closed. Temporaries
    are unique per attempt and only the creator removes its own; temporaries of
    other, possibly live, writers are never deleted (V002R22 swept them).
    """
    def atomic_receipt(path, data):
        import time
        import uuid
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(path):
            fail("RECEIPT_ALREADY_EXISTS:" + path.name)
        tmp = path.with_name(path.name + ".pending." + str(os.getpid()) + "." + str(time.time_ns()) + "." + uuid.uuid4().hex)
        created = False
        try:
            with open(tmp, "xb") as f:
                created = True
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(str(tmp), str(path))
            except FileExistsError:
                fail("RECEIPT_RACE_WINNER_PRESERVED:" + path.name)
            except OSError as exc:
                fail("RECEIPT_NO_CLOBBER_PUBLISH:" + path.name + ":" + type(exc).__name__)
            published = os.lstat(path)
            # Same stat call on both names (only this attempt removes its own temp).
            if _is_link_or_reparse(published) or not os.path.samestat(published, os.lstat(tmp)):
                fail("RECEIPT_PUBLISHED_IDENTITY:" + path.name)
            with open(path, "rb+") as committed:
                os.fsync(committed.fileno())
            _fsync_directory(path.parent)
            if hashlib.sha256(path.read_bytes()).hexdigest().upper() != hashlib.sha256(data).hexdigest().upper():
                fail("RECEIPT_POSTWRITE_SHA:" + path.name)
        finally:
            if created:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    return atomic_receipt


def make_attempt_scoped_atomic():
    """B06-04: one exclusive temporary per attempt, removed by its creator on failure."""
    def atomic(path, data):
        import uuid
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp." + str(os.getpid()) + "." + uuid.uuid4().hex)
        owned = False
        try:
            with open(tmp, "xb") as f:
                owned = True
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(path))
            owned = False
        finally:
            if owned:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        with open(path, "rb+") as committed:
            os.fsync(committed.fileno())
        _fsync_directory(path.parent)
    return atomic


def install_engine_namespace(ns: dict, binding: dict, receipt: dict, authority_generation: dict | None = None) -> None:
    validate_binding(binding)
    validate_locator_receipt(receipt, binding)
    # The authenticated owner gate carries the logical generation used by HMAC
    # checkpoints. A Windows locator may move without changing that generation.
    authority_generation = deepcopy(authority_generation if authority_generation is not None else receipt["generation"])
    require(is_target_generation(authority_generation, binding), "ADAPTER_AUTHORITY_GENERATION_TARGET")
    for key in (*_TARGET_FIELDS, "purpose"):
        require(authority_generation.get(key) == receipt["generation"].get(key), "ADAPTER_AUTHORITY_IDENTITY_DRIFT:" + key)
    require(not ns.get("_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_INSTALLED", False), "ADAPTER_ENGINE_INSTALLATION_DUPLICATE")
    NativeVSS = ns.get("NativeVSS")
    require(NativeVSS is not None, "ADAPTER_ENGINE_NATIVEVSS_MISSING")
    original_assert_present = NativeVSS.assert_present
    original_shadow_root = NativeVSS.shadow_root
    original_read_json = ns.get("_d4r_read_json_file")
    require(callable(original_read_json), "ADAPTER_ENGINE_D4R_READ_JSON_MISSING")
    original_atomic_receipt = ns.get("_d4r_atomic_receipt")
    original_atomic = ns.get("_d4r_atomic")
    engine_fail = ns.get("_d4r_fail")
    require(callable(original_atomic_receipt), "ADAPTER_ENGINE_D4R_ATOMIC_RECEIPT_MISSING")
    require(callable(original_atomic), "ADAPTER_ENGINE_D4R_ATOMIC_MISSING")
    require(callable(engine_fail), "ADAPTER_ENGINE_D4R_FAIL_MISSING")
    ns["_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_ORIGINALS"] = {
        "NativeVSS.assert_present": original_assert_present,
        "NativeVSS.shadow_root": original_shadow_root,
        "_d4r_read_json_file": original_read_json,
        "_d4r_atomic_receipt": original_atomic_receipt,
        "_d4r_atomic": original_atomic,
    }

    def adapted_assert_present(self, generation):
        if not is_target_generation(generation, binding):
            return original_assert_present(self, generation)
        # Requery native status and stable identity; only shadow_root uses the
        # current locator. Do not replace a signed checkpoint generation.
        reconcile_generation(self, generation, binding)
        return None

    def adapted_shadow_root(self, generation, live_root):
        if not is_target_generation(generation, binding):
            return original_shadow_root(self, generation, live_root)
        current = reconcile_generation(self, generation, binding)
        return original_shadow_root(self, current, live_root)

    def adapted_read_json_file(path, label):
        obj = original_read_json(path, label)
        if label != "G_CA_RECEIPT_PARSE":
            return obj
        physical = validate_locator_receipt(obj, binding)
        require(canonical_json_bytes(physical) == canonical_json_bytes(receipt), "LOCATOR_RECEIPT_INLINE_PHYSICAL_MISMATCH")
        view = _receipt_compatibility_view(physical)
        view["generation"] = deepcopy(authority_generation)
        return view

    NativeVSS.assert_present = adapted_assert_present
    NativeVSS.shadow_root = adapted_shadow_root
    ns["_d4r_read_json_file"] = adapted_read_json_file
    # Frozen V002R22 bytes stay unchanged; their call sites resolve these globals at call time.
    ns["_d4r_atomic_receipt"] = make_no_clobber_receipt_writer(engine_fail)
    ns["_d4r_atomic"] = make_attempt_scoped_atomic()
    ns["_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_INSTALLED"] = True
    ns["_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_SCHEMA"] = ADAPTER_SCHEMA


def select_admitted_gate(requested: dict, binding: dict, authority: dict) -> dict:
    """Reuse the run's anchor bytes; never mint, alter or re-sign a gate per resume.

    B06R3 / rev. 37 §13.2 (option B): the anchor is the checkpoint's identity, not a
    production approval. Each check below is either identity continuity or a data
    constraint that the frozen V002R22 dispatch_bootstrap enforces on OWNER_GATE.json.
    """
    require(authority.get("schema") == "TICKSTORE_D4_RUN_AUTHORITY_V005" and authority.get("status") == "ACTIVE", "ADMITTED_GATE_AUTHORITY")
    require(authority.get("effect_scope") == "D4_ONLY" and authority.get("d5_authorized") is False and authority.get("full_authorized") is False, "ADMITTED_GATE_SCOPE")
    raw = pathlib.Path(authority["owner_gate_path"]).read_bytes()
    require(sha256_bytes(raw) == authority.get("owner_gate_sha256") == binding["owner_gate_sha256"], "ADMITTED_GATE_PHYSICAL_SHA")
    gate = json.loads(raw.decode("utf-8"))
    require(canonical_json_bytes(gate) == raw, "ADMITTED_GATE_CANONICAL_BYTES")
    require(gate.get("schema") == "RECOVERY_OWNER_GATE_V004" and gate.get("authorized") is True and gate.get("mode") == "CERTIFY_SCRATCH", "ANCHOR_FROZEN_ENGINE_FORMAT")
    require(gate.get("recovery_source_sha256") == authority.get("successor_release_sha256") == binding["frozen_release_sha256"], "ANCHOR_FROZEN_ENGINE_SOURCE")
    require(gate.get("admission_generation") == authority.get("generation"), "ADMITTED_GATE_GENERATION")
    require(set(gate) == set(requested), "ADMITTED_GATE_FIELD_SET")
    for key in requested:
        if key != "release_id":
            require(gate[key] == requested[key], "ADMITTED_GATE_REQUEST_DRIFT:" + key)
    require(isinstance(gate.get("release_id"), str) and bool(gate["release_id"]), "ADMITTED_GATE_RELEASE_ID")
    return gate


def install_orchestrator_namespace(ns: dict, binding: dict, adapter_dir: os.PathLike[str] | str, receipt_path: os.PathLike[str] | str, *, post_d4=False) -> None:
    validate_binding(binding)
    if post_d4:
        require(os.environ.get("TICKSTORE_D4_RESUME_ENABLE") != "1", "POST_D4_CANNOT_USE_D4_AUTHORITY")
    require(not ns.get("_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_INSTALLED", False), "ADAPTER_ORCHESTRATOR_INSTALLATION_DUPLICATE")
    O = ns.get("O")
    require(O is not None, "ADAPTER_ORCHESTRATOR_CLASS_MISSING")
    original_n_d4 = O.n_d4
    original_bundle = O.bundle
    original_launch = O.launch
    ns["_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_ORIGINALS"] = {
        "O.n_d4": original_n_d4,
        "O.bundle": original_bundle,
        "O.launch": original_launch,
    }
    adapter_dir = pathlib.Path(adapter_dir)
    receipt_path = pathlib.Path(receipt_path)
    adapter_bytes = (adapter_dir / "runtime_locator_adapter.py").read_bytes()
    binding_bytes = (adapter_dir / "RUNTIME_LOCATOR_ADAPTER_BINDING.json").read_bytes()
    inline_entry_path = adapter_dir / "runtime_locator_inline_entry.py"
    adapted_launch_path = adapter_dir / "Launch-TickstoreBundle-Adapter.ps1"
    require(sha256_bytes(adapter_bytes) == binding["adapter_sha256"], "ADAPTER_SOURCE_SHA")
    # B06-02: the binding injected into the bundle is the binding object admitted by the entry.
    require(json.loads(binding_bytes.decode("utf-8")) == binding, "ADAPTER_BINDING_BYTES_NOT_ADMITTED")
    require(sha256_bytes(inline_entry_path.read_bytes()) == binding["inline_entry_sha256"], "ADAPTER_INLINE_ENTRY_SHA")
    require(sha256_bytes(adapted_launch_path.read_bytes()) == binding["adapted_launch_sha256"], "ADAPTER_LAUNCH_SHA")

    def read_receipt() -> dict:
        raw = receipt_path.read_bytes()
        obj = json.loads(raw.decode("utf-8-sig"))
        validate_locator_receipt(obj, binding)
        return obj

    def adapted_n_d4(self):
        historical = self.st.d.get("G_CA")
        if not is_target_generation(historical, binding):
            # B06R2 route closure: D4 resume never reaches the frozen n_d4/bare helpers.
            require(os.environ.get("TICKSTORE_D4_RESUME_ENABLE") != "1", "ADAPTER_D4_RESUME_NON_TARGET_N_D4_FORBIDDEN")
            return original_n_d4(self)
        receipt = read_receipt()
        runtime_generation = deepcopy(receipt["generation"])
        # Fresh requery immediately before shadow access; no STATE.G_CA mutation.
        r = self.rootsc()
        st = self.eng.Win32Store()
        v = self.eng.NativeVSS(st, self.st.d["cprof"])
        try:
            fresh = reconcile_generation(v, historical, binding)
            for key in (*_TARGET_FIELDS, "device_object", "purpose"):
                require(str(fresh.get(key)) == str(runtime_generation.get(key)), "LOCATOR_RECEIPT_RUNTIME_DRIFT:" + key)
            inv = self.invs0(v.shadow_root(runtime_generation, r["scratch"]))
        finally:
            v.close()
        cert = self.cert("CERTIFY_SCRATCH", r, historical, self.st.d["cprof"], s0=inv)
        self.st.d["canary_scratch_cert"] = base64.b64encode(cert).decode()
        ns["atomj"](self.st.sp, self.st.d)
        return {"cert_sha256": ns["shab"](cert)}

    def adapted_bundle(self, name, gate, extra=None, certs=None, deadline=None, noledger=False):
        generation = gate.get("admission_generation") if isinstance(gate, dict) else None
        adapted_modes = {"CERTIFY_SCRATCH"}
        if post_d4:
            adapted_modes.update({"CERTIFY_CANONICAL", "MANIFEST_REDERIVATION", "LIVE_EQUALITY", "RECOVER", "STALE_LOCK"})
        if not (gate.get("mode") in adapted_modes and is_target_generation(generation, binding)):
            # D4 resume helpers are only hardened inside the adapted engine namespace.
            require(os.environ.get("TICKSTORE_D4_RESUME_ENABLE") != "1", "ADAPTER_D4_RESUME_NON_TARGET_BUNDLE_FORBIDDEN")
            return original_bundle(self, name, gate, extra=extra, certs=certs, deadline=deadline, noledger=noledger)
        receipt_raw = receipt_path.read_bytes()
        receipt_obj = json.loads(receipt_raw.decode("utf-8-sig"))
        validate_locator_receipt(receipt_obj, binding)
        if os.environ.get("TICKSTORE_D4_RESUME_ENABLE") == "1":
            authority_path = pathlib.Path(os.environ["TICKSTORE_D4_RUN_AUTHORITY"])
            authority_raw = authority_path.read_bytes()  # B06R2: hashed bytes are the parsed bytes
            require(sha256_bytes(authority_raw) == os.environ["TICKSTORE_D4_RUN_AUTHORITY_SHA256"].upper(), "ADMITTED_AUTHORITY_SHA")
            authority = json.loads(authority_raw.decode("ascii"))
            require(not certs and deadline is None, "ADMITTED_GATE_EXTRA_MUTATION_FORBIDDEN")
            gate = select_admitted_gate(gate, binding, authority)
        injected = dict(extra or {})
        injected["RUNTIME_LOCATOR_ADAPTER.bin"] = adapter_bytes
        injected["RUNTIME_LOCATOR_BINDING.json"] = binding_bytes
        injected["RUNTIME_LOCATOR_RECEIPT.json"] = receipt_raw
        return original_bundle(self, name, gate, extra=injected, certs=certs, deadline=deadline, noledger=noledger)

    def _bundle_is_target(bundle_path: os.PathLike[str] | str) -> bool:
        import zipfile
        with zipfile.ZipFile(bundle_path, "r") as z:
            names = set(z.namelist())
            return {
                "RUNTIME_LOCATOR_ADAPTER.bin",
                "RUNTIME_LOCATOR_BINDING.json",
                "RUNTIME_LOCATOR_RECEIPT.json",
            } <= names

    def adapted_launch(self, bundle_path, anchor_path, label, async_=False):
        if not _bundle_is_target(bundle_path):
            # B06R2 route closure: the frozen launcher/loader never runs a D4 resume engine.
            require(os.environ.get("TICKSTORE_D4_RESUME_ENABLE") != "1", "ADAPTER_D4_RESUME_NON_TARGET_LAUNCH_FORBIDDEN")
            return original_launch(self, bundle_path, anchor_path, label, async_=async_)
        so = self.rd / f"{label}.stdout.log"
        se = self.rd / f"{label}.stderr.log"
        fo = open(so, "wb")
        fe = open(se, "wb")
        cmd = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(adapted_launch_path),
            "-PackageRoot", str(self.pkg), "-BundlePath", str(bundle_path), "-AnchorPath", str(anchor_path),
            "-PythonPath", self.py, "-AdapterEntryPath", str(inline_entry_path),
        ]
        p = ns["subprocess"].Popen(cmd, stdout=fo, stderr=fe, creationflags=0x08000000)
        if async_:
            return p, fo, fe, so, se
        code = p.wait()
        fo.close(); fe.close()
        return code, so, se

    O.n_d4 = adapted_n_d4
    O.bundle = adapted_bundle
    O.launch = adapted_launch
    ns["_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_INSTALLED"] = True
    ns["_TICKSTORE_RUNTIME_LOCATOR_ADAPTER_SCHEMA"] = ADAPTER_SCHEMA
