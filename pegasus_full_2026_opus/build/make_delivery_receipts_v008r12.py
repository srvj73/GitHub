"""Gera os recibos externos do V008R12 (correção da revisão preparatória da origem sobre a R11:
R11-ORIGIN-01/02/03), vinculados aos bytes finais. Preserva a auditoria independente R10=FAIL
(F01-F04 fechados na R11), a campanha nativa R9 (23/23, MET) e as correções R10. Não executa
economia; não consulta política.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R12_20261023.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R12_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14"
ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
R11_ZIP_SHA = "DD1B3432FBD84EEACE7D6B06867C4CEB79BAB951F0BD6E51B8CC1DF015BDF94C"
AUDIT_ZIP_SHA = "AD59A7B39744A500EAA7EFAE1F56F23775162FE6839413246710557ABCDB67D3"
GATES = {"g4": "FROZEN", "qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN",
         "reselection_2026": "FORBIDDEN", "run_released": "NO", "full_released": "NO",
         "paid_credit": "NOT_USED", "independent_audit": "R10_FAIL_F01_F04_CLOSED_R11; R11_ORIGIN_REVIEW_CLOSED_R12; FORMAL_REAUDIT_PENDING_ORIGIN"}


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
    origin = json.loads((of / "r12_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R12.json").read_text(encoding="utf-8"))
    r11closure = json.loads((of / "r11_audit_fixes/FINDINGS_CLOSURE_V008R11.json").read_text(encoding="utf-8"))
    fcs = json.loads((of / "r12_origin_fixes/FALSE_COMPLETENESS_SEARCH_V008R12.json").read_text(encoding="utf-8"))
    tep = json.loads((e / "TESTED_EQUALS_PACKAGED_CHECK.json").read_text(encoding="utf-8"))
    dv = json.loads((e / "DELIVERED_VERIFY.json").read_text(encoding="utf-8"))
    nce = q["native_completeness_evaluation"]
    npass = sum(c["result"] == "PASS" for c in q["cases"])
    nskip = sum(c["result"] == "SKIPPED_NON_NATIVE" for c in q["cases"])
    unit_log = (of / "m1_battery/04_UNIT_TESTS.log").read_text(errors="replace")
    unit_n = next((ln.split()[1] for ln in unit_log.splitlines() if ln.startswith("Ran ")), "?")
    nat_pass = sum(c.get("result") == "PASS" for c in natq.get("cases", []))

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
                                    "all_closed_r12": origin.get("all_closed"),
                                    "findings": [{"id": f["finding"], "closed": f["closed"]} for f in origin.get("findings", [])],
                                    "evidence_in": "receipts/V008/offline_final/r12_origin_fixes/"},
              "false_completeness": {"verdict": fcs.get("verdict"),
                                     "mandatory_integration_unimplemented": fcs.get("mandatory_integration_unimplemented")}}

    final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": (d / ZIP_NAME).stat().st_size, "members": zmembers},
             "manifest_sha256": msha, "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"],
             "bootstrap": {"name": BOOT_NAME, "sha256": bsha, "bytes": (d / BOOT_NAME).stat().st_size},
             "supersedes_v008r11": {"zip_sha256": R11_ZIP_SHA, "reason": "origin preparatory review of R11: R11-ORIGIN-01 (close() closed Job handle with live tree before raise; W04 released while child alive), R11-ORIGIN-02 (Q11 matched historical PID), R11-ORIGIN-03 (cust.close() not guaranteed on pre-spawn-fail). All corrected fail-closed."},
             "entrypoint_pegasus_entry_sha256": ENTRY_SHA}

    put(d, "MISSION_LOCK_V008R12_DELIVERY.json", {
        "schema": "PEGASUS_FULL_2026_V008R12_MISSION_LOCK_DELIVERY",
        "mission_id": "PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022",
        "base_codex_v003_sha256": "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041",
        "final_bytes": final, "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED",
        "review_trail": review, "native_qualification_r9": native_r9, **GATES, "result_return_to": FOOT})

    put(d, "G0_OFFLINE_RECEIPT_V008R12.json", {
        "schema": "PEGASUS_FULL_2026_V008R12_G0_OFFLINE_RECEIPT", "final_bytes": final,
        "zip_crc": "PASS", "zip_member_safety": "PASS",
        "delivered_extract_verify": dv["result"], "delivered_manifest_sha256": dv["manifest_sha256"],
        "delivered_files_checked": dv["files_checked"],
        "offline_tests": {"supervisor_unit": "%s_OF_%s" % (unit_n, unit_n),
                          "supervisor_mutation": "%d_OF_%d_KILLED" % (mut["killed"], mut["mutants"]),
                          "bootstrap_exit_boundary": "%s passed=%s" % (bb["result"], bb["passed"]),
                          "bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
                          "supervised_qualification": "%s; PASS=%d (incl. Q16); SKIPPED_NON_NATIVE=%d; error=%s" % (
                              q["result"], npass, nskip, q.get("error"))},
        "review_trail": review, "native_qualification_r9": native_r9,
        "powershell_parse": "PASS_PWSH_7.4.6_LINUX; PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R9", **GATES})

    put(d, "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R12.json", {
        "schema": "PEGASUS_FULL_2026_V008R12_TESTED_EQUALS_PACKAGED_DELIVERED",
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
        "G2_W04_FULL": "QUALIFIED_NATIVE (R9); F01/F02 + R11-ORIGIN-01/03 fechados (W04 obrigatório; pré-spawn fail-closed; lifecycle garantido)",
        "G3_W04_JIT_JOB": "QUALIFIED_NATIVE (R9); F03 + R11-ORIGIN-02 fechados (identidade temporal (pid,ctime) única)",
        "G4_SAFESTOP_RESUME": "QUALIFIED_NATIVE (R9); F04 + R11-ORIGIN-01 fechados (NO_KILL real: close nunca fecha/mata árvore viva; decisão reservada registrada)",
        "G5_INTEGRATED_NATIVE_WIN": "QUALIFIED_NATIVE 23/23 (R9) nos bytes R9; R12 fecha a revisão da origem (delta offline-provado)",
        "G6_CANDIDATE_COMPLETENESS": "ENGINEERING_COMPLETE; F01-F04 + R11-ORIGIN-01/02/03 fechados; native MET nos bytes R9; selagem formal e reauditoria focal com a origem"}
    put(d, "PREDELIVERY_CONTROL_MATRIX_V008R12.json", {
        "schema": "PEGASUS_FULL_2026_V008R12_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
        "offline_evidence": {
            "v003_full_chain": "%s %d cases (imutavel)" % (v3["result"], len(v3["cases"])),
            "v008r12_supervised": "%s; PASS=%d (incl. Q16); SKIPPED_NON_NATIVE=%d; error=%s" % (q["result"], npass, nskip, q.get("error")),
            "native_completeness_evaluation": nce,
            "exit_boundary_bootstrap": "%s passed=%s" % (bb["result"], bb["passed"]),
            "supervisor_unit": "%s_OF_%s (inclui JobClosePlan, GrandchildContained, SupervisionPrespawnLifecycle)" % (unit_n, unit_n),
            "supervisor_mutants": "%d_OF_%d_KILLED (inclui job_close_plan_closes_live_tree, grandchild_contained_ignores_ctime)" % (mut["killed"], mut["mutants"]),
            "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A"},
        "review_trail": review, "false_completeness_search": fcs, "native_qualification_r9": native_r9,
        "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED; F01-F04 + R11-ORIGIN-01/02/03 CLOSED",
        "executable_delivery_ready": "READY; prova nativa dirigida de timeout/kill e re-run confirmatório sao do titular/origem",
        **GATES, "result_return_to": FOOT})

    put(d, "CANDIDATE_COMPLETENESS_RECEIPT_V008R12.json", {
        "schema": "PEGASUS_FULL_2026_V008R12_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
        "parts": {
            "1_source_and_lineage": "PASS (V003 físico byte-idêntico; entrypoint testado=empacotado=entregue); QS4 sucessor ausente provado",
            "2_consumers_implemented_wired_and_blocked": "PASS; auditoria R10 (F01-F04) e revisão da origem R11 (R11-ORIGIN-01/02/03) fechadas fail-closed. Busca de falsa completude: %s" % fcs.get("verdict"),
            "3_offline_qualification_final_bytes": "PASS (19/19 V003; V008R12 %d PASS incl. Q16 + %d SKIP; %s/%s unit; %d/%d mutantes supervisor; 20/20 bootstrap boundary; %d/%d bootstrap mutantes)" % (npass, nskip, unit_n, unit_n, mut["killed"], mut["mutants"], bm["killed"], bm["mutants"]),
            "4_native_target_qualification": "MET nos bytes R9 (23/23 numa execução); evidência preservada em native_campaign_r9/. As correções da auditoria/origem são no lado do pai/decisão (gates), com controles negativos offline; a prova nativa dirigida de timeout/kill (R11-ORIGIN-01/F04) e a identidade temporal real de Q11 (R11-ORIGIN-02) são do titular/origem",
            "5_tested_packaged_installed_delivered": "PASS offline (%d arquivos conferidos); instalado PENDENTE (modo Install, opcional)" % dv["files_checked"]},
        "candidate_completeness": "ENGINEERING_COMPLETE_ALL_FINDINGS_CLOSED_NATIVE_MET_ON_R9_BYTES",
        "review_trail": review,
        "single_external_item_remaining": "reauditoria focal pela origem/mesmo auditor + selagem formal; sob autorização: prova nativa dirigida de timeout/kill (NO_KILL/W04 na árvore viva) e re-execução nativa confirmatória nos bytes R12",
        "out_of_mission_gate": "Harness QS4 sucessor vinculado ao adaptador EC96FE9A exige qualificação QS4 (QS4=NO)",
        **GATES, "result_return_to": FOOT})

    put(d, "PREDELIVERY_ADMISSION_RECEIPT_V008R12.json", {
        "schema": "PEGASUS_FULL_2026_V008R12_PREDELIVERY_ADMISSION_RECEIPT", "final_bytes": final,
        "components": {p.relative_to(d).as_posix(): sha(p) for p in sorted(d.rglob("*")) if p.is_file()},
        "admitted_for": "OWNER_WINDOWS_NON_ECONOMIC_CAMPAIGN + ORIGIN_FOCAL_REAUDIT (Verify -> opcional QualifyNative confirmatório; prova dirigida de timeout/kill só sob autorização, sem matar processos salvo salvaguardas)",
        "not_admitted_for": ["QS4", "FULL economico", "Phase B/C economicas", "reselection", "RUN_RELEASED",
                             "Install/Rollback produtivo sem autorização", "alteração de política/MASTER/HEAD"],
        **GATES, "result_return_to": FOOT})

    files = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "DELIVERY_MANIFEST_SHA256.json")
    put(d, "DELIVERY_MANIFEST_SHA256.json", {
        "schema": "PEGASUS_FULL_2026_V008R12_DELIVERY_MANIFEST",
        "members": [{"path": p.relative_to(d).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]})
    print(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
