from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys


def sha_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def parse_d4_arguments(argv: list[str]) -> argparse.Namespace:
    """Constrain dispatch before reading paths or executing either namespace.

    Even frozen 'status' and 'plan' construct State and rewrite STATE.json.
    Omitting --until in the frozen runner defaults to E9, not D4.
    """
    class Once(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None):
            if getattr(namespace, self.dest, None) is not None:
                parser.error("ADAPTER_ENTRY_DUPLICATE_ARGUMENT:" + str(option_string))
            setattr(namespace, self.dest, value)

    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("command", choices=("run", "resume"))
    parser.add_argument("--until", required=True, choices=("D4",), action=Once)
    parser.add_argument("--package", required=True, action=Once)
    parser.add_argument("--python", required=True, action=Once)
    return parser.parse_args(argv)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_link_or_reparse(st: os.stat_result) -> bool:
    import stat as _stat
    return _stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _lexical(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _ident(st: os.stat_result) -> tuple:
    # Physical identity and version of one directory entry, taken with lstat only.
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def require_no_link_chain(path, label: str) -> None:
    """B06R2: reject a symlink, junction or other reparse point at the path or any ancestor."""
    p = pathlib.Path(_lexical(path))
    for part in (p, *p.parents):
        try:
            st = os.lstat(part)
        except FileNotFoundError:
            raise RuntimeError(label + ("_MISSING" if part == p else "_ANCESTOR_MISSING")) from None
        if _is_link_or_reparse(st):
            raise RuntimeError(label + "_LINK_OR_REPARSE")


def read_pinned_regular(path, label: str) -> tuple:
    """Read a regular file once; its identity/version must be the same before and after the read."""
    require_no_link_chain(path, label)
    before = os.lstat(path)
    try:
        raw = pathlib.Path(path).read_bytes()
    except FileNotFoundError:
        raise RuntimeError(label + "_MISSING") from None
    try:
        after = os.lstat(path)
    except FileNotFoundError:
        raise RuntimeError(label + "_CHANGED_DURING_READ") from None
    if _is_link_or_reparse(after) or _ident(before) != _ident(after) or len(raw) != after.st_size:
        raise RuntimeError(label + "_CHANGED_DURING_READ")
    return raw, _ident(after)


class AdmittedStart:
    """Objects admitted at the D4 start boundary; later consumers use these, not re-reads."""
    __slots__ = ("state_path", "control_root", "config_path", "config_raw", "config_sha256",
                 "config_ident", "state_raw", "state_ident")

    def __init__(self, state_path, control_root, config_path, config_raw, config_sha256,
                 config_ident=None, state_raw=None, state_ident=None):
        self.state_path = state_path
        self.control_root = control_root
        self.config_path = config_path
        self.config_raw = bytes(config_raw)
        self.config_sha256 = config_sha256
        self.config_ident = config_ident
        self.state_raw = None if state_raw is None else bytes(state_raw)
        self.state_ident = state_ident


class RunIdentity:
    """RUN_AUTHORITY and its checkpoint anchor, each read once (hashed bytes = parsed bytes)."""
    __slots__ = ("ra", "ra_raw", "ra_sha", "anchor_raw", "anchor_sha", "anchor")

    def __init__(self, ra, ra_raw, anchor_raw):
        self.ra = ra
        self.ra_raw = bytes(ra_raw)
        self.ra_sha = _sha(ra_raw)
        self.anchor_raw = bytes(anchor_raw)
        self.anchor_sha = _sha(anchor_raw)
        self.anchor = json.loads(self.anchor_raw.decode("utf-8-sig"))


def load_run_identity(binding: dict) -> RunIdentity:
    """Load the D4 run identity before the frozen O constructor can touch STATE.

    B06R3 / policy rev. 37 §13.2 (decision: option B): OWNER_GATE.json is no
    longer an autonomous production approval. The historical gate is read only
    as the technical identity anchor of the checkpoint (its SHA-256 is part of
    RUN_AUTHORITY and of every signed checkpoint payload). Every property of the
    anchor is judged later by evaluate_resume_identity, as a frozen-engine data
    constraint or as identity continuity, never as an approval.
    """
    if os.environ.get("TICKSTORE_D4_RESUME_ENABLE") != "1":
        raise RuntimeError("ADAPTER_ENTRY_D4_AUTHORITY_REQUIRED")
    authority = pathlib.Path(os.environ["TICKSTORE_D4_RUN_AUTHORITY"])
    authority_raw, _ = read_pinned_regular(authority, "ADAPTER_ENTRY_AUTHORITY")
    if _sha(authority_raw) != os.environ["TICKSTORE_D4_RUN_AUTHORITY_SHA256"].upper():
        raise RuntimeError("ADAPTER_ENTRY_AUTHORITY_SHA")
    ra = json.loads(authority_raw.decode("ascii"))
    if (ra.get("schema") != "TICKSTORE_D4_RUN_AUTHORITY_V005" or ra.get("status") != "ACTIVE"
        or ra.get("effect_scope") != "D4_ONLY" or ra.get("d5_authorized") is not False
        or ra.get("full_authorized") is not False):
        raise RuntimeError("ADAPTER_ENTRY_AUTHORITY_SCOPE")
    anchor_raw, _ = read_pinned_regular(ra["owner_gate_path"], "ADAPTER_ENTRY_ANCHOR")
    if _sha(anchor_raw) != ra.get("owner_gate_sha256"):
        raise RuntimeError("ADAPTER_ENTRY_ANCHOR_SHA")
    return RunIdentity(ra, authority_raw, anchor_raw)


def validate_first_admission_commit(authority: dict, state_raw: bytes, state_path=None) -> None:
    """Authenticate a newly materialized instance before any frozen constructor.

    Historical authorities remain under their existing reconciliation contract.
    A first-admission authority can only refer to a complete, byte-bound support
    directory, and absence of checkpoint requires the original physical STATE.
    """
    manifest_path = authority.get("first_admission_manifest_path")
    if manifest_path is None:
        return
    path = pathlib.Path(manifest_path)
    raw, _ = read_pinned_regular(path, "FIRST_ADMISSION_COMMIT")
    if _sha(raw) != authority.get("first_admission_manifest_sha256"):
        raise RuntimeError("FIRST_ADMISSION_COMMIT_SHA")
    manifest = json.loads(raw.decode("ascii"))
    expected = {"TECHNICAL_EXECUTION_DESCRIPTOR.json", "G_CA_RUNTIME_LOCATOR.json",
                "RUNTIME_LOCATOR_ADAPTER_BINDING.json", "runtime_locator_adapter.py",
                "runtime_locator_orchestrator_entry.py", "runtime_locator_inline_entry.py",
                "INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1", "Launch-TickstoreBundle-Adapter.ps1"}
    if (manifest.get("schema") != "TICKSTORE_FIRST_ADMISSION_COMMIT_V001"
        or manifest.get("run_id") != authority.get("run_id")
        or set(manifest.get("files", {})) != expected
        or manifest.get("initial_state") != authority.get("first_admission_state")):
        raise RuntimeError("FIRST_ADMISSION_COMMIT_CONTRACT")
    for name, digest in manifest["files"].items():
        data, _ = read_pinned_regular(path.parent / name, "FIRST_ADMISSION_SUPPORT")
        if _sha(data) != digest:
            raise RuntimeError("FIRST_ADMISSION_SUPPORT_SHA:" + name)
    for pk, hk, name in (("owner_gate_path", "owner_gate_sha256", "TECHNICAL_EXECUTION_DESCRIPTOR.json"),
                         ("gca_recovery_receipt_path", "gca_recovery_receipt_sha256", "G_CA_RUNTIME_LOCATOR.json"),
                         ("adapter_binding_path", "adapter_binding_sha256", "RUNTIME_LOCATOR_ADAPTER_BINDING.json")):
        if (_lexical(authority.get(pk, "")) != _lexical(path.parent / name)
            or authority.get(hk) != manifest["files"][name]):
            raise RuntimeError("FIRST_ADMISSION_RUNTIME_BINDING:" + pk)
    for pk, hk in (("b07_receipt_path", "b07_receipt_sha256"), ("completeness_path", "completeness_sha256"),
                   ("final_code_manifest_path", "final_code_manifest_sha256"),
                   ("policy_master_path", "policy_master_sha256"), ("policy_head_path", "policy_head_sha256"),
                   ("origin_witness_path", "origin_witness_sha256")):
        data, _ = read_pinned_regular(authority[pk], "FIRST_ADMISSION_GATE_EVIDENCE")
        if _sha(data) != authority.get(hk):
            raise RuntimeError("FIRST_ADMISSION_GATE_EVIDENCE_SHA:" + pk)
    if not os.path.lexists(pathlib.Path(authority["resume_root"]) / "CHECKPOINT.json"):
        pin = authority["first_admission_state"]
        if (state_path is None or _sha(state_raw) != pin.get("sha256")
            or list(_ident(os.lstat(state_path))) != pin.get("identity")):
            raise RuntimeError("FIRST_ADMISSION_INITIAL_STATE_CHANGED")


def validate_run_authority(binding: dict) -> dict:
    """Compatibility wrapper (B06R3): run scope and anchor integrity only."""
    return load_run_identity(binding).ra


_STABLE_GENERATION_FIELDS = ("snapshot_id", "snapshot_set_id", "provider_id", "volume_identity", "purpose")
CHECKPOINT_SCHEMA = "TICKSTORE_D4_SIGNED_CHECKPOINT_V003"
CHECKPOINT_PAYLOAD_SCHEMA = "TICKSTORE_D4_CERTIFY_CHECKPOINT_V003"


def _norm_generation_value(key, value):
    if key in ("snapshot_id", "snapshot_set_id", "provider_id"):
        return str(value or "").strip().strip("{}").lower()
    return value


def _same_generation(a, b) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    return all(_norm_generation_value(k, a.get(k)) == _norm_generation_value(k, b.get(k)) and a.get(k) is not None
               for k in _STABLE_GENERATION_FIELDS)


def _frozen_library(release_raw: bytes) -> dict:
    ns = {"__name__": "tickstore_frozen_engine_identity_library", "__file__": "<tickstore_publisher_recovery_v004.py>"}
    exec(compile(release_raw, "<tickstore_publisher_recovery_v004.py>", "exec"), ns, ns)
    return ns


def evaluate_resume_identity(identity: RunIdentity, binding: dict, admitted, locator_receipt: dict,
                             release_raw: bytes, key_hex: str) -> list:
    """B06R3: prove that anchor, RUN_AUTHORITY, run_id, signed checkpoint, STATE and VSS generation
    belong to one execution. Returns [(label, ok, detail)]; nothing is written.

    Frozen-engine constraints are cited by function so that a mismatch is recognised as a technical
    impossibility of the frozen V002R22 release, not as a missing approval:
      dispatch_bootstrap: anchor gate format, recovery_source == running engine, OWNER_GATE member hash;
      _d4r_activate_runtime: RUN_AUTHORITY.owner_gate_sha256 == bundle anchor; successor == engine;
      _d4r_read_checkpoint: checkpoint payload bound to run_id, authority, release, config, anchor, generation.
    """
    import hmac as _hmac
    ra, anchor = identity.ra, identity.anchor
    out = []

    def check(label, ok, detail=""):
        out.append((label, bool(ok), detail))

    release_sha = _sha(release_raw)
    generation = anchor.get("admission_generation") if isinstance(anchor, dict) else None
    check("ANCHOR_IS_BOUND_IDENTITY", identity.anchor_sha == str(ra.get("owner_gate_sha256", "")).upper()
          == str(binding.get("owner_gate_sha256", "")).upper()
          == str(locator_receipt.get("owner_gate_sha256", "")).upper(), identity.anchor_sha)
    check("FROZEN_ENGINE_ANCHOR_FORMAT(dispatch_bootstrap)",
          isinstance(anchor, dict) and anchor.get("schema") == "RECOVERY_OWNER_GATE_V004"
          and anchor.get("authorized") is True and anchor.get("mode") == "CERTIFY_SCRATCH"
          and isinstance(anchor.get("permissions"), dict) and anchor["permissions"].get("CERTIFY_SCRATCH") is True
          and "release_bundle_sha256" not in anchor and "external_anchor_sha256" not in anchor,
          "format constants required by the frozen engine; not an approval")
    check("FROZEN_ENGINE_SOURCE(dispatch_bootstrap/_d4r_activate_runtime)",
          isinstance(anchor, dict) and anchor.get("recovery_source_sha256") == release_sha
          == str(ra.get("successor_release_sha256", "")).upper() == str(binding.get("frozen_release_sha256", "")).upper(),
          "anchor.recovery_source=" + str(anchor.get("recovery_source_sha256") if isinstance(anchor, dict) else None)
          + " running_engine=" + release_sha)
    check("GENERATION_ANCHOR_EQUALS_RUN_AUTHORITY", generation is not None and generation == ra.get("generation"))
    check("GENERATION_LOCATOR_STABLE_IDENTITY", _same_generation(generation, locator_receipt.get("generation")))
    g_ca = None
    if getattr(admitted, "state_raw", None) is not None:
        g_ca = json.loads(admitted.state_raw.decode("utf-8")).get("G_CA")
    check("GENERATION_STATE_G_CA_STABLE_IDENTITY", _same_generation(generation, g_ca))
    check("CONFIG_ADMITTED_EQUALS_RUN_AUTHORITY", str(ra.get("config_sha256", "")).upper() == admitted.config_sha256)
    key = b""
    try:
        key = bytes.fromhex(key_hex or "")
    except ValueError:
        key = b""
    check("RUN_KEY_EQUALS_RUN_AUTHORITY", len(key) == 32 and _sha(key) == str(ra.get("key_sha256", "")).upper())
    resume_root = pathlib.Path(str(ra.get("resume_root", "")))
    cp_path = resume_root / "CHECKPOINT.json"
    lib = _frozen_library(release_raw)
    if os.path.lexists(cp_path):
        try:
            raw, _ = read_pinned_regular(cp_path, "ADAPTER_ENTRY_CHECKPOINT")
            signed = json.loads(raw.decode("ascii"))
            payload = signed.get("payload") if isinstance(signed, dict) else None
            ok_sig = (isinstance(payload, dict) and signed.get("schema") == CHECKPOINT_SCHEMA and len(key) == 32
                      and _hmac.compare_digest(str(signed.get("hmac_sha256", "")).upper(), lib["_d4r_hmac_hex"](key, payload)))
        except (RuntimeError, ValueError, UnicodeDecodeError) as exc:
            payload, ok_sig = None, False
            check("CHECKPOINT_READ", False, str(exc))
        check("CHECKPOINT_SIGNATURE_RUN_KEY", ok_sig)
        p = payload if isinstance(payload, dict) else {}
        check("CHECKPOINT_PAYLOAD_SCHEMA", p.get("schema") == CHECKPOINT_PAYLOAD_SCHEMA)
        check("CHECKPOINT_RUN_ID", p.get("run_id") == ra.get("run_id") and bool(ra.get("run_id")))
        check("CHECKPOINT_RUN_AUTHORITY_SHA", p.get("run_authority_sha256") == identity.ra_sha)
        check("CHECKPOINT_RELEASE", p.get("successor_release_sha256") == release_sha)
        check("CHECKPOINT_CONFIG", p.get("config_sha256") == admitted.config_sha256)
        check("CHECKPOINT_ANCHOR", p.get("owner_gate_sha256") == identity.anchor_sha)
        check("CHECKPOINT_GENERATION", generation is not None and p.get("generation_sha256") == lib["_d4r_sha_obj"](generation))
        check("CHECKPOINT_TOTAL", p.get("total") == lib["S0_COUNT"])
        committed = p.get("committed")
        inventory = anchor.get("s0_inventory") if isinstance(anchor, dict) else None
        check("CHECKPOINT_COMMITTED_WITHIN_ANCHOR_INVENTORY", isinstance(committed, list) and isinstance(inventory, dict)
              and committed == sorted(committed) and set(committed) <= set(inventory)
              and p.get("committed_count") == len(committed))
    else:
        chunks = resume_root / "chunks"
        orphan = chunks.is_dir() and any(chunks.iterdir())
        check("CHECKPOINT_ABSENT_WITHOUT_COMMITTED_CHUNKS", str(ra.get("resume_root", "")) != "" and not orphan,
              "no checkpoint to preserve" if not orphan else "chunks without checkpoint")
    return out


def reconcile_resume_identity(identity: RunIdentity, binding: dict, admitted, locator_receipt: dict,
                              release_raw: bytes, key_hex: str) -> list:
    report = evaluate_resume_identity(identity, binding, admitted, locator_receipt, release_raw, key_hex)
    failed = [label for label, ok, _ in report if not ok]
    if failed:
        raise RuntimeError("ADAPTER_ENTRY_IDENTITY_NOT_RECONCILED:" + ",".join(failed))
    return report


CAS_DEBRIS_MARKERS = (".cas-new.", ".cas-old.", ".cas-intent.")


def require_no_cas_debris(state_path) -> None:
    """B06R3: an interrupted STATE commit is never resumed or repaired implicitly.

    Leftovers of the CAS protocol block admission; only the explicit
    state_cas_recovery tool may resolve them, from its recorded intent.
    """
    state_path = pathlib.Path(state_path)
    try:
        names = os.listdir(state_path.parent)
    except FileNotFoundError:
        return
    if any(n.startswith(state_path.name) and any(m in n for m in CAS_DEBRIS_MARKERS) for n in names):
        raise RuntimeError("ADAPTER_ENTRY_STATE_CAS_RECOVERY_REQUIRED")


def validate_d4_start(package: pathlib.Path, python: str, authority: dict) -> AdmittedStart:
    """Read-only start-boundary check; never instantiate frozen State here."""
    config_path = package / "config" / "STAGE_A_SEALED_VALUES_V001.json"
    if config_path.resolve() != pathlib.Path(authority["config_path"]).resolve():
        raise RuntimeError("ADAPTER_ENTRY_CONFIG_PATH")
    raw, config_ident = read_pinned_regular(config_path, "ADAPTER_ENTRY_CONFIG")
    config_sha = _sha(raw)
    if config_sha != authority.get("config_sha256"):
        raise RuntimeError("ADAPTER_ENTRY_CONFIG_SHA")
    config = json.loads(raw)
    if (pathlib.Path(python).resolve() != pathlib.Path(sys.executable).resolve()
        or sha_file(pathlib.Path(python)) != config.get("python_exe_sha256")):
        raise RuntimeError("ADAPTER_ENTRY_PYTHON_IDENTITY")
    control_root = pathlib.Path(config["control_root"])
    state_path = control_root / "state" / "STATE.json"
    require_no_cas_debris(state_path)
    state_raw, state_ident = read_pinned_regular(state_path, "ADAPTER_ENTRY_STATE")
    validate_d4_state(json.loads(state_raw))
    return AdmittedStart(state_path=state_path, control_root=control_root, config_path=config_path,
                         config_raw=raw, config_sha256=config_sha, config_ident=config_ident,
                         state_raw=state_raw, state_ident=state_ident)


def validate_d4_state(state: dict) -> None:
    # --until is only an upper bound in the frozen runner. Earlier next_node
    # values would dispatch earlier nodes; a later value could return false PASS.
    if (state.get("schema") != "TICKSTORE_ORCH_STATE_V001"
        or state.get("next_node") != "D4"
        or state.get("status") not in ("FAIL", "SAFE_STOP")
        or not isinstance(state.get("completed"), list)
        or "D4" in state["completed"]
        or state.get("canary_scratch_cert") is not None):
        raise RuntimeError("ADAPTER_ENTRY_STATE_NOT_D4_ONLY")


def _fsync_directory(directory: pathlib.Path) -> None:
    try:
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, PermissionError):
        pass


def acquire_state_boundary(state_path: pathlib.Path):
    """B06R2: one D4 entry per STATE for the whole process lifetime.

    Windows: named kernel mutex (same Global\\ pattern as the FULL lease); it
    disappears with the process. Elsewhere (test hosts): flock on a lock file
    in the temporary directory, also released by process exit.
    Returns a callable that releases the boundary (tests only).
    """
    key = _sha(_lexical(state_path.resolve()).encode("utf-8"))
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes as w
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.argtypes = [w.HANDLE, w.BOOL, w.LPCWSTR]
        k.CreateMutexW.restype = w.HANDLE
        k.CloseHandle.argtypes = [w.HANDLE]
        k.CloseHandle.restype = w.BOOL
        ctypes.set_last_error(0)
        handle = k.CreateMutexW(None, False, "Global\\TICKSTORE_D4_ENTRY_STATE_" + key)
        if not handle:
            raise RuntimeError("ADAPTER_ENTRY_STATE_BOUNDARY_CREATE:" + str(ctypes.get_last_error()))
        if ctypes.get_last_error() == 183:
            k.CloseHandle(handle)
            raise RuntimeError("ADAPTER_ENTRY_STATE_BOUNDARY_BUSY")
        return lambda: k.CloseHandle(handle)
    import fcntl
    import tempfile
    f = open(os.path.join(tempfile.gettempdir(), "TICKSTORE_D4_ENTRY_STATE_" + key + ".lock"), "a+b")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RuntimeError("ADAPTER_ENTRY_STATE_BOUNDARY_BUSY") from None
    return f.close


def guard_frozen_state_reads(namespace: dict, admitted, *, state_validator=validate_d4_state,
                             transition_validator=None) -> None:
    """Bind every frozen State/config consumption to the objects admitted for D4_ONLY.

    B06-01 (B06R2): STATE is pinned by identity and version (dev, ino, size,
    mtime_ns, SHA-256) from admission. Constructing State never writes STATE.
    Every journal append and every STATE write first re-verifies the pin; a
    STATE write is a compare-and-swap (rename current -> backup, verify that
    the moved entry is the pinned one, publish with create-if-absent). A
    vanished, replaced or newer STATE is preserved and the entry fails closed.
    One D4 entry per STATE holds a process-lifetime boundary.
    B06-02 (B06R2): the configuration is recognised by its admitted lexical
    path as well as its resolved path, so retargeting the name cannot fall
    back to a free read; links/reparse points anywhere in the chain, or any
    identity/byte drift, block. Consumers receive only the admitted buffer.
    Accepts AdmittedStart, or a STATE path for State-only callers (the pin is
    then taken at the first construction).
    """
    import uuid
    if isinstance(admitted, AdmittedStart):
        state_path, config = pathlib.Path(admitted.state_path), admitted
        pin = {"sha": None if admitted.state_raw is None else _sha(admitted.state_raw), "ident": admitted.state_ident}
    else:
        state_path, config = pathlib.Path(admitted), None
        pin = {"sha": None, "ident": None}
    expected = state_path.resolve()
    state_lexical = _lexical(state_path)
    admitted_root = state_path.parent.parent.resolve()
    if config is not None and config.control_root.resolve() != admitted_root:
        raise RuntimeError("ADAPTER_ENTRY_ADMITTED_ROOT_MISMATCH")
    config_expected = config.config_path.resolve() if config is not None else None
    config_lexical = _lexical(config.config_path) if config is not None else None
    original_atomj = namespace["atomj"]
    original_read = namespace["rj"]
    boundary = {"release": None}

    def is_state(path) -> bool:
        return _lexical(path) == state_lexical or pathlib.Path(path).resolve() == expected

    def is_config(path) -> bool:
        return config is not None and (_lexical(path) == config_lexical or pathlib.Path(path).resolve() == config_expected)

    def verify_pin(stage: str) -> bytes:
        try:
            raw, ident = read_pinned_regular(state_path, "ADAPTER_ENTRY_STATE")
        except RuntimeError as exc:
            raise RuntimeError("ADAPTER_ENTRY_STATE_CONCURRENT_CHANGE:" + stage + ":" + str(exc)) from None
        if _sha(raw) != pin["sha"] or ident != pin["ident"]:
            raise RuntimeError("ADAPTER_ENTRY_STATE_CONCURRENT_CHANGE:" + stage)
        return raw

    def guarded_read(path):
        if is_config(path):
            try:
                raw, ident = read_pinned_regular(path, "ADAPTER_ENTRY_CONFIG")
            except RuntimeError:
                raise RuntimeError("ADAPTER_ENTRY_CONFIG_DRIFT") from None
            if _sha(raw) != config.config_sha256 or (config.config_ident is not None and ident != config.config_ident):
                raise RuntimeError("ADAPTER_ENTRY_CONFIG_DRIFT")
            return json.loads(config.config_raw.decode("utf-8"))
        if is_state(path):
            if pin["sha"] is None:
                raise RuntimeError("ADAPTER_ENTRY_STATE_NOT_PINNED")
            obj = json.loads(verify_pin("READ").decode("utf-8"))
            state_validator(obj)
            return obj
        return original_read(path)

    def rename_with_retry(src: pathlib.Path, dst: pathlib.Path) -> None:
        import time
        for attempt in range(10):
            try:
                os.rename(src, dst)  # Windows: MoveFileExW without REPLACE_EXISTING
                return
            except PermissionError:
                if attempt == 9:
                    raise RuntimeError("ADAPTER_ENTRY_STATE_COMMIT_BUSY") from None
                time.sleep(0.1)

    def commit_state(obj) -> None:
        data = namespace["jb"](obj)
        previous_raw = verify_pin("COMMIT")
        if transition_validator is not None:
            transition_validator(json.loads(previous_raw), obj)
        tag = str(os.getpid()) + "." + uuid.uuid4().hex
        partial = state_path.with_name(state_path.name + ".cas-new." + tag)
        backup = state_path.with_name(state_path.name + ".cas-old." + tag)
        intent = state_path.with_name(state_path.name + ".cas-intent." + tag)
        with open(partial, "xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        # B06R3: durable record of the confirmed (prev) and target (new) versions,
        # so an interruption can be resolved deterministically by the recovery tool.
        intent_obj = {"schema": "TICKSTORE_D4_STATE_CAS_INTENT_V001", "tag": tag, "state_name": state_path.name,
                      "prev_sha256": pin["sha"], "prev_identity": list(pin["ident"]), "new_sha256": _sha(data)}
        with open(intent, "xb") as f:
            f.write((json.dumps(intent_obj, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))
            f.flush()
            os.fsync(f.fileno())
        _fsync_directory(state_path.parent)
        cleanup_intent = True
        try:
            try:
                rename_with_retry(state_path, backup)
            except FileNotFoundError:
                raise RuntimeError("ADAPTER_ENTRY_STATE_CONCURRENT_CHANGE:VANISHED_BEFORE_COMMIT") from None
            try:
                moved_raw, moved_ident = read_pinned_regular(backup, "ADAPTER_ENTRY_STATE_BACKUP")
                # A rename keeps device, file id, size and mtime: anything else is not the pinned STATE.
                swapped = _sha(moved_raw) != pin["sha"] or moved_ident != pin["ident"]
            except RuntimeError:
                swapped = True
            if swapped:
                try:
                    os.link(backup, state_path)  # put the concurrent winner back, never clobbering
                    os.unlink(backup)
                except OSError:
                    cleanup_intent = False  # leave the evidence for the recovery tool
                raise RuntimeError("ADAPTER_ENTRY_STATE_CONCURRENT_CHANGE:REPLACED_BEFORE_COMMIT")
            try:
                os.link(partial, state_path)  # create-if-absent: a STATE created meanwhile is preserved
            except FileExistsError:
                cleanup_intent = False  # confirmed version stays in cas-old; recovery decides
                raise RuntimeError("ADAPTER_ENTRY_STATE_CONCURRENT_CHANGE:RECREATED_DURING_COMMIT") from None
            os.unlink(partial)
            new_raw, new_ident = read_pinned_regular(state_path, "ADAPTER_ENTRY_STATE")
            if new_raw != data:
                raise RuntimeError("ADAPTER_ENTRY_STATE_COMMIT_READBACK")
            with open(state_path, "rb+") as committed:
                os.fsync(committed.fileno())
            _fsync_directory(state_path.parent)
            pin.update(sha=_sha(data), ident=new_ident)
            os.unlink(backup)
        finally:
            try:
                os.unlink(partial)
            except OSError:
                pass
            if cleanup_intent and not os.path.lexists(backup):
                try:
                    os.unlink(intent)
                    _fsync_directory(state_path.parent)
                except OSError:
                    pass

    def guarded_atomj(path, obj):
        if is_state(path):
            if pin["sha"] is None or boundary["release"] is None:
                raise RuntimeError("ADAPTER_ENTRY_STATE_WRITE_OUTSIDE_BOUNDARY")
            return commit_state(obj)
        return original_atomj(path, obj)

    frozen_state = namespace["State"]

    class D4OnlyState(frozen_state):
        def __init__(self, root):
            root = pathlib.Path(root)
            if root.resolve() != admitted_root:
                raise RuntimeError("ADAPTER_ENTRY_STATE_ROOT_NOT_ADMITTED")
            require_no_cas_debris(root / "state" / "STATE.json")
            raw, ident = read_pinned_regular(root / "state" / "STATE.json", "ADAPTER_ENTRY_STATE")
            obj = json.loads(raw.decode("utf-8"))
            state_validator(obj)
            if pin["sha"] is None:
                pin.update(sha=_sha(raw), ident=ident)
            elif _sha(raw) != pin["sha"] or ident != pin["ident"]:
                raise RuntimeError("ADAPTER_ENTRY_STATE_CHANGED_SINCE_ADMISSION")
            if boundary["release"] is None:
                boundary["release"] = acquire_state_boundary(state_path)
                verify_pin("BOUNDARY")
            # Same attribute layout and directories as frozen State.__init__;
            # unlike it, no STATE rewrite here (the admitted bytes stay in place).
            self.root = root; self.sd = root / "state"; self.runs = root / "runs"
            self.inbox = root / "inbox"; self.packs = root / "packs"; self.ev = root / "evidence"
            for p in (self.sd, self.runs, self.inbox, self.packs, self.ev):
                p.mkdir(parents=True, exist_ok=True)
            self.sp = self.sd / "STATE.json"; self.jp = self.sd / "STATE_JOURNAL.jsonl"
            self.d = obj

        def log(self, node, phase, **x):
            verify_pin("JOURNAL")
            return frozen_state.log(self, node, phase, **x)

    def release_boundary():
        if boundary["release"] is not None:
            boundary["release"]()
            boundary["release"] = None

    namespace["rj"] = guarded_read
    namespace["atomj"] = guarded_atomj
    namespace["State"] = D4OnlyState
    namespace["_TICKSTORE_D4_ENTRY_RELEASE_STATE_BOUNDARY"] = release_boundary


def pin_frozen_engine_load(namespace: dict, release_path: pathlib.Path, release_raw: bytes) -> None:
    """B06-02 (same principle for code): O loads the engine from the hashed buffer."""
    expected = release_path.resolve()

    def pinned_load_engine(p):
        if pathlib.Path(p).resolve() != expected:
            raise RuntimeError("ADAPTER_ENTRY_ENGINE_PATH_NOT_ADMITTED")
        ns = {"__name__": "tickstore_engine_library", "__file__": str(p)}
        exec(compile(release_raw, str(p), "exec"), ns, ns)
        return namespace["types"].SimpleNamespace(**ns)

    namespace["load_engine"] = pinned_load_engine


def main() -> int:
    args = parse_d4_arguments(sys.argv[1:])
    package = pathlib.Path(args.package)
    adapter_dir = pathlib.Path(os.environ.get("TICKSTORE_RUNTIME_LOCATOR_ADAPTER_DIR", pathlib.Path(__file__).resolve().parent))
    receipt_path = pathlib.Path(os.environ["TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT"])
    binding_path = adapter_dir / "RUNTIME_LOCATOR_ADAPTER_BINDING.json"
    adapter_path = adapter_dir / "runtime_locator_adapter.py"
    inline_entry = adapter_dir / "runtime_locator_inline_entry.py"
    adapted_loader = adapter_dir / "INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1"
    adapted_launch = adapter_dir / "Launch-TickstoreBundle-Adapter.ps1"
    frozen_orchestrator = package / "modules" / "orchestrator.py"
    frozen_release = package / "engine" / "tickstore_publisher_recovery_v004_release.py"

    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    if binding.get("schema") != "TICKSTORE_G_CA_RUNTIME_LOCATOR_ADAPTER_BINDING_V002":
        raise RuntimeError("ADAPTER_ENTRY_BINDING_SCHEMA")
    checks = (
        (frozen_release, "frozen_release_sha256", "ADAPTER_ENTRY_FROZEN_RELEASE"),
        (frozen_orchestrator, "frozen_orchestrator_sha256", "ADAPTER_ENTRY_FROZEN_ORCHESTRATOR"),
        (adapter_path, "adapter_sha256", "ADAPTER_ENTRY_ADAPTER"),
        (inline_entry, "inline_entry_sha256", "ADAPTER_ENTRY_INLINE"),
        (adapted_loader, "adapted_loader_sha256", "ADAPTER_ENTRY_LOADER"),
        (adapted_launch, "adapted_launch_sha256", "ADAPTER_ENTRY_LAUNCH"),
    )
    admitted_code = {}
    for path, key, label in checks:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest().upper() != str(binding.get(key, "")).upper():
            raise RuntimeError(label + "_SHA")
        admitted_code[key] = raw
    if not receipt_path.is_file():
        raise RuntimeError("ADAPTER_ENTRY_LOCATOR_RECEIPT_MISSING")
    identity = load_run_identity(binding)
    admitted = validate_d4_start(package, args.python, identity.ra)
    validate_first_admission_commit(identity.ra, admitted.state_raw, admitted.state_path)

    adapter_ns = {"__name__": "tickstore_runtime_locator_adapter_orchestrator", "__file__": str(adapter_path)}
    adapter_raw = admitted_code["adapter_sha256"]
    exec(compile(adapter_raw, str(adapter_path), "exec"), adapter_ns, adapter_ns)
    adapter_ns["validate_binding"](binding)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    adapter_ns["validate_locator_receipt"](receipt, binding)
    # B06R3 (option B): resume only when anchor, RUN_AUTHORITY, run_id, signed checkpoint,
    # STATE and VSS generation are proven to be one execution.
    reconcile_resume_identity(identity, binding, admitted, receipt, admitted_code["frozen_release_sha256"],
                              os.environ.get("TICKSTORE_D4_RUN_HMAC_KEY_HEX", ""))

    orch_ns = {"__name__": "tickstore_frozen_orchestrator_with_runtime_adapter", "__file__": str(frozen_orchestrator)}
    orch_raw = admitted_code["frozen_orchestrator_sha256"]
    exec(compile(orch_raw, str(frozen_orchestrator), "exec"), orch_ns, orch_ns)
    adapter_ns["install_orchestrator_namespace"](orch_ns, binding, adapter_dir, receipt_path)
    guard_frozen_state_reads(orch_ns, admitted)
    pin_frozen_engine_load(orch_ns, frozen_release, admitted_code["frozen_release_sha256"])
    return int(orch_ns["main"]())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print("ORCHESTRATOR_ADAPTER_BLOCKED=" + str(exc), flush=True)
        raise SystemExit(2)
