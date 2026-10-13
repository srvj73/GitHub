from __future__ import annotations

import multiprocessing as mp
import os
import signal
import time

import tickstore_full_multiwork as m


def cooperative(stop_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    while not stop_event.is_set():
        time.sleep(0.02)


def stubborn():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    time.sleep(60)


def main():
    if os.name != "nt":
        raise SystemExit("WINDOWS_ONLY")

    ctx = mp.get_context("spawn")

    # Cooperative tree: helper must leave no residual process and require no force.
    stop = ctx.Event()
    eq = ctx.Queue()
    pq = ctx.Queue()
    cqs = [ctx.Queue(), ctx.Queue()]
    workers = [ctx.Process(target=cooperative, args=(stop,)) for _ in range(2)]
    publisher = ctx.Process(target=cooperative, args=(stop,))
    for p in workers:
        p.start()
    publisher.start()

    active = {
        f"W{i+1:03d}-SYNTH": {"process": p, "command_q": cqs[i]}
        for i, p in enumerate(workers)
    }
    report = m._bounded_shutdown_process_tree(
        active, publisher, pq, eq, stop, "SMOKE",
        timeout_seconds=10.0, terminate_grace_seconds=2.0, kill_grace_seconds=2.0
    )
    if report["forced_terminate"] or report["forced_kill"]:
        raise RuntimeError("COOPERATIVE_SHUTDOWN_REQUIRED_FORCE")
    if any(p.is_alive() for p in workers) or publisher.is_alive():
        raise RuntimeError("COOPERATIVE_PROCESS_RESIDUAL")
    print("WINDOWS_RC4R2_COOPERATIVE_PROCESS_TREE_CLEAN=PASS")

    # Stubborn tree: bounded escalation must terminate it and still leave no residual.
    stop2 = ctx.Event()
    eq2 = ctx.Queue()
    pq2 = ctx.Queue()
    cq2 = ctx.Queue()
    worker = ctx.Process(target=stubborn)
    publisher2 = ctx.Process(target=cooperative, args=(stop2,))
    worker.start()
    publisher2.start()
    active2 = {"W001-STUBBORN": {"process": worker, "command_q": cq2}}
    report2 = m._bounded_shutdown_process_tree(
        active2, publisher2, pq2, eq2, stop2, "SMOKE_ESCALATE",
        timeout_seconds=0.5, terminate_grace_seconds=2.0, kill_grace_seconds=2.0
    )
    if worker.is_alive() or publisher2.is_alive():
        raise RuntimeError("ESCALATED_PROCESS_RESIDUAL")
    if "WORKER:W001-STUBBORN" not in report2["forced_terminate"]:
        raise RuntimeError("STUBBORN_WORKER_NOT_TERMINATED")
    print("WINDOWS_RC4R2_BOUNDED_ESCALATION=PASS")
    print("WINDOWS_RC4R2_NO_RESIDUAL_CHILDREN=PASS")
    print("WINDOWS_RC4R2_SAFE_STOP_PROCESS_TREE_SMOKE=PASS")
    print("REAL_CSV_READ=NO")
    print("PRODUCTION_DEST_WRITE=NO")


if __name__ == "__main__":
    main()
