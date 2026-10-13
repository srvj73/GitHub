"""Read-only reconciliation of supplied, hash-bound Windows observations.

This is an implementer diagnosis, never admission, retirement authority, or a
replacement FINISHED journal event. Native observations must be refreshed at
any future admission boundary; this tool neither dispatches nor changes STATE.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path


def reconcile(observed, system, roots):
    errors = []
    def need(ok, label):
        if not ok:
            errors.append(label)
    need(observed.get("schema") == "TICKSTORE_D4_PREDECESSOR_OBSERVATION_V001", "OBSERVATION_SCHEMA")
    need(system.get("schema") == "TICKSTORE_D4_PREDECESSOR_SYSTEM_OBSERVATION_V001", "SYSTEM_SCHEMA")
    need(roots.get("schema") == "TICKSTORE_D4_ROOTS_EVIDENCE_V001", "ROOTS_SCHEMA")
    need(observed.get("read_only") is True and observed.get("inputs_unchanged") is True, "OBSERVATION_STABILITY")
    need(observed.get("bundle_binding_verified") is True, "BUNDLE_IDENTITY_NOT_BOUND")
    need(observed.get("journal_chain_intact") is True and roots.get("journal", {}).get("chain_intact") is True, "JOURNAL_CHAIN")
    for name in ("state", "journal"):
        s = observed.get(name, {}).get("sha256")
        need(isinstance(s, str) and len(s) == 64 and s == roots.get(name, {}).get("sha256"), name.upper() + "_OBSERVATIONS_DIFFER")
    entries = observed.get("d4_entries", [])
    last = entries[-1] if entries else {}
    need(last.get("phase") == "STARTED" and last.get("run_id") == observed.get("run") and bool(observed.get("run")), "PREDECESSOR_NOT_IDENTIFIED")
    need(roots.get("journal", {}).get("last", {}).get("run_id") == observed.get("run"), "ROOTS_PREDECESSOR_DIFFERENT")
    try:
        started = datetime.datetime.fromisoformat(last["ts"])
        boot = datetime.datetime.fromisoformat(system["last_boot_utc"].replace("Z", "+00:00"))
        sampled = datetime.datetime.fromisoformat(system["observed_utc"].replace("Z", "+00:00"))
        need(started < boot <= sampled, "LATER_BOOT_NOT_PROVEN")
    except (KeyError, TypeError, ValueError):
        need(False, "LATER_BOOT_NOT_PROVEN")
    need(system.get("admin") is True and isinstance(system.get("processes"), list), "NATIVE_CENSUS_NOT_QUALIFIED")
    for p in system.get("processes", []):
        need(p.get("command_available") is True, "PROCESS_IDENTITY_INCOMPLETE")
        need(p.get("tickstore_marker") is False, "RECOVERY_PROCESS_OBSERVED")
        if not p.get("is_observer"):
            need(Path(p.get("exe") or "").name.lower() not in ("python.exe", "pythonw.exe"), "UNCLASSIFIED_PYTHON_PROCESS")
    lease = observed.get("mutex", {})
    need(lease.get("operation") == "OpenMutexW_ONLY" and lease.get("present") is False and lease.get("error") == 2,
         "LEASE_ABSENCE_NOT_PROVEN")
    bound = observed.get("roots", {})
    need(set(bound) == {"dest_root", "scratch_root", "recovery_root"}, "ROOT_SET")
    for v in bound.values():
        old, actual = v.get("historical", {}), v.get("actual", {})
        need(v.get("same_identity") is True and actual.get("volume") == old.get("volume")
             and actual.get("file_id") == old.get("file_id") and bool(actual.get("file_id")), "ROOT_IDENTITY")
    locks = observed.get("locks", [])
    need(len(locks) == 3 and all(v.get("present") is False for v in locks), "WRITER_LOCK_ABSENCE_NOT_PROVEN")
    need(observed.get("gate_mode") == "CERTIFY_SCRATCH", "PREDECESSOR_EFFECT_SCOPE")
    need(observed.get("recovery_entries") == [] and roots.get("recovery_root", {}).get("entries") == 0, "RECOVERY_OUTPUT_PRESENT_OR_UNKNOWN")
    fingerprint = roots.get("scope_fingerprint", {})
    need(fingerprint.get("unchanged") is True and fingerprint.get("before") == fingerprint.get("after")
         and bool(fingerprint.get("before")), "ROOT_SCOPE_STABILITY")
    need(roots.get("classification") == "FIRST_ADMISSION_NO_CHECKPOINT"
         and roots.get("absence_claims_limited_to_scope") is True, "FIRST_ADMISSION_SCOPE_NOT_PROVEN")
    return {
        "schema": "TICKSTORE_D4_PREDECESSOR_RECONCILIATION_V001",
        "role": "IMPLEMENTER_DIAGNOSTIC_ONLY",
        "classification": "BLOCKED_INSUFFICIENT_PROOF" if errors else "PREDECESSOR_TERMINATED_COMPLETION_UNPROVEN",
        "run_id": observed.get("run"), "reasons": sorted(set(errors)),
        "predecessor_runtime_survival_excluded": not errors,
        "journal_finished_proven": False,
        "journal_mutation_performed": False,
        "checkpoint_absence_global": False,
        "checkpoint_absence_scope": roots.get("scope", []),
        "first_admission_executed": False,
        "production_authorized": False,
        "B06_independent_pass": False,
        "next_boundary": "New admission must retain the original STARTED history and bind a distinct run; no resume identity is fabricated. Current physical preconditions, final-code independent B06 and B07 remain required.",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for n in ("observation", "system", "roots"):
        ap.add_argument("--" + n, required=True)
    args = ap.parse_args(argv)
    objects = []
    inputs = {}
    for n in ("observation", "system", "roots"):
        p = Path(getattr(args, n)); raw = p.read_bytes()
        objects.append(json.loads(raw.decode("utf-8-sig")))
        inputs[n] = {"path": str(p), "sha256": hashlib.sha256(raw).hexdigest().upper()}
    out = reconcile(*objects); out["input_files"] = inputs
    print(json.dumps(out, indent=2, sort_keys=True))
    return 2 if out["reasons"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
