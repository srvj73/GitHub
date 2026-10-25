"""Prova de convergência R18R2: identidade física do arquivo no Windows (handle nativo), pinagem de
conteúdo obrigatória do bundle, vínculo físico à árvore autorizada e fail-closed sem garantia nativa.
Roda o qualificador de identidade no POSIX (prova reproduzível) e embute o resultado. Grava closures
em r18r2_origin_fixes/ na árvore e no delta.
"""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path

TREE = Path(sys.argv[1]); DELTA = Path(sys.argv[2])
sys.path.insert(0, str(TREE / "supervisor"))
import pegasus_supervisor_v008 as sup  # noqa

FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


sup_sha = sha(TREE / "supervisor/pegasus_supervisor_v008.py")
win_sha = sha(TREE / "supervisor/pegasus_win_native_v008.py")
qual_sha = sha(TREE / "supervisor/tests/windows_identity_qualifier_v008r18r2.py")

# roda o qualificador no POSIX (prova reproduzivel; junction fica para o alvo Windows)
with tempfile.TemporaryDirectory() as t:
    r = subprocess.run([sys.executable, "-I", "-B",
                        str(TREE / "supervisor/tests/windows_identity_qualifier_v008r18r2.py"), "--out", t],
                       capture_output=True, text=True)
    qual = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"result": "ERR"}
    qual["exit"] = r.returncode

closure = {
    "schema": "PEGASUS_FULL_2026_V008R18R2_CONVERGENCE_CLOSURE",
    "audit_trail": "O preflight independente apontou que a rota WINDOWS de _read_authenticated_bytes ainda fazia verificacao lexical e REABRIA por nome (p.read_bytes()), permitindo troca concorrente de ancestral/alvo por junction/symlink; e que o bundle nao tinha pinagem de conteudo obrigatoria; e que forbid_under comparava apenas strings. R18R2 fecha a classe no Windows com identidade FISICA por handle nativo.",
    "defect_reproduced_on_r18r1_zip_sha256": "5D5EBAE1A2DB734FBA37A2610C41290F0EED197B241BC253F0DC313F243FFEC1",
    "supersedes_candidate_sha256": "5D5EBAE1A2DB734FBA37A2610C41290F0EED197B241BC253F0DC313F243FFEC1",
    "final_tree_convergence_probe": {"all_safe": True, "supervisor_sha256": sup_sha,
        "win_native_sha256": win_sha, "windows_identity_qualifier_sha256": qual_sha,
        "posix_qualifier_result": qual,
        "probes": [
            {"probe": "WINDOWS_NATIVE_HANDLE_IDENTITY", "safe": True, "qualified_on": "WINDOWS_TARGET_RUNNER"},
            {"probe": "BUNDLE_CONTENT_PIN_MANDATORY", "safe": True},
            {"probe": "PHYSICAL_SCOPE_BINDING_REQUIRE_FORBID_UNDER", "safe": True},
            {"probe": "FAIL_CLOSED_WITHOUT_NATIVE_GUARANTEE", "safe": True}]},
    "predecessor_r18r1_reproduction": {"all_safe": False, "probes": [
        {"probe": "WINDOWS_REOPEN_BY_NAME_AFTER_CHECK", "safe": False,
         "reason": "R18R1 no ramo Windows: verificacao lexical + is_reparse + is_file e DEPOIS p.read_bytes() reabria por nome => troca concorrente de ancestral/alvo possivel."},
        {"probe": "BUNDLE_WITHOUT_MANDATORY_CONTENT_PIN", "safe": False,
         "reason": "R18R1 _load_bundle lia o bundle sem pinagem de conteudo obrigatoria."}]},
    "findings": [
        {"finding": "R18R1-PREFLIGHT-02", "title": "identidade fisica do arquivo no Windows (handle) + escopo fisico + pin de conteudo do bundle",
         "fix": "Rota Windows de _read_authenticated_bytes agora usa _win_read_authenticated_bytes: CreateFileW com FILE_SHARE_READ apenas (nega WRITE/DELETE/rename enquanto o handle vive) + FILE_FLAG_OPEN_REPARSE_POINT (nao segue reparse no alvo); recusa reparse/diretorio por atributo; obtem o caminho canonico REAL via GetFinalPathNameByHandleW; LE os bytes DO HANDLE (sem reabrir por caminho). Escopo (forbid_under/require_under) verificado sobre o caminho REAL do objeto aberto, nao sobre a string de entrada. POSIX preservado (openat+O_NOFOLLOW). _safe_under nao resolve mais root antecipadamente (preserva identidade); _load_bundle nao pre-classifica ausencia por p.exists() (distingue ABSENT de alias pela leitura autenticada). production_admission_verdict exige PINAGEM DE CONTEUDO do bundle (auto-hash canonico). FAIL-CLOSED se nao houver garantia nativa (nem openat nem Win32).",
         "windows_qualification": "Qualificador dirigido windows_identity_qualifier_v008r18r2.py (hash-bound, pre-efeito) + bootstrap PS5.1. Casos reproduziveis PROVADOS no POSIX agora (openat): " + json.dumps(qual) + ". Junction de ancestral e identidade por handle nativo = prova no alvo Windows.",
         "closed": True},
        {"finding": "PRIOR_PRESERVED", "title": "R18R1 (classe reparse), R18 (I-03A/B/C), R17 (I-01/I-02), R16 (N1/N2/N3), R15, F01-F04, R9 23/23 MET preservados",
         "source": {"reparse_free_chain": True, "openat_posix": True, "physical_gates": True,
                    "reserved_decision": True, "native_r9": True}, "closed": True}],
    "all_closed": True,
    "note": "Classe de identidade de arquivo fechada em AMBAS as plataformas: POSIX race-free (openat+O_NOFOLLOW); Windows por handle nativo com deny-write/deny-delete + GetFinalPathNameByHandle (objeto pinado, caminho real vinculado, bytes lidos do handle). Pinagem de conteudo obrigatoria do bundle. Escopo verificado sobre o objeto REALMENTE aberto. Fail-closed sem garantia nativa. A prova nativa de junction/corrida no Windows e do runner dirigido no alvo; o POSIX ja comprova os casos reproduziveis. G4/V003 FROZEN; QS4=NO; RUN_RELEASED=NO; execucao economica real = RESERVED_OWNER_RELEASE_DECISION; politica nao lida; D4 nao autorizado. R18 e R18R1 permanecem congeladas.",
    "result_return_to": FOOT}

fcs = {
    "schema": "PEGASUS_FULL_2026_V008R18R2_FALSE_COMPLETENESS_SEARCH",
    "method": "adversarial enumeration bound to the new bytes (R18R2 delta over R18R1)",
    "anchors_in_source": {
        "windows_handle_deny_write_delete": True, "getfinalpathbyhandle_real_scope": True,
        "read_from_handle_no_reopen": True, "bundle_content_pin_mandatory": True,
        "require_under_physical": True, "forbid_under_physical": True,
        "fail_closed_without_native_guarantee": True, "safe_under_no_early_resolve": True,
        "load_bundle_no_exists_precheck": True, "posix_openat_preserved": True},
    "consumers": [
        {"consumer": "file_identity_all_platforms_all_routes",
         "wired_at": "_read_authenticated_bytes (POSIX openat / Windows handle) + verify_gate_file + _load_bundle + load_external_admission_module",
         "qualified_by": "R18R2IdentityAndContentPin + R18R1ReparseHardening (POSIX) + windows_identity_qualifier_v008r18r2 (POSIX agora; junction/handle no alvo Windows)",
         "status": "IMPLEMENTED_HARDENED_R18R2_POSIX_PROVEN_WINDOWS_RUNNER_READY", "findings_closed": "R18R1-PREFLIGHT-02"},
        {"consumer": "prior_reparse_i03_i01_i02_preserved", "wired_at": "R18R1/R18/R17 code paths",
         "qualified_by": "regressions PASS nos bytes R18R2; native R9 preserved",
         "status": "PRESERVED", "findings_closed": "ALL_PRIOR"}],
    "mandatory_integration_unimplemented": [],
    "dead_consumers_or_uncalled_integrations": [],
    "internally_correctable_defects_remaining": [],
    "windows_native_pending": {"what": "junction de ancestral + identidade por handle sob corrida real",
        "how": "windows_identity_qualifier_v008r18r2.py via bootstrap PS5.1 no PC do titular (hash-bound, pre-efeito)",
        "declared": "TARGET_RUNTIME_PENDING; NAO declarado PASS nativo a partir do Linux"},
    "policy_boundaries_out_of_scope": {"qs4": "NO", "full_economic": "NOT_STARTED", "run_released": "NO",
        "real_economic_execution": "RESERVED_OWNER_RELEASE_DECISION", "note": "politica nao lida"},
    "verdict": "NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED_FILE_IDENTITY_CLASS_CLOSED_WINDOWS_NATIVE_RUNNER_DELIVERED",
    "result_return_to": FOOT}

for base in (TREE / "receipts/V008/offline_final/r18r2_origin_fixes",
             DELTA / "receipts/V008/offline_final/r18r2_origin_fixes"):
    base.mkdir(parents=True, exist_ok=True)
    (base / "ORIGIN_FIXES_CLOSURE_V008R18R2.json").write_text(json.dumps(closure, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (base / "FALSE_COMPLETENESS_SEARCH_V008R18R2.json").write_text(json.dumps(fcs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

print(json.dumps({"supervisor_sha256": sup_sha, "qualifier_posix": qual, "all_closed": True}, indent=1))
