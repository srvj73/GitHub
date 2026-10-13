"""Windows-only FULL_SERIAL RC1 journal -> MULTIWORK RC2R3 recovery bridge smoke.
Synthetic data only; no production source/destination.
"""
from pathlib import Path
import tempfile
import sys

import tickstore_serial_runner as core
import tickstore_full_multiwork as mw
from test_full_serial_r9 import fixture, SyntheticCodec, LEDGER_SHA


def main():
    if sys.platform != "win32":
        print("WINDOWS_RC1_RECOVERY_BRIDGE=SKIP_NON_WINDOWS")
        return 0
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        source,dest,days,months,contract,ids,cert=fixture(root,dates=("20200709",))
        c=days[0]; month=months[c["month_id"]]; codec=SyntheticCodec()
        full_ids=dict(ids)
        full_ids["spec_sha256"]="FULL_SERIAL_SPEC"
        full_ids["full_plan_contract_sha256"]="FULL_PLAN_CONTRACT"
        full_ids["gate_b_certificate_sha256"]="GATE_B_CERT"

        src=core.source_for(source,c)
        with core.PinnedSource(src,int(month["source_size"]),month["source_sha256"]) as guard:
            oracle=core.make_oracle(c,month,dict(guard.identity),LEDGER_SHA,full_ids)
            lock=core.acquire_lock(dest)
            try:
                try:
                    core._run_day_already_locked(guard,c,oracle,dest,codec,core.FaultInjector("AFTER_GROUP_0_JOURNAL"))
                except OSError as exc:
                    if "AFTER_GROUP_0_JOURNAL" not in str(exc):
                        raise
                else:
                    raise AssertionError("INTERRUPTION_NOT_INJECTED")
            finally:
                core.release_lock(lock)

        pp=core._full_day_paths(dest,c)
        j=core.read_json_strict(pp["journal"])
        if j.get("oracle",{}).get("runner_ids") != full_ids:
            raise AssertionError("SERIAL_JOURNAL_FULL_IDS_NOT_BOUND")

        wrong_ids=dict(full_ids);wrong_ids["spec_sha256"]="GENERIC_SINGLE_DAY_SPEC"
        with core.PinnedSource(src,int(month["source_size"]),month["source_sha256"]) as guard:
            wrong_oracle=core.make_oracle(c,month,dict(guard.identity),LEDGER_SHA,wrong_ids)
            lock=core.acquire_lock(dest)
            try:
                try:
                    core._run_day_already_locked(guard,c,wrong_oracle,dest,codec,core.FaultInjector(None))
                except core.Blocked as exc:
                    if str(exc) != "JOURNAL_ORACLE_MISMATCH":
                        raise
                else:
                    raise AssertionError("MISMATCH_NOT_REPRODUCED")
            finally:
                core.release_lock(lock)

        status=mw._recover_full_serial_day(source,dest,c,month,LEDGER_SHA,full_ids,codec)
        if not str(status).startswith("RESUMED"):
            raise AssertionError("RECOVERY_STATUS:"+str(status))
        state=core.transaction_state(core._full_day_paths(dest,c),dest)
        if not state["container"] or not state["commit"] or state["partial"] or state["journal"]:
            raise AssertionError("RECOVERY_FINAL_STATE:"+repr(state))
        print("WINDOWS_RC1_RECOVERY_BRIDGE_REPRO_MISMATCH=PASS")
        print("WINDOWS_RC1_RECOVERY_BRIDGE_FULL_IDS=PASS")
        print("WINDOWS_RC1_RECOVERY_BRIDGE_FINAL_STATE=PASS")
        print("REAL_CSV_READ=NO")
        print("PRODUCTION_DEST_WRITE=NO")
        print("WINDOWS_RC1_RECOVERY_BRIDGE=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
