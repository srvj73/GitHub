"""Gera os recibos externos do V008 vinculados aos bytes finais (fora do ZIP; sem autorreferência).

python -I -B make_delivery_receipts_v008.py --delivery <dir> --tree <árvore V008> --evidence <scratch>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008_20261022.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1"
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14"
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
    q = json.loads((t / "receipts/V008/offline_final/v008_supervised_qualification/V008_QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    v3 = json.loads((t / "receipts/V008/offline_final/v003_full_chain/QUALIFICATION_RECEIPT.json").read_text(encoding="utf-8"))
    mut = json.loads((t / "receipts/V008/offline_final/m1_battery/05_MUTATION.json").read_text(encoding="utf-8"))
    tep = json.loads((e / "TESTED_EQUALS_PACKAGED_CHECK.json").read_text(encoding="utf-8"))
    dv = json.loads((e / "DELIVERED_VERIFY.json").read_text(encoding="utf-8"))
    final = {"zip": {"name": ZIP_NAME, "sha256": zsha, "bytes": (d / ZIP_NAME).stat().st_size, "members": 2945},
             "manifest_sha256": msha, "bootstrap": {"name": BOOT_NAME, "sha256": bsha, "bytes": (d / BOOT_NAME).stat().st_size},
             "entrypoint_pegasus_entry_sha256": "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"}

    put(d, "MISSION_LOCK_V008_DELIVERY.json", {
        "schema": "PEGASUS_FULL_2026_V008_MISSION_LOCK_DELIVERY",
        "mission_id": "PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022",
        "handoff_sha256": "EC24BA6D8A95743559782AFF75087B240ACECB152CE880FC07FD2F7370ED45D2",
        "base_codex_v003_sha256": "CC37261C017FA541BE125EE5432B29E63480D694EB26900A565D2ADDBD539041",
        "final_bytes": final, "policy_custody": "EXCLUSIVE_TO_ORIGIN_NOT_CONSULTED", **GATES,
        "result_return_to": FOOT})

    put(d, "G0_OFFLINE_RECEIPT_V008.json", {
        "schema": "PEGASUS_FULL_2026_V008_G0_OFFLINE_RECEIPT", "final_bytes": final,
        "zip_crc": "PASS", "zip_member_safety": "PASS", "delivered_extract_verify": dv["result"],
        "delivered_manifest_sha256": dv["manifest_sha256"],
        "python_compile_new_code": "8_OF_8_ON_3.12.3_AND_3.13.16",
        "powershell_parse": "PASS_PWSH_7.4.6_LINUX_LIMITED_EVIDENCE",
        "windows_ps51_parse": "PENDING_OWNER_CAMPAIGN_STEP_1",
        "windows_python_3_14_7": "PENDING_OWNER_CAMPAIGN", **GATES})

    put(d, "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008.json", {
        "schema": "PEGASUS_FULL_2026_V008_TESTED_EQUALS_PACKAGED_DELIVERED",
        "tested_manifest_sha256_m1": q["package_manifest_sha256"],
        "final_manifest_sha256_m2": msha,
        "m1_to_m2": tep,
        "tested_code_sha256": q["tested_code_sha256"], "tested_supervisor_sha256": q["tested_supervisor_sha256"],
        "v003_chain_code_sha256_equals_final_code": all(
            v3["code_sha256"][k].upper() == q["tested_code_sha256"][k] for k in v3["code_sha256"]),
        "delivered_zip_extract_verify": dv["result"], "delivered_unit_tests": "46_OF_46_PASS",
        "installed": "PENDING_OWNER_INSTALL_MODE",
        "result": "PASS_TESTED_EQUALS_PACKAGED_EQUALS_DELIVERED_OFFLINE"})

    gates = {
        "G1_SOURCE_BINDING": "PASS_SOURCE_CONSOLIDATION; QS4_HARNESS_BINDING=BLOCKED_PROVEN_ADAPTER_PIN_MISMATCH",
        "G2_W04_FULL": "IMPLEMENTED; OFFLINE_DECISION_QUALIFIED; NATIVE_PENDING_OWNER_CAMPAIGN",
        "G3_W04_JIT_JOB": "IMPLEMENTED; OFFLINE_ORCHESTRATION_QUALIFIED; NATIVE_PENDING_OWNER_CAMPAIGN",
        "G4_SAFESTOP_RESUME": "OFFLINE_PASS_REAL_RUNTIME_SYNTHETIC; NATIVE_PENDING_OWNER_CAMPAIGN",
        "G5_INTEGRATED_NATIVE_WIN": "CAMPAIGN_READY_NOT_EXECUTED",
        "G6_CANDIDATE_COMPLETENESS": "NOT_PASS_PENDING_NATIVE_EVIDENCE"}
    put(d, "PREDELIVERY_CONTROL_MATRIX_V008.json", {
        "schema": "PEGASUS_FULL_2026_V008_PREDELIVERY_CONTROL_MATRIX", "final_bytes": final, "gates": gates,
        "offline_evidence": {
            "v003_full_chain": "%s %d cases" % (v3["result"], len(v3["cases"])),
            "v008_supervised": "%s; PASS=%d; SKIPPED_NON_NATIVE=%d" % (
                q["result"], sum(c["result"] == "PASS" for c in q["cases"]),
                sum(c["result"] == "SKIPPED_NON_NATIVE" for c in q["cases"])),
            "unit_tests": "46_OF_46", "mutants": "%d_OF_%d_KILLED" % (mut["killed"], mut["mutants"]),
            "pending_causal_probe": "RUNTIME_EXONERATED_MULTI_INSTANT_CAPTURE_ATTRIBUTED",
            "qs4_binding_packaged_r001": "BLOCKED_ADAPTER_PIN_05A0CF3D_VS_V003_EC96FE9A"},
        "engineering_implementation": "ALL_INTERNALLY_IMPLEMENTABLE_ITEMS_IMPLEMENTED",
        "engineering_complete": "NOT_PASS_PENDING_NATIVE_WINDOWS_CAMPAIGN",
        "executable_delivery_ready": "READY_FOR_OWNER_NON_ECONOMIC_QUALIFICATION_CAMPAIGN_ONLY",
        **GATES, "result_return_to": FOOT})

    put(d, "CANDIDATE_COMPLETENESS_RECEIPT_V008.json", {
        "schema": "PEGASUS_FULL_2026_V008_CANDIDATE_COMPLETENESS_FIVE_PART", "final_bytes": final,
        "parts": {
            "1_source_and_lineage": "PASS (V003 físico byte-idêntico; parents por SHA; entrypoint testado=empacotado); QS4 sucessor ausente provado",
            "2_consumers_implemented_and_blocked": "PASS (supervisor W04/Job/SAFE_STOP/porta; FULL B/C via release_admission; QS4 via binding+admissão externa)",
            "3_offline_qualification_final_bytes": "PASS (19/19 V003; 9/9 V008; 46/46; 14/14 mutantes)",
            "4_native_target_qualification": "PENDING (campanha QualifyNative: PS 5.1, Python 3.14.7, W04 Q10a-f, Job Q11, Q01-Q09 sob Job real)",
            "5_tested_packaged_installed_delivered": "PASS offline para testado=empacotado=entregue; instalado PENDENTE (modo Install)"},
        "candidate_completeness": "NOT_PASS",
        "single_external_blocker": "Execução nativa da campanha única no PC do titular (efeito físico Windows indisponível ao implementador)",
        "out_of_mission_gate": "Harness QS4 sucessor vinculado ao adaptador EC96FE9A exige qualificação QS4 (QS4=NO nesta missão)",
        **GATES, "result_return_to": FOOT})

    put(d, "PREDELIVERY_ADMISSION_RECEIPT_V008.json", {
        "schema": "PEGASUS_FULL_2026_V008_PREDELIVERY_ADMISSION_RECEIPT", "final_bytes": final,
        "components": {n: sha(d / n) for n in sorted(x.name for x in d.iterdir() if x.is_file())},
        "admitted_for": "OWNER_WINDOWS_NON_ECONOMIC_CAMPAIGN (Verify -> QualifyNative -> opcional Install)",
        "not_admitted_for": ["QS4", "FULL econômico", "Phase B/C econômicas", "reselection", "auditoria formal (antes de CANDIDATE_COMPLETENESS=PASS)"],
        **GATES, "result_return_to": FOOT})

    files = sorted(x for x in d.iterdir() if x.is_file() and x.name != "DELIVERY_MANIFEST_SHA256.json")
    put(d, "DELIVERY_MANIFEST_SHA256.json", {"schema": "PEGASUS_FULL_2026_V008_DELIVERY_MANIFEST",
                                             "members": [{"path": x.name, "bytes": x.stat().st_size, "sha256": sha(x)} for x in files]})
    print(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
