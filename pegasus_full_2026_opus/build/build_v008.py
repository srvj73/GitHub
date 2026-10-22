"""Build determinístico do PEGASUS FULL 2026 V008 a partir do payload V003 byte-idêntico.

  python -I -B build_v008.py manifest --tree <árvore V008> --v003-payload <payload V003>
  python -I -B build_v008.py package  --tree <árvore V008> --out <zip>

`manifest`: (1) preserva o manifesto V003 em receipts/V008/PARENT_V003_MANIFEST_SHA256.json;
(2) prova que TODO arquivo do V003 permanece byte-idêntico na árvore V008 (exceto o próprio
manifesto raiz, regenerado); (3) gera MANIFEST_SHA256.json no formato V003 ({caminho: SHA}).
`package`: ZIP determinístico (ordem lexicográfica, mtime fixo, DEFLATE) da árvore exata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

FIXED_DT = (2026, 10, 22, 0, 0, 0)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def files(tree: Path):
    return sorted(p for p in tree.rglob("*") if p.is_file())


def cmd_manifest(ns) -> int:
    tree = Path(ns.tree).resolve()
    v3 = Path(ns.v003_payload).resolve()
    v3m = json.loads((v3 / "MANIFEST_SHA256.json").read_text(encoding="utf-8"))
    parent_copy = tree / "receipts" / "V008" / "PARENT_V003_MANIFEST_SHA256.json"
    parent_copy.parent.mkdir(parents=True, exist_ok=True)
    src_bytes = (v3 / "MANIFEST_SHA256.json").read_bytes()
    if parent_copy.exists():
        if parent_copy.read_bytes() != src_bytes:
            raise SystemExit("PARENT_MANIFEST_COPY_DRIFT")
    else:
        parent_copy.write_bytes(src_bytes)
    drift = [k for k, h in v3m.items() if not (tree / k).is_file() or sha(tree / k) != h.upper()]
    if drift:
        raise SystemExit("V003_BYTES_NOT_PRESERVED:%s" % drift[:10])
    for leftovers in ("__pycache__",):
        bad = [p for p in tree.rglob(leftovers)]
        if bad:
            raise SystemExit("BYTECODE_IN_TREE:%s" % bad[:3])
    out = {}
    for p in files(tree):
        rel = p.relative_to(tree).as_posix()
        if rel == "MANIFEST_SHA256.json":
            continue
        out[rel] = sha(p)
    (tree / "MANIFEST_SHA256.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    added = sorted(set(out) - set(v3m))
    print(json.dumps({"members": len(out), "v003_members_preserved": len(v3m), "added": added,
                      "manifest_sha256": sha(tree / "MANIFEST_SHA256.json"),
                      "parent_v003_manifest_sha256": hashlib.sha256(src_bytes).hexdigest().upper()}, indent=1))
    return 0


def cmd_package(ns) -> int:
    tree = Path(ns.tree).resolve()
    out = Path(ns.out).resolve()
    if out.exists():
        raise SystemExit("OUTPUT_EXISTS_FAIL_CLOSED")
    base = tree.name
    with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files(tree):
            rel = base + "/" + p.relative_to(tree).as_posix()
            zi = zipfile.ZipInfo(rel, FIXED_DT)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o100644 << 16
            with p.open("rb") as f:
                z.writestr(zi, f.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(out) as z:
        if z.testzip() is not None:
            raise SystemExit("ZIP_CRC_FAILURE")
        n = len(z.namelist())
    print(json.dumps({"zip": str(out), "bytes": out.stat().st_size, "sha256": sha(out), "members": n}, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--tree", required=True)
    m.add_argument("--v003-payload", required=True)
    p = sub.add_parser("package")
    p.add_argument("--tree", required=True)
    p.add_argument("--out", required=True)
    ns = ap.parse_args(argv)
    return cmd_manifest(ns) if ns.cmd == "manifest" else cmd_package(ns)


if __name__ == "__main__":
    sys.exit(main())
