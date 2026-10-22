"""Testes offline do supervisor V008 (núcleos puros, binding QS4, SAFE_STOP V006, CLI).

Uso: python -I -B supervisor/tests/test_supervisor_v008.py
Variável PEGASUS_SUPERVISOR_UNDER_TEST permite apontar um mutante (harness de mutação).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUP = HERE.parent
ROOT = SUP.parent
sys.path.insert(0, str(SUP))

_target = os.environ.get("PEGASUS_SUPERVISOR_UNDER_TEST")
if _target:
    spec = importlib.util.spec_from_file_location("pegasus_supervisor_v008", _target)
    sup = importlib.util.module_from_spec(spec)
    sys.modules["pegasus_supervisor_v008"] = sup
    spec.loader.exec_module(sup)
else:
    import pegasus_supervisor_v008 as sup
import pegasus_qs4_binding_v008 as qb  # noqa: E402


def good_w04():
    return dict(
        native=True,
        lease={"targets": 5, "acquired": 5, "sharing_violations": [], "errors": [],
               "held_until_tree_empty": True, "revalidation_failures": []},
        dirs={"targets": 2, "acquired": 2, "errors": [], "held_until_tree_empty": True},
        usn={"journal_id_start": 7, "journal_id_end": 7, "first_usn_end": 100, "start_usn": 500,
             "end_usn": 900, "read_complete": True, "records_on_protected": []},
        identity={"reparse_points": [], "id_changes": [], "sha_mismatch": [], "link_count_changes": []},
        census={"truncated": False, "external_writers_under_target": [], "unresolved": 1772})


class W04Verdict(unittest.TestCase):
    def test_pass_native_and_unknown_reported_not_absence(self):
        v = sup.w04_verdict(**good_w04())
        self.assertEqual(v["w04_full"], "PASS_NATIVE_SAME_ATTEMPT")
        self.assertEqual(v["census_unresolved_reported"], 1772)
        self.assertIn("NOT_ABSENCE_PROOF", v["census_unresolved_semantics"])

    def test_non_native_never_attests(self):
        g = good_w04(); g["native"] = False
        self.assertEqual(sup.w04_verdict(**g)["w04_full"], "NOT_ATTESTED_NON_NATIVE_PLATFORM")

    def _blocked(self, mutate, needle):
        g = good_w04(); mutate(g)
        v = sup.w04_verdict(**g)
        self.assertEqual(v["w04_full"], "BLOCKED", v)
        self.assertTrue(any(needle in x for x in v["gaps"]), v)

    def test_preexisting_writer(self):
        self._blocked(lambda g: g["lease"].update(sharing_violations=[{"path": "x", "winerror": 32}], acquired=4),
                      "PREEXISTING_WRITER")

    def test_partial_lease(self):
        self._blocked(lambda g: g["lease"].update(acquired=4), "LEASE_NOT_ACQUIRED")

    def test_lease_errors(self):
        self._blocked(lambda g: g["lease"].update(errors=[{"path": "x", "winerror": 5}]), "LEASE_OPEN_ERRORS")

    def test_released_early(self):
        self._blocked(lambda g: g["lease"].update(held_until_tree_empty=False), "RELEASED_BEFORE_TREE_EMPTY")

    def test_revalidation(self):
        self._blocked(lambda g: g["lease"].update(revalidation_failures=[{"path": "x"}]), "REVALIDATION")

    def test_dirs(self):
        self._blocked(lambda g: g["dirs"].update(acquired=1), "DIRECTORY_HOLD_INCOMPLETE")

    def test_usn_journal_changed(self):
        self._blocked(lambda g: g["usn"].update(journal_id_end=8), "USN_JOURNAL_IDENTITY")

    def test_usn_purged(self):
        self._blocked(lambda g: g["usn"].update(first_usn_end=600), "USN_JOURNAL_PURGED")

    def test_usn_incomplete(self):
        self._blocked(lambda g: g["usn"].update(read_complete=False), "USN_READ_INCOMPLETE")

    def test_protected_modified_new_name_or_alias(self):
        self._blocked(lambda g: g["usn"].update(records_on_protected=[{"reason": 0x100, "name": "new.csv"}]),
                      "PROTECTED_SET_MODIFIED")

    def test_reparse(self):
        self._blocked(lambda g: g["identity"].update(reparse_points=["C:\\x"]), "REPARSE")

    def test_identity_change(self):
        self._blocked(lambda g: g["identity"].update(id_changes=["a"]), "ID_CHANGES")

    def test_hardlink_count(self):
        self._blocked(lambda g: g["identity"].update(link_count_changes=["a"]), "LINK_COUNT")

    def test_census_external_writer(self):
        self._blocked(lambda g: g["census"].update(external_writers_under_target=[{"pid": 9}]), "CENSUS_EXTERNAL_WRITER")

    def test_census_truncated(self):
        self._blocked(lambda g: g["census"].update(truncated=True), "CENSUS_TRUNCATED")


def marks(order):
    return [{"mark": m, "mono_ns": 100 + i} for i, m in enumerate(order)]


class JitAndLineage(unittest.TestCase):
    ORDER = ["W04_ARM", "CHILD_CREATED", "CHILD_RESUMED", "TREE_EMPTY", "W04_DISARM"]

    def test_jit_ok_even_with_equal_timestamps(self):
        m = [{"mark": n, "mono_ns": 5} for n in self.ORDER]
        self.assertIn("W04_ARMED_BEFORE", sup.jit_verdict(m)["jit"])

    def test_jit_child_before_arm(self):
        with self.assertRaises(sup.SupervisorBlocked):
            sup.jit_verdict(marks(["CHILD_CREATED", "W04_ARM", "CHILD_RESUMED", "TREE_EMPTY", "W04_DISARM"]))

    def test_jit_disarm_before_tree_empty(self):
        with self.assertRaises(sup.SupervisorBlocked):
            sup.jit_verdict(marks(["W04_ARM", "CHILD_CREATED", "CHILD_RESUMED", "W04_DISARM", "TREE_EMPTY"]))

    def test_jit_missing(self):
        with self.assertRaises(sup.SupervisorBlocked):
            sup.jit_verdict(marks(self.ORDER[:-1]))

    def test_jit_non_monotonic(self):
        m = marks(self.ORDER); m[2]["mono_ns"] = 1
        with self.assertRaises(sup.SupervisorBlocked):
            sup.jit_verdict(m)

    def test_lineage_gapless(self):
        v = sup.lineage_verdict(native_job=True, new_process=[{"pid": 1, "ctime": 5}, {"pid": 2, "ctime": 6}],
                                accounting={"TotalProcesses": 2, "ActiveProcesses": 0}, active_zero_seen=True,
                                breakaway_allowed=False)
        self.assertEqual(v["lineage"], "GAPLESS_NATIVE_JOB")

    def test_lineage_pid_reuse_counts_twice(self):
        v = sup.lineage_verdict(native_job=True, new_process=[{"pid": 1, "ctime": 5}, {"pid": 1, "ctime": 9}],
                                accounting={"TotalProcesses": 2, "ActiveProcesses": 0}, active_zero_seen=True,
                                breakaway_allowed=False)
        self.assertEqual(v["processes"], 2)

    def test_lineage_gap(self):
        with self.assertRaises(sup.SupervisorBlocked):
            sup.lineage_verdict(native_job=True, new_process=[{"pid": 1, "ctime": 5}],
                                accounting={"TotalProcesses": 2, "ActiveProcesses": 0}, active_zero_seen=True,
                                breakaway_allowed=False)

    def test_lineage_not_empty(self):
        with self.assertRaises(sup.SupervisorBlocked):
            sup.lineage_verdict(native_job=True, new_process=[{"pid": 1, "ctime": 5}],
                                accounting={"TotalProcesses": 1, "ActiveProcesses": 1}, active_zero_seen=False,
                                breakaway_allowed=False)

    def test_lineage_breakaway(self):
        with self.assertRaises(sup.SupervisorBlocked):
            sup.lineage_verdict(native_job=True, new_process=[], accounting={"TotalProcesses": 0, "ActiveProcesses": 0},
                                active_zero_seen=True, breakaway_allowed=True)

    def test_lineage_posix_is_observational(self):
        v = sup.lineage_verdict(native_job=False, new_process=[{"pid": 1, "ctime": 5}],
                                accounting={"TotalProcesses": 1, "ActiveProcesses": 0}, active_zero_seen=True,
                                breakaway_allowed=False)
        self.assertIn("NOT_NATIVE", v["lineage"])


class SafeStopCompletion(unittest.TestCase):
    ST = {"SAFE_STOP": "YES", "PROCESS_TREE_CLEAN": "YES", "COMMITTED": 2}
    W = {"w04_full": "PASS_NATIVE_SAME_ATTEMPT"}

    def test_confirmed(self):
        v = sup.safestop_verdict(stop_requested=True, child_exit=130, tree_empty=True, status=self.ST,
                                 checkpoint_valid=True, run_lock_present=False, w04=self.W)
        self.assertEqual(v["safe_stop"], "CONFIRMED_BY_SUPERVISOR")

    def test_exit_not_130(self):
        v = sup.safestop_verdict(stop_requested=True, child_exit=0, tree_empty=True, status=self.ST,
                                 checkpoint_valid=True, run_lock_present=False, w04=self.W)
        self.assertEqual(v["safe_stop"], "NOT_CONFIRMED")

    def test_not_drained(self):
        v = sup.safestop_verdict(stop_requested=True, child_exit=130, tree_empty=False, status=self.ST,
                                 checkpoint_valid=True, run_lock_present=False, w04=self.W)
        self.assertIn("PROCESS_TREE_NOT_DRAINED", v["gaps"])

    def test_lock_and_w04(self):
        v = sup.safestop_verdict(stop_requested=True, child_exit=130, tree_empty=True, status=self.ST,
                                 checkpoint_valid=True, run_lock_present=True, w04={"w04_full": "BLOCKED"})
        self.assertIn("RUN_LOCK_STILL_PRESENT", v["gaps"])
        self.assertIn("W04_CONTINUITY_BROKEN", v["gaps"])

    def test_child_self_claim_not_enough(self):
        v = sup.safestop_verdict(stop_requested=True, child_exit=130, tree_empty=True,
                                 status={"SAFE_STOP": "NO", "PROCESS_TREE_CLEAN": "YES"},
                                 checkpoint_valid=False, run_lock_present=False, w04=self.W)
        self.assertEqual(v["safe_stop"], "NOT_CONFIRMED")

    def test_completion_ok(self):
        inv = {"a": {"type": "file", "sha256": "1"}}
        self.assertTrue(sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=False,
                                               inventory_a=inv, inventory_b=dict(inv))["completed"])

    def test_completion_refuses_lock_multi_instant_capture(self):
        inv = {"a": {"type": "file", "sha256": "1"}}
        v = sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=True, inventory_a=inv, inventory_b=inv)
        self.assertFalse(v["completed"])
        v = sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=False, inventory_a=inv,
                                   inventory_b={"a": {"type": "file", "sha256": "2"}})
        self.assertIn("INVENTORY_UNSTABLE_BETWEEN_PASSES", v["gaps"])

    def test_eta(self):
        self.assertEqual(sup.eta_status(committed=0, total=10, started_mono=0, now_mono=5, initial_committed=0)["eta_s"], "UNKNOWN")
        e = sup.eta_status(committed=2, total=10, started_mono=0, now_mono=4, initial_committed=0)
        self.assertAlmostEqual(e["eta_s"], 16.0)
        with self.assertRaises(sup.SupervisorBlocked):
            sup.eta_status(committed=11, total=10, started_mono=0, now_mono=1, initial_committed=0)


def _write_harness(d: Path, pin: str, hooks=True):
    d.mkdir(parents=True)
    methods = ("run", "run_case", "run_step", "commit_step", "save", "reconcile_resume", "finish") if hooks else ("run",)
    body = "class Orchestrator:\n" + "".join("    def %s(self, *a, **k):\n        return 'ORIGINAL'\n" % m for m in methods)
    (d / "qs4_harness.py").write_text(body + "def main(argv):\n    return 0\n", encoding="utf-8")
    sha = hashlib.sha256((d / "qs4_harness.py").read_bytes()).hexdigest().upper()
    (d / "MANIFEST_SHA256.txt").write_text("%s  qs4_harness.py\n" % sha, encoding="utf-8")
    m = hashlib.sha256((d / "MANIFEST_SHA256.txt").read_bytes()).hexdigest().upper()
    (d / "HARNESS_IDENTITY.json").write_text(json.dumps({"manifest_sha256": m, "harness_identity_sha256": m,
                                                        "adapter_identity_sha256": pin}), encoding="utf-8")


class QS4Binding(unittest.TestCase):
    def test_required_adapter_is_v003_g4(self):
        self.assertEqual(qb.required_adapter_identity(ROOT),
                         "EC96FE9A020963EC8164F1C31B1AEBCEC148A68CB494F46CD634449D174B0C41")

    def test_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            _write_harness(Path(t) / "h", "05A0CF3D807A63BA7FD5BB36374D93E56E3D727183CFD3C62D3C0D637F1DDD0A")
            r = qb.binding_report(Path(t) / "h", ROOT)
            self.assertEqual(r["binding"], "BLOCKED")
            self.assertIn("ADAPTER_BINDING_MISMATCH", r["cause"])

    def test_bound_when_pinned_and_hooks(self):
        with tempfile.TemporaryDirectory() as t:
            _write_harness(Path(t) / "h", qb.required_adapter_identity(ROOT))
            self.assertEqual(qb.binding_report(Path(t) / "h", ROOT)["binding"], "BOUND")

    def test_missing_durable_hooks_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            _write_harness(Path(t) / "h", qb.required_adapter_identity(ROOT), hooks=False)
            self.assertEqual(qb.binding_report(Path(t) / "h", ROOT)["binding"], "BLOCKED")

    def test_tampered_harness_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            h = Path(t) / "h"
            _write_harness(h, qb.required_adapter_identity(ROOT))
            (h / "qs4_harness.py").write_text("tampered", encoding="utf-8")
            self.assertEqual(qb.binding_report(h, ROOT)["binding"], "BLOCKED")

    def test_packaged_r001_harness_blocked_by_adapter_pin(self):
        r = qb.binding_report(ROOT / "QS4_HARNESS_R001" / "PHASE_B_QS4_HARNESS_V001", ROOT)
        self.assertEqual(r["binding"], "BLOCKED")
        self.assertEqual(r["harness_identity_sha256"],
                         "E52AF7826DF225AD58EB76C3156C6DDB75813D4E001DB2F176D78BF4008C7106")
        self.assertEqual(r["harness_adapter_pin"],
                         "05A0CF3D807A63BA7FD5BB36374D93E56E3D727183CFD3C62D3C0D637F1DDD0A")
        self.assertIn("ADAPTER_BINDING_MISMATCH", r["cause"])
        self.assertEqual(r["durable_hook_contract"]["source_sha256"],
                         "A84EB3055F7744C1385694FF8C66745FE3C6A0FCF08A3A3DF17915C3860AA291")

    def test_supervised_main_blocks_without_external_admission(self):
        with tempfile.TemporaryDirectory() as t:
            _write_harness(Path(t) / "h", qb.required_adapter_identity(ROOT))
            self.assertEqual(qb.qs4_supervised_main(Path(t) / "h", ROOT, ["plan"]), 2)
            self.assertNotIn("qs4_harness", sys.modules)

    def test_safestop_adapter_wired_on_orchestrator(self):
        with tempfile.TemporaryDirectory() as t:
            ev = Path(t) / "ev"; ev.mkdir()
            att = "0123456789abcdef0123456789abcdef"

            class HarnessBlocked(Exception):
                pass

            class FakeL:
                pass
            FakeL.HarnessBlocked = HarnessBlocked
            led = Path(t) / "QS4_LEDGER.json"; jr = Path(t) / "QS4_LEDGER.jsonl"
            led.write_text("{}"); jr.write_text("")
            FakeL.ledger_verify = staticmethod(lambda a, b: {"partial": None})

            class Orchestrator:
                def run_case(self, case):
                    return "ORIGINAL_RAN"

                def run_step(self, *a):
                    return "ORIGINAL_RAN"

            inst = Orchestrator()
            inst.session, inst.logical, inst.active_child, inst.led = "S", "L", None, {"partial": None}
            inst.ledger_p, inst.journal_p, inst.L = str(led), str(jr), FakeL
            adapter = qb.install_safestop(Orchestrator, evidence_root=ev, attempt_id=att, source_sha="A" * 64,
                                          session_id="S", logical_id="L")
            self.assertEqual(inst.run_case({}), "ORIGINAL_RAN")  # sem pedido: passa
            (ev / "STOP_BINDING.json").write_text(json.dumps({"schema": "PEGASUS_FULL_V006_STOP_BINDING",
                "attempt_id": att, "session_id": "S", "logical_id": "L", "source_sha256": "A" * 64,
                "outer_checkpoint_sha256": "C" * 64}))
            (ev / "STOP_REQUEST.json").write_text(json.dumps({"schema": "PEGASUS_FULL_V005_STOP_REQUEST",
                "attempt_id": att, "checkpoint_sha256": "C" * 64}))
            with self.assertRaises(HarnessBlocked):
                inst.run_step()  # pedido observado ANTES de admitir nova unidade
            self.assertTrue((ev / "STOP_OBSERVED.json").is_file())
            adapter.uninstall()
            self.assertEqual(Orchestrator.run_case.__name__, "run_case")


class RunPathWiring(unittest.TestCase):
    def test_make_run_plan_refuses_economic_without_proof(self):
        with self.assertRaises(sup.SupervisorBlocked):
            sup.make_run_plan(label="x", argv=["a"], protected_root="/i", out_root="/o",
                              economic=True, admission_schema="s", admission_sha256="h")

    def test_make_run_plan_allows_non_economic(self):
        plan = sup.make_run_plan(label="x", argv=["a"], protected_root="/i", out_root="/o",
                                 economic=False, admission_schema="s", admission_sha256="h")
        self.assertEqual(plan["schema"], sup.RUN_PLAN_SCHEMA)
        self.assertFalse(plan["economic"])

    def test_make_run_plan_economic_with_proof_is_marked(self):
        plan = sup.make_run_plan(label="x", argv=["a"], protected_root="/i", out_root="/o",
                                 economic=True, external_authorization_proven=True,
                                 admission_schema="s", admission_sha256="h")
        self.assertTrue(plan["economic"] and plan["external_authorization_proven"])

    def test_default_admission_always_blocks(self):
        entry = sup._import_entry()
        with self.assertRaises(entry.Blocked):
            sup.DefaultReleaseAdmission().admit(phase="B", package_root=sup.ROOT, entry=entry, ns=None)

    def test_run_supervised_refuses_economic_plan(self):
        entry = sup._import_entry()
        plan = {"schema": sup.RUN_PLAN_SCHEMA, "label": "e", "argv": ["run-b"], "protected_root": "/i",
                "out_root": "/o", "economic": True, "external_authorization_proven": False}
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(sup.SupervisorBlocked):
                sup._run_supervised(plan, evidence=Path(t) / "ev", entry=entry)

    def test_run_supervised_rejects_bad_schema(self):
        entry = sup._import_entry()
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(sup.SupervisorBlocked):
                sup._run_supervised({"schema": "WRONG"}, evidence=Path(t) / "ev", entry=entry)


class CliFailClosed(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, "-I", "-B", str(SUP / "pegasus_supervisor_v008.py"), *args],
                              capture_output=True, text=True, timeout=300)

    def test_run_modes_blocked_before_any_effect(self):
        for c in ("run-b", "run-c", "run-full"):
            p = self._run(c)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("G00_RUN_RELEASE_DISABLED", p.stdout)
            self.assertIn('"effects": "NONE"', p.stdout)

    def test_verify_package(self):
        p = self._run("verify")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PASS_PACKAGE_VERIFIED", p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
