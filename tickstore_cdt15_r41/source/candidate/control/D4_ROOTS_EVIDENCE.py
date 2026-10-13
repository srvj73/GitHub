"""TICKSTORE B06R4 - read-only evidence of the EFFECTIVE D4 roots and classification of the execution.

Why these roots (derived from code, not from a disk-wide search):
  * RUN_AUTHORITY_V005 has exactly one producer, the effectful wrapper (all versions 21F73B16,
    4FE9480C, 33A21925): it writes only <ResumeRoot>\\authority\\RUN_AUTHORITY.json and never deletes it.
  * The signed checkpoint is written by the frozen engine at RUN_AUTHORITY.resume_root, which the
    wrapper sets to <ResumeRoot>\\checkpoint; the engine refuses to run without RUN_AUTHORITY.
  * Immutable D4 receipts (d4_resume_prepared.<run_id>.<date>.json) live in the gate's recovery root,
    i.e. STATE.canary.recovery; orchestrator run logs live in <ControlRoot>\\runs.
  * The historical anchor and other admission receipts live under the promotion-prep receipts folder.
Absence is therefore claimed ONLY for the enumerated scope, which is reported in full.

Never writes outside --out, never constructs State, never loads the orchestrator or engine,
never reads key material (protected_key_b64 is reported only as present/absent).

Usage: python -B -I D4_ROOTS_EVIDENCE.py --resume-root <...> --control-root <...>
          [--receipts-root <...>] [--extra-root <...> ...] --out <report.json>
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

SCHEMAS = {
    "TICKSTORE_D4_RUN_AUTHORITY_V005": "run_authority",
    "TICKSTORE_D4_SIGNED_CHECKPOINT_V003": "checkpoint",
    "TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT_V001": "gca_locator_receipt",
    "TICKSTORE_G_CA_RECOVERY_RECEIPT_V001": "gca_recovery_receipt",
    "RECOVERY_OWNER_GATE_V004": "owner_gate",
    "TICKSTORE_D4_RESUME_EFFECTFUL_V002R22_CHILD_RESULT": "wrapper_child_result",
    "TICKSTORE_D4_POLICY_ADMISSION_RECEIPT_V001": "policy_admission_receipt",
}
MARKERS = ("D4_RESUME_RECONCILED", "D4_CHUNK_COMMIT", "D4_CHUNK_FORWARD_RECONCILE", "D4_SAFE_STOP_BOUNDARY",
           "D4_CHUNK_REUSE", "TICKSTORE_PUBLISHER_RECOVERY_V004=BLOCKED", "ORCHESTRATOR_ADAPTER_BLOCKED")
MAX_JSON = 4 * 1024 * 1024
MAX_LOG = 64 * 1024 * 1024
MAX_DEPTH = 4
MAX_FILES = 20000


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def walk(root, max_depth=MAX_DEPTH):
    """Bounded walk (no link following); yields files and reports truncation."""
    root = Path(root); out = []; truncated = False
    for ancestor in (root, *root.parents):
        if os.path.lexists(ancestor) and (ancestor.is_symlink() or getattr(os.lstat(ancestor), "st_file_attributes", 0) & 0x400):
            return out, {"root": str(root), "present": True, "error": "LINK_OR_REPARSE"}
    if not root.is_dir():
        return out, {"root": str(root), "present": False}
    stack = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError as exc:
            return out, {"root": str(root), "present": True, "error": type(exc).__name__}
        for e in entries:
            if e.is_symlink() or getattr(e.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:
                return out, {"root": str(root), "present": True, "error": "LINK_OR_REPARSE"}
            if e.is_dir(follow_symlinks=False):
                if depth < max_depth:
                    stack.append((Path(e.path), depth + 1))
                else:
                    truncated = True
            elif e.is_file(follow_symlinks=False):
                out.append(Path(e.path))
                if len(out) >= MAX_FILES:
                    return out, {"root": str(root), "present": True, "truncated_file_cap": True}
    return out, {"root": str(root), "present": True, "depth_truncated": truncated, "files": len(out)}


def classify_json(p):
    try:
        st = p.stat()
        if st.st_size > MAX_JSON:
            return None
        obj = json.loads(p.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict) or obj.get("schema") not in SCHEMAS:
        return None
    kind = SCHEMAS[obj["schema"]]
    item = {"kind": kind, "path": str(p), "sha256": sha_file(p), "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}
    if kind == "run_authority":
        item.update({k: obj.get(k) for k in ("run_id", "status", "successor_release_sha256", "owner_gate_sha256",
                                             "owner_gate_path", "config_sha256", "resume_root", "key_sha256", "generation")})
        item["protected_key_present"] = bool(obj.get("protected_key_b64"))
    elif kind == "checkpoint":
        pl = obj.get("payload") or {}
        item.update({k: pl.get(k) for k in ("status", "committed_count", "last_committed", "run_id", "total",
                                            "owner_gate_sha256", "successor_release_sha256", "config_sha256")})
        item["hmac_present"] = bool(obj.get("hmac_sha256"))
    elif kind == "owner_gate":
        item.update({k: obj.get(k) for k in ("mode", "authorized", "recovery_source_sha256", "release_id",
                                             "admission_generation")})
    elif kind in ("gca_locator_receipt", "gca_recovery_receipt"):
        item.update({k: obj.get(k) for k in ("status", "owner_gate_sha256", "state_status", "state_next_node",
                                             "canary_scratch_cert", "generation")})
    elif kind == "wrapper_child_result":
        item.update({k: obj.get(k) for k in ("status", "exit_code", "error", "final_error")})
    return item


def scope_fingerprint(roots):
    """Metadata observation only; equality is not proof of absence of all intervening writes."""
    h = hashlib.sha256(); n = 0
    for root, _, depth in roots:
        files, _info = walk(root, depth)
        for f in sorted(files):
            try:
                st = os.lstat(f)
            except OSError:
                continue
            h.update(("%s|%d|%d\n" % (f, st.st_size, st.st_mtime_ns)).encode("utf-8", "replace")); n += 1
    return {"files": n, "sha256": h.hexdigest().upper()}


def journal_facts(path):
    p = Path(path)
    if not p.is_file():
        return {"present": False}
    lines = p.read_bytes().splitlines(); prev = ""; intact = True; d4 = []
    for i, line in enumerate(lines):
        try:
            o = json.loads(line)
        except ValueError:
            intact = False; break
        if o.get("prev_line_sha256") != prev:
            intact = False
        prev = hashlib.sha256(line).hexdigest().upper()
        if o.get("node") == "D4":
            d4.append({"line": i, "ts": o.get("ts"), "phase": o.get("phase"), "status": o.get("status"),
                       "run_id": o.get("run_id"), "primary_error": o.get("primary_error")})
    last = json.loads(lines[-1]) if lines and intact else None
    return {"present": True, "sha256": sha_file(p), "lines": len(lines), "chain_intact": intact, "d4_entries": d4,
            "last": None if last is None else {k: last.get(k) for k in ("ts", "node", "phase", "status", "run_id")}}


def scan_runs(control_root):
    runs = Path(control_root) / "runs"; out = []
    if not runs.is_dir():
        return {"present": False}
    for d in sorted(x for x in runs.iterdir() if x.is_dir() and not x.is_symlink()):
        item = {"run": d.name, "files": sorted(f.name for f in d.iterdir() if f.is_file())[:200], "markers": {}}
        for f in d.iterdir():
            if f.is_file() and f.suffix == ".log" and f.stat().st_size <= MAX_LOG:
                with open(f, "rb") as fh:
                    for raw in fh:
                        text = raw.decode("utf-8", "replace")
                        for m in MARKERS:
                            if m in text:
                                item["markers"][m] = item["markers"].get(m, 0) + 1
                        if text.startswith("REASON=") and len(item.setdefault("reasons", [])) < 5:
                            item["reasons"].append(text.strip()[:200])
        for name in ("RECEIPT_D4.json", "RESULT_D4.json"):
            p = d / name
            if p.is_file():
                try:
                    o = json.loads(p.read_text(encoding="utf-8"))
                    item[name] = {k: o.get(k) for k in ("status", "primary_error", "finished_at", "effect_scope")}
                except ValueError:
                    item[name] = "UNPARSEABLE"
        out.append(item)
    return {"present": True, "runs": out}


def classify(rep, wrapper_ra):
    ras = [x for x in rep["found"] if x["kind"] == "run_authority"]
    cps = [x for x in rep["found"] if x["kind"] == "checkpoint"]
    receipts = rep["recovery_root"].get("d4_resume_prepared", 0) if isinstance(rep.get("recovery_root"), dict) else 0
    marker_runs = [r["run"] for r in rep["runs"].get("runs", []) if any(
        k in r["markers"] for k in ("D4_RESUME_RECONCILED", "D4_CHUNK_COMMIT", "D4_CHUNK_FORWARD_RECONCILE", "D4_CHUNK_REUSE"))]
    chunks = rep["resume_root"].get("checkpoint_chunks", 0)
    evidence_of_resumable_run = bool(cps or receipts or marker_runs or chunks)
    scope_ok = (all(s.get("present") is not False or s.get("optional") for s in rep["scope"])
                and not any(s.get("truncated_file_cap") or s.get("depth_truncated") or s.get("error") for s in rep["scope"])
                and rep["recovery_root"].get("present") is True and rep["runs"].get("present") is True
                and rep["journal"].get("present") is True and rep["journal"].get("chain_intact") is True)
    if not ras and not evidence_of_resumable_run:
        if not scope_ok:
            return "NOT_PROVEN_SCOPE_INCOMPLETE"
        return "FIRST_ADMISSION_NO_CHECKPOINT"
    if len(ras) == 1 and ras[0]["path"].lower() == str(wrapper_ra).lower():
        ra = ras[0]
        if ra.get("successor_release_sha256") != rep["release"].get("sha256"):
            return "INCOMPATIBLE_RUN_AUTHORITY_RELEASE"
        anchors = [g for g in rep["found"] if g["kind"] == "owner_gate" and g["sha256"] == str(ra.get("owner_gate_sha256", "")).upper()]
        if not anchors:
            return "NOT_PROVEN_ANCHOR_NOT_FOUND_IN_SCOPE"
        if any(g.get("recovery_source_sha256") != rep["release"].get("sha256") for g in anchors):
            return "INCOMPATIBLE_ANCHOR_SOURCE_FROZEN_ENGINE"
        cp_ok = [c for c in cps if c.get("run_id") == ra.get("run_id")]
        if cps and not cp_ok:
            return "INCOMPATIBLE_CHECKPOINT_RUN"
        return "RESUME_CANDIDATE_RUN_IDENTITY_DIAGNOSTIC_REQUIRED"
    if len(ras) > 1 or (ras and ras[0]["path"].lower() != str(wrapper_ra).lower()):
        return "INCOMPATIBLE_MULTIPLE_OR_MISPLACED_RUN_AUTHORITY"
    return "NOT_PROVEN_ARTIFACTS_WITHOUT_RUN_AUTHORITY"


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--resume-root", required=True)
    ap.add_argument("--control-root", required=True)
    ap.add_argument("--receipts-root")
    ap.add_argument("--extra-root", action="append", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    rr, cr = Path(a.resume_root), Path(a.control_root)
    wrapper_ra = rr / "authority" / "RUN_AUTHORITY.json"
    rep = {"schema": "TICKSTORE_D4_ROOTS_EVIDENCE_V001", "read_only": True, "key_material_read": False,
           "wrapper_run_authority_path": str(wrapper_ra), "wrapper_checkpoint_path": str(rr / "checkpoint" / "CHECKPOINT.json"),
           "scope": [], "found": []}
    release = rr / "SUCCESSOR_PACKAGE" / "engine" / "tickstore_publisher_recovery_v004_release.py"
    rep["release"] = {"path": str(release), "sha256": sha_file(release) if release.is_file() else None}
    top = sorted(x.name for x in rr.iterdir()) if rr.is_dir() else None
    cpd = rr / "checkpoint"
    rep["resume_root"] = {"present": rr.is_dir(), "top_level": top,
                          "authority_dir": sorted(x.name for x in (rr / "authority").iterdir()) if (rr / "authority").is_dir() else None,
                          "checkpoint_dir": sorted(x.name for x in cpd.iterdir()) if cpd.is_dir() else None,
                          "checkpoint_chunks": len([x for x in (cpd / "chunks").iterdir()]) if (cpd / "chunks").is_dir() else 0}
    roots = [(rr, False, MAX_DEPTH), (cr / "state", False, 1), (cr / "inbox", True, 2), (cr / "evidence", True, 3)]
    if a.receipts_root:
        roots.append((Path(a.receipts_root), False, MAX_DEPTH))
    roots += [(Path(x), True, MAX_DEPTH) for x in a.extra_root]
    state = cr / "state" / "STATE.json"; canary = None
    if state.is_file():
        st = json.loads(state.read_bytes().decode("utf-8"))
        rep["state"] = {"sha256": sha_file(state), "next_node": st.get("next_node"), "status": st.get("status"),
                        "completed_tail": (st.get("completed") or [])[-4:], "G_CA": st.get("G_CA"),
                        "canary": st.get("canary"), "keys": sorted(st)}
        canary = (st.get("canary") or {}).get("recovery")
    fp_roots = list(roots) + [(cr / "runs", True, 2)] + ([(Path(canary), True, 0)] if canary else [])
    fp_before = scope_fingerprint(fp_roots)
    if canary:
        rec = Path(canary); names = sorted(os.listdir(rec)) if rec.is_dir() else None
        rep["recovery_root"] = {"path": str(rec), "present": names is not None,
                                "entries": len(names or []),
                                "d4_resume_prepared": len([n for n in names or [] if n.startswith("d4_resume_prepared.")]),
                                "d4_resume_run_ids": sorted({n.split(".")[1] for n in names or [] if n.startswith("d4_resume_prepared.") and n.count(".") >= 3}),
                                "certify_scratch": len([n for n in names or [] if n.startswith("certify_scratch.")])}
    else:
        rep["recovery_root"] = {"present": False, "reason": "STATE.canary.recovery absent"}
    for root, optional, depth in roots:
        files, info = walk(root, depth); info["optional"] = optional; info["max_depth"] = depth
        rep["scope"].append(info)
        for f in files:
            if f.suffix.lower() == ".json" and "SUCCESSOR_PACKAGE" not in f.parts:
                item = classify_json(f)
                if item:
                    rep["found"].append(item)
    rep["journal"] = journal_facts(cr / "state" / "STATE_JOURNAL.jsonl")
    rep["runs"] = scan_runs(cr)
    fp_after = scope_fingerprint(fp_roots)
    rep["scope_fingerprint"] = {"before": fp_before, "after": fp_after, "unchanged": fp_before == fp_after}
    rep["classification"] = classify(rep, wrapper_ra) if fp_before == fp_after else "NOT_PROVEN_SCOPE_CHANGED_DURING_READ"
    rep["absence_claims_limited_to_scope"] = True
    Path(a.out).write_text(json.dumps(rep, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("D4_ROOTS_CLASSIFICATION=" + rep["classification"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
