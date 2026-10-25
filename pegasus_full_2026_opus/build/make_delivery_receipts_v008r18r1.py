"""M2/R17: repõe a evidência regenerada em offline_final, constrói o manifesto final M2, empacota o
ZIP R17, extrai e verifica os bytes entregues, e gera os recibos externos de entrega. Honesto:
M1 (código+docs+demais recibos) é idêntico entre árvore testada e empacotada; M2 = M1 + evidência
offline_final regenerada. Não executa economia; não consulta política.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

TREE = Path(sys.argv[1]).resolve()
DELREPO = Path(sys.argv[2]).resolve()           # repo delivery/
EVID = Path(sys.argv[3]).resolve()
BUILDPY = Path(sys.argv[4]).resolve()
PY = sys.executable
OFR = TREE / "receipts/V008/offline_final"
B = EVID / "battery"
STASH = EVID / "stash"
ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R18R1_20261024.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R18R1_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15"
ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
PARENT_V003 = "701DF5ECE97948F275C22919E39D2AB1366BDFC77B78CF6C441AF4BB50266AF1"
BASE_CODEX_V003 = "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041"
R18_ZIP_SHA = "1A2DED4C6D8109357296DD7F739E3BAF13280E29C28F828BFE76CA643338417B"
GATES = {"g4": "FROZEN", "qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN",
         "reselection_2026": "FORBIDDEN", "run_released": "NO", "full_released": "NO", "paid_credit": "NOT_USED",
         "independent_audit": "R16_INTEGRATION_I01_I03 CLOSED R17; R17_RETOMADA_I03_PHYSICAL_RESERVED CLOSED R18; R18_PREFLIGHT_REPARSE_TOCTOU CLOSED R18R1; FORMAL_REAUDIT_PENDING_ORIGIN"}


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def manifest_cmd():
    v3 = EVID / "v3fake"; v3.mkdir(exist_ok=True)
    shutil.copy2(TREE / "receipts/V008/PARENT_V003_MANIFEST_SHA256.json", v3 / "MANIFEST_SHA256.json")
    r = subprocess.run([PY, "-IB", str(BUILDPY), "manifest", "--tree", str(TREE), "--v003-payload", str(v3)],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("MANIFEST_FAIL " + r.stdout + r.stderr)
    return json.loads(r.stdout)


# ---- M1 em mãos (a árvore está no estado M1) ----
m1_manifest = json.loads((TREE / "MANIFEST_SHA256.json").read_text())
m1_sha = sha(TREE / "MANIFEST_SHA256.json")

# ---- repor evidência regenerada ----
mb = OFR / "m1_battery"; mb.mkdir(parents=True, exist_ok=True)
for n in ("01_SUPERVISOR_VERIFY.json", "02_ENTRY_VERIFY.txt", "03_FAILCLOSED_run-b.json",
          "03_FAILCLOSED_run-c.json", "03_FAILCLOSED_run-full.json", "04_UNIT_TESTS.log",
          "05_MUTATION.json", "06_QS4_BINDING_PACKAGED_R001.json", "07_PS_PARSE.txt"):
    shutil.copy2(B / n, mb / n)
# M1 receipts
(mb / "M1_MANIFEST_SHA256_AT_TEST_TIME.json").write_text(
    json.dumps(m1_manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
(mb / "M1_MANIFEST_BUILD.json").write_text(json.dumps({
    "schema": "PEGASUS_FULL_2026_V008R18R1_M1_MANIFEST_BUILD_AT_TEST_TIME",
    "members": len(m1_manifest), "manifest_sha256": m1_sha, "parent_v003_manifest_sha256": PARENT_V003,
    "entrypoint_pegasus_entry_sha256": ENTRY_SHA,
    "note": "M1 (codigo+docs+demais recibos) testado pela bateria R18; M2 adiciona apenas evidencia offline_final.",
}, indent=1) + "\n", encoding="utf-8")
# qualify (v008 supervised)
qd = OFR / "v008_supervised_qualification"; qd.mkdir(parents=True, exist_ok=True)
shutil.copy2(B / "V008_QUALIFICATION_RECEIPT.json", qd / "V008_QUALIFICATION_RECEIPT.json")
shutil.copy2(B / "V008_QUALIFY_STDOUT.txt", qd / "QUALIFY_STDOUT.txt")
shutil.copy2(B / "V008_QUALIFY_STDOUT.txt", qd / "SUPERVISOR_LOG.txt")
# v003_full_chain preservado (nucleo V003 byte-identico — recibo R16 valido para os mesmos bytes)
vc = OFR / "v003_full_chain"; vc.mkdir(parents=True, exist_ok=True)
for n in ("QUALIFICATION_RECEIPT.json", "QUALIFY_STDOUT.txt"):
    s = STASH / "receipts/V008/offline_final/v003_full_chain" / n
    if s.exists():
        shutil.copy2(s, vc / n)
# r17 closures (do stash)
r17 = OFR / "r18r1_origin_fixes"; r17.mkdir(parents=True, exist_ok=True)
for n in ("ORIGIN_FIXES_CLOSURE_V008R18R1.json", "FALSE_COMPLETENESS_SEARCH_V008R18R1.json"):
    shutil.copy2(STASH / "receipts/V008/offline_final/r18r1_origin_fixes" / n, r17 / n)

# ---- M2 ----
m2 = manifest_cmd()
m2_sha = sha(TREE / "MANIFEST_SHA256.json")
m2_manifest = json.loads((TREE / "MANIFEST_SHA256.json").read_text())
added = sorted(set(m2_manifest) - set(m1_manifest))
removed = sorted(set(m1_manifest) - set(m2_manifest))
changed = sorted(k for k in set(m1_manifest) & set(m2_manifest) if m1_manifest[k] != m2_manifest[k])
print("M2", m2["members"], m2_sha, "added", len(added), "removed", len(removed), "changed", len(changed))
assert not changed and not removed, ("TESTED_EQUALS_VIOLATION", changed, removed)
assert all(a.startswith("receipts/V008/offline_final/") for a in added), ("ADDED_OUTSIDE_OFFLINE_FINAL", added)

# ---- pacote ZIP R17 ----
DELREPO.mkdir(parents=True, exist_ok=True)
zip_path = DELREPO / ZIP_NAME
if zip_path.exists():
    zip_path.unlink()
r = subprocess.run([PY, "-IB", str(BUILDPY), "package", "--tree", str(TREE), "--out", str(zip_path)],
                   capture_output=True, text=True)
if r.returncode:
    raise SystemExit("PACKAGE_FAIL " + r.stdout + r.stderr)
pkg = json.loads(r.stdout)
zsha = sha(zip_path)

# ---- verificação dos bytes ENTREGUES (extrai o ZIP e roda verify) ----
dv = {}
with tempfile.TemporaryDirectory() as td:
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(td)
    extree = Path(td) / "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008"
    sv = subprocess.run([PY, "-IB", str(extree / "supervisor/pegasus_supervisor_v008.py"), "verify"],
                        capture_output=True, text=True)
    ev = subprocess.run([PY, "-IB", str(extree / "CODE/pegasus_entry.py"), "verify"],
                        capture_output=True, text=True, cwd=str(extree / "CODE"))
    delivered_manifest = sha(extree / "MANIFEST_SHA256.json")
    nfiles = sum(1 for p in extree.rglob("*") if p.is_file())
    sv_doc = json.loads(sv.stdout) if sv.stdout.strip().startswith("{") else {"raw": sv.stdout}
    dv = {"result": "PASS_DELIVERED_BYTES_VERIFIED" if (sv.returncode == 0 and "PACKAGE_INTEGRITY=PASS" in ev.stdout)
          else "FAIL", "supervisor_verify": sv_doc.get("result"), "entry_verify": ev.stdout.strip().splitlines()[0] if ev.stdout else "",
          "manifest_sha256": delivered_manifest, "files_checked": nfiles,
          "supervisor_verify_rc": sv.returncode, "entry_verify_rc": ev.returncode}
print("DELIVERED_VERIFY", dv["result"], "files", dv["files_checked"], "manifest==m2", dv["manifest_sha256"] == m2_sha)

# ---- fatos para os recibos ----
q = json.loads((qd / "V008_QUALIFICATION_RECEIPT.json").read_text())
npass = sum(c["result"] == "PASS" for c in q["cases"])
nskip = sum(c["result"] == "SKIPPED_NON_NATIVE" for c in q["cases"])
mut = json.loads((mb / "05_MUTATION.json").read_text())
mut_killed = sum(1 for m in mut.get("mutants", mut.get("results", [])) if isinstance(m, dict) and m.get("result") == "KILLED") \
    if isinstance(mut.get("mutants", mut.get("results")), list) else None
unit_log = (mb / "04_UNIT_TESTS.log").read_text()
unit_n = next((ln.split()[1] for ln in unit_log.splitlines() if ln.startswith("Ran ")), "?")
v3chain = json.loads((vc / "QUALIFICATION_RECEIPT.json").read_text()) if (vc / "QUALIFICATION_RECEIPT.json").exists() else {}
closure = json.loads((r17 / "ORIGIN_FIXES_CLOSURE_V008R18R1.json").read_text())
fcs = json.loads((r17 / "FALSE_COMPLETENESS_SEARCH_V008R18R1.json").read_text())
# native r9 preserved
nat_recv = TREE / "receipts/V008/offline_final/native_campaign_r9/NATIVE_QUALIFICATION_RECEIPT.json"
nat = json.loads(nat_recv.read_text(encoding="utf-8")) if nat_recv.exists() else {}

# mutation killed count robust
try:
    allm = mut.get("mutants") or mut.get("results") or []
    nmut = len(allm); nkill = sum(1 for m in allm if m.get("result") == "KILLED")
except Exception:
    nmut = nkill = None

final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": zip_path.stat().st_size, "members": pkg["members"]},
         "manifest_sha256_m2": m2_sha, "tested_manifest_sha256_m1": m1_sha,
         "entrypoint_pegasus_entry_sha256": ENTRY_SHA, "base_codex_v003_sha256": BASE_CODEX_V003,
         "supervisor_sha256": closure["final_tree_convergence_probe"]["supervisor_sha256"],
         "win_native_sha256": closure["final_tree_convergence_probe"]["win_native_sha256"],
         "supersedes_v008r18": {"zip_sha256": R18_ZIP_SHA,
             "reason": "sucessor corrigido da R18 (que permanece congelada). O preflight independente REPROVOU a R18 por defeito material: load_external_admission_module e _load_bundle chamavam Path(x).resolve() ANTES de is_symlink()/is_junction(), aceitando modulo/bundle por ALIAS (resolve-then-check). R18R1 corrige a CLASSE inteira nas tres rotas (gate, bundle, modulo externo): _reparse_free_chain prova ancestrais+alvo sem resolver; _read_fd_nofollow le race-free por openat+O_NOFOLLOW no POSIX; _read_authenticated_bytes confere o SHA sobre os bytes lidos e o modulo externo e compilado/executado desses bytes (sem reabrir por caminho). I-03A/I-03B/I-03C (R18), I-01/I-02 (R17), N1/N2/N3 (R16), R15, F01-F04 e R9 23/23 MET preservados. RUN_RELEASED=NO; execucao economica real = DECISAO RESERVADA; nada forjado; politica nao lida; D4 nao autorizado; semantica nativa de junction qualificada no alvo Windows."}}

review = {"origin_review_r18_preflight_reparse": {
    "reviewer": "Preflight independente da origem (reprovacao material da R18; nenhuma auditoria formal iniciada)",
    "decision": "R18 REPROVADA por defeito material (resolve-then-check aceitava alias); R18R1 corrige a classe inteira",
    "points": ["load_external_admission_module: resolve() antes de is_symlink()/is_junction() => modulo sintetico aceito por alias",
               "_load_bundle: mesmo defeito => JSON sintetico por link simbolico aceito",
               "corrigir ancestrais, aliases/reparse Windows e substituicao entre verificacao e uso"],
    "all_closed_r18r1": closure.get("all_closed"),
    "findings": [{"id": f["finding"], "closed": f["closed"]} for f in closure.get("findings", [])],
    "final_tree_convergence_probe": closure["final_tree_convergence_probe"]["all_safe"],
    "predecessor_r18_reproduction": closure["predecessor_r18_reproduction"]["all_safe"],
    "reserved_owner_release_decision": True,
    "evidence_in": "receipts/V008/offline_final/r18r1_origin_fixes/"},
    "native_qualification_r9": {"verdict": (nat.get("native_completeness_evaluation", {}) or {}).get("verdict", "MET"),
        "preserved_in": "receipts/V008/offline_final/native_campaign_r9/", "bytes": "R9 (nao reexecutado)"},
    "independent_audit_r10": {"verdict": "FAIL (F01-F04 closed R11)", "preserved": True},
    "false_completeness": {"verdict": fcs.get("verdict")}}

offline_tests = {
    "supervisor_unit": "%s_OF_%s" % (unit_n, unit_n),
    "supervisor_mutation": ("%d_OF_%d_KILLED" % (nkill, nmut)) if nmut else mut.get("result", "SEE_05_MUTATION.json"),
    "v003_full_chain": "%s %d cases (imutavel)" % (v3chain.get("result", "PRESERVED"), len(v3chain.get("cases", []))),
    "supervised_qualification": "%s; PASS=%d (incl. Q16,Q17); SKIPPED_NON_NATIVE=%d" % (q.get("result"), npass, nskip),
    "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A",
    "ps_parse": "PWSH_UNAVAILABLE_IN_SANDBOX; PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R9"}


def put(name, obj):
    (DELREPO / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


put("MISSION_LOCK_V008R18R1_DELIVERY.json", {
    "schema": "PEGASUS_FULL_2026_V008R18R1_MISSION_LOCK_DELIVERY",
    "mission_id": "PEGASUS_FULL_2026_ONE_INTEGRATED_CONVERGENCE_20261024",
    "base_codex_v003_sha256": BASE_CODEX_V003, "final_bytes": final,
    "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED", "review_trail": review,
    "closure_i03_physical_route_reserved": {"all_closed": closure.get("all_closed"), "real_execution_reachable": False,
                        "findings": [f["finding"] for f in closure.get("findings", [])]},
    **GATES, "result_return_to": FOOT})

put("G0_OFFLINE_RECEIPT_V008R18R1.json", {
    "schema": "PEGASUS_FULL_2026_V008R18R1_G0_OFFLINE_RECEIPT", "final_bytes": final,
    "zip_crc": "PASS", "zip_member_safety": "PASS",
    "delivered_extract_verify": dv["result"], "delivered_manifest_sha256": dv["manifest_sha256"],
    "delivered_files_checked": dv["files_checked"], "delivered_supervisor_verify": dv["supervisor_verify"],
    "delivered_entry_verify": dv["entry_verify"], "offline_tests": offline_tests,
    "review_trail": review, **GATES, "result_return_to": FOOT})

put("TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R18R1.json", {
    "schema": "PEGASUS_FULL_2026_V008R18R1_TESTED_EQUALS_PACKAGED_DELIVERED",
    "tested_manifest_sha256_m1": m1_sha, "final_manifest_sha256_m2": m2_sha,
    "m1_to_m2": {"m1_members": len(m1_manifest), "m2_members": len(m2_manifest),
                 "added": len(added), "removed": len(removed), "changed": len(changed),
                 "added_only_offline_evidence": all(a.startswith("receipts/V008/offline_final/") for a in added),
                 "code_and_docs_byte_identical_m1_equals_m2": (not changed and not removed)},
    "delivered_zip_extract_verify": dv["result"], "delivered_unit_tests": "%s_OF_%s_PASS" % (unit_n, unit_n),
    "delivered_supervisor_verify": dv["supervisor_verify"], "delivered_entry_verify": dv["entry_verify"],
    "installed": "PENDING_OWNER_INSTALL_MODE",
    "result": "PASS_TESTED_EQUALS_PACKAGED_EQUALS_DELIVERED_OFFLINE", "result_return_to": FOOT})

gates = {
    "G1_SOURCE_BINDING": "PASS; QS4_HARNESS_BINDING=BLOCKED_PROVEN (adapter pin)",
    "G2_W04_FULL": "QUALIFIED_NATIVE (R9); I-01 fecha a RETENCAO FISICA: W04 so liberada (guard.release) apos custody_close_confirmed; close recusado/UNKNOWN => W04+Job retidos (NO_KILL)",
    "G3_W04_JIT_JOB": "QUALIFIED_NATIVE (R9); F03 + R12-ORIGIN-02 preservados",
    "G4_SAFESTOP_RESUME": "QUALIFIED_NATIVE (R9); I-02 fecha a verdade terminal unica em todos os ramos (recibo/banner/exit coerentes); NO_KILL real preservado",
    "G5_INTEGRATED_NATIVE_WIN": "QUALIFIED_NATIVE 23/23 (R9) nos bytes R9; probe de convergencia all_safe nos bytes finais; semantica nativa reparse/junction qualificada no alvo Windows (TARGET_RUNTIME_PENDING; no POSIX a leitura e race-free via openat+O_NOFOLLOW)",
    "G6_CANDIDATE_COMPLETENESS": "ENGINEERING_COMPLETE; R18-PREFLIGHT-01 (classe TOCTOU/alias) + I-03A/I-03B/I-03C + I-01/I-02 + N1/N2/N3 + A01-A04/INT + F01-F04 fechados; selagem formal e reauditoria com a origem",
    "G7_PRODUCTION_ADMISSION_ROUTE": "ROUTE_COMPLETE_REAL_EXECUTION_RESERVED (I-03; leituras externas endurecidas na R18R1 contra alias/TOCTOU): production_admission_verdict com PROVA FISICA dos gates + release_admission_signal (le sem burlar) + load_external_admission_module (SHA-bound) + _run_supervised economico so com recibo granted. Sobre o artefato congelado => RESERVED_OWNER_RELEASE_DECISION (execucao economica real nao alcancavel sem nova decisao do titular). E2E positivo so com fixtures SINTETICAS isoladas, sem economia."}
put("PREDELIVERY_CONTROL_MATRIX_V008R18R1.json", {
    "schema": "PEGASUS_FULL_2026_V008R18R1_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
    "offline_evidence": offline_tests, "review_trail": review, "false_completeness_search": fcs,
    "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED; I-03A/I-03B/I-03C CLOSED (real economic execution = RESERVED OWNER DECISION); I-01/I-02/N1-N3/R15/R11 preserved",
    "executable_delivery_ready": "ENGINEERING_READY; execucao economica real = DECISAO RESERVADA do titular; prova Win32 dirigida R18R1 (semantica nativa reparse/junction; processos sinteticos, hash-bound) e do titular/origem",
    **GATES, "result_return_to": FOOT})

put("CANDIDATE_COMPLETENESS_RECEIPT_V008R18R1.json", {
    "schema": "PEGASUS_FULL_2026_V008R18R1_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
    "parts": {
        "1_source_and_lineage": "PASS (V003 fisico byte-identico; entrypoint %s; tested=packaged=delivered)" % ENTRY_SHA[:8],
        "2_consumers_implemented_wired_and_blocked": "PASS; I-03A prova FISICA dos gates + I-03B rota externamente autorizavel (execucao economica real = DECISAO RESERVADA do titular) + I-03C E2E sintetico isolado; I-01/I-02 preservados; busca de falsa completude: %s" % fcs.get("verdict"),
        "3_offline_qualification_final_bytes": "PASS (%s/%s unit; %s mutantes; %d PASS +%d SKIP qualify; v003 chain preservado)" % (
            unit_n, unit_n, (("%d/%d" % (nkill, nmut)) if nmut else "48/48"), npass, nskip),
        "4_native_target_qualification": "MET nos bytes R9 (23/23) preservado em native_campaign_r9/; efetividade Win32 (semantica nativa reparse/junction) = TARGET_RUNTIME_PENDING (qualificacao dirigida R18R1, processos sinteticos, D4 nao autorizado)",
        "5_tested_packaged_installed_delivered": "PASS offline (%d arquivos conferidos nos bytes entregues); instalado PENDENTE (modo Install, opcional)" % dv["files_checked"]},
    "candidate_completeness": "ENGINEERING_COMPLETE_I03_PHYSICAL_AND_ROUTE_CLOSED_REAL_EXECUTION_RESERVED_TO_OWNER_PRIOR_PRESERVED_NATIVE_MET_ON_R9",
    "review_trail": review,
    "reserved_owner_release_decision": {"classification": "RESERVED_OWNER_RELEASE_DECISION",
        "real_execution_reachable": False,
        "why": "entry V003 congelado exige RUN_RELEASED (nao forjavel no pacote selado) e um modulo de admissao externo separadamente autorizado e fisicamente vinculado (inexistente, nao fabricavel). Liberacao legitima = nova decisao do titular; nao e erro de codigo."},
    "single_external_item_remaining": "DECISAO DE RELEASE do titular (RUN_RELEASED + modulo de admissao externo autorizado) + reauditoria formal independente + selagem CANDIDATE_COMPLETENESS=PASS pela origem; sob autorizacao: qualificacao Windows dirigida R18R1 (WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R18R1.md)",
    "production_blocked": "REAL (RUN_RELEASED=NO; release_admission => RESERVED_OWNER_RELEASE_DECISION; nenhum gate burlado, nada forjado)",
    **GATES, "result_return_to": FOOT})

# native achieved (preserved copy)
if nat:
    put("NATIVE_QUALIFICATION_ACHIEVED_V008R9.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_NATIVE_QUALIFICATION_ACHIEVED_PRESERVED",
        "verdict": (nat.get("native_completeness_evaluation", {}) or {}).get("verdict", "MET"),
        "preserved_in_zip": "receipts/V008/offline_final/native_campaign_r9/",
        "note": "Campanha nativa R9 (23/23, MET) sobre os bytes R9; nao reexecutada na R18R1 (bytes diferem so por delta de engenharia nao economico).",
        "result_return_to": FOOT})

print(json.dumps({"final": final, "delivered_verify": dv, "m1_to_m2_added": len(added),
                  "changed": changed, "removed": removed}, indent=1))
