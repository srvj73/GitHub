"""PEGASUS FULL 2026 V008 — qualificação integrada NÃO econômica sob o supervisor.

Usa o runtime REAL do V003 (`tests/synthetic_chain.py` -> coordenador, workers, journal,
pending, checkpoint, RunLock) somente sobre fixtures SINTÉTICAS geradas por
`r1r11_fixtures.generate`. Cada execução roda sob o supervisor (W04 + custódia + SAFE_STOP +
porta de conclusão). No Windows nativo, W04/Job são reais; em outras plataformas o resultado
W04/Job é marcado como não nativo e jamais promove G2/G3.

Casos (todos no mesmo processo de qualificação, roots novos, nada é apagado):
  Q01 referência mono-worker (limpa) sob supervisão
  Q02 multi-worker: bytes econômicos == Q01 (comparação A/B determinística)
  Q03 SAFE_STOP injetado pelo supervisor após 1º commit -> 130 confirmado pelo supervisor
  Q04 retomada de Q03 -> bytes == Q01 (exactly-once, nada COMMITTED repetido)
  Q05 lacuna 1: fault after_journal (journal ativo, sem pending)
  Q06 lacuna 2 na retomada: crash after_commit_before_checkpoint (exit 87, RUN.lock órfão)
  Q07 retomada final: RUN.lock órfão reconciliado por identidade, commit órfão reconciliado,
      bytes == Q01, sessões já COMMITTED intactas
  Q08 negativo: journal duplicado/sobreposto -> fail-closed, sem mutação de COMMITTED
  Q09 porta de evidência: estado com RUN.lock órfão NÃO é aceito como COMPLETED
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CODE = ROOT / "CODE"
sys.path.insert(0, str(HERE))
import pegasus_supervisor_v008 as sup  # noqa: E402


def _economic(out: Path) -> dict:
    # Mesma definição do tests/qualify.py do V003 (inclui qualquer resíduo sob sessions/).
    r = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted((out / "sessions").rglob("*")) if p.is_file()}
    cp = out / "CHECKPOINT.json"
    r["CHECKPOINT.json"] = hashlib.sha256(cp.read_bytes()).hexdigest() if cp.is_file() else None
    return r


def _committed_files(out: Path) -> dict:
    return {p.relative_to(out).as_posix(): sup.sha256_file(p)
            for p in sorted((out / "sessions").rglob("*")) if p.is_file() and ".pending" not in p.as_posix()}


def run_qualification(evidence: Path, workers_ref: int = 1, workers_multi: int = 3) -> int:
    evidence = Path(evidence).resolve()
    if evidence.is_relative_to(ROOT):
        raise sup.SupervisorBlocked("EVIDENCE_INSIDE_SEALED_PACKAGE_FORBIDDEN")
    evidence.mkdir(parents=True, exist_ok=False)
    log_path = evidence / "SUPERVISOR_LOG.txt"

    def log(msg: str) -> None:
        line = time.strftime("%Y-%m-%dT%H:%M:%S") + " " + msg
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    entry = sup._import_entry()
    manifest_sha = entry.verify_tree(ROOT)
    parents = sup.verify_supervisor_parents()
    log("PACKAGE_VERIFIED=" + manifest_sha)
    if str(CODE) not in sys.path:
        sys.path.insert(0, str(CODE))
    from r1r11_fixtures import generate
    inputs = evidence / "inputs"
    generate(inputs, heavy_cycles=2)

    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    chain = ROOT / "tests" / "synthetic_chain.py"

    def argv(out: Path, workers: int, fault=None, reference=False):
        a = [sys.executable, "-B", str(chain), "--inputs", str(inputs), "--out", str(out),
             "--workers", str(workers)]
        if fault:
            a += ["--fault", fault]
        if reference:
            a.append("--reference")
        return a

    def supervise(label, out, workers, fault=None, reference=False, stop_after=None):
        s = sup.Supervision(evidence=evidence, protected_root=inputs, out_root=out, label=label,
                            stop_after_committed=stop_after, log=log)
        r = s.run(argv(out, workers, fault, reference), env)
        log("CASE_RESULT %s exit=%s" % (label, r["child_exit"]))
        return r

    receipt = {"schema": "PEGASUS_FULL_2026_V008_INTEGRATED_QUALIFICATION_V001",
               "platform": platform.platform(), "python": sys.version.split()[0], "os_name": os.name,
               "native_windows": os.name == "nt", "economic_execution": False, "synthetic_only": True,
               "package_manifest_sha256": manifest_sha, "supervisor_parents": parents,
               "tested_code_sha256": {p.name: sup.sha256_file(p) for p in sorted(CODE.glob("*.py"))},
               "tested_supervisor_sha256": {p.name: sup.sha256_file(p) for p in sorted(HERE.glob("*.py"))},
               "cases": [], **sup.GATES}

    def case(name, ok, **detail):
        receipt["cases"].append({"case": name, "result": "PASS" if ok else "FAIL", **detail})
        log("%s=%s" % (name, "PASS" if ok else "FAIL"))
        if not ok:
            raise AssertionError(name + " " + json.dumps(detail, sort_keys=True, default=str)[:2000])

    started = time.time()
    try:
        ref = evidence / "Q01_reference_w1"
        r1 = supervise("Q01_reference_w1", ref, workers_ref, reference=True)
        case("Q01_REFERENCE_SUPERVISED_COMPLETED", r1["child_exit"] == 0 and r1["completion"]["completed"],
             completion=r1["completion"], w04=r1["w04"], lineage=r1["lineage"], jit=r1["jit"])
        clean = _economic(ref)

        multi = evidence / ("Q02_multi_w%d" % workers_multi)
        r2 = supervise("Q02_multi", multi, workers_multi)
        case("Q02_MULTIWORK_BYTES_EQUAL_REFERENCE",
             r2["child_exit"] == 0 and r2["completion"]["completed"] and _economic(multi) == clean,
             lineage=r2["lineage"], w04=r2["w04"])

        stop = evidence / "Q03_safe_stop"
        r3 = supervise("Q03_safe_stop", stop, 2, stop_after=1)
        committed_at_stop = int(r3["status"].get("COMMITTED", -1))
        case("Q03_SAFE_STOP_CONFIRMED_BY_SUPERVISOR",
             r3["safe_stop"]["safe_stop"].startswith("CONFIRMED_BY_SUPERVISOR") and 1 <= committed_at_stop <= 3,
             safe_stop=r3["safe_stop"], committed_at_stop=committed_at_stop, w04=r3["w04"])
        before = _committed_files(stop)
        r4 = supervise("Q04_safe_stop_resume", stop, 3)
        case("Q04_RESUME_EXACTLY_ONCE_AFTER_SAFE_STOP",
             r4["child_exit"] == 0 and r4["completion"]["completed"] and _economic(stop) == clean
             and all(_committed_files(stop).get(k) == v for k, v in before.items()),
             committed_before=len(before))

        gap = evidence / "Q05_two_gap_chain"
        r5 = supervise("Q05_gap1_after_journal", gap, 2, fault="after_journal")
        active = sorted(p.name for p in (gap / "_commit_journal").iterdir()) if (gap / "_commit_journal").exists() else []
        case("Q05_GAP1_JOURNAL_WITHOUT_PENDING",
             r5["child_exit"] not in (0, None) and len(active) == 1
             and not any(".pending" in k for k in sup.inventory(gap)) and not r5["run_lock_present"],
             child_exit=r5["child_exit"], active_journals=active)

        neg = evidence / "Q08_duplicate_journal_negative"
        shutil.copytree(gap, neg)
        src = neg / "_commit_journal" / active[0]
        s_name, rest = active[0].split(".", 1)
        inst, _json = rest.rsplit(".", 1)
        pid_part, ns_part = inst.split("_")
        dup = neg / "_commit_journal" / ("%s.%s_%d.json" % (s_name, pid_part, int(ns_part) + 1))
        dup.write_bytes(src.read_bytes())
        neg_before = _committed_files(neg)
        r8 = supervise("Q08_duplicate_journal_negative", neg, 2)
        child_log = (evidence / "Q08_duplicate_journal_negative.child.log").read_text(errors="replace")
        case("Q08_DUPLICATE_JOURNAL_FAIL_CLOSED",
             r8["child_exit"] not in (0, None) and "MULTIPLE_UNRESOLVED_JOURNALS" in child_log
             and _committed_files(neg) == neg_before and not r8["completion"]["completed"],
             child_exit=r8["child_exit"])

        before_gap2 = _committed_files(gap)
        r6 = supervise("Q06_gap2_crash_commit_checkpoint", gap, 2, fault="crash:after_commit_before_checkpoint")
        orphan_lock = json.loads((gap / "RUN.lock").read_text()) if (gap / "RUN.lock").exists() else None
        case("Q06_GAP2_CRASH_AFTER_COMMIT_BEFORE_CHECKPOINT",
             r6["child_exit"] == 87 and orphan_lock is not None
             and all(_committed_files(gap).get(k) == v for k, v in before_gap2.items()),
             child_exit=r6["child_exit"], orphan_run_lock_pid=(orphan_lock or {}).get("pid"))

        gate = sup.completion_verdict(child_exit=0, tree_empty=True, run_lock_present=(gap / "RUN.lock").exists(),
                                      inventory_a=sup.inventory(gap), inventory_b=sup.inventory(gap))
        case("Q09_EVIDENCE_GATE_REFUSES_ORPHAN_LOCK_STATE", gate["completed"] is False and "RUN_LOCK_PRESENT" in gate["gaps"],
             gate=gate)

        before_final = _committed_files(gap)
        r7 = supervise("Q07_final_resume", gap, 3)
        hist = sorted(p.name for p in (gap / "_journal_history").iterdir())
        case("Q07_TWO_GAPS_RESUME_EXACTLY_ONCE",
             r7["child_exit"] == 0 and r7["completion"]["completed"] and _economic(gap) == clean
             and all(_committed_files(gap).get(k) == v for k, v in before_final.items())
             and any(h.endswith(".RECOVERED_REQUEUE") for h in hist)
             and any(h.endswith(".RECOVERED_COMMITTED") for h in hist)
             and not (gap / "RUN.lock").exists(),
             journal_history=hist)
        if os.name == "nt":
            _windows_native_negatives(evidence, inputs, env, case, log)
        else:
            receipt["cases"].append({"case": "Q10_W04_NATIVE_NEGATIVES", "result": "SKIPPED_NON_NATIVE",
                                     "reason": "Lease de compartilhamento/USN existem só no Windows; não promove G2."})
            receipt["cases"].append({"case": "Q11_JOB_LINEAGE_BREAKAWAY", "result": "SKIPPED_NON_NATIVE",
                                     "reason": "Job Object existe só no Windows; não promove G3."})
        receipt["result"] = "PASS_INTEGRATED_SUPERVISED_QUALIFICATION_SYNTHETIC"
        receipt["w04_g2_g3_native"] = "QUALIFIED_ON_THIS_HOST" if os.name == "nt" else "NOT_NATIVE_HOST_NOT_PROMOTED"
        rc = sup.EXIT_PASS
    except Exception as exc:
        receipt["result"] = "FAIL_STOP_CHAIN"
        receipt["error"] = repr(exc)[:4000]
        rc = sup.EXIT_FAIL
    finally:
        receipt["seconds"] = round(time.time() - started, 3)
        sup.write_json_new(evidence / "V008_QUALIFICATION_RECEIPT.json", receipt)
    log("V008_QUALIFICATION=" + receipt["result"])
    return rc


# =====================================================================================
# Negativos nativos Windows (G2 W04 e G3 Job) — executados SÓ em os.name == 'nt'
# =====================================================================================
_EXTERNAL_WRITE = r"""
import sys
try:
    with open(sys.argv[1], 'ab') as f:
        f.write(b'X')
    print('WRITE_SUCCEEDED')
except OSError as e:
    print('WRITE_DENIED winerror=%s' % getattr(e, 'winerror', None))
"""
_EXTERNAL_HOLD_WRITER = r"""
import sys, time
f = open(sys.argv[1], 'r+b')
print('HOLDING', flush=True)
time.sleep(float(sys.argv[2]))
"""
_EXTERNAL_HOLD_MAPPING = r"""
import sys, time, mmap
f = open(sys.argv[1], 'r+b')
m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE)
f.close()                       # handle de arquivo fechado; seção gravável continua mapeada
print('MAPPED', flush=True)
time.sleep(float(sys.argv[2]))
"""
_JOB_CHILD = r"""
import subprocess, sys, ctypes
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
kids = [subprocess.Popen([sys.executable, '-c', 'pass']) for _ in range(5)]
for k in kids: k.wait()
try:
    subprocess.Popen([sys.executable, '-c', 'pass'], creationflags=CREATE_BREAKAWAY_FROM_JOB).wait()
    print('BREAKAWAY_SUCCEEDED')
except OSError as e:
    print('BREAKAWAY_DENIED winerror=%s' % getattr(e, 'winerror', None))
"""


def _windows_native_negatives(evidence, inputs, env, case, log):
    import subprocess
    import pegasus_win_native_v008 as win
    py = sys.executable

    def ext(code, *args, wait=True):
        p = subprocess.Popen([py, "-I", "-B", "-c", code, *map(str, args)], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, env=env)
        if not wait:
            return p
        out, _ = p.communicate(timeout=120)
        return out.strip()

    def fresh(name):
        d = evidence / name
        shutil.copytree(inputs, d)
        return d, sorted(p for p in d.rglob("*") if p.is_file())[0]

    # (1) escritor externo durante a lease: negado pelo kernel; W04 continua PASS.
    d, f = fresh("Q10a_external_writer")
    lease = win.W04NativeLease(d, log); lease.arm()
    w = ext(_EXTERNAL_WRITE, f)
    ren = ext("import os,sys\ntry:\n os.replace(sys.argv[1], sys.argv[1]+'.moved'); print('RENAME_SUCCEEDED')\n"
              "except OSError as e: print('RENAME_DENIED winerror=%s' % getattr(e,'winerror',None))", f)
    v = sup.w04_verdict(native=True, **{k: v for k, v in lease.disarm(True).items()})
    case("Q10a_EXTERNAL_WRITER_AND_RENAME_DENIED_BY_LEASE",
         w.startswith("WRITE_DENIED") and ren.startswith("RENAME_DENIED") and v["w04_full"] == "PASS_NATIVE_SAME_ATTEMPT",
         writer=w, rename=ren, w04=v)

    # (2) escritor pré-existente: a lease não pode ser obtida -> BLOCKED.
    d, f = fresh("Q10b_preexisting_writer")
    holder = ext(_EXTERNAL_HOLD_WRITER, f, 20, wait=False); holder.stdout.readline()
    lease = win.W04NativeLease(d, log); lease.arm()
    v = sup.w04_verdict(native=True, **lease.disarm(True)); holder.wait(60)
    case("Q10b_PREEXISTING_WRITER_BLOCKS", v["w04_full"] == "BLOCKED"
         and any("PREEXISTING_WRITER" in g for g in v["gaps"]), w04=v)

    # (3) seção mapeada gravável pré-existente (handle já fechado) -> BLOCKED.
    d, f = fresh("Q10c_preexisting_writable_mapping")
    holder = ext(_EXTERNAL_HOLD_MAPPING, f, 20, wait=False); holder.stdout.readline()
    lease = win.W04NativeLease(d, log); lease.arm()
    v = sup.w04_verdict(native=True, **lease.disarm(True)); holder.wait(60)
    case("Q10c_PREEXISTING_WRITABLE_MAPPING_BLOCKS", v["w04_full"] == "BLOCKED", w04=v)

    # (4) novo nome, stream alternado e hardlink: detectados pelo USN -> BLOCKED.
    for label, code in (("Q10d_new_name", "open(__import__('sys').argv[1]+'.new','wb').write(b'n')"),
                        ("Q10e_alternate_stream", "open(__import__('sys').argv[1]+':evil','wb').write(b'n')"),
                        ("Q10f_hardlink", "import os,sys; os.link(sys.argv[1], sys.argv[1]+'.alias')")):
        d, f = fresh(label)
        lease = win.W04NativeLease(d, log); lease.arm()
        out = ext("import sys\ntry:\n " + code.replace("\n", "\n ") + "\n print('DONE')\n"
                  "except OSError as e: print('DENIED winerror=%s' % getattr(e,'winerror',None))", f)
        v = sup.w04_verdict(native=True, **lease.disarm(True))
        case(label.upper() + "_NEVER_PASSES", v["w04_full"] == "BLOCKED" or out.startswith("DENIED"),
             actor=out, w04=v)

    # (5) Job: netos de vida curta contados sem lacuna; breakaway negado.
    s = sup.Supervision(evidence=evidence, protected_root=inputs, out_root=evidence / "Q11_job", label="Q11_job", log=log)
    (evidence / "Q11_job").mkdir()
    r = s.run([py, "-I", "-B", "-c", _JOB_CHILD], env)
    child_log = (evidence / "Q11_job.child.log").read_text(errors="replace")
    case("Q11_JOB_GAPLESS_LINEAGE_AND_BREAKAWAY_DENIED",
         r["lineage"]["lineage"] == "GAPLESS_NATIVE_JOB" and r["lineage"]["processes"] >= 6
         and "BREAKAWAY_DENIED" in child_log and r["child_exit"] == 0,
         lineage=r["lineage"], jit=r["jit"])
