"""PEGASUS FULL 2026 V008 — supervisor externo: o pai realmente executado.

Camada nova sobre o Codex V003 (payload byte-idêntico; CODE/ intocado, porque o
`verify_package()` do runtime exige que CODE/SHA256SUMS.txt liste exatamente CODE/).

O supervisor é o processo que o launcher executa. Ele:

  1. verifica a árvore inteira pelo `pegasus_entry.verify_tree` (mesmos bytes do V003);
  2. para B/C/FULL, chama `pegasus_entry.release_admission` ANTES de qualquer efeito
     (bloqueio incondicional enquanto RELEASE_STATE != RUN_RELEASED; nada aqui o promove);
  3. arma o W04 just-in-time ANTES de criar o filho (logo, antes de qualquer PREPARE dele):
     lease nativa deny-write/deny-delete sobre o conjunto protegido, diretórios sem
     DELETE-share, marco USN inicial e census de handles; mantém tudo até a árvore esvaziar;
  4. cria o filho suspenso, associa ao Job e só então retoma (Windows); acompanha a
     linhagem por (PID, creation_time) pela porta de conclusão do Job e pela contabilidade;
  5. converte Ctrl+C em SAFE_STOP cooperativo (o coordenador V003 fecha a admissão na
     fronteira de commit; o supervisor nunca mata processo) e só CONFIRMA o SAFE_STOP com
     evidência própria: exit 130, Job drenado, STATUS limpo, checkpoint válido, RUN.lock
     ausente e W04 contínuo;
  6. só declara COMPLETED (e só captura evidência) depois de exit observado, árvore vazia,
     RUN.lock ausente e dois inventários (dev, ino, bytes, sha256) idênticos — a disciplina
     que faltou na captura multi-instante que gerou o resíduo histórico PENDING/journal.

Fronteiras: G4=FROZEN, QS4=NO, FULL_ECONOMIC=NO, PHASE_C=FORBIDDEN, RESELECTION_2026=FORBIDDEN,
RUN_RELEASED=NO. O modo `qualify` usa SOMENTE fixtures sintéticas do próprio pacote.

RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CODE = ROOT / "CODE"

SCHEMA = "PEGASUS_FULL_2026_SUPERVISOR_V008"
HEARTBEAT_S = 10.0
EXIT_PASS, EXIT_BLOCKED, EXIT_FAIL, EXIT_SAFE_STOP = 0, 2, 3, 130

GATES = {"g4": "FROZEN", "qs4": "NO", "full_economic": "NO", "phase_c": "FORBIDDEN",
         "reselection_2026": "FORBIDDEN", "run_released": "NO", "full_released": "NO"}

# Bytes preservados que o supervisor importa (identidade conferida antes do uso).
PINNED_SUPERVISOR_PARENTS = {
    "native_handle_backend_v001.py": "8FEF13130C104E3EFFEABF88B25DFEFCF5851BBD6D5BBA853BB956406E49436E",
    "pegasus_qs4_stop_bridge_v006.py": "178CEBBCF81E243DB0F0CE0A2A3355749C07A86266F37929E05C567819049152",
}


class SupervisorBlocked(RuntimeError):
    """Fail-closed: nenhuma invariante não comprovada é convertida em PASS."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def write_json_new(path: Path, obj) -> str:
    """Escrita exclusiva + fsync; nunca sobrescreve evidência."""
    path = Path(path)
    data = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return hashlib.sha256(data).hexdigest().upper()


def write_json_atomic(path: Path, obj) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    data = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# =====================================================================================
# 1) NÚCLEOS DE DECISÃO PUROS (determinísticos, sem SO) — qualificáveis offline
# =====================================================================================
def w04_verdict(*, native: bool, lease: Mapping, dirs: Mapping, usn: Mapping,
                identity: Mapping, census: Mapping) -> dict:
    """Decisão W04_FULL. Só atesta com prova nativa contínua; senão NOT_ATTESTED/BLOCKED.

    Prova primária (kernel): lease deny-write/deny-delete aberta ANTES do filho e mantida
    até a árvore esvaziar. Uma abertura com compartilhamento só-leitura FALHA com
    ERROR_SHARING_VIOLATION se existir QUALQUER handle com acesso de escrita/remoção ou
    seção mapeada gravável sobre o arquivo — em qualquer processo, inclusive protegido e
    qualquer que seja o tipo reportado pelo census. Depois de aberta, nenhuma nova escrita,
    remoção ou renomeação é admitida. A prova é por arquivo (FCB), logo cobre aliases
    (hardlinks, nomes 8.3, caminhos \\\\?\\ ou subst) sem depender do nome.
    Detecção complementar (filesystem): continuidade do diário USN do início ao fim, sem
    expurgo, com ZERO registros sobre os FRN protegidos ou com pai em diretório protegido —
    cobre criação de novos nomes, streams alternados, hardlinks novos, atributos/segurança.
    Census de handles: corroboração; escritor externo RESOLVIDO sob alvo bloqueia; handles
    não resolvidos são reportados como NÃO-prova-de-ausência e ficam cobertos pela lease.
    """
    if not native:
        return {"w04_full": "NOT_ATTESTED_NON_NATIVE_PLATFORM",
                "reason": "Somente Windows nativo produz lease de compartilhamento + USN."}
    gaps: List[str] = []
    n = int(lease.get("targets", -1))
    if n <= 0:
        gaps.append("LEASE_TARGET_SET_EMPTY")
    if int(lease.get("acquired", -1)) != n:
        gaps.append("LEASE_NOT_ACQUIRED_ON_ALL_TARGETS")
    if lease.get("sharing_violations"):
        gaps.append("PREEXISTING_WRITER_OR_WRITABLE_MAPPING:%d" % len(lease["sharing_violations"]))
    if lease.get("errors"):
        gaps.append("LEASE_OPEN_ERRORS:%d" % len(lease["errors"]))
    if lease.get("held_until_tree_empty") is not True:
        gaps.append("LEASE_RELEASED_BEFORE_TREE_EMPTY")
    if lease.get("revalidation_failures"):
        gaps.append("LEASE_REVALIDATION_FAILED:%d" % len(lease["revalidation_failures"]))
    if int(dirs.get("acquired", -1)) != int(dirs.get("targets", -2)) or dirs.get("errors"):
        gaps.append("DIRECTORY_HOLD_INCOMPLETE")
    if dirs.get("held_until_tree_empty") is not True:
        gaps.append("DIRECTORY_HOLD_RELEASED_EARLY")
    if usn.get("journal_id_start") is None or usn.get("journal_id_start") != usn.get("journal_id_end"):
        gaps.append("USN_JOURNAL_IDENTITY_CHANGED_OR_ABSENT")
    if usn.get("first_usn_end") is None or usn.get("start_usn") is None or \
            int(usn["first_usn_end"]) > int(usn["start_usn"]):
        gaps.append("USN_JOURNAL_PURGED_DURING_ATTEMPT")
    if usn.get("read_complete") is not True:
        gaps.append("USN_READ_INCOMPLETE")
    if usn.get("records_on_protected"):
        gaps.append("PROTECTED_SET_MODIFIED:%d" % len(usn["records_on_protected"]))
    for k in ("reparse_points", "id_changes", "sha_mismatch", "link_count_changes"):
        if identity.get(k):
            gaps.append("IDENTITY_%s:%d" % (k.upper(), len(identity[k])))
    if census.get("truncated"):
        gaps.append("CENSUS_TRUNCATED")
    if census.get("external_writers_under_target"):
        gaps.append("CENSUS_EXTERNAL_WRITER_UNDER_TARGET:%d" % len(census["external_writers_under_target"]))
    if gaps:
        return {"w04_full": "BLOCKED", "gaps": gaps}
    return {"w04_full": "PASS_NATIVE_SAME_ATTEMPT",
            "targets": n, "directories": int(dirs["targets"]),
            "usn": {"journal_id": usn["journal_id_start"], "start_usn": usn["start_usn"],
                    "end_usn": usn.get("end_usn")},
            "census_unresolved_reported": int(census.get("unresolved", 0)),
            "census_unresolved_semantics": "NOT_ABSENCE_PROOF;COVERED_BY_KERNEL_SHARE_ACCESS_LEASE"}


def jit_verdict(marks: Sequence[Mapping]) -> dict:
    """Ordem W04_ARM -> CHILD_CREATED -> CHILD_RESUMED -> TREE_EMPTY -> W04_DISARM.

    A prova de ordem é a SEQUÊNCIA dos marcos (gravados pelo mesmo thread do supervisor,
    na ordem das operações); os timestamps monotônicos devem ser não-decrescentes. Isso não
    depende da resolução do relógio do host."""
    seen: Dict[str, int] = {}
    idx: Dict[str, int] = {}
    last = None
    for i, m in enumerate(marks):
        name, t = m.get("mark"), m.get("mono_ns")
        if not isinstance(name, str) or not isinstance(t, int):
            raise SupervisorBlocked("JIT_MARK_MALFORMED")
        if last is not None and t < last:
            raise SupervisorBlocked("JIT_MARKS_NOT_MONOTONIC")
        last = t
        if name not in seen:
            seen[name], idx[name] = t, i
    order = ("W04_ARM", "CHILD_CREATED", "CHILD_RESUMED", "TREE_EMPTY", "W04_DISARM")
    for o in order:
        if o not in seen:
            raise SupervisorBlocked("JIT_MARK_MISSING:" + o)
    if [idx[o] for o in order] != sorted(idx[o] for o in order):
        raise SupervisorBlocked("JIT_ORDER_VIOLATION")
    return {"jit": "W04_ARMED_BEFORE_CHILD_CREATION_HELD_UNTIL_TREE_EMPTY",
            **{k.lower() + "_ns": seen[k] for k in order}}


def lineage_verdict(*, native_job: bool, new_process: Sequence[Mapping],
                    accounting: Mapping, active_zero_seen: bool,
                    breakaway_allowed: bool) -> dict:
    """Linhagem sem lacunas. No Windows a pertença ao Job é garantida pelo kernel (Job
    anônimo: nenhum processo externo obtém handle de ASSIGN); a completude é provada por
    TotalProcesses == nº de identidades NEW_PROCESS distintas."""
    if breakaway_allowed:
        raise SupervisorBlocked("JOB_BREAKAWAY_ALLOWED")
    idents = {(int(p["pid"]), int(p.get("ctime") or 0)) for p in new_process}
    unresolved = sum(1 for p in new_process if not p.get("ctime"))
    if int(accounting.get("ActiveProcesses", -1)) != 0 or not active_zero_seen:
        raise SupervisorBlocked("JOB_TREE_NOT_EMPTY")
    if native_job:
        if int(accounting.get("TotalProcesses", -1)) != len(idents):
            raise SupervisorBlocked("JOB_LINEAGE_GAP total=%s observed=%d"
                                    % (accounting.get("TotalProcesses"), len(idents)))
        return {"lineage": "GAPLESS_NATIVE_JOB", "processes": len(idents),
                "identity_unresolved_short_lived": unresolved}
    return {"lineage": "OBSERVATIONAL_POSIX_SESSION_NOT_NATIVE_PROOF",
            "processes_observed": len(idents)}


def safestop_verdict(*, stop_requested: bool, child_exit: Optional[int], tree_empty: bool,
                     status: Mapping, checkpoint_valid: bool, run_lock_present: bool,
                     w04: Mapping) -> dict:
    """Confirmação INDEPENDENTE do SAFE_STOP (o filho não se autoconfirma)."""
    gaps = []
    if not stop_requested:
        gaps.append("STOP_NOT_REQUESTED")
    if child_exit != EXIT_SAFE_STOP:
        gaps.append("CHILD_EXIT_NOT_130:%s" % child_exit)
    if not tree_empty:
        gaps.append("PROCESS_TREE_NOT_DRAINED")
    if status.get("SAFE_STOP") != "YES" or status.get("PROCESS_TREE_CLEAN") != "YES":
        gaps.append("CHILD_STATUS_NOT_SAFE")
    if not checkpoint_valid:
        gaps.append("CHECKPOINT_INVALID")
    if run_lock_present:
        gaps.append("RUN_LOCK_STILL_PRESENT")
    if w04.get("w04_full") not in ("PASS_NATIVE_SAME_ATTEMPT", "NOT_ATTESTED_NON_NATIVE_PLATFORM"):
        gaps.append("W04_CONTINUITY_BROKEN")
    if gaps:
        return {"safe_stop": "NOT_CONFIRMED", "gaps": gaps}
    native = w04.get("w04_full") == "PASS_NATIVE_SAME_ATTEMPT"
    return {"safe_stop": "CONFIRMED_BY_SUPERVISOR" + ("" if native else "_NON_NATIVE_W04"),
            "committed_at_stop": status.get("COMMITTED")}


def completion_verdict(*, child_exit: Optional[int], tree_empty: bool, run_lock_present: bool,
                       inventory_a: Mapping, inventory_b: Mapping) -> dict:
    """COMPLETED só após exit 0 + árvore vazia + RUN.lock ausente + inventário estável.
    Também é a porta de captura de evidência (anti captura multi-instante)."""
    gaps = []
    if child_exit != 0:
        gaps.append("CHILD_EXIT:%s" % child_exit)
    if not tree_empty:
        gaps.append("PROCESS_TREE_NOT_EMPTY")
    if run_lock_present:
        gaps.append("RUN_LOCK_PRESENT")
    if dict(inventory_a) != dict(inventory_b):
        gaps.append("INVENTORY_UNSTABLE_BETWEEN_PASSES")
    if gaps:
        return {"completed": False, "gaps": gaps}
    return {"completed": True, "inventory_entries": len(inventory_a),
            "inventory_sha256": hashlib.sha256(json.dumps(inventory_a, sort_keys=True).encode()).hexdigest().upper()}


def eta_status(*, committed: int, total: int, started_mono: float, now_mono: float,
               initial_committed: int) -> dict:
    """Progresso só por unidades COMMITTED; ETA calculável ou UNKNOWN justificado."""
    if total < 0 or committed < 0 or committed > total:
        raise SupervisorBlocked("PROGRESS_COUNTERS_INVALID")
    delta = committed - initial_committed
    elapsed = max(now_mono - started_mono, 1e-9)
    pct = 100.0 * committed / total if total else 0.0
    if delta <= 0:
        return {"committed": committed, "total": total, "pct": pct, "eta_s": "UNKNOWN",
                "eta_reason": "NO_UNIT_COMMITTED_IN_THIS_ATTEMPT"}
    rate = delta / elapsed
    return {"committed": committed, "total": total, "pct": pct,
            "eta_s": (total - committed) / rate, "eta_reason": "COMMITTED_UNIT_MEAN",
            "rate_units_per_s": rate}


# =====================================================================================
# 2) INVENTÁRIO / EVIDÊNCIA
# =====================================================================================
def inventory(root: Path, *, include_sha: bool = True) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    root = Path(root)
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            out[rel] = {"type": "link"}
        elif p.is_dir():
            out[rel] = {"type": "dir"}
        else:
            rec = {"type": "file", "bytes": st.st_size, "dev": st.st_dev, "ino": st.st_ino}
            if include_sha:
                rec["sha256"] = sha256_file(p)
            out[rel] = rec
    return out


def checkpoint_valid(out_root: Path) -> bool:
    cp = Path(out_root) / "CHECKPOINT.json"
    if not cp.is_file():
        return False
    sys.path.insert(0, str(CODE))
    try:
        from minotauro_v004_runner import _verify_checkpoint_self
        _verify_checkpoint_self(json.loads(cp.read_text(encoding="utf-8")))
        return True
    except Exception:
        return False


# =====================================================================================
# 3) CUSTÓDIA DE PROCESSOS
# =====================================================================================
class PosixCustody:
    """Camada de teste/portabilidade: sessão própria (setsid). Observacional — NÃO é prova
    nativa de Job; serve para qualificar offline a orquestração com o runtime real."""
    native_job = False

    def __init__(self, log: Callable[[str], None]):
        self.log = log
        self.proc: Optional[subprocess.Popen] = None
        self.seen: Dict[int, int] = {}
        self.marks: List[dict] = []

    def mark(self, name: str) -> None:
        self.marks.append({"mark": name, "mono_ns": time.monotonic_ns()})

    @staticmethod
    def _stat(pid: int):
        try:
            raw = Path("/proc/%d/stat" % pid).read_text()
        except OSError:
            return None
        rest = raw[raw.rindex(")") + 2:].split()
        # campos após comm: state(3) ppid(4) pgrp(5) session(6) ... starttime(22)
        return {"pid": pid, "ppid": int(rest[1]), "sid": int(rest[3]), "start": int(rest[19])}

    def start(self, argv: Sequence[str], cwd: Path, env: Mapping, stdout_path: Path) -> int:
        fh = stdout_path.open("xb")
        self.mark("CHILD_CREATED")
        self.proc = subprocess.Popen(list(argv), cwd=str(cwd), env=dict(env), stdout=fh,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        fh.close()
        self.mark("CHILD_RESUMED")
        self.sample()
        return self.proc.pid

    def members(self) -> List[dict]:
        if self.proc is None:
            return []
        rows = []
        for d in Path("/proc").iterdir():
            if d.name.isdigit():
                st = self._stat(int(d.name))
                if st and st["sid"] == self.proc.pid:
                    rows.append(st)
        return rows

    def sample(self) -> None:
        for m in self.members():
            self.seen.setdefault(m["pid"], m["start"])

    def poll(self) -> Optional[int]:
        return None if self.proc is None else self.proc.poll()

    def request_stop(self) -> None:
        # Somente o coordenador recebe o sinal (workers V003 ignoram SIGINT).
        os.kill(self.proc.pid, signal.SIGINT)

    def tree_empty(self) -> bool:
        return not self.members()

    def accounting(self) -> dict:
        return {"TotalProcesses": len(self.seen), "ActiveProcesses": len(self.members())}

    def new_process_events(self) -> List[dict]:
        return [{"pid": p, "ctime": c} for p, c in sorted(self.seen.items())]

    def close(self) -> None:
        pass


def make_custody(log):
    if os.name == "nt":
        import pegasus_win_native_v008 as win
        return win.WindowsJobCustody(log)
    return PosixCustody(log)


# =====================================================================================
# 4) W04 (nativo no Windows; continuidade por hash nas demais plataformas)
# =====================================================================================
class W04Guard:
    def __init__(self, targets_root: Path, log):
        self.root = Path(targets_root)
        self.log = log
        self.native = os.name == "nt"
        self.impl = None
        self.baseline = None

    def arm(self) -> dict:
        if self.native:
            import pegasus_win_native_v008 as win
            self.impl = win.W04NativeLease(self.root, self.log)
            return self.impl.arm()
        self.baseline = inventory(self.root)
        return {"armed": "HASH_BASELINE_ONLY", "files": sum(1 for v in self.baseline.values() if v["type"] == "file")}

    def revalidate(self) -> None:
        if self.impl is not None:
            self.impl.revalidate()

    def disarm(self, tree_empty: bool) -> dict:
        if self.impl is not None:
            rep = self.impl.disarm(tree_empty)
            return w04_verdict(native=True, lease=rep["lease"], dirs=rep["dirs"], usn=rep["usn"],
                               identity=rep["identity"], census=rep["census"])
        after = inventory(self.root)
        same = {k: v for k, v in after.items()} == self.baseline
        v = w04_verdict(native=False, lease={}, dirs={}, usn={}, identity={}, census={})
        v["hash_continuity"] = "UNCHANGED" if same else "CHANGED"
        if not same:
            v["w04_full"] = "BLOCKED"
        return v


# =====================================================================================
# 5) EXECUÇÃO SUPERVISIONADA DE UM FILHO
# =====================================================================================
class Supervision:
    def __init__(self, *, evidence: Path, protected_root: Path, out_root: Path, label: str,
                 stop_after_committed: Optional[int] = None, log=print):
        self.evidence = Path(evidence)
        self.protected_root = Path(protected_root)
        self.out_root = Path(out_root)
        self.label = label
        self.stop_after_committed = stop_after_committed
        self.log = log
        self.stop_requested = False
        self._prev_sigint = None

    def _status(self) -> dict:
        p = self.out_root / "TELEMETRY" / "R1R11_STATUS.json"
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _on_sigint(self, *_):
        # Ctrl+C no supervisor = pedido de SAFE_STOP; nunca kill. 2º Ctrl+C: espera.
        if not self.stop_requested:
            self.log("SUPERVISOR_SAFE_STOP_REQUESTED=YES ADMISSION=CLOSED_BY_COORDINATOR NO_KILL")
        self.stop_requested = True

    def run(self, argv: Sequence[str], env: Mapping, timeout_s: Optional[float] = 900.0,
            stale_after_s: float = 120.0) -> dict:
        """`stale_after_s`: watchdog de produção — se o heartbeat do STATUS do coordenador
        (gravado a cada 10 s pelo V003) parar por mais que isso com o filho vivo, o supervisor
        pede SAFE_STOP cooperativo (uma vez) e registra; nunca termina processo.
        `timeout_s`: limite total usado só na qualificação (None em produção)."""
        cust = make_custody(self.log)
        guard = W04Guard(self.protected_root, self.log)
        arm = guard.arm()
        cust.mark("W04_ARM")
        if threading.current_thread() is threading.main_thread():
            self._prev_sigint = signal.signal(signal.SIGINT, self._on_sigint)
        stdout = self.evidence / (self.label + ".child.log")
        t0 = time.monotonic()
        pid = cust.start(argv, self.evidence, env, stdout)
        status_initial = None
        last_hb = 0.0
        rc = None
        stop_sent = False
        last_updated = None
        last_change = time.monotonic()
        try:
            while True:
                rc = cust.poll()
                cust.sample()
                now = time.monotonic()
                st = self._status()
                if status_initial is None and st:
                    status_initial = int(st.get("COMMITTED", 0))
                if st.get("updated_at") != last_updated:
                    last_updated, last_change = st.get("updated_at"), now
                elif rc is None and now - last_change > stale_after_s and not self.stop_requested:
                    self.stop_requested = True
                    self.log("WATCHDOG_STALE_HEARTBEAT seconds=%.1f ACTION=SAFE_STOP_REQUEST NO_KILL"
                             % (now - last_change))
                if (self.stop_after_committed is not None and not self.stop_requested and st
                        and int(st.get("COMMITTED", 0)) >= self.stop_after_committed and rc is None):
                    self.stop_requested = True
                    self.log("SUPERVISOR_SAFE_STOP_INJECTED after_committed=%d" % int(st["COMMITTED"]))
                if self.stop_requested and rc is None and not stop_sent:
                    # Encaminhado UMA vez ao coordenador; repetição seria o 2º Ctrl+C
                    # (V003: SECOND_CTRL_C=WAIT_NO_KILL). Nunca termina processo.
                    cust.request_stop()
                    stop_sent = True
                if now - last_hb >= HEARTBEAT_S or rc is not None:
                    guard.revalidate()
                    if st:
                        e = eta_status(committed=int(st.get("COMMITTED", 0)), total=int(st.get("TOTAL", 0)),
                                       started_mono=t0, now_mono=now,
                                       initial_committed=status_initial or 0)
                        self.log("PEGASUS_SUPERVISOR_HEARTBEAT label=%s child=%d committed=%s/%s eta_s=%s"
                                 % (self.label, pid, e["committed"], e["total"], e["eta_s"]))
                    last_hb = now
                if rc is not None:
                    break
                if timeout_s is not None and now - t0 > timeout_s:
                    raise SupervisorBlocked("QUALIFICATION_TIMEOUT_RECONCILE_REQUIRED_PID_%d" % pid)
                time.sleep(0.05)
            # Drenagem: a árvore só é considerada vazia pelo próprio custodiante.
            drain_deadline = time.monotonic() + 120
            while not cust.tree_empty():
                cust.sample()
                if time.monotonic() > drain_deadline:
                    raise SupervisorBlocked("PROCESS_TREE_NOT_DRAINED_NO_KILL")
                time.sleep(0.2)
            cust.mark("TREE_EMPTY")
            w04 = guard.disarm(tree_empty=True)
            cust.mark("W04_DISARM")
        finally:
            if self._prev_sigint is not None:
                signal.signal(signal.SIGINT, self._prev_sigint)
            cust.close()
        lineage = lineage_verdict(native_job=cust.native_job, new_process=cust.new_process_events(),
                                  accounting=cust.accounting(), active_zero_seen=cust.tree_empty(),
                                  breakaway_allowed=getattr(cust, "breakaway_allowed", False))
        jit = jit_verdict([m for m in cust.marks if m["mark"] != "W04_ARM_BEGIN"])
        run_lock = (self.out_root / "RUN.lock").exists()
        inv_a = inventory(self.out_root)
        inv_b = inventory(self.out_root)
        result = {"label": self.label, "child_pid": pid, "child_exit": rc, "w04_arm": arm,
                  "w04": w04, "jit": jit, "lineage": lineage, "run_lock_present": run_lock,
                  "status": self._status(), "stop_requested": self.stop_requested}
        if self.stop_requested:
            result["safe_stop"] = safestop_verdict(
                stop_requested=True, child_exit=rc, tree_empty=cust.tree_empty(), status=result["status"],
                checkpoint_valid=checkpoint_valid(self.out_root), run_lock_present=run_lock, w04=w04)
        else:
            result["completion"] = completion_verdict(child_exit=rc, tree_empty=cust.tree_empty(),
                                                      run_lock_present=run_lock,
                                                      inventory_a=inv_a, inventory_b=inv_b)
        return result


# =====================================================================================
# 6) COMANDOS
# =====================================================================================
def _import_entry():
    if str(CODE) not in sys.path:
        sys.path.insert(0, str(CODE))
    import pegasus_entry  # bytes V003 F77B5266…, inalterados
    return pegasus_entry


def verify_supervisor_parents() -> dict:
    out = {}
    for name, expected in PINNED_SUPERVISOR_PARENTS.items():
        got = sha256_file(HERE / name)
        if got != expected:
            raise SupervisorBlocked("SUPERVISOR_PARENT_IDENTITY_MISMATCH " + name)
        out[name] = got
    return out


def cmd_verify(_ns) -> int:
    entry = _import_entry()
    ident = entry.verify_tree(ROOT)
    parents = verify_supervisor_parents()
    print(json.dumps({"schema": SCHEMA, "result": "PASS_PACKAGE_VERIFIED", "manifest_sha256": ident,
                      "entry_sha256": sha256_file(CODE / "pegasus_entry.py"),
                      "supervisor_parents": parents, **GATES}, sort_keys=True))
    return EXIT_PASS


def cmd_run(ns) -> int:
    """Caminho FULL B/C: admissão externa SEMPRE antes de W04/Job/filho."""
    entry = _import_entry()
    entry.verify_tree(ROOT)
    verify_supervisor_parents()
    phase = "C" if ns.cmd == "run-c" else "B"
    try:
        entry.release_admission({}, phase)
    except entry.Blocked as exc:
        print(json.dumps({"schema": SCHEMA, "result": "BLOCKED", "cause": str(exc),
                          "effects": "NONE", **GATES}, sort_keys=True))
        return EXIT_BLOCKED
    # Inalcançável no artefato atual (RELEASE_STATE fixo em QUALIFICATION_ONLY_RUN_DISABLED);
    # mantido explícito para que a futura admissão revisada seja a única porta.
    raise SupervisorBlocked("RELEASE_ADMISSION_RETURNED_WITHOUT_EXTERNAL_MODULE")


def cmd_bind_qs4(ns) -> int:
    import pegasus_qs4_binding_v008 as qb
    rep = qb.binding_report(Path(ns.harness_dir), ROOT)
    print(json.dumps(rep, sort_keys=True, indent=2))
    return EXIT_PASS if rep["binding"] == "BOUND" else EXIT_BLOCKED


def cmd_qualify(ns) -> int:
    import pegasus_qualify_v008 as q
    return q.run_qualification(Path(ns.evidence), workers_ref=1, workers_multi=3)


def build_parser():
    ap = argparse.ArgumentParser(prog="pegasus_supervisor_v008")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify")
    for c in ("run-b", "run-c", "run-full"):
        sub.add_parser(c)
    b = sub.add_parser("bind-qs4")
    b.add_argument("--harness-dir", required=True)
    q = sub.add_parser("qualify")
    q.add_argument("--evidence", required=True)
    return ap


def main(argv=None) -> int:
    ns = build_parser().parse_args(argv)
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    try:
        if ns.cmd == "verify":
            return cmd_verify(ns)
        if ns.cmd in ("run-b", "run-c", "run-full"):
            return cmd_run(ns)
        if ns.cmd == "bind-qs4":
            return cmd_bind_qs4(ns)
        if ns.cmd == "qualify":
            return cmd_qualify(ns)
    except SupervisorBlocked as exc:
        print("PEGASUS_SUPERVISOR=BLOCKED " + str(exc), flush=True)
        return EXIT_BLOCKED
    except Exception as exc:
        # pegasus_entry.Blocked (verify/admissão do V003) e qualquer falha técnica: fail-closed.
        if type(exc).__name__ == "Blocked":
            print("PEGASUS_SUPERVISOR=BLOCKED " + str(exc), flush=True)
            return EXIT_BLOCKED
        raise
    return EXIT_BLOCKED


if __name__ == "__main__":
    sys.exit(main())
