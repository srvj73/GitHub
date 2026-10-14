"""Owner-local static prohibition checks; never imports or executes the runner.

This bounded scanner is supporting evidence, not an independent release audit.
"""
import ast
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent


def scan():
    source=(HERE/"tickstore_serial_runner.py").read_text(encoding="utf-8")
    launcher=(HERE/"run_tickstore_full_serial_r9.ps1").read_text(encoding="utf-8-sig")
    tree=ast.parse(source)
    constants={node.targets[0].id:ast.literal_eval(node.value)
               for node in tree.body if isinstance(node,ast.Assign) and len(node.targets)==1
               and isinstance(node.targets[0],ast.Name) and isinstance(node.value,ast.Constant)}
    functions={node.name:node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    forbidden=("ThreadPoolExecutor","ProcessPoolExecutor","multiprocessing","concurrent.futures",
               "os.cpu_count","threading.Thread","ThreadPool","Pool(","Start-Job","ForEach-Object -Parallel")
    options=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=="add_argument":
            options.extend(a.value for a in node.args if isinstance(a,ast.Constant) and isinstance(a.value,str))
    orchestration=ast.get_source_segment(source,functions["_execute_full_serial"])
    reconciliation=functions["reconcile_full_readonly"]
    inventory_lines=sorted(n.lineno for n in ast.walk(reconciliation) if isinstance(n,ast.Call)
                           and isinstance(n.func,ast.Name) and n.func.id=="_full_artifact_inventory")
    manifest_lines=sorted(n.lineno for n in ast.walk(reconciliation) if isinstance(n,ast.Call)
                          and isinstance(n.func,ast.Name) and n.func.id=="_full_manifest")
    shadow_lines=[n.lineno for n in ast.walk(reconciliation) if isinstance(n,ast.If)
                  and "mp.with_suffix" in ast.unparse(n.test) and "strict_lstat" in ast.unparse(n.test)]
    seal=ast.get_source_segment(source,functions["FullSourceFinalSeal"])
    cleanup_scopes=[n for n in functions["_execute_full_serial"].body if isinstance(n,ast.Try)
                    and any(isinstance(c,ast.Call) and ast.unparse(c.func)=="seal.close"
                            for statement in n.finalbody for c in ast.walk(statement))]
    template=json.loads((HERE/"FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json").read_text(encoding="utf-8"))
    gate_fields={"schema","authorized","runner_schema","runner_sha256","reference_sha256",
                 "full_spec_sha256","full_plan_sha256","full_plan_contract_sha256","ledger_sha256",
                 "gate_b_certificate_sha256","source_root","dest_root","scratch_root",
                 "source_volume","dest_volume","scratch_volume"}
    public=functions["run_full_serial"]
    first=public.body[0]
    release_entry=ast.get_source_segment(source,public)
    release_calls={}
    for node in ast.walk(public):
        if isinstance(node,ast.Call):
            name=ast.unparse(node.func)
            release_calls.setdefault(name,[]).append(node.lineno)
    gate_functions=[functions[name] for name in (
        "validate_full_gate_arguments","full_gate_bindings","validate_full_owner_gate","run_full_serial"
    )]
    gate_mutators=[]
    for fn in gate_functions:
        for node in ast.walk(fn):
            if isinstance(node,ast.Call):
                name=ast.unparse(node.func)
                if (name in ("atomic_write_json","atomic_write_bytes","write_transaction_json",
                             "secure_create_new_fd","open","json.dump")
                        or name.endswith((".write_text",".write_bytes",".open"))):
                    gate_mutators.append(name)
    authorized_gate_json=[]
    for path in HERE.rglob("*.json"):
        try:obj=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,UnicodeError,json.JSONDecodeError):continue
        if isinstance(obj,dict) and obj.get("authorized") is True:
            authorized_gate_json.append(str(path.relative_to(HERE)))
    launcher_parameters=("SourceRoot","DestRoot","ScratchRoot","LedgerZip","FullGateFile","FullGateSha256")
    full_nodes=[node for name,node in functions.items() if name.startswith("_full") or name.startswith("full_")
                or name in ("FullSerialSourceView","FullSerialMonth","FullSourceFinalSeal","FullSerialLockBoundary","validate_full_plan","validate_full_owner_gate",
                            "validate_certified_r8_day","reconcile_full_readonly","run_full_serial","_execute_full_serial")]
    forbidden_mutators=[]
    for fn in full_nodes:
        for node in ast.walk(fn):
            if isinstance(node,ast.Call):
                name=ast.unparse(node.func)
                if name in ("safe_unlink_regular","discard_uncommitted","secure_replace","os.remove","os.unlink","shutil.rmtree") or name.endswith(".unlink"):
                    forbidden_mutators.append(name)
    checks={
        "R9_RELEASE_RC1_IDENTITY":constants.get("RUNNER_SCHEMA")=="TICKSTORE_SERIAL_RUNNER_V001R9_FULL_SERIAL_RELEASE_RC1",
        "FULL_SERIAL_RELEASE_CAPABILITY":constants.get("FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE") is True,
        "FULL_HISTORY_HARD_FALSE":constants.get("FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE") is False,
        "PUBLIC_ENTRY_CAPABILITY_GUARD":isinstance(first,ast.If) and ast.unparse(first.test)=="not FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE"
                                        and isinstance(first.body[0],ast.Raise),
        "GATE_SYNTAX_BEFORE_RELEASE_ACCESS":release_entry.index("validate_full_gate_arguments(")
                                             <release_entry.index("require_windows_pilot_runtime(")
                                             <release_entry.index("load_ledgers("),
        "OWNER_GATE_BEFORE_FULL_DISPATCH":release_calls.get("validate_full_owner_gate",[10**9])[0]
                                           <release_calls.get("_execute_full_serial",[-1])[0],
        "NO_OWNER_GATE_GENERATOR":not gate_mutators,
        "NO_AUTHORIZED_GATE_JSON":not authorized_gate_json,
        "LAUNCHER_SIX_MANDATORY_GATE_PARAMETERS":all(
            f"[Parameter(Mandatory=$true)][string]${name}" in launcher for name in launcher_parameters
        ) and all(flag in launcher for flag in (
            "--source-root","--dest-root","--scratch-root","--ledger-zip",
            "--full-gate-file","--full-gate-sha256"
        )),
        "NO_EMBEDDED_TRUSTED_GATE_SHA":"FullGateSha256=" not in launcher
                                       and "--full-gate-sha256 " + "$FullGateSha256" in launcher,
        "NO_POOL_ROUTE":all(word not in source+launcher for word in forbidden),
        "NO_AUTOCPU_OPTION":not any("cpu" in option.lower() or "worker" in option.lower() for option in options),
        "NO_SOURCE_DELETE_OPTION":not any(any(word in option.lower() for word in ("delete","cleanup","remove")) for option in options),
        "NO_NEW_DELETION_PATH":not forbidden_mutators,
        "NO_PS_DELETION":re.search(r"\b(Remove-Item|del|erase|rmdir)\b",launcher,re.I) is None,
        "NO_DAY_WRAPPER_LOOP":"run_one_day(" not in orchestration,
        "ONE_INVOCATION_ACQUIRE":orchestration.count("acquire_lock(")==1,
        "ONE_INVOCATION_RELEASE":orchestration.count("release_lock(")==1,
        "RECONCILE_BEFORE_PASS":orchestration.index("reconcile_full_readonly(")<orchestration.index("TICKSTORE_FULL_SERIAL_STATUS=PASS"),
        "RELEASE_BEFORE_PASS":orchestration.index("release_lock(")<orchestration.index("TICKSTORE_FULL_SERIAL_STATUS=PASS"),
        "FINAL_SOURCE_SEAL_BEFORE_RECONCILIATION":orchestration.index("seal.open_all(")<orchestration.index("reconcile_full_readonly("),
        "FINAL_SOURCE_SEAL_CLOSE_BEFORE_PASS":orchestration.index("reconcile_full_readonly(")
                                               <orchestration.index("release_lock(")
                                               <orchestration.index("seal.verify_bindings(")
                                               <orchestration.index("seal.close(")
                                               <orchestration.index("TICKSTORE_FULL_SERIAL_STATUS=PASS"),
        "FINAL_SOURCE_SEAL_RESIDUAL_FINALLY":len(cleanup_scopes)==1
                                              and orchestration.count("seal.close(")==2
                                              and "if seal.handles:" in orchestration
                                              and "if primary_error is None:primary_error=sys.exc_info()" in orchestration,
        "FINAL_SOURCE_SEAL_SECURE_PIN":"secure_open_existing_fd(path,writable=False,source_pin=True)" in seal,
        "FINAL_SOURCE_SEAL_CANONICAL_ORDER":"for month_id in sorted(self.months):" in seal,
        "FINAL_SOURCE_SEAL_HASH":"self.hash_fd(fd)!=self.months[month_id][\"source_sha256\"].upper()" in seal,
        "FINAL_SOURCE_SEAL_LIGHTWEIGHT":"os.read(fd,1024*1024)" in seal and "os.fdopen" not in seal and "PinnedSource(" not in seal,
        "FINAL_SOURCE_SEAL_IDENTITY":all(field in seal for field in ("normalized_path","size","mtime_ns","st_dev","st_ino","os.fstat")),
        "TWO_TERMINAL_INVENTORIES":len(inventory_lines)==2,
        "TERMINAL_RECONCILIATION_ORDER":len(inventory_lines)==2 and len(manifest_lines)==3 and len(shadow_lines)==1
                                          and manifest_lines[0]<inventory_lines[0]<manifest_lines[1]<inventory_lines[1]
                                          <shadow_lines[0]<manifest_lines[2],
        "NO_HISTORY_NAMING_IN_NEW_LAYER":all("PEGASUS_TICKSTORE" not in ast.get_source_segment(source,n) for n in full_nodes),
        "FROZEN_TEMPLATE_CLOSED":json.loads((HERE/"FULL_OWNER_GATE_TEMPLATE_DO_NOT_USE.json").read_text())["authorized"] is False,
        "R9_TEMPLATE_FIELDS":set(template)==gate_fields,
        "R9_TEMPLATE_CLOSED":template.get("authorized") is False,
        "R9_TEMPLATE_SCHEMA":template.get("schema")==constants.get("FULL_OWNER_GATE_SCHEMA")
                               and template.get("runner_schema")==constants.get("RUNNER_SCHEMA"),
        "R9_TEMPLATE_RELEASE_MACHINE_NULL":all(template.get(key) is None for key in (
            "runner_sha256","full_spec_sha256","source_root","dest_root","scratch_root",
            "source_volume","dest_volume","scratch_volume")),
    }
    for key,ok in checks.items():print(f"{key}={'PASS' if ok else 'FAIL'}")
    if not all(checks.values()):raise SystemExit(2)
    print("STATIC_R9_CHECKS=PASS")
    print("RELEASE_VERDICT=NOT_ASSERTED")


if __name__=="__main__":scan()
