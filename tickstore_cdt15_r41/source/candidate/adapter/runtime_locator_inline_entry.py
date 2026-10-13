from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _decode_members(payload: dict) -> dict[str, bytes]:
    return {name: base64.b64decode(value, validate=True) for name, value in payload["members"].items()}


def _preverify_payload(payload: dict) -> tuple[dict, dict[str, bytes], dict]:
    anchor = payload["anchor"]
    members = _decode_members(payload)
    manifest_raw = members["RELEASE_MANIFEST.json"]
    if _sha(manifest_raw) != str(anchor["release_manifest_sha256"]).upper():
        raise RuntimeError("ADAPTER_PREVERIFY_MANIFEST_HASH")
    if _sha(members["OWNER_GATE.json"]) != str(anchor["owner_gate_sha256"]).upper():
        raise RuntimeError("ADAPTER_PREVERIFY_OWNER_HASH")
    manifest = json.loads(manifest_raw.decode("utf-8"))
    if manifest.get("schema") != "RELEASE_MANIFEST_V004":
        raise RuntimeError("ADAPTER_PREVERIFY_MANIFEST_SCHEMA")
    expected_names = set(members) - {"RELEASE_MANIFEST.json"}
    if set(manifest.get("members", {})) != expected_names:
        raise RuntimeError("ADAPTER_PREVERIFY_MEMBER_SET")
    for name, item in manifest["members"].items():
        raw = members[name]
        if _sha(raw) != item.get("sha256") or len(raw) != item.get("bytes"):
            raise RuntimeError("ADAPTER_PREVERIFY_MEMBER_HASH:" + name)
    frozen = members["tickstore_publisher_recovery_v004.py"]
    if _sha(frozen) != str(anchor["recovery_source_sha256"]).upper():
        raise RuntimeError("ADAPTER_PREVERIFY_FROZEN_SOURCE")
    binding = json.loads(members["RUNTIME_LOCATOR_BINDING.json"].decode("utf-8"))
    if _sha(frozen) != str(binding["frozen_release_sha256"]).upper():
        raise RuntimeError("ADAPTER_PREVERIFY_BINDING_RELEASE")
    adapter_raw = members["RUNTIME_LOCATOR_ADAPTER.bin"]
    if _sha(adapter_raw) != str(binding["adapter_sha256"]).upper():
        raise RuntimeError("ADAPTER_PREVERIFY_ADAPTER_HASH")
    receipt = json.loads(members["RUNTIME_LOCATOR_RECEIPT.json"].decode("utf-8-sig"))
    return anchor, members, binding


def execute_payload(payload: dict) -> int:
    anchor, members, binding = _preverify_payload(payload)
    adapter_raw = members["RUNTIME_LOCATOR_ADAPTER.bin"]
    receipt = json.loads(members["RUNTIME_LOCATOR_RECEIPT.json"].decode("utf-8-sig"))
    adapter_ns = {"__name__": "tickstore_runtime_locator_adapter_inline", "__file__": "<RUNTIME_LOCATOR_ADAPTER.bin>"}
    exec(compile(adapter_raw, "<RUNTIME_LOCATOR_ADAPTER.bin>", "exec"), adapter_ns, adapter_ns)
    adapter_ns["validate_binding"](binding)
    adapter_ns["validate_locator_receipt"](receipt, binding)

    frozen_raw = members["tickstore_publisher_recovery_v004.py"]
    engine_ns = {"__name__": "tickstore_frozen_engine_with_runtime_adapter", "__file__": "<tickstore_publisher_recovery_v004.py>"}
    exec(compile(frozen_raw, "<tickstore_publisher_recovery_v004.py>", "exec"), engine_ns, engine_ns)
    gate = json.loads(members["OWNER_GATE.json"].decode("utf-8"))
    adapter_ns["install_engine_namespace"](engine_ns, binding, receipt, gate["admission_generation"])

    try:
        return int(engine_ns["dispatch_bootstrap"](payload))
    except engine_ns["D4ResumeSafeStop"]:
        print("SAFE_STOP=YES\nD4_RESUME_CHECKPOINT_RECONCILED=YES\nD4_CERTIFICATE_PERSISTED=NO", flush=True)
        return 130
    except KeyboardInterrupt:
        print("SAFE_STOP=NO\nINTERRUPTED_RECONCILIATION_REQUIRED=YES", flush=True)
        return 130
    except Exception as exc:
        print("TICKSTORE_PUBLISHER_RECOVERY_V004=BLOCKED\nREASON=" + str(exc), flush=True)
        return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap-handle", type=int, required=True)
    args = ap.parse_args()
    if sys.argv[0] != "-":
        raise RuntimeError("INLINE_STDIN_SOURCE_REQUIRED")
    if os.name != "nt":
        raise RuntimeError("WINDOWS_REQUIRED")
    import msvcrt
    fd = msvcrt.open_osfhandle(args.bootstrap_handle, os.O_RDONLY | os.O_BINARY)
    with os.fdopen(fd, "rb") as pipe:
        raw = pipe.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise RuntimeError("BOOTSTRAP_TOO_LARGE")
    return execute_payload(json.loads(raw.decode("utf-8")))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print("TICKSTORE_RUNTIME_LOCATOR_INLINE_ENTRY=BLOCKED\nREASON=" + str(exc), flush=True)
        raise SystemExit(2)
