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
import time
import unittest
from pathlib import Path
from unittest import mock

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
             "end_usn": 900, "read_complete": True, "records_on_protected": [],
             "coverage": {"read_complete": True, "reason": None, "start_usn": 500, "end_usn": 900,
                          "covered_to": 900, "pages": 3, "records_parsed": 40}},
        identity={"reparse_points": [], "id_changes": [], "sha_mismatch": [], "link_count_changes": []},
        census={"truncated": False, "external_writers_under_target": [], "unresolved": 1772})


JIT_OK = {"jit": "W04_ARMED_BEFORE_CHILD_CREATION_HELD_UNTIL_TREE_EMPTY"}
LIN_NATIVE = {"lineage": "GAPLESS_NATIVE_JOB", "processes": 1}
LIN_POSIX = {"lineage": "OBSERVATIONAL_POSIX_SESSION_NOT_NATIVE_PROOF", "processes_observed": 1}


def term(mode):
    return {"terminal": "COMPLETE", "mode": mode, "gaps": []}


PROVEN_STOP = dict(terminal=term("SAFE_STOP"), lineage=LIN_NATIVE, jit=JIT_OK)
PROVEN_DONE_POSIX = dict(terminal=term("COMPLETION"), lineage=LIN_POSIX, jit=JIT_OK)
PROVEN_DONE_NATIVE = dict(terminal=term("COMPLETION"), lineage=LIN_NATIVE, jit=JIT_OK)


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
                                 checkpoint_valid=True, run_lock_present=False, w04=self.W, **PROVEN_STOP)
        self.assertEqual(v["safe_stop"], "CONFIRMED_BY_SUPERVISOR")

    def test_exit_not_130(self):
        v = sup.safestop_verdict(stop_requested=True, child_exit=0, tree_empty=True, status=self.ST,
                                 checkpoint_valid=True, run_lock_present=False, w04=self.W)
        self.assertEqual(v["safe_stop"], "NOT_CONFIRMED")

    def test_noncooperative_exit_blocks_even_with_full_evidence(self):
        # Com TODA a demais evidência provada (terminal SAFE_STOP, linhagem, JIT, status, checkpoint,
        # sem lock, W04 nativo), um exit NÃO cooperativo (ex.: 5) ainda tem de impedir a confirmação:
        # a saída cooperativa é condição isolada e indispensável. Mata `safestop_any_exit`.
        v = sup.safestop_verdict(stop_requested=True, child_exit=5, tree_empty=True, status=self.ST,
                                 checkpoint_valid=True, run_lock_present=False, w04=self.W, **PROVEN_STOP)
        self.assertEqual(v["safe_stop"], "NOT_CONFIRMED")
        self.assertEqual(v["gaps"], ["CHILD_EXIT_NOT_COOPERATIVE_STOP:5"])

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

    OKW04 = {"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM"}

    def test_completion_ok(self):
        inv = {"a": {"type": "file", "sha256": "1"}}
        self.assertTrue(sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=False,
                                               inventory_a=inv, inventory_b=dict(inv), w04=self.OKW04,
                                               **PROVEN_DONE_POSIX)["completed"])

    def test_completion_refuses_lock_multi_instant_capture(self):
        inv = {"a": {"type": "file", "sha256": "1"}}
        v = sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=True, inventory_a=inv,
                                   inventory_b=inv, w04=self.OKW04)
        self.assertFalse(v["completed"])
        v = sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=False, inventory_a=inv,
                                   inventory_b={"a": {"type": "file", "sha256": "2"}}, w04=self.OKW04)
        self.assertIn("INVENTORY_UNSTABLE_BETWEEN_PASSES", v["gaps"])

    def test_completion_requires_w04_attested(self):
        # F01: W04 BLOCKED (ou qualquer veredito não atestado) impede COMPLETED mesmo com exit 0,
        # árvore vazia, sem lock e inventário estável.
        inv = {"a": {"type": "file", "sha256": "1"}}
        for bad in ({"w04_full": "BLOCKED"}, {"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM_X"}, {}):
            v = sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=False,
                                       inventory_a=inv, inventory_b=dict(inv), w04=bad)
            self.assertFalse(v["completed"], bad)
            self.assertTrue(any(g.startswith("W04_NOT_ATTESTED") for g in v["gaps"]), v["gaps"])
        self.assertTrue(sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=False,
                        inventory_a=inv, inventory_b=dict(inv),
                        w04={"w04_full": "PASS_NATIVE_SAME_ATTEMPT"}, **PROVEN_DONE_NATIVE)["completed"])

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
        # R18: um plano econômico exige TAMBÉM o recibo de release concedida (granted=True).
        plan = sup.make_run_plan(label="x", argv=["a"], protected_root="/i", out_root="/o",
                                 economic=True, external_authorization_proven=True,
                                 admission_schema="s", admission_sha256="h",
                                 release_admission_receipt={"granted": True, "kind": "SYNTHETIC_ISOLATED"},
                                 plan_kind="SYNTHETIC_ISOLATED")
        self.assertTrue(plan["economic"] and plan["external_authorization_proven"])

    def test_make_run_plan_economic_without_receipt_refused(self):
        with self.assertRaises(sup.SupervisorBlocked) as cm:
            sup.make_run_plan(label="x", argv=["a"], protected_root="/i", out_root="/o",
                              economic=True, external_authorization_proven=True,
                              admission_schema="s", admission_sha256="h")
        self.assertIn("ECONOMIC_RUN_PLAN_WITHOUT_RELEASE_ADMISSION_RECEIPT", str(cm.exception))

    def test_default_admission_always_blocks(self):
        entry = sup._import_entry()
        with self.assertRaises(entry.Blocked):
            sup.DefaultReleaseAdmission().admit(phase="B", package_root=sup.ROOT, entry=entry, ns=None)

    def test_run_supervised_refuses_economic_plan(self):
        entry = sup._import_entry()
        plan = {"schema": sup.RUN_PLAN_SCHEMA, "label": "e", "argv": ["run-b"], "protected_root": "/i",
                "out_root": "/o", "economic": True, "external_authorization_proven": False}
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(sup.SupervisorBlocked) as cm:
                sup._run_supervised(plan, evidence=Path(t) / "ev", entry=entry)
            # causa ESPECÍFICA: mata o mutante que desliga o gate de autorização externa (sem o qual
            # o ramo cairia no gate de recibo, com outra causa).
            self.assertIn("ECONOMIC_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION", str(cm.exception))

    def test_run_supervised_rejects_bad_schema(self):
        entry = sup._import_entry()
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(sup.SupervisorBlocked):
                sup._run_supervised({"schema": "WRONG"}, evidence=Path(t) / "ev", entry=entry)


class ExitClassification(unittest.TestCase):
    def test_known_codes(self):
        self.assertEqual(sup.classify_exit(0), "PASS")
        self.assertEqual(sup.classify_exit(2), "BLOCKED_FAIL_CLOSED_NO_EFFECT")
        self.assertEqual(sup.classify_exit(3), "FAIL_TECHNICAL_AFTER_EFFECT_START")
        self.assertEqual(sup.classify_exit(130), "SAFE_STOP_CONFIRMED_RESUMABLE")

    def test_absent_or_bogus_code_never_pass(self):
        for bogus in (None, True, False, "0", 0.0):
            self.assertEqual(sup.classify_exit(bogus), "EXIT_UNKNOWN_FAIL_CLOSED", bogus)
        for code in (1, 9, 87, 255, -2, 3221225786):
            self.assertEqual(sup.classify_exit(code), "UNCLASSIFIED_NONZERO_FAIL", code)

    def test_main_technical_failure_exits_3_not_1(self):
        # R15: exercita o ramo de falha técnica de main() EM PROCESSO (o mutante é carregado como
        # `sup`), independente de --admission (agora selado). Uma exceção não-Blocked num comando
        # => exit 3 (nunca 0/1), com a linha FAIL_TECHNICAL. O mutante technical_failure_exits_zero
        # (return EXIT_FAIL -> EXIT_PASS) é morto por esta asserção.
        import io
        from contextlib import redirect_stdout
        def boom(_ns):
            raise RuntimeError("boom")
        buf = io.StringIO()
        with mock.patch.object(sup, "cmd_verify", boom), redirect_stdout(buf):
            rc = sup.main(["verify"])
        self.assertEqual(rc, sup.EXIT_FAIL, buf.getvalue())
        self.assertIn("PEGASUS_SUPERVISOR=FAIL_TECHNICAL RuntimeError: boom", buf.getvalue())


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


class SafeStopExitPlatform(unittest.TestCase):
    """O codigo de saida de um Ctrl+C cooperativo HONRADO e dependente de plataforma: 130 no
    POSIX (CPython re-ergue o SIGINT); 1 ou 0xC000013A no Windows (KeyboardInterrupt desenrolado
    ou STATUS_CONTROL_C_EXIT). Exigir literalmente 130 era um artefato POSIX que derrubou o Q03
    na campanha nativa. O codigo e corroboracao; a confirmacao exige a evidencia independente
    (STATUS SAFE_STOP=YES + arvore drenada + checkpoint valido + sem RUN.lock + W04), e o Q04
    prova a retomada exactly-once."""
    CLEAN = dict(stop_requested=True, tree_empty=True,
                 status={"SAFE_STOP": "YES", "PROCESS_TREE_CLEAN": "YES", "COMMITTED": 1},
                 checkpoint_valid=True, run_lock_present=False, w04={"w04_full": "PASS_NATIVE_SAME_ATTEMPT"},
                 **PROVEN_STOP)

    def _v(self, code):
        return sup.safestop_verdict(child_exit=code, **self.CLEAN)

    def test_helper_posix_only_130(self):
        with mock.patch.object(sup.os, "name", "posix"):
            self.assertTrue(sup.is_cooperative_stop_exit(130))
            for bad in (0, 1, 2, 87, sup.EXIT_CTRL_C_WINDOWS, None, True):
                self.assertFalse(sup.is_cooperative_stop_exit(bad), bad)

    def test_helper_windows_interrupt_codes(self):
        with mock.patch.object(sup.os, "name", "nt"):
            for ok in (130, 1, sup.EXIT_CTRL_C_WINDOWS):
                self.assertTrue(sup.is_cooperative_stop_exit(ok), ok)
            for bad in (0, 2, 87, None, True):
                self.assertFalse(sup.is_cooperative_stop_exit(bad), bad)

    def test_windows_ctrl_c_confirms_with_independent_evidence(self):
        with mock.patch.object(sup.os, "name", "nt"):
            self.assertTrue(self._v(1)["safe_stop"].startswith("CONFIRMED_BY_SUPERVISOR"))
            self.assertTrue(self._v(sup.EXIT_CTRL_C_WINDOWS)["safe_stop"].startswith("CONFIRMED_BY_SUPERVISOR"))

    def test_posix_exit_1_not_confirmed_but_130_is(self):
        with mock.patch.object(sup.os, "name", "posix"):
            self.assertEqual(self._v(1)["safe_stop"], "NOT_CONFIRMED")
            self.assertEqual(self._v(130)["safe_stop"], "CONFIRMED_BY_SUPERVISOR")

    def test_completion_exit_never_confirms_stop(self):
        for name in ("posix", "nt"):
            with mock.patch.object(sup.os, "name", name):
                self.assertEqual(self._v(0)["safe_stop"], "NOT_CONFIRMED")

    def test_crash_code_not_confirmed_even_on_windows(self):
        with mock.patch.object(sup.os, "name", "nt"):
            v = self._v(87)
            self.assertEqual(v["safe_stop"], "NOT_CONFIRMED")
            self.assertIn("CHILD_EXIT_NOT_COOPERATIVE_STOP:87", v["gaps"])

    def test_windows_interrupt_code_without_child_status_still_rejected(self):
        # codigo de interrupcao sozinho nao basta: sem STATUS SAFE_STOP=YES, continua NOT_CONFIRMED
        with mock.patch.object(sup.os, "name", "nt"):
            v = sup.safestop_verdict(stop_requested=True, child_exit=1, tree_empty=True,
                                     status={"SAFE_STOP": "NO", "PROCESS_TREE_CLEAN": "YES"},
                                     checkpoint_valid=True, run_lock_present=False,
                                     w04={"w04_full": "PASS_NATIVE_SAME_ATTEMPT"})
            self.assertEqual(v["safe_stop"], "NOT_CONFIRMED")
            self.assertIn("CHILD_STATUS_NOT_SAFE", v["gaps"])


class SafeStopRedelivery(unittest.TestCase):
    """Reentrega cooperativa do SAFE_STOP até o coordenador LATCH-ar (STATUS.STOP_REQUESTED=True)
    ou o filho sair. Cobre a corrida nativa em que o Ctrl+C entregue no spawn de workers os mata
    em import sem o coordenador registrar o pedido (campanha R4: Q12b pendurou 1800s)."""
    BASE = dict(stop_requested=True, child_running=True, latched=False, active=2,
                require_active_window=True, now=1000.0, last_delivery=0.0, deliveries=0)

    def _d(self, **kw):
        return sup.should_deliver_safe_stop(**{**self.BASE, **kw})

    def test_first_delivery_immediate_when_workers_active(self):
        self.assertTrue(self._d())

    def test_no_delivery_in_spawn_window_active_zero_on_windows(self):
        # ACTIVE=0 e a janela de import/spawn no Windows: entregar aqui mataria workers e encravaria
        # o coordenador (campanha R5, Q03). So entrega com workers em execucao.
        self.assertFalse(self._d(active=0, now=99999.0))
        self.assertFalse(self._d(active=0, now=99999.0, deliveries=0))

    def test_posix_delivers_regardless_of_active(self):
        # POSIX: os.kill mira so o coordenador, sem corrida de console; o gate de janela nao se aplica.
        self.assertTrue(self._d(require_active_window=False, active=0, now=99999.0))

    def test_waits_interval_between_deliveries(self):
        self.assertFalse(self._d(now=1005.0, last_delivery=1000.0, deliveries=1))   # 5s < 15s
        self.assertTrue(self._d(now=1020.0, last_delivery=1000.0, deliveries=1))    # 20s >= 15s

    def test_latched_stops_redelivery(self):
        # uma vez registrado pelo coordenador, nao reentrega (2o Ctrl+C do V003 = WAIT_NO_KILL)
        self.assertFalse(self._d(latched=True, now=99999.0, last_delivery=0.0, deliveries=1))

    def test_bounded_by_max_deliveries(self):
        self.assertFalse(self._d(now=99999.0, last_delivery=0.0, deliveries=sup.SAFE_STOP_MAX_DELIVERIES))

    def test_no_delivery_after_child_exit(self):
        self.assertFalse(self._d(child_running=False, now=99999.0))

    def test_no_delivery_without_request(self):
        self.assertFalse(self._d(stop_requested=False, now=99999.0))


class CustodyLifecycleContract(unittest.TestCase):
    """Trava o contrato cuja violação derrubou a campanha nativa R2 com
    JOB_ACCOUNTING_FAILED winerror=6 (ERROR_INVALID_HANDLE): no Windows, close() fecha o
    handle do Job, de modo que qualquer accounting()/tree_empty()/new_process_events() após
    close() é inválido. A evidência terminal deve ser capturada ANTES de close(); o POSIX
    espelha a recusa para reproduzir a classe de erro offline."""

    def test_terminal_evidence_capturable_before_close_then_refused_after(self):
        cust = sup.PosixCustody(lambda *_a, **_k: None)
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            cust.start([sys.executable, "-I", "-c", "pass"], td, dict(os.environ), td / "child.out")
            deadline = time.monotonic() + 30
            while cust.poll() is None:           # coleta o filho (senão fica zumbi em /proc)
                time.sleep(0.01)
            while not cust.tree_empty():
                cust.sample()
                if time.monotonic() > deadline:
                    self.fail("child did not drain")
                time.sleep(0.02)
            acct = cust.accounting()            # capturável enquanto aberto
            self.assertEqual(acct["ActiveProcesses"], 0)
            self.assertGreaterEqual(acct["TotalProcesses"], 1)
            self.assertIsInstance(cust.new_process_events(), list)
            cust.close()
            for fn in (cust.accounting, cust.tree_empty, cust.new_process_events):
                with self.assertRaises(RuntimeError) as ctx:
                    fn()
                self.assertIn("CUSTODY_QUERIED_AFTER_CLOSE", str(ctx.exception), fn.__name__)


class NativeNegativesReplay(unittest.TestCase):
    """R9: _replay_case_records reencena os casos do subprocesso no recibo do pai, levanta na
    PRIMEIRA falha, e é fail-closed contra filho incompleto (caso ausente ou completed=False)."""

    def _q(self):
        import pegasus_qualify_v008 as q  # import tardio: não perturba o harness de mutação
        return q

    def _case_and_sink(self):
        sink = []

        def case(name, ok, **detail):
            sink.append({"case": name, "result": "PASS" if ok else "FAIL", **detail})
            if not ok:
                raise AssertionError(name + " " + json.dumps(detail, sort_keys=True, default=str)[:200])
        return case, sink

    def _full_records(self, **overrides):
        recs = [{"case": n, "ok": True, "result": "PASS", "detail": {"w04": {"w04_full": "PASS_NATIVE_SAME_ATTEMPT"}}}
                for n in self._q()._NATIVE_NEGATIVE_CASES]
        for r in recs:
            if r["case"] in overrides:
                r.update(overrides[r["case"]])
        return recs

    def test_all_pass_complete_records_every_case(self):
        q = self._q()
        case, sink = self._case_and_sink()
        q._replay_case_records(self._full_records(), case, doc={"completed": True})
        self.assertEqual([c["case"] for c in sink], list(q._NATIVE_NEGATIVE_CASES))
        self.assertTrue(all(c["result"] == "PASS" for c in sink))
        # detail (ex.: w04) é repassado ao pai e preservado para a avaliação de completude.
        self.assertEqual(sink[0]["w04"]["w04_full"], "PASS_NATIVE_SAME_ATTEMPT")

    def test_first_failure_raises_and_stops(self):
        q = self._q()
        case, sink = self._case_and_sink()
        bad = q._NATIVE_NEGATIVE_CASES[2]
        recs = self._full_records(**{bad: {"ok": False, "result": "FAIL", "detail": {"why": "x"}}})
        with self.assertRaises(AssertionError) as ctx:
            q._replay_case_records(recs, case, doc={"completed": True})
        self.assertIn(bad, str(ctx.exception))
        self.assertEqual(sink[-1]["case"], bad)              # registrou até a falha
        self.assertEqual(len(sink), 3)                       # parou na primeira falha

    def test_missing_case_is_fail_closed(self):
        q = self._q()
        case, sink = self._case_and_sink()
        recs = [r for r in self._full_records() if r["case"] != q._NATIVE_NEGATIVE_CASES[-1]]
        with self.assertRaises(sup.SupervisorBlocked) as ctx:
            q._replay_case_records(recs, case, doc={"completed": True})
        self.assertIn("NATIVE_NEGATIVES_CASES_MISSING", str(ctx.exception))
        self.assertIn(q._NATIVE_NEGATIVE_CASES[-1], str(ctx.exception))

    def test_incomplete_child_is_fail_closed(self):
        q = self._q()
        case, _ = self._case_and_sink()
        with self.assertRaises(sup.SupervisorBlocked) as ctx:
            q._replay_case_records(self._full_records(), case, doc={"completed": False, "error": "boom"})
        self.assertIn("NATIVE_NEGATIVES_CHILD_DID_NOT_COMPLETE", str(ctx.exception))


class W04PrespawnGate(unittest.TestCase):
    """F02: w04_prespawn_verdict bloqueia o spawn quando a lease não foi adquirida."""

    def test_clean_acquisition_allows_spawn(self):
        v = sup.w04_prespawn_verdict({"sharing_violations": [], "open_errors": [], "reparse": [],
                                      "files": 5, "dirs": 1})
        self.assertEqual(v["prespawn"], "ACQUIRED_CLEAN")

    def test_sharing_violation_blocks_spawn(self):
        v = sup.w04_prespawn_verdict({"sharing_violations": [{"path": "x", "winerror": 32}],
                                      "open_errors": [], "reparse": []})
        self.assertEqual(v["prespawn"], "BLOCKED_NO_SPAWN")
        self.assertTrue(any("PREEXISTING_WRITER_OR_SHARING_VIOLATION" in g for g in v["gaps"]))

    def test_open_error_and_reparse_block_spawn(self):
        self.assertEqual(sup.w04_prespawn_verdict({"sharing_violations": [], "open_errors": [{"path": "y", "winerror": 5}],
                                                   "reparse": []})["prespawn"], "BLOCKED_NO_SPAWN")
        self.assertEqual(sup.w04_prespawn_verdict({"sharing_violations": [], "open_errors": [],
                                                   "reparse": ["z"]})["prespawn"], "BLOCKED_NO_SPAWN")


class LineageUnresolvedIdentity(unittest.TestCase):
    """F03: identidade (pid, ctime) não resolvida NÃO pode classificar GAPLESS no Job nativo."""

    def test_unresolved_ctime_blocks_gapless(self):
        with self.assertRaises(sup.SupervisorBlocked) as ctx:
            sup.lineage_verdict(native_job=True, new_process=[{"pid": 10, "ctime": 0}],
                                accounting={"TotalProcesses": 1, "ActiveProcesses": 0},
                                active_zero_seen=True, breakaway_allowed=False)
        self.assertIn("JOB_IDENTITY_UNRESOLVED_NO_GAPLESS", str(ctx.exception))
        with self.assertRaises(sup.SupervisorBlocked):
            sup.lineage_verdict(native_job=True, new_process=[{"pid": 10}],  # ctime ausente
                                accounting={"TotalProcesses": 1, "ActiveProcesses": 0},
                                active_zero_seen=True, breakaway_allowed=False)

    def test_resolved_identity_gapless(self):
        v = sup.lineage_verdict(native_job=True, new_process=[{"pid": 10, "ctime": 777}],
                                accounting={"TotalProcesses": 1, "ActiveProcesses": 0},
                                active_zero_seen=True, breakaway_allowed=False)
        self.assertEqual(v["lineage"], "GAPLESS_NATIVE_JOB")
        self.assertEqual(v["identity_unresolved_short_lived"], 0)


class JobCloseNoKill(unittest.TestCase):
    """F04: a disposição de fechamento do Job honra NO_KILL quando a árvore está viva."""

    def test_empty_tree_safe_close(self):
        self.assertEqual(sup.job_close_disposition(0), "CLOSE_EMPTY_SAFE")

    def test_live_tree_clears_kill_on_close(self):
        self.assertEqual(sup.job_close_disposition(3), "CLEAR_KILL_ON_CLOSE_LEAVE_RUNNING_NO_KILL")
        self.assertEqual(sup.job_close_disposition(1), "CLEAR_KILL_ON_CLOSE_LEAVE_RUNNING_NO_KILL")


class JobClosePlan(unittest.TestCase):
    """R11-ORIGIN-01: com árvore viva o supervisor NUNCA fecha o handle do Job (close_handles=False),
    independentemente de ter conseguido limpar KILL_ON_JOB_CLOSE."""

    def test_empty_tree_closes_handles(self):
        p = sup.job_close_plan(0, True)
        self.assertTrue(p["close_handles"]) and self.assertFalse(p["live_tree"])

    def test_live_tree_never_closes_handles(self):
        for cleared in (True, False):
            p = sup.job_close_plan(2, cleared)
            self.assertFalse(p["close_handles"], cleared)
            self.assertTrue(p["live_tree"])
            self.assertTrue(p["retain_custody"])
            self.assertEqual(p["kill_risk"], not cleared)


class GrandchildContained(unittest.TestCase):
    """R12-ORIGIN-02: contenção por identidade temporal INDEPENDENTE do neto (pid, ctime próprios)
    casando com a observação independente do Job."""

    def test_independent_identity_match(self):
        ok, ident, why = sup.grandchild_contained(7, 111, [(7, 111), (9, 222)])
        self.assertTrue(ok); self.assertEqual(ident, [7, 111])
        self.assertIn("TWO_INDEPENDENT_SOURCES", why)

    def test_divergent_ctime_rejected(self):
        ok, ident, why = sup.grandchild_contained(7, 999, [(7, 111)])
        self.assertFalse(ok); self.assertIsNone(ident)
        self.assertEqual(why, "INDEPENDENT_CTIME_DIVERGENT_FROM_JOB")

    def test_no_independent_ctime_rejected(self):
        self.assertEqual(sup.grandchild_contained(7, None, [(7, 111)])[0], False)
        self.assertEqual(sup.grandchild_contained(7, 0, [(7, 111)])[0], False)

    def test_absent_pid_rejected(self):
        self.assertEqual(sup.grandchild_contained(7, 111, [(9, 222)])[0], False)

    def test_ambiguous_pid_rejected(self):
        self.assertEqual(sup.grandchild_contained(7, 111, [(7, 111), (7, 112)])[0], False)


class CustodyFinalizeDecision(unittest.TestCase):
    """R12-ORIGIN-01: a decisão de finalização nunca abandona/mata uma árvore viva."""

    def test_empty_tree_finalizes(self):
        self.assertEqual(sup.custody_finalize_decision(tree_empty=True, reconcile_deadline_reached=True,
                                                       production=False), "FINALIZE_TREE_EMPTY_SAFE")

    def test_live_tree_holds_before_deadline(self):
        self.assertEqual(sup.custody_finalize_decision(tree_empty=False, reconcile_deadline_reached=False,
                                                       production=False), "HOLD_SUPERVISE_UNTIL_TREE_EMPTY_NO_KILL")

    def test_production_holds_even_after_deadline(self):
        self.assertEqual(sup.custody_finalize_decision(tree_empty=False, reconcile_deadline_reached=True,
                                                       production=True), "HOLD_SUPERVISE_UNTIL_TREE_EMPTY_NO_KILL")

    def test_qualification_deadline_reserved_fail_closed(self):
        self.assertEqual(sup.custody_finalize_decision(tree_empty=False, reconcile_deadline_reached=True,
                                                       production=False), "RESERVED_DECISION_FAIL_CLOSED_NO_KILL")

    def test_never_finalizes_live_tree(self):
        for dl in (True, False):
            for prod in (True, False):
                self.assertNotEqual(sup.custody_finalize_decision(tree_empty=False, reconcile_deadline_reached=dl,
                                                                  production=prod), "FINALIZE_TREE_EMPTY_SAFE")


class ReconcileStepAction(unittest.TestCase):
    """R13-ORIGIN-01: a ação por iteração do laço de reconciliação NUNCA encerra a custódia com a
    árvore viva (nem finaliza, nem mata, nem solta W04). A decisão reservada é SURGIDA e MANTIDA."""

    def test_empty_tree_is_the_only_finalize(self):
        for dl in (True, False):
            for prod in (True, False):
                for rep in (True, False):
                    self.assertEqual(sup.reconcile_step_action(tree_empty=True, deadline_reached=dl,
                                                               production=prod, reserved_reported=rep),
                                     "FINALIZE_SAFE")

    def test_live_before_deadline_holds(self):
        self.assertEqual(sup.reconcile_step_action(tree_empty=False, deadline_reached=False,
                                                   production=False, reserved_reported=False), "HOLD")

    def test_live_production_holds_after_deadline(self):
        self.assertEqual(sup.reconcile_step_action(tree_empty=False, deadline_reached=True,
                                                   production=True, reserved_reported=False), "HOLD")

    def test_qualification_deadline_reports_reserved_once_then_holds(self):
        self.assertEqual(sup.reconcile_step_action(tree_empty=False, deadline_reached=True,
                                                   production=False, reserved_reported=False),
                         "REPORT_RESERVED_THEN_HOLD")
        # já reportada -> apenas segue viva (hold), sem re-reportar e sem encerrar
        self.assertEqual(sup.reconcile_step_action(tree_empty=False, deadline_reached=True,
                                                   production=False, reserved_reported=True), "HOLD")

    def test_live_tree_never_terminates_custody(self):
        # Invariante central: com árvore viva, a única ação possível é continuar vivo (HOLD) ou
        # surgir a reservada (que também segue viva). JAMAIS finalizar/encerrar.
        for dl in (True, False):
            for prod in (True, False):
                for rep in (True, False):
                    act = sup.reconcile_step_action(tree_empty=False, deadline_reached=dl,
                                                    production=prod, reserved_reported=rep)
                    self.assertIn(act, ("HOLD", "REPORT_RESERVED_THEN_HOLD"))
                    self.assertNotEqual(act, "FINALIZE_SAFE")


class _ReconcileCustody:
    """Dupla de custódia que mantém a árvore VIVA por N amostragens após o prazo e depois esvazia.
    Registra fechamentos e prova que NENHUM kill foi solicitado (não há método de kill)."""
    native_job = False
    breakaway_allowed = False

    def __init__(self, live_polls):
        self._left = live_polls
        self.closed = 0
        self.closed_while_live = 0
        self.marks = []
        self._empty = False

    def start(self, *a, **k):
        self.mark("CHILD_CREATED")
        self.mark("CHILD_RESUMED")
        return 9777

    def mark(self, n):
        self.marks.append({"mark": n, "mono_ns": 1})

    def poll(self):
        return None  # filho "vivo" no laço principal; a saída se dá por timeout_s

    def sample(self):
        pass

    def tree_empty(self):
        if self._left > 0:
            self._left -= 1
            return False
        self._empty = True
        return True

    def request_stop(self):
        pass

    def accounting(self):
        return {"TotalProcesses": 1, "ActiveProcesses": 0}

    def new_process_events(self):
        return [{"pid": 9777, "ctime": 5}]

    def close(self):
        self.closed += 1
        if not self._empty:
            self.closed_while_live += 1
        # R16 (N2): devolve prova estruturada; só confirma fechamento com a árvore vazia.
        return {"closed": bool(self._empty), "handles_closed": bool(self._empty),
                "active_processes": 0 if self._empty else 1, "reason": "FAKE_RECONCILE_CLOSE"}


class _ReconcileGuard:
    def __init__(self):
        self.disarmed = None
        self.evaluated = None
        self.released = 0
        self.order = []

    def arm(self):
        return {"armed": "X"}

    def prespawn_verdict(self):
        return {"prespawn": "ACQUIRED_CLEAN"}

    def release(self):
        self.released += 1
        self.order.append("release")

    def revalidate(self):
        pass

    def evaluate(self, tree_empty):
        # I-01 (R17): avalia SEM liberar a lease (handles retidos até prova de fechamento do Job).
        self.evaluated = tree_empty
        self.order.append("evaluate")
        return {"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM"}

    def disarm(self, tree_empty):
        self.disarmed = tree_empty
        v = self.evaluate(tree_empty)
        self.release()
        return v


class SupervisionReconcileHold(unittest.TestCase):
    """R13-ORIGIN-01: no esgotamento do prazo de reconciliação com a árvore viva, Supervision.run
    NÃO levanta nem encerra a custódia — permanece vivo (report-and-hold) e só finaliza/fecha quando
    a árvore esvazia. Prova com dupla de custódia e RECONCILE_HOLD_S=0 (sem matar processo real)."""

    def test_reserved_deadline_holds_then_finalizes_on_tree_empty(self):
        cust = _ReconcileCustody(live_polls=2)   # vive 2 amostragens após o prazo, depois esvazia
        guard = _ReconcileGuard()
        with mock.patch.object(sup, "make_custody", lambda log: cust), \
                mock.patch.object(sup, "W04Guard", lambda root, log: guard), \
                mock.patch.object(sup, "RECONCILE_HOLD_S", 0.0):
            with tempfile.TemporaryDirectory() as t:
                ev = Path(t) / "ev"; ev.mkdir()
                s = sup.Supervision(evidence=ev, protected_root=Path(t) / "prot",
                                    out_root=Path(t) / "out", label="L", log=lambda *a, **k: None)
                # timeout_s pequeno: o laço principal cai na reconciliação com a árvore viva
                result = s.run(["x"], {}, timeout_s=0.15)
                # (1) NÃO levantou; retornou um veredito
                self.assertIsInstance(result, dict)
                # (2) a decisão reservada foi SURGIDA à origem enquanto vivo (uma vez)
                self.assertTrue((ev / "L_W04_NOKILL_RESERVED_DECISION.json").exists())
                rec = json.loads((ev / "L_W04_NOKILL_RESERVED_DECISION.json").read_text())
                self.assertEqual(rec["custodian"], "ALIVE_SUPERVISING_HOLDS_W04_AND_JOB_NO_KILL")
                self.assertIn("SELF_TERMINATE_ON_LIVE_TREE", rec["supervisor_never"])
        # (3) fechou exatamente uma vez e SOMENTE com a árvore vazia (nunca com árvore viva)
        self.assertEqual(cust.closed, 1)
        self.assertEqual(cust.closed_while_live, 0)
        # (4) W04 só foi AVALIADA com a árvore vazia (proteção por toda a vida da árvore)
        self.assertIs(guard.evaluated, True)
        # (4b) I-01: a liberação física da lease ocorreu DEPOIS da avaliação (evaluate antes de release)
        self.assertEqual(guard.order[:2], ["evaluate", "release"])
        self.assertGreaterEqual(guard.released, 1)
        # (5) a reconciliação foi marcada como mantida viva, sem kill
        self.assertIn("RESERVED_DECISION_HELD_ALIVE_NO_KILL", result.get("reconcile_reason", ""))


class _LifecycleGuard:
    def __init__(self, prespawn_clean):
        self._clean = prespawn_clean
        self.released = 0

    def arm(self):
        return {"armed": "X"}

    def prespawn_verdict(self):
        return {"prespawn": "ACQUIRED_CLEAN"} if self._clean else {"prespawn": "BLOCKED_NO_SPAWN", "gaps": ["G"]}

    def release(self):
        self.released += 1

    def revalidate(self):
        pass

    def evaluate(self, tree_empty):
        return {"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM"}

    def disarm(self, tree_empty):
        v = self.evaluate(tree_empty)
        self.release()
        return v


class _LifecycleCustody:
    native_job = False
    breakaway_allowed = False

    def __init__(self, start_raises):
        self._start_raises = start_raises
        self.closed = 0
        self.started = False
        self.marks = []

    def mark(self, n):
        self.marks.append({"mark": n, "mono_ns": 1})

    def start(self, *a, **k):
        self.started = True
        if self._start_raises:
            raise RuntimeError("START_BOOM")
        return 4321

    def child_state(self):
        # Popen falhou antes de existir filho: estado declarado explicitamente (sem filho vivo).
        return {"child_created": False, "assigned": False, "resumed_threads": 0, "rollback": None,
                "child_alive": False, "pid": None}

    def close(self):
        self.closed += 1


class SupervisionPrespawnLifecycle(unittest.TestCase):
    """R11-ORIGIN-03: cust.close() roda EXATAMENTE UMA VEZ nos caminhos pré-spawn falhos (prespawn
    BLOCKED e exceção em start), sem matar processo real (custódia é uma dupla)."""

    def _run(self, *, prespawn_clean, start_raises, exc):
        cust = _LifecycleCustody(start_raises=start_raises)
        guard = _LifecycleGuard(prespawn_clean=prespawn_clean)
        with mock.patch.object(sup, "make_custody", lambda log: cust), \
                mock.patch.object(sup, "W04Guard", lambda root, log: guard):
            with tempfile.TemporaryDirectory() as t:
                ev = Path(t) / "ev"; ev.mkdir()
                s = sup.Supervision(evidence=ev, protected_root=Path(t) / "prot",
                                    out_root=Path(t) / "out", label="L", log=lambda *a, **k: None)
                with self.assertRaises(exc):
                    s.run(["x"], {}, timeout_s=5)
        return cust, guard

    def test_close_once_on_prespawn_block(self):
        cust, guard = self._run(prespawn_clean=False, start_raises=False, exc=sup.SupervisorBlocked)
        self.assertEqual(cust.closed, 1)
        self.assertFalse(cust.started)
        self.assertEqual(guard.released, 1)

    def test_close_once_on_start_exception(self):
        # R15 (INT-07): falha do start SEM filho vivo é bloqueio sem efeito (PrespawnBlocked), com
        # a lease liberada e o custodiante fechado exatamente uma vez.
        cust, guard = self._run(prespawn_clean=True, start_raises=True, exc=sup.PrespawnBlocked)
        self.assertEqual(cust.closed, 1)
        self.assertTrue(cust.started)
        self.assertEqual(guard.released, 1)


class _FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class NativeNegativesFreshProcess(unittest.TestCase):
    """R10 — fronteira fail-closed de _native_negatives_in_fresh_process: o filho DEVE sair com
    código 0. Controle negativo (reproduz o defeito da origem): um filho que grava um JSON completo
    e DEPOIS sai com código não zero NÃO pode ser aceito."""

    def _q(self):
        import pegasus_qualify_v008 as q
        return q

    def _full_records(self, q):
        return [{"case": n, "ok": True, "result": "PASS", "detail": {}} for n in q._NATIVE_NEGATIVE_CASES]

    def _run_with(self, q, evidence, *, rc, write_doc):
        """Chama a fronteira com subprocess.run mockado; o mock grava (ou não) o JSON e devolve rc."""
        result_path = evidence / "NATIVE_NEGATIVES_RESULT.json"
        sink = []

        def case(name, ok, **detail):
            sink.append({"case": name, "ok": ok})
            if not ok:
                raise AssertionError(name)

        def fake_run(cmd, **kw):
            if write_doc is not None:
                result_path.write_text(json.dumps(write_doc), encoding="utf-8")
            return _FakeProc(rc, stdout="child stdout rc=%d" % rc)

        with mock.patch("subprocess.run", side_effect=fake_run):
            q._native_negatives_in_fresh_process(evidence, evidence / "inputs", dict(os.environ), case, lambda *_: None)
        return sink

    def test_nonzero_child_exit_rejected_even_with_complete_json(self):
        # CONTROLE NEGATIVO: filho grava JSON completo (7 casos PASS, completed=True) e sai rc=3.
        q = self._q()
        doc = {"completed": True, "cases": self._full_records(q)}
        with tempfile.TemporaryDirectory() as t:
            ev = Path(t)
            with self.assertRaises(sup.SupervisorBlocked) as ctx:
                self._run_with(q, ev, rc=3, write_doc=doc)
            self.assertIn("NATIVE_NEGATIVES_CHILD_NONZERO_EXIT", str(ctx.exception))

    def test_zero_exit_complete_json_accepted(self):
        q = self._q()
        doc = {"completed": True, "cases": self._full_records(q)}
        with tempfile.TemporaryDirectory() as t:
            sink = self._run_with(q, Path(t), rc=0, write_doc=doc)
        self.assertEqual([c["case"] for c in sink], list(q._NATIVE_NEGATIVE_CASES))

    def test_zero_exit_missing_json_rejected(self):
        q = self._q()
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(sup.SupervisorBlocked) as ctx:
                self._run_with(q, Path(t), rc=0, write_doc=None)
            self.assertIn("NATIVE_NEGATIVES_CHILD_NO_RESULT", str(ctx.exception))



# =====================================================================================
# R15 — convergência integrada: cobertura USN, evidência terminal, disposições de custódia,
# isolamento de admissão e exceções do loop de supervisão (por invariante/classe, não por bug)
# =====================================================================================
def _usn_page(nxt, *records):
    return (True, 0, int(nxt).to_bytes(8, "little", signed=True) + b"".join(records))


def _usn_rec_v2(usn, frn=5, par=9, name="a.csv", reason=0x100):
    nb = name.encode("utf-16-le")
    rl = 60 + len(nb)
    rl += (-rl) % 8
    b = bytearray(rl)
    b[0:4] = rl.to_bytes(4, "little")
    b[4:6] = (2).to_bytes(2, "little")
    b[8:16] = frn.to_bytes(8, "little")
    b[16:24] = par.to_bytes(8, "little")
    b[24:32] = int(usn).to_bytes(8, "little", signed=True)
    b[40:44] = reason.to_bytes(4, "little")
    b[56:58] = len(nb).to_bytes(2, "little")
    b[58:60] = (60).to_bytes(2, "little")
    b[60:60 + len(nb)] = nb
    return bytes(b)


class UsnScanCoverage(unittest.TestCase):
    """C2/A02: a cobertura só é completa com progressão inequívoca até end_usn."""

    def _pages(self, *pages):
        seq = list(pages)
        def read(cur):
            return seq.pop(0) if seq else (False, 38, b"")
        return read

    def test_complete_reaches_end(self):
        r = sup.usn_scan_coverage(self._pages(_usn_page(200, _usn_rec_v2(120, frn=77), _usn_rec_v2(150))),
                                  100, 200, {77}, set())
        self.assertTrue(r["read_complete"]); self.assertIsNone(r["reason"])
        self.assertEqual([h["frn"] for h in r["hits"]], [77])

    def test_nonprogress_cursor_incomplete(self):
        r = sup.usn_scan_coverage(self._pages(_usn_page(100)), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertEqual(r["reason"], "USN_CURSOR_NOT_ADVANCING")

    def test_eof_before_end_incomplete(self):
        r = sup.usn_scan_coverage(lambda c: (False, 38, b""), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertEqual(r["reason"], "USN_EOF_BEFORE_END")

    def test_ioctl_failure_incomplete(self):
        r = sup.usn_scan_coverage(lambda c: (False, 5, b""), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertTrue(r["reason"].startswith("USN_READ_FAILED"))

    def test_journal_entry_deleted_incomplete(self):
        r = sup.usn_scan_coverage(lambda c: (False, 1181, b""), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertEqual(r["reason"], "USN_JOURNAL_ENTRY_DELETED")

    def test_malformed_record_incomplete(self):
        bad = _usn_page(200, (4).to_bytes(4, "little") + (2).to_bytes(2, "little") + b"\x00\x00")
        r = sup.usn_scan_coverage(self._pages(bad), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertEqual(r["reason"], "USN_RECORD_MALFORMED")

    def test_unknown_version_incomplete(self):
        rec = (64).to_bytes(4, "little") + (9).to_bytes(2, "little") + b"\x00" * 58
        r = sup.usn_scan_coverage(self._pages(_usn_page(200, rec)), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertTrue(r["reason"].startswith("USN_RECORD_VERSION_UNSUPPORTED"))

    def test_frn128_high_bits_unmappable(self):
        nb = "x".encode("utf-16-le"); rl = 76 + len(nb); rl += (-rl) % 8
        b = bytearray(rl); b[0:4] = rl.to_bytes(4, "little"); b[4:6] = (3).to_bytes(2, "little")
        b[8:16] = (5).to_bytes(8, "little"); b[16:24] = (1).to_bytes(8, "little")  # FRN bits altos != 0
        b[40:48] = (120).to_bytes(8, "little", signed=True); b[72:74] = len(nb).to_bytes(2, "little")
        b[74:76] = (76).to_bytes(2, "little"); b[76:76 + len(nb)] = nb
        r = sup.usn_scan_coverage(self._pages(_usn_page(200, bytes(b))), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertEqual(r["reason"], "USN_FRN128_UNMAPPABLE")

    def test_record_usn_out_of_window_rejected(self):
        r = sup.usn_scan_coverage(self._pages(_usn_page(200, _usn_rec_v2(250))), 100, 200, set(), set())
        self.assertFalse(r["read_complete"]); self.assertEqual(r["reason"], "USN_RECORD_ORDER_INVALID")

    def test_bounds_absent(self):
        self.assertFalse(sup.usn_scan_coverage(lambda c: _usn_page(c + 1), None, 200, set(), set())["read_complete"])


class W04UsnCoverageProof(unittest.TestCase):
    """C2: w04_verdict exige a PROVA de cobertura, não só o booleano read_complete."""

    def test_coverage_absent_blocks(self):
        g = good_w04(); g["usn"].pop("coverage")
        v = sup.w04_verdict(**g)
        self.assertEqual(v["w04_full"], "BLOCKED"); self.assertIn("USN_COVERAGE_PROOF_ABSENT", v["gaps"])

    def test_coverage_short_of_end_blocks(self):
        g = good_w04(); g["usn"]["coverage"] = dict(g["usn"]["coverage"], covered_to=800)
        v = sup.w04_verdict(**g)
        self.assertEqual(v["w04_full"], "BLOCKED"); self.assertIn("USN_COVERAGE_SHORT_OF_END", v["gaps"])

    def test_coverage_incomplete_reason_blocks(self):
        g = good_w04(); g["usn"]["coverage"] = dict(g["usn"]["coverage"], read_complete=False, reason="USN_EOF_BEFORE_END")
        v = sup.w04_verdict(**g)
        self.assertEqual(v["w04_full"], "BLOCKED")
        self.assertTrue(any(x.startswith("USN_COVERAGE_INCOMPLETE") for x in v["gaps"]))


class TreeVerifiedEmpty(unittest.TestCase):
    def test_requires_two_consecutive(self):
        self.assertFalse(sup.tree_verified_empty(0))
        self.assertFalse(sup.tree_verified_empty(1))
        self.assertTrue(sup.tree_verified_empty(2))
        self.assertTrue(sup.tree_verified_empty(3))


class StartFailureDisposition(unittest.TestCase):
    def test_no_child(self):
        self.assertEqual(sup.start_failure_disposition(child_created=False, assigned=False, resumed_threads=0),
                         "NO_CHILD_NO_EFFECT")

    def test_suspended_never_resumed_rolls_back(self):
        self.assertEqual(sup.start_failure_disposition(child_created=True, assigned=False, resumed_threads=0),
                         "ROLLBACK_OWN_SUSPENDED_CHILD")
        self.assertEqual(sup.start_failure_disposition(child_created=True, assigned=True, resumed_threads=0),
                         "ROLLBACK_OWN_SUSPENDED_CHILD")

    def test_running_child_never_terminated(self):
        self.assertEqual(sup.start_failure_disposition(child_created=True, assigned=True, resumed_threads=1),
                         "CHILD_RUNNING_UNDER_CUSTODY")


class OwnerDispositionAndRelease(unittest.TestCase):
    def _doc(self, **o):
        d = {"schema": sup.OWNER_DISPOSITION_SCHEMA, "disposition": "RELEASE_CUSTODY_LEAVE_TREE_RUNNING",
             "ack_label": "L", "ack_child_pid": 4242, "owner_statement": "autorizo deixar rodando"}
        d.update(o); return d

    def test_absent_is_wait(self):
        self.assertEqual(sup.owner_disposition_verdict(None, label="L", child_pid=4242)["disposition"], "WAIT")

    def test_valid_release(self):
        self.assertEqual(sup.owner_disposition_verdict(self._doc(), label="L", child_pid=4242)["disposition"], "RELEASE")

    def test_ack_mismatch_is_wait(self):
        self.assertEqual(sup.owner_disposition_verdict(self._doc(ack_child_pid=9), label="L", child_pid=4242)["disposition"], "WAIT")
        self.assertEqual(sup.owner_disposition_verdict(self._doc(ack_label="X"), label="L", child_pid=4242)["disposition"], "WAIT")

    def test_wrong_schema_is_wait(self):
        self.assertEqual(sup.owner_disposition_verdict(self._doc(schema="x"), label="L", child_pid=4242)["disposition"], "WAIT")

    def test_release_plan_requires_flag_cleared(self):
        self.assertTrue(sup.owner_release_plan(kill_on_close_cleared=True)["release"])
        bad = sup.owner_release_plan(kill_on_close_cleared=False)
        self.assertFalse(bad["release"]); self.assertTrue(bad["kill_risk"])


class TerminalEvidence(unittest.TestCase):
    STATUS = {"schema": sup.STATUS_SCHEMA_V003, "PHASE": "SYNTHETIC_COMMITTED", "COMMITTED": 3, "TOTAL": 3,
              "PCT": 100.0, "RATE": "UNKNOWN", "ETA": 0.0, "FINISH": "NOW", "ACTIVE": 0, "READY_WAITING": 0,
              "CHECKPOINT": "s3", "SAFE_STOP": "NO", "PROCESS_TREE_CLEAN": "YES", "STOP_REQUESTED": False,
              "run_instance": "4242_999", "out_root": "/o", "mode": "SYNTHETIC", "updated_at": "t"}

    def _v(self, mode="COMPLETION", status=None, **kw):
        base = dict(mode=mode, status=status if status is not None else dict(self.STATUS), status_state="OK",
                    pre_run_instance=None, supervised_pids={4242}, expected_out_root="/o",
                    checkpoint_ok=True, checkpoint_completed=3)
        base.update(kw)
        return sup.terminal_evidence_verdict(**base)

    def test_complete(self):
        self.assertEqual(self._v()["terminal"], "COMPLETE")

    def test_absent_status_incomplete(self):
        self.assertEqual(self._v(status={}, status_state="ABSENT")["terminal"], "INCOMPLETE")

    def test_stale_run_instance_rejected(self):
        self.assertIn("STATUS_NOT_FRESH_FOR_THIS_ATTEMPT", self._v(pre_run_instance="4242_999")["gaps"])

    def test_foreign_producer_rejected(self):
        self.assertIn("STATUS_PRODUCER_NOT_IN_SUPERVISED_TREE", self._v(supervised_pids={9999})["gaps"])

    def test_not_fully_committed_rejected(self):
        st = dict(self.STATUS, COMMITTED=2)
        self.assertIn("STATUS_NOT_FULLY_COMMITTED", self._v(status=st, checkpoint_completed=2)["gaps"])

    def test_checkpoint_mismatch_rejected(self):
        self.assertIn("CHECKPOINT_COMMITTED_MISMATCH", self._v(checkpoint_completed=2)["gaps"])

    def test_tree_not_clean_rejected(self):
        st = dict(self.STATUS, PROCESS_TREE_CLEAN="NO")
        self.assertIn("STATUS_PROCESS_TREE_NOT_CLEAN", self._v(status=st)["gaps"])

    def test_out_root_mismatch_rejected(self):
        self.assertIn("STATUS_OUT_ROOT_MISMATCH", self._v(expected_out_root="/other")["gaps"])

    def test_safe_stop_mode(self):
        st = dict(self.STATUS, SAFE_STOP="YES", COMMITTED=1, TOTAL=3, PCT=33.3)
        self.assertEqual(self._v(mode="SAFE_STOP", status=st, checkpoint_completed=1)["terminal"], "COMPLETE")


class CompletionTerminalRequired(unittest.TestCase):
    INV = {"a": {"type": "file", "sha256": "1"}}
    TERM = {"terminal": "COMPLETE", "mode": "COMPLETION", "gaps": []}
    LIN = {"lineage": "GAPLESS_NATIVE_JOB", "processes": 1}
    JIT = {"jit": "W04_ARMED_BEFORE_CHILD_CREATION_HELD_UNTIL_TREE_EMPTY"}
    W = {"w04_full": "PASS_NATIVE_SAME_ATTEMPT"}

    def _c(self, **kw):
        base = dict(child_exit=0, tree_empty=True, run_lock_present=False, inventory_a=self.INV,
                    inventory_b=dict(self.INV), w04=self.W, terminal=self.TERM, lineage=self.LIN, jit=self.JIT)
        base.update(kw)
        return sup.completion_verdict(**base)

    def test_all_proven_completes(self):
        self.assertTrue(self._c()["completed"])

    def test_missing_terminal_blocks(self):
        v = self._c(terminal=None)
        self.assertFalse(v["completed"]); self.assertTrue(any("TERMINAL_EVIDENCE_NOT_PROVEN" in g for g in v["gaps"]))

    def test_incomplete_terminal_blocks(self):
        v = self._c(terminal={"terminal": "INCOMPLETE", "mode": "COMPLETION", "gaps": ["STATUS_ABSENT"]})
        self.assertFalse(v["completed"])

    def test_missing_lineage_blocks(self):
        v = self._c(lineage={"lineage": "BLOCKED", "cause": "x"})
        self.assertFalse(v["completed"]); self.assertTrue(any("LINEAGE_NOT_PROVEN" in g for g in v["gaps"]))

    def test_missing_jit_blocks(self):
        v = self._c(jit={"jit": "BLOCKED"})
        self.assertFalse(v["completed"]); self.assertTrue(any("JIT_ORDER_NOT_PROVEN" in g for g in v["gaps"]))

    def test_posix_observational_lineage_ok_when_w04_non_native(self):
        v = self._c(w04={"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM"},
                    lineage={"lineage": "OBSERVATIONAL_POSIX_SESSION_NOT_NATIVE_PROOF", "processes_observed": 1})
        self.assertTrue(v["completed"])


class PlanIsolation(unittest.TestCase):
    def _plan(self, argv, out="/tmp/out", economic=False):
        return {"schema": sup.RUN_PLAN_SCHEMA, "argv": argv, "out_root": out, "economic": economic}

    def test_synthetic_chain_isolated(self):
        v = sup.plan_isolation_verdict(self._plan(["py", "-B", str(ROOT / "tests" / "synthetic_chain.py"),
                                                   "--out", "/tmp/o"]), package_root=ROOT)
        self.assertEqual(v["isolation"], "ISOLATED_NON_ECONOMIC", v)

    def test_code_runtime_rejected(self):
        v = sup.plan_isolation_verdict(self._plan(["py", "-I", str(ROOT / "CODE" / "pegasus_entry.py"), "run-b"]),
                                       package_root=ROOT)
        self.assertEqual(v["isolation"], "NOT_ISOLATED")
        self.assertTrue(any("ECONOMIC" in g for g in v["gaps"]))

    def test_economic_module_name_rejected(self):
        v = sup.plan_isolation_verdict(self._plan(["py", "-m", "r1r11_full_2026"]), package_root=ROOT)
        self.assertEqual(v["isolation"], "NOT_ISOLATED")

    def test_out_inside_package_rejected(self):
        v = sup.plan_isolation_verdict(self._plan(["py", "-B", str(ROOT / "tests" / "synthetic_chain.py")],
                                                  out=str(ROOT / "inside")), package_root=ROOT)
        self.assertIn("OUT_ROOT_INSIDE_SEALED_PACKAGE", v["gaps"])


class _ExcCustody(_ReconcileCustody):
    """Custódia-dupla parametrizável para exceções do loop: injeta falhas em stop/observe."""
    def __init__(self, *, live_polls=3, stop_raises=None, stop_result=None, observe_raises=0):
        super().__init__(live_polls=live_polls)
        self._stop_raises = stop_raises
        self._stop_result = stop_result
        self._observe_raises = observe_raises
        self.stop_calls = 0

    def request_stop(self):
        self.stop_calls += 1
        if self._stop_raises is not None:
            raise self._stop_raises
        return self._stop_result if self._stop_result is not None else {"delivered": True}

    def observe_tree(self):
        if self._observe_raises > 0:
            self._observe_raises -= 1
            raise RuntimeError("JOB_ACCOUNTING_FAILED_INJECTED")
        return "EMPTY" if self.tree_empty() else "LIVE"


class SupervisionCustodyExceptions(unittest.TestCase):
    """C1/I2: nenhuma exceção pós-spawn sai de run(); close() nunca com árvore viva; sem kill."""

    def _run(self, cust, *, out_fields=None, stop_after=None):
        guard = _ReconcileGuard()
        with mock.patch.object(sup, "make_custody", lambda log: cust), \
                mock.patch.object(sup, "W04Guard", lambda root, log: guard), \
                mock.patch.object(sup, "RECONCILE_HOLD_S", 0.0):
            with tempfile.TemporaryDirectory() as t:
                ev = Path(t) / "ev"; ev.mkdir(); out = Path(t) / "out"; out.mkdir()
                if out_fields is not None:
                    (out / "TELEMETRY").mkdir(parents=True)
                    (out / "TELEMETRY" / "R1R11_STATUS.json").write_text(json.dumps(out_fields), encoding="utf-8")
                s = sup.Supervision(evidence=ev, protected_root=Path(t) / "p", out_root=out, label="L",
                                    stop_after_committed=stop_after, log=lambda *a, **k: None)
                result = s.run(["x"], {}, timeout_s=0.2)
        return result, cust

    def _assert_safe(self, cust, result):
        self.assertIsInstance(result, dict)
        self.assertEqual(cust.closed, 1)
        self.assertEqual(cust.closed_while_live, 0)

    def test_stop_raises_holds_until_empty(self):
        c = _ExcCustody(live_polls=3, stop_raises=RuntimeError("CTRL_C_DELIVERY_FAILED helper_exit=7"))
        r, c = self._run(c, out_fields={"COMMITTED": 1, "TOTAL": 3, "ACTIVE": 1}, stop_after=1)
        self._assert_safe(c, r)

    def test_stop_structured_failure_holds(self):
        c = _ExcCustody(live_polls=3, stop_result={"delivered": False, "helper_exit": 7})
        r, c = self._run(c, out_fields={"COMMITTED": 1, "TOTAL": 3, "ACTIVE": 1}, stop_after=1)
        self._assert_safe(c, r)

    def test_observe_raises_holds(self):
        c = _ExcCustody(live_polls=2, observe_raises=2)
        r, c = self._run(c)
        self._assert_safe(c, r)

    def test_corrupt_telemetry_non_int_holds(self):
        c = _ExcCustody(live_polls=2)
        r, c = self._run(c, out_fields={"COMMITTED": "x?", "TOTAL": 3, "ACTIVE": "!"})
        self._assert_safe(c, r)

    def test_committed_gt_total_holds(self):
        c = _ExcCustody(live_polls=2)
        r, c = self._run(c, out_fields={"COMMITTED": 9, "TOTAL": 3, "ACTIVE": 1})
        self._assert_safe(c, r)

    def test_revalidate_raises_holds(self):
        guard = _ReconcileGuard()
        def boom():
            raise RuntimeError("W04_REVALIDATE_INJECTED")
        guard.revalidate = boom
        c = _ExcCustody(live_polls=2)
        with mock.patch.object(sup, "make_custody", lambda log: c), \
                mock.patch.object(sup, "W04Guard", lambda root, log: guard), \
                mock.patch.object(sup, "RECONCILE_HOLD_S", 0.0):
            with tempfile.TemporaryDirectory() as t:
                ev = Path(t) / "ev"; ev.mkdir(); out = Path(t) / "out"; out.mkdir()
                s = sup.Supervision(evidence=ev, protected_root=Path(t) / "p", out_root=out, label="L", log=lambda *a, **k: None)
                r = s.run(["x"], {}, timeout_s=0.2)
        self._assert_safe(c, r)


class AdmissionSealed(unittest.TestCase):
    """C4/INT-13: --admission só aceita o módulo sintético selado do pacote (caminho + SHA)."""

    def test_unsealed_path_refused(self):
        with tempfile.TemporaryDirectory() as t:
            eviladm = Path(t) / "evil.py"
            eviladm.write_text("ADMISSION=None\n", encoding="utf-8")
            ns = type("NS", (), {"admission": str(eviladm)})()
            with self.assertRaises(sup.SupervisorBlocked) as c:
                sup._load_admission(ns)
            self.assertIn("ADMISSION_MODULE_NOT_SEALED_SYNTHETIC", str(c.exception))

    def test_default_without_flag(self):
        ns = type("NS", (), {"admission": None})()
        self.assertIsInstance(sup._load_admission(ns), sup.DefaultReleaseAdmission)


# =====================================================================================
# R16 — fechamento sistêmico da família causal N1/N2/N3 (parecer físico da origem sobre a R15).
# Cada teste FALHA na R15 congelada (símbolo ausente ou comportamento contraditório) e PASSA nos
# bytes R16. Fixtures sintéticas; nenhum processo real; nenhuma chamada Win32.
# =====================================================================================
class _N1Custody:
    """start() falha DEPOIS de retomar 1 thread; o filho então morre rápido (child_alive=False).
    Efeitos são POSSÍVEIS: o supervisor não pode declarar bloqueio pré-spawn sem efeito."""
    native_job = False
    breakaway_allowed = False

    def __init__(self):
        self.closed = 0
        self.marks = []
        self._empty_after = 0

    def start(self, *a, **k):
        self.mark("CHILD_CREATED")
        raise RuntimeError("SIMULATED_FAILURE_AFTER_FIRST_THREAD_RESUME")

    def child_state(self):
        return {"child_created": True, "assigned": True, "resumed_threads": 1, "rollback": None,
                "child_alive": False, "pid": 777}

    def mark(self, n):
        self.marks.append({"mark": n, "mono_ns": 1})

    def poll(self):
        return 1  # filho morto rapidamente, exit != 0

    def sample(self):
        pass

    def observe_tree(self):
        return "EMPTY"

    def request_stop(self):
        return {"delivered": True}

    def accounting(self):
        return {"TotalProcesses": 1, "ActiveProcesses": 0}

    def new_process_events(self):
        return [{"pid": 777, "ctime": 5}]

    def close(self):
        self.closed += 1
        return {"closed": True, "handles_closed": True, "active_processes": 0, "reason": "FAKE_N1_CLOSE"}


class _N2Custody:
    """accounting final consistente com árvore vazia, mas close() RECUSA (prova closed=False)."""
    native_job = False
    breakaway_allowed = False

    def __init__(self):
        self.closed = 0
        self.marks = []

    def mark(self, n):
        self.marks.append({"mark": n, "mono_ns": 1})

    def accounting(self):
        return {"TotalProcesses": 1, "ActiveProcesses": 0}

    def new_process_events(self):
        return []

    def observe_tree(self):
        return "EMPTY"

    def tree_empty(self):
        return True

    def release_live_tree_by_owner(self):
        return {"released": False, "reason": "NO_OWNER_DISPOSITION"}

    def close(self):
        self.closed += 1
        # N2: o adaptador NÃO prova fechamento (handles retidos) — retorno sem prova.
        return {"closed": False, "handles_closed": False, "active_processes": 1,
                "reason": "FAKE_N2_CLOSE_REFUSED"}


class _N2Guard:
    def __init__(self):
        self.disarmed = 0
        self.evaluated = 0
        self.released = 0

    def evaluate(self, tree_empty):
        # I-01 (R17): avalia sem liberar; close recusado => release NUNCA é chamado.
        self.evaluated += 1
        return {"w04_full": "BLOCKED", "gaps": ["FAKE"]}

    def disarm(self, tree_empty):
        self.disarmed += 1
        v = self.evaluate(tree_empty)
        self.release()
        return v

    def release(self):
        self.released += 1


class _N3Supervision:
    """Supervisão sintética que devolve conclusão positiva com custódia resolvida."""
    def __init__(self, **kw):
        self.primary_error = None
        self.phase = "CUSTODIAN_CLOSED"
        self.ctx = {"custody_closed": True}

    def run(self, *a, **k):
        return {"label": "RECEIPT_FAIL", "child_exit": 0, "outcome": "TREE_EMPTY_CUSTODY_CLOSED",
                "w04": {"w04_full": "PASS_NATIVE_SAME_ATTEMPT"}, "lineage": {"lineage": "GAPLESS_NATIVE_JOB"},
                "completion": {"completed": True}}

    def _set_phase(self, *a, **k):
        pass

    def summary(self):
        return {"phase": self.phase}


class R16EffectClassPure(unittest.TestCase):
    """N1 puro: classificação de efeitos por fatos (não por 'morto na consulta')."""

    def test_resumed_thread_is_effects_possible(self):
        k = sup.start_failure_effect_class(child_created=True, assigned=True, resumed_threads=1,
                                           child_alive=False, rollback_confirmed=False)
        self.assertEqual(k, "EFFECTS_POSSIBLE_CHILD_EXECUTED")
        self.assertFalse(sup.start_failure_is_no_effect(k))

    def test_no_child_is_no_effect(self):
        k = sup.start_failure_effect_class(child_created=False, assigned=False, resumed_threads=0,
                                           child_alive=False, rollback_confirmed=False)
        self.assertTrue(sup.start_failure_is_no_effect(k))

    def test_suspended_rolled_back_is_no_effect(self):
        k = sup.start_failure_effect_class(child_created=True, assigned=False, resumed_threads=0,
                                           child_alive=False, rollback_confirmed=True)
        self.assertEqual(k, "NO_EFFECT_SUSPENDED_ROLLED_BACK")
        self.assertTrue(sup.start_failure_is_no_effect(k))

    def test_uncertain_is_fail_closed_not_no_effect(self):
        k = sup.start_failure_effect_class(child_created=True, assigned=True, resumed_threads=0,
                                           child_alive=None, rollback_confirmed=False)
        self.assertEqual(k, "EFFECTS_UNCERTAIN_FAIL_CLOSED")
        self.assertFalse(sup.start_failure_is_no_effect(k))

    def test_alive_no_resume_supervise(self):
        k = sup.start_failure_effect_class(child_created=True, assigned=True, resumed_threads=0,
                                           child_alive=True, rollback_confirmed=False)
        self.assertFalse(sup.start_failure_is_no_effect(k))


class R16CloseProofPure(unittest.TestCase):
    """N2 puro: fechamento só confirmado com prova (closed=True, ativo=0, árvore verificada)."""

    def test_none_is_not_proof(self):
        self.assertFalse(sup.custody_close_confirmed(None, tree_verified_empty=True))

    def test_closed_false_is_not_proof(self):
        self.assertFalse(sup.custody_close_confirmed({"closed": False, "active_processes": 0}, tree_verified_empty=True))

    def test_active_nonzero_is_not_proof(self):
        self.assertFalse(sup.custody_close_confirmed({"closed": True, "active_processes": 1}, tree_verified_empty=True))

    def test_tree_not_verified_is_not_proof(self):
        self.assertFalse(sup.custody_close_confirmed({"closed": True, "active_processes": 0}, tree_verified_empty=False))

    def test_full_proof_confirms(self):
        self.assertTrue(sup.custody_close_confirmed({"closed": True, "active_processes": 0}, tree_verified_empty=True))


class R16OutcomeCoherencePure(unittest.TestCase):
    """N3 puro: desfecho único e coerente; recibo ausente nunca é sucesso."""

    def test_completed_persisted_pass(self):
        o = sup.supervised_final_outcome(completed=True, stopped=False, receipt_persisted=True)
        self.assertEqual((o["result"], o["exit_code"]), ("PASS_SUPERVISED_RUN", sup.EXIT_PASS))

    def test_completed_not_persisted_is_fail(self):
        o = sup.supervised_final_outcome(completed=True, stopped=False, receipt_persisted=False)
        self.assertEqual(o["exit_code"], sup.EXIT_FAIL)
        self.assertTrue(o["result"].startswith("FAIL"))

    def test_stopped_persisted_safe_stop(self):
        o = sup.supervised_final_outcome(completed=False, stopped=True, receipt_persisted=True)
        self.assertEqual(o["exit_code"], sup.EXIT_SAFE_STOP)

    def test_nothing_persisted_fail(self):
        o = sup.supervised_final_outcome(completed=False, stopped=False, receipt_persisted=False)
        self.assertEqual(o["exit_code"], sup.EXIT_FAIL)


class R16Integration(unittest.TestCase):
    """N1/N2/N3 nos módulos reais: comportamento contraditório da R15 vira fail-closed coerente."""

    def test_n1_run_spawned_resumed_thread_is_not_no_effect(self):
        cust, guard = _N1Custody(), _ReconcileGuard()
        with mock.patch.object(sup, "RECONCILE_HOLD_S", 0.0):
            with tempfile.TemporaryDirectory() as t:
                ev = Path(t) / "ev"; ev.mkdir(); out = Path(t) / "out"; out.mkdir()
                s = sup.Supervision(evidence=ev, protected_root=Path(t) / "p", out_root=out, label="N1",
                                    log=lambda *a, **k: None)
                # Na R15 isto LEVANTA PrespawnBlocked (bug N1). Na R16 devolve um resultado estruturado.
                result = s._run_spawned(cust, guard, {"armed": "X"}, ["x"], {}, 5, 120.0)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("effects_started"))
        self.assertIsNot((result.get("completion") or {}).get("completed"), True)
        self.assertEqual(s.ctx.get("start_failure", {}).get("effect_class"), "EFFECTS_POSSIBLE_CHILD_EXECUTED")

    def test_n2_finalize_close_refused_is_not_custodian_closed(self):
        cust, guard = _N2Custody(), _N2Guard()
        with tempfile.TemporaryDirectory() as t:
            ev = Path(t) / "ev"; ev.mkdir(); out = Path(t) / "out"; out.mkdir()
            s = sup.Supervision(evidence=ev, protected_root=Path(t) / "p", out_root=out, label="N2",
                                log=lambda *a, **k: None)
            s.ctx["tree_verified_empty"] = True  # evita o laço de hold; isola a prova de fechamento
            with mock.patch.object(sup.Supervision, "_compute_result",
                                   lambda self, *a, **k: {"_compute": "R15_TERMINAL_PATH"}):
                s._finalize(cust, guard, {"armed": "X"}, 777, {"exit": "TREE_EMPTY", "rc": 0})
        # N2: close() recusou => NUNCA custody_closed=True nem fase CUSTODIAN_CLOSED.
        self.assertIsNot(s.ctx.get("custody_closed"), True)
        self.assertNotEqual(s.phase, "CUSTODIAN_CLOSED")
        # I-01 (R17): close recusado => a lease W04 NUNCA foi liberada fisicamente (handles retidos).
        self.assertEqual(guard.released, 0)
        self.assertGreaterEqual(guard.evaluated, 1)
        self.assertIs(s.ctx.get("w04_held_pending_close"), True)

    def test_n3_run_supervised_receipt_fail_is_coherent(self):
        import contextlib, io
        plan = dict(schema=sup.RUN_PLAN_SCHEMA, economic=False, label="RECEIPT_FAIL",
                    argv=["py", "-B", "synthetic.py"], out_root="/tmp/o", protected_root="/tmp/p",
                    admission_schema="SYNTH", admission_sha256="ABC")
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(sup, "Supervision", _N3Supervision), \
                mock.patch.object(sup, "plan_isolation_verdict",
                                  lambda *a, **k: {"isolation": "ISOLATED_NON_ECONOMIC", "gaps": []}), \
                mock.patch.object(sup, "persist_run_receipt",
                                  lambda *a, **k: {"persisted": False, "path": None, "error": "SIMULATED_IO_ERROR"}):
            with contextlib.redirect_stdout(buf):
                code = sup._run_supervised(plan, evidence=Path(t), entry=object())
        last = json.loads(buf.getvalue().strip().splitlines()[-1])
        # N3: coerência total — recibo não persistido => exit 3 E result FAIL (nunca PASS).
        self.assertEqual(code, sup.EXIT_FAIL)
        self.assertEqual(last["exit_code"], sup.EXIT_FAIL)
        self.assertTrue(str(last["result"]).startswith("FAIL"))


# =====================================================================================
# I-01 (R17) — a AVALIAÇÃO da W04 é separada da LIBERAÇÃO física da lease. W04Guard.evaluate
# nunca solta handles; só disarm (retrocompat) e release o fazem. Falha na R16 (W04Guard não
# possuía evaluate; disarm liberava sempre) e PASSA nos bytes R17.
# =====================================================================================
class _FakeNativeLease:
    """Dupla do W04NativeLease: registra se disarm foi chamado com release=True/False e os releases."""
    def __init__(self):
        self.disarm_calls = []
        self.released = 0
        self.rep = {"lease": {"targets": 1, "acquired": 1, "sharing_violations": [], "errors": [],
                              "held_until_tree_empty": True, "revalidation_failures": []},
                    "dirs": {"targets": 1, "acquired": 1, "errors": [], "held_until_tree_empty": True},
                    "usn": {"journal_id_start": 1, "journal_id_end": 1, "first_usn_end": 1, "start_usn": 2,
                            "end_usn": 3, "read_complete": True, "records_on_protected": [],
                            "coverage": {"read_complete": True, "reason": None, "start_usn": 2, "end_usn": 3,
                                         "covered_to": 3, "pages": 1, "records_parsed": 1}},
                    "identity": {"reparse_points": [], "id_changes": [], "sha_mismatch": [], "link_count_changes": []},
                    "census": {"truncated": False, "external_writers_under_target": [], "unresolved": 0,
                               "stats_start": None, "stats_end": None, "attempts": [1, 1]}}

    def disarm(self, tree_empty, release=True):
        self.disarm_calls.append(release)
        if release:
            self.release()
        return self.rep

    def release(self):
        self.released += 1


# =====================================================================================
# I-02 (R17) — verdade terminal ÚNICA em TODOS os ramos de _run_supervised. Um BLOCKED/exit 2 só é
# legítimo com o recibo canônico persistido; sobre um fallback FAIL o desfecho é FAIL/exit 3.
# Falha na R16 (ramo PrespawnBlocked retornava exit 2 fixo) e PASSA nos bytes R17.
# =====================================================================================
class _PrespawnBlockedSupervision:
    def __init__(self, **kw):
        self.primary_error = None
        self.phase = "PRESPAWN"
        self.ctx = {}

    def run(self, *a, **k):
        raise sup.PrespawnBlocked("W04_ARM_INCOMPLETE_NO_SPAWN_NO_PROTECTED_EFFECTS:TEST")

    def _set_phase(self, *a, **k):
        pass

    def summary(self):
        return {"phase": self.phase}


class R17TerminalCoherencePure(unittest.TestCase):
    def test_prespawn_block_persisted_is_blocked(self):
        o = sup.terminal_for_prespawn_block(True)
        self.assertEqual((o["result"], o["exit_code"]), ("BLOCKED_PRESPAWN_NO_EFFECT", sup.EXIT_BLOCKED))

    def test_prespawn_block_not_persisted_is_fail(self):
        o = sup.terminal_for_prespawn_block(False)
        self.assertEqual(o["exit_code"], sup.EXIT_FAIL)
        self.assertTrue(o["result"].startswith("FAIL"))

    def test_post_spawn_fail_is_always_fail(self):
        for p in (True, False):
            o = sup.terminal_for_post_spawn_fail(p, effects_started=True)
            self.assertEqual(o["exit_code"], sup.EXIT_FAIL)
            self.assertTrue(o["result"].startswith("FAIL"))


class R17TerminalCoherenceIntegration(unittest.TestCase):
    def _run(self, persisted):
        import contextlib, io
        plan = dict(schema=sup.RUN_PLAN_SCHEMA, economic=False, label="PRESPAWN",
                    argv=["py", "-B", "synthetic.py"], out_root="/tmp/o", protected_root="/tmp/p",
                    admission_schema="SYNTH", admission_sha256="ABC")
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(sup, "Supervision", _PrespawnBlockedSupervision), \
                mock.patch.object(sup, "plan_isolation_verdict",
                                  lambda *a, **k: {"isolation": "ISOLATED_NON_ECONOMIC", "gaps": []}), \
                mock.patch.object(sup, "persist_run_receipt",
                                  lambda *a, **k: {"persisted": persisted, "path": "/x" if persisted else None,
                                                   "error": None if persisted else "SIMULATED_IO_ERROR"}):
            with contextlib.redirect_stdout(buf):
                code = sup._run_supervised(plan, evidence=Path(t), entry=object())
        last = json.loads(buf.getvalue().strip().splitlines()[-1])
        return code, last

    def test_prespawn_block_with_canonical_receipt_is_exit_2(self):
        code, last = self._run(persisted=True)
        self.assertEqual(code, sup.EXIT_BLOCKED)
        self.assertEqual(last["exit_code"], sup.EXIT_BLOCKED)
        self.assertEqual(last["result"], "BLOCKED_PRESPAWN_NO_EFFECT")

    def test_prespawn_block_with_failed_receipt_is_exit_3_coherent(self):
        # R16: retornava exit 2 fixo mesmo com o fallback FAIL gravado (verdade terminal incoerente).
        code, last = self._run(persisted=False)
        self.assertEqual(code, sup.EXIT_FAIL)
        self.assertEqual(last["exit_code"], sup.EXIT_FAIL)
        self.assertTrue(str(last["result"]).startswith("FAIL"))
        self.assertEqual(last["exit_class"], sup.classify_exit(sup.EXIT_FAIL))


# =====================================================================================
# I-03 (R17) — admissão de PRODUÇÃO real e encadeamento B->C->FULL, fail-closed. A rota existe,
# é alcançável e condicionada aos contratos técnicos; mesmo um pacote de autorização completo
# bloqueia no selo final. Falha na R16 (não havia ProductionReleaseAdmission/production_admission_
# verdict; run-full escolhia phase=B) e PASSA nos bytes R17.
# =====================================================================================
_RELEASE_ID = "SYNTHETIC_RELEASE_2026_R18_ISOLATED"


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest().upper()


def _write_physical_gates(bundle_root, release_id=_RELEASE_ID):
    """Escreve um ARQUIVO físico por gate obrigatório sob bundle_root/gates/ e devolve os registros
    com SHA REAL do conteúdo (prova física, não SHA textual)."""
    gdir = Path(bundle_root) / "gates"
    gdir.mkdir(parents=True, exist_ok=True)
    gates = {}
    for g in sup.REQUIRED_PRODUCTION_GATES:
        rel = "gates/%s.json" % g
        content = json.dumps({"gate": g, "release_id": release_id, "attestation": "SYNTHETIC_PASS"},
                             sort_keys=True).encode("utf-8")
        (Path(bundle_root) / rel).write_bytes(content)
        gates[g] = {"path": rel, "sha256": _sha_bytes(content), "status": "PASS", "release_id": release_id}
    return gates


def _physical_bundle(bundle_root, *, phase_chain=None, release_id=_RELEASE_ID, external_module=None):
    b = {"schema": sup.PRODUCTION_AUTH_SCHEMA, "release_id": release_id,
         "gates": _write_physical_gates(bundle_root, release_id),
         "phase_chain": phase_chain if phase_chain is not None else {"B": "PASS", "C": "PASS"}}
    if external_module is not None:
        b["external_admission_module"] = external_module
    return b


class _FakeEntryRunDisabled:
    """V003 congelado: RELEASE_STATE != RUN_RELEASED => G00_RUN_RELEASE_DISABLED (decisão reservada)."""
    class Blocked(RuntimeError):
        pass

    def release_admission(self, req, phase):
        raise self.Blocked("G00_RUN_RELEASE_DISABLED; QS2/QS3/QS4/QS5_B06_AND_R01_R06_PENDING")


class _FakeEntryDefer:
    """Fixture SINTÉTICA: RELEASE_STATE=RUN_RELEASED => o V003 delega ao módulo externo autorizado
    (G00_EXTERNAL_RELEASE_ADMISSION_NOT_INSTALLED). NÃO é o entry real; serve só para exercitar a
    plumbing de forma isolada, sem tocar o V003 real nem ser confundida com release real."""
    class Blocked(RuntimeError):
        pass

    def release_admission(self, req, phase):
        raise self.Blocked("G00_EXTERNAL_RELEASE_ADMISSION_NOT_INSTALLED")


_SYNTH_EXTERNAL_MODULE = '''
"""Modulo de admissao EXTERNO SINTETICO e ISOLADO (nao e release real do V003)."""
import os, sys, tempfile
import pegasus_supervisor_v008 as sup

class _Adm:
    schema = "SYNTHETIC_ISOLATED_EXTERNAL_ADMISSION"
    def admit(self, *, phase, package_root, entry, ns, verdict):
        out = os.path.join(tempfile.mkdtemp(prefix="pegasus_synth_econ_"), "OUT")
        prot = tempfile.mkdtemp(prefix="pegasus_synth_prot_")
        receipt = {"granted": True, "kind": "SYNTHETIC_ISOLATED",
                   "release_id": verdict.get("release_id"),
                   "authority": "SYNTHETIC_EXTERNAL_MODULE_NOT_REAL_V003_RELEASE"}
        # argv aponta um runtime SINTETICO (nunca CODE/ nem modulos economicos reais)
        argv = [sys.executable, "-I", "-c",
                "import os,sys; os.makedirs(sys.argv[1], exist_ok=True); "
                "open(os.path.join(sys.argv[1],'SYNTH_ECON.txt'),'w').write('synthetic'); sys.exit(0)",
                out]
        return sup.make_run_plan(label="SYNTH_ECON_"+phase, argv=argv, protected_root=prot, out_root=out,
                                 economic=True, external_authorization_proven=True,
                                 admission_schema=self.schema, admission_sha256="SYNTH",
                                 release_admission_receipt=receipt, plan_kind="SYNTHETIC_ISOLATED",
                                 timeout_s=60)

ADMISSION = _Adm()
'''


class R18ProductionAdmissionPhysicalGates(unittest.TestCase):
    """Prova FÍSICA dos gates: lê+re-hasheia o arquivo, proveniência, path-safety. Falha na R17
    (production_admission_verdict so aceitava SHA textual) e PASSA nos bytes R18."""

    def test_absent_bundle_blocked(self):
        v = sup.production_admission_verdict(None, phase="B", bundle_root=None)
        self.assertEqual(v["admission"], "BLOCKED")
        self.assertIn("AUTHORIZATION_BUNDLE_ABSENT", v["gaps"])

    def test_physically_verified_complete(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertEqual(v["admission"], "ADMITTED_GATES_PHYSICALLY_VERIFIED")
            self.assertEqual(set(v["gates_physically_verified"]), set(sup.REQUIRED_PRODUCTION_GATES))

    def test_invented_sha_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            b["gates"]["QS4_SUCCESSOR_QUALIFICATION"]["sha256"] = "B" * 64  # SHA inventado
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertEqual(v["admission"], "BLOCKED")
            self.assertTrue(any("GATE_CONTENT_SHA_MISMATCH" in x for x in v["gaps"]))

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            (Path(t) / "gates" / "POLICYROOT_LIVE_CAPTURE.json").unlink()
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertTrue(any("GATE_FILE_ABSENT" in x for x in v["gaps"]))

    def test_false_status_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            b["gates"]["QS5_B06_INDEPENDENT_AUDIT"]["status"] = "PENDING"
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertTrue(any("GATE_NOT_PASS" in x for x in v["gaps"]))

    def test_stale_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            b["gates"]["SOURCE_ADMISSION_BY_HASH"]["release_id"] = "OTHER_STALE_RELEASE"
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertTrue(any("GATE_PROVENANCE_RELEASE_ID_MISMATCH_OR_STALE" in x for x in v["gaps"]))

    def test_concurrent_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            # altera o conteúdo do arquivo APÓS o bundle ter sido escrito (manipulação concorrente)
            (Path(t) / "gates" / "R01_R06_PHYSICAL_DEFINITIONS.json").write_bytes(b"tampered")
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertTrue(any("GATE_CONTENT_SHA_MISMATCH_OR_CONCURRENT_MUTATION" in x for x in v["gaps"]))

    def test_reparse_alias_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            victim = Path(t) / "gates" / "VOLUME_SERIAL_AND_FREE_SPACE.json"
            victim.unlink()
            try:
                victim.symlink_to(Path(t) / "gates" / "R01_R06_PHYSICAL_DEFINITIONS.json")
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertTrue(any("REPARSE_OR_ALIAS" in x for x in v["gaps"]))

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t)
            b["gates"]["RUNTIME_PYTHON_3_14_7_PS_5_1"]["path"] = "../escape.json"
            v = sup.production_admission_verdict(b, phase="B", bundle_root=Path(t))
            self.assertTrue(any("ESCAPE" in x or "OUTSIDE" in x for x in v["gaps"]))

    def test_chain_predecessor_enforced(self):
        with tempfile.TemporaryDirectory() as t:
            b = _physical_bundle(t, phase_chain={})  # FULL exige B e C
            v = sup.production_admission_verdict(b, phase="FULL", bundle_root=Path(t))
            self.assertTrue(any("PHASE_CHAIN_PREDECESSOR_NOT_PASS" in x for x in v["gaps"]))


class R18ReservedOwnerReleaseDecision(unittest.TestCase):
    """Sobre o artefato congelado a rota chega HONESTAMENTE à decisão reservada e para: nenhuma
    execução econômica real é alcançável sem uma nova decisão de release legitimamente autorizada."""

    def _bundle(self, d, **kw):
        p = Path(d) / "AUTH_BUNDLE.json"
        p.write_text(json.dumps(_physical_bundle(d, **kw)), encoding="utf-8")
        return str(p)

    def test_frozen_entry_yields_reserved_decision(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pkg:
            adm = sup.ProductionReleaseAdmission(self._bundle(t))
            entry = _FakeEntryRunDisabled()
            with self.assertRaises(entry.Blocked) as cm:
                adm.admit(phase="B", package_root=Path(pkg), entry=entry, ns=None)
            self.assertIn("RESERVED_OWNER_RELEASE_DECISION", str(cm.exception))

    def test_incomplete_bundle_blocks_before_signal(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pkg:
            path = Path(t) / "AUTH_BUNDLE.json"
            path.write_text(json.dumps({"schema": "WRONG"}), encoding="utf-8")
            adm = sup.ProductionReleaseAdmission(str(path))
            entry = _FakeEntryRunDisabled()
            with self.assertRaises(entry.Blocked) as cm:
                adm.admit(phase="B", package_root=Path(pkg), entry=entry, ns=None)
            self.assertIn("PRODUCTION_ADMISSION_BLOCKED", str(cm.exception))

    def test_bundle_inside_sealed_package_forbidden(self):
        with tempfile.TemporaryDirectory() as pkg:
            path = Path(pkg) / "AUTH_BUNDLE.json"
            path.write_text(json.dumps(_physical_bundle(pkg)), encoding="utf-8")
            adm = sup.ProductionReleaseAdmission(str(path))
            with self.assertRaises(sup.SupervisorBlocked):
                adm.admit(phase="B", package_root=Path(pkg), entry=_FakeEntryRunDisabled(), ns=None)


class R18ExternalRouteSyntheticE2E(unittest.TestCase):
    """Demonstração E2E SINTÉTICA e ISOLADA: com RELEASE_STATE=RUN_RELEASED (fixture) o V003 delega
    ao módulo externo autorizado (SHA-bound), que produz um RunPlan econômico de espécie
    SYNTHETIC_ISOLATED; `_run_supervised` o EXECUTA sob supervisão SEM tocar o V003 real. Uma admissão
    positiva simulada NUNCA é confundida com release real."""

    def _external_module(self, d):
        p = Path(d) / "external_release_admission.py"
        p.write_text(_SYNTH_EXTERNAL_MODULE, encoding="utf-8")
        return p

    def test_external_module_identity_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pkg:
            modp = self._external_module(t)
            b = _physical_bundle(t, external_module={"path": str(modp), "sha256": "C" * 64})
            path = Path(t) / "AUTH_BUNDLE.json"; path.write_text(json.dumps(b), encoding="utf-8")
            adm = sup.ProductionReleaseAdmission(str(path))
            with self.assertRaises(sup.SupervisorBlocked) as cm:
                adm.admit(phase="B", package_root=Path(pkg), entry=_FakeEntryDefer(), ns=None)
            self.assertIn("EXTERNAL_ADMISSION_MODULE_IDENTITY_MISMATCH", str(cm.exception))

    def test_defer_loads_external_module_and_admits_economic_plan(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pkg:
            modp = self._external_module(t)
            import hashlib as _h
            msha = _h.sha256(modp.read_bytes()).hexdigest().upper()
            b = _physical_bundle(t, external_module={"path": str(modp), "sha256": msha})
            path = Path(t) / "AUTH_BUNDLE.json"; path.write_text(json.dumps(b), encoding="utf-8")
            adm = sup.ProductionReleaseAdmission(str(path))
            plan = adm.admit(phase="B", package_root=Path(pkg), entry=_FakeEntryDefer(), ns=None)
            self.assertEqual(plan["schema"], sup.RUN_PLAN_SCHEMA)
            self.assertTrue(plan["economic"])
            self.assertEqual(plan["plan_kind"], "SYNTHETIC_ISOLATED")
            self.assertIs(plan["release_admission_receipt"]["granted"], True)

    def test_supervised_executes_synthetic_economic_plan(self):
        # A plumbing econômica é ALCANÇÁVEL: o plano sintético entra em _run_supervised (não é
        # bloqueado por falta de recibo) e roda sob supervisão. (Resultado terminal nao e o foco.)
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pkg:
            modp = self._external_module(t)
            import hashlib as _h
            msha = _h.sha256(modp.read_bytes()).hexdigest().upper()
            b = _physical_bundle(t, external_module={"path": str(modp), "sha256": msha})
            path = Path(t) / "AUTH_BUNDLE.json"; path.write_text(json.dumps(b), encoding="utf-8")
            adm = sup.ProductionReleaseAdmission(str(path))
            plan = adm.admit(phase="B", package_root=Path(pkg), entry=_FakeEntryDefer(), ns=None)
            with tempfile.TemporaryDirectory() as ev:
                code = sup._run_supervised(plan, evidence=Path(ev), entry=_FakeEntryDefer())
            # NAO foi bloqueado por falta de recibo/isolamento: entrou na execucao supervisionada.
            self.assertIn(code, (sup.EXIT_PASS, sup.EXIT_FAIL, sup.EXIT_SAFE_STOP))

    def test_run_supervised_economic_without_receipt_blocks(self):
        plan = dict(sup.make_run_plan(label="X", argv=["py", "-c", "0"], protected_root="/p",
                                      out_root="/tmp/zzz_r18", economic=True,
                                      external_authorization_proven=True, admission_schema="S",
                                      admission_sha256="H",
                                      release_admission_receipt={"granted": True, "kind": "SYNTHETIC_ISOLATED"}))
        plan["release_admission_receipt"] = None  # recibo removido depois de criado
        with self.assertRaises(sup.SupervisorBlocked) as cm:
            sup._run_supervised(plan, evidence=Path("/tmp/zzz_r18_ev"), entry=_FakeEntryDefer())
        self.assertIn("ECONOMIC_PLAN_WITHOUT_RELEASE_ADMISSION_RECEIPT", str(cm.exception))


class R17W04EvaluateVsRelease(unittest.TestCase):
    def test_evaluate_holds_handles(self):
        g = sup.W04Guard.__new__(sup.W04Guard)
        g.impl = _FakeNativeLease(); g.root = Path("/x"); g.native = True; g.baseline = None
        v = g.evaluate(tree_empty=True)
        self.assertEqual(v["w04_full"], "PASS_NATIVE_SAME_ATTEMPT")
        self.assertEqual(g.impl.disarm_calls, [False])  # avaliou SEM pedir release
        self.assertEqual(g.impl.released, 0)            # handles ainda retidos

    def test_release_closes_only_after_explicit_call(self):
        g = sup.W04Guard.__new__(sup.W04Guard)
        g.impl = _FakeNativeLease(); g.root = Path("/x"); g.native = True; g.baseline = None
        g.evaluate(tree_empty=True)
        self.assertEqual(g.impl.released, 0)
        g.release()
        self.assertEqual(g.impl.released, 1)

    def test_disarm_is_evaluate_then_release(self):
        g = sup.W04Guard.__new__(sup.W04Guard)
        g.impl = _FakeNativeLease(); g.root = Path("/x"); g.native = True; g.baseline = None
        g.disarm(tree_empty=True)
        # retrocompat: avaliou e liberou num passo
        self.assertEqual(g.impl.released, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
