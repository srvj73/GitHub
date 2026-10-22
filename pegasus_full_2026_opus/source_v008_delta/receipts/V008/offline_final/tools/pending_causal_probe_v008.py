"""PEGASUS V008 — probe causal instrumentado do caso `during_pending` (sintético, não econômico).

Fecha a lacuna registrada no V003 (`directed_instrumented_probe=NOT_EXECUTED`): reproduz,
sobre fixtures SINTÉTICAS do próprio pacote e em root novo fora dele, a mesma sequência do
`tests/qualify.py` V003 para o ponto `during_pending`

    reference_w1 (limpo)  ->  fault_during_pending (workers=2)  ->  resume (workers=3, mesmo root)

registrando TODA operação de filesystem sob o root (rename/replace, remove/unlink, rmdir,
rmtree, mkdir, open de escrita) via `sys.addaudithook`, com pid/ppid, e inventários com
(st_dev, st_ino, bytes, sha256) após cada fase. Nada é apagado pelo probe; nenhum dado real,
D: ou execução econômica é tocado. O pacote V003 é usado byte-idêntico (somente leitura).

Uso: python -I -B pending_causal_probe_v008.py --package <payload V003> --work <root novo>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import sys
import time
from pathlib import Path

TRACE_EVENTS = {"os.rename", "os.remove", "os.rmdir", "shutil.rmtree", "os.mkdir", "open"}


def _install_trace(trace_path: Path, watch_root: Path) -> None:
    import threading
    root = str(watch_root.resolve())
    trace_s = str(trace_path.resolve())
    if trace_s.startswith(root + os.sep):
        raise SystemExit("TRACE_FILE_INSIDE_WATCHED_ROOT_FORBIDDEN")
    guard = threading.local()

    def hook(event, args):
        if event not in TRACE_EVENTS or getattr(guard, "busy", False):
            return
        paths = []
        for a in args:
            if isinstance(a, (str, bytes, os.PathLike)):
                try:
                    paths.append(os.fsdecode(os.fspath(a)))
                except Exception:
                    pass
        if not any(p.startswith(root) for p in paths):
            return
        if event == "open":
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            writes = (isinstance(mode, str) and any(c in mode for c in "wxa+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            if not writes:
                return
        guard.busy = True
        try:
            rec = {"t_ns": time.monotonic_ns(), "pid": os.getpid(), "ppid": os.getppid(),
                   "event": event, "paths": [p[len(root):] or "/" for p in paths]}
            line = (json.dumps(rec, sort_keys=True) + "\n").encode()
            fd = os.open(trace_s, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)
        finally:
            guard.busy = False

    sys.addaudithook(hook)


def inventory(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        st = p.lstat()
        if p.is_file() and not p.is_symlink():
            out[rel] = {"type": "file", "bytes": st.st_size, "dev": st.st_dev, "ino": st.st_ino,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest().upper()}
        elif p.is_dir():
            out[rel] = {"type": "dir", "dev": st.st_dev, "ino": st.st_ino}
    return out


def economic(out: Path) -> dict:
    # Mesma definição do qualify.py V003 (inclui qualquer resíduo sob sessions/).
    r = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted((out / "sessions").rglob("*")) if p.is_file()}
    r["CHECKPOINT.json"] = hashlib.sha256((out / "CHECKPOINT.json").read_bytes()).hexdigest()
    return r


def run_chain(package: Path, inputs: Path, out: Path, workers: int, fault=None,
              reference=False, trace=None) -> int:
    """Executa tests/synthetic_chain.py do pacote num processo filho com o trace ativo."""
    import subprocess
    argv = [sys.executable, "-I", "-B", __file__, "--_child", "--package", str(package),
            "--inputs", str(inputs), "--out", str(out), "--workers", str(workers),
            "--trace", str(trace)]
    if fault:
        argv += ["--fault", fault]
    if reference:
        argv.append("--reference")
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    env.pop("PYTHONPATH", None)
    log = out.parent / (out.name + "." + ("fault" if fault else "run") + str(int(time.time_ns())) + ".log")
    with log.open("x") as fh:
        p = subprocess.Popen(argv, stdout=fh, stderr=subprocess.STDOUT, env=env)
        rc = p.wait(timeout=600)
    return rc, log


def child(ns) -> int:
    _install_trace(Path(ns.trace), Path(ns.out).parent)
    chain = Path(ns.package) / "tests" / "synthetic_chain.py"
    sys.argv = [str(chain), "--inputs", ns.inputs, "--out", ns.out, "--workers", str(ns.workers)]
    if ns.fault:
        sys.argv += ["--fault", ns.fault]
    if ns.reference:
        sys.argv.append("--reference")
    try:
        runpy.run_path(str(chain), run_name="__main__")
    except SystemExit as e:
        return int(e.code or 0)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--work")
    ap.add_argument("--_child", action="store_true")
    ap.add_argument("--inputs"); ap.add_argument("--out"); ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--fault"); ap.add_argument("--reference", action="store_true"); ap.add_argument("--trace")
    ns = ap.parse_args()
    if ns._child:
        return child(ns)

    package = Path(ns.package).resolve()
    work = Path(ns.work).resolve()
    if work.is_relative_to(package):
        raise SystemExit("WORK_INSIDE_PACKAGE_FORBIDDEN")
    work.mkdir(parents=True, exist_ok=False)
    trace = work.parent / (work.name + "_FS_OPERATION_TRACE.jsonl")
    sys.path.insert(0, str(package / "CODE"))
    from r1r11_fixtures import generate
    generate(work / "inputs", heavy_cycles=2)

    report = {"schema": "PEGASUS_V008_PENDING_CAUSAL_PROBE_V001", "python": sys.version.split()[0],
              "package": str(package), "economic_execution": False, "synthetic_only": True, "phases": {}}
    clean = work / "reference_w1"
    rc, log = run_chain(package, work / "inputs", clean, 1, reference=True, trace=trace)
    report["phases"]["reference_w1"] = {"rc": rc, "log": log.name}
    dest = work / "fault_during_pending"
    rc, log = run_chain(package, work / "inputs", dest, 2, fault="during_pending", trace=trace)
    report["phases"]["fault_during_pending"] = {"rc": rc, "log": log.name}
    inv_fault = inventory(dest)
    (work / "INVENTORY_AFTER_FAULT.json").write_text(json.dumps(inv_fault, indent=1, sort_keys=True))
    rc, log = run_chain(package, work / "inputs", dest, 3, trace=trace)
    report["phases"]["resume_during_pending"] = {"rc": rc, "log": log.name}
    inv_resume = inventory(dest)
    (work / "INVENTORY_AFTER_RESUME.json").write_text(json.dumps(inv_resume, indent=1, sort_keys=True))

    eq = economic(dest) == economic(clean)
    leftovers = {
        "pending_dirs": sorted(k for k in inv_resume if k.startswith("sessions/") and ".pending" in k),
        "active_journals": sorted(k for k in inv_resume if k.startswith("_commit_journal/") and inv_resume[k]["type"] == "file"),
        "run_lock_present": "RUN.lock" in inv_resume,
        "journal_history": sorted(k for k in inv_resume if k.startswith("_journal_history/")),
    }
    report.update({"economic_equal_to_clean": eq, "leftovers_after_resume": leftovers,
                   "fault_state_pending": sorted(k for k in inv_fault if ".pending" in k),
                   "fault_state_active_journals": sorted(k for k in inv_fault if k.startswith("_commit_journal/") and inv_fault[k]["type"] == "file"),
                   "fault_state_run_lock": "RUN.lock" in inv_fault})
    (work / "PROBE_RESULT.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
