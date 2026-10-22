"""PEGASUS FULL 2026 V008 — binding unívoco do harness QS4 e ligação do SAFE_STOP V006.

Regra de binding (por bytes, nunca por data/nome/ordem):
  harness BOUND  <=>  (a) MANIFEST_SHA256.txt do diretório do harness confere arquivo a
                      arquivo e o conjunto é exato; (b) HARNESS_IDENTITY.json.manifest_sha256
                      == SHA do manifesto; (c) HARNESS_IDENTITY.adapter_identity_sha256 ==
                      identidade do adaptador G4 deste pacote (HISTORICAL_G4/ADAPTER_IDENTITY.json,
                      cujo manifesto também confere); (d) qs4_harness.py expõe a superfície durável
                      exigida pelo DurableStopAdapter V006 (verify_source_contract).

Resultado físico nesta entrega: o único harness corrigido disponível (QS4 V002 R001,
identidade E52AF782…) exige o adaptador 05A0CF3D…, enquanto o adaptador G4 do V003 é
EC96FE9A… (FIXB_RUNTIME_ROOT_REBIND) => QS4_HARNESS_ADAPTER_BINDING_MISMATCH. Não se fabrica
re-pin: um sucessor QS4 vinculado ao EC96FE9A exige a própria qualificação QS4, vedada nesta
missão (QS4=NO). O caminho permanece implementado e fail-closed.

O wrapper (`qs4_supervised_main`) é o filho que o supervisor executaria para QS4: confere o
binding, instala o DurableStopAdapter no Orchestrator real e só então chamaria o main do
harness — mas antes exige a admissão QS4 externa, inexistente neste artefato.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


class QS4BindingBlocked(RuntimeError):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()


def _verify_manifest_dir(d: Path, manifest_name: str, identity_name: str) -> str:
    """Mesma convenção de qs4_lib.verify_manifest_dir: o arquivo de identidade fica fora do
    manifesto (a identidade É o SHA do manifesto)."""
    mf = d / manifest_name
    if not mf.is_file():
        raise QS4BindingBlocked("MANIFEST_ABSENT:" + str(mf))
    listed = {}
    for line in mf.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        h, n = line.split(None, 1)
        n = n.strip().lstrip("*").removeprefix("./")
        if n in listed:
            raise QS4BindingBlocked("MANIFEST_DUPLICATE:" + n)
        listed[n] = h.upper()
    actual = {p.relative_to(d).as_posix() for p in d.rglob("*")
              if p.is_file() and p != mf and p.relative_to(d).as_posix() != identity_name}
    if set(listed) != actual:
        raise QS4BindingBlocked("MANIFEST_SET_MISMATCH:%s" % sorted(set(listed) ^ actual)[:10])
    for n, h in listed.items():
        if _sha(d / n) != h:
            raise QS4BindingBlocked("MANIFEST_HASH_MISMATCH:" + n)
    return _sha(mf)


def required_adapter_identity(package_root: Path) -> str:
    g4 = Path(package_root) / "HISTORICAL_G4"
    ident = json.loads((g4 / "ADAPTER_IDENTITY.json").read_text(encoding="utf-8"))
    msha = _verify_manifest_dir(g4, "MANIFEST_SHA256.txt", "ADAPTER_IDENTITY.json")
    if ident.get("manifest_sha256") != msha or ident.get("adapter_identity_sha256") != msha:
        raise QS4BindingBlocked("PACKAGE_ADAPTER_IDENTITY_SELF_MISMATCH")
    return msha


def binding_report(harness_dir: Path, package_root: Path) -> dict:
    sys.path.insert(0, str(HERE))
    import pegasus_qs4_stop_bridge_v006 as bridge
    rep = {"schema": "PEGASUS_FULL_2026_V008_QS4_BINDING_V001", "harness_dir": str(harness_dir),
           "rule": "BYTES_ONLY_NO_TIME_NAME_OR_ORDER", "qs4": "NO"}
    try:
        need = required_adapter_identity(package_root)
        rep["required_adapter_identity"] = need
        hd = Path(harness_dir)
        hid = json.loads((hd / "HARNESS_IDENTITY.json").read_text(encoding="utf-8"))
        msha = _verify_manifest_dir(hd, "MANIFEST_SHA256.txt", "HARNESS_IDENTITY.json")
        rep["harness_manifest_sha256"] = msha
        rep["harness_identity_sha256"] = hid.get("harness_identity_sha256")
        rep["harness_adapter_pin"] = hid.get("adapter_identity_sha256")
        if hid.get("manifest_sha256") != msha:
            raise QS4BindingBlocked("HARNESS_IDENTITY_MANIFEST_MISMATCH")
        src = hd / "qs4_harness.py"
        rep["durable_hook_contract"] = bridge.verify_source_contract(src, _sha(src))
        if hid.get("adapter_identity_sha256") != need:
            raise QS4BindingBlocked("QS4_HARNESS_ADAPTER_BINDING_MISMATCH harness_pin=%s package_adapter=%s"
                                    % (hid.get("adapter_identity_sha256"), need))
        rep["binding"] = "BOUND"
    except (QS4BindingBlocked, bridge.BridgeBlocked, OSError, ValueError, KeyError) as exc:
        rep["binding"] = "BLOCKED"
        rep["cause"] = type(exc).__name__ + ":" + str(exc)
    return rep


def install_safestop(orchestrator_cls, *, evidence_root: Path, attempt_id: str,
                     source_sha: str, session_id: str, logical_id: str):
    """Liga o DurableStopAdapter V006 aos hooks run_case/run_step do Orchestrator real."""
    sys.path.insert(0, str(HERE))
    import pegasus_qs4_stop_bridge_v006 as bridge
    adapter = bridge.DurableStopAdapter(evidence_root, attempt_id, source_sha, session_id, logical_id)
    adapter.install(orchestrator_cls)
    return adapter


def qs4_supervised_main(harness_dir: Path, package_root: Path, argv, *, external_admission=None) -> int:
    """Filho QS4 sob o supervisor. Ordem fail-closed: binding -> admissão QS4 -> adaptador
    SAFE_STOP -> main do harness. `external_admission` é o módulo revisado futuro; não existe
    neste artefato, portanto o retorno é BLOCKED antes de importar o harness."""
    rep = binding_report(harness_dir, package_root)
    if rep["binding"] != "BOUND":
        print("QS4_SUPERVISED=BLOCKED " + rep.get("cause", "UNBOUND"), flush=True)
        return 2
    if external_admission is None:
        print("QS4_SUPERVISED=BLOCKED QS4_EXECUTION_FORBIDDEN_NO_EXTERNAL_ADMISSION", flush=True)
        return 2
    external_admission.admit(rep)  # deve lançar se não admitido
    sys.path.insert(0, str(harness_dir))
    import qs4_harness
    evidence_root, attempt_id, session_id, logical_id = external_admission.stop_binding()
    adapter = install_safestop(qs4_harness.Orchestrator, evidence_root=evidence_root,
                               attempt_id=attempt_id, source_sha=_sha(Path(harness_dir) / "qs4_harness.py"),
                               session_id=session_id, logical_id=logical_id)
    try:
        return qs4_harness.main(list(argv))
    finally:
        adapter.uninstall()
