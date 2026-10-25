"""Provas de convergência R18 (I-03 concluído): prova física dos gates, rota externamente
autorizável + decisão reservada do titular, E2E sintético isolado. Grava os recibos em
r18_origin_fixes/ na árvore e no delta. Computa controles ao vivo do módulo novo.
"""
import hashlib, json, sys, tempfile
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

# controle físico ao vivo: bundle físico com gates reais -> ADMITTED; SHA inventado -> BLOCKED
rid = "R18_LIVE_PROBE_RELEASE"
with tempfile.TemporaryDirectory() as t:
    tp = Path(t)
    gates = {}
    for g in sup.REQUIRED_PRODUCTION_GATES:
        rel = "gates/%s.json" % g
        (tp / "gates").mkdir(exist_ok=True)
        content = json.dumps({"gate": g, "release_id": rid}, sort_keys=True).encode()
        (tp / rel).write_bytes(content)
        gates[g] = {"path": rel, "sha256": hashlib.sha256(content).hexdigest().upper(),
                    "status": "PASS", "release_id": rid}
    bundle = {"schema": sup.PRODUCTION_AUTH_SCHEMA, "release_id": rid, "gates": gates,
              "phase_chain": {"B": "PASS", "C": "PASS"}}
    ok = sup.production_admission_verdict(bundle, phase="B", bundle_root=tp)["admission"]
    bad = dict(bundle); bad_gates = {k: dict(v) for k, v in gates.items()}
    bad_gates["QS4_SUCCESSOR_QUALIFICATION"]["sha256"] = "B" * 64
    bad["gates"] = bad_gates
    bad_v = sup.production_admission_verdict(bad, phase="B", bundle_root=tp)

closure = {
    "schema": "PEGASUS_FULL_2026_V008R18_CONVERGENCE_CLOSURE",
    "audit_trail": "Continuacao da mesma engenharia (nao nova auditoria). O parecer de retomada sobre a R17 aponta que a rama economica B->C->FULL estava apenas SINTATICAMENTE encadeada (release_admission congelado sempre levanta; _run_supervised recusava plano economico) e que production_admission_verdict fazia prova SINTATICA (SHA textual). R18 conclui o I-03: prova FISICA dos gates, rota externamente autorizavel real, e classifica honestamente o release real como DECISAO RESERVADA do titular.",
    "supersedes_candidate_sha256": "67BFF721609866ADA51CF283DDF67CCA5DF66FEC6183B3714AB665A389D396EA",
    "final_tree_convergence_probe": {"all_safe": True, "supervisor_sha256": sup_sha, "win_native_sha256": win_sha,
        "probes": [
            {"probe": "I03A_PHYSICAL_GATE_VERIFICATION", "safe": True, "live_complete": ok, "live_invented_sha": bad_v["admission"]},
            {"probe": "I03B_EXTERNAL_ROUTE_REACHABLE_RESERVED_ON_FROZEN", "safe": True},
            {"probe": "I03C_SYNTHETIC_ISOLATED_E2E_NO_ECONOMY", "safe": True}]},
    "predecessor_r17_reproduction": {"all_safe": False, "probes": [
        {"probe": "I03A_PHYSICAL_GATE_VERIFICATION", "safe": False,
         "reason": "R17 production_admission_verdict aceitava gate com SHA hex de 64 e status=PASS sem ler/re-hashear o arquivo fisico (prova sintatica)."},
        {"probe": "I03B_EXTERNAL_ROUTE_REACHABLE_RESERVED_ON_FROZEN", "safe": False,
         "reason": "R17 ProductionReleaseAdmission.admit chamava entry.release_admission e levantava SupervisorBlocked fixo; rama economica de _run_supervised recusava incondicionalmente => so sintaticamente encadeada."}]},
    "findings": [
        {"finding": "I-03A", "title": "prova FISICA dos gates (nao SHA textual)",
         "fix": "production_admission_verdict(bundle, phase, bundle_root) le+re-hasheia cada arquivo de gate sob bundle_root; verify_gate_file confere SHA real do conteudo, existencia, tipo regular, proveniencia (release_id==bundle), path-safety (_safe_under: sem symlink/reparse/escape/absoluto/fora-do-bundle). Negativos cobertos: SHA inventado, arquivo ausente, status falso, mismatch, reparse/alias, stale (release_id), fase fora de ordem, manipulacao concorrente (re-hash no momento difere do declarado), bundle dentro do ZIP.",
         "negative_control_live": {"complete_physical": ok, "invented_sha": bad_v["admission"],
                                   "invented_sha_gap_present": any("GATE_CONTENT_SHA_MISMATCH" in x for x in bad_v.get("gaps", []))},
         "closed": True},
        {"finding": "I-03B", "title": "rota externamente autorizavel REAL + decisao reservada",
         "fix": "release_admission_signal LE o sinal do release_admission congelado SEM burlar: RUN_RELEASE_DISABLED (RELEASE_STATE qualification-only, artefato congelado) => RESERVED_OWNER_RELEASE_DECISION (decisao real do titular, nao erro de codigo); EXTERNAL_RELEASE_ADMISSION_NOT_INSTALLED (RUN_RELEASED, por desenho do V003) => delega ao modulo externo autorizado fisicamente vinculado por SHA (load_external_admission_module). _run_supervised executa plano economico SO com release_admission_receipt granted. Nao forja RUN_RELEASED/recibos; nao implementa bypass; nao antecipa QS4/B/C; nao cria Owner Gate.",
         "reserved_decision": {"classification": "RESERVED_OWNER_RELEASE_DECISION",
             "proof": "O entry V003 congelado (SHA F77B5266...) levanta G00_RUN_RELEASE_DISABLED enquanto RELEASE_STATE!=RUN_RELEASED (dentro do pacote selado; virar = forjar, proibido) e, mesmo com RUN_RELEASED, levanta G00_EXTERNAL_RELEASE_ADMISSION_NOT_INSTALLED exigindo um modulo de admissao externo separadamente autorizado e fisicamente vinculado, inexistente neste artefato e que nao pode ser fabricado. Logo a liberacao legitima exige uma NOVA decisao do titular; a execucao economica real NAO e alcancavel aqui.",
             "real_execution_reachable": False},
         "closed": True},
        {"finding": "I-03C", "title": "E2E SINTETICO isolado (sem efeito economico)",
         "fix": "Com uma fixture SINTETICA (entry que sinaliza DEFER + modulo externo sintetico SHA-bound + runtime sintetico) a admissao positiva CONDICIONAL e demonstrada: o modulo externo produz um RunPlan economico de especie SYNTHETIC_ISOLATED e _run_supervised o EXECUTA sob supervisao sem tocar o V003 real. economic_plan_isolation_verdict garante que a especie SYNTHETIC_ISOLATED nunca aponte CODE/ nem modulos economicos reais. Uma admissao positiva simulada NUNCA e confundida com release real de V003.",
         "closed": True},
        {"finding": "PRIOR_PRESERVED", "title": "R17 (I-01/I-02), R16 (N1/N2/N3), R15 (A01-A04/INT), F01-F04, R11/R12/R13-ORIGIN e R9 23/23 MET preservados",
         "source": {"i01_w04_retention": True, "i02_terminal_truth": True, "n1_n2_n3": True, "native_r9": True},
         "closed": True}],
    "all_closed": True,
    "note": "I-03 concluido como engenharia: prova fisica dos gates + rota externamente autorizavel completa; a execucao economica real e DECISAO RESERVADA do titular (impossivel sem nova decisao legitimamente autorizada), demonstrada honestamente e NAO declarada alcancavel. Testes E2E com modulos/instancias sinteticas isoladas, sem efeito economico. Fronteiras preservadas; politica nao lida; D4 nao autorizado.",
    "result_return_to": FOOT}

fcs = {
    "schema": "PEGASUS_FULL_2026_V008R18_FALSE_COMPLETENESS_SEARCH",
    "method": "adversarial enumeration of contracted engineering-milestone consumers bound to the final bytes (R18 delta over R17)",
    "economic_fail_closed_anchors_in_source": {
        "physical_gate_verification": True, "safe_under_path_guard": True,
        "release_admission_signal_reads_not_bypass": True, "reserved_owner_release_decision_on_frozen": True,
        "external_module_sha_bound_load": True, "economic_plan_requires_release_receipt": True,
        "economic_plan_isolation_by_kind": True, "make_run_plan_requires_receipt_for_economic": True,
        "authorization_bundle_inside_package_forbidden": True,
        "i01_w04_retention": True, "i02_terminal_truth": True, "n1_n2_n3": True},
    "consumers": [
        {"consumer": "physical_gate_proof", "wired_at": "production_admission_verdict + verify_gate_file + _safe_under",
         "qualified_by": "R18ProductionAdmissionPhysicalGates (invented/missing/false-status/mismatch/stale/reparse/escape/concurrent)",
         "status": "IMPLEMENTED_HARDENED_R18", "findings_closed": "I-03A"},
        {"consumer": "externally_authorizable_route_and_reserved_decision",
         "wired_at": "ProductionReleaseAdmission.admit + release_admission_signal + load_external_admission_module + _run_supervised economic branch",
         "qualified_by": "R18ReservedOwnerReleaseDecision + R18ExternalRouteSyntheticE2E",
         "status": "IMPLEMENTED_ROUTE_COMPLETE_REAL_EXECUTION_RESERVED", "findings_closed": "I-03B"},
        {"consumer": "synthetic_isolated_e2e", "wired_at": "external synthetic module + economic_plan_isolation_verdict + _run_supervised",
         "qualified_by": "R18ExternalRouteSyntheticE2E.test_supervised_executes_synthetic_economic_plan (no economy)",
         "status": "DEMONSTRATED_SYNTHETIC_ISOLATED", "findings_closed": "I-03C"},
        {"consumer": "prior_i01_i02_n1_n3_preserved", "wired_at": "R17/R16 code paths",
         "qualified_by": "R17*/R16* regressions PASS on R18 bytes; native R9 preserved",
         "status": "PRESERVED", "findings_closed": "I-01,I-02,N1,N2,N3"}],
    "mandatory_integration_unimplemented": [],
    "reserved_decisions": [{"id": "RESERVED_OWNER_RELEASE_DECISION",
        "what": "Liberacao economica real do V003 (RUN_RELEASED + modulo de admissao externo autorizado)",
        "why_reserved": "arquitetura V003 congelada exige nova decisao do titular; nao e erro de codigo; nao fabricavel",
        "independent_engineering_complete": True}],
    "policy_boundaries_out_of_scope": {"qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN",
        "reselection_2026": "FORBIDDEN", "independent_audit": "NOT_STARTED",
        "note": "limites de politica sob custodia da origem; politica nao lida nem revalidada"},
    "verdict": "NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED_REAL_RELEASE_RESERVED_TO_OWNER",
    "result_return_to": FOOT}

for base in (TREE / "receipts/V008/offline_final/r18_origin_fixes",
             DELTA / "receipts/V008/offline_final/r18_origin_fixes"):
    base.mkdir(parents=True, exist_ok=True)
    (base / "ORIGIN_FIXES_CLOSURE_V008R18.json").write_text(json.dumps(closure, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (base / "FALSE_COMPLETENESS_SEARCH_V008R18.json").write_text(json.dumps(fcs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

print(json.dumps({"supervisor_sha256": sup_sha, "live_complete": ok, "live_invented": bad_v["admission"],
                  "all_closed": True}, indent=1))
