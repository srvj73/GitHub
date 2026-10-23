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
# Entrega do SAFE_STOP só em JANELA SEGURA (workers confirmadamente em execução, ACTIVE>0):
# o Ctrl+C vai ao grupo do console, então entregue durante o spawn/import dos workers (ACTIVE=0,
# logo após um SESSION_COMMIT) ele MATA os workers em import e encrava o coordenador — que nunca
# LATCH-a o pedido (STATUS.STOP_REQUESTED fica False) e do qual nenhum Ctrl+C posterior recupera
# (observado na campanha nativa R5: Q03 preso em COMMITTED=1/3 ACTIVE=0). Com workers em execução
# (ACTIVE>0) eles ignoram o SIGINT (design V003) e só o coordenador reage, registrando o pedido e
# fechando a admissão no próximo SESSION_COMMIT. Reentrega (também em janela segura) cobre um sinal
# perdido; jamais termina processo. SAFE_STOP_HONOR_DEADLINE_S converte um encrave (pedido feito
# mas nunca LATCH-ado) em falha-fechada rápida e clara, em vez de pendurar até o timeout total.
SAFE_STOP_REDELIVER_S = 15.0
SAFE_STOP_MAX_DELIVERIES = 10
SAFE_STOP_HONOR_DEADLINE_S = 180.0
# R12-ORIGIN-01: numa parada controlada com a árvore AINDA viva, o custodiante permanece VIVO e
# supervisionando (W04 + Job retidos, NO_KILL, drenagem cooperativa) até TREE_EMPTY. Em produção
# (timeout_s=None) o hold não tem prazo — o custodiante vivo é a custódia durável, nunca abandona
# a árvore nem a mata. Na qualificação (bounded) este prazo limita o hold para não pendurar o teste;
# esgotado com árvore viva, é DECISÃO RESERVADA à origem (sem kill, sem soltar W04 no supervisor).
RECONCILE_HOLD_S = 300.0


def should_deliver_safe_stop(*, stop_requested: bool, child_running: bool, latched: bool,
                             active: int, require_active_window: bool, now: float, last_delivery: float,
                             deliveries: int, interval: float = SAFE_STOP_REDELIVER_S,
                             max_deliveries: int = SAFE_STOP_MAX_DELIVERIES) -> bool:
    """Decide se o supervisor deve (re)entregar o Ctrl+C cooperativo agora. Puro/testável.
    No Windows (require_active_window) só entrega com workers em execução (active>0), fora da janela
    de import/spawn, pois o Ctrl+C vai ao grupo do console; no POSIX o sinal vai só ao coordenador
    (os.kill), sem essa corrida, e o gate não se aplica. Nunca reentrega depois de LATCH-ado (o 2º
    Ctrl+C do V003 é WAIT_NO_KILL) nem após o limite."""
    if not stop_requested or not child_running or latched:
        return False
    if require_active_window and active <= 0:
        return False
    if deliveries >= max_deliveries:
        return False
    return (now - last_delivery) >= interval
EXIT_PASS, EXIT_BLOCKED, EXIT_FAIL, EXIT_SAFE_STOP = 0, 2, 3, 130

# Classificação única de exit codes do PEGASUS (supervisor, bootstrap e recibos usam a mesma).
EXIT_CLASSES = {
    EXIT_PASS: "PASS",
    EXIT_BLOCKED: "BLOCKED_FAIL_CLOSED_NO_EFFECT",
    EXIT_FAIL: "FAIL_TECHNICAL_AFTER_EFFECT_START",
    EXIT_SAFE_STOP: "SAFE_STOP_CONFIRMED_RESUMABLE",
}


def classify_exit(code) -> str:
    """Nunca converte ausência de código em sucesso: None/bool/não-int => EXIT_UNKNOWN."""
    if isinstance(code, bool) or not isinstance(code, int):
        return "EXIT_UNKNOWN_FAIL_CLOSED"
    return EXIT_CLASSES.get(code, "UNCLASSIFIED_NONZERO_FAIL" if code != 0 else "PASS")


# Código de saída de um Ctrl+C cooperativo HONRADO pelo filho — dependente de plataforma.
# POSIX: o CPython restaura o SIGINT ao default e o re-ergue, então o processo morre por
# SIGINT (128+2 = 130). Windows NÃO tem essa semântica: o CTRL_C_EVENT vira KeyboardInterrupt
# e, ao desenrolar o processo (ex.: InterruptedError no multiprocessing), sai 1; quando o
# handler de console do próprio Windows encerra o processo, sai 0xC000013A (STATUS_CONTROL_C_EXIT).
# O código de saída é apenas CORROBORAÇÃO: a confirmação do SAFE_STOP exige, além dele, a
# evidência independente (STATUS do filho SAFE_STOP=YES + árvore drenada + checkpoint válido +
# RUN.lock ausente + continuidade W04), e o Q04 prova a retomada exactly-once.
EXIT_CTRL_C_WINDOWS = 0xC000013A  # STATUS_CONTROL_C_EXIT (3221225786)


def is_cooperative_stop_exit(code) -> bool:
    if isinstance(code, bool) or not isinstance(code, int):
        return False
    if code == EXIT_SAFE_STOP:            # 130 — convenção POSIX de SIGINT
        return True
    if os.name == "nt":                   # manifestações nativas do Ctrl+C cooperativo
        return code in (1, EXIT_CTRL_C_WINDOWS)
    return False

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
    # Diagnósticos do census preservados em AMBOS os veredictos (observabilidade R9): quantas
    # tentativas cada census gastou e quantos name-workers foram abandonados (indício direto do
    # acúmulo que provoca o truncamento). Não alteram o fail-closed; só o tornam auditável.
    stats_start = census.get("stats_start") or {}
    stats_end = census.get("stats_end") or {}
    census_diag = {
        "census_attempts": census.get("attempts"),
        "census_abandoned_name_workers": [stats_start.get("abandoned_name_workers"),
                                          stats_end.get("abandoned_name_workers")],
        "census_truncated": bool(census.get("truncated")),
    }
    if gaps:
        return {"w04_full": "BLOCKED", "gaps": gaps, **census_diag}
    return {"w04_full": "PASS_NATIVE_SAME_ATTEMPT",
            "targets": n, "directories": int(dirs["targets"]),
            "usn": {"journal_id": usn["journal_id_start"], "start_usn": usn["start_usn"],
                    "end_usn": usn.get("end_usn")},
            "census_unresolved_reported": int(census.get("unresolved", 0)),
            "census_unresolved_semantics": "NOT_ABSENCE_PROOF;COVERED_BY_KERNEL_SHARE_ACCESS_LEASE",
            **census_diag}


def job_close_disposition(active_processes: int) -> str:
    """F04 (auditoria): decisão PURA de como fechar a custódia do Job, honrando NO_KILL.

    - Árvore vazia (active==0): fechar o handle é inofensivo -> CLOSE_EMPTY_SAFE.
    - Árvore AINDA viva (active>0), caso de encerramento controlado (timeout/SAFE_STOP não
      honrado): fechar o handle com KILL_ON_JOB_CLOSE mataria a árvore. NO_KILL exige limpar o
      flag antes de fechar e deixar a árvore viva para reconciliação pela próxima execução
      -> CLEAR_KILL_ON_CLOSE_LEAVE_RUNNING_NO_KILL. Reter o handle até sys.exit NÃO é garantia."""
    if int(active_processes) <= 0:
        return "CLOSE_EMPTY_SAFE"
    return "CLEAR_KILL_ON_CLOSE_LEAVE_RUNNING_NO_KILL"


def custody_finalize_decision(*, tree_empty: bool, reconcile_deadline_reached: bool, production: bool) -> str:
    """R12-ORIGIN-01 (revisão da origem): decisão PURA de finalização da custódia numa parada
    controlada, garantindo simultaneamente NO_KILL e proteção W04 durante TODA a vida da árvore.
    NUNCA retorna uma opção que mate ou que abandone a árvore viva sem proteção.

    - árvore vazia -> FINALIZE_TREE_EMPTY_SAFE (fecha com segurança; W04 foi mantida até aqui).
    - árvore viva, prazo não esgotado -> HOLD_SUPERVISE_UNTIL_TREE_EMPTY_NO_KILL (custodiante VIVO
      continua supervisionando, W04+Job retidos, drenagem cooperativa; esta é a custódia durável).
    - árvore viva, prazo esgotado, PRODUÇÃO -> HOLD_SUPERVISE_UNTIL_TREE_EMPTY_NO_KILL (produção não
      tem prazo: o custodiante permanece vivo; jamais sai com a árvore viva).
    - árvore viva, prazo esgotado, QUALIFICAÇÃO (bounded) -> RESERVED_DECISION_FAIL_CLOSED_NO_KILL
      (surge para a origem; o supervisor não mata e não solta W04 — decisão reservada)."""
    if tree_empty:
        return "FINALIZE_TREE_EMPTY_SAFE"
    if not reconcile_deadline_reached or production:
        return "HOLD_SUPERVISE_UNTIL_TREE_EMPTY_NO_KILL"
    return "RESERVED_DECISION_FAIL_CLOSED_NO_KILL"


def reconcile_step_action(*, tree_empty: bool, deadline_reached: bool, production: bool,
                          reserved_reported: bool) -> str:
    """R13-ORIGIN-01 (revisão da origem sobre R12): ação PURA por iteração do laço de reconciliação
    com custódia preservada. A custódia durável exige que o supervisor permaneça VIVO enquanto a
    árvore estiver viva — reter handles só até o encerramento do supervisor NÃO é custódia, pois no
    encerramento o `KILL_ON_JOB_CLOSE` ativo mataria a árvore e, removido, a deixaria órfã sem W04.
    Por isso esta função NUNCA retorna uma ação que mate, feche handles ou ENCERRE o supervisor com
    a árvore viva: a decisão reservada à origem é SURFACED e MANTIDA (hold com o custodiante vivo),
    jamais convertida em término/kill (não é autorização implícita para matar).

    Deriva a classificação de `custody_finalize_decision` e mapeia para a ação do laço:
    - FINALIZE_TREE_EMPTY_SAFE (árvore vazia) -> 'FINALIZE_SAFE' (ÚNICO caminho de saída do hold; só
      então fechar o Job é inofensivo).
    - RESERVED_DECISION_FAIL_CLOSED_NO_KILL, ainda não reportada -> 'REPORT_RESERVED_THEN_HOLD' (surge
      à origem UMA vez; o custodiante continua VIVO, W04+Job retidos, NO_KILL).
    - HOLD_SUPERVISE_UNTIL_TREE_EMPTY_NO_KILL, ou reservada já reportada -> 'HOLD' (segue vivo)."""
    decision = custody_finalize_decision(tree_empty=tree_empty,
                                         reconcile_deadline_reached=deadline_reached,
                                         production=production)
    if decision == "FINALIZE_TREE_EMPTY_SAFE":
        return "FINALIZE_SAFE"
    if decision == "RESERVED_DECISION_FAIL_CLOSED_NO_KILL" and not reserved_reported:
        return "REPORT_RESERVED_THEN_HOLD"
    return "HOLD"


def job_close_plan(active_processes: int, clear_kill_ok: bool) -> dict:
    """R11-ORIGIN-01: plano PURO de ações ao fechar a custódia do Job, honrando NO_KILL.

    - Árvore vazia: fechar os handles é inofensivo -> close_handles=True.
    - Árvore AINDA viva (encerramento controlado): o supervisor NUNCA fecha os handles do Job
      (fechar deixaria o KILL_ON_JOB_CLOSE disparar OU descartaria a custódia) e NUNCA mata.
      Retém os handles; a tentativa de limpar KILL_ON_JOB_CLOSE já ocorreu e seu resultado
      (`clear_kill_ok`) só classifica o risco residual no FIM DO PROCESSO (decisão reservada à
      origem), jamais faz o supervisor fechar o handle aqui. Ordem fail-closed: decidir ANTES de
      qualquer CloseHandle."""
    if int(active_processes) <= 0:
        return {"close_handles": True, "live_tree": False, "kill_risk": False, "retain_custody": False}
    return {"close_handles": False, "live_tree": True, "kill_risk": (not bool(clear_kill_ok)),
            "retain_custody": True}


def grandchild_contained(gpid: int, gctime, job_idents: Sequence) -> tuple:
    """R12-ORIGIN-02 (revisão da origem): contenção do neto provada por IDENTIDADE TEMPORAL
    INDEPENDENTE. `gctime` é o creation_time obtido pelo PRÓPRIO neto (GetProcessTimes nele mesmo),
    não derivado do PID observado. Exige que ESSE par (gpid, gctime) — a identidade que o neto
    reportou de si — esteja na observação INDEPENDENTE do Job (`job_idents`, da
    JobObjectBasicProcessIdList resolvida pelo supervisor via process_ctime), e que seja o ÚNICO
    ctime para aquele PID (sem ambiguidade de reciclagem). Duas fontes independentes concordando
    sobre (pid, creation_time) = overlap verificável de vida/pertença ao Job.

    Recusa (retorna contido=False): sem ctime independente do neto; ctime independente DIVERGENTE do
    observado; PID ausente do Job; ou PID com múltiplos ctime (reciclado/ambíguo).
    Retorna (contido, [pid, ctime] | None, motivo)."""
    if not gctime:
        return False, None, "NO_INDEPENDENT_GRANDCHILD_CTIME"
    observed = {int(c) for (p, c) in job_idents if int(p) == int(gpid) and c}
    if not observed:
        return False, None, "PID_NOT_RESOLVED_IN_JOB"
    if len(observed) > 1:
        return False, None, "AMBIGUOUS_PID_MULTIPLE_CTIME"
    if int(gctime) not in observed:
        return False, None, "INDEPENDENT_CTIME_DIVERGENT_FROM_JOB"
    return True, [int(gpid), int(gctime)], "TEMPORAL_IDENTITY_MATCH_TWO_INDEPENDENT_SOURCES"


def w04_prespawn_verdict(state: Mapping) -> dict:
    """F02 (auditoria): veredito PRÉ-SPAWN sobre a aquisição efetiva da proteção W04, antes de
    criar qualquer filho. Função pura (testável offline com doubles da API). BLOQUEIA sem spawn se
    a lease não foi obtida em todos os alvos: sharing violation (escritor/handle pré-existente),
    erro de abertura, ou ponto de reparse no conjunto protegido. Census truncado é apenas
    corroboração (tratado no disarm/subprocesso) e não bloqueia o spawn por si só."""
    gaps = []
    if state.get("sharing_violations"):
        gaps.append("PREEXISTING_WRITER_OR_SHARING_VIOLATION:%d" % len(state["sharing_violations"]))
    if state.get("open_errors"):
        gaps.append("LEASE_OPEN_ERRORS:%d" % len(state["open_errors"]))
    if state.get("reparse"):
        gaps.append("REPARSE_POINT_ON_PROTECTED:%d" % len(state["reparse"]))
    if gaps:
        return {"prespawn": "BLOCKED_NO_SPAWN", "gaps": gaps}
    return {"prespawn": "ACQUIRED_CLEAN", "files": state.get("files"), "dirs": state.get("dirs")}


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
        # F03 (auditoria): não promover identidade desconhecida. Uma identidade (pid, ctime) com
        # ctime não resolvido (None/0) não pode ser contada como vínculo temporal válido nem
        # classificar GAPLESS — falta de prova de identidade é BLOQUEIO, não "sem lacunas".
        if unresolved:
            raise SupervisorBlocked("JOB_IDENTITY_UNRESOLVED_NO_GAPLESS:%d" % unresolved)
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
    if not is_cooperative_stop_exit(child_exit):
        gaps.append("CHILD_EXIT_NOT_COOPERATIVE_STOP:%s" % child_exit)
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
                       inventory_a: Mapping, inventory_b: Mapping, w04: Mapping) -> dict:
    """COMPLETED só após exit 0 + árvore vazia + RUN.lock ausente + inventário estável + W04
    atestado. Também é a porta de captura de evidência (anti captura multi-instante).

    F01 (auditoria): a aprovação do W04 é condição OBRIGATÓRIA da conclusão. Um W04 BLOCKED
    (lease não adquirida, USN sobre o conjunto protegido, census de escritor externo, ou — fora
    do Windows — continuidade de hash CHANGED) NÃO pode ser promovido a COMPLETED/exit 0. O
    único veredito não nativo aceito é NOT_ATTESTED_NON_NATIVE_PLATFORM com o conjunto protegido
    intacto; qualquer outro valor bloqueia a conclusão."""
    gaps = []
    if child_exit != 0:
        gaps.append("CHILD_EXIT:%s" % child_exit)
    if not tree_empty:
        gaps.append("PROCESS_TREE_NOT_EMPTY")
    if run_lock_present:
        gaps.append("RUN_LOCK_PRESENT")
    if dict(inventory_a) != dict(inventory_b):
        gaps.append("INVENTORY_UNSTABLE_BETWEEN_PASSES")
    if (w04 or {}).get("w04_full") not in ("PASS_NATIVE_SAME_ATTEMPT", "NOT_ATTESTED_NON_NATIVE_PLATFORM"):
        gaps.append("W04_NOT_ATTESTED:%s" % (w04 or {}).get("w04_full"))
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
        self._closed = False

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

    def _assert_open(self) -> None:
        # Contrato espelhado do Windows (lá o handle do Job fica inválido após close): nenhuma
        # consulta ao custodiante é válida depois de close(). Faz o caminho POSIX reproduzir,
        # offline, a mesma classe de erro de ordenação que no nativo seria ERROR_INVALID_HANDLE.
        if getattr(self, "_closed", False):
            raise RuntimeError("CUSTODY_QUERIED_AFTER_CLOSE")

    def tree_empty(self) -> bool:
        self._assert_open()
        return not self.members()

    def accounting(self) -> dict:
        self._assert_open()
        return {"TotalProcesses": len(self.seen), "ActiveProcesses": len(self.members())}

    def new_process_events(self) -> List[dict]:
        self._assert_open()
        return [{"pid": p, "ctime": c} for p, c in sorted(self.seen.items())]

    def close(self) -> None:
        self._closed = True


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

    def prespawn_verdict(self) -> dict:
        # F02: fora do Windows não há lease a adquirir (só baseline de hash); nada a bloquear
        # antes do spawn. No Windows, consulta o estado de aquisição real da lease.
        if self.impl is not None:
            return w04_prespawn_verdict(self.impl.prespawn_state())
        return {"prespawn": "ACQUIRED_CLEAN"}

    def release(self) -> None:
        # Libera handles parciais quando o pré-spawn bloqueia (nenhum efeito protegido).
        if self.impl is not None and hasattr(self.impl, "release"):
            self.impl.release()

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
        # R11-ORIGIN-03 (revisão da origem): o custodiante (no Windows) já abriu Job + porta IOCP e
        # iniciou a thread de bombeamento na construção. O arm, o gate pré-spawn (F02) e o start
        # ficam DENTRO do try/finally para garantir que cust.close() rode EXATAMENTE UMA VEZ em todo
        # caminho pré-spawn falho (prespawn BLOCKED, exceção em arm ou em start), sem vazar Job/
        # IOCP/thread e sem matar processo (a árvore está vazia nesses ramos).
        try:
            guard = W04Guard(self.protected_root, self.log)
            arm = guard.arm()
            cust.mark("W04_ARM")
            # F02 (auditoria): gate PRÉ-SPAWN fail-closed. A proteção W04 tem de estar EFETIVAMENTE
            # adquirida antes de criar qualquer filho. Se a lease não foi obtida em todos os alvos
            # (sharing violation, erro de abertura, reparse no conjunto protegido), libera os handles
            # parciais e BLOQUEIA sem spawn e sem efeitos protegidos — nunca cria o filho para só
            # descobrir no disarm. Fora do Windows não há lease a adquirir (baseline de hash), então
            # o veredito pré-spawn é limpo e o caminho offline não muda.
            prespawn = guard.prespawn_verdict()
            if prespawn.get("prespawn") != "ACQUIRED_CLEAN":
                guard.release()
                raise SupervisorBlocked("W04_ARM_INCOMPLETE_NO_SPAWN_NO_PROTECTED_EFFECTS:" + ";".join(prespawn.get("gaps", [])))
            if threading.current_thread() is threading.main_thread():
                self._prev_sigint = signal.signal(signal.SIGINT, self._on_sigint)
            stdout = self.evidence / (self.label + ".child.log")
            t0 = time.monotonic()
            pid = cust.start(argv, self.evidence, env, stdout)
            status_initial = None
            last_hb = 0.0
            rc = None
            stop_deliveries = 0
            last_stop_delivery = 0.0
            stop_requested_at = None
            last_updated = None
            last_change = time.monotonic()
            reconcile_reason = None
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
                if self.stop_requested and stop_requested_at is None:
                    stop_requested_at = now
                latched = bool(st.get("STOP_REQUESTED"))
                if should_deliver_safe_stop(stop_requested=self.stop_requested, child_running=(rc is None),
                                            latched=latched, active=int(st.get("ACTIVE", 0) or 0),
                                            require_active_window=(os.name == "nt"), now=now,
                                            last_delivery=last_stop_delivery, deliveries=stop_deliveries):
                    # Entrega COOPERATIVA do SAFE_STOP SÓ com workers em execução (ACTIVE>0), fora da
                    # janela de import/spawn; reentregue (em janela segura) até o coordenador LATCH-ar
                    # (STATUS.STOP_REQUESTED=True) ou o filho sair. Nunca termina processo.
                    cust.request_stop()
                    stop_deliveries += 1
                    last_stop_delivery = now
                    self.log("SAFE_STOP_DELIVERY n=%d active=%s latched=False"
                             % (stop_deliveries, st.get("ACTIVE")))
                # Encrave: pedido feito mas o coordenador nunca LATCH-ou dentro do prazo -> falha-
                # fechada rápida e clara (não pendura até o timeout total). Só enquanto não LATCH-ado.
                if (self.stop_requested and not latched and rc is None and stop_requested_at is not None
                        and now - stop_requested_at > SAFE_STOP_HONOR_DEADLINE_S):
                    # R12-ORIGIN-01: não abandona a árvore viva. Sai do loop para a fase de
                    # reconciliação com custódia preservada (W04+Job retidos; NO_KILL; drenagem
                    # cooperativa até TREE_EMPTY). Nunca mata, nunca solta W04 com árvore viva.
                    reconcile_reason = "SAFE_STOP_NOT_HONORED_NO_LATCH"
                    break
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
                    # R12-ORIGIN-01: idem — reconciliação com custódia preservada, sem abandonar/matar.
                    reconcile_reason = "QUALIFICATION_TIMEOUT"
                    break
                time.sleep(0.05)
            # Drenagem / reconciliação com CUSTÓDIA PRESERVADA (R12-ORIGIN-01). A árvore só é vazia
            # pelo próprio custodiante. Enquanto houver árvore viva, o supervisor permanece VIVO
            # supervisionando: mantém a lease W04 (revalida), reentrega o SAFE_STOP cooperativo em
            # janela segura e NUNCA mata. W04 só é liberada (disarm) ao atingir TREE_EMPTY — logo a
            # proteção cobre TODA a vida da árvore. Em produção (timeout_s=None) o hold é sem prazo
            # (custodiante vivo = custódia durável); na qualificação, esgotado o prazo com árvore
            # viva, é decisão reservada à origem (fail-closed, sem kill, sem soltar W04).
            reconcile_deadline = time.monotonic() + RECONCILE_HOLD_S
            reserved_reported = False
            while True:
                now = time.monotonic()
                action = reconcile_step_action(tree_empty=cust.tree_empty(),
                                               deadline_reached=(now > reconcile_deadline),
                                               production=(timeout_s is None),
                                               reserved_reported=reserved_reported)
                if action == "FINALIZE_SAFE":
                    break  # ÚNICA saída do hold: árvore vazia -> fechar é inofensivo.
                cust.sample()
                st = self._status()
                latched = bool(st.get("STOP_REQUESTED"))
                if should_deliver_safe_stop(stop_requested=self.stop_requested, child_running=True,
                                            latched=latched, active=int(st.get("ACTIVE", 0) or 0),
                                            require_active_window=(os.name == "nt"), now=now,
                                            last_delivery=last_stop_delivery, deliveries=stop_deliveries):
                    cust.request_stop()
                    stop_deliveries += 1
                    last_stop_delivery = now
                guard.revalidate()  # W04 mantida durante TODA a vida da árvore; NUNCA mata/fecha handle
                if action == "REPORT_RESERVED_THEN_HOLD":
                    # R13-ORIGIN-01: a decisão reservada à origem NÃO encerra o supervisor. Com a
                    # árvore viva, levantar/retornar faria o processo terminar e seus handles fecharem
                    # -> com KILL_ON_JOB_CLOSE ativo mataria a árvore; removido, a deixaria órfã sem
                    # W04. Então o custodiante PERMANECE VIVO (W04 + Job retidos, handle do Job ABERTO
                    # => KILL_ON_JOB_CLOSE, ativo ou removido, NÃO dispara) e apenas SURGE a decisão à
                    # origem UMA vez; a saída do hold só ocorre em TREE_EMPTY (ou disposição autorizada
                    # pela origem). Nunca mata, nunca solta W04, nunca autoriza kill implícito.
                    reserved_reported = True
                    reconcile_reason = (reconcile_reason or "DRAIN") + "+RESERVED_DECISION_HELD_ALIVE_NO_KILL"
                    try:
                        write_json_atomic(self.evidence / (self.label + "_W04_NOKILL_RESERVED_DECISION.json"), {
                            "schema": "PEGASUS_FULL_2026_V008_W04_NOKILL_LIVE_TREE_RESERVED_DECISION",
                            "label": self.label, "child_pid": pid, "reconcile_reason": reconcile_reason,
                            "custodian": "ALIVE_SUPERVISING_HOLDS_W04_AND_JOB_NO_KILL",
                            "disposition": "RESERVED_FOR_ORIGIN (drenar ate TREE_EMPTY / autorizar kill / handoff de custodia)",
                            "supervisor_never": ["KILL", "CLOSE_JOB_HANDLE_ON_LIVE_TREE",
                                                 "RELEASE_W04_ON_LIVE_TREE", "SELF_TERMINATE_ON_LIVE_TREE"],
                            "kill_on_job_close_note": "handle do Job mantido ABERTO pelo custodiante vivo => KILL_ON_JOB_CLOSE (ativo ou removido) NAO dispara"})
                    except Exception:
                        pass
                    self.log("CUSTODY_RECONCILE_DEADLINE_RESERVED_DECISION_NO_KILL pid=%d: supervisor permanece VIVO "
                             "(W04+Job retidos, NO_KILL); aguarda TREE_EMPTY ou disposicao da origem" % pid)
                time.sleep(0.2)
            cust.mark("TREE_EMPTY")
            w04 = guard.disarm(tree_empty=True)
            cust.mark("W04_DISARM")
            # Evidência terminal capturada ANTES de fechar o custodiante. No Windows,
            # cust.close() fecha o handle do Job (KILL_ON_JOB_CLOSE é só o fail-safe de
            # queda do supervisor); consultá-lo depois daria ERROR_INVALID_HANDLE. Nenhuma
            # consulta ao custodiante pode ocorrer após close() — os custodiantes recusam.
            final_accounting = cust.accounting()
            final_tree_empty = int(final_accounting.get("ActiveProcesses", -1)) == 0
            new_proc_events = cust.new_process_events()
            marks_snapshot = list(cust.marks)
            native_job = cust.native_job
            breakaway_allowed = getattr(cust, "breakaway_allowed", False)
        finally:
            if self._prev_sigint is not None:
                signal.signal(signal.SIGINT, self._prev_sigint)
            # R11-ORIGIN-01/03: close() nunca mata nem fecha o handle do Job com a árvore viva
            # (ver WindowsJobCustody.close); roda exatamente uma vez em todo caminho (sucesso ou
            # falha pré-spawn/arm/start). Se a árvore ficou viva num encerramento controlado
            # (timeout/SAFE_STOP não honrado), registra a DECISÃO RESERVADA à origem: NO_KILL pelo
            # supervisor, W04 e Job retidos (não liberados/fechados), reconciliação na próxima
            # execução; a única morte possível (no fim do processo, se o flag não pôde ser limpo)
            # é falha-fechada reservada, não ação do supervisor.
            cust.close()
            if getattr(cust, "live_tree_at_close", False):
                rec = {"schema": "PEGASUS_FULL_2026_V008_W04_NOKILL_LIVE_TREE_RESERVED_DECISION",
                       "label": self.label,
                       "kill_on_job_close_cleared": getattr(cust, "kill_on_job_close_cleared", None),
                       "kill_risk_at_process_exit": getattr(cust, "close_kill_risk", None),
                       "job_handles": "RETAINED_NOT_CLOSED_ON_LIVE_TREE_NO_KILL_BY_SUPERVISOR",
                       "w04_lease": "RETAINED_UNTIL_PROCESS_EXIT_NOT_RELEASED_EARLY",
                       "reconciliation": "RESERVED_DECISION_FOR_ORIGIN (drenar / autorizar kill / handoff de custódia); orfão reconciliado por RUN.lock+journal na próxima execução",
                       "no_kill": "SUPERVISOR_PERFORMS_NO_KILL_AND_NO_HANDLE_CLOSE_ON_LIVE_TREE"}
                try:
                    write_json_atomic(self.evidence / (self.label + "_W04_NOKILL_RESERVED_DECISION.json"), rec)
                except Exception:
                    pass
                self.log("W04_NOKILL_LIVE_TREE_RESERVED_DECISION cleared=%s kill_risk=%s"
                         % (getattr(cust, "kill_on_job_close_cleared", None), getattr(cust, "close_kill_risk", None)))
        lineage = lineage_verdict(native_job=native_job, new_process=new_proc_events,
                                  accounting=final_accounting, active_zero_seen=final_tree_empty,
                                  breakaway_allowed=breakaway_allowed)
        jit = jit_verdict([m for m in marks_snapshot if m["mark"] != "W04_ARM_BEGIN"])
        run_lock = (self.out_root / "RUN.lock").exists()
        inv_a = inventory(self.out_root)
        inv_b = inventory(self.out_root)
        result = {"label": self.label, "child_pid": pid, "child_exit": rc, "w04_arm": arm,
                  "w04": w04, "jit": jit, "lineage": lineage, "run_lock_present": run_lock,
                  "job_pids": sorted({int(e["pid"]) for e in new_proc_events}),
                  # F03 (auditoria): identidades (pid, creation_time) observadas no Job, para prova
                  # de pertença/contenção por identidade temporal — não só por PID histórico.
                  "job_idents": sorted([int(e["pid"]), int(e.get("ctime") or 0)] for e in new_proc_events),
                  "status": self._status(), "stop_requested": self.stop_requested,
                  "reconcile_reason": reconcile_reason}
        if self.stop_requested:
            result["safe_stop"] = safestop_verdict(
                stop_requested=True, child_exit=rc, tree_empty=final_tree_empty, status=result["status"],
                checkpoint_valid=checkpoint_valid(self.out_root), run_lock_present=run_lock, w04=w04)
        else:
            result["completion"] = completion_verdict(child_exit=rc, tree_empty=final_tree_empty,
                                                      run_lock_present=run_lock,
                                                      inventory_a=inv_a, inventory_b=inv_b, w04=w04)
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


# =====================================================================================
# ADMISSÃO -> PLANO -> CAMINHO EXECUTÁVEL SUPERVISIONADO
# =====================================================================================
# Contrato de admissão (fecha a lacuna estrutural da V008): a porta única para QUALQUER
# execução supervisionada. Uma admissão `admit(...)` ou LEVANTA `entry.Blocked`
# (fail-closed) ou devolve um RunPlan que `_run_supervised` executa sob W04/Job/SAFE_STOP.
# Nenhum plano econômico roda sem (a) uma autorização externa comprovada que só o módulo
# revisado da origem pode emitir (ausente neste artefato) E (b) o próprio
# `pegasus_entry`/`r1r11_full_2026` liberar `release_admission` (sempre BLOCKED aqui).
RUN_PLAN_SCHEMA = "PEGASUS_FULL_2026_V008_RUN_PLAN"


def make_run_plan(*, label, argv, protected_root, out_root, economic,
                  external_authorization_proven=False, admission_schema, admission_sha256,
                  stop_after_committed=None, timeout_s=None):
    if economic and not external_authorization_proven:
        # Um plano econômico só pode existir com prova de autorização externa.
        raise SupervisorBlocked("ECONOMIC_RUN_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION")
    return {"schema": RUN_PLAN_SCHEMA, "label": str(label), "argv": [str(a) for a in argv],
            "protected_root": str(protected_root), "out_root": str(out_root),
            "economic": bool(economic), "external_authorization_proven": bool(external_authorization_proven),
            "admission_schema": admission_schema, "admission_sha256": admission_sha256,
            "stop_after_committed": stop_after_committed, "timeout_s": timeout_s}


class DefaultReleaseAdmission:
    """Admissão de produção: delega ao `release_admission` selado do V003. Nunca devolve
    plano — levanta `entry.Blocked` com a causa G00. É a admissão default de run-b/-c/-full."""
    schema = "PEGASUS_FULL_2026_V008_DEFAULT_RELEASE_ADMISSION"

    def admit(self, *, phase, package_root, entry, ns):
        entry.release_admission({}, phase)  # sempre levanta entry.Blocked neste artefato
        raise SupervisorBlocked("RELEASE_ADMISSION_RETURNED_WITHOUT_EXTERNAL_MODULE")


def _load_admission(ns):
    """Default: DefaultReleaseAdmission. `--admission <arquivo.py>` injeta um módulo de
    admissão — permitido SOMENTE para qualificação sintética isolada; um módulo injetado
    jamais pode produzir um plano econômico (make_run_plan recusa)."""
    path = getattr(ns, "admission", None)
    if not path:
        return DefaultReleaseAdmission()
    import importlib.util
    # Identidade única de módulo: quando rodando como script (__main__), registra este
    # módulo sob o nome canônico para que o `import pegasus_supervisor_v008` do módulo de
    # admissão injetado resolva PARA ESTE, evitando duas classes SupervisorBlocked/RunPlan.
    sys.modules.setdefault("pegasus_supervisor_v008", sys.modules[__name__])
    p = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("pegasus_injected_admission", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    adm = mod.ADMISSION
    adm.injected_from = str(p)
    adm.injected_sha256 = sha256_file(p)
    return adm


def _run_supervised(plan, *, evidence: Path, entry, log=print) -> int:
    """Executa o argv admitido sob supervisão plena: W04 armado antes do filho, Job com
    linhagem, SAFE_STOP cooperativo, watchdog, retomada e porta de conclusão/evidência."""
    if plan.get("schema") != RUN_PLAN_SCHEMA:
        raise SupervisorBlocked("RUN_PLAN_SCHEMA_INVALID")
    if plan["economic"]:
        if not plan.get("external_authorization_proven"):
            raise SupervisorBlocked("ECONOMIC_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION")
        # Dupla barreira: mesmo com plano econômico "autorizado", o executor econômico real
        # revalida `release_admission` por dentro; neste artefato isso bloqueia de novo.
        entry.release_admission({}, "C" if "run-c" in plan["argv"] else "B")
        raise SupervisorBlocked("ECONOMIC_EXECUTION_STILL_BLOCKED_BY_ENTRY_RELEASE_ADMISSION")
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    out_root = Path(plan["out_root"])
    s = Supervision(evidence=evidence, protected_root=Path(plan["protected_root"]), out_root=out_root,
                    label=plan["label"], stop_after_committed=plan.get("stop_after_committed"), log=log)
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    try:
        result = s.run(plan["argv"], env, timeout_s=plan.get("timeout_s"))
    except SupervisorBlocked as exc:
        # O filho já foi criado: bloqueio aqui é falha APÓS início de efeito (exit 3), com
        # recibo; o supervisor não mata processo e exige reconciliação.
        fail = {"schema": "PEGASUS_FULL_2026_V008_SUPERVISED_RUN_RESULT", "result": "FAIL_SUPERVISED_RUN",
                "cause": str(exc), "exit_code": EXIT_FAIL, "exit_class": classify_exit(EXIT_FAIL),
                "plan": {k: plan[k] for k in ("label", "economic", "admission_schema", "admission_sha256")}}
        write_json_atomic(evidence / (plan["label"] + "_SUPERVISED_RUN_RESULT.json"), fail)
        print(json.dumps({"schema": fail["schema"], "result": fail["result"], "cause": fail["cause"]}, sort_keys=True))
        return EXIT_FAIL
    result["schema"] = "PEGASUS_FULL_2026_V008_SUPERVISED_RUN_RESULT"
    result["plan"] = {k: plan[k] for k in ("label", "economic", "admission_schema", "admission_sha256")}
    completed = result.get("completion", {}).get("completed") is True
    stopped = (result.get("safe_stop", {}) or {}).get("safe_stop", "").startswith("CONFIRMED_BY_SUPERVISOR")
    # Desfecho real -> exit: concluído 0; SAFE_STOP confirmado 130 (retomável); qualquer
    # outro desfecho (filho falhou, parada não confirmada) é falha após início de efeito: 3.
    code = EXIT_PASS if completed else (EXIT_SAFE_STOP if stopped else EXIT_FAIL)
    result["exit_code"] = code
    result["exit_class"] = classify_exit(code)
    result["result"] = ("PASS_SUPERVISED_RUN" if completed else
                        "SAFE_STOP_CONFIRMED_SUPERVISED_RUN" if stopped else "FAIL_SUPERVISED_RUN")
    write_json_atomic(evidence / (plan["label"] + "_SUPERVISED_RUN_RESULT.json"), result)
    print(json.dumps({k: result[k] for k in ("schema", "result", "label", "child_exit") if k in result}
                     | {"w04_full": result.get("w04", {}).get("w04_full"),
                        "lineage": result.get("lineage", {}).get("lineage")}, sort_keys=True))
    return code


def cmd_run(ns) -> int:
    """Caminho FULL B/C/FULL: admissão (única porta) -> plano -> execução supervisionada.
    W04/Job/SAFE_STOP/retomada ficam ANTES de qualquer efeito; econômico fica fail-closed."""
    entry = _import_entry()
    entry.verify_tree(ROOT)
    verify_supervisor_parents()
    phase = "C" if ns.cmd == "run-c" else "B"
    admission = _load_admission(ns)
    try:
        plan = admission.admit(phase=phase, package_root=ROOT, entry=entry, ns=ns)
    except entry.Blocked as exc:
        print(json.dumps({"schema": SCHEMA, "result": "BLOCKED", "cause": str(exc),
                          "admission": getattr(admission, "schema", type(admission).__name__),
                          "effects": "NONE", **GATES}, sort_keys=True))
        return EXIT_BLOCKED
    # Admissão concedida: percorre o caminho executável supervisionado (fecha a lacuna).
    if getattr(ns, "evidence", None):
        evidence = Path(ns.evidence)
    else:
        evidence = Path(plan["out_root"]).parent / (plan["label"] + "_EVIDENCE")
    return _run_supervised(plan, evidence=evidence, entry=entry)


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
        rp = sub.add_parser(c)
        # Admissão default = produção (bloqueia). --admission injeta um módulo SOMENTE para
        # qualificação sintética isolada; nunca pode produzir plano econômico.
        rp.add_argument("--admission", default=None)
        rp.add_argument("--evidence", default=None)
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
        # pegasus_entry.Blocked e SupervisorBlocked (inclusive vindo de um módulo de admissão
        # injetado, com outra identidade de classe): fail-closed por nome.
        if type(exc).__name__ in ("Blocked", "SupervisorBlocked"):
            print("PEGASUS_SUPERVISOR=BLOCKED " + str(exc), flush=True)
            return EXIT_BLOCKED
        # Falha técnica não prevista: nunca sai com código não documentado (1) nem 0.
        import traceback
        traceback.print_exc()
        print("PEGASUS_SUPERVISOR=FAIL_TECHNICAL " + type(exc).__name__ + ": " + str(exc), flush=True)
        return EXIT_FAIL
    return EXIT_BLOCKED


if __name__ == "__main__":
    sys.exit(main())
