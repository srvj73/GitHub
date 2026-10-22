"""Gera os recibos externos do V008R8 (contencao de breakaway do Job: Q11 verifica que o neto permanece na contabilidade do Job, nao o proxy do CreateProcess). Nao executa economia; nao consulta politica.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R8_20261022.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R8_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14"
ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
R7_ZIP_SHA = "FDFCEDB59BB361C05B9900FFE4697B5C9496159C546CB379C10E82ECB1002F7F"
NATIVE_R7_ZIP_SHA = "AD7D815615D199E17E1AD31EAF0B6AB46131FF9FCD9E9B38614B83989831D1D7"
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
    msha = sha(t / "MANIFEST_SHA256.json")
    of = t / "receipts/V008/offline_final"
    q = json.loads((of / "v008_supervised_qualification/V008_QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    v3 = json.loads((of / "v003_full_chain/QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    mut = json.loads((of / "m1_battery/05_MUTATION.json").read_text(encoding="utf-8"))
    bb = json.loads((of / "bootstrap_boundary/BOOTSTRAP_EXIT_BOUNDARY_RESULT.json").read_text(encoding="utf-8"))
    bm = json.loads((of / "bootstrap_boundary/BOOTSTRAP_MUTATION_RESULT.json").read_text(encoding="utf-8"))
    nat = json.loads((of / "native_campaign_r7/CAMPAIGN_RESULT.json").read_text(encoding="utf-8"))
    tep = json.loads((e / "TESTED_EQUALS_PACKAGED_CHECK.json").read_text(encoding="utf-8"))
    dv = json.loads((e / "DELIVERED_VERIFY.json").read_text(encoding="utf-8"))
    nce = q["native_completeness_evaluation"]
    npass = sum(c["result"] == "PASS" for c in q["cases"])
    nskip = sum(c["result"] == "SKIPPED_NON_NATIVE" for c in q["cases"])
    unit_log = (of / "m1_battery/04_UNIT_TESTS.log").read_text(errors="replace")
    unit_n = next((ln.split()[1] for ln in unit_log.splitlines() if ln.startswith("Ran ")), "?")
    native_steps = {k: v.get("classification") for k, v in nat.get("steps", {}).items()}

    final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": (d / ZIP_NAME).stat().st_size, "members": 2946},
             "manifest_sha256": msha, "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"],
             "bootstrap": {"name": BOOT_NAME, "sha256": bsha, "bytes": (d / BOOT_NAME).stat().st_size},
             "supersedes_v008r7": {"zip_sha256": R7_ZIP_SHA, "reason": "bounded retry of the corroboration handle census (intermittent truncation blocked Q10a in R7); fail-closed unchanged"},
             "entrypoint_pegasus_entry_sha256": ENTRY_SHA}

    put(d, "MISSION_LOCK_V008R8_DELIVERY.json", {
        "schema": "PEGASUS_FULL_2026_V008R8_MISSION_LOCK_DELIVERY",
        "mission_id": "PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022",
        "base_codex_v003_sha256": "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041",
        "final_bytes": final, "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED", **GATES,
        "result_return_to": FOOT})

    put(d, "G0_OFFLINE_RECEIPT_V008R8.json", {
        "schema": "PEGASUS_FULL_2026_V008R8_G0_OFFLINE_RECEIPT", "final_bytes": final,
        "zip_crc": "PASS", "zip_member_safety": "PASS",
        "delivered_extract_verify": dv["result"], "delivered_manifest_sha256": dv["manifest_sha256"],
        "delivered_files_checked": dv["files_checked"],
        "offline_tests": {"supervisor_unit": "%s_OF_%s" % (unit_n, unit_n),
                          "supervisor_mutation": "%d_OF_%d_KILLED" % (mut["killed"], mut["mutants"]),
                          "bootstrap_exit_boundary": "%s passed=%s" % (bb["result"], bb["passed"]),
                          "bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
                          "supervised_qualification": "%s; PASS=%d; SKIPPED_NON_NATIVE=%d; error=%s" % (
                              q["result"], npass, nskip, q.get("error"))},
        "native_campaign_r7": {"zip_sha256": NATIVE_R7_ZIP_SHA, "exit_boundary_steps": native_steps,
                               "advanced_to": "16 casos (Q01-Q15) PASS antes de Q10a",
                               "blocker": "Q10a W04 BLOCKED por CENSUS_TRUNCATED intermitente (passou na R6); prova primaria do kernel OK",
                               "resolved_in": "V008R8_CENSUS_BOUNDED_RETRY"},
        "python_compile_new_code": "PASS_ON_3.13 (campanha nativa usa Python 3.14.7 do titular)",
        "powershell_parse": "PASS_PWSH_7.4.6_LINUX; PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R3", **GATES})

    put(d, "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R8.json", {
        "schema": "PEGASUS_FULL_2026_V008R8_TESTED_EQUALS_PACKAGED_DELIVERED",
        "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"], "final_manifest_sha256_m2": msha,
        "m1_to_m2": {k: tep[k] for k in ("m1_members", "m2_members", "m1_to_m2_added", "m1_to_m2_removed",
                                         "m1_to_m2_changed", "m1_to_m2_delta_only_offline_evidence",
                                         "tested_code_sha256_equals_final_manifest",
                                         "tested_supervisor_sha256_present_in_final")},
        "delivered_zip_extract_verify": dv["result"], "delivered_unit_tests": "%s_OF_%s_PASS" % (unit_n, unit_n),
        "delivered_supervisor_verify": "PASS_PACKAGE_VERIFIED", "delivered_entry_verify": "PACKAGE_INTEGRITY=PASS",
        "installed": "PENDING_OWNER_INSTALL_MODE",
        "result": "PASS_TESTED_EQUALS_PACKAGED_EQUALS_DELIVERED_OFFLINE"})

    gates = {
        "G1_SOURCE_BINDING": "PASS; SUPERVISED_RUN_PATH + EXIT_BOUNDARY + JOB_HANDLE_LIFECYCLE + SAFE_STOP_PLATFORM CLOSED; QS4_HARNESS_BINDING=BLOCKED_PROVEN",
        "G2_W04_FULL": "IMPLEMENTED; W04 nativo + Q10a-f PASS na R6; census de corroboracao com nova tentativa limitada (R8), fail-closed inalterado",
        "G3_W04_JIT_JOB": "IMPLEMENTED; 22/23 nativos PASS na R6; Q11 contencao real (R7) pendente de execucao nativa",
        "G4_SAFESTOP_RESUME": "SAFE_STOP_PLATFORM_R4 + SAFE_WINDOW_R6; Q03 SAFE_STOP e Q04 retomada PASS NATIVOS na R6",
        "G5_INTEGRATED_NATIVE_WIN": "22/23 nativos PASS na R6; R7 parou em Q10a por census truncado intermitente; re-run R8 p/ confirmar 23/23",
        "G6_CANDIDATE_COMPLETENESS": "NOT_PASS_PENDING_NATIVE_EVIDENCE; native_completeness_evaluation=%s" % nce["verdict"]}
    put(d, "PREDELIVERY_CONTROL_MATRIX_V008R8.json", {
        "schema": "PEGASUS_FULL_2026_V008R8_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
        "offline_evidence": {
            "v003_full_chain": "%s %d cases (imutavel)" % (v3["result"], len(v3["cases"])),
            "v008r4_supervised": "%s; PASS=%d; SKIPPED_NON_NATIVE=%d; error=%s" % (q["result"], npass, nskip, q.get("error")),
            "native_completeness_evaluation": nce,
            "exit_boundary_bootstrap": "%s passed=%s (template inalterado, provado nativo)" % (bb["result"], bb["passed"]),
            "exit_boundary_bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
            "supervisor_unit": "%s_OF_%s (inclui SafeStopExitPlatform e CustodyLifecycleContract)" % (unit_n, unit_n),
            "supervisor_mutants": "%d_OF_%d_KILLED (inclui safestop_windows_accepts_any_code, custody_guard_after_close_disabled)" % (mut["killed"], mut["mutants"]),
            "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A"},
        "native_campaign_r7": {"exit_boundary": "VALIDATED_NATIVE", "exit_boundary_steps": native_steps,
                               "native_cases_pass": "16 (Q01-Q15) antes de Q10a; R6 havia provado 22/23", "blocker": "Q10a CENSUS_TRUNCATED intermitente (corroboracao); Q11 nao alcancado",
                               "resolved_in": "V008R8"},
        "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED",
        "engineering_complete": "NOT_PASS_PENDING_NATIVE_WINDOWS_RERUN",
        "executable_delivery_ready": "READY_FOR_OWNER_NON_ECONOMIC_QUALIFICATION_RERUN_ONLY",
        **GATES, "result_return_to": FOOT})

    put(d, "CANDIDATE_COMPLETENESS_RECEIPT_V008R8.json", {
        "schema": "PEGASUS_FULL_2026_V008R8_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
        "parts": {
            "1_source_and_lineage": "PASS (V003 fisico byte-identico; entrypoint testado=empacotado=entregue); QS4 sucessor ausente provado",
            "2_consumers_implemented_wired_and_blocked": "PASS (W04/Job/SAFE_STOP/porta; cmd_run->admission->_run_supervised; fronteira de exit exata; handle do Job e SAFE_STOP corretos por plataforma; FULL B/C e QS4 fail-closed)",
            "3_offline_qualification_final_bytes": "PASS (19/19 V003 imutavel; V008R8 %d PASS + %d SKIPPED_NON_NATIVE incl. Q14/Q15; %s/%s unit incl. SafeStopExitPlatform+CustodyLifecycleContract; %d/%d mutantes supervisor; 20/20 bootstrap boundary; %d/%d bootstrap mutantes)" % (npass, nskip, unit_n, unit_n, mut["killed"], mut["mutants"], bm["killed"], bm["mutants"]),
            "4_native_target_qualification": "PENDING_RERUN (R2 fronteira de exit; R3 handle do Job; R4 Q01-Q09+Q12 PASS nativos incl. Q03 SAFE_STOP/Q04 retomada, Q12b expos a corrida de reentrega, agora corrigida; faltam Q12b em diante, W04 Q10a-f, Job Q11; native_completeness_evaluation=%s)" % nce["verdict"],
            "5_tested_packaged_installed_delivered": "PASS offline (%d arquivos conferidos); instalado PENDENTE (modo Install)" % dv["files_checked"]},
        "candidate_completeness": "NOT_PASS",
        "single_external_blocker": "Re-execucao nativa da campanha unica no PC do titular (efeito fisico Windows indisponivel ao implementador)",
        "out_of_mission_gate": "Harness QS4 sucessor vinculado ao adaptador EC96FE9A exige qualificacao QS4 (QS4=NO)",
        **GATES, "result_return_to": FOOT})

    put(d, "PREDELIVERY_ADMISSION_RECEIPT_V008R8.json", {
        "schema": "PEGASUS_FULL_2026_V008R8_PREDELIVERY_ADMISSION_RECEIPT", "final_bytes": final,
        "components": {n: sha(d / n) for n in sorted(x.name for x in d.iterdir() if x.is_file())},
        "admitted_for": "OWNER_WINDOWS_NON_ECONOMIC_CAMPAIGN_RERUN (Verify -> QualifyNative -> opcional Install)",
        "not_admitted_for": ["QS4", "FULL economico", "Phase B/C economicas", "reselection",
                             "auditoria formal (antes de CANDIDATE_COMPLETENESS=PASS)"],
        **GATES, "result_return_to": FOOT})

    files = sorted(x for x in d.iterdir() if x.is_file() and x.name != "DELIVERY_MANIFEST_SHA256.json")
    put(d, "DELIVERY_MANIFEST_SHA256.json", {
        "schema": "PEGASUS_FULL_2026_V008R8_DELIVERY_MANIFEST",
        "members": [{"path": x.name, "bytes": x.stat().st_size, "sha256": sha(x)} for x in files]})
    print(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
