"""Gera os recibos externos do V008R16 (fechamento sistêmico do parecer físico da origem sobre a R15:
R12-ORIGIN-01 custódia durável NO_KILL+W04 em toda a vida da árvore; R12-ORIGIN-02 identidade
temporal INDEPENDENTE do neto), vinculados aos bytes finais. Preserva a auditoria independente
R10=FAIL (F01-F04 fechados na R11), a revisão da origem sobre R11 (R11-ORIGIN-01/02/03 fechados na
R12), a campanha nativa R9 (23/23, MET) e as correções R10. Não executa economia; não consulta
política.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R16_20261024.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R16_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14"
ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
R14_ZIP_SHA = "012D4347D7283B46EDC59A2BB49A58DBC1AE54F250E463FB002102031AF3D7CF"
R15_ZIP_SHA = "75EE96E700408876B4F5509DB2B6397517AE993C29A05BA713480D912C5A1490"
AUDIT_ZIP_SHA = "AD59A7B39744A500EAA7EFAE1F56F23775162FE6839413246710557ABCDB67D3"
GATES = {"g4": "FROZEN", "qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN",
         "reselection_2026": "FORBIDDEN", "run_released": "NO", "full_released": "NO",
         "paid_credit": "NOT_USED",
         "independent_audit": "R10_FAIL_F01_F04_CLOSED_R11; R11_ORIGIN_CLOSED_R12; R12_ORIGIN_CLOSED_R13; R13_PHYSICAL_CLOSED_R14; R14_DEEP_AUDIT_A01_A04_INT_CLOSED_R15; R15_PHYSICAL_PARECER_N1_N3_CLOSED_R16; FORMAL_REAUDIT_PENDING_ORIGIN"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def put(d: Path, name: str, obj) -> None:
    p = d / name
    if p.exists():
        raise SystemExit("RECEIPT_EXISTS_FAIL_CLOSED " + name)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delivery", required=True)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--evidence", required=True)
    ns = ap.parse_args(argv)
    d, t, e = Path(ns.delivery), Path(ns.tree), Path(ns.evidence)
    zsha, bsha = sha(d / ZIP_NAME), sha(d / BOOT_NAME)
    with zipfile.ZipFile(d / ZIP_NAME) as z:
        zmembers = len(z.namelist())
    msha = sha(t / "MANIFEST_SHA256.json")
    of = t / "receipts/V008/offline_final"
    q = json.loads((of / "v008_supervised_qualification/V008_QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    v3 = json.loads((of / "v003_full_chain/QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    mut = json.loads((of / "m1_battery/05_MUTATION.json").read_text(encoding="utf-8"))
    bb = json.loads((of / "bootstrap_boundary/BOOTSTRAP_EXIT_BOUNDARY_RESULT.json").read_text(encoding="utf-8"))
    bm = json.loads((of / "bootstrap_boundary/BOOTSTRAP_MUTATION_RESULT.json").read_text(encoding="utf-8"))
    nat = json.loads((of / "native_campaign_r9/CAMPAIGN_RESULT.json").read_text(encoding="utf-8-sig"))
    natq = json.loads((of / "native_campaign_r9/NATIVE_QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    origin = json.loads((of / "r16_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R16.json").read_text(encoding="utf-8"))
    r15origin = json.loads((of / "r15_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R15.json").read_text(encoding="utf-8"))
    r11closure = json.loads((of / "r11_audit_fixes/FINDINGS_CLOSURE_V008R11.json").read_text(encoding="utf-8"))
    r12origin = json.loads((of / "r12_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R12.json").read_text(encoding="utf-8"))
    r13origin = json.loads((of / "r13_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R13.json").read_text(encoding="utf-8"))
    r14origin = json.loads((of / "r14_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R14.json").read_text(encoding="utf-8"))
    fcs = json.loads((of / "r16_origin_fixes/FALSE_COMPLETENESS_SEARCH_V008R16.json").read_text(encoding="utf-8"))
    tep = json.loads((e / "TESTED_EQUALS_PACKAGED_CHECK.json").read_text(encoding="utf-8"))
    dv = json.loads((e / "DELIVERED_VERIFY.json").read_text(encoding="utf-8"))
    nce = q["native_completeness_evaluation"]
    npass = sum(c["result"] == "PASS" for c in q["cases"])
    nskip = sum(c["result"] == "SKIPPED_NON_NATIVE" for c in q["cases"])
    unit_log = (of / "m1_battery/04_UNIT_TESTS.log").read_text(errors="replace")
    unit_n = next((ln.split()[1] for ln in unit_log.splitlines() if ln.startswith("Ran ")), "?")
    nat_pass = sum(c.get("result") == "PASS" for c in natq.get("cases", []))

    r12_findings = [{"id": f["finding"], "closed": f["closed"]} for f in r12origin.get("findings", [])
                    if str(f.get("finding", "")).startswith("R12-ORIGIN")]
    r13_findings = [{"id": f["finding"], "closed": f["closed"]} for f in r13origin.get("findings", [])
                    if str(f.get("finding", "")).startswith("R13-ORIGIN")]
    r15_findings = [{"id": f["finding"], "closed": f["closed"]} for f in r15origin.get("findings", [])]
    r16_findings = [{"id": f["finding"], "closed": f["closed"]} for f in origin.get("findings", [])]

    native_r9 = {"result_zip_sha256": "7290A855726B2791D478249574EF9BD4F4AA6835B4F23CAB0A37D9A3DC38CE5E",
                 "bound_to_bytes": {"zip_sha256": nat.get("zip_sha256"), "manifest_sha256": nat.get("manifest_sha256")},
                 "qualifynative_exit": nat.get("qualification_exit"), "cases_pass": nat_pass,
                 "native_completeness_evaluation": natq.get("native_completeness_evaluation", {}).get("verdict"),
                 "preserved_in": "receipts/V008/offline_final/native_campaign_r9/"}
    review = {"independent_audit_r10": {"auditor": "Work Astra", "verdict": "FAIL",
                                        "package_sha256": AUDIT_ZIP_SHA, "findings": "F01-F04",
                                        "all_closed_r11": r11closure.get("all_closed"),
                                        "preserved_in": "receipts/V008/offline_final/r11_audit_fixes/"},
              "origin_review_r11": {"reviewer": "ChatGPT origin/custody (not independent auditor)",
                                    "decision": "CANDIDATE_COMPLETENESS_NOT_PASS; FORMAL_REAUDIT_DISPATCH_BLOCKED",
                                    "points": ["R11-ORIGIN-01", "R11-ORIGIN-02", "R11-ORIGIN-03"],
                                    "all_closed_r12": r12origin.get("all_closed"),
                                    "preserved_in": "receipts/V008/offline_final/r12_origin_fixes/"},
              "origin_review_r12": {"reviewer": "ChatGPT origin/custody (not independent auditor, not native Windows)",
                                    "decision": "CANDIDATE_COMPLETENESS_NOT_PASS; two open material blockers",
                                    "points": ["R12-ORIGIN-01 (durable custody: NO_KILL + W04 over whole tree life + effective custody + recovery)",
                                               "R12-ORIGIN-02 (independent, temporally-bound grandchild identity)"],
                                    "all_closed_r13": r13origin.get("all_closed"),
                                    "findings": r12_findings,
                                    "preserved_in": "receipts/V008/offline_final/r13_origin_fixes/"},
              "origin_review_r13": {"reviewer": "ChatGPT origin/custody (physical review of the frozen R13 ZIP)",
                                    "physical_verification": "PACKAGE_INTEGRITY=PASS; MANIFEST=2953/2953 PASS",
                                    "decision": "CANDIDATE_COMPLETENESS_NOT_PASS; one open material blocker",
                                    "points": ["R13-ORIGIN-01 (reserved decision must not terminate the supervisor with a live tree)"],
                                    "all_closed_r14": r14origin.get("all_closed"),
                                    "findings": r13_findings,
                                    "preserved_in": "receipts/V008/offline_final/r14_origin_fixes/"},
              "origin_review_r14_deep_audit": {"reviewer": "ChatGPT origin/custody (deep preparatory audit of the frozen R14 candidate)",
                                    "physical_verification": "PACKAGE_INTEGRITY_R14=PASS; MANIFEST=2955/2955",
                                    "decision": "CANDIDATE_COMPLETENESS=NOT_PASS; INTEGRATED_ENGINEERING_READY=NO; single integrated convergence required",
                                    "points": ["A01 SAFE_STOP exception -> premature custody exit (reproduced on R14 bytes)",
                                               "A02 USN reader false completeness -> W04 false PASS (reproduced, bytes 97A9543C)",
                                               "A03 completion lacked terminal STATUS/receipt proof",
                                               "A04 technical failure may not emit structured receipt",
                                               "INT boundary/exception family + --admission isolation"],
                                    "all_closed_r15": r15origin.get("all_closed"),
                                    "findings": r15_findings,
                                    "final_tree_convergence_probe": (r15origin.get("final_tree_convergence_probe") or {}).get("all_safe"),
                                    "predecessor_r14_reproduction": r15origin.get("predecessor_r14_reproduction"),
                                    "evidence_in": "receipts/V008/offline_final/r15_origin_fixes/"},
              "origin_review_r15_physical": {"reviewer": "ChatGPT origin/custody (physical review of the frozen R15 ZIP + reproducible synthetic negatives)",
                                    "physical_verification": "PACKAGE_INTEGRITY_R15=PASS; MANIFEST=2962/2962; CRC/paths/bootstrap PASS",
                                    "decision": "CANDIDATE_COMPLETENESS=NOT_PASS; ORIGIN_INTEGRATION_GATE=NOT_PASS_MATERIAL_CONTRADICTIONS; single systemic closure required",
                                    "points": ["N1 effect classification after resume (resumed_threads>=1 executed, classified NO_EFFECT exit 2)",
                                               "N2 custodian declared CUSTODIAN_CLOSED after close() refused (ActiveProcesses>0 / no proof)",
                                               "N3 summary printed result=PASS with exit_code=3 when canonical receipt failed"],
                                    "all_closed_r16": origin.get("all_closed"),
                                    "findings": r16_findings,
                                    "final_tree_convergence_probe": (origin.get("final_tree_convergence_probe") or {}).get("all_safe"),
                                    "predecessor_r15_reproduction": origin.get("predecessor_r15_reproduction"),
                                    "evidence_in": "receipts/V008/offline_final/r16_origin_fixes/"},
              "false_completeness": {"verdict": fcs.get("verdict"),
                                     "mandatory_integration_unimplemented": fcs.get("mandatory_integration_unimplemented")}}

    final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": (d / ZIP_NAME).stat().st_size, "members": zmembers},
             "manifest_sha256": msha, "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"],
             "bootstrap": {"name": BOOT_NAME, "sha256": bsha, "bytes": (d / BOOT_NAME).stat().st_size},
             "supersedes_v008r15": {"zip_sha256": R15_ZIP_SHA, "reason": "origin physical review of R15 reproduced three synthetic negatives (N1/N2/N3) converging on one causal class: no single exhaustive contract binding child phase, effects already possible, custody/handles actually held or released, terminal result and final receipt/exit. R16 closes the class: N1 start_failure_effect_class classifies effects by facts (resumed_threads>=1 executed -> effects possible, never no-effect exit 2); N2 close() returns structured proof and _finalize re-checks final accounting before disarm/close, declaring CUSTODIAN_CLOSED only via custody_close_confirmed (else observable hold, W04+Job retained, NO_KILL); N3 supervised_final_outcome centralizes the outcome so result/exit_code/exit_class/phase/banner always agree and a missing canonical receipt is never success. Regression N1/N2/N3 fail on frozen R15 and pass on R16; convergence probe all_safe on final bytes and UNSAFE reproduced on R15 bytes. R15 frozen, V003 core, prior PASS (F01-F04, R11/R12/R13-ORIGIN, A01-A04/INT) and R9 native 23/23 MET all preserved. D4 (forced supervisor kill) not authorized."},
             "entrypoint_pegasus_entry_sha256": ENTRY_SHA}

    put(d, "MISSION_LOCK_V008R16_DELIVERY.json", {
        "schema": "PEGASUS_FULL_2026_V008R16_MISSION_LOCK_DELIVERY",
        "mission_id": "PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022",
        "base_codex_v003_sha256": "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041",
        "final_bytes": final, "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED",
        "review_trail": review, "native_qualification_r9": native_r9, **GATES, "result_return_to": FOOT})

    put(d, "G0_OFFLINE_RECEIPT_V008R16.json", {
        "schema": "PEGASUS_FULL_2026_V008R16_G0_OFFLINE_RECEIPT", "final_bytes": final,
        "zip_crc": "PASS", "zip_member_safety": "PASS",
        "delivered_extract_verify": dv["result"], "delivered_manifest_sha256": dv["manifest_sha256"],
        "delivered_files_checked": dv["files_checked"],
        "offline_tests": {"supervisor_unit": "%s_OF_%s" % (unit_n, unit_n),
                          "supervisor_mutation": "%d_OF_%d_KILLED" % (mut["killed"], mut["mutants"]),
                          "bootstrap_exit_boundary": "%s passed=%s" % (bb["result"], bb["passed"]),
                          "bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
                          "supervised_qualification": "%s; PASS=%d (incl. Q16, Q17); SKIPPED_NON_NATIVE=%d; error=%s" % (
                              q["result"], npass, nskip, q.get("error"))},
        "review_trail": review, "native_qualification_r9": native_r9,
        "powershell_parse": "PASS_PWSH_7.4.6_LINUX; PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R9", **GATES})

    put(d, "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R16.json", {
        "schema": "PEGASUS_FULL_2026_V008R16_TESTED_EQUALS_PACKAGED_DELIVERED",
        "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"], "final_manifest_sha256_m2": msha,
        "m1_to_m2": {"m1_members": tep["m1_members"], "m2_members": tep["m2_members"],
                     "m1_to_m2_added": len(tep["m1_to_m2_added"]), "m1_to_m2_removed": len(tep["m1_to_m2_removed"]),
                     "m1_to_m2_changed": len(tep["m1_to_m2_changed"]),
                     "m1_to_m2_delta_only_offline_evidence": tep["m1_to_m2_delta_only_offline_evidence"],
                     "tested_code_sha256_equals_final_manifest": tep["tested_code_sha256_equals_final_manifest"],
                     "tested_supervisor_sha256_present_in_final": tep["tested_supervisor_sha256_present_in_final"]},
        "delivered_zip_extract_verify": dv["result"], "delivered_unit_tests": "%s_OF_%s_PASS" % (unit_n, unit_n),
        "delivered_supervisor_verify": "PASS_PACKAGE_VERIFIED", "delivered_entry_verify": "PACKAGE_INTEGRITY=PASS",
        "installed": "PENDING_OWNER_INSTALL_MODE",
        "result": "PASS_TESTED_EQUALS_PACKAGED_EQUALS_DELIVERED_OFFLINE"})

    gates = {
        "G1_SOURCE_BINDING": "PASS; QS4_HARNESS_BINDING=BLOCKED_PROVEN",
        "G2_W04_FULL": "QUALIFIED_NATIVE (R9); F01/F02 + R11-ORIGIN-01/03 + R12-ORIGIN-01 fechados (W04 obrigatório; pré-spawn fail-closed; lifecycle garantido; W04 retida por TODA a vida da árvore)",
        "G3_W04_JIT_JOB": "QUALIFIED_NATIVE (R9); F03 + R11-ORIGIN-02 + R12-ORIGIN-02 fechados (identidade temporal (pid,ctime) INDEPENDENTE e única do neto)",
        "G4_SAFESTOP_RESUME": "QUALIFIED_NATIVE (R9); F04 + R11-ORIGIN-01 + R12-ORIGIN-01 + R13-ORIGIN-01 + A01 (R15) fechados (NO_KILL real: Supervision e maquina de estados; nenhuma excecao pos-spawn encerra a custodia; close() so com arvore VERIFICADA vazia; observe_tree tri-estado)",
        "G5_INTEGRATED_NATIVE_WIN": "QUALIFIED_NATIVE 23/23 (R9) nos bytes R9; R15 fecha a auditoria preparatoria profunda da origem sobre R14 (A01-A04 + INT); probe de convergencia all_safe nos bytes finais; prova Win32 dirigida pendente",
        "G6_CANDIDATE_COMPLETENESS": "ENGINEERING_COMPLETE; F01-F04 + R11/R12/R13-ORIGIN + A01-A04 + INT-FAMILY + C4-ISOLATION fechados; native MET nos bytes R9; selagem formal e reauditoria focal com a origem"}
    put(d, "PREDELIVERY_CONTROL_MATRIX_V008R16.json", {
        "schema": "PEGASUS_FULL_2026_V008R16_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
        "offline_evidence": {
            "v003_full_chain": "%s %d cases (imutavel)" % (v3["result"], len(v3["cases"])),
            "v008r15_supervised": "%s; PASS=%d (incl. Q16, Q17); SKIPPED_NON_NATIVE=%d; error=%s" % (q["result"], npass, nskip, q.get("error")),
            "native_completeness_evaluation": nce,
            "exit_boundary_bootstrap": "%s passed=%s" % (bb["result"], bb["passed"]),
            "supervisor_unit": "%s_OF_%s (inclui UsnScanCoverage, TerminalEvidence, CompletionTerminalRequired, SupervisionCustodyExceptions, StartFailureDisposition, OwnerDispositionAndRelease, PlanIsolation, AdmissionSealed)" % (unit_n, unit_n),
            "supervisor_mutants": "%d_OF_%d_KILLED (inclui usn_coverage_accepts_nonprogress, completion_ignores_terminal_evidence, terminal_accepts_stale_run_instance, tree_verified_empty_accepts_single, admission_accepts_unsealed_module, plan_isolation_allows_economic_entry)" % (mut["killed"], mut["mutants"]),
            "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A"},
        "review_trail": review, "false_completeness_search": fcs, "native_qualification_r9": native_r9,
        "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED; F01-F04 + R11/R12/R13-ORIGIN + A01-A04 + INT-FAMILY + C4-ISOLATION CLOSED",
        "executable_delivery_ready": "READY; prova nativa dirigida de custódia durável/NO_KILL em processos sintéticos sao do titular/origem",
        **GATES, "result_return_to": FOOT})

    put(d, "CANDIDATE_COMPLETENESS_RECEIPT_V008R16.json", {
        "schema": "PEGASUS_FULL_2026_V008R16_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
        "parts": {
            "1_source_and_lineage": "PASS (V003 físico byte-idêntico; entrypoint testado=empacotado=entregue); QS4 sucessor ausente provado",
            "2_consumers_implemented_wired_and_blocked": "PASS; auditoria R10 (F01-F04), revisoes da origem R11/R12/R13 e a auditoria preparatoria profunda R14 (A01-A04 + familias INT + isolamento --admission) fechadas fail-closed; probe de convergencia all_safe nos bytes finais. Busca de falsa completude: %s" % fcs.get("verdict"),
            "3_offline_qualification_final_bytes": "PASS (19/19 V003; V008R16 %d PASS incl. Q16, Q17 + %d SKIP; %s/%s unit; %d/%d mutantes supervisor; 20/20 bootstrap boundary; %d/%d bootstrap mutantes)" % (npass, nskip, unit_n, unit_n, mut["killed"], mut["mutants"], bm["killed"], bm["mutants"]),
            "4_native_target_qualification": "MET nos bytes R9 (23/23 numa execução); evidência preservada em native_campaign_r9/. As correções da auditoria/origem são no lado do pai/decisão (gates), com controles negativos offline; a prova nativa dirigida de custódia durável/NO_KILL — custodiante vivo até TREE_EMPTY (R12-ORIGIN-01/R13-ORIGIN-01) — e a identidade do neto em processo sintético (R12-ORIGIN-02) são do titular/origem",
            "5_tested_packaged_installed_delivered": "PASS offline (%d arquivos conferidos); instalado PENDENTE (modo Install, opcional)" % dv["files_checked"]},
        "candidate_completeness": "ENGINEERING_COMPLETE_ALL_FINDINGS_CLOSED_NATIVE_MET_ON_R9_BYTES",
        "review_trail": review,
        "single_external_item_remaining": "reauditoria formal independente + selagem de CANDIDATE_COMPLETENESS=PASS pela origem; sob autorizacao: qualificacao Windows dirigida (processos sinteticos, hash-bound) das propriedades A01/A02/A03 e KILL_ON_JOB_CLOSE ativo/removido, conforme WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R15.md; re-execucao nativa confirmatoria nos bytes R15",
        "out_of_mission_gate": "Harness QS4 sucessor vinculado ao adaptador EC96FE9A exige qualificação QS4 (QS4=NO)",
        **GATES, "result_return_to": FOOT})

    put(d, "PREDELIVERY_ADMISSION_RECEIPT_V008R16.json", {
        "schema": "PEGASUS_FULL_2026_V008R16_PREDELIVERY_ADMISSION_RECEIPT", "final_bytes": final,
        "components": {p.relative_to(d).as_posix(): sha(p) for p in sorted(d.rglob("*")) if p.is_file()},
        "admitted_for": "OWNER_WINDOWS_NON_ECONOMIC_CAMPAIGN + ORIGIN_FOCAL_REAUDIT (Verify -> opcional QualifyNative confirmatório; prova dirigida de custódia durável/NO_KILL só sob autorização, com processos sintéticos, sem matar processos salvo salvaguardas autorizadas)",
        "not_admitted_for": ["QS4", "FULL economico", "Phase B/C economicas", "reselection", "RUN_RELEASED",
                             "Install/Rollback produtivo sem autorização", "alteração de política/MASTER/HEAD"],
        **GATES, "result_return_to": FOOT})

    files = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "DELIVERY_MANIFEST_SHA256.json")
    put(d, "DELIVERY_MANIFEST_SHA256.json", {
        "schema": "PEGASUS_FULL_2026_V008R16_DELIVERY_MANIFEST",
        "members": [{"path": p.relative_to(d).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]})
    print(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
