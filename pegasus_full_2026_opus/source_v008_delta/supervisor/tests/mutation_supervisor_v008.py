"""Controles negativos por mutação: cada mutante enfraquece UMA invariante do supervisor e
DEVE ser morto pela suíte test_supervisor_v008.py. Mutantes vivem só em diretório temporário.

Uso: python -I -B supervisor/tests/mutation_supervisor_v008.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "pegasus_supervisor_v008.py"

MUTANTS = [
    ("ignore_sharing_violation", 'if lease.get("sharing_violations"):', 'if False:'),
    ("ignore_lease_release_early", 'if lease.get("held_until_tree_empty") is not True:', 'if False:'),
    ("ignore_usn_records", 'if usn.get("records_on_protected"):', 'if False:'),
    ("ignore_usn_purge", 'int(usn["first_usn_end"]) > int(usn["start_usn"]):', 'False:'),
    ("ignore_census_writer", 'if census.get("external_writers_under_target"):', 'if False:'),
    ("non_native_attests", 'if not native:\n        return {"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM",',
     'if False:\n        return {"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM",'),
    ("jit_order_unchecked", 'if [idx[o] for o in order] != sorted(idx[o] for o in order):', 'if False:'),
    ("lineage_gap_unchecked", 'if int(accounting.get("TotalProcesses", -1)) != len(idents):', 'if False:'),
    ("breakaway_allowed", 'if breakaway_allowed:\n        raise', 'if False:\n        raise'),
    ("safestop_any_exit", 'if child_exit != EXIT_SAFE_STOP:', 'if False:'),
    ("safestop_ignore_lock", 'if run_lock_present:\n        gaps.append("RUN_LOCK_STILL_PRESENT")',
     'if False:\n        gaps.append("RUN_LOCK_STILL_PRESENT")'),
    ("completion_ignore_lock", 'if run_lock_present:\n        gaps.append("RUN_LOCK_PRESENT")',
     'if False:\n        gaps.append("RUN_LOCK_PRESENT")'),
    ("completion_ignore_unstable_inventory", 'if dict(inventory_a) != dict(inventory_b):', 'if False:'),
    ("eta_from_attempts", 'if delta <= 0:', 'if False:'),
    ("run_plan_allows_economic", 'if economic and not external_authorization_proven:\n        # Um plano econômico só pode existir com prova de autorização externa.\n        raise SupervisorBlocked("ECONOMIC_RUN_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION")',
     'if False:\n        # Um plano econômico só pode existir com prova de autorização externa.\n        raise SupervisorBlocked("ECONOMIC_RUN_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION")'),
    ("run_supervised_runs_economic", 'if not plan.get("external_authorization_proven"):\n            raise SupervisorBlocked("ECONOMIC_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION")',
     'if False:\n            raise SupervisorBlocked("ECONOMIC_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION")'),
    ("default_admission_returns_plan", 'entry.release_admission({}, phase)  # sempre levanta entry.Blocked neste artefato\n        raise SupervisorBlocked("RELEASE_ADMISSION_RETURNED_WITHOUT_EXTERNAL_MODULE")',
     'return make_run_plan(label="L", argv=["x"], protected_root="/i", out_root="/o", economic=True, external_authorization_proven=True, admission_schema="x", admission_sha256="h")'),
    ("absent_exit_classified_pass", 'if isinstance(code, bool) or not isinstance(code, int):\n        return "EXIT_UNKNOWN_FAIL_CLOSED"',
     'if isinstance(code, bool) or not isinstance(code, int):\n        return "PASS"'),
    ("unknown_nonzero_classified_pass", 'return EXIT_CLASSES.get(code, "UNCLASSIFIED_NONZERO_FAIL" if code != 0 else "PASS")',
     'return EXIT_CLASSES.get(code, "PASS")'),
    ("technical_failure_exits_zero", '        print("PEGASUS_SUPERVISOR=FAIL_TECHNICAL " + type(exc).__name__ + ": " + str(exc), flush=True)\n        return EXIT_FAIL',
     '        print("PEGASUS_SUPERVISOR=FAIL_TECHNICAL " + type(exc).__name__ + ": " + str(exc), flush=True)\n        return EXIT_PASS'),
]

SUBSET = ["W04Verdict", "JitAndLineage", "SafeStopCompletion", "RunPathWiring", "ExitClassification"]


def main() -> int:
    src = SRC.read_text(encoding="utf-8")
    results = []
    with tempfile.TemporaryDirectory() as t:
        for name, old, new in MUTANTS:
            if src.count(old) != 1:
                results.append({"mutant": name, "result": "INVALID_MUTANT_ANCHOR"})
                continue
            m = Path(t) / (name + ".py")
            m.write_text(src.replace(old, new), encoding="utf-8")
            env = {**os.environ, "PEGASUS_SUPERVISOR_UNDER_TEST": str(m), "PYTHONDONTWRITEBYTECODE": "1"}
            p = subprocess.run([sys.executable, "-B", str(HERE / "test_supervisor_v008.py"), *SUBSET],
                               capture_output=True, text=True, env=env, timeout=300)
            results.append({"mutant": name, "result": "KILLED" if p.returncode != 0 else "SURVIVED"})
    killed = sum(1 for r in results if r["result"] == "KILLED")
    out = {"schema": "PEGASUS_FULL_2026_V008_SUPERVISOR_MUTATION_V001", "mutants": len(MUTANTS),
           "killed": killed, "results": results,
           "result": "PASS_ALL_MUTANTS_KILLED" if killed == len(MUTANTS) else "FAIL_MUTANT_SURVIVED"}
    print(json.dumps(out, indent=1))
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
