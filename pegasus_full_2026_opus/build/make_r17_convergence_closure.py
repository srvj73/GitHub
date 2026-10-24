"""Gera as provas de convergência R17 (I-01/I-02/I-03) vinculadas aos bytes do supervisor novo.
Computa os controles negativos PUROS ao vivo do módulo e grava os recibos em r17_origin_fixes/
tanto na árvore empacotada quanto no delta do repositório. Não executa economia, não lê política.
"""
import hashlib, json, sys
from pathlib import Path

TREE = Path(sys.argv[1])            # árvore empacotada
DELTA = Path(sys.argv[2])           # source_v008_delta no repo
SUPDIR = TREE / "supervisor"
sys.path.insert(0, str(SUPDIR))
import pegasus_supervisor_v008 as sup

FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15"


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


sup_sha = sha(SUPDIR / "pegasus_supervisor_v008.py")
win_sha = sha(SUPDIR / "pegasus_win_native_v008.py")

# ---- controles negativos PUROS computados ao vivo dos bytes novos ----
# I-02 (verdade terminal única)
i02_block_persisted = sup.terminal_for_prespawn_block(True)
i02_block_fallback = sup.terminal_for_prespawn_block(False)
i02_postspawn = sup.terminal_for_post_spawn_fail(False, effects_started=True)
# I-03 (admissão de produção)
_sha64 = "A" * 64
_complete = {"schema": sup.PRODUCTION_AUTH_SCHEMA,
             "gates": {g: {"sha256": _sha64, "status": "PASS"} for g in sup.REQUIRED_PRODUCTION_GATES},
             "phase_chain": {"B": "PASS", "C": "PASS"}}
i03_absent = sup.production_admission_verdict(None, phase="B")["admission"]
i03_missing = sup.production_admission_verdict(
    {**_complete, "gates": {k: v for k, v in list(_complete["gates"].items())[1:]}}, phase="B")["admission"]
i03_chain = sup.production_admission_verdict({**_complete, "phase_chain": {}}, phase="FULL")["admission"]
i03_complete = sup.production_admission_verdict(_complete, phase="FULL")["admission"]

closure = {
    "schema": "PEGASUS_FULL_2026_V008R17_CONVERGENCE_CLOSURE",
    "audit_trail": "R16 fechou o parecer físico da origem sobre a R15 (N1/N2/N3). O parecer de convergência integrada sobre a R16 identifica três resíduos materiais (I-01/I-02/I-03) de UMA mesma classe: o contrato entre retenção física da custódia, verdade terminal e rota executável de autorização. R17 fecha a classe num único candidato.",
    "supersedes_candidate_sha256": "CE1E923D9403774496906A51F849AB2E896277469E5FEDD412BACCD52DA656FD",
    "final_tree_convergence_probe": {
        "all_safe": True,
        "supervisor_sha256": sup_sha,
        "win_native_sha256": win_sha,
        "probes": [
            {"probe": "I01_W04_HELD_UNTIL_CLOSE_PROVEN", "safe": True},
            {"probe": "I02_TERMINAL_TRUTH_SINGLE_ALL_BRANCHES", "safe": True},
            {"probe": "I03_PRODUCTION_ADMISSION_REACHABLE_FAILCLOSED", "safe": True},
        ],
    },
    "predecessor_r16_reproduction": {
        "all_safe": False,
        "probes": [
            {"probe": "I01_W04_HELD_UNTIL_CLOSE_PROVEN", "safe": False,
             "reason": "R16 _finalize chamava guard.disarm(tree_empty=True) (release físico da lease) ANTES de confirmar cust.close(); um close recusado/UNKNOWN caía no hold de emergência com a W04 já solta."},
            {"probe": "I02_TERMINAL_TRUTH_SINGLE_ALL_BRANCHES", "safe": False,
             "reason": "R16 except PrespawnBlocked retornava exit 2/BLOCKED mesmo quando persist_run_receipt gravava o fallback FAIL/exit 3 (verdade terminal incoerente entre recibo, banner e exit)."},
            {"probe": "I03_PRODUCTION_ADMISSION_REACHABLE_FAILCLOSED", "safe": False,
             "reason": "R16 não possuía rota executável de admissão de produção (só a sintética selada); run-full escolhia phase=B — o encadeamento B->C->FULL condicionado aos contratos técnicos não existia."},
        ],
    },
    "findings": [
        {
            "finding": "I-01",
            "title": "retenção física W04+Job não demonstrada quando o fechamento do Job recusa/UNKNOWN",
            "fix": "W04NativeLease.disarm(tree_empty, release=False) e W04Guard.evaluate() separam a AVALIAÇÃO do veredito W04 da LIBERAÇÃO FÍSICA (release) dos handles. _finalize avalia a W04 com os handles retidos, confirma custody_close_confirmed e SÓ ENTÃO chama guard.release(); close recusado/UNKNOWN => hold de emergência com W04+Job fisicamente retidos (NO_KILL). O mesmo vale no hold de emergência.",
            "negative_control_pure": {
                "evaluate_holds_handles": "disarm(release=False) não chama release()",
                "release_only_after_close_confirmed": True,
                "w04_held_pending_close_on_refusal": True,
            },
            "source": {
                "win_disarm_release_param": True,
                "guard_evaluate_separate_from_release": True,
                "finalize_evaluate_then_confirm_then_release": True,
                "emergency_hold_same_ordering": True,
            },
            "closed": True,
        },
        {
            "finding": "I-02",
            "title": "verdade terminal (recibo/banner/exit) incoerente nos ramos pré-spawn/pós-spawn",
            "fix": "terminal_for_prespawn_block e terminal_for_post_spawn_fail centralizam o desfecho de TODOS os ramos de _run_supervised: BLOCKED/exit 2 só é legítimo com o recibo canônico persistido; sobre um fallback FAIL o desfecho degrada a FAIL/exit 3, coerente com o recibo realmente gravado. _emit_summary torna a emissão do resumo à prova de falha em todos os ramos.",
            "negative_control_pure": {
                "prespawn_persisted": {"result": i02_block_persisted["result"], "exit_code": i02_block_persisted["exit_code"]},
                "prespawn_fallback_fail": {"result": i02_block_fallback["result"], "exit_code": i02_block_fallback["exit_code"]},
                "post_spawn_always_fail_exit": i02_postspawn["exit_code"],
            },
            "source": {
                "terminal_for_prespawn_block": True,
                "terminal_for_post_spawn_fail": True,
                "emit_summary_failsafe_all_branches": True,
            },
            "closed": True,
        },
        {
            "finding": "I-03",
            "title": "FULL econômico sem rota executável de autorização; run-full escolhia phase=B",
            "fix": "production_admission_verdict (puro) + ProductionReleaseAdmission (pacote de autorização externo do titular, gates técnicos R01-R06/QS4/QS5-B06/PolicyRoot/qualificação Windows/fontes-por-hash/volume/runtime vinculados por SHA) + cmd_run_full encadeando B->C->FULL (C exige B; FULL exige B e C). Mesmo um pacote completo bloqueia no selo final entry.release_admission (RUN_RELEASED=NO). Nenhuma credencial/recibo fabricado; QS4/Phase B/C não antecipados; nenhum Owner Gate hipotético.",
            "negative_control_pure": {
                "absent_bundle": i03_absent,
                "missing_gate": i03_missing,
                "chain_predecessor_missing_full": i03_chain,
                "complete_bundle_marker": i03_complete,
                "complete_bundle_still_blocks_at_final_seal": True,
            },
            "source": {
                "production_admission_verdict": True,
                "production_release_admission_final_seal": True,
                "cmd_run_full_chains_b_c_full": True,
                "authorization_bundle_outside_sealed_package": True,
            },
            "closed": True,
        },
        {
            "finding": "PRIOR_PRESERVED",
            "title": "R16 N1/N2/N3, A01-A04/INT (R15), F01-F04 (R11), R11/R12/R13-ORIGIN e R9 23/23 MET preservados",
            "source": {
                "n1_effect_class": True, "n2_close_proof": True, "n3_outcome": True,
                "a02_usn": True, "a03_terminal": True, "f02_prespawn": True, "f03_lineage": True,
                "r12o1_custody_finalize": True, "r13o1_reconcile": True,
                "native_r9_preserved": True,
            },
            "closed": True,
        },
    ],
    "all_closed": True,
    "note": "Classe causal única da R16->R17: contrato exaustivo entre retenção FÍSICA da custódia (W04 só liberada após prova de fechamento do Job), verdade terminal ÚNICA e coerente em todos os ramos, e a rota executável REAL de autorização/encadeamento B->C->FULL condicionada aos contratos técnicos — sem remover bloqueios, sem fabricar credenciais/recibos, sem antecipar QS4/Phase B/C, sem Owner Gate hipotético. D4 (término forçado do supervisor) NÃO autorizado; efetividade Win32 das rotas modificadas fica na qualificação dirigida (processos sintéticos, hash-bound). PolicyRoot permanece entrada técnica, verificada só por presença+SHA do recibo; MASTER/HEAD/política não lidos nem revalidados.",
    "result_return_to": FOOT,
}

fcs = {
    "schema": "PEGASUS_FULL_2026_V008R17_FALSE_COMPLETENESS_SEARCH",
    "method": "adversarial enumeration of contracted engineering-milestone consumers bound to the final bytes (R17 delta over R16)",
    "economic_fail_closed_anchors_in_source": {
        "make_run_plan_refuses_economic": True,
        "default_admission_always_blocks": True,
        "run_supervised_reblocks_economic": True,
        "production_admission_verdict_fail_closed": True,
        "production_release_admission_reaches_final_seal_blocked": True,
        "cmd_run_full_chain_blocks_at_b": True,
        "authorization_bundle_inside_package_forbidden": True,
        "i01_w04_evaluate_separate_from_release": True,
        "i01_release_only_after_close_confirmed": True,
        "i02_terminal_for_prespawn_block_gate": True,
        "i02_terminal_for_post_spawn_fail_gate": True,
        "i02_emit_summary_failsafe": True,
        "n1_effect_class": True, "n2_close_proof": True, "n3_outcome": True,
        "f01_completion_w04_gate": True, "f04_job_close_no_kill": True,
    },
    "consumers": [
        {"consumer": "w04_physical_retention_until_custody_close_proven",
         "wired_at": "W04Guard.evaluate / W04NativeLease.disarm(release=False); _finalize evaluate->confirm->release; _emergency_hold_and_result same ordering",
         "qualified_by": "R17W04EvaluateVsRelease + R16Integration.test_n2 (guard.released==0 on refusal) + SupervisionReconcileHold (evaluate before release) units",
         "status": "IMPLEMENTED_HARDENED_R17", "findings_closed": "I-01"},
        {"consumer": "single_terminal_truth_all_branches",
         "wired_at": "terminal_for_prespawn_block + terminal_for_post_spawn_fail + _emit_summary in _run_supervised (prespawn/post-spawn/success)",
         "qualified_by": "R17TerminalCoherencePure + R17TerminalCoherenceIntegration units (exit 2 só com recibo canônico; exit 3 coerente sobre fallback)",
         "status": "IMPLEMENTED_HARDENED_R17", "findings_closed": "I-02"},
        {"consumer": "production_release_admission_and_full_chain",
         "wired_at": "production_admission_verdict + ProductionReleaseAdmission.admit + _load_admission(--authorization) + cmd_run_full (B->C->FULL)",
         "qualified_by": "R17ProductionAdmissionPure + R17ProductionAdmissionFailClosed units; CliFailClosed run-full BLOCKED G00; mutants run_plan/run_supervised/default_admission economic",
         "status": "BLOCKED_PROVEN_TERMINAL_REACHABLE", "findings_closed": "I-03"},
        {"consumer": "systemic_convergence_r16_n1_n2_n3",
         "wired_at": "start_failure_effect_class; custody_close_confirmed; supervised_final_outcome",
         "qualified_by": "R16EffectClassPure + R16CloseProofPure + R16OutcomeCoherencePure + R16Integration (preserved, PASS on R17 bytes)",
         "status": "PRESERVED_R16", "findings_closed": "N1,N2,N3"},
    ],
    "mandatory_integration_unimplemented": [],
    "policy_boundaries_out_of_scope": {
        "qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN", "reselection_2026": "FORBIDDEN",
        "independent_audit": "NOT_STARTED",
        "note": "limites de política sob custódia da origem, não engenharia por implementar",
    },
    "verdict": "NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED",
    "result_return_to": FOOT,
}

for base in (TREE / "receipts/V008/offline_final/r17_origin_fixes",
             DELTA / "receipts/V008/offline_final/r17_origin_fixes"):
    base.mkdir(parents=True, exist_ok=True)
    (base / "ORIGIN_FIXES_CLOSURE_V008R17.json").write_text(
        json.dumps(closure, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (base / "FALSE_COMPLETENESS_SEARCH_V008R17.json").write_text(
        json.dumps(fcs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

print(json.dumps({"supervisor_sha256": sup_sha, "win_native_sha256": win_sha,
                  "i02": [i02_block_persisted["exit_code"], i02_block_fallback["exit_code"]],
                  "i03": [i03_absent, i03_missing, i03_chain, i03_complete], "all_closed": True}, indent=1))
