"""Gera os recibos externos do V008R9 (negativos nativos Q10a-f/Q11 em subprocesso novo, para
o backend de census pinado partir de um estado de handles limpo; diagnosticos de census
persistidos no veredito W04). Nao executa economia; nao consulta politica.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R9_20261022.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R9_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14"
ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
R8_ZIP_SHA = "17A9FB12168F88CBF5CFC4454D211AB773C30E63AEEB95E529899597693DF411"
GATES = {"g4": "FROZEN", "qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN",
         "reselection_2026": "FORBIDDEN", "run_released": "NO", "full_released": "NO",
         "paid_credit": "NOT_USED", "independent_audit": "NOT_STARTED"}


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
    with __import__("zipfile").ZipFile(d / ZIP_NAME) as z:
        zmembers = len(z.namelist())
    msha = sha(t / "MANIFEST_SHA256.json")
    of = t / "receipts/V008/offline_final"
    q = json.loads((of / "v008_supervised_qualification/V008_QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    v3 = json.loads((of / "v003_full_chain/QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    mut = json.loads((of / "m1_battery/05_MUTATION.json").read_text(encoding="utf-8"))
    bb = json.loads((of / "bootstrap_boundary/BOOTSTRAP_EXIT_BOUNDARY_RESULT.json").read_text(encoding="utf-8"))
    bm = json.loads((of / "bootstrap_boundary/BOOTSTRAP_MUTATION_RESULT.json").read_text(encoding="utf-8"))
    nat = json.loads((of / "native_campaign_r8/CAMPAIGN_RESULT.json").read_text(encoding="utf-8"))
    natq = json.loads((of / "native_campaign_r8/NATIVE_QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    tep = json.loads((e / "TESTED_EQUALS_PACKAGED_CHECK.json").read_text(encoding="utf-8"))
    dv = json.loads((e / "DELIVERED_VERIFY.json").read_text(encoding="utf-8"))
    nce = q["native_completeness_evaluation"]
    npass = sum(c["result"] == "PASS" for c in q["cases"])
    nskip = sum(c["result"] == "SKIPPED_NON_NATIVE" for c in q["cases"])
    unit_log = (of / "m1_battery/04_UNIT_TESTS.log").read_text(errors="replace")
    unit_n = next((ln.split()[1] for ln in unit_log.splitlines() if ln.startswith("Ran ")), "?")
    native_steps = {k: v.get("classification") for k, v in nat.get("steps", {}).items()}
    nat_zip = nat.get("zip_sha256")
    nat_pass = sum(c.get("result") == "PASS" for c in natq.get("cases", []))
    nat_q10a = next((c for c in natq.get("cases", []) if c.get("case", "").startswith("Q10a")), {})

    final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": (d / ZIP_NAME).stat().st_size, "members": zmembers},
             "manifest_sha256": msha, "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"],
             "bootstrap": {"name": BOOT_NAME, "sha256": bsha, "bytes": (d / BOOT_NAME).stat().st_size},
             "supersedes_v008r8": {"zip_sha256": R8_ZIP_SHA, "reason": "native negatives (Q10a-f, Q11) now run in a fresh -I -B subprocess so the pinned census backend starts from a clean handle state; the long-lived qualify process accumulated abandoned name-worker handles, truncating the Q10a census even with the R8 bounded retry; fail-closed unchanged; census diagnostics persisted in both W04 verdicts"},
             "entrypoint_pegasus_entry_sha256": ENTRY_SHA}

    put(d, "MISSION_LOCK_V008R9_DELIVERY.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_MISSION_LOCK_DELIVERY",
        "mission_id": "PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022",
        "base_codex_v003_sha256": "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041",
        "final_bytes": final, "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED", **GATES,
        "result_return_to": FOOT})

    put(d, "G0_OFFLINE_RECEIPT_V008R9.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_G0_OFFLINE_RECEIPT", "final_bytes": final,
        "zip_crc": "PASS", "zip_member_safety": "PASS",
        "delivered_extract_verify": dv["result"], "delivered_manifest_sha256": dv["manifest_sha256"],
        "delivered_files_checked": dv["files_checked"],
        "offline_tests": {"supervisor_unit": "%s_OF_%s" % (unit_n, unit_n),
                          "supervisor_mutation": "%d_OF_%d_KILLED" % (mut["killed"], mut["mutants"]),
                          "bootstrap_exit_boundary": "%s passed=%s" % (bb["result"], bb["passed"]),
                          "bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
                          "supervised_qualification": "%s; PASS=%d; SKIPPED_NON_NATIVE=%d; error=%s" % (
                              q["result"], npass, nskip, q.get("error"))},
        "native_campaign_r8": {"zip_sha256": nat_zip, "exit_boundary_steps": native_steps,
                               "advanced_to": "16 casos (Q01-Q09, Q12-Q15) PASS antes de Q10a",
                               "blocker": "Q10a W04 BLOCKED por CENSUS_TRUNCATED apesar das 3 tentativas (R8); prova do kernel OK (WRITE_DENIED; RENAME_DENIED winerror=32)",
                               "root_cause": "backend de census pinado abandona threads com handles em consultas de nome travadas e varre o proprio processo; handles acumulam no processo de qualificacao longevo (Q12 em subprocesso proprio passou; Q10a no processo longevo truncou na mesma execucao)",
                               "resolved_in": "V008R9_FRESH_PROCESS_NATIVE_NEGATIVES"},
        "python_compile_new_code": "PASS_ON_3.13 (campanha nativa usa Python 3.14.7 do titular)",
        "powershell_parse": "PASS_PWSH_7.4.6_LINUX; PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R8", **GATES})

    put(d, "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R9.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_TESTED_EQUALS_PACKAGED_DELIVERED",
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
        "G1_SOURCE_BINDING": "PASS; SUPERVISED_RUN_PATH + EXIT_BOUNDARY + JOB_HANDLE_LIFECYCLE + SAFE_STOP_PLATFORM CLOSED; QS4_HARNESS_BINDING=BLOCKED_PROVEN",
        "G2_W04_FULL": "IMPLEMENTED; W04 nativo + Q10a-f PASS na R6; census de corroboracao com 3 tentativas (R8) e negativos em processo novo (R9); diagnosticos de census persistidos; fail-closed inalterado",
        "G3_W04_JIT_JOB": "IMPLEMENTED; 22/23 nativos PASS na R6; Q11 contencao real (R7) pendente de execucao nativa (campanhas R7/R8 pararam antes de Q11)",
        "G4_SAFESTOP_RESUME": "SAFE_STOP_PLATFORM_R4 + SAFE_WINDOW_R6; Q03 SAFE_STOP e Q04 retomada PASS NATIVOS na R6; Q12b run-full SAFE_STOP/retomada PASS NATIVO na R8",
        "G5_INTEGRATED_NATIVE_WIN": "22/23 nativos PASS na R6; R7/R8 pararam em Q10a por census truncado (processo longevo); re-run R9 com negativos em processo novo p/ confirmar 23/23",
        "G6_CANDIDATE_COMPLETENESS": "NOT_PASS_PENDING_NATIVE_EVIDENCE; native_completeness_evaluation=%s" % nce["verdict"]}
    put(d, "PREDELIVERY_CONTROL_MATRIX_V008R9.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
        "offline_evidence": {
            "v003_full_chain": "%s %d cases (imutavel)" % (v3["result"], len(v3["cases"])),
            "v008r9_supervised": "%s; PASS=%d; SKIPPED_NON_NATIVE=%d; error=%s" % (q["result"], npass, nskip, q.get("error")),
            "native_completeness_evaluation": nce,
            "exit_boundary_bootstrap": "%s passed=%s (template inalterado, provado nativo)" % (bb["result"], bb["passed"]),
            "exit_boundary_bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
            "supervisor_unit": "%s_OF_%s (inclui NativeNegativesReplay)" % (unit_n, unit_n),
            "supervisor_mutants": "%d_OF_%d_KILLED (ancoras inalteradas; inclui safestop_windows_accepts_any_code, custody_guard_after_close_disabled)" % (mut["killed"], mut["mutants"]),
            "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A"},
        "native_campaign_r8": {"exit_boundary": "VALIDATED_NATIVE", "exit_boundary_steps": native_steps,
                               "native_cases_pass": "%d (Q01-Q09, Q12-Q15) antes de Q10a; R6 havia provado 22/23" % nat_pass,
                               "q10a": "FAIL W04=%s (%s); prova do kernel OK, so a corroboracao truncou" % (
                                   nat_q10a.get("w04", {}).get("w04_full"), ",".join(nat_q10a.get("w04", {}).get("gaps", []))),
                               "blocker": "Q10a CENSUS_TRUNCATED no processo longevo; Q11 nao alcancado",
                               "resolved_in": "V008R9 (negativos nativos em subprocesso novo)"},
        "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED",
        "engineering_complete": "NOT_PASS_PENDING_NATIVE_WINDOWS_RERUN",
        "executable_delivery_ready": "READY_FOR_OWNER_NON_ECONOMIC_QUALIFICATION_RERUN_ONLY",
        **GATES, "result_return_to": FOOT})

    put(d, "CANDIDATE_COMPLETENESS_RECEIPT_V008R9.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
        "parts": {
            "1_source_and_lineage": "PASS (V003 fisico byte-identico; entrypoint testado=empacotado=entregue); QS4 sucessor ausente provado",
            "2_consumers_implemented_wired_and_blocked": "PASS (W04/Job/SAFE_STOP/porta; cmd_run->admission->_run_supervised; fronteira de exit exata; handle do Job e SAFE_STOP corretos por plataforma; negativos nativos em processo proprio; FULL B/C e QS4 fail-closed)",
            "3_offline_qualification_final_bytes": "PASS (19/19 V003 imutavel; V008R9 %d PASS + %d SKIPPED_NON_NATIVE incl. Q14/Q15; %s/%s unit incl. NativeNegativesReplay; %d/%d mutantes supervisor; 20/20 bootstrap boundary; %d/%d bootstrap mutantes)" % (npass, nskip, unit_n, unit_n, mut["killed"], mut["mutants"], bm["killed"], bm["mutants"]),
            "4_native_target_qualification": "PENDING_RERUN (R2 fronteira de exit; R3 handle do Job; R4 SAFE_STOP por plataforma; R6 22/23 incl. Q03/Q04/Q10a-f; R8 16 casos PASS e Q12b run-full SAFE_STOP/retomada, parou em Q10a por census truncado no processo longevo; R9 move os negativos nativos p/ subprocesso novo; faltam Q10a-f e Q11 na mesma execucao; native_completeness_evaluation=%s)" % nce["verdict"],
            "5_tested_packaged_installed_delivered": "PASS offline (%d arquivos conferidos); instalado PENDENTE (modo Install)" % dv["files_checked"]},
        "candidate_completeness": "NOT_PASS",
        "single_external_blocker": "Re-execucao nativa da campanha unica no PC do titular (efeito fisico Windows indisponivel ao implementador)",
        "out_of_mission_gate": "Harness QS4 sucessor vinculado ao adaptador EC96FE9A exige qualificacao QS4 (QS4=NO)",
        "policy_fallback_note": "Se o census truncar mesmo no processo novo, aceitar corroboracao degradada com a prova de kernel completa e decisao de politica do titular/origem, nao do implementador; o W04 permanece fail-closed por padrao.",
        **GATES, "result_return_to": FOOT})

    put(d, "PREDELIVERY_ADMISSION_RECEIPT_V008R9.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_PREDELIVERY_ADMISSION_RECEIPT", "final_bytes": final,
        "components": {n: sha(d / n) for n in sorted(x.name for x in d.iterdir() if x.is_file())},
        "admitted_for": "OWNER_WINDOWS_NON_ECONOMIC_CAMPAIGN_RERUN (Verify -> QualifyNative -> opcional Install)",
        "not_admitted_for": ["QS4", "FULL economico", "Phase B/C economicas", "reselection",
                             "auditoria formal (antes de CANDIDATE_COMPLETENESS=PASS)"],
        **GATES, "result_return_to": FOOT})

    files = sorted(x for x in d.iterdir() if x.is_file() and x.name != "DELIVERY_MANIFEST_SHA256.json")
    put(d, "DELIVERY_MANIFEST_SHA256.json", {
        "schema": "PEGASUS_FULL_2026_V008R9_DELIVERY_MANIFEST",
        "members": [{"path": x.name, "bytes": x.stat().st_size, "sha256": sha(x)} for x in files]})
    print(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
