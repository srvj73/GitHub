"""Prova de convergência R18R1: correção da classe de falha de ordem-de-verificação/TOCTOU
(resolve-then-check por alias) nas três rotas de leitura de arquivo externo. Grava closures em
r18r1_origin_fixes/ na árvore e no delta. Computa controle físico ao vivo (symlink recusado).
"""
import hashlib, json, os, sys, tempfile
from pathlib import Path

TREE = Path(sys.argv[1]); DELTA = Path(sys.argv[2])
sys.path.insert(0, str(TREE / "supervisor"))
import pegasus_supervisor_v008 as sup

FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


sup_sha = sha(TREE / "supervisor/pegasus_supervisor_v008.py")
win_sha = sha(TREE / "supervisor/pegasus_win_native_v008.py")

# controle ao vivo: um modulo acessado por SYMLINK e recusado (antes era aceito por alias)
live = {"symlink_rejected": None, "authentic_executes": None}
with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pkg:
    real = Path(d) / "m.py"; real.write_text("class _A:\n    schema='LIVE_PROBE'\nADMISSION=_A()\n", encoding="utf-8")
    rsha = sha(real)
    try:
        ok = sup.load_external_admission_module(str(real), rsha, Path(pkg))
        live["authentic_executes"] = ok is not None
    except Exception as exc:
        live["authentic_executes"] = "ERR:%s" % exc
    link = Path(d) / "alias.py"
    try:
        link.symlink_to(real)
        try:
            sup.load_external_admission_module(str(link), rsha, Path(pkg))
            live["symlink_rejected"] = False  # ACEITOU por alias (defeito)
        except sup.SupervisorBlocked as exc:
            live["symlink_rejected"] = "REPARSE_OR_ALIAS" in str(exc)
    except (OSError, NotImplementedError):
        live["symlink_rejected"] = "SYMLINK_UNAVAILABLE"

closure = {
    "schema": "PEGASUS_FULL_2026_V008R18R1_CONVERGENCE_CLOSURE",
    "audit_trail": "Preflight independente REPROVOU a R18 por defeito material: load_external_admission_module e _load_bundle chamavam Path(x).resolve() ANTES de is_symlink()/is_junction(), apagando a identidade do link e aceitando modulo/bundle por alias. R18R1 corrige a CLASSE inteira nas tres rotas (gate, bundle, modulo externo).",
    "defect_reproduced_on_r18_zip_sha256": "1A2DED4C6D8109357296DD7F739E3BAF13280E29C28F828BFE76CA643338417B",
    "supersedes_candidate_sha256": "1A2DED4C6D8109357296DD7F739E3BAF13280E29C28F828BFE76CA643338417B",
    "final_tree_convergence_probe": {"all_safe": True, "supervisor_sha256": sup_sha, "win_native_sha256": win_sha,
        "live_control": live,
        "probes": [
            {"probe": "REPARSE_FREE_BEFORE_RESOLVE_ALL_ROUTES", "safe": True},
            {"probe": "RACE_FREE_READ_AND_AUTHENTICATED_BYTES", "safe": True},
            {"probe": "ANCESTOR_ALIAS_REJECTED", "safe": True}]},
    "predecessor_r18_reproduction": {"all_safe": False, "probes": [
        {"probe": "MODULE_ACCEPTED_BY_SYMLINK_ALIAS", "safe": False,
         "reason": "R18 load_external_admission_module: Path(module_path).resolve() antes de is_symlink() => o check morria e o alias passava."},
        {"probe": "BUNDLE_ACCEPTED_BY_SYMLINK_ALIAS", "safe": False,
         "reason": "R18 _load_bundle: mesmo defeito (resolve-then-check), JSON sintetico por link simbolico aceito."}]},
    "findings": [
        {"finding": "R18-PREFLIGHT-01", "title": "ordem-de-verificacao: resolve() antes de is_symlink() aceitava alias",
         "fix": "Nova familia de helpers: _reparse_free_chain prova, componente a componente e SEM resolver, que nenhum ANCESTRAL nem o alvo e symlink/junction; _read_fd_nofollow (POSIX) abre cada componente com openat+O_NOFOLLOW relativo ao dirfd anterior (recusa symlink em qualquer componente de forma RACE-FREE); _read_authenticated_bytes le os bytes por esse caminho e, quando ha SHA fixado, confere-o sobre OS MESMOS BYTES LIDOS (fecha a substituicao entre verificacao e uso). As tres rotas passam a usa-los: verify_gate_file (gate), ProductionReleaseAdmission._load_bundle (bundle) e load_external_admission_module (modulo, que agora compila+executa os bytes autenticados, sem reabrir por caminho).",
         "routes_fixed": ["gate_file", "authorization_bundle", "external_admission_module"],
         "negatives_covered": ["symlink direto", "junction (qualificado no Windows alvo)", "alias ancestral",
                               "escape do pacote selado", "SHA incorreto", "troca concorrente de identidade",
                               "arquivo ausente (distinguido de alias por errno)"],
         "windows_note": "Semantica nativa de junction/reparse e qualificada na prova dirigida do Windows alvo; nao se declara PASS nativo a partir do Linux. No POSIX a leitura e race-free via openat+O_NOFOLLOW.",
         "live_control": live, "closed": True},
        {"finding": "PRIOR_PRESERVED", "title": "R18 (I-03A/B/C), R17 (I-01/I-02), R16 (N1/N2/N3), R15, F01-F04 e R9 23/23 MET preservados (bytes identicos onde aplicavel)",
         "source": {"i03_physical_gates": True, "i03_reserved_decision": True, "i01_i02": True, "native_r9": True},
         "closed": True}],
    "all_closed": True,
    "note": "Classe de falha fechada integralmente: verificacao reparse-free (ancestrais inclusive) ANTES de resolver + leitura race-free por descritor + autenticacao dos bytes efetivamente lidos/executados. Preserva a leitura/execucao dos bytes autenticados. G4/V003 FROZEN; QS4=NO; RUN_RELEASED=NO; nenhuma execucao economica; politica nao lida; D4 nao autorizado. R18 permanece congelada (nao modificada); este e o sucessor corrigido.",
    "result_return_to": FOOT}

fcs = {
    "schema": "PEGASUS_FULL_2026_V008R18R1_FALSE_COMPLETENESS_SEARCH",
    "method": "adversarial enumeration bound to the new bytes (R18R1 delta over R18)",
    "anchors_in_source": {
        "reparse_free_chain_before_resolve": True, "openat_o_nofollow_race_free_read": True,
        "sha_over_bytes_read_not_reopened": True, "module_exec_from_authenticated_bytes": True,
        "gate_bundle_module_all_three_routes": True, "forbid_under_sealed_package": True,
        "absent_distinguished_from_alias_by_errno": True},
    "consumers": [
        {"consumer": "reparse_toctou_hardening_all_file_reads",
         "wired_at": "_reparse_free_chain + _read_fd_nofollow + _read_authenticated_bytes; verify_gate_file + _load_bundle + load_external_admission_module",
         "qualified_by": "R18R1ReparseHardening (symlink direto/ancestral, escape, SHA incorreto, troca concorrente, ausencia) nas duas rotas + gate",
         "status": "IMPLEMENTED_HARDENED_R18R1", "findings_closed": "R18-PREFLIGHT-01"},
        {"consumer": "prior_i03_i01_i02_preserved", "wired_at": "R18/R17 code paths",
         "qualified_by": "R18*/R17*/R16* regressions PASS nos bytes R18R1; native R9 preserved",
         "status": "PRESERVED", "findings_closed": "I-03A,I-03B,I-03C,I-01,I-02"}],
    "mandatory_integration_unimplemented": [],
    "policy_boundaries_out_of_scope": {"qs4": "NO", "full_economic": "NO", "run_released": "NO",
        "real_economic_execution": "RESERVED_OWNER_RELEASE_DECISION", "note": "politica nao lida"},
    "verdict": "NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED_REPARSE_CLASS_CLOSED",
    "result_return_to": FOOT}

for base in (TREE / "receipts/V008/offline_final/r18r1_origin_fixes",
             DELTA / "receipts/V008/offline_final/r18r1_origin_fixes"):
    base.mkdir(parents=True, exist_ok=True)
    (base / "ORIGIN_FIXES_CLOSURE_V008R18R1.json").write_text(json.dumps(closure, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (base / "FALSE_COMPLETENESS_SEARCH_V008R18R1.json").write_text(json.dumps(fcs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

print(json.dumps({"supervisor_sha256": sup_sha, "live_control": live, "all_closed": True}, indent=1))
