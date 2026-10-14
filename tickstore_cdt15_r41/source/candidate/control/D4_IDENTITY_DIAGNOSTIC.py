"""TICKSTORE B06R3 - read-only diagnostic of the D4 resume identity (policy rev. 37, option B).

Evaluates, with the SAME function the D4 entry uses before dispatch
(evaluate_resume_identity), whether the historical anchor, RUN_AUTHORITY, run_id,
signed checkpoint, STATE and VSS generation belong to one execution. It never
writes outside --out, never constructs State, never loads the orchestrator and
never dispatches. The run key (if supplied by the caller through
TICKSTORE_D4_RUN_HMAC_KEY_HEX) is used only to verify the checkpoint HMAC.

Usage: python -B -I D4_IDENTITY_DIAGNOSTIC.py --run-authority <RUN_AUTHORITY.json> --state <STATE.json>
         --config <STAGE_A_SEALED_VALUES_V001.json> --release <tickstore_publisher_recovery_v004_release.py>
         --binding <RUNTIME_LOCATOR_ADAPTER_BINDING.json> [--locator-receipt <receipt.json>]
         [--adapter-dir <adapter dir>] --out <report.json>
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def load_entry(adapter_dir):
    p = Path(adapter_dir) / "runtime_locator_orchestrator_entry.py"
    spec = importlib.util.spec_from_file_location("tickstore_identity_diagnostic_entry", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, sha(p.read_bytes())


def facts_of(path):
    if not path:
        return {"path": None, "present": False}
    p = Path(path)
    if not p.is_file():
        return {"path": str(p), "present": False}
    raw = p.read_bytes()
    return {"path": str(p), "present": True, "sha256": sha(raw), "bytes": len(raw)}


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for name in ("--run-authority", "--state", "--config", "--release", "--binding", "--out"):
        ap.add_argument(name, required=True)
    ap.add_argument("--locator-receipt")
    ap.add_argument("--adapter-dir", default=str(Path(__file__).resolve().parent.parent / "adapter"))
    a = ap.parse_args(argv)
    E, entry_sha = load_entry(a.adapter_dir)
    rep = {"schema": "TICKSTORE_D4_IDENTITY_DIAGNOSTIC_V001", "read_only": True, "entry_sha256": entry_sha,
           "inputs": {k: facts_of(v) for k, v in (("run_authority", a.run_authority), ("state", a.state),
                                                   ("config", a.config), ("release", a.release),
                                                   ("binding", a.binding), ("locator_receipt", a.locator_receipt or ""))}}
    out = Path(a.out)
    if not Path(a.run_authority).exists():
        # B06R4: absence at ONE path is not a global proof; scope-wide evidence comes from D4_ROOTS_EVIDENCE.
        rep["verdict"] = "RUN_AUTHORITY_ABSENT_AT_GIVEN_PATH_SCOPE_LIMITED"
        rep["scope_note"] = "absence verified only at --run-authority; run D4_ROOTS_EVIDENCE for the effective roots"
        out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(rep["verdict"]); return 0
    ra_raw = Path(a.run_authority).read_bytes(); ra = json.loads(ra_raw.decode("ascii"))
    anchor_path = Path(str(ra.get("owner_gate_path", "")))
    rep["run_authority"] = {k: ra.get(k) for k in ("run_id", "successor_release_sha256", "owner_gate_sha256",
                                                    "owner_gate_path", "config_sha256", "resume_root", "generation")}
    rep["anchor"] = facts_of(anchor_path)
    if not anchor_path.exists():
        rep["verdict"] = "BLOCKED_ANCHOR_FILE_MISSING"
        out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(rep["verdict"]); return 1
    identity = E.RunIdentity(ra, ra_raw, anchor_path.read_bytes())
    anchor = identity.anchor
    rep["anchor"].update({k: anchor.get(k) for k in ("schema", "mode", "recovery_source_sha256", "release_id",
                                                     "admission_generation")})
    config_raw = Path(a.config).read_bytes()
    state_raw = Path(a.state).read_bytes() if Path(a.state).exists() else None
    admitted = E.AdmittedStart(state_path=Path(a.state), control_root=Path(a.state).parent.parent,
                               config_path=Path(a.config), config_raw=config_raw, config_sha256=sha(config_raw),
                               state_raw=state_raw)
    binding = json.loads(Path(a.binding).read_bytes().decode("utf-8"))
    receipt = json.loads(Path(a.locator_receipt).read_bytes().decode("utf-8-sig")) if a.locator_receipt else {}
    sd = Path(a.state).parent
    if sd.is_dir():
        rep["state_dir_cas_debris"] = sorted(n for n in os.listdir(sd) if n.startswith("STATE.json.cas-"))
        rec_path = Path(__file__).resolve().parent / "STATE_CAS_RECOVERY.py"
        spec = importlib.util.spec_from_file_location("tickstore_identity_diagnostic_recovery", rec_path)
        rec = importlib.util.module_from_spec(spec); spec.loader.exec_module(rec)
        rep["journal"] = rec.journal_chain(sd / "STATE_JOURNAL.jsonl")
    if state_raw is not None:
        st = json.loads(state_raw.decode("utf-8"))
        rep["state"] = {k: st.get(k) for k in ("next_node", "status", "completed", "G_CA")}
        rep["state"]["canary_scratch_cert_present"] = st.get("canary_scratch_cert") is not None
    key_hex = os.environ.get("TICKSTORE_D4_RUN_HMAC_KEY_HEX", "")
    rep["run_key_supplied"] = bool(key_hex)
    report = E.evaluate_resume_identity(identity, binding, admitted, receipt, Path(a.release).read_bytes(), key_hex)
    rep["checks"] = [{"label": l, "ok": ok, "detail": d} for l, ok, d in report]
    not_evaluable = set()
    if not a.locator_receipt:
        not_evaluable |= {"ANCHOR_IS_BOUND_IDENTITY", "GENERATION_LOCATOR_STABLE_IDENTITY"}
    if not key_hex:
        not_evaluable |= {"RUN_KEY_EQUALS_RUN_AUTHORITY", "CHECKPOINT_SIGNATURE_RUN_KEY"}
    failed = [c["label"] for c in rep["checks"] if not c["ok"] and c["label"] not in not_evaluable]
    rep["not_evaluable_without_input"] = sorted(not_evaluable)
    rep["failed"] = failed
    cp = Path(str(ra.get("resume_root", ""))) / "CHECKPOINT.json"
    rep["checkpoint"] = facts_of(cp)
    if cp.exists():
        try:
            p = json.loads(cp.read_bytes().decode("ascii")).get("payload") or {}
            rep["checkpoint"].update({k: p.get(k) for k in ("status", "committed_count", "last_committed", "run_id",
                                                            "owner_gate_sha256", "successor_release_sha256")})
        except ValueError:
            rep["checkpoint"]["parse"] = "FAILED"
    chunks = Path(str(ra.get("resume_root", ""))) / "chunks"
    rep["chunks_count"] = len([x for x in chunks.iterdir() if x.is_file()]) if chunks.is_dir() else 0
    rep["verdict"] = "IDENTITY_RECONCILED" if not failed and not not_evaluable else (
        "IDENTITY_NOT_RECONCILED_BLOCK_RESUME" if failed else "PARTIALLY_EVALUATED_SUPPLY_MISSING_INPUTS")
    out.write_text(json.dumps(rep, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(rep["verdict"] + (" FAILED=" + ",".join(failed) if failed else ""))
    return 0 if rep["verdict"] == "IDENTITY_RECONCILED" else 1


if __name__ == "__main__":
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log("D4_IDENTITY_DIAGNOSTIC", main))
