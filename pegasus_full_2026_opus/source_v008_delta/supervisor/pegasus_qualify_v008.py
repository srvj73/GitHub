"""PEGASUS FULL 2026 V008 — qualificação integrada NÃO econômica sob o supervisor.

Usa o runtime REAL do V003 (`tests/synthetic_chain.py` -> coordenador, workers, journal,
pending, checkpoint, RunLock) somente sobre fixtures SINTÉTICAS geradas por
`r1r11_fixtures.generate`. Cada execução roda sob o supervisor (W04 + custódia + SAFE_STOP +
porta de conclusão). No Windows nativo, W04/Job são reais; em outras plataformas o resultado
W04/Job é marcado como não nativo e jamais promove G2/G3.

Casos (todos no mesmo processo de qualificação, roots novos, nada é apagado):
  Q01 referência mono-worker (limpa) sob supervisão
  Q02 multi-worker: bytes econômicos == Q01 (comparação A/B determinística)
  Q03 SAFE_STOP injetado pelo supervisor após 1º commit -> parada cooperativa confirmada pela
      evidência independente (exit de interrupção por plataforma: 130 POSIX / 1|0xC000013A Windows)
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
import re
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


NATIVE_REQUIRED_CASES = (
    "Q01_REFERENCE_SUPERVISED_COMPLETED", "Q02_MULTIWORK_BYTES_EQUAL_REFERENCE",
    "Q03_SAFE_STOP_CONFIRMED_BY_SUPERVISOR", "Q04_RESUME_EXACTLY_ONCE_AFTER_SAFE_STOP",
    "Q05_GAP1_JOURNAL_WITHOUT_PENDING", "Q06_GAP2_CRASH_AFTER_COMMIT_BEFORE_CHECKPOINT",
    "Q07_TWO_GAPS_RESUME_EXACTLY_ONCE", "Q08_DUPLICATE_JOURNAL_FAIL_CLOSED",
    "Q09_EVIDENCE_GATE_REFUSES_ORPHAN_LOCK_STATE",
    "Q10a_EXTERNAL_WRITER_AND_RENAME_DENIED_BY_LEASE", "Q10b_PREEXISTING_WRITER_BLOCKS",
    "Q10c_PREEXISTING_WRITABLE_MAPPING_BLOCKS", "Q10D_NEW_NAME_NEVER_PASSES",
    "Q10E_ALTERNATE_STREAM_NEVER_PASSES", "Q10F_HARDLINK_NEVER_PASSES",
    "Q11_JOB_GAPLESS_LINEAGE_AND_BREAKAWAY_DENIED",
    "Q12_CMD_RUN_WIRED_SUPERVISED_PATH_COMPLETES", "Q12b_CMD_RUN_SAFESTOP_THEN_RESUME_EXACTLY_ONCE",
    "Q13a_DEFAULT_ADMISSION_BLOCKS_ALL_RUN_MODES", "Q13b_ECONOMIC_PLAN_REFUSED", "Q13c_ECONOMIC_ENTRY_ARGV_BLOCKED",
    "Q14_SUBPROCESS_EXIT_PROPAGATION_MATRIX_UNDER_CUSTODY", "Q15_TECHNICAL_FAILURE_CLASSIFICATION",
)

# F01: casos cuja aprovação exige W04 nativo PASS por caso (execuções supervisionadas positivas +
# o negativo Q10a que deve passar com a lease). Contagem agregada não substitui nenhum destes.
W04_NATIVE_PASS_REQUIRED = (
    "Q01_REFERENCE_SUPERVISED_COMPLETED", "Q02_MULTIWORK_BYTES_EQUAL_REFERENCE",
    "Q03_SAFE_STOP_CONFIRMED_BY_SUPERVISOR", "Q10a_EXTERNAL_WRITER_AND_RENAME_DENIED_BY_LEASE",
    "Q12_CMD_RUN_WIRED_SUPERVISED_PATH_COMPLETES",
)


def native_completeness_evaluation(receipt: dict) -> dict:
    """Critérios objetivos para as partes 3-4 do CANDIDATE_COMPLETENESS, avaliados SOBRE os
    resultados deste próprio run. Fora do Windows nativo o veredito é sempre NOT_MET."""
    by = {c.get("case"): c for c in receipt.get("cases", [])}
    unmet = []
    if not receipt.get("native_windows"):
        unmet.append("NOT_NATIVE_WINDOWS_HOST")
    if receipt.get("result") != "PASS_INTEGRATED_SUPERVISED_QUALIFICATION_SYNTHETIC":
        unmet.append("QUALIFICATION_CHAIN_NOT_PASS")
    for name in NATIVE_REQUIRED_CASES:
        if by.get(name, {}).get("result") != "PASS":
            unmet.append("CASE_NOT_PASS:" + name)
    w04_native = [c for c in receipt.get("cases", []) if isinstance(c.get("w04"), dict)
                  and c["w04"].get("w04_full") == "PASS_NATIVE_SAME_ATTEMPT"]
    lineage_native = [c for c in receipt.get("cases", []) if isinstance(c.get("lineage"), dict)
                      and c["lineage"].get("lineage") == "GAPLESS_NATIVE_JOB"]
    if receipt.get("native_windows"):
        # F01 (auditoria): exigir o predicado W04 nativo POR CASO obrigatório; contagem agregada
        # não pode compensar um caso que deveria ter W04 PASS e não teve. (A contagem segue como
        # informação, mas o gate é por caso.)
        for name in W04_NATIVE_PASS_REQUIRED:
            if by.get(name, {}).get("w04", {}).get("w04_full") != "PASS_NATIVE_SAME_ATTEMPT":
                unmet.append("W04_CASE_NOT_PASS_NATIVE:" + name)
        if len(w04_native) < 4:
            unmet.append("W04_PASS_NATIVE_SAME_ATTEMPT_COUNT<4:%d" % len(w04_native))
        if len(lineage_native) < 3:
            unmet.append("GAPLESS_NATIVE_JOB_COUNT<3:%d" % len(lineage_native))
        if "NATIVE" not in str(by.get("Q03_SAFE_STOP_CONFIRMED_BY_SUPERVISOR", {}).get("w04", {}).get("w04_full", "")):
            unmet.append("SAFE_STOP_W04_NOT_NATIVE")
    return {"schema": "PEGASUS_FULL_2026_V008R2_NATIVE_COMPLETENESS_EVALUATION",
            "required_cases": len(NATIVE_REQUIRED_CASES), "w04_native_pass_cases": len(w04_native),
            "gapless_native_job_cases": len(lineage_native), "unmet": unmet,
            "verdict": "MET" if not unmet else "NOT_MET"}


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
                                      inventory_a=sup.inventory(gap), inventory_b=sup.inventory(gap),
                                      w04={"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM"})
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
        # Q12/Q13 — caminho executável supervisionado via cmd_run + admissão (fecha a lacuna
        # estrutural). Mesma via de produção run-b/-c/-full; aqui com admissão sintética
        # isolada e não econômica, e com os negativos que mantêm o econômico fail-closed.
        _supervised_run_path_cases(evidence, inputs, env, case, log)
        if os.name == "nt":
            # R9: os negativos nativos rodam num processo NOVO (ver _native_negatives_in_fresh_process):
            # fiel à produção (cada execução supervisionada é um processo próprio) e sem o acúmulo de
            # handles do backend de census que truncava o W04 num processo de qualificação longevo.
            _native_negatives_in_fresh_process(evidence, inputs, env, case, log)
        else:
            receipt["cases"].append({"case": "Q10_W04_NATIVE_NEGATIVES", "result": "SKIPPED_NON_NATIVE",
                                     "reason": "Lease de compartilhamento/USN existem só no Windows; não promove G2."})
            receipt["cases"].append({"case": "Q11_JOB_LINEAGE_BREAKAWAY", "result": "SKIPPED_NON_NATIVE",
                                     "reason": "Job Object existe só no Windows; não promove G3."})
        # Q16 (auditoria F01) — negativo INTEGRADO: uma violação W04 tem de bloquear completion/exit,
        # chegando ao recibo. Fora do Windows o filho altera o conjunto protegido -> W04 BLOCKED ->
        # NÃO COMPLETED (exit FAIL). No Windows a lease NEGA a escrita externa -> protegido intacto ->
        # W04 PASS -> COMPLETED (o mesmo gate, provado nos dois sentidos). Não entra nos 23 casos
        # nativos (preserva o recibo R9); é regressão de integração do gate.
        _w04_blocked_integrated_negative(evidence, inputs, env, case, log)
        receipt["result"] = "PASS_INTEGRATED_SUPERVISED_QUALIFICATION_SYNTHETIC"
        receipt["w04_g2_g3_native"] = "QUALIFIED_ON_THIS_HOST" if os.name == "nt" else "NOT_NATIVE_HOST_NOT_PROMOTED"
        rc = sup.EXIT_PASS
    except Exception as exc:
        receipt["result"] = "FAIL_STOP_CHAIN"
        receipt["error"] = repr(exc)[:4000]
        rc = sup.EXIT_FAIL
    finally:
        receipt["seconds"] = round(time.time() - started, 3)
        receipt["native_completeness_evaluation"] = native_completeness_evaluation(receipt)
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
import subprocess, sys
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
kids = [subprocess.Popen([sys.executable, '-c', 'pass']) for _ in range(5)]
for k in kids: k.wait()
# Tenta escapar da custodia via CREATE_BREAKAWAY_FROM_JOB. No Win8+ (jobs aninhados) o SO pode
# NAO lancar e mesmo assim manter o neto no Job; o invariante real de custodia e a CONTENCAO
# (o neto permanece na contabilidade do Job), nao o lancamento. O neto fica vivo ~3s para o
# supervisor registrar sua pertenca (NEW_PROCESS/IOCP + sample).
try:
    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'],
                         creationflags=CREATE_BREAKAWAY_FROM_JOB)
    print('BREAKAWAY_CREATEPROCESS=OK pid=%d' % p.pid, flush=True)
    p.wait()
except OSError as e:
    print('BREAKAWAY_DENIED winerror=%s' % getattr(e, 'winerror', None), flush=True)
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
    # Contencao do breakaway: o neto NAO escapa da custodia. Vale se o SO negou o flag
    # (BREAKAWAY_DENIED) OU se, apesar de o CreateProcess nao lancar, o neto permaneceu na
    # contabilidade do Job (seu PID aparece em job_pids, registrado por NEW_PROCESS/IOCP+sample).
    # Escape real = CreateProcess OK e PID fora do Job.
    m = re.search(r"BREAKAWAY_CREATEPROCESS=OK pid=(\d+)", child_log)
    # F03 / R11-ORIGIN-02 (revisão da origem): a contenção é provada por IDENTIDADE TEMPORAL
    # (pid, creation_time), NÃO por PID histórico. job_idents vem da JobObjectBasicProcessIdList
    # resolvida pelo supervisor (process_ctime capturado enquanto o processo está vivo no Job, o que
    # mitiga reciclagem de PID). grandchild_contained exige que o PID do neto apareça com EXATAMENTE
    # UM ctime resolvido; um PID solto/ambíguo não prova contenção. O par vinculado vai ao recibo.
    job_idents = [(int(p), int(c)) for p, c in (r.get("job_idents") or [])]
    unresolved = int(r.get("lineage", {}).get("identity_unresolved_short_lived", -1))
    bound_ident = None
    if "BREAKAWAY_DENIED" in child_log:
        breakaway_contained, detail = True, "DENIED_BY_OS"
    elif m:
        gpid = int(m.group(1))
        breakaway_contained, bound_ident = sup.grandchild_contained(gpid, job_idents)
        detail = "OK_pid=%s_temporal_identity_bound=%s" % (gpid, bound_ident)
    else:
        breakaway_contained, detail = False, "NO_BREAKAWAY_MARKER"
    case("Q11_JOB_GAPLESS_LINEAGE_AND_BREAKAWAY_DENIED",
         r["lineage"]["lineage"] == "GAPLESS_NATIVE_JOB" and r["lineage"]["processes"] >= 6
         and unresolved == 0 and breakaway_contained and r["child_exit"] == 0,
         lineage=r["lineage"], jit=r["jit"], breakaway_contained=breakaway_contained, breakaway=detail,
         identity_unresolved=unresolved, grandchild_bound_identity=bound_ident, job_idents=len(job_idents))


# =====================================================================================
# R9 — negativos nativos em PROCESSO NOVO + reencenação no recibo do pai
# =====================================================================================
# Conjunto exato de casos que o modo filho DEVE produzir. Guarda de completude: um filho que
# termina cedo com JSON parcial (faltando qualquer um) é tratado como falha (fail-closed).
_NATIVE_NEGATIVE_CASES = (
    "Q10a_EXTERNAL_WRITER_AND_RENAME_DENIED_BY_LEASE", "Q10b_PREEXISTING_WRITER_BLOCKS",
    "Q10c_PREEXISTING_WRITABLE_MAPPING_BLOCKS", "Q10D_NEW_NAME_NEVER_PASSES",
    "Q10E_ALTERNATE_STREAM_NEVER_PASSES", "Q10F_HARDLINK_NEVER_PASSES",
    "Q11_JOB_GAPLESS_LINEAGE_AND_BREAKAWAY_DENIED",
)


def _replay_case_records(records, case, doc=None):
    """Reencena no recibo do PAI cada caso coletado pelo filho, preservando a semântica de
    `case` (registra e levanta na PRIMEIRA falha). Ao final — só se nenhum caso falhou —
    exige que TODOS os casos nativos esperados estejam presentes e que o filho tenha concluído.
    Assim o fail-closed sobrevive a um filho que caiu no meio ou devolveu JSON parcial."""
    for r in records:
        case(r["case"], bool(r.get("ok")), **dict(r.get("detail") or {}))
    present = {r.get("case") for r in records}
    missing = [n for n in _NATIVE_NEGATIVE_CASES if n not in present]
    if missing:
        raise sup.SupervisorBlocked("NATIVE_NEGATIVES_CASES_MISSING:" + ",".join(missing))
    if doc is not None and not doc.get("completed"):
        raise sup.SupervisorBlocked("NATIVE_NEGATIVES_CHILD_DID_NOT_COMPLETE:" + str(doc.get("error"))[:800])


def _native_negatives_in_fresh_process(evidence, inputs, env, case, log):
    """Lança os negativos nativos (Q10a–f, Q11) num SUBPROCESSO NOVO (`-I -B`) e reencena os
    resultados no recibo do pai. O filho grava NATIVE_NEGATIVES_RESULT.json; a ausência do JSON
    ou de qualquer caso esperado é falha técnica (fail-closed), nunca PASS silencioso."""
    import subprocess
    result_path = evidence / "NATIVE_NEGATIVES_RESULT.json"
    child_stdout = evidence / "NATIVE_NEGATIVES_CHILD_STDOUT.txt"
    if result_path.exists():
        raise sup.SupervisorBlocked("NATIVE_NEGATIVES_RESULT_PREEXISTS")
    cmd = [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
           "--native-negatives", str(evidence), str(inputs), str(result_path)]
    log("NATIVE_NEGATIVES_FRESH_PROCESS_SPAWN " + " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
    child_stdout.write_text((p.stdout or "") + "\n--- stderr ---\n" + (p.stderr or ""), encoding="utf-8")
    log("NATIVE_NEGATIVES_FRESH_PROCESS_EXIT rc=%s" % p.returncode)
    # Fronteira fail-closed: o filho DEVE terminar com código 0. No caminho projetado ele sempre
    # retorna 0 (até uma exceção interna vira caso negativo + completed=False, reencenado pelo pai);
    # um código não zero significa falha fora desse caminho (aborto do interpretador/SO, erro no
    # flush de saída no encerramento, etc.) e NUNCA pode ser aceito, ainda que o JSON tenha sido
    # gravado completo antes da saída. Exigido ANTES de ler/aceitar qualquer caso.
    if p.returncode != 0:
        tail = (p.stdout or "") + (p.stderr or "")
        raise sup.SupervisorBlocked("NATIVE_NEGATIVES_CHILD_NONZERO_EXIT rc=%s tail=%s" % (p.returncode, tail[-800:]))
    if not result_path.is_file():
        tail = (p.stdout or "") + (p.stderr or "")
        raise sup.SupervisorBlocked("NATIVE_NEGATIVES_CHILD_NO_RESULT rc=%s tail=%s" % (p.returncode, tail[-800:]))
    doc = json.loads(result_path.read_text(encoding="utf-8"))
    log("NATIVE_NEGATIVES_FRESH_PROCESS_REPLAY cases=%d completed=%s"
        % (len(doc.get("cases") or []), doc.get("completed")))
    _replay_case_records(doc.get("cases") or [], case, doc=doc)


def _native_negatives_child(evidence_dir, inputs_dir, result_path) -> int:
    """Modo filho (processo novo): roda SÓ os negativos nativos, COLETANDO os casos sem levantar,
    e grava o JSON de resultado. Não promove nada sozinho — o pai reencena e decide o veredito."""
    evidence = Path(evidence_dir)
    inputs = Path(inputs_dir)
    out = Path(result_path)
    log_path = evidence / "NATIVE_NEGATIVES_LOG.txt"
    records: list = []

    def log(msg: str) -> None:
        line = time.strftime("%Y-%m-%dT%H:%M:%S") + " " + msg
        print(line, flush=True)
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def collect(name, ok, **detail):
        records.append({"case": name, "ok": bool(ok), "result": "PASS" if ok else "FAIL", "detail": detail})
        log("%s=%s" % (name, "PASS" if ok else "FAIL"))

    doc = {"schema": "PEGASUS_FULL_2026_V008R9_NATIVE_NEGATIVES_CHILD_V001",
           "pid": os.getpid(), "python": sys.version.split()[0], "os_name": os.name,
           "native_windows": os.name == "nt", "cases": records}
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    try:
        _windows_native_negatives(evidence, inputs, dict(os.environ), collect, log)
        doc["completed"] = True
    except Exception as exc:  # noqa: BLE001 — qualquer falha vira caso negativo + completed=False
        doc["completed"] = False
        doc["error"] = repr(exc)[:4000]
        collect("Q10_NATIVE_NEGATIVES_CHILD_EXCEPTION", False, error=repr(exc)[:2000])
        log("NATIVE_NEGATIVES_CHILD_EXCEPTION=" + repr(exc)[:400])
    sup.write_json_new(out, doc)
    log("NATIVE_NEGATIVES_CHILD_RESULT=" + out.name + " completed=%s" % doc["completed"])
    return 0


# =====================================================================================
# Q16 (auditoria F01) — negativo integrado do gate W04 no caminho de conclusão/exit
# =====================================================================================
def _w04_blocked_integrated_negative(evidence, inputs, env, case, log):
    py = sys.executable
    prot = evidence / "Q16_protected"; prot.mkdir(parents=True, exist_ok=True)
    fx = prot / "fixture.txt"; fx.write_text("original", encoding="utf-8")
    out = evidence / "Q16_out"; out.mkdir(parents=True, exist_ok=True)
    # Filho curto que TENTA alterar o arquivo protegido e sai 0 (para isolar: o único motivo de
    # não-COMPLETED deve ser o W04, não a saída do filho).
    child = ("import sys\n"
             "p = sys.argv[1]\n"
             "try:\n"
             "    open(p, 'a', encoding='utf-8').write('MUT'); print('MUTATED_PROTECTED')\n"
             "except OSError as e:\n"
             "    print('WRITE_DENIED winerror=%s' % getattr(e, 'winerror', None))\n"
             "sys.exit(0)\n")
    s = sup.Supervision(evidence=evidence, protected_root=prot, out_root=out, label="Q16_w04_blocked", log=log)
    r = s.run([py, "-I", "-B", "-c", child, str(fx)], env, timeout_s=120)
    mutated = fx.read_text(encoding="utf-8", errors="replace") != "original"
    w04f = r.get("w04", {}).get("w04_full")
    comp = r.get("completion", {}) or {}
    if os.name == "nt":
        # A lease NEGA a escrita externa; o protegido fica intacto e o W04 passa -> COMPLETED.
        ok = (not mutated) and w04f == "PASS_NATIVE_SAME_ATTEMPT" and comp.get("completed") is True
        detail = "NATIVE_LEASE_DENIED_EXTERNAL_WRITE"
    else:
        # Sem lease: o filho altera o protegido -> W04 BLOCKED -> completion recusa (exit FAIL).
        ok = (mutated and w04f == "BLOCKED" and comp.get("completed") is False
              and any(str(g).startswith("W04_NOT_ATTESTED") for g in comp.get("gaps", []))
              and r.get("child_exit") == 0)
        detail = "NON_NATIVE_HASH_CONTINUITY_BLOCKS_COMPLETION"
    case("Q16_W04_BLOCKED_BLOCKS_COMPLETION_INTEGRATED", ok,
         platform_branch=detail, mutated=mutated, w04=r.get("w04"), completion=comp, child_exit=r.get("child_exit"))


# =====================================================================================
# Q12/Q13 — caminho executável supervisionado (run-b/-c/-full) via admissão
# =====================================================================================
def _supervised_run_path_cases(evidence, inputs, env, case, log):
    import subprocess
    admission = HERE / "tests" / "pegasus_synthetic_admission_v008.py"
    sup_py = HERE / "pegasus_supervisor_v008.py"
    py = sys.executable

    def run_cmd(cmd, extra_env, label):
        e = {**env, **extra_env}
        out = evidence / (label + ".run.log")
        p = subprocess.run([py, "-I", "-B", str(sup_py), cmd, "--admission", str(admission),
                            "--evidence", str(evidence / (label + "_EV"))],
                           capture_output=True, text=True, env=e, timeout=1800)
        out.write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
        return p

    def run_default(cmd, label):
        out = evidence / (label + ".run.log")
        p = subprocess.run([py, "-I", "-B", str(sup_py), cmd], capture_output=True, text=True,
                           env=env, timeout=300)
        out.write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
        return p

    # Q12: run-b com admissão sintética -> caminho supervisionado completo até COMPLETED.
    out12 = evidence / "Q12_out"
    p12 = run_cmd("run-b", {"PEGASUS_SYN_INPUTS": str(inputs), "PEGASUS_SYN_OUT": str(out12),
                            "PEGASUS_SYN_WORKERS": "3"}, "Q12_supervised_run")
    res12_path = evidence / "Q12_supervised_run_EV" / "SYN_SUPERVISED_SUPERVISED_RUN_RESULT.json"
    res12 = json.loads(res12_path.read_text()) if res12_path.is_file() else {}
    case("Q12_CMD_RUN_WIRED_SUPERVISED_PATH_COMPLETES",
         p12.returncode == 0 and res12.get("result") == "PASS_SUPERVISED_RUN" and res12.get("exit_code") == 0
         and res12.get("completion", {}).get("completed") is True
         # F01: W04 obrigatório no caminho integrado — não aceitar Q12 com W04 não atestado.
         and res12.get("w04", {}).get("w04_full") in ("PASS_NATIVE_SAME_ATTEMPT", "NOT_ATTESTED_NON_NATIVE_PLATFORM")
         and res12.get("jit", {}).get("jit", "").startswith("W04_ARMED_BEFORE")
         and _economic(out12) == _economic(evidence / "Q01_reference_w1"),
         returncode=p12.returncode, completion=res12.get("completion"), jit=res12.get("jit"),
         w04=res12.get("w04"), lineage=res12.get("lineage"))

    # Q12b: run-full com admissão sintética + SAFE_STOP injetado -> parada confirmada, retomada.
    out12b = evidence / "Q12b_out"
    p12b = run_cmd("run-full", {"PEGASUS_SYN_INPUTS": str(inputs), "PEGASUS_SYN_OUT": str(out12b),
                                "PEGASUS_SYN_WORKERS": "2", "PEGASUS_SYN_STOP": "1"}, "Q12b_supervised_safestop")
    res12b = json.loads((evidence / "Q12b_supervised_safestop_EV" / "SYN_SUPERVISED_SUPERVISED_RUN_RESULT.json").read_text())
    p12c = run_cmd("run-full", {"PEGASUS_SYN_INPUTS": str(inputs), "PEGASUS_SYN_OUT": str(out12b),
                                "PEGASUS_SYN_WORKERS": "3"}, "Q12c_supervised_resume")
    res12c = json.loads((evidence / "Q12c_supervised_resume_EV" / "SYN_SUPERVISED_SUPERVISED_RUN_RESULT.json").read_text())
    case("Q12b_CMD_RUN_SAFESTOP_THEN_RESUME_EXACTLY_ONCE",
         p12b.returncode == 130 and res12b.get("exit_code") == 130
         and (res12b.get("safe_stop", {}) or {}).get("safe_stop", "").startswith("CONFIRMED_BY_SUPERVISOR")
         and p12c.returncode == 0 and res12c.get("completion", {}).get("completed") is True
         and _economic(out12b) == _economic(evidence / "Q01_reference_w1"),
         safe_stop_exit=p12b.returncode, safe_stop=res12b.get("safe_stop"), resume_completion=res12c.get("completion"))

    # Q13a: admissão de produção (sem --admission) bloqueia run-b/-c/-full com causa G00.
    blocked = {}
    for cmd in ("run-b", "run-c", "run-full"):
        p = run_default(cmd, "Q13a_default_" + cmd)
        doc = json.loads(p.stdout.strip().splitlines()[-1])
        blocked[cmd] = (p.returncode, doc.get("result"), doc.get("cause", ""), doc.get("effects"))
    case("Q13a_DEFAULT_ADMISSION_BLOCKS_ALL_RUN_MODES",
         all(v[0] == 2 and v[1] == "BLOCKED" and "G00_RUN_RELEASE_DISABLED" in v[2] and v[3] == "NONE"
             for v in blocked.values()), blocked=blocked)

    # Q13b: admissão sintética que tenta marcar plano econômico -> recusa (make_run_plan).
    p13b = run_cmd("run-b", {"PEGASUS_SYN_INPUTS": str(inputs), "PEGASUS_SYN_OUT": str(evidence / "Q13b_out"),
                             "PEGASUS_SYN_TRY_ECONOMIC": "1"}, "Q13b_economic_plan_refused")
    case("Q13b_ECONOMIC_PLAN_REFUSED",
         p13b.returncode == 2 and "ECONOMIC_RUN_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION" in (p13b.stdout + p13b.stderr),
         returncode=p13b.returncode)

    # Q13c: admissão que aponta argv ao executor econômico real -> bloqueado antes de efeito.
    out13c = evidence / "Q13c_out"
    p13c = run_cmd("run-b", {"PEGASUS_SYN_INPUTS": str(inputs), "PEGASUS_SYN_OUT": str(out13c),
                             "PEGASUS_SYN_TARGET_ECONOMIC_ENTRY": "1"}, "Q13c_economic_entry_blocked")
    case("Q13c_ECONOMIC_ENTRY_ARGV_BLOCKED",
         p13c.returncode == 2
         and "ECONOMIC_RUN_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION" in (p13c.stdout + p13c.stderr)
         and not out13c.exists(),
         returncode=p13c.returncode)


    # Q14: matriz de propagação de exit por subprocesso sob a custódia (Job no Windows;
    # sessão POSIX aqui). Filhos de saída RÁPIDA — o caso que o bootstrap R1 lia como 0.
    observed = {}
    for code in (0, 1, 2, 3, 7, 19, 37, 130):
        s14 = sup.Supervision(evidence=evidence, protected_root=inputs, out_root=evidence / ("Q14_exit_%d" % code),
                              label="Q14_exit_%d" % code, log=log)
        (evidence / ("Q14_exit_%d" % code)).mkdir()
        r14 = s14.run([py, "-I", "-c", "import sys; sys.exit(%d)" % code], env, timeout_s=120)
        observed[code] = r14["child_exit"]
    case("Q14_SUBPROCESS_EXIT_PROPAGATION_MATRIX_UNDER_CUSTODY",
         all(isinstance(v, int) and v == k for k, v in observed.items()), observed=observed)

    # Q15: classificação técnica — exceção na admissão => 3 (nunca 1/0); filho falho => 3.
    p15a = run_cmd("run-b", {"PEGASUS_SYN_INPUTS": str(inputs), "PEGASUS_SYN_OUT": str(evidence / "Q15a_out"),
                             "PEGASUS_SYN_RAISE": "1"}, "Q15a_admission_exception")
    p15b = run_cmd("run-b", {"PEGASUS_SYN_INPUTS": str(inputs), "PEGASUS_SYN_OUT": str(evidence / "Q15b_out"),
                             "PEGASUS_SYN_CHILD_EXIT": "9"}, "Q15b_child_exit_9")
    r15b_path = evidence / "Q15b_child_exit_9_EV" / "SYN_CHILD_EXIT_SUPERVISED_RUN_RESULT.json"
    r15b = json.loads(r15b_path.read_text()) if r15b_path.is_file() else {}
    case("Q15_TECHNICAL_FAILURE_CLASSIFICATION",
         p15a.returncode == 3 and "FAIL_TECHNICAL" in p15a.stdout
         and p15b.returncode == 3 and r15b.get("child_exit") == 9 and r15b.get("result") == "FAIL_SUPERVISED_RUN"
         and r15b.get("exit_class") == "FAIL_TECHNICAL_AFTER_EFFECT_START",
         admission_exception_exit=p15a.returncode, child_fail_exit=p15b.returncode, child_exit=r15b.get("child_exit"))


# =====================================================================================
# Entrada de modo filho (R9). Só roda quando o arquivo é EXECUTADO como script com
# --native-negatives; como módulo importado (qualificação, testes, mutação) nada muda.
# =====================================================================================
if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "--native-negatives":
        sys.exit(_native_negatives_child(sys.argv[2], sys.argv[3], sys.argv[4]))
    sys.stderr.write("USO: python pegasus_supervisor_v008.py qualify --evidence <dir>\n")
    sys.exit(2)
