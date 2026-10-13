"""TICKSTORE B06R3 - deterministic resolution of an interrupted STATE CAS commit.

Explicit tool, never invoked by the D4 entry. Default is a read-only DIAGNOSE;
--apply performs only the action that the evidence determines, under the same
process-lifetime boundary that a D4 entry holds (so no live entry can race).

CAS protocol of the D4 entry (runtime_locator_orchestrator_entry.commit_state):
  1 write STATE.json.cas-new.<tag> (target bytes), fsync
  2 write STATE.json.cas-intent.<tag> {prev_sha256, prev_identity, new_sha256}, fsync file+dir
  3 rename STATE.json -> STATE.json.cas-old.<tag>
  4 link  cas-new -> STATE.json (create-if-absent), unlink cas-new, readback, fsync
  5 unlink cas-old, unlink cas-intent

Decision table (one tag only; anything else -> BLOCKED_MANUAL, nothing changed):
  R1 STATE absent, intent, cas-old sha == intent.prev        -> restore cas-old (confirmed) as STATE
                                                                 by create-if-absent link; target is
                                                                 never promoted (it was not confirmed)
  R2 STATE present, sha == intent.new                         -> commit had completed; archive debris
  R3 STATE present, sha == intent.prev, no cas-old            -> commit never started step 3; archive debris
  R4 otherwise                                                -> BLOCKED_MANUAL (no write)
Consistency proofs required before any write:
  * journal STATE_JOURNAL.jsonl hash chain intact (prev_line_sha256 of every line);
  * restored/kept STATE parses with schema TICKSTORE_ORCH_STATE_V001;
  * if --checkpoint is given: the kept STATE must not claim D4 complete (completed has D4 or
    next_node beyond D4) unless the checkpoint payload status is ALL_CHUNKS_COMMITTED.
Debris is never deleted: it is moved to state/cas_recovery/<tag>/ with a receipt.
The live intent is retained until that receipt has been flushed. A partial
archive stays BLOCKED_MANUAL; this tool does not silently complete it on retry.
Diagnosis and apply are bound to the same physical STATE/debris/journal and,
when supplied, checkpoint versions. This check is not checkpoint authentication.

Usage: python -B -I STATE_CAS_RECOVERY.py --state <...\\state\\STATE.json> [--checkpoint <CHECKPOINT.json>]
                                          [--adapter-dir <adapter dir>] [--apply]
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

NODES_AFTER_D4 = {"D5", "D6", "D7", "D8", "D9", "D10", "D11", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9",
                  "F1", "F2", "F3", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "H1", "H2", "H3", "H4", "H5", "H6",
                  "I1", "DONE"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def load_entry(adapter_dir):
    p = Path(adapter_dir) / "runtime_locator_orchestrator_entry.py"
    spec = importlib.util.spec_from_file_location("tickstore_cas_recovery_entry", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def journal_chain(journal: Path):
    if not journal.exists():
        return {"present": False, "intact": True, "lines": 0, "last": None}
    lines = journal.read_bytes().splitlines()
    prev = ""
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            return {"present": True, "intact": False, "lines": len(lines), "broken_at": i, "last": None}
        if obj.get("prev_line_sha256") != prev:
            return {"present": True, "intact": False, "lines": len(lines), "broken_at": i, "last": None}
        prev = sha(line)
    last = json.loads(lines[-1]) if lines else None
    return {"present": True, "intact": True, "lines": len(lines),
            "last": None if last is None else {k: last.get(k) for k in ("node", "phase", "status")}}


def claims_d4_complete(state):
    return "D4" in (state.get("completed") or []) or state.get("next_node") in NODES_AFTER_D4


def _evidence_snapshot(state_path, checkpoint):
    """Bind diagnosis to physical versions, including an explicitly supplied checkpoint.

    These are local consistency fingerprints, not HMAC verification or release authority.
    No recovery code is allowed to ignore a supplied checkpoint at the apply boundary.
    """
    paths = [state_path, state_path.parent / "STATE_JOURNAL.jsonl"]
    paths.extend(sorted(state_path.parent.glob(state_path.name + ".cas-*")))
    if checkpoint is not None:
        paths.append(Path(checkpoint))
    out = {}
    for p in paths:
        for parent in (p.parent, *p.parent.parents):
            s = os.lstat(parent)
            if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                raise RuntimeError("CAS_RECOVERY_LINK_OR_REPARSE")
        key = os.path.normcase(os.path.abspath(p))
        try:
            before = os.lstat(p)
        except FileNotFoundError:
            out[key] = None
            continue
        if not stat.S_ISREG(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("CAS_RECOVERY_NOT_REGULAR")
        def identity(s):
            return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]
        with p.open("rb") as f:
            opened = os.fstat(f.fileno())
            raw = f.read()
            last = os.fstat(f.fileno())
        after = os.lstat(p)
        if not identity(before) == identity(opened) == identity(last) == identity(after):
            raise RuntimeError("CAS_RECOVERY_EVIDENCE_CHANGED")
        out[key] = {"identity": identity(after), "sha256": sha(raw)}
    return out


def diagnose(state_path: Path, checkpoint: Path = None):
    state_path = Path(state_path)
    try:
        before = _evidence_snapshot(state_path, checkpoint)
        rep, parts = _diagnose(state_path, checkpoint)
        after = _evidence_snapshot(state_path, checkpoint)
        if before != after:
            raise RuntimeError("CAS_RECOVERY_EVIDENCE_CHANGED")
        rep["evidence_snapshot"] = after
        rep["checkpoint_path"] = None if checkpoint is None else os.path.abspath(checkpoint)
        # A partial archive needs explicit review. Do not silently retry with a
        # different decision, discard the original, or report NOTHING_TO_RECOVER.
        archive_root = state_path.parent / "cas_recovery"
        pending = []
        if os.path.lexists(archive_root):
            s = os.lstat(archive_root)
            if not stat.S_ISDIR(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                raise RuntimeError("CAS_RECOVERY_ARCHIVE_NOT_REGULAR_DIRECTORY")
            for d in archive_root.iterdir():
                s = os.lstat(d)
                if not stat.S_ISDIR(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                    raise RuntimeError("CAS_RECOVERY_ARCHIVE_NOT_REGULAR_DIRECTORY")
                receipt = d / "RECOVERY_RECEIPT.json"
                valid = False
                if os.path.lexists(receipt):
                    s = os.lstat(receipt)
                    if stat.S_ISREG(s.st_mode) and not getattr(s, "st_file_attributes", 0) & 0x400:
                        try:
                            obj = json.loads(receipt.read_bytes())
                            valid = (isinstance(obj, dict) and obj.get("applied") is True
                                     and obj.get("tag") == d.name
                                     and os.path.normcase(os.path.abspath(obj.get("state", "")))
                                     == os.path.normcase(os.path.abspath(state_path)))
                        except (ValueError, TypeError):
                            pass
                if not valid or d.name in rep.get("tags", []):
                    pending.append(str(d))
        if pending:
            rep["decision"] = "BLOCKED_MANUAL"
            rep["reasons"].append("RECOVERY_ARCHIVE_FINALIZATION_PENDING")
            rep["pending_archives"] = sorted(pending)
            return rep, None
        return rep, parts
    except (OSError, RuntimeError) as exc:
        return {"schema": "TICKSTORE_D4_STATE_CAS_RECOVERY_REPORT_V001", "state": str(state_path),
                "decision": "BLOCKED_MANUAL", "reasons": [str(exc)]}, None


def _diagnose(state_path: Path, checkpoint: Path = None):
    sd = state_path.parent
    names = sorted(os.listdir(sd))
    pat = re.compile(re.escape(state_path.name) + r"\.cas-(new|old|intent)\.([0-9]+\.[0-9a-f]{32})$")
    found = {}
    for n in names:
        m = pat.match(n)
        if m:
            found.setdefault(m.group(2), {})[m.group(1)] = sd / n
    loose = [n for n in names if n.startswith(state_path.name + ".cas-") and not pat.match(n)]
    rep = {"schema": "TICKSTORE_D4_STATE_CAS_RECOVERY_REPORT_V001", "state": str(state_path),
           "state_present": os.path.lexists(state_path), "tags": sorted(found), "unrecognised_debris": loose,
           "decision": "BLOCKED_MANUAL", "reasons": []}
    if not found and not loose:
        rep["decision"] = "NOTHING_TO_RECOVER"
        return rep, None
    if loose or len(found) != 1:
        rep["reasons"].append("DEBRIS_NOT_SINGLE_TAG")
        return rep, None
    tag = rep["tags"][0]; parts = found[tag]; rep["tag"] = tag
    if "intent" not in parts:
        rep["reasons"].append("INTENT_MISSING")
        return rep, None
    try:
        intent = json.loads(parts["intent"].read_bytes().decode("ascii"))
    except ValueError:
        rep["reasons"].append("INTENT_UNREADABLE"); return rep, None
    if intent.get("schema") != "TICKSTORE_D4_STATE_CAS_INTENT_V001" or intent.get("tag") != tag:
        rep["reasons"].append("INTENT_SCHEMA_OR_TAG"); return rep, None
    rep["intent"] = {k: intent.get(k) for k in ("prev_sha256", "new_sha256")}
    if "new" in parts:
        rep["cas_new_matches_intent"] = sha(parts["new"].read_bytes()) == intent["new_sha256"]
        if not rep["cas_new_matches_intent"]:
            rep["reasons"].append("CAS_NEW_NOT_INTENT_TARGET"); return rep, None
    jc = journal_chain(sd / "STATE_JOURNAL.jsonl"); rep["journal"] = jc
    if not jc["intact"]:
        rep["reasons"].append("JOURNAL_CHAIN_BROKEN"); return rep, None
    if not rep["state_present"]:
        if "old" not in parts:
            rep["reasons"].append("STATE_ABSENT_WITHOUT_CONFIRMED_BACKUP"); return rep, None
        old_raw = parts["old"].read_bytes()
        if sha(old_raw) != intent["prev_sha256"]:
            rep["reasons"].append("CAS_OLD_NOT_CONFIRMED_VERSION"); return rep, None
        kept_raw, action = old_raw, "R1_RESTORE_CONFIRMED"
    else:
        cur = state_path.read_bytes()
        if sha(cur) == intent["new_sha256"]:
            kept_raw, action = cur, "R2_COMMIT_COMPLETED_ARCHIVE_DEBRIS"
        elif sha(cur) == intent["prev_sha256"] and "old" not in parts:
            kept_raw, action = cur, "R3_COMMIT_NOT_STARTED_ARCHIVE_DEBRIS"
        else:
            rep["reasons"].append("STATE_PRESENT_MATCHES_NEITHER_PREV_NOR_NEW"); return rep, None
    try:
        kept = json.loads(kept_raw.decode("utf-8"))
    except ValueError:
        rep["reasons"].append("KEPT_STATE_UNPARSEABLE"); return rep, None
    if kept.get("schema") != "TICKSTORE_ORCH_STATE_V001":
        rep["reasons"].append("KEPT_STATE_SCHEMA"); return rep, None
    rep["kept_state"] = {k: kept.get(k) for k in ("next_node", "status")}
    if jc["last"] and jc["last"].get("phase") == "FINISHED" and action == "R1_RESTORE_CONFIRMED":
        rep["journal_relation"] = "TRANSITION_LOGGED_NOT_COMMITTED_RESTORED_STATE_IS_PRE_TRANSITION"
    else:
        rep["journal_relation"] = "CONSISTENT_WITH_KEPT_STATE"
    if checkpoint is not None:
        try:
            payload = json.loads(Path(checkpoint).read_bytes().decode("ascii")).get("payload") or {}
        except (OSError, ValueError):
            rep["reasons"].append("CHECKPOINT_UNREADABLE"); return rep, None
        rep["checkpoint"] = {k: payload.get(k) for k in ("status", "committed_count", "run_id")}
        if claims_d4_complete(kept) and payload.get("status") != "ALL_CHUNKS_COMMITTED":
            rep["reasons"].append("STATE_AHEAD_OF_CHECKPOINT"); return rep, None
    rep["decision"] = action
    return rep, parts


def apply(state_path: Path, rep, parts, entry):
    if rep.get("decision") not in ("R1_RESTORE_CONFIRMED", "R2_COMMIT_COMPLETED_ARCHIVE_DEBRIS",
                                   "R3_COMMIT_NOT_STARTED_ARCHIVE_DEBRIS") or "evidence_snapshot" not in rep:
        raise RuntimeError("CAS_RECOVERY_DIAGNOSIS_REQUIRED")
    sd = state_path.parent; tag = rep["tag"]
    release = entry.acquire_state_boundary(state_path)  # no live D4 entry may hold this STATE
    try:
        checkpoint = rep.get("checkpoint_path")
        again, parts2 = diagnose(state_path, Path(checkpoint) if checkpoint else None)
        if again != rep:
            raise RuntimeError("CAS_RECOVERY_EVIDENCE_CHANGED")
        parts = parts2  # only paths from the diagnosis repeated under the boundary
        if rep["decision"] == "R1_RESTORE_CONFIRMED":
            try:
                os.link(parts["old"], state_path)  # create-if-absent: a concurrent STATE is never overwritten
            except FileExistsError:
                raise RuntimeError("CAS_RECOVERY_CONCURRENT_STATE_PRESERVED") from None
            if sha(state_path.read_bytes()) != rep["intent"]["prev_sha256"]:
                raise RuntimeError("CAS_RECOVERY_READBACK")
        evidence = sd / "cas_recovery" / tag
        evidence.mkdir(parents=True, exist_ok=False)
        for kind in ("new", "old"):
            if kind in parts:
                os.rename(parts[kind], evidence / parts[kind].name)
        # Keep the live intent blocking D4 until the receipt has been flushed.
        # The archived hard link preserves the exact original bytes; no replace.
        os.link(parts["intent"], evidence / parts["intent"].name)
        entry._fsync_directory(sd)
        result = dict(rep)
        result["applied"] = True
        result["applied_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result["state_sha256_after"] = sha(state_path.read_bytes())
        with open(evidence / "RECOVERY_RECEIPT.json", "xb") as f:
            f.write((json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        entry._fsync_directory(evidence)
        os.unlink(parts["intent"])
        entry._fsync_directory(sd)
        return result
    finally:
        release()


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--state", required=True)
    ap.add_argument("--checkpoint")
    ap.add_argument("--adapter-dir", default=str(Path(__file__).resolve().parent.parent / "adapter"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    state_path = Path(a.state)
    rep, parts = diagnose(state_path, Path(a.checkpoint) if a.checkpoint else None)
    if a.apply and rep["decision"].startswith("R"):
        rep = apply(state_path, rep, parts, load_entry(a.adapter_dir))
    print(json.dumps(rep, indent=2, sort_keys=True, default=str))
    return 0 if rep["decision"] in ("NOTHING_TO_RECOVER",) or rep.get("applied") or (not a.apply and rep["decision"].startswith("R")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
