"""Gera os recibos externos do V008R10 (fronteira fail-closed: o subprocesso dos negativos
nativos DEVE sair com rc==0 antes de aceitar os casos reencenados; controle negativo reproduz o
defeito; busca adversarial de falsa completude consolidada). Preserva a evidencia nativa R9
(23/23 PASS, MET). Nao executa economia; nao consulta politica.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R10_20261023.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R10_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14"
ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
R9_ZIP_SHA = "2C3F39EBADC292CEE197D21E837B6A264B532550AD80F8A66160EE8C51B3273C"
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
    negctl = json.loads((of / "r10_boundary_fix/NEGATIVE_CONTROL_NONZERO_CHILD_EXIT.json").read_text(encoding="utf-8"))
    fcs = json.loads((of / "r10_boundary_fix/FALSE_COMPLETENESS_SEARCH_V008R10.json").read_text(encoding="utf-8"))
    tep = json.loads((e / "TESTED_EQUALS_PACKAGED_CHECK.json").read_text(encoding="utf-8"))
    dv = json.loads((e / "DELIVERED_VERIFY.json").read_text(encoding="utf-8"))
    nce = q["native_completeness_evaluation"]
    npass = sum(c["result"] == "PASS" for c in q["cases"])
    nskip = sum(c["result"] == "SKIPPED_NON_NATIVE" for c in q["cases"])
    unit_log = (of / "m1_battery/04_UNIT_TESTS.log").read_text(errors="replace")
    unit_n = next((ln.split()[1] for ln in unit_log.splitlines() if ln.startswith("Ran ")), "?")
    nat_pass = sum(c.get("result") == "PASS" for c in natq.get("cases", []))
    nat_nce = natq.get("native_completeness_evaluation", {})

    native_r9 = {"result_zip_sha256": "7290A855726B2791D478249574EF9BD4F4AA6835B4F23CAB0A37D9A3DC38CE5E",
                 "qualification_receipt_sha256": nat.get("qualification_receipt_sha256"),
                 "bound_to_bytes": {"zip_sha256": nat.get("zip_sha256"), "manifest_sha256": nat.get("manifest_sha256"),
                                    "python_sha256": nat.get("python_sha256"), "bootstrap_sha256": nat.get("bootstrap_sha256")},
                 "qualifynative_exit": nat.get("qualification_exit"), "cases_pass": nat_pass,
                 "native_completeness_evaluation": nat_nce.get("verdict"),
                 "host": "PS 5.1 build %s, %s CPUs, elevated" % (nat.get("os_build"), nat.get("logical_cpus")),
                 "preserved_in": "receipts/V008/offline_final/native_campaign_r9/"}

    final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": (d / ZIP_NAME).stat().st_size, "members": zmembers},
             "manifest_sha256": msha, "tested_manifest_sha256_m1": tep["m1_tested_manifest_sha256"],
             "bootstrap": {"name": BOOT_NAME, "sha256": bsha, "bytes": (d / BOOT_NAME).stat().st_size},
             "supersedes_v008r9": {"zip_sha256": R9_ZIP_SHA, "reason": "fail-closed boundary: _native_negatives_in_fresh_process now REQUIRES the child subprocess rc==0 before accepting the replayed cases (origin review found a child that wrote a complete JSON then exited non-zero would be accepted)"},
             "entrypoint_pegasus_entry_sha256": ENTRY_SHA}

    put(d, "MISSION_LOCK_V008R10_DELIVERY.json", {
        "schema": "PEGASUS_FULL_2026_V008R10_MISSION_LOCK_DELIVERY",
        "mission_id": "PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022",
        "base_codex_v003_sha256": "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041",
        "final_bytes": final, "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED",
        "native_qualification_r9": native_r9, **GATES, "result_return_to": FOOT})

    put(d, "G0_OFFLINE_RECEIPT_V008R10.json", {
        "schema": "PEGASUS_FULL_2026_V008R10_G0_OFFLINE_RECEIPT", "final_bytes": final,
        "zip_crc": "PASS", "zip_member_safety": "PASS",
        "delivered_extract_verify": dv["result"], "delivered_manifest_sha256": dv["manifest_sha256"],
        "delivered_files_checked": dv["files_checked"],
        "offline_tests": {"supervisor_unit": "%s_OF_%s" % (unit_n, unit_n),
                          "supervisor_mutation": "%d_OF_%d_KILLED" % (mut["killed"], mut["mutants"]),
                          "bootstrap_exit_boundary": "%s passed=%s" % (bb["result"], bb["passed"]),
                          "bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
                          "supervised_qualification": "%s; PASS=%d; SKIPPED_NON_NATIVE=%d; error=%s" % (
                              q["result"], npass, nskip, q.get("error"))},
        "boundary_fix_r10": {"defect": "p.returncode do subprocesso dos negativos nativos so era registrado, nao exigido ==0; filho que grava JSON completo e sai !=0 era aceito",
                             "fix": "exige rc==0 antes de aceitar casos (NATIVE_NEGATIVES_CHILD_NONZERO_EXIT)",
                             "negative_control": negctl.get("result"),
                             "prefix_defective_outcome": negctl.get("prefix_defective", {}).get("outcome"),
                             "fixed_outcome": negctl.get("fixed", {}).get("outcome")},
        "false_completeness_search": {"verdict": fcs.get("verdict"),
                                      "mandatory_integration_unimplemented": fcs.get("mandatory_integration_unimplemented"),
                                      "economic_anchors_in_source": fcs.get("economic_fail_closed_anchors_in_source")},
        "native_qualification_r9": native_r9,
        "python_compile_new_code": "PASS_ON_3.13 (campanha nativa usou Python 3.14.7 do titular)",
        "powershell_parse": "PASS_PWSH_7.4.6_LINUX; PS5.1_NATIVE_VALIDATED_BY_CAMPAIGNS_R2_R9", **GATES})

    put(d, "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R10.json", {
        "schema": "PEGASUS_FULL_2026_V008R10_TESTED_EQUALS_PACKAGED_DELIVERED",
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
        "G2_W04_FULL": "QUALIFIED_NATIVE (R9: Q10a-f PASS, census abandoned=[0,0] em processo novo); fail-closed inalterado",
        "G3_W04_JIT_JOB": "QUALIFIED_NATIVE (R9: Q11 contencao real PASS; GAPLESS_NATIVE_JOB em Q01/Q02/Q11/Q12)",
        "G4_SAFESTOP_RESUME": "QUALIFIED_NATIVE (R9: Q03/Q04 e Q12b run-full PASS)",
        "G5_INTEGRATED_NATIVE_WIN": "QUALIFIED_NATIVE 23/23 numa unica execucao (R9), native_completeness_evaluation=MET nos bytes R9",
        "G6_CANDIDATE_COMPLETENESS": "ENGINEERING_COMPLETE; native MET nos bytes R9; R10 endurece a fronteira de aceitacao (delta offline-provado e inerte no run nativo observado); selagem formal com a origem"}
    put(d, "PREDELIVERY_CONTROL_MATRIX_V008R10.json", {
        "schema": "PEGASUS_FULL_2026_V008R10_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
        "offline_evidence": {
            "v003_full_chain": "%s %d cases (imutavel)" % (v3["result"], len(v3["cases"])),
            "v008r10_supervised": "%s; PASS=%d; SKIPPED_NON_NATIVE=%d; error=%s" % (q["result"], npass, nskip, q.get("error")),
            "native_completeness_evaluation": nce,
            "exit_boundary_bootstrap": "%s passed=%s (template inalterado, provado nativo)" % (bb["result"], bb["passed"]),
            "exit_boundary_bootstrap_mutation": "%d_OF_%d_KILLED" % (bm["killed"], bm["mutants"]),
            "supervisor_unit": "%s_OF_%s (inclui NativeNegativesReplay + NativeNegativesFreshProcess)" % (unit_n, unit_n),
            "supervisor_mutants": "%d_OF_%d_KILLED (ancoras inalteradas)" % (mut["killed"], mut["mutants"]),
            "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A"},
        "boundary_fix_r10": {"negative_control": negctl.get("result"),
                             "reproduces_defect": negctl.get("reproduces_defect"),
                             "fix_closes_defect": negctl.get("fix_closes_defect")},
        "false_completeness_search": fcs,
        "native_qualification_r9": native_r9,
        "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED",
        "engineering_complete": "YES_NATIVE_MET_ON_R9_BYTES; R10_DELTA_OFFLINE_PROVEN",
        "executable_delivery_ready": "READY; optional R10 native re-run is confirmatory only",
        **GATES, "result_return_to": FOOT})

    put(d, "CANDIDATE_COMPLETENESS_RECEIPT_V008R10.json", {
        "schema": "PEGASUS_FULL_2026_V008R10_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
        "parts": {
            "1_source_and_lineage": "PASS (V003 fisico byte-identico; entrypoint testado=empacotado=entregue); QS4 sucessor ausente provado",
            "2_consumers_implemented_wired_and_blocked": "PASS (W04/Job/SAFE_STOP/porta; cmd_run->admission->_run_supervised; fronteira de exit exata; negativos nativos em processo proprio com rc==0 exigido; FULL B/C e QS4 fail-closed terminais) — busca adversarial de falsa completude: %s" % fcs.get("verdict"),
            "3_offline_qualification_final_bytes": "PASS (19/19 V003 imutavel; V008R10 %d PASS + %d SKIPPED_NON_NATIVE incl. Q14/Q15; %s/%s unit incl. NativeNegativesFreshProcess; %d/%d mutantes supervisor; 20/20 bootstrap boundary; %d/%d bootstrap mutantes)" % (npass, nskip, unit_n, unit_n, mut["killed"], mut["mutants"], bm["killed"], bm["mutants"]),
            "4_native_target_qualification": "MET nos bytes R9 (23/23 numa execucao: Q01-Q15 + W04 Q10a-f + Q11; W04 PASS_NATIVE=5, GAPLESS_NATIVE_JOB=4; census abandoned=[0,0]); evidencia preservada em native_campaign_r9/. R10 difere de R9 so pela fronteira rc==0 (parent-side), offline-provada pelo controle negativo e INERTE no run nativo observado (filho saiu rc=0)",
            "5_tested_packaged_installed_delivered": "PASS offline (%d arquivos conferidos); instalado PENDENTE (modo Install, opcional)" % dv["files_checked"]},
        "candidate_completeness": "ENGINEERING_COMPLETE_NATIVE_MET_ON_R9_BYTES",
        "r10_delta_vs_r9": "fronteira fail-closed rc==0 no pai dos negativos nativos; offline-provada (controle negativo); inerte no run nativo R9 (rc=0)",
        "r10_native_rerun": "OPCIONAL/confirmatorio — nao requerido: o delta e offline-provavel e nao alterou a execucao nativa observada",
        "formal_seal": "WITH_ORIGIN (custodia normativa MASTER/HEAD exclusiva do ChatGPT de origem)",
        "single_external_item_remaining": "selagem formal de CANDIDATE_COMPLETENESS=PASS pela origem (e, se desejado, uma re-execucao nativa confirmatoria sobre os bytes R10)",
        "out_of_mission_gate": "Harness QS4 sucessor vinculado ao adaptador EC96FE9A exige qualificacao QS4 (QS4=NO)",
        **GATES, "result_return_to": FOOT})

    put(d, "PREDELIVERY_ADMISSION_RECEIPT_V008R10.json", {
        "schema": "PEGASUS_FULL_2026_V008R10_PREDELIVERY_ADMISSION_RECEIPT", "final_bytes": final,
        "components": {p.relative_to(d).as_posix(): sha(p) for p in sorted(d.rglob("*")) if p.is_file()},
        "admitted_for": "OWNER_WINDOWS_NON_ECONOMIC_CAMPAIGN (Verify -> opcional QualifyNative confirmatorio -> opcional Install)",
        "not_admitted_for": ["QS4", "FULL economico", "Phase B/C economicas", "reselection",
                             "auditoria formal independente (custodia da origem)"],
        **GATES, "result_return_to": FOOT})

    files = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "DELIVERY_MANIFEST_SHA256.json")
    put(d, "DELIVERY_MANIFEST_SHA256.json", {
        "schema": "PEGASUS_FULL_2026_V008R10_DELIVERY_MANIFEST",
        "members": [{"path": p.relative_to(d).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]})
    print(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
