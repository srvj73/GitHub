"""PEGASUS FULL V006: bounded, deployment-pinned QS4 SAFE_STOP adapter.

This module must be integrated at the real QS4 orchestrator boundary after physical
parent identification. It does not start QS4, modify G4, or release a full run.
A child-side STOP_OBSERVED can become SAFE_STOP_CONFIRMED only with independent
supervisor evidence: drained Job, complete output and release readback.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

SCHEMA_BINDING = "PEGASUS_FULL_V006_STOP_BINDING"
SCHEMA_REQUEST = "PEGASUS_FULL_V005_STOP_REQUEST"
SCHEMA_OBSERVED = "PEGASUS_FULL_V006_STOP_OBSERVED"
BLOCK_TAG = "V006_SAFE_STOP_AT_DURABLE_BOUNDARY"

class BridgeBlocked(RuntimeError):
    pass


def sha(path: Path) -> str:
    with path.open("rb") as f:
        h = hashlib.sha256()
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise BridgeBlocked("SOURCE_ABSENT_OR_REPARSE:" + path.name)
    data = path.read_bytes()
    if len(data) > 1024 * 1024:
        raise BridgeBlocked("OVERSIZED_JSON")
    obj = json.loads(data.decode("utf-8-sig"))
    if not isinstance(obj, dict):
        raise BridgeBlocked("OBJECT_REQUIRED")
    return obj


def atomic_write_new(path: Path, value: dict) -> str:
    if path.exists() or path.is_symlink():
        raise BridgeBlocked("IMMUTABLE_TARGET_EXISTS")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise BridgeBlocked("OUTPUT_PARENT_INVALID")
    blob = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    pending = path.with_name(path.name + ".pending." + os.urandom(12).hex())
    try:
        with pending.open("xb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        # For productive use, an owner-scoped exclusive lock protects this rename.
        if path.exists():
            raise BridgeBlocked("IMMUTABLE_RACE")
        os.rename(pending, path)
    finally:
        if pending.exists():
            pending.unlink()
    return sha(path)


def verify_source_contract(qs4_source: Path, sealed_sha: str) -> dict:
    """Verify original source and its hook surface, without importing or running it."""
    import ast
    if not isinstance(sealed_sha, str) or len(sealed_sha) != 64:
        raise BridgeBlocked("SOURCE_PIN_REQUIRED")
    if sha(qs4_source) != sealed_sha.upper():
        raise BridgeBlocked("QS4_SOURCE_SHA_MISMATCH")
    parsed = ast.parse(qs4_source.read_text("utf-8-sig"), filename=qs4_source.name)
    c = next((x for x in parsed.body if isinstance(x, ast.ClassDef) and x.name == "Orchestrator"), None)
    if c is None:
        raise BridgeBlocked("QS4_ORCHESTRATOR_ABSENT")
    names = {x.name for x in c.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))}
    mandatory = {"run", "run_case", "run_step", "commit_step", "save", "reconcile_resume", "finish"}
    if not mandatory <= names:
        raise BridgeBlocked("QS4_DURABLE_HOOKS_NOT_COMPATIBLE")
    return {"source_sha256": sealed_sha.upper(), "hooks": sorted(mandatory), "source_bytes": qs4_source.stat().st_size}


class DurableStopAdapter:
    """Hook run_case + run_step *before* admitting a new case or atomic step."""
    def __init__(self, evidence_root: Path, attempt_id: str, original_source_sha: str,
                 session_id: str, logical_id: str):
        self.evidence_root = evidence_root
        self.attempt_id = attempt_id
        self.source_sha = original_source_sha.upper()
        self.session_id = session_id
        self.logical_id = logical_id
        self.observed = False
        self.observed_sha = None
        self._patched_class = None
        self._originals = None
        if (not evidence_root.is_dir() or evidence_root.is_symlink()
                or len(attempt_id) != 32 or any(x not in "0123456789abcdef" for x in attempt_id)):
            raise BridgeBlocked("STOP_EVIDENCE_ROOT_ATTEMPT_INVALID")

    def _check(self, instance: Any) -> None:
        request_path = self.evidence_root / "STOP_REQUEST.json"
        if not request_path.exists():
            return
        if self.observed:
            raise BridgeBlocked("DUPLICATE_SAFE_STOP_OBSERVATION")
        bind_path = self.evidence_root / "STOP_BINDING.json"
        request = load_json(request_path)
        binding = load_json(bind_path)
        if (binding.get("schema") != SCHEMA_BINDING
            or binding.get("attempt_id") != self.attempt_id
            or binding.get("session_id") != self.session_id
            or binding.get("logical_id") != self.logical_id
            or binding.get("source_sha256") != self.source_sha):
            raise BridgeBlocked("STOP_BINDING_INVALID")
        if (request.get("schema") != SCHEMA_REQUEST
            or request.get("attempt_id") != self.attempt_id
            or request.get("checkpoint_sha256") != binding.get("outer_checkpoint_sha256")):
            raise BridgeBlocked("STOP_REQUEST_BOUNDARY_MISMATCH")
        if (getattr(instance, "session", None) != self.session_id
            or getattr(instance, "logical", None) != self.logical_id):
            raise BridgeBlocked("QS4_SESSION_IDENTITY_MISMATCH")
        if instance.active_child is not None:
            if instance.active_child.poll() is None:
                raise BridgeBlocked("QS4_ACTIVE_CHILD_STOP_NOT_ATOMIC")
            raise BridgeBlocked("QS4_CHILD_OBJECT_NOT_CLEARED")
        if not isinstance(instance.led, dict) or instance.led.get("partial") is not None:
            raise BridgeBlocked("QS4_PARTIAL_TRANSACTION_ON_STOP")
        ledger = Path(instance.ledger_p)
        journal = Path(instance.journal_p)
        original_sha = sha(ledger)
        original_journal_sha = sha(journal)
        # Native harness supplies the authoritative durable ledger verifier.
        verified = instance.L.ledger_verify(ledger, journal)
        if not isinstance(verified, dict) or verified.get("partial") is not None:
            raise BridgeBlocked("QS4_DURABLE_LEDGER_PARTIAL")
        if sha(ledger) != original_sha or sha(journal) != original_journal_sha:
            raise BridgeBlocked("QS4_LEDGER_CHANGED_DURING_STOP_CHECK")
        # No new unit admitted once request is observed. This is an observation,
        # not proof the supervisor Job has drained or W04 remained continuously held.
        doc = {
            "schema": SCHEMA_OBSERVED,
            "attempt_id": self.attempt_id,
            "session_id": self.session_id,
            "logical_id": self.logical_id,
            "source_sha256": self.source_sha,
            "request_sha256": sha(request_path),
            "outer_checkpoint_sha256": request["checkpoint_sha256"],
            "qs4_ledger_sha256": original_sha,
            "qs4_journal_sha256": original_journal_sha,
            "active_child": "NO",
            "partial": "NO",
            "boundary": "BETWEEN_DURABLE_QS4_ATOMIC_UNITS",
            "job_drained": "NOT_ATTESTED_BY_CHILD",
            "safe_stop_confirmed": "NO",
        }
        self.observed_sha = atomic_write_new(self.evidence_root / "STOP_OBSERVED.json", doc)
        self.observed = True
        # QS4 records a fail-closed stop in its own finish() and no new step starts.
        raise instance.L.HarnessBlocked(BLOCK_TAG, self.observed_sha)

    def install(self, orchestrator_cls: type) -> None:
        if self._patched_class is not None:
            raise BridgeBlocked("BRIDGE_ALREADY_INSTALLED")
        previous_run_case = orchestrator_cls.run_case
        previous_run_step = orchestrator_cls.run_step
        bridge = self
        def safe_run_case(instance, *args, **kwargs):
            bridge._check(instance)
            return previous_run_case(instance, *args, **kwargs)
        def safe_run_step(instance, *args, **kwargs):
            bridge._check(instance)
            return previous_run_step(instance, *args, **kwargs)
        orchestrator_cls.run_case = safe_run_case
        orchestrator_cls.run_step = safe_run_step
        self._patched_class = orchestrator_cls
        self._originals = (previous_run_case, previous_run_step)

    def uninstall(self) -> None:
        if self._patched_class is not None:
            self._patched_class.run_case, self._patched_class.run_step = self._originals
        self._patched_class = None
        self._originals = None


def inspect_supervisor_confirmation(*, evidence_root: Path,
                                    expected_observed_sha: str,
                                    child_pid: int, child_created_filetime: int,
                                    native_job_active: int,
                                    capture_complete: bool,
                                    existing_file_guard_readback: bool,
                                    w04_full_coverage_attested: bool) -> dict:
    """Strictly evaluate evidence supplied by an *external*, same-attempt supervisor.

    These arguments are NOT a self-asserted certificate. Caller must bind to
    physically observed native job/handle identity and record independent proofs.
    """
    observed = load_json(evidence_root / "STOP_OBSERVED.json")
    if sha(evidence_root / "STOP_OBSERVED.json") != expected_observed_sha.upper():
        raise BridgeBlocked("STOP_OBSERVED_SHA_MISMATCH")
    if observed.get("schema") != SCHEMA_OBSERVED or observed.get("safe_stop_confirmed") != "NO":
        raise BridgeBlocked("STOP_OBSERVED_SCHEMA")
    if child_pid <= 0 or child_created_filetime <= 0:
        raise BridgeBlocked("CHILD_PID_CREATION_TIME_UNATTESTED")
    if native_job_active != 0 or not capture_complete or not existing_file_guard_readback:
        raise BridgeBlocked("SAFE_STOP_NATIVE_CUSTODY_NOT_DRAINED")
    if not w04_full_coverage_attested:
        raise BridgeBlocked("SAFE_STOP_W04_FULL_COVERAGE_NOT_ATTESTED")
    return {"eligible_for_independent_review": True,
            "safe_stop_confirmed": "NOT_AUTOMATICALLY_GRANTED",
            "binding": (child_pid, child_created_filetime),
            "request_sha256": observed["request_sha256"],
            "qs4_ledger_sha256": observed["qs4_ledger_sha256"]}


def _main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--verify-source", required=True)
    p.add_argument("--sha256", required=True)
    args = p.parse_args()
    r = verify_source_contract(Path(args.verify_source), args.sha256)
    print(json.dumps({"result": "PASS_SOURCE_HOOK_COMPATIBILITY_ONLY", **r}, sort_keys=True))

if __name__ == "__main__":
    _main()
