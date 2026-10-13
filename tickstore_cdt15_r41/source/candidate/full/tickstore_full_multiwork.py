from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import hashlib
import json
import math
import multiprocessing as mp
import os
import queue
import re
import shutil
import signal
import stat
import sys
import time
import traceback
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tickstore_serial_runner as core
import pts2g_reference as ref
from FULL_PROCESS_CONTROL import ProcessJob, StopEvent
from FULL_OBSERVABILITY import Heartbeat

WRAPPER_SCHEMA = "TICKSTORE_R9_FULL_MULTIWORK_RC4R2_V001"
MULTIWORK_GATE_SCHEMA = "TICKSTORE_FULL_MULTIWORK_OWNER_GATE_V001"
DEFAULT_MAX_WORKERS = 22
DEFAULT_RAM_TARGET_PERCENT = 60
ESTIMATED_WORKER_RAM_BYTES = 1280 * 1024**2
PARENT_RAM_RESERVE_BYTES = 2 * 1024**3
PROGRESS_INTERVAL_SECONDS = 5.0
PRODUCTIVITY_STALL_SECONDS = 180.0
SAFE_STOP_JOIN_TIMEOUT_SECONDS = 60.0
SAFE_STOP_TERMINATE_GRACE_SECONDS = 5.0
SAFE_STOP_KILL_GRACE_SECONDS = 5.0
COORDINATOR_SCHEMA = "TICKSTORE_MULTIWORK_COORDINATOR_STATE_V002"


class MultiworkBlocked(RuntimeError):
    pass


class CooperativeSafeStop(KeyboardInterrupt):
    """Issued only after verified cooperative process-tree cleanup."""


class ResourceSafeStop(KeyboardInterrupt):
    """Resource pressure takes the existing cooperative checkpoint/cleanup path."""


def memory_decision(snapshot, memory, target_percent):
    used = max(snapshot['working_set_bytes'], snapshot['private_bytes'])
    target = memory['total'] * target_percent // 100
    if used >= target or memory['available'] < PARENT_RAM_RESERVE_BYTES:
        return 'SAFE_STOP'
    if used + ESTIMATED_WORKER_RAM_BYTES > target or memory['available'] < ESTIMATED_WORKER_RAM_BYTES + PARENT_RAM_RESERVE_BYTES:
        return 'DRAIN'
    return 'LAUNCH'


def instance_scratch(scratch_root, admission, bindings):
    """Use one durable namespace per admitted instance; never consume old scratch."""
    run_id = admission.instance['run_id']
    if not isinstance(run_id, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,80}', run_id) is None:
        raise MultiworkBlocked('FULL_RUN_ID_INVALID')
    root = Path(scratch_root)/'RUN_INSTANCES'/run_id
    core.strict_directory(root.parent, create=True)
    existed = core.strict_lstat(root, allow_missing=True) is not None
    core.strict_directory(root, create=not existed)
    path = root/'INSTANCE.json'
    identity = dict(schema='TICKSTORE_FULL_SCRATCH_INSTANCE_V001', run_id=run_id,
                    code_manifest_sha256=admission.descriptor['code_manifest_sha256'],
                    instance_sha256=admission.descriptor['instance_sha256'],
                    bindings={k: v for k, v in bindings.items() if k not in ('schema', 'authorized')})
    raw = (json.dumps(identity, sort_keys=True, separators=(',', ':'))+'\n').encode('ascii')
    if existed:
        if core.secure_read_all(path) != raw:
            raise MultiworkBlocked('FULL_SCRATCH_INSTANCE_DRIFT')
    else:
        fd = core.secure_create_new_fd(path)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        if core.secure_read_all(path) != raw:
            raise MultiworkBlocked('FULL_SCRATCH_INSTANCE_READBACK')
    return root


class WorkerSafeStop(Exception):
    pass


class FullProcessLease:
    """Use the historical RecoveryProcessLease native lifetime pattern for FULL."""
    def __init__(self, dest_root):
        if os.name != "nt":
            raise MultiworkBlocked("FULL_LEASE_WINDOWS_REQUIRED")
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        H = ctypes.wintypes.HANDLE
        self.k.CreateMutexW.argtypes = [H, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
        self.k.CreateMutexW.restype = H
        self.k.CloseHandle.argtypes = [H]
        self.k.CloseHandle.restype = ctypes.wintypes.BOOL
        self.k.GetCurrentProcess.restype = H
        self.k.GetProcessTimes.argtypes = [H] + [ctypes.POINTER(ctypes.c_uint64)] * 4
        self.k.GetProcessTimes.restype = ctypes.wintypes.BOOL
        name = "Global\\TICKSTORE_FULL_" + hashlib.sha256(core._norm_binding_path(Path(dest_root)).encode("utf-8")).hexdigest()
        ctypes.set_last_error(0)
        self.handle = self.k.CreateMutexW(None, False, name)
        if not self.handle:
            raise MultiworkBlocked("FULL_LEASE_CREATE:" + str(ctypes.get_last_error()))
        if ctypes.get_last_error() == 183:
            self.close()
            raise MultiworkBlocked("FULL_LEASE_LIVE_SUPERVISOR")
        try:
            times = [ctypes.c_uint64() for _ in range(4)]
            if not self.k.GetProcessTimes(self.k.GetCurrentProcess(), *(ctypes.byref(t) for t in times)):
                raise MultiworkBlocked("FULL_LEASE_PROCESS_IDENTITY")
            self.identity = {"pid": os.getpid(), "creation_filetime": times[0].value}
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            if not self.k.CloseHandle(self.handle):
                raise MultiworkBlocked("FULL_LEASE_CLOSE")
            self.handle = None


def sha256_file(path: Path) -> str:
    return core.sha256_file(Path(path)).upper()


def wrapper_sha256() -> str:
    return sha256_file(Path(__file__).resolve())


def stable_json_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strict_gate_sha(value: str) -> str:
    value = str(value or "").strip().upper()
    if len(value) != 64 or any(c not in "0123456789ABCDEF" for c in value):
        raise MultiworkBlocked("MULTIWORK_GATE_SHA256_INVALID")
    return value


def _read_json_bytes(path: Path, expected_sha: str):
    raw = core.secure_read_all(Path(path))
    actual = hashlib.sha256(raw).hexdigest().upper()
    if actual != expected_sha:
        raise MultiworkBlocked("MULTIWORK_GATE_DIGEST_MISMATCH")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except MultiworkBlocked:
        raise
    except Exception as exc:
        raise MultiworkBlocked("MULTIWORK_GATE_JSON_INVALID") from exc
    if not isinstance(obj, dict):
        raise MultiworkBlocked("MULTIWORK_GATE_NOT_OBJECT")
    return obj


def _reject_duplicate_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise MultiworkBlocked("MULTIWORK_GATE_DUPLICATE_KEY:" + str(key))
        out[key] = value
    return out


def windows_memory_status():
    if os.name != "nt":
        raise MultiworkBlocked("MULTIWORK_REQUIRES_WINDOWS")

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.wintypes.DWORD),
            ("dwMemoryLoad", ctypes.wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise MultiworkBlocked("WINDOWS_MEMORY_STATUS_FAIL")
    return {
        "total": int(status.ullTotalPhys),
        "available": int(status.ullAvailPhys),
        "load_percent": int(status.dwMemoryLoad),
    }


def choose_workers(requested: str, month_count: int, max_workers: int, ram_target_percent: int):
    cpu = int(os.cpu_count() or 1)
    max_workers = max(1, min(int(max_workers), 32))
    ram_target_percent = max(20, min(int(ram_target_percent), 80))
    mem = windows_memory_status()
    cpu_budget = max(1, cpu - 2)
    target_total = int(mem["total"] * (ram_target_percent / 100.0))
    usable = min(target_total, int(mem["available"] * 0.85)) - PARENT_RAM_RESERVE_BYTES
    ram_budget = usable // ESTIMATED_WORKER_RAM_BYTES
    if ram_budget < 1:
        raise MultiworkBlocked("INSUFFICIENT_RAM_FOR_ONE_WORKER")

    if str(requested).upper() != "AUTO":
        try:
            n = int(requested)
        except Exception as exc:
            raise MultiworkBlocked("WORKERS_MUST_BE_AUTO_OR_INTEGER") from exc
        if n < 1 or n > max_workers:
            raise MultiworkBlocked("WORKER_COUNT_OUT_OF_RANGE")
        if n > cpu_budget:
            raise MultiworkBlocked("WORKER_COUNT_EXCEEDS_CPU_BUDGET")
        if n > ram_budget:
            raise MultiworkBlocked("WORKER_COUNT_EXCEEDS_RAM_BUDGET")
        return min(n, month_count), mem

    workers = min(month_count, max_workers, cpu_budget, ram_budget)
    return max(1, int(workers)), mem


def _norm(path: Path):
    return core._norm_binding_path(Path(path))


def validate_multiwork_gate(path: Path, sha256: str, *, core_gate_sha256: str,
                            source_root: Path, dest_root: Path, scratch_root: Path,
                            workers: int, max_workers: int, ram_target_percent: int):
    sha256 = _strict_gate_sha(sha256)
    obj = _read_json_bytes(Path(path), sha256)
    expected_fields = {
        "schema", "authorized", "wrapper_schema", "wrapper_sha256",
        "core_runner_sha256", "core_owner_gate_sha256",
        "source_root", "dest_root", "scratch_root",
        "source_volume", "dest_volume", "scratch_volume",
        "workers_max", "ram_target_percent_max",
    }
    if set(obj) != expected_fields:
        raise MultiworkBlocked("MULTIWORK_GATE_FIELD_SET_MISMATCH")
    if obj["schema"] != MULTIWORK_GATE_SCHEMA:
        raise MultiworkBlocked("MULTIWORK_GATE_SCHEMA_MISMATCH")
    if obj["authorized"] is not True:
        raise MultiworkBlocked("MULTIWORK_GATE_NOT_AUTHORIZED")
    if obj["wrapper_schema"] != WRAPPER_SCHEMA:
        raise MultiworkBlocked("MULTIWORK_GATE_WRAPPER_SCHEMA_MISMATCH")
    if str(obj["wrapper_sha256"]).upper() != wrapper_sha256():
        raise MultiworkBlocked("MULTIWORK_GATE_WRAPPER_SHA_MISMATCH")
    core_ids = core.file_ids(Path(core.__file__).resolve().parent)
    if str(obj["core_runner_sha256"]).upper() != core_ids["runner_sha256"].upper():
        raise MultiworkBlocked("MULTIWORK_GATE_CORE_RUNNER_SHA_MISMATCH")
    if str(obj["core_owner_gate_sha256"]).upper() != str(core_gate_sha256).upper():
        raise MultiworkBlocked("MULTIWORK_GATE_CORE_GATE_SHA_MISMATCH")

    roots = {
        "source_root": Path(source_root),
        "dest_root": Path(dest_root),
        "scratch_root": Path(scratch_root),
    }
    for key, value in roots.items():
        if str(obj[key]) != _norm(value):
            raise MultiworkBlocked("MULTIWORK_GATE_PATH_MISMATCH:" + key)
        expected_vol = core.windows_volume_identity(value)
        if obj[key.replace("_root", "_volume")] != expected_vol:
            raise MultiworkBlocked("MULTIWORK_GATE_VOLUME_MISMATCH:" + key)

    if int(obj["workers_max"]) < workers:
        raise MultiworkBlocked("MULTIWORK_GATE_WORKERS_EXCEEDED")
    if int(obj["workers_max"]) > int(max_workers):
        raise MultiworkBlocked("MULTIWORK_GATE_MAX_WORKERS_POLICY_MISMATCH")
    if int(obj["ram_target_percent_max"]) < int(ram_target_percent):
        raise MultiworkBlocked("MULTIWORK_GATE_RAM_TARGET_EXCEEDED")
    return obj


class ParentMonthPin:
    """Parent-owned write/delete-denying handle that overlaps the worker month pin."""
    def __init__(self, path: Path, identity: dict):
        self.path=Path(path)
        self.identity=dict(identity)
        self.fd=None

    def open(self):
        self.fd=core.secure_open_existing_fd(self.path,writable=False,source_pin=True)
        self.verify()
        return self

    def verify(self):
        if self.fd is None:
            raise core.Blocked("PARENT_MONTH_PIN_CLOSED")
        core.source_identity_quick_check(self.path,self.identity)
        st=os.fstat(self.fd)
        exp=self.identity
        vals=(st.st_size,st.st_mtime_ns,int(getattr(st,"st_dev",0) or 0),int(getattr(st,"st_ino",0) or 0))
        expected=(int(exp["size"]),int(exp["mtime_ns"]),int(exp.get("st_dev",0) or 0),int(exp.get("st_ino",0) or 0))
        if vals[:2]!=expected[:2] or (expected[3] and vals[3] and vals[2:]!=expected[2:]):
            raise core.Blocked("PARENT_MONTH_PIN_IDENTITY_MISMATCH")
        return True

    @classmethod
    def open_from_expected(cls, path: Path, expected_size: int, expected_sha: str):
        pin=cls(Path(path),{})
        pin.fd=core.secure_open_existing_fd(pin.path,writable=False,source_pin=True)
        st=os.fstat(pin.fd)
        if int(st.st_size)!=int(expected_size):
            os.close(pin.fd);pin.fd=None
            raise core.Blocked(f"PARENT_PRESTART_SOURCE_SIZE_MISMATCH:{st.st_size}:{expected_size}")
        pin.identity={
            "normalized_path":os.path.normcase(os.path.normpath(os.path.abspath(str(pin.path)))),
            "size":int(st.st_size),
            "mtime_ns":int(st.st_mtime_ns),
            "st_dev":int(getattr(st,"st_dev",0) or 0),
            "st_ino":int(getattr(st,"st_ino",0) or 0),
            "sha256":str(expected_sha).upper(),
        }
        pin.verify()
        return pin

    def close(self):
        if self.fd is not None:
            os.close(self.fd);self.fd=None


class ExternalWorkerPinGuard:
    """RC1 publication guard backed by the parent-owned continuous month pin."""
    def __init__(self, parent_pin: ParentMonthPin):
        self.parent_pin=parent_pin
        self.path=parent_pin.path
        self.identity=dict(parent_pin.identity)

    def verify_path_binding(self):
        return self.parent_pin.verify()

    def verify_full(self):
        return self.parent_pin.verify()

    def seek(self, *args, **kwargs):
        raise MultiworkBlocked("EXTERNAL_PIN_GUARD_IS_NOT_A_READER")

    tell = seek
    readline = seek


class StreamingMonthSource:
    """Single-pass month reader: source pin + SHA256 + build stream in one physical pass.

    The oracle is bound to the ledger-expected SHA256 immediately, but no canonical
    publication is permitted until finish_and_verify() proves the actual stream digest.
    The handle is opened with source_pin=True and remains pinned for the entire pass.
    """
    CHUNK_BYTES = 8 * 1024 * 1024
    EVENT_BYTES = 16 * 1024 * 1024

    def __init__(self, path: Path, expected_size: int, expected_sha: str, stop_event=None,
                 event_q=None, worker_id: str | None=None, month_id: str | None=None):
        self.path=Path(path)
        self.expected_size=int(expected_size)
        self.expected_sha=str(expected_sha).upper()
        self.stop_event=stop_event
        self.event_q=event_q
        self.worker_id=worker_id
        self.month_id=month_id
        self.fd=None;self.file=None;self.identity=None
        self._hash=hashlib.sha256();self._hashed=0;self._last_event=0;self.verified=False

    def __enter__(self):
        core.strict_regular_file(self.path)
        self.fd=core.secure_open_existing_fd(self.path,writable=False,source_pin=True)
        self.file=os.fdopen(self.fd,"rb",buffering=8*1024*1024)
        self.fd=None
        st=os.fstat(self.file.fileno())
        if int(st.st_size)!=self.expected_size:
            raise core.Blocked(f"SOURCE_SIZE_MISMATCH:{st.st_size}:{self.expected_size}")
        self.identity={
            "normalized_path":os.path.normcase(os.path.normpath(os.path.abspath(str(self.path)))),
            "size":int(st.st_size),
            "mtime_ns":int(st.st_mtime_ns),
            "st_dev":int(getattr(st,"st_dev",0) or 0),
            "st_ino":int(getattr(st,"st_ino",0) or 0),
            "sha256":self.expected_sha,
        }
        self.verify_path_binding()
        return self

    def __exit__(self,*exc):
        if self.file is not None:
            self.file.close();self.file=None

    def verify_path_binding(self):
        if self.file is None or self.file.closed:
            raise core.Blocked("STREAMING_SOURCE_PIN_CLOSED")
        core.source_identity_quick_check(self.path,self.identity)
        st=os.fstat(self.file.fileno())
        exp=self.identity
        vals=(int(st.st_size),int(st.st_mtime_ns),int(getattr(st,"st_dev",0) or 0),int(getattr(st,"st_ino",0) or 0))
        expected=(int(exp["size"]),int(exp["mtime_ns"]),int(exp.get("st_dev",0) or 0),int(exp.get("st_ino",0) or 0))
        if vals[:2]!=expected[:2] or (expected[3] and vals[3] and vals[2:]!=expected[2:]):
            raise core.Blocked("STREAMING_SOURCE_HANDLE_IDENTITY_CHANGED")
        return True

    def _check_stop(self):
        if self.stop_event is not None and self.stop_event.is_set():
            raise WorkerSafeStop()

    def _account(self, data: bytes):
        if data:
            self._hash.update(data);self._hashed += len(data)
            if self.event_q is not None and self._hashed-self._last_event>=self.EVENT_BYTES:
                self._last_event=self._hashed
                self.event_q.put({
                    "type":"SCAN","worker":self.worker_id,"month_id":self.month_id,
                    "bytes_scanned":self._hashed,"month_bytes":self.expected_size,
                })

    def scan_to(self,target:int):
        target=int(target)
        current=self.tell()
        if target<current:
            raise core.Blocked(f"STREAMING_SOURCE_BACKWARD_SEEK:{current}:{target}")
        if target>self.expected_size:
            raise core.Blocked(f"STREAMING_SOURCE_TARGET_AFTER_EOF:{target}:{self.expected_size}")
        while current<target:
            self._check_stop()
            need=min(self.CHUNK_BYTES,target-current)
            b=self.file.read(need)
            if not b:
                raise core.Blocked("SOURCE_EOF_DURING_SINGLE_PASS_SCAN")
            self._account(b)
            current += len(b)
        if current!=target:
            raise core.Blocked("STREAMING_SOURCE_SCAN_TARGET_MISMATCH")
        return current

    def seek(self,target,*args):
        if args and any(int(x)!=0 for x in args):
            raise core.Blocked("STREAMING_SOURCE_SEEK_MODE_UNSUPPORTED")
        return self.scan_to(int(target))

    def tell(self):
        return int(self.file.tell())

    def readline(self):
        raw=self.file.readline()
        self._account(raw)
        return raw

    def finish_and_verify(self):
        self.scan_to(self.expected_size)
        self.verify_path_binding()
        digest=self._hash.hexdigest().upper()
        if self._hashed!=self.expected_size:
            raise core.Blocked(f"SOURCE_STREAM_BYTE_COUNT_MISMATCH:{self._hashed}:{self.expected_size}")
        if digest!=self.expected_sha:
            raise core.Blocked("SOURCE_SHA256_MISMATCH_SINGLE_PASS:"+str(self.path))
        self.verify_path_binding()
        self.verified=True
        if self.event_q is not None:
            self.event_q.put({
                "type":"SCAN","worker":self.worker_id,"month_id":self.month_id,
                "bytes_scanned":self._hashed,"month_bytes":self.expected_size,
            })
        return digest


def _scratch_day_paths(scratch_root: Path, month_id: str, date_key: str):
    """Use RC4R2 scratch first, then resume one compatible RC4/RC3/RC2R3 pair in place.

    No legacy artifact is copied, renamed or deleted merely because the wrapper revision
    changed. More than one complete revision pair for the same date is fail-closed.
    """
    scratch_root=Path(scratch_root)
    core.strict_directory(scratch_root,create=False)
    roots=[
        ("RC4R2",scratch_root / "FULL_MULTIWORK_RC4R2" / month_id / date_key),
        ("RC4",scratch_root / "FULL_MULTIWORK_RC4" / month_id / date_key),
        ("RC3",scratch_root / "FULL_MULTIWORK_RC3" / month_id / date_key),
        ("RC2R3",scratch_root / "FULL_MULTIWORK_RC2R3" / month_id / date_key),
    ]

    found=[]
    for namespace,root in roots:
        partial=root/(date_key+".pts2g.partial")
        journal=root/(date_key+".journal.json")
        pe=core.strict_lstat(partial,allow_missing=True) is not None
        je=core.strict_lstat(journal,allow_missing=True) is not None
        if pe!=je:
            raise core.Blocked(namespace+"_SCRATCH_PARTIAL_JOURNAL_PAIR_MISMATCH:"+date_key)
        if pe:
            found.append((namespace,root,partial,journal))

    if len(found)>1:
        raise core.Blocked("SCRATCH_REVISION_CONFLICT:"+date_key)
    if found:
        namespace,root,partial,journal=found[0]
        return {"root":root,"partial":partial,"journal":journal,"namespace":namespace}

    current_root=scratch_root / "FULL_MULTIWORK_RC4R2" / month_id / date_key
    core.strict_directory(scratch_root/"FULL_MULTIWORK_RC4R2",create=True)
    core.strict_directory(scratch_root/"FULL_MULTIWORK_RC4R2"/month_id,create=True)
    core.strict_directory(current_root,create=True)
    return {
        "root":current_root,
        "partial":current_root/(date_key+".pts2g.partial"),
        "journal":current_root/(date_key+".journal.json"),
        "namespace":"RC4R2",
    }

def _clean_orphan_scratch(partial: Path, journal: Path):
    pe = core.strict_lstat(partial, allow_missing=True) is not None
    je = core.strict_lstat(journal, allow_missing=True) is not None
    if pe != je:
        raise core.Blocked("SCRATCH_ORPHAN_FAIL_CLOSED")
    return "CLEAN"


def _build_or_resume_day_cooperative(source_view, c, oracle, partial: Path, journal: Path,
                                     zstd, stop_event, event_q, worker_id: str):
    p_exists = core.strict_lstat(partial, allow_missing=True) is not None
    j_exists = core.strict_lstat(journal, allow_missing=True) is not None
    if p_exists != j_exists:
        _clean_orphan_scratch(partial, journal)
        p_exists = core.strict_lstat(partial, allow_missing=True) is not None
        j_exists = core.strict_lstat(journal, allow_missing=True) is not None
    if p_exists != j_exists:
        raise core.Blocked("SCRATCH_PARTIAL_JOURNAL_PAIR_MISMATCH")

    fresh = not p_exists
    if not p_exists:
        j = core.init_partial(partial, journal, c, oracle)
        row_start = 0
        source_cursor = int(c["first_offset"])
        durable = int(j["durable_end"])
    else:
        j = core.read_json_strict(journal)
        state = j.get("state")
        if state == "VALIDATED_PENDING_PUBLISH":
            core.validate_validated_partial(
                partial, journal, c, oracle, zstd,
                allowed_states=("VALIDATED_PENDING_PUBLISH",)
            )
            return "RESUMED"
        if state != "BUILDING":
            raise core.Blocked("SCRATCH_JOURNAL_STATE_UNEXPECTED:" + str(state))
        row_start, source_cursor, durable = core.validate_completed_groups(
            partial, c, j, zstd, oracle=oracle,
            allowed_states=("BUILDING",), require_full_groups=False
        )
        if core.strict_regular_file(partial).st_size != durable:
            core.truncate_to_durable(partial, durable)

    midnight = ref.midnight_epoch_from_datekey(int(c["date_key"]))
    expected_rows = int(c["rows"])
    day_end = int(c["block_end_offset"])
    group_count = math.ceil(expected_rows / ref.GROUP_TICKS)

    source_view.verify_path_binding()
    source_view.seek(source_cursor)
    while row_start < expected_rows:
        if stop_event.is_set():
            raise WorkerSafeStop()
        gi = len(j["completed_groups"])
        if gi >= group_count:
            raise core.Blocked("TOO_MANY_GROUPS")
        gb = ref.GroupBuilder(int(c["date_key"]), gi, row_start)
        target = min(ref.GROUP_TICKS, expected_rows - row_start)
        for _ in range(target):
            line_start = source_view.tell()
            raw = source_view.readline()
            line_end = source_view.tell()
            if not raw:
                raise core.Blocked("SOURCE_EOF_DURING_GROUP")
            if line_end > day_end:
                raise core.Blocked("SOURCE_LINE_CROSSES_DAY")
            logical = raw[:-1] if raw.endswith(b"\n") else raw
            if logical.endswith(b"\r"):
                logical = logical[:-1]
            row = ref.parse_row(logical, int(c["date_key"]), midnight)
            gb.add(row, line_start, line_end)
        g = gb.finalize(zstd)
        for section in g["sections"]:
            section["payload_offset"] = durable
            durable += section["stored_len"]
        core.write_group_payload(partial, g, core.FaultInjector(None))
        j["completed_groups"].append(core.serialize_group(g))
        j["durable_end"] = durable
        core.atomic_journal(journal, j)
        row_start += g["row_count"]
        source_cursor = g["source_end"]
        event_q.put({
            "type": "GROUP",
            "worker": worker_id,
            "month_id": c["month_id"],
            "date_key": c["date_key"],
            "group": gi + 1,
            "groups": group_count,
            "rows": row_start,
            "day_rows": expected_rows,
            "source_pos": int(source_view.tell()),
        })
        if stop_event.is_set():
            raise WorkerSafeStop()

    if source_cursor != day_end:
        raise core.Blocked("SOURCE_DAY_END_NOT_EXACT")
    if row_start != expected_rows:
        raise core.Blocked("SOURCE_ROW_COUNT_NOT_EXACT")
    source_view.verify_path_binding()
    core.finalize_partial_container(partial, journal, c, oracle, zstd)
    return "BUILT" if fresh else "RESUMED"


def _worker_main(worker_id: str, source_root: str, scratch_root: str, month_id: str,
                 month: dict, days: list, ledger_sha: str, ids: dict,
                 event_q, command_q, stop_event):
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        zstd = core.require_windows_pilot_runtime()
        ordered = sorted(days, key=lambda x: int(x["first_offset"]))
        if not ordered:
            raise MultiworkBlocked("WORKER_EMPTY_MONTH")
        src = core.source_for(Path(source_root), ordered[0])
        with StreamingMonthSource(
            src, int(month["source_size"]), month["source_sha256"],
            stop_event=stop_event, event_q=event_q, worker_id=worker_id, month_id=month_id,
        ) as view:
            identity = dict(view.identity)
            event_q.put({
                "type": "OPENED", "worker": worker_id,
                "month_id": month_id, "identity": identity,
            })
            cmd = command_q.get()
            if cmd.get("type") == "STOP" or stop_event.is_set():
                event_q.put({"type": "MONTH_STOPPED", "worker": worker_id, "month_id": month_id})
                return
            if cmd.get("type") != "START":
                raise MultiworkBlocked("WORKER_EXPECTED_START")
            build_keys = set(cmd.get("build_keys", []))
            staged=[]
            month_rows_done=0
            for c in ordered:
                if stop_event.is_set():
                    event_q.put({"type": "MONTH_STOPPED", "worker": worker_id, "month_id": month_id})
                    return
                key=c["date_key"]
                if key in build_keys:
                    event_q.put({"type":"STATE","worker":worker_id,"month_id":month_id,"state":"BUILDING","date_key":key})
                    oracle = core.make_oracle(c, month, identity, ledger_sha, ids)
                    sp = _scratch_day_paths(Path(scratch_root), month_id, key)
                    core.free_space_gate(Path(scratch_root), int(c["source_day_bytes"]))
                    try:
                        status = _build_or_resume_day_cooperative(
                            view, c, oracle, sp["partial"], sp["journal"], zstd,
                            stop_event, event_q, worker_id
                        )
                    except WorkerSafeStop:
                        event_q.put({"type": "MONTH_STOPPED", "worker": worker_id, "month_id": month_id})
                        return
                    # A fully validated scratch day may have required no source reads.
                    if view.tell() < int(c["block_end_offset"]):
                        view.scan_to(int(c["block_end_offset"]))
                    if view.tell() != int(c["block_end_offset"]):
                        raise core.Blocked("SINGLE_PASS_DAY_END_MISMATCH:"+key)
                    month_rows_done += int(c["rows"])
                    item={
                        "date_key":key,"scratch_partial":str(sp["partial"]),
                        "scratch_journal":str(sp["journal"]),"scratch_status":status,
                        "scratch_namespace":sp.get("namespace","RC3"),
                    }
                    staged.append(item)
                    event_q.put({
                        "type":"DAY_STAGED","worker":worker_id,"month_id":month_id,
                        "date_key":key,"month_rows_done":month_rows_done,
                        "bytes_scanned":int(view.tell()),"scratch_status":status,
                        "scratch_namespace":sp.get("namespace","RC3"),
                    })
                else:
                    event_q.put({"type":"STATE","worker":worker_id,"month_id":month_id,"state":"SCANNING","date_key":key})
                    view.scan_to(int(c["block_end_offset"]))
            digest=view.finish_and_verify()
            event_q.put({
                "type":"MONTH_VERIFIED","worker":worker_id,"month_id":month_id,
                "identity":identity,"actual_sha256":digest,
                "bytes_scanned":int(month["source_size"]),"staged":staged,
            })
    except WorkerSafeStop:
        event_q.put({"type": "MONTH_STOPPED", "worker": worker_id, "month_id": month_id})
    except BaseException as exc:
        event_q.put({
            "type": "ERROR", "worker": worker_id, "month_id": month_id,
            "error_type": type(exc).__name__, "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        raise



def _day_state_present(state: dict):
    return any(bool(state.get(k)) for k in (
        "container","partial","journal","journal_atomic","commit","commit_partial","commit_stage"
    ))


def _canonical_transient_dates(dest_root: Path, days: list):
    dates=[]
    manifest_atomic = core.manifest_path(dest_root).with_suffix(core.manifest_path(dest_root).suffix + ".partial")
    manifest_shadow = core.strict_lstat(manifest_atomic, allow_missing=True) is not None
    for c in days:
        pp=core._full_day_paths(dest_root,c)
        state=core.transaction_state(pp,dest_root)
        transient = any(state.get(k, False) for k in (
            "partial","journal","journal_atomic","commit_partial","commit_stage"
        ))
        pair_mismatch = bool(state.get("container")) != bool(state.get("commit"))
        if transient or pair_mismatch:
            dates.append(c["date_key"])
    if manifest_shadow and not dates:
        raise core.Blocked("MANIFEST_ATOMIC_WITHOUT_IDENTIFIABLE_DAY_TRANSACTION")
    return dates


def _recover_full_serial_day(source_root: Path, dest_root: Path, c: dict, month: dict,
                             ledger_sha: str, ids: dict, zstd):
    """Recover a canonical FULL_SERIAL transaction with the exact FULL release oracle.

    A FULL_SERIAL journal was created with the ids returned by full_release_materials().
    The generic single-day run_one_day() route intentionally uses file_ids() instead and
    therefore cannot be used as a compatibility bridge for a FULL_SERIAL journal.
    """
    src = core.source_for(source_root, c)
    lock = None
    result = None
    with core.PinnedSource(src, int(month["source_size"]), month["source_sha256"]) as source_guard:
        oracle = core.make_oracle(c, month, dict(source_guard.identity), ledger_sha, ids)
        lock = core.acquire_lock(dest_root)
        try:
            result = core._run_day_already_locked(
                source_guard, c, oracle, dest_root, zstd, core.FaultInjector(None)
            )
        finally:
            if lock is not None:
                core.release_lock(lock)
                lock = None
    if result not in ("REUSED", "RESUMED", "RESUMED_PUBLICATION", "RESUMED_MANIFEST", "BUILT"):
        raise core.Blocked("PRE_MULTIWORK_RECOVERY_UNEXPECTED_STATUS:" + str(result))
    return result


def _normalize_interrupted_canonical_transactions(source_root: Path, dest_root: Path, days: list,
                                                   months: dict, ledger_sha: str, ids: dict, zstd):
    dates = _canonical_transient_dates(dest_root, days)
    if not dates:
        return 0
    by_key = {c["date_key"]: c for c in days}
    print(f"PRE_MULTIWORK_RECOVERY_DAYS={len(dates)}", flush=True)
    for key in dates:
        c = by_key.get(key)
        if c is None:
            raise core.Blocked("PRE_MULTIWORK_RECOVERY_DATE_NOT_IN_PLAN:" + key)
        month = months.get(c["month_id"])
        if month is None:
            raise core.Blocked("PRE_MULTIWORK_RECOVERY_MONTH_NOT_IN_PLAN:" + c["month_id"])
        print(f"PRE_MULTIWORK_RECOVERY DATE={key} START", flush=True)
        status = _recover_full_serial_day(source_root, dest_root, c, month, ledger_sha, ids, zstd)
        print(f"PRE_MULTIWORK_RECOVERY DATE={key} PASS STATUS={status}", flush=True)
    return len(dates)

def _canonical_day_has_state(dest_root: Path, c):
    pp = core.paths_for_day(dest_root, c)
    state = core.transaction_state(pp, dest_root)
    return _day_state_present(state), pp, state


def _publish_ready_day(dest_root: Path, c, month, parent_pin: ParentMonthPin, ledger_sha, ids, zstd,
                       scratch_partial: Path, scratch_journal: Path):
    guard = ExternalWorkerPinGuard(parent_pin)
    identity = dict(parent_pin.identity)
    oracle = core.make_oracle(c, month, identity, ledger_sha, ids)
    core.validate_validated_partial(
        Path(scratch_partial), Path(scratch_journal), c, oracle, zstd,
        allowed_states=("VALIDATED_PENDING_PUBLISH",)
    )
    has_state, pp, state = _canonical_day_has_state(dest_root, c)
    if has_state:
        raise core.Blocked("CANONICAL_STATE_APPEARED_DURING_WORKER_BUILD:" + c["date_key"])

    # Two-file transfer is intentionally crash-recoverable rather than falsely atomic.
    # Any crash between the moves leaves a zero-authority orphan that RC1 classifies safely.
    core.secure_replace(Path(scratch_journal), pp["journal"])
    core.secure_replace(Path(scratch_partial), pp["partial"])
    result = core._run_day_already_locked(guard, c, oracle, dest_root, zstd, core.FaultInjector(None))
    return result


def _cleanup_empty_scratch_day(path: Path):
    path = Path(path)
    try:
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except Exception:
        pass


def _atomic_coordinator_state(path: Path, state: dict):
    # The coordinator owns this checkpoint under the destination lease. An
    # attempt-scoped temporary cannot poison retry or delete another writer's work.
    path = Path(path)
    tmp = path.with_name(path.name + ".pending." + str(os.getpid()) + "." + uuid.uuid4().hex)
    raw = core.stable_json(state) + b"\n"
    fd = core.secure_create_new_fd(tmp)
    identity = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        core.secure_replace(tmp, path)
        if core.secure_read_all(path) != raw:
            raise MultiworkBlocked("COORDINATOR_CHECKPOINT_READBACK")
    finally:
        if fd != -1: os.close(fd)
        current = core.strict_lstat(tmp, allow_missing=True)
        if current is not None:
            if not os.path.samestat(identity, current):
                raise MultiworkBlocked("COORDINATOR_TEMP_IDENTITY_CHANGED")
            core.safe_unlink_regular(tmp)


def _progress_bar(percent: float, width: int = 30):
    filled = max(0, min(width, int(round(width * percent / 100.0))))
    if percent < 100.0:
        filled = min(filled, max(0, width - 1))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _fmt_rate(value: float):
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value/1_000:.2f}K"
    return f"{value:.1f}"


def _print_progress(*, total_rows, published_rows, inflight_rows, published_days, total_days,
                    counts, active_workers, worker_limit, months_done, total_months, started, force=False,
                    last_print_ref=None, worker_states=None, worker_scan_bytes=None,
                    completed_source_bytes=0, total_source_bytes=0, final_reconciled=False):
    now = time.perf_counter()
    if not force and last_print_ref is not None and now - last_print_ref[0] < PROGRESS_INTERVAL_SECONDS:
        return
    if last_print_ref is not None:
        last_print_ref[0] = now
    # Publication is the durable completion boundary; staged rows can still fail.
    effective = min(total_rows, max(0, published_rows))
    row_pct = 100.0 * effective / total_rows if total_rows else 100.0
    if not final_reconciled:
        row_pct = min(row_pct, 99.999)
    elapsed = max(now - started, 1e-9)
    rate = effective / elapsed
    publish_eta = ref.fmt_eta((total_rows-effective)/rate) if rate > 0 else "UNKNOWN"
    states=worker_states or {}
    scans=worker_scan_bytes or {}
    scanned=min(int(total_source_bytes or 0), int(completed_source_bytes)+sum(int(x) for x in scans.values()))
    source_pct=(100.0*scanned/total_source_bytes) if total_source_bytes else 0.0
    source_mib_s=(scanned/1024**2)/elapsed
    eta = ref.fmt_eta((total_source_bytes-scanned)/(source_mib_s*1024**2)) if source_mib_s>0 and total_source_bytes else "UNKNOWN"
    state_counts={}
    for st in states.values(): state_counts[st]=state_counts.get(st,0)+1
    try:
        mem = windows_memory_status();ram_avail = mem["available"] / 1024**3
    except Exception:
        ram_avail = -1.0
    try:
        d_free = shutil.disk_usage(Path("D:\\")).free / 1024**3 if os.name == "nt" else -1.0
    except Exception:
        d_free = -1.0
    print(
        f"PROGRESS {_progress_bar(row_pct)} ROW_PCT={row_pct:7.3f}% SOURCE_PCT={source_pct:7.3f}% "
        f"FINAL_RECONCILED={'YES' if final_reconciled else 'NO'} "
        f"DAYS={published_days}/{total_days} MONTHS={months_done}/{total_months} "
        f"WORKERS={active_workers}/{worker_limit} BUILDING={state_counts.get('BUILDING',0)} "
        f"SCANNING={state_counts.get('SCANNING',0)} LAUNCHING={state_counts.get('LAUNCHING',0)} "
        f"ROWS_S={_fmt_rate(rate)} ETA_PUBLISH={publish_eta} "
        f"INFLIGHT_ROWS={sum(inflight_rows.values())} SOURCE_MIB_S={source_mib_s:.2f} ETA_SCAN={eta} "
        f"BUILT={counts['BUILT']} REUSED={counts['REUSED']} RESUMED={counts['RESUMED']} "
        f"RAM_AVAILABLE_GIB={ram_avail:.2f} D_FREE_GIB={d_free:.2f}",
        flush=True,
    )


def _classify_month_build_keys(dest_root: Path, days: list):
    build=[];existing=[]
    for c in days:
        pp=core._full_day_paths(dest_root,c)
        state=core.transaction_state(pp,dest_root)
        transient=any(bool(state.get(k)) for k in ("partial","journal","journal_atomic","commit_partial","commit_stage"))
        pair_mismatch=bool(state.get("container")) != bool(state.get("commit"))
        if transient or pair_mismatch:
            raise core.Blocked("CANONICAL_TRANSIENT_AFTER_PRE_RECOVERY:"+c["date_key"])
        if bool(state.get("container")) and bool(state.get("commit")):
            existing.append(c["date_key"])
        elif not _day_state_present(state):
            build.append(c["date_key"])
        else:
            raise core.Blocked("CANONICAL_STATE_UNCLASSIFIED:"+c["date_key"])
    return build,existing


def _validate_existing_for_month(dest_root: Path, days: list, existing_keys: set, all_keys: set, month: dict,
                                 parent_pin: ParentMonthPin, ledger_sha: str, ids: dict, cert, zstd, counts):
    identity=dict(parent_pin.identity)
    guard=ExternalWorkerPinGuard(parent_pin)
    published_rows=0;published_days=0
    core._full_manifest(dest_root,all_keys,complete=False)
    for c in days:
        if c["date_key"] not in existing_keys: continue
        pp=core._full_day_paths(dest_root,c)
        if core._is_r8_pair(pp,cert):
            guard.verify_full()
            current_manifest=core._full_manifest(dest_root,all_keys,complete=False)
            status=core.validate_certified_r8_day(
                pp,c,month,identity,ledger_sha,cert,dest_root,zstd,
                current_manifest["records"].get(c["date_key"]),
            )
            guard.verify_full()
        else:
            oracle=core.make_oracle(c,month,identity,ledger_sha,ids)
            status=core._run_day_already_locked(guard,c,oracle,dest_root,zstd,core.FaultInjector(None))
        if status not in ("REUSED","RESUMED","RESUMED_PUBLICATION","RESUMED_MANIFEST","BUILT"):
            raise core.Blocked("MULTIWORK_UNEXPECTED_EXISTING_STATUS:"+str(status))
        counts["RESUMED" if str(status).startswith("RESUMED") else status]+=1
        published_rows += int(c["rows"]);published_days += 1
    return published_rows,published_days




def _publisher_main(command_q, event_q, stop_event, *, dest_root: str, coordinator_path: str,
                    all_keys: set, months: dict, by_month: dict, ledger_sha: str, ids: dict,
                    cert: dict, workers_effective: int, total_days: int, total_rows: int):
    """Dedicated canonical single-writer process.

    Worker/hash/build throughput is independent of canonical validation/publication. The
    parent keeps the original month pin open continuously; this process opens an additional
    overlapping source pin while publishing one month at a time.
    """
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        zstd=core.require_windows_pilot_runtime()
        dest_root=Path(dest_root)
        coordinator_path=Path(coordinator_path)
        counts={"BUILT":0,"REUSED":0,"RESUMED":0,"FAILED":0}
        published_rows=0
        published_days=0
        months_published=0
        event_q.put({"type":"PUBLISHER_READY"})

        while True:
            cmd=command_q.get()
            typ=cmd.get("type")
            if typ=="STOP":
                event_q.put({
                    "type":"PUBLISHER_STOPPED","published_days":published_days,
                    "published_rows":published_rows,"months_published":months_published,
                    "counts":dict(counts),
                })
                return
            if typ!="PUBLISH_MONTH":
                raise MultiworkBlocked("PUBLISHER_COMMAND_UNKNOWN:"+str(typ))
            if stop_event.is_set():
                event_q.put({
                    "type":"PUBLISHER_STOPPED","published_days":published_days,
                    "published_rows":published_rows,"months_published":months_published,
                    "counts":dict(counts),
                })
                return

            month_id=str(cmd["month_id"])
            identity=dict(cmd["identity"])
            build_keys=set(cmd.get("build_keys") or [])
            existing_keys=set(cmd.get("existing_keys") or [])
            staged=list(cmd.get("staged") or [])
            month_keys={c["date_key"] for c in by_month[month_id]}
            if build_keys | existing_keys != month_keys:
                raise MultiworkBlocked("PUBLISHER_MONTH_CLASSIFICATION_INCOMPLETE:"+month_id)
            if build_keys & existing_keys:
                raise MultiworkBlocked("PUBLISHER_MONTH_CLASSIFICATION_OVERLAP:"+month_id)

            pin=ParentMonthPin(Path(identity["normalized_path"]),identity).open()
            try:
                pin.verify()
                event_q.put({"type":"PUBLISH_MONTH_START","month_id":month_id})

                add_rows,add_days=_validate_existing_for_month(
                    dest_root,by_month[month_id],existing_keys,all_keys,months[month_id],pin,
                    ledger_sha,ids,cert,zstd,counts,
                )
                published_rows += add_rows
                published_days += add_days

                staged_by_key={str(x["date_key"]):x for x in staged}
                if set(staged_by_key)!=build_keys:
                    raise MultiworkBlocked("PUBLISHER_STAGED_DAY_SET_MISMATCH:"+month_id)

                for c in by_month[month_id]:
                    key=c["date_key"]
                    if key not in build_keys:
                        continue
                    if stop_event.is_set():
                        event_q.put({
                            "type":"PUBLISHER_STOPPED","published_days":published_days,
                            "published_rows":published_rows,"months_published":months_published,
                            "counts":dict(counts),
                        })
                        return
                    item=staged_by_key[key]
                    partial=Path(item["scratch_partial"])
                    journal=Path(item["scratch_journal"])
                    _publish_ready_day(
                        dest_root,c,months[month_id],pin,ledger_sha,ids,zstd,partial,journal
                    )
                    logical_status=str(item.get("scratch_status","RESUMED"))
                    counts["RESUMED" if logical_status.startswith("RESUMED") else "BUILT"] += 1
                    published_rows += int(c["rows"])
                    published_days += 1
                    _cleanup_empty_scratch_day(partial.parent)
                    state={
                        "schema":COORDINATOR_SCHEMA,"wrapper_sha256":wrapper_sha256(),
                        "core_runner_sha256":ids["runner_sha256"].upper(),
                        "days_published":published_days,"days_total":total_days,
                        "rows_published":published_rows,"rows_total":total_rows,
                        "last_date_key":key,"counts":dict(counts),
                        "workers_effective":workers_effective,
                        "source_pass":"ONE_PHYSICAL_PASS_PER_MONTH",
                        "publisher":"DEDICATED_SINGLE_WRITER_PROCESS",
                        "updated_unix_ns":time.time_ns(),
                    }
                    _atomic_coordinator_state(coordinator_path,state)
                    event_q.put({
                        "type":"PUBLISH_DAY","month_id":month_id,"date_key":key,
                        "published_days":published_days,"published_rows":published_rows,
                        "counts":dict(counts),
                    })

                months_published += 1
                event_q.put({
                    "type":"MONTH_PUBLISHED","month_id":month_id,
                    "published_days":published_days,"published_rows":published_rows,
                    "months_published":months_published,"counts":dict(counts),
                })
            finally:
                pin.close()
    except BaseException as exc:
        event_q.put({
            "type":"PUBLISHER_ERROR","error_type":type(exc).__name__,"error":str(exc),
            "traceback":traceback.format_exc(),
        })
        # The coordinator may be draining telemetry during shutdown. Preserve
        # failure in the process exit status even when this event is discarded.
        raise
def _close_mp_queue(q):
    if q is None:
        return
    try:
        q.close()
    except BaseException:
        pass
    try:
        q.cancel_join_thread()
    except BaseException:
        pass


def _bounded_shutdown_process_tree(active, publisher_proc, publish_q, event_q, stop_event,
                                   prefix: str, timeout_seconds: float = SAFE_STOP_JOIN_TIMEOUT_SECONDS,
                                   terminate_grace_seconds: float = SAFE_STOP_TERMINATE_GRACE_SECONDS,
                                   kill_grace_seconds: float = SAFE_STOP_KILL_GRACE_SECONDS):
    """Stop all RC4 processes without allowing a second Ctrl+C to escape cleanup.

    Normal path is cooperative. If a process remains after the bounded wait, it is terminated,
    then killed only as a last resort. Callers must not print SAFE_STOP=YES until this returns.
    """
    prior_sigint = None
    if threading.current_thread() is threading.main_thread():
        try:
            prior_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except BaseException:
            prior_sigint = None

    forced_terminate = []
    forced_kill = []
    try:
        stop_event.set()
        for info in active.values():
            try:
                info["command_q"].put_nowait({"type": "STOP"})
            except BaseException:
                pass
        try:
            publish_q.put_nowait({"type": "STOP"})
        except BaseException:
            pass

        deadline = time.perf_counter() + max(0.1, float(timeout_seconds))
        last_report = 0.0
        while True:
            # Drain telemetry while joining: bounded child feeders must be able to exit.
            for _ in range(256):
                try:
                    event_q.get_nowait()
                except queue.Empty:
                    break
            waiting = []
            for wid, info in list(active.items()):
                proc = info["process"]
                proc.join(timeout=0.02)
                if proc.is_alive():
                    waiting.append((wid, proc))
            publisher_waiting = bool(publisher_proc is not None and publisher_proc.is_alive())
            if not waiting and not publisher_waiting:
                break
            now = time.perf_counter()
            if now >= deadline:
                break
            if now - last_report >= 1.0:
                if waiting:
                    print(f"{prefix}_WAITING_WORKERS={len(waiting)}", flush=True)
                if publisher_waiting:
                    print(f"{prefix}_WAITING_PUBLISHER=1", flush=True)
                last_report = now
            time.sleep(0.10)

        survivors = []
        for wid, info in list(active.items()):
            proc = info["process"]
            if proc.is_alive():
                survivors.append(("WORKER:" + wid, proc))
        if publisher_proc is not None and publisher_proc.is_alive():
            survivors.append(("PUBLISHER", publisher_proc))

        if survivors:
            for label, proc in survivors:
                try:
                    proc.terminate()
                    forced_terminate.append(label)
                except BaseException:
                    pass
            term_deadline = time.perf_counter() + max(0.1, float(terminate_grace_seconds))
            while time.perf_counter() < term_deadline:
                if not any(proc.is_alive() for _, proc in survivors):
                    break
                for _, proc in survivors:
                    proc.join(timeout=0.02)
                time.sleep(0.05)

        stubborn = [(label, proc) for label, proc in survivors if proc.is_alive()]
        if stubborn:
            for label, proc in stubborn:
                try:
                    proc.kill()
                    forced_kill.append(label)
                except BaseException:
                    pass
            kill_deadline = time.perf_counter() + max(0.1, float(kill_grace_seconds))
            while time.perf_counter() < kill_deadline:
                if not any(proc.is_alive() for _, proc in stubborn):
                    break
                for _, proc in stubborn:
                    proc.join(timeout=0.02)
                time.sleep(0.05)

        still_alive = []
        for wid, info in list(active.items()):
            proc = info["process"]
            if proc.is_alive():
                still_alive.append("WORKER:" + wid)
        if publisher_proc is not None and publisher_proc.is_alive():
            still_alive.append("PUBLISHER")
        if still_alive:
            raise MultiworkBlocked("SHUTDOWN_PROCESS_TREE_STILL_ALIVE:" + ",".join(still_alive))

        # Reap all children and close feeder threads so the parent itself can return to PowerShell.
        for _, info in list(active.items()):
            proc = info["process"]
            proc.join(timeout=0.1)
            _close_mp_queue(info.get("command_q"))
        if publisher_proc is not None and publisher_proc.pid is not None:
            publisher_proc.join(timeout=0.1)
        _close_mp_queue(publish_q)
        _close_mp_queue(event_q)

        return {
            "forced_terminate": forced_terminate,
            "forced_kill": forced_kill,
            "process_tree_clean": True,
            "child_exit_codes": {
                **{"WORKER:" + wid: info["process"].exitcode
                   for wid, info in active.items() if info["process"].pid is not None},
                **({"PUBLISHER": publisher_proc.exitcode}
                   if publisher_proc is not None and publisher_proc.pid is not None else {}),
            },
        }
    finally:
        if prior_sigint is not None:
            try:
                signal.signal(signal.SIGINT, prior_sigint)
            except BaseException:
                pass



def _cooperative_stop_confirmed(report):
    return (isinstance(report, dict) and report.get("process_tree_clean") is True
            and report.get("forced_terminate") == [] and report.get("forced_kill") == []
            and isinstance(report.get("child_exit_codes"), dict)
            and all(code == 0 for code in report["child_exit_codes"].values()))


def _finalize_coordinator_resources(active, sealed_pins, publisher_proc, lock, lease, primary_error):
    def cleanup_error(label, error):
        nonlocal primary_error
        print("FINALIZATION_ERROR=" + label + ":" + str(error), flush=True)
        # An interrupt cannot mask a failed cleanup and become SAFE_STOP/130.
        if primary_error is None or isinstance(primary_error[1], KeyboardInterrupt):
            primary_error = (MultiworkBlocked, MultiworkBlocked("FINALIZATION_" + label), None)

    children_alive = publisher_proc.is_alive() or any(
        info["process"].is_alive() for info in active.values())
    if children_alive:
        print("LOCK_RETAINED=YES PROCESS_TREE_CLEAN=NO", flush=True)
        cleanup_error("LOCK_RETAINED_LIVE_CHILD", "process tree not clean")
        return primary_error
    for info in active.values():
        pin = info.get("parent_pin")
        if pin is not None:
            try: pin.close()
            except BaseException as exc:
                cleanup_error("SOURCE_PIN", exc)
    while sealed_pins:
        _, pin = sealed_pins.popitem()
        try: pin.close()
        except BaseException as exc:
            cleanup_error("SEALED_PIN", exc)
    if lock is not None:
        try:
            with core.FullSerialLockBoundary(): core.release_lock(lock)
        except BaseException as exc:
            cleanup_error("WRITER_LOCK", exc)
    if lease is not None:
        try: lease.close()
        except BaseException as exc:
            cleanup_error("LEASE", exc)
    return primary_error


def execute_multiwork(source_root: Path, dest_root: Path, scratch_root: Path,
                      ledger_zip: Path, core_gate_file=None, core_gate_sha256=None,
                      multiwork_gate_file=None, multiwork_gate_sha256=None,
                      workers_requested="AUTO", max_workers=DEFAULT_MAX_WORKERS,
                      ram_target_percent=DEFAULT_RAM_TARGET_PERCENT, *,
                      chain_file=None, chain_sha256=None, b06_sha256=None):
    # Old administrative gates cannot admit this changed candidate.
    if any(x is not None for x in (core_gate_file, core_gate_sha256,
                                   multiwork_gate_file, multiwork_gate_sha256)):
        raise MultiworkBlocked("LEGACY_ADMINISTRATIVE_OWNER_GATE_REVOKED")
    if not chain_file or not chain_sha256 or not b06_sha256:
        raise MultiworkBlocked("TECHNICAL_RELEASE_CHAIN_REQUIRED")
    control = Path(__file__).resolve().parent.parent / "control"
    sys.path.insert(0, str(control))
    from FULL_RELEASE_CHAIN import ReleaseChain
    with ReleaseChain(chain_file, chain_sha256, b06_sha256, control.parent) as admission:
        # Compatibility entrypoint: validate every legacy argument, then enter
        # the same bounded lifecycle as the menu. Engine success alone is not FULL.
        instance = admission.instance
        for label, path in (('source', source_root), ('dest', dest_root), ('scratch', scratch_root)):
            if _norm(Path(path)) != _norm(Path(instance['bindings'][label + '_root'])):
                raise MultiworkBlocked('ENTRYPOINT_ROOT_DRIFT:' + label)
        if _norm(Path(ledger_zip)) != _norm(Path(instance['ledger_path'])):
            raise MultiworkBlocked('ENTRYPOINT_LEDGER_DRIFT')
        limits = instance['resources']
        if max_workers != limits['max_workers'] or ram_target_percent != limits['ram_target_percent']:
            raise MultiworkBlocked('ENTRYPOINT_RESOURCE_DRIFT')
        admission.revalidate()
    import FULL_RUNNER
    return FULL_RUNNER.main(['--stage', 'FULL', '--chain-file', str(chain_file),
        '--chain-sha256', chain_sha256, '--b06-sha256', b06_sha256,
        '--workers', str(workers_requested)])


def _execute_admitted_multiwork(source_root, dest_root, scratch_root, ledger_zip,
                                 workers_requested, max_workers, ram_target_percent, admission, *, completion=None):
    if os.name != "nt":
        raise MultiworkBlocked("MULTIWORK_REQUIRES_WINDOWS")
    zstd = core.require_windows_pilot_runtime()
    base = Path(core.__file__).resolve().parent
    contract, cert, ids = core.full_release_materials(base)
    days, months, ledger_sha = core.load_ledgers(ledger_zip)
    days = core.validate_full_plan(days, months, ledger_sha, contract)
    core_bindings = core.full_gate_bindings(source_root, dest_root, scratch_root, ids, contract)
    if not days or not months:
        raise MultiworkBlocked("FULL_EMPTY_PLAN")
    workers, mem = choose_workers(workers_requested, len(months), max_workers, ram_target_percent)
    admission.validate_full(core_bindings, workers, max_workers, ram_target_percent)

    total_rows = sum(int(c["rows"]) for c in days)
    total_days = len(days)
    total_source_bytes = sum(int(m["source_size"]) for m in months.values())
    month_ids = sorted(months)
    by_month = {m: sorted([c for c in days if c["month_id"] == m], key=lambda x:int(x["first_offset"])) for m in month_ids}
    all_keys = {c["date_key"] for c in days}
    counts = {"BUILT": 0, "REUSED": 0, "RESUMED": 0, "FAILED": 0}
    identities = {}
    published_rows = 0
    published_days = 0
    inflight_rows = {}
    worker_states = {}
    worker_scan_bytes = {}
    completed_source_bytes = 0
    months_done = 0
    months_verified = 0
    publish_backlog = 0
    verified_outbox = {}
    next_publish_month = 0
    publisher_state = "STARTING"
    started = time.perf_counter()
    last_print = [0.0]
    last_productive = [time.perf_counter()]

    print("TICKSTORE_FULL_MULTIWORK=START", flush=True)
    print(f"WRAPPER_SCHEMA={WRAPPER_SCHEMA}", flush=True)
    print(f"WRAPPER_SHA256={wrapper_sha256()}", flush=True)
    print(f"CORE_RUNNER_SHA256={ids['runner_sha256'].upper()}", flush=True)
    print(f"WORKERS_REQUESTED={workers_requested}", flush=True)
    print(f"WORKERS_EFFECTIVE={workers}", flush=True)
    print(f"CPU_LOGICAL={os.cpu_count() or 1}", flush=True)
    print(f"RAM_TARGET_PERCENT={ram_target_percent}", flush=True)
    print(f"RAM_TOTAL_GIB={mem['total']/1024**3:.2f}", flush=True)
    print(f"RAM_AVAILABLE_GIB={mem['available']/1024**3:.2f}", flush=True)
    print("SOURCE_PASS=ONE_PHYSICAL_PASS_PER_MONTH", flush=True)
    print("SOURCE_HASH=INLINE_WITH_SCAN_AND_BUILD", flush=True)
    print("WORKER_DAY_ACK_BARRIER=NO", flush=True)
    print("WORKER_START_BARRIER=PREQUEUED_AFTER_PARENT_PIN", flush=True)
    print("PUBLICATION=DEDICATED_SINGLE_WRITER_PROCESS_AFTER_MONTH_SHA_VERIFIED", flush=True)
    print("PUBLICATION_OVERLAPS_WORKER_BUILD=YES", flush=True)
    print("SAFE_STOP=GROUP_OR_SCAN_CHUNK_BOUNDARY_PLUS_PUBLISH_DAY_BOUNDARY", flush=True)
    print(f"SAFE_STOP_JOIN_TIMEOUT_SECONDS={int(SAFE_STOP_JOIN_TIMEOUT_SECONDS)}", flush=True)
    print("SAFE_STOP_SECOND_CTRL_C_DURING_CLEANUP=IGNORED", flush=True)
    print("RESUME=ADMITTED_INSTANCE_ONLY; HISTORICAL_SCRATCH=PRESERVED", flush=True)
    print(f"PRODUCTIVITY_STALL_SECONDS={int(PRODUCTIVITY_STALL_SECONDS)}", flush=True)

    core.strict_directory(dest_root, create=False)
    core.strict_directory(scratch_root, create=False)
    # The final path is selected under the destination lease, before child launch.
    coordinator_path = None

    ctx = mp.get_context("spawn")
    event_q = ctx.Queue(maxsize=8 * workers + 32)
    stop_event = ctx.Event()
    publish_q = ctx.Queue(maxsize=2 * workers + 1)
    active = {}
    sealed_pins = {}
    pending_months = list(month_ids)
    lock = None
    lease = None
    primary_error = None
    safe_stop_report = None
    reconciliation = None
    heartbeat = None
    worker_seq = [0]

    job = None
    last_memory = [0.0]
    last_memory_print = [0.0]
    memory_state = ['LAUNCH']
    draining_since = [None]
    native_stop = None
    publisher_proc = None
    publisher_kwargs = dict(
        **{
            "command_q":publish_q,"event_q":event_q,"stop_event":stop_event,
            "dest_root":str(dest_root),"coordinator_path":str(coordinator_path),
            "all_keys":all_keys,"months":months,"by_month":by_month,"ledger_sha":ledger_sha,
            "ids":ids,"cert":cert,"workers_effective":workers,
            "total_days":total_days,"total_rows":total_rows,
        },
    )

    def start_month(month_id):
        ordered=by_month[month_id]
        src=core.source_for(Path(source_root),ordered[0])
        parent_pin=ParentMonthPin.open_from_expected(
            src,int(months[month_id]["source_size"]),months[month_id]["source_sha256"]
        )
        try:
            build_keys,existing_keys=_classify_month_build_keys(dest_root,ordered)
            worker_seq[0] += 1
            worker_id = f"W{worker_seq[0]:03d}-{month_id}"
            command_q = ctx.Queue(maxsize=2)
            command_q.put({"type":"START","build_keys":build_keys})
            proc = job.start(ctx, _worker_main,
                args=(worker_id, str(source_root), str(scratch_root), month_id,
                      months[month_id], ordered, ledger_sha, ids,
                      event_q, command_q, stop_event),
                name="TICKSTORE-" + worker_id,
            )
            active[worker_id] = {
                "process": proc, "command_q": command_q, "month_id": month_id,
                "identity": dict(parent_pin.identity), "parent_pin": parent_pin,
                "build_keys": list(build_keys), "existing_keys": list(existing_keys),
            }
            worker_states[worker_id]="LAUNCHING"
            worker_scan_bytes[worker_id]=0
        except BaseException:
            parent_pin.close()
            raise

    def stop_and_join_all(prefix: str):
        return _bounded_shutdown_process_tree(
            active, publisher_proc, publish_q, event_q, stop_event, prefix
        )

    def fill_worker_slots():
        # Bound both running builds and sealed months awaiting the single writer.
        while (pending_months and not stop_event.is_set() and len(active) < workers
               and len(active) + publish_backlog < 2 * workers):
            if check_memory(force=True) != 'LAUNCH':
                break
            start_month(pending_months.pop(0))

    def check_memory(force=False):
        if heartbeat is not None:
            heartbeat.update(committed_rows=published_rows, committed_days=published_days,
                             active_workers=len(active), pending_publications=publish_backlog)
        now = time.perf_counter()
        if not force and now - last_memory[0] < 1.0:
            return memory_state[0]
        sample = job.memory_snapshot(); memory = windows_memory_status()
        if heartbeat is not None: heartbeat.update(ram_tree=sample, ram_available_bytes=memory['available'])
        decision = memory_decision(sample, memory, ram_target_percent)
        if now - last_memory_print[0] >= PROGRESS_INTERVAL_SECONDS or decision != memory_state[0]:
            print('RAM_TREE=' + json.dumps(dict(sample, decision=decision, target_percent=ram_target_percent,
                  total_bytes=memory['total'], available_bytes=memory['available']), sort_keys=True), flush=True)
            last_memory_print[0] = now
        last_memory[0] = now; memory_state[0] = decision
        if decision == 'SAFE_STOP':
            print('SAFE_STOP_REASON=RAM_PRESSURE', flush=True)
            raise ResourceSafeStop('RAM_PRESSURE')
        if decision == 'DRAIN':
            if draining_since[0] is None: draining_since[0] = now
            if not active and not publish_backlog and now - draining_since[0] >= 30:
                print('SAFE_STOP_REASON=RAM_NO_LAUNCH_CAPACITY_30S', flush=True)
                raise ResourceSafeStop('RAM_NO_LAUNCH_CAPACITY_30S')
        else:
            draining_since[0] = None
        return decision

    try:
        lease = FullProcessLease(dest_root)
        admission.revalidate()
        native_stop = StopEvent(admission.instance["run_id"])
        scratch_root = instance_scratch(scratch_root, admission, core_bindings)
        coordinator_path = scratch_root/'FULL_MULTIWORK_RC4R2'/'COORDINATOR_STATE.json'
        publisher_kwargs['coordinator_path'] = str(coordinator_path)
        core.strict_directory(coordinator_path.parent, create=True)
        print("FULL_OWNER=" + json.dumps(lease.identity, sort_keys=True) + " LEASE=NATIVE_HANDLE", flush=True)
        heartbeat = Heartbeat(scratch_root/('HEARTBEAT_' + uuid.uuid4().hex + '.json'),
            _atomic_coordinator_state, dict(run_id=admission.instance['run_id'],
            code_manifest_sha256=admission.descriptor['code_manifest_sha256'],
            instance_sha256=admission.descriptor['instance_sha256'])).start()
        heartbeat.update(phase='NORMALIZATION', total_rows=total_rows)
        recovered_before_parallel = _normalize_interrupted_canonical_transactions(
            source_root, dest_root, days, months, ledger_sha, ids, zstd
        )
        if recovered_before_parallel:
            print(f"PRE_MULTIWORK_RECOVERY=PASS COUNT={recovered_before_parallel}", flush=True)

        heartbeat.check()
        if native_stop.requested(): raise KeyboardInterrupt()
        with core.FullSerialLockBoundary():
            lock = core.acquire_lock(dest_root)
        core._full_manifest(dest_root, all_keys)

        job = ProcessJob()
        publisher_proc = job.start(ctx, _publisher_main, kwargs=publisher_kwargs,
                                   name="TICKSTORE-RC4R2-PUBLISHER")
        try:
            ready=event_q.get(timeout=120.0)
        except queue.Empty as exc:
            raise MultiworkBlocked("PUBLISHER_READY_TIMEOUT") from exc
        if ready.get("type")=="PUBLISHER_ERROR":
            raise MultiworkBlocked("PUBLISHER_START_ERROR:"+str(ready.get("error")))
        if ready.get("type")!="PUBLISHER_READY":
            raise MultiworkBlocked("PUBLISHER_FIRST_EVENT_UNEXPECTED:"+str(ready.get("type")))
        publisher_state="IDLE"
        print("PUBLISHER_READY=YES",flush=True)

        heartbeat.update(phase='PIPELINE')
        fill_worker_slots()

        _print_progress(
            total_rows=total_rows,published_rows=published_rows,inflight_rows=inflight_rows,
            published_days=published_days,total_days=total_days,counts=counts,
            active_workers=len(active),worker_limit=workers,months_done=months_done,total_months=len(months),
            started=started,force=True,last_print_ref=last_print,worker_states=worker_states,
            worker_scan_bytes=worker_scan_bytes,completed_source_bytes=completed_source_bytes,
            total_source_bytes=total_source_bytes,
        )
        print(f"PIPELINE VERIFIED={months_verified} PUBLISH_BACKLOG={publish_backlog} PUBLISHER={publisher_state}",flush=True)

        while active or months_done < len(months):
            if native_stop.requested():
                raise KeyboardInterrupt()
            check_memory()
            fill_worker_slots()
            # Evaluate independently of queue activity; nonproductive chatter must
            # not defeat the watchdog by preventing the queue.Empty branch.
            if (active or publish_backlog) and time.perf_counter()-last_productive[0] > PRODUCTIVITY_STALL_SECONDS:
                raise MultiworkBlocked('PRODUCTIVITY_STALL_NO_PIPELINE_PROGRESS')
            try:
                msg=event_q.get(timeout=1.0)
            except queue.Empty:
                for wid,info in list(active.items()):
                    proc=info["process"]
                    if not proc.is_alive():
                        if proc.exitcode not in (None,0):
                            raise MultiworkBlocked(f"WORKER_EXITED_UNCLEAN:{wid}:exit={proc.exitcode}")
                        raise MultiworkBlocked(f"WORKER_EXITED_WITHOUT_TERMINAL_EVENT:{wid}:exit={proc.exitcode}")
                if not publisher_proc.is_alive() and months_done < len(months):
                    raise MultiworkBlocked("PUBLISHER_EXITED_BEFORE_FULL_COMPLETION")
                if (active or publish_backlog) and time.perf_counter()-last_productive[0] > PRODUCTIVITY_STALL_SECONDS:
                    raise MultiworkBlocked("PRODUCTIVITY_STALL_NO_PIPELINE_PROGRESS")
                _print_progress(
                    total_rows=total_rows,published_rows=published_rows,inflight_rows=inflight_rows,
                    published_days=published_days,total_days=total_days,counts=counts,
                    active_workers=len(active),worker_limit=workers,months_done=months_done,total_months=len(months),
                    started=started,last_print_ref=last_print,worker_states=worker_states,
                    worker_scan_bytes=worker_scan_bytes,completed_source_bytes=completed_source_bytes,
                    total_source_bytes=total_source_bytes,
                )
                print(f"PIPELINE VERIFIED={months_verified} PUBLISH_BACKLOG={publish_backlog} PUBLISHER={publisher_state}",flush=True)
                continue

            typ=msg.get("type")
            wid=msg.get("worker")
            productive_types={
                "OPENED","SCAN","GROUP","DAY_STAGED","MONTH_VERIFIED","MONTH_STOPPED",
                "PUBLISH_MONTH_START","PUBLISH_DAY","MONTH_PUBLISHED","PUBLISHER_STOPPED",
            }
            if typ in productive_types:
                last_productive[0]=time.perf_counter()

            if typ in ("PUBLISHER_READY","PUBLISH_MONTH_START","PUBLISH_DAY","MONTH_PUBLISHED","PUBLISHER_STOPPED","PUBLISHER_ERROR"):
                if typ=="PUBLISHER_ERROR":
                    raise MultiworkBlocked(
                        f"PUBLISHER_ERROR:{msg.get('error_type')}:{msg.get('error')}\n{msg.get('traceback')}"
                    )
                if typ=="PUBLISH_MONTH_START":
                    publisher_state="PUBLISHING:"+str(msg.get("month_id"))
                elif typ=="PUBLISH_DAY":
                    published_days=int(msg["published_days"])
                    published_rows=int(msg["published_rows"])
                    counts=dict(msg["counts"])
                elif typ=="MONTH_PUBLISHED":
                    published_days=int(msg["published_days"])
                    published_rows=int(msg["published_rows"])
                    counts=dict(msg["counts"])
                    months_done=int(msg["months_published"])
                    publish_backlog=max(0,publish_backlog-1)
                    fill_worker_slots()
                    publisher_state="IDLE"
                    month_id=str(msg["month_id"])
                    print(
                        f"MONTH_VERIFIED_AND_PUBLISHED month={month_id} MONTHS={months_done}/{len(months)} "
                        f"SHA256=PASS PUBLISH_BACKLOG={publish_backlog}",flush=True
                    )
                elif typ=="PUBLISHER_STOPPED":
                    publisher_state="STOPPED"
                _print_progress(
                    total_rows=total_rows,published_rows=published_rows,inflight_rows=inflight_rows,
                    published_days=published_days,total_days=total_days,counts=counts,
                    active_workers=len(active),worker_limit=workers,months_done=months_done,total_months=len(months),
                    started=started,last_print_ref=last_print,worker_states=worker_states,
                    worker_scan_bytes=worker_scan_bytes,completed_source_bytes=completed_source_bytes,
                    total_source_bytes=total_source_bytes,
                )
                if typ in ("MONTH_PUBLISHED","PUBLISH_MONTH_START"):
                    print(f"PIPELINE VERIFIED={months_verified} PUBLISH_BACKLOG={publish_backlog} PUBLISHER={publisher_state}",flush=True)
                continue

            if wid not in active and typ not in ("ERROR",):
                raise MultiworkBlocked("EVENT_FROM_UNKNOWN_WORKER:"+str(wid))
            info=active.get(wid)

            if typ=="OPENED":
                month_id=msg["month_id"]
                identity=dict(msg["identity"])
                if identity!=dict(info["identity"]):
                    raise MultiworkBlocked("WORKER_PRESTART_IDENTITY_MISMATCH:"+month_id)
                info["parent_pin"].verify()
                worker_states[wid]="SCANNING"
                print(
                    f"WORKER_OPENED worker={wid} month={month_id} BUILD_DAYS={len(info['build_keys'])} "
                    f"EXISTING_DAYS={len(info['existing_keys'])} PREHASH=NO START_PREQUEUED=YES",flush=True
                )

            elif typ=="STATE":
                worker_states[wid]=str(msg.get("state") or "SCANNING")

            elif typ=="SCAN":
                worker_scan_bytes[wid]=max(worker_scan_bytes.get(wid,0),int(msg.get("bytes_scanned",0)))
                if worker_states.get(wid)=="LAUNCHING": worker_states[wid]="SCANNING"
                _print_progress(
                    total_rows=total_rows,published_rows=published_rows,inflight_rows=inflight_rows,
                    published_days=published_days,total_days=total_days,counts=counts,
                    active_workers=len(active),worker_limit=workers,months_done=months_done,total_months=len(months),
                    started=started,last_print_ref=last_print,worker_states=worker_states,
                    worker_scan_bytes=worker_scan_bytes,completed_source_bytes=completed_source_bytes,
                    total_source_bytes=total_source_bytes,
                )

            elif typ=="GROUP":
                inflight_rows[wid]=int(msg["rows"])
                worker_states[wid]="BUILDING"
                if "source_pos" in msg:
                    worker_scan_bytes[wid]=max(worker_scan_bytes.get(wid,0),int(msg["source_pos"]))
                _print_progress(
                    total_rows=total_rows,published_rows=published_rows,inflight_rows=inflight_rows,
                    published_days=published_days,total_days=total_days,counts=counts,
                    active_workers=len(active),worker_limit=workers,months_done=months_done,total_months=len(months),
                    started=started,last_print_ref=last_print,worker_states=worker_states,
                    worker_scan_bytes=worker_scan_bytes,completed_source_bytes=completed_source_bytes,
                    total_source_bytes=total_source_bytes,
                )

            elif typ=="DAY_STAGED":
                worker_states[wid]="SCANNING"
                inflight_rows[wid]=int(msg.get("month_rows_done",0))
                worker_scan_bytes[wid]=max(worker_scan_bytes.get(wid,0),int(msg.get("bytes_scanned",0)))

            elif typ=="MONTH_VERIFIED":
                month_id=msg["month_id"]
                expected_sha=str(months[month_id]["source_sha256"]).upper()
                actual_sha=str(msg.get("actual_sha256","")).upper()
                if actual_sha!=expected_sha:
                    raise MultiworkBlocked("WORKER_MONTH_SHA_EVENT_MISMATCH:"+month_id)
                if dict(msg.get("identity") or {})!=dict(info["identity"] or {}):
                    raise MultiworkBlocked("WORKER_MONTH_IDENTITY_CHANGED:"+month_id)
                proc=info["process"]
                proc.join(timeout=30)
                if proc.is_alive(): raise MultiworkBlocked("WORKER_DID_NOT_EXIT_AFTER_MONTH_VERIFIED:"+wid)
                if proc.exitcode!=0: raise MultiworkBlocked(f"WORKER_MONTH_EXIT_NONZERO:{wid}:{proc.exitcode}")

                parent_pin=info["parent_pin"]
                parent_pin.verify()
                identities[month_id]=dict(info["identity"])
                sealed_pins[month_id]=parent_pin
                info["parent_pin"]=None
                build_keys=set(info["build_keys"] or [])
                existing_keys=set(info["existing_keys"] or [])
                staged=list(msg.get("staged") or [])
                staged_keys=[str(x.get("date_key")) for x in staged]
                if len(staged_keys)!=len(set(staged_keys)) or set(staged_keys)!=build_keys:
                    raise MultiworkBlocked("STAGED_DAY_SET_MISMATCH:"+month_id)

                completed_source_bytes += int(months[month_id]["source_size"])
                months_verified += 1
                active.pop(wid)
                worker_states.pop(wid,None)
                worker_scan_bytes.pop(wid,None)
                inflight_rows.pop(wid,None)

                verified_outbox[month_id] = {
                    "type":"PUBLISH_MONTH","month_id":month_id,
                    "identity":dict(identities[month_id]),
                    "build_keys":sorted(build_keys),"existing_keys":sorted(existing_keys),
                    "staged":staged,
                }
                publish_backlog += 1
                # Parallel scan completion cannot reorder canonical commits.
                while next_publish_month < len(month_ids) and month_ids[next_publish_month] in verified_outbox:
                    publish_q.put(verified_outbox.pop(month_ids[next_publish_month]))
                    next_publish_month += 1
                fill_worker_slots()
                print(
                    f"MONTH_VERIFIED_QUEUED month={month_id} VERIFIED={months_verified}/{len(months)} "
                    f"PUBLISH_BACKLOG={publish_backlog} ACTIVE_WORKERS={len(active)}/{workers}",flush=True
                )

            elif typ=="MONTH_STOPPED":
                proc=info["process"]
                proc.join(timeout=30.0)
                if proc.is_alive():
                    raise MultiworkBlocked("WORKER_STOP_DID_NOT_EXIT:"+wid)
                if proc.exitcode not in (0,None):
                    raise MultiworkBlocked(f"WORKER_STOP_EXIT_NONZERO:{wid}:{proc.exitcode}")
                if info.get("parent_pin") is not None:
                    info["parent_pin"].verify();info["parent_pin"].close();info["parent_pin"]=None
                active.pop(wid);worker_states.pop(wid,None);worker_scan_bytes.pop(wid,None);inflight_rows.pop(wid,None)

            elif typ=="ERROR":
                raise MultiworkBlocked(
                    f"WORKER_ERROR:{msg.get('worker')}:{msg.get('month_id')}:"
                    f"{msg.get('error_type')}:{msg.get('error')}\n{msg.get('traceback')}"
                )
            else:
                raise MultiworkBlocked("UNKNOWN_WORKER_EVENT:"+str(typ))

        if stop_event.is_set(): raise KeyboardInterrupt()
        if published_days!=total_days:
            raise MultiworkBlocked(f"PUBLISHED_DAY_COUNT_MISMATCH:{published_days}:{total_days}")
        if months_verified!=len(months) or months_done!=len(months):
            raise MultiworkBlocked(f"MONTH_PIPELINE_COUNT_MISMATCH:{months_verified}:{months_done}:{len(months)}")
        if set(identities)!=set(months) or set(sealed_pins)!=set(months):
            raise MultiworkBlocked("VERIFIED_SOURCE_MONTH_SET_MISMATCH")
        for month_id in sorted(sealed_pins): sealed_pins[month_id].verify()

        publish_q.put({"type":"STOP"})
        publisher_proc.join(timeout=30.0)
        if publisher_proc.is_alive():
            raise MultiworkBlocked("PUBLISHER_DID_NOT_EXIT_AFTER_STOP")
        if publisher_proc.exitcode!=0:
            raise MultiworkBlocked("PUBLISHER_EXIT_NONZERO:"+str(publisher_proc.exitcode))

        heartbeat.update(phase='FINAL_RECONCILIATION', committed_rows=published_rows, committed_days=published_days)
        print("FINAL_READONLY_RECONCILE=START",flush=True)
        core.reconcile_full_readonly(dest_root,days,months,ledger_sha,ids,cert,identities,zstd)
        heartbeat.check()
        if native_stop.requested(): raise KeyboardInterrupt()
        manifest_raw = core.secure_read_all(core.manifest_path(dest_root))
        reconciliation = dict(schema='TICKSTORE_MULTIWORK_RECONCILIATION_V001', status='PASS',
            run_id=admission.instance['run_id'], instance_sha256=admission.descriptor['instance_sha256'],
            code_manifest_sha256=admission.descriptor['code_manifest_sha256'],
            days=total_days, rows=total_rows, manifest_sha256=__import__('hashlib').sha256(manifest_raw).hexdigest().upper(),
            source_months=months_verified, source_identities=identities, ledger_sha256=ledger_sha,
            created_unix_ns=time.time_ns())
        print("FINAL_READONLY_RECONCILE=PASS",flush=True)

        with core.FullSerialLockBoundary():
            core.release_lock(lock);lock=None
        for month_id in sorted(sealed_pins): sealed_pins[month_id].verify()
        while sealed_pins:
            _,pin=sealed_pins.popitem();pin.close()
        print("FULL_SOURCE_CONTINUOUS_PIN_SEAL=PASS",flush=True)

    except KeyboardInterrupt:
        primary_error=sys.exc_info()
        safe_stop_report=stop_and_join_all("SAFE_STOP")
        print(f"SAFE_STOP_FORCED_TERMINATE={len(safe_stop_report['forced_terminate'])}",flush=True)
        print(f"SAFE_STOP_FORCED_KILL={len(safe_stop_report['forced_kill'])}",flush=True)
        if not _cooperative_stop_confirmed(safe_stop_report):
            primary_error=(MultiworkBlocked, MultiworkBlocked("SAFE_STOP_NOT_COOPERATIVE_RECONCILIATION_REQUIRED"), None)
    except BaseException:
        primary_error=sys.exc_info()
        stop_and_join_all("ERROR_STOP")
    finally:
        primary_error = _finalize_coordinator_resources(
            active, sealed_pins, publisher_proc, lock, lease, primary_error)
        if native_stop is not None:
            try:
                native_stop.close()
            except BaseException as exc:
                if primary_error is None:
                    primary_error = (type(exc), exc, exc.__traceback__)
        if job is not None:
            try:
                job.close()
            except BaseException as exc:
                if primary_error is None:
                    primary_error = (type(exc), exc, exc.__traceback__)

    if heartbeat is not None:
        try:
            heartbeat.update(phase='ENGINE_RECONCILED' if primary_error is None else 'STOPPED',
                             committed_rows=published_rows, committed_days=published_days)
            heartbeat.close('ENGINE_PASS_PENDING_POSTFULL' if primary_error is None else
                            'SAFE_STOP' if isinstance(primary_error[1], KeyboardInterrupt) and _cooperative_stop_confirmed(safe_stop_report) else 'FAILED')
        except BaseException as exc:
            primary_error = (type(exc), exc, exc.__traceback__)
    if primary_error is not None:
        _,exc,tb=primary_error
        if isinstance(exc, KeyboardInterrupt) and _cooperative_stop_confirmed(safe_stop_report):
            print("SAFE_STOP_PROCESS_TREE=PASS",flush=True)
            print("SAFE_STOP=YES",flush=True)
            print("SAFE_STOP_GRANULARITY=ROW_GROUP_OR_SCAN_CHUNK_OR_PUBLISH_DAY",flush=True)
            print("RESUME=YES",flush=True)
        _print_progress(
            total_rows=total_rows,published_rows=published_rows,inflight_rows=inflight_rows,
            published_days=published_days,total_days=total_days,counts=counts,
            active_workers=0,worker_limit=workers,months_done=months_done,total_months=len(months),
            started=started,force=True,last_print_ref=last_print,worker_states={},worker_scan_bytes={},
            completed_source_bytes=completed_source_bytes,total_source_bytes=total_source_bytes,
        )
        if isinstance(exc, KeyboardInterrupt) and _cooperative_stop_confirmed(safe_stop_report):
            raise CooperativeSafeStop('MULTIWORK_COOPERATIVE_STOP') from exc
        raise exc.with_traceback(tb)

    _print_progress(
        total_rows=total_rows,published_rows=published_rows,inflight_rows={},published_days=published_days,
        total_days=total_days,counts=counts,active_workers=0,worker_limit=workers,months_done=len(months),
        total_months=len(months),started=started,force=True,last_print_ref=last_print,worker_states={},
        worker_scan_bytes={},completed_source_bytes=total_source_bytes,total_source_bytes=total_source_bytes,
        final_reconciled=True,
    )
    if completion is not None:
        completion(reconciliation)
    print("TICKSTORE_FULL_MULTIWORK_STATUS=PASS",flush=True)
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--dest-root", required=True)
    ap.add_argument("--scratch-root", required=True)
    ap.add_argument("--ledger-zip", required=True)
    ap.add_argument("--chain-file", required=True)
    ap.add_argument("--chain-sha256", required=True)
    ap.add_argument("--b06-sha256", required=True)
    ap.add_argument("--workers", default="AUTO")
    ap.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    ap.add_argument("--ram-target-percent", type=int, default=DEFAULT_RAM_TARGET_PERCENT)
    args = ap.parse_args()

    return execute_multiwork(
        Path(args.source_root), Path(args.dest_root), Path(args.scratch_root), Path(args.ledger_zip),
        workers_requested=args.workers, max_workers=args.max_workers,
        ram_target_percent=args.ram_target_percent,
        chain_file=Path(args.chain_file), chain_sha256=args.chain_sha256,
        b06_sha256=args.b06_sha256,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        # execute_multiwork emits YES only after a verified process-tree shutdown.
        print("INTERRUPTED=YES", flush=True)
        raise SystemExit(130)
    except Exception as exc:
        print("TICKSTORE_FULL_MULTIWORK_STATUS=BLOCKED", flush=True)
        print("REASON=" + str(exc), flush=True)
        raise SystemExit(2)
