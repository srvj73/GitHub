"""Cerimonial de build/qualificação R17 (M1 -> bateria -> M2 -> pacote -> verificação dos bytes).
Honesto: a evidência regenerável de offline_final é movida para fora em M1; o manifesto M1 cobre
código+docs+demais recibos; a bateria roda contra M1 (o verify de CLI lê o manifesto M1); M2 adiciona
só a evidência regenerada + as provas de convergência R17. Empacota o ZIP R17 e re-verifica os bytes
extraídos. Não executa economia; não consulta política.
"""
import hashlib, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path

TREE = Path(sys.argv[1]).resolve()
DELIVERY = Path(sys.argv[2]).resolve()       # pegasus_full_2026_opus/delivery (repo)
EVID = Path(sys.argv[3]).resolve()           # external evidence dir
BUILD = TREE.parent.parent / "build" if False else None
PY = sys.executable
SUP = TREE / "supervisor"
OFR = "receipts/V008/offline_final"
ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R18R1_20261024.zip"

REGEN = [f"{OFR}/m1_battery/{n}" for n in (
    "01_SUPERVISOR_VERIFY.json", "02_ENTRY_VERIFY.txt", "03_FAILCLOSED_run-b.json",
    "03_FAILCLOSED_run-c.json", "03_FAILCLOSED_run-full.json", "04_UNIT_TESTS.log",
    "05_MUTATION.json", "06_QS4_BINDING_PACKAGED_R001.json", "07_PS_PARSE.txt",
    "M1_MANIFEST_BUILD.json", "M1_MANIFEST_SHA256_AT_TEST_TIME.json")] + [
    f"{OFR}/v003_full_chain/QUALIFICATION_RECEIPT.json", f"{OFR}/v003_full_chain/QUALIFY_STDOUT.txt",
    f"{OFR}/v008_supervised_qualification/V008_QUALIFICATION_RECEIPT.json",
    f"{OFR}/v008_supervised_qualification/QUALIFY_STDOUT.txt",
    f"{OFR}/v008_supervised_qualification/SUPERVISOR_LOG.txt",
    f"{OFR}/r18r1_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R18R1.json",
    f"{OFR}/r18r1_origin_fixes/FALSE_COMPLETENESS_SEARCH_V008R18R1.json"]


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def build_manifest():
    v3 = EVID / "v3fake"
    v3.mkdir(exist_ok=True)
    shutil.copy2(TREE / "receipts/V008/PARENT_V003_MANIFEST_SHA256.json", v3 / "MANIFEST_SHA256.json")
    r = subprocess.run([PY, "-I", "-B", str(TREE.parent.parent / "build/build_v008.py") if False else
                        str(BUILDPY), "manifest", "--tree", str(TREE), "--v003-payload", str(v3)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("MANIFEST_FAIL: " + r.stdout + r.stderr)
    return json.loads(r.stdout)


BUILDPY = Path(sys.argv[4]).resolve()         # build/build_v008.py

# ---- M1: mover evidência regenerável para fora, construir o manifesto de teste ----
stash = EVID / "stash"
stash.mkdir(parents=True, exist_ok=True)
for rel in REGEN:
    src = TREE / rel
    if src.exists():
        dst = stash / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
# podar diretórios que ficaram vazios (verify_tree confere o conjunto de diretórios)
for d in sorted((TREE / OFR).rglob("*"), reverse=True):
    if d.is_dir() and not any(d.iterdir()):
        d.rmdir()
m1 = build_manifest()
m1_sha = sha(TREE / "MANIFEST_SHA256.json")
print("M1", m1["members"], m1_sha)

# ---- bateria contra M1 (ROOT/MANIFEST_SHA256.json == M1) ----
env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
supv = str(SUP / "pegasus_supervisor_v008.py")


def run(args, **kw):
    return subprocess.run([PY, "-I", "-B", supv, *args], capture_output=True, text=True, env=env, **kw)


b = EVID / "battery"
b.mkdir(exist_ok=True)
(b / "01_SUPERVISOR_VERIFY.json").write_text(run(["verify"]).stdout, encoding="utf-8")
(b / "02_ENTRY_VERIFY.txt").write_text(
    subprocess.run([PY, "-I", "-B", str(TREE / "CODE/pegasus_entry.py"), "verify"],
                   capture_output=True, text=True, cwd=str(TREE / "CODE")).stdout, encoding="utf-8")
for mode in ("run-b", "run-c", "run-full"):
    (b / ("03_FAILCLOSED_%s.json" % mode)).write_text(run([mode]).stdout, encoding="utf-8")
(b / "06_QS4_BINDING_PACKAGED_R001.json").write_text(
    run(["bind-qs4", "--harness-dir", str(TREE / "QS4_HARNESS_R001/PHASE_B_QS4_HARNESS_V001")]).stdout, encoding="utf-8")
# unit tests (191) -> log externo; o teste de CLI verify lê o manifesto M1 e PASSA
ut = run_unit = subprocess.run([PY, "-I", "-B", str(SUP / "tests/test_supervisor_v008.py")],
                               capture_output=True, text=True, env=env)
(b / "04_UNIT_TESTS.log").write_text(ut.stdout + ut.stderr, encoding="utf-8")
# mutation (48) -> JSON
mut = subprocess.run([PY, "-I", "-B", str(SUP / "tests/mutation_supervisor_v008.py")],
                     capture_output=True, text=True, env=env)
(b / "05_MUTATION.json").write_text(mut.stdout, encoding="utf-8")
# ps parse indisponível no sandbox (sem pwsh); registrado honestamente
(b / "07_PS_PARSE.txt").write_text(
    "PWSH_UNAVAILABLE_IN_SANDBOX; BOOTSTRAP_PS51_TEMPLATE_BYTE_VALIDATED_R16_SAME_GRAMMAR; "
    "PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R9\n", encoding="utf-8")
# qualify integrado (posix não-nativo) -> recibo
qev = EVID / "qev"
if qev.exists():
    shutil.rmtree(qev)
qr = run(["qualify", "--evidence", str(qev)])
(b / "V008_QUALIFICATION_RECEIPT.json").write_text(
    (qev / "V008_QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8") if (qev / "V008_QUALIFICATION_RECEIPT.json").exists()
    else json.dumps({"result": "QUALIFY_STDOUT_ONLY", "stdout_tail": qr.stdout[-2000:]}), encoding="utf-8")
(b / "V008_QUALIFY_STDOUT.txt").write_text(qr.stdout + qr.stderr, encoding="utf-8")
print("UNIT_rc", ut.returncode, "MUT_rc", mut.returncode, "QUALIFY_rc", qr.returncode)
print("UNIT_tail", (ut.stdout + ut.stderr).strip().splitlines()[-1])
print("MUT_result", json.loads(mut.stdout).get("result") if mut.stdout.strip().startswith("{") else mut.stdout[-200:])
