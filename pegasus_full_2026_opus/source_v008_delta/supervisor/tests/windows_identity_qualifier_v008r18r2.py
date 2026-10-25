"""PEGASUS FULL 2026 — Qualificador DIRIGIDO de identidade de arquivo (R18R2), seguro pré-efeito.

Exercita as TRÊS rotas de leitura de arquivo externo do supervisor contra fixtures SINTÉTICAS
isoladas, cobrindo a classe TOCTOU/reparse que o preflight apontou:

  verify_gate_file  ·  ProductionReleaseAdmission._load_bundle  ·  load_external_admission_module

Casos (positivos e negativos): arquivo regular autêntico; symlink de arquivo; symlink de diretório
ancestral; junction de diretório ancestral (Windows); escape do pacote selado; bundle/módulo dentro
do pacote selado; SHA-256 incorreto; troca concorrente de identidade (bytes != SHA fixado); arquivo
ausente; falha de abertura. Cada caso tem veredito ESPERADO; o runner confirma o comportamento.

É SEGURO PRÉ-EFEITO: não executa economia, não instala nada, não toca as três árvores protegidas,
não lê política. Resultado é hash-bound (SHA-256 do supervisor). Exit 0 só se todos os casos
obrigatórios da plataforma se comportarem como esperado; senão exit 3 (falha técnica de contrato).

Uso (o bootstrap PS 5.1 chama):  python -I -B windows_identity_qualifier_v008r18r2.py --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../supervisor/tests
SUP = HERE.parent                               # .../supervisor
ROOT = SUP.parent                               # pacote selado
sys.path.insert(0, str(SUP))
import pegasus_supervisor_v008 as sup  # noqa: E402

IS_WIN = os.name == "nt"


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def _seal(bundle: dict) -> dict:
    body = {k: v for k, v in bundle.items() if k != "bundle_content_sha256"}
    bundle["bundle_content_sha256"] = _sha_bytes(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return bundle


def _mk_symlink(link: Path, target: Path, directory=False) -> bool:
    try:
        link.symlink_to(target, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError):
        return False


def _mk_junction(link: Path, target: Path) -> bool:
    # Junction é nativo de Windows (mklink /J). Em POSIX não existe => indisponível.
    if not IS_WIN:
        return False
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
        return True
    except Exception:
        return False


def _module_src() -> str:
    return ("class _A:\n    schema='WIN_IDENTITY_PROBE'\nADMISSION=_A()\n")


def _expect_block(fn, needle):
    try:
        fn()
        return {"result": "UNEXPECTED_ACCEPT", "ok": False}
    except sup.SupervisorBlocked as exc:
        return {"result": "BLOCKED", "ok": (needle in str(exc)), "cause": str(exc)[:200]}
    except Exception as exc:  # qualquer Blocked com outro nome de classe também conta como bloqueio
        name = type(exc).__name__
        return {"result": "BLOCKED_OTHER:%s" % name, "ok": (name in ("Blocked",)), "cause": str(exc)[:200]}


def run_cases(outdir: Path) -> dict:
    cases = []

    def rec(cid, platform, ok, detail):
        # ok=None => caso PULADO nesta plataforma (não conta como obrigatório); não coagir None->False.
        cases.append({"id": cid, "platform": platform, "ok": (None if ok is None else bool(ok)), **detail})

    with tempfile.TemporaryDirectory(prefix="pegasus_winident_") as td, \
            tempfile.TemporaryDirectory(prefix="pegasus_sealed_") as pkg:
        d = Path(td)
        pkg = Path(pkg)

        # ---- módulo externo: autêntico (positivo) ----
        realmod = d / "ext.py"; realmod.write_text(_module_src(), encoding="utf-8")
        msha = _sha_file(realmod)
        try:
            adm = sup.load_external_admission_module(str(realmod), msha, pkg)
            ok = getattr(adm, "schema", None) == "WIN_IDENTITY_PROBE"
            rec("MODULE_AUTHENTIC", "both", ok, {"result": "LOADED"})
        except Exception as exc:
            rec("MODULE_AUTHENTIC", "both", False, {"result": "ERR", "cause": str(exc)[:200]})

        # ---- módulo: SHA incorreto ----
        rec("MODULE_BAD_SHA", "both",
            _expect_block(lambda: sup.load_external_admission_module(str(realmod), "D" * 64, pkg),
                          "IDENTITY_MISMATCH")["ok"], {"result": "BLOCKED_EXPECTED"})

        # ---- módulo: troca concorrente de identidade (bytes != SHA fixado) ----
        swapped = d / "ext_swapped.py"; swapped.write_text(_module_src() + "# swap\n", encoding="utf-8")
        rec("MODULE_CONCURRENT_SWAP", "both",
            _expect_block(lambda: sup.load_external_admission_module(str(swapped), msha, pkg),
                          "IDENTITY_MISMATCH_OR_CONCURRENT_SWAP")["ok"], {"result": "BLOCKED_EXPECTED"})

        # ---- módulo: ausente ----
        rec("MODULE_ABSENT", "both",
            _expect_block(lambda: sup.load_external_admission_module(str(d / "nope.py"), msha, pkg),
                          "ABSENT")["ok"], {"result": "BLOCKED_EXPECTED"})

        # ---- módulo: dentro do pacote selado ----
        inpkg = pkg / "ext.py"; inpkg.write_text(_module_src(), encoding="utf-8")
        rec("MODULE_INSIDE_SEALED", "both",
            _expect_block(lambda: sup.load_external_admission_module(str(inpkg), _sha_file(inpkg), pkg),
                          "INSIDE_SEALED_PACKAGE")["ok"], {"result": "BLOCKED_EXPECTED"})

        # ---- módulo: symlink direto de arquivo ----
        linkmod = d / "ext_link.py"
        if _mk_symlink(linkmod, realmod):
            rec("MODULE_FILE_SYMLINK", "both",
                _expect_block(lambda: sup.load_external_admission_module(str(linkmod), msha, pkg),
                              "REPARSE_OR_ALIAS")["ok"], {"result": "BLOCKED_EXPECTED"})
        else:
            rec("MODULE_FILE_SYMLINK", "both", None, {"result": "SKIPPED_SYMLINK_UNAVAILABLE"})

        # ---- módulo: symlink de diretório ancestral ----
        realdir = d / "rd"; realdir.mkdir(); (realdir / "ext.py").write_text(_module_src(), encoding="utf-8")
        aliasdir = d / "ad"
        if _mk_symlink(aliasdir, realdir, directory=True):
            rec("MODULE_ANCESTOR_SYMLINK", "both",
                _expect_block(lambda: sup.load_external_admission_module(str(aliasdir / "ext.py"),
                              _sha_file(realdir / "ext.py"), pkg), "REPARSE_OR_ALIAS")["ok"],
                {"result": "BLOCKED_EXPECTED"})
        else:
            rec("MODULE_ANCESTOR_SYMLINK", "both", None, {"result": "SKIPPED_SYMLINK_UNAVAILABLE"})

        # ---- módulo: junction de diretório ancestral (Windows) ----
        jdir = d / "jd"
        if _mk_junction(jdir, realdir):
            rec("MODULE_ANCESTOR_JUNCTION", "windows",
                _expect_block(lambda: sup.load_external_admission_module(str(jdir / "ext.py"),
                              _sha_file(realdir / "ext.py"), pkg), "REPARSE_OR_ALIAS")["ok"],
                {"result": "BLOCKED_EXPECTED"})
        else:
            rec("MODULE_ANCESTOR_JUNCTION", "windows", None,
                {"result": "SKIPPED_JUNCTION_WINDOWS_ONLY" if not IS_WIN else "SKIPPED_MKLINK_FAILED"})

        # ---- bundle: autêntico (gates físicos) + decisão reservada no entry congelado ----
        broot = d / "bundle_root"; broot.mkdir()
        gates = {}
        for g in sup.REQUIRED_PRODUCTION_GATES:
            rel = "gates/%s.json" % g
            (broot / "gates").mkdir(exist_ok=True)
            content = json.dumps({"gate": g, "release_id": "WINIDENT"}, sort_keys=True).encode("utf-8")
            (broot / rel).write_bytes(content)
            gates[g] = {"path": rel, "sha256": _sha_bytes(content), "status": "PASS", "release_id": "WINIDENT"}
        bundle = _seal({"schema": sup.PRODUCTION_AUTH_SCHEMA, "release_id": "WINIDENT", "gates": gates,
                        "phase_chain": {"B": "PASS", "C": "PASS"}})
        v = sup.production_admission_verdict(bundle, phase="B", bundle_root=broot)
        rec("BUNDLE_GATES_PHYSICAL_AUTHENTIC", "both", v["admission"] == "ADMITTED_GATES_PHYSICALLY_VERIFIED",
            {"result": v["admission"]})

        # ---- bundle: pinagem de conteúdo adulterada ----
        tam = dict(bundle); tam["release_id"] = "TAMPERED"
        v2 = sup.production_admission_verdict(tam, phase="B", bundle_root=broot)
        rec("BUNDLE_CONTENT_PIN_TAMPER", "both",
            v2["admission"] == "BLOCKED" and any("CONTENT_SHA_MISSING_OR_MISMATCH" in x for x in v2["gaps"]),
            {"result": v2["admission"]})

        # ---- bundle: symlink do arquivo de bundle ----
        bpath = broot / "AUTH_BUNDLE.json"; bpath.write_text(json.dumps(bundle), encoding="utf-8")
        blink = d / "bundle_link.json"
        if _mk_symlink(blink, bpath):
            adm = sup.ProductionReleaseAdmission(str(blink))

            class _E:
                class Blocked(RuntimeError):
                    pass

                def release_admission(self, req, phase):
                    raise self.Blocked("G00_RUN_RELEASE_DISABLED")
            rec("BUNDLE_FILE_SYMLINK", "both",
                _expect_block(lambda: adm.admit(phase="B", package_root=pkg, entry=_E(), ns=None),
                              "REPARSE_OR_ALIAS")["ok"], {"result": "BLOCKED_EXPECTED"})
        else:
            rec("BUNDLE_FILE_SYMLINK", "both", None, {"result": "SKIPPED_SYMLINK_UNAVAILABLE"})

        # ---- fail-closed: sem garantia nativa (openat ausente e não-Windows) ----
        if not IS_WIN:
            saved = sup._O_NOFOLLOW
            try:
                sup._O_NOFOLLOW = 0
                probe = d / "probe.bin"; probe.write_bytes(b"x")
                rec("FAIL_CLOSED_NO_NATIVE_GUARANTEE", "posix",
                    _expect_block(lambda: sup._read_authenticated_bytes(str(probe), kind="PROBE"),
                                  "NATIVE_IDENTITY_GUARANTEE_UNAVAILABLE_FAIL_CLOSED")["ok"],
                    {"result": "BLOCKED_EXPECTED"})
            finally:
                sup._O_NOFOLLOW = saved
        else:
            rec("FAIL_CLOSED_NO_NATIVE_GUARANTEE", "posix", None, {"result": "SKIPPED_ON_WINDOWS"})

    required = [c for c in cases if c["ok"] is not None]
    all_ok = all(c["ok"] for c in required)
    receipt = {
        "schema": "PEGASUS_FULL_2026_V008R18R2_WINDOWS_IDENTITY_QUALIFICATION",
        "platform": "windows" if IS_WIN else ("posix" if os.name == "posix" else os.name),
        "python": sys.version.split()[0],
        "supervisor_sha256": _sha_file(SUP / "pegasus_supervisor_v008.py"),
        "win_native_sha256": _sha_file(SUP / "pegasus_win_native_v008.py"),
        "native_read_path": ("WIN32_HANDLE_DENY_WRITE_DELETE" if IS_WIN else
                             ("POSIX_OPENAT_O_NOFOLLOW" if (os.open in getattr(os, "supports_dir_fd", set())
                                                           and sup._O_NOFOLLOW) else "NONE_FAIL_CLOSED")),
        "cases": cases,
        "required_cases": len(required),
        "required_pass": sum(1 for c in required if c["ok"]),
        "skipped": [c["id"] for c in cases if c["ok"] is None],
        "result": "PASS" if all_ok else "FAIL",
        "effects": "NONE_PRE_EFFECT_NO_ECONOMY_NO_INSTALL_NO_PROTECTED_TREE_TOUCH",
        "gates": {"g4": "FROZEN", "qs4": "NO", "run_released": "NO", "full_economic": "NOT_STARTED"},
        "wall_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "result_return_to": "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15",
    }
    outdir.mkdir(parents=True, exist_ok=True)
    rp = outdir / "WINDOWS_IDENTITY_QUALIFICATION_R18R2_RESULT.json"
    rp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="windows_identity_qualifier_v008r18r2")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args(argv)
    receipt = run_cases(Path(ns.out).resolve())
    print(json.dumps({"result": receipt["result"], "platform": receipt["platform"],
                      "native_read_path": receipt["native_read_path"],
                      "required_pass": "%d/%d" % (receipt["required_pass"], receipt["required_cases"]),
                      "skipped": receipt["skipped"]}, ensure_ascii=False))
    return 0 if receipt["result"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
