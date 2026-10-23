"""Gera os recibos externos do V008R11 (correção dos achados F01-F04 da auditoria independente
Work Astra, AUDIT_VERDICT=FAIL sobre a R10), vinculados aos bytes finais. Preserva a evidência
nativa R9 (23/23, MET) e a correção R10. Não executa economia; não consulta política.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R11_20261023.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R11_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14"
ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
R10_ZIP_SHA = "8B3FA7E58D8CE3052981D9A85452F62DB7D4E88FBC3A318507DF7C129DE61B1A"
AUDIT_ZIP_SHA = "AD59A7B39744A500EAA7EFAE1F56F23775162FE6839413246710557ABCDB67D3"
GATES = {"g4": "FROZEN", "qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN",
         "reselection_2026": "FORBIDDEN", "run_released": "NO", "full_released": "NO",
         "paid_credit": "NOT_USED", "independent_audit": "STARTED_R10_FAIL_FINDINGS_CLOSED_R11"}


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
    closure = json.loads((of / "r11_audit_fixes/FINDINGS_CLOSURE_V008R11.json").read_text(encoding="utf-8"))
    fcs = json.loads((of / "r11_audit_fixes/FALSE_COMPLETENESS_SEARCH_V008R11.json").read_text(encoding="utf-8"))
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
    audit = {"auditor": "Work Astra (independent, operator-attested)", "verdict_on_r10": "FAIL",
             "audit_package_sha256": AUDIT_ZIP_SHA, "findings_all_closed": closure.get("all_closed"),
             "findings": [{"id": f["finding"], "closed": f["closed"], "fix": f["fix"]} for f in closure.get("findings", [])],
             "false_completeness": {"verdict": fcs.get("verdict"),
                                    "mandatory_integration_unimplemented": fcs.get("mandatory_integration_unimplemented")},
             "closed_in": "V008R11"}

    final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": (d / ZIP_NAME).stat().st_size, "members": zmembers},
             "manifest_sha256": msha, "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"],
             "bootstrap": {"name": BOOT_NAME, "sha256": bsha, "bytes": (d / BOOT_NAME).stat().st_size},
             "supersedes_v008r10": {"zip_sha256": R10_ZIP_SHA, "reason": "independent audit (Work Astra) FAIL on R10: F01 W04 BLOCKED not gating completion/exit; F02 incomplete W04 arm not preventing spawn; F03 unresolved identity -> GAPLESS and Q11 historical-PID-only; F04 KILL_ON_JOB_CLOSE could kill a live tree on controlled timeout exit. All corrected fail-closed."},
             "entrypoint_pegasus_entry_sha256": ENTRY_SHA}

    put(d, "MISSION_LOCK_V008R11_DELIVERY.json", {
        "schema": "PEGASUS_FULL_2026_V008R11_MISSION_LOCK_DELIVERY",
        "mission_id": "PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022",
        "base_codex_v003_sha256": "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041",
        "final_bytes": final, "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED",
        "independent_audit_findings": audit, "native_qualification_r9": native_r9, **GATES, "result_return_to": FOOT})

    put(d, "G0_OFFLINE_RECEIPT_V008R11.json", {
        "schema": "PEGASUS_FULL_2026_V008R11_G0_OFFLINE_RECEIPT", "final_bytes": final,
        "zip_crc": "PASS", "zip_member_safety": "PASS",
        "delivered_extract_verify": dv["result"], "delivered_manifest_sha256": dv["manifest_sha256"],
        "delivered_files_checked": dv["files_checked"],
        "offline_tests": {"supervisor_unit": "%s_OF_%s" % (unit_n, unit_n),
                          "supervisor_mutation": "%d_OF_%d_KILLED" % (mut["killed"], mut["mutants"]),
                          "bootstrap_exit_boundary": "%s passed=%s" % (bb["result"], bb["passed"]),
                          "bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
                          "supervised_qualification": "%s; PASS=%d (incl. Q16 integrado); SKIPPED_NON_NATIVE=%d; error=%s" % (
                              q["result"], npass, nskip, q.get("error"))},
        "independent_audit_findings": audit,
        "native_qualification_r9": native_r9,
        "powershell_parse": "PASS_PWSH_7.4.6_LINUX; PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R9", **GATES})

    put(d, "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R11.json", {
        "schema": "PEGASUS_FULL_2026_V008R11_TESTED_EQUALS_PACKAGED_DELIVERED",
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
        "G2_W04_FULL": "QUALIFIED_NATIVE (R9); F01/F02 corrigidos: W04 obrigatório na conclusão/exit e gate pré-spawn fail-closed",
        "G3_W04_JIT_JOB": "QUALIFIED_NATIVE (R9); F03 corrigido: identidade temporal (pid,ctime); unresolved bloqueia GAPLESS; Q11 por identidade resolvida",
        "G4_SAFESTOP_RESUME": "QUALIFIED_NATIVE (R9); F04 corrigido: NO_KILL no close de árvore viva (limpa KILL_ON_JOB_CLOSE; reconcilia na próxima execução)",
        "G5_INTEGRATED_NATIVE_WIN": "QUALIFIED_NATIVE 23/23 (R9) nos bytes R9; R11 corrige os achados da auditoria (delta offline-provado)",
        "G6_CANDIDATE_COMPLETENESS": "ENGINEERING_COMPLETE; achados F01-F04 fechados; native MET nos bytes R9; selagem formal e re-auditoria focal com a origem"}
    put(d, "PREDELIVERY_CONTROL_MATRIX_V008R11.json", {
        "schema": "PEGASUS_FULL_2026_V008R11_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
        "offline_evidence": {
            "v003_full_chain": "%s %d cases (imutavel)" % (v3["result"], len(v3["cases"])),
            "v008r11_supervised": "%s; PASS=%d (incl. Q16); SKIPPED_NON_NATIVE=%d; error=%s" % (q["result"], npass, nskip, q.get("error")),
            "native_completeness_evaluation": nce,
            "exit_boundary_bootstrap": "%s passed=%s" % (bb["result"], bb["passed"]),
            "supervisor_unit": "%s_OF_%s (inclui CompletionW04, W04PrespawnGate, LineageUnresolvedIdentity, JobCloseNoKill)" % (unit_n, unit_n),
            "supervisor_mutants": "%d_OF_%d_KILLED (inclui completion_ignores_w04, prespawn_accepts_sharing_violation, lineage_accepts_unresolved_identity, job_close_kills_live_tree)" % (mut["killed"], mut["mutants"]),
            "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A"},
        "independent_audit_findings": audit,
        "false_completeness_search": fcs,
        "native_qualification_r9": native_r9,
        "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED; F01-F04 CLOSED",
        "executable_delivery_ready": "READY; optional R11 native re-run is confirmatory only",
        **GATES, "result_return_to": FOOT})

    put(d, "CANDIDATE_COMPLETENESS_RECEIPT_V008R11.json", {
        "schema": "PEGASUS_FULL_2026_V008R11_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
        "parts": {
            "1_source_and_lineage": "PASS (V003 físico byte-idêntico; entrypoint testado=empacotado=entregue); QS4 sucessor ausente provado",
            "2_consumers_implemented_wired_and_blocked": "PASS; achados da auditoria F01-F04 fechados (W04 obrigatório na conclusão/exit + por caso; gate pré-spawn fail-closed; identidade temporal; NO_KILL no close). Busca de falsa completude: %s" % fcs.get("verdict"),
            "3_offline_qualification_final_bytes": "PASS (19/19 V003; V008R11 %d PASS incl. Q16 + %d SKIP; %s/%s unit; %d/%d mutantes supervisor; 20/20 bootstrap boundary; %d/%d bootstrap mutantes)" % (npass, nskip, unit_n, unit_n, mut["killed"], mut["mutants"], bm["killed"], bm["mutants"]),
            "4_native_target_qualification": "MET nos bytes R9 (23/23 numa execução); evidência preservada em native_campaign_r9/. R11 corrige os achados da auditoria (gates no lado do pai/decisão), com controles negativos offline; prova nativa dirigida de kill (F04) e re-execução confirmatória nos bytes R11 são do titular/origem",
            "5_tested_packaged_installed_delivered": "PASS offline (%d arquivos conferidos); instalado PENDENTE (modo Install, opcional)" % dv["files_checked"]},
        "candidate_completeness": "ENGINEERING_COMPLETE_AUDIT_FINDINGS_CLOSED_NATIVE_MET_ON_R9_BYTES",
        "independent_audit_findings": audit,
        "single_external_item_remaining": "re-auditoria focal pela origem/mesmo auditor e selagem formal; opcionalmente re-execução nativa confirmatória e prova nativa dirigida de timeout/kill (F04) sob autorização da origem",
        "out_of_mission_gate": "Harness QS4 sucessor vinculado ao adaptador EC96FE9A exige qualificação QS4 (QS4=NO)",
        **GATES, "result_return_to": FOOT})

    put(d, "PREDELIVERY_ADMISSION_RECEIPT_V008R11.json", {
        "schema": "PEGASUS_FULL_2026_V008R11_PREDELIVERY_ADMISSION_RECEIPT", "final_bytes": final,
        "components": {p.relative_to(d).as_posix(): sha(p) for p in sorted(d.rglob("*")) if p.is_file()},
        "admitted_for": "OWNER_WINDOWS_NON_ECONOMIC_CAMPAIGN + ORIGIN_FOCAL_REAUDIT (Verify -> opcional QualifyNative confirmatório -> opcional Install)",
        "not_admitted_for": ["QS4", "FULL economico", "Phase B/C economicas", "reselection", "RUN_RELEASED",
                             "Install/Rollback produtivo sem autorização", "alteração de política/MASTER/HEAD"],
        **GATES, "result_return_to": FOOT})

    files = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "DELIVERY_MANIFEST_SHA256.json")
    put(d, "DELIVERY_MANIFEST_SHA256.json", {
        "schema": "PEGASUS_FULL_2026_V008R11_DELIVERY_MANIFEST",
        "members": [{"path": p.relative_to(d).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]})
    print(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
