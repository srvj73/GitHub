"""Controles negativos por mutação da fronteira de exit/stdio do bootstrap V008R2.

Cada mutante enfraquece UMA invariante do template e DEVE ser morto pelo
test_bootstrap_exit_boundary_v008.ps1. Mutantes vivem só em diretório temporário.

Uso: python -I -B mutation_bootstrap_exit_boundary_v008.py --pwsh <pwsh> --python <python>
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "launcher" / "BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.template.ps1"
TEST = HERE / "test_bootstrap_exit_boundary_v008.ps1"

MUTANTS = [
    ("null_exit_coerced_to_zero", "    if ($null -eq $Raw) { throw 'NATIVE_EXIT_NULL' }\r\n", ""),
    ("exit_read_before_exit_allowed", "    if (-not $Child.HasExited) { throw 'NATIVE_EXIT_READ_BEFORE_EXIT' }\r\n", ""),
    ("relay_trusts_process_on_mismatch", "    if ([int]$ProcessExit -ne [int]$FileExit) { return 3 }\r\n", ""),
    ("relay_null_becomes_zero", "    if ($null -eq $ProcessExit -or $null -eq $FileExit) { return 3 }\r\n",
     "    if ($null -eq $ProcessExit -or $null -eq $FileExit) { return 0 }\r\n"),
    ("expected_ignored", "    elseif (-not ($Expected -contains $Code)) { $Class = 'MISMATCH' }\r\n", ""),
    ("pythonpath_leaks", "    $Info.EnvironmentVariables.Remove('PYTHONPATH')\r\n", ""),
    ("watchdog_kills_child", "            throw ('NATIVE_TIMEOUT_NO_KILL_RECONCILE label=' + $Label + ' pid=' + $ChildId)\r\n",
     "            $Child.Kill()\r\n            throw ('NATIVE_TIMEOUT_NO_KILL_RECONCILE label=' + $Label + ' pid=' + $ChildId)\r\n"),
    ("stderr_not_drained", "    $ErrTask = $Child.StandardError.ReadToEndAsync()\r\n",
     "    $ErrTask = [System.Threading.Tasks.Task]::FromResult('')\r\n"),
]


def run(pwsh, python, src, name, old, new, tmp):
    if src.count(old) != 1:
        return {"mutant": name, "result": "INVALID_MUTANT_ANCHOR"}
    mt = Path(tmp) / (name + ".ps1")
    mt.write_text(src.replace(old, new), encoding="ascii", newline="")
    out = Path(tmp) / (name + "_out")
    p = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-File", str(TEST), "-Template", str(mt),
                        "-Python", python, "-Out", str(out)], capture_output=True, text=True, timeout=600)
    return {"mutant": name, "result": "KILLED" if p.returncode != 0 else "SURVIVED"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", required=True)
    ap.add_argument("--python", required=True)
    ns = ap.parse_args()
    with open(TEMPLATE, encoding="ascii", newline="") as fh:  # preserva CRLF das âncoras
        src = fh.read()
    with tempfile.TemporaryDirectory() as t, cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(run, ns.pwsh, ns.python, src, n, o, w, t) for n, o, w in MUTANTS]
        results = [f.result() for f in futs]
    killed = sum(r["result"] == "KILLED" for r in results)
    doc = {"schema": "PEGASUS_FULL_2026_V008R2_BOOTSTRAP_MUTATION", "mutants": len(MUTANTS), "killed": killed,
           "results": results, "result": "PASS_ALL_MUTANTS_KILLED" if killed == len(MUTANTS) else "FAIL_MUTANT_SURVIVED"}
    print(json.dumps(doc, indent=1))
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
