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


class PrespawnBlocked(SupervisorBlocked):
    """R15 (INT-07): bloqueio com NENHUM filho vivo (antes do spawn, ou rollback confirmado do
    próprio filho suspenso que nunca executou). Sem efeito: classificação exit 2, não 3."""
    effects = "NONE"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def write_json_new(path: Path, obj) -> str:
    """Escrita exclusiva + fsync; nunca sobrescreve evidência."""
    path = Path(path)
    data = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return hashlib.sha256(data).hexdigest().upper()


def write_json_atomic(path: Path, obj) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    data = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode("utf-8")
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
    # R15 (A02): o booleano não basta. Exige a PROVA de cobertura produzida por usn_scan_coverage,
    # coerente com os limites do próprio recibo e cobrindo até end_usn.
    cov = usn.get("coverage")
    if not isinstance(cov, Mapping):
        gaps.append("USN_COVERAGE_PROOF_ABSENT")
    else:
        if cov.get("read_complete") is not True or cov.get("reason") is not None:
            gaps.append("USN_COVERAGE_INCOMPLETE:%s" % cov.get("reason"))
        if cov.get("start_usn") != usn.get("start_usn") or cov.get("end_usn") != usn.get("end_usn"):
            gaps.append("USN_COVERAGE_BOUNDS_MISMATCH")
        try:
            short = int(cov.get("covered_to")) < int(usn.get("end_usn"))
        except (TypeError, ValueError):
            short = True
        if short:
            gaps.append("USN_COVERAGE_SHORT_OF_END")
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


USN_ERROR_HANDLE_EOF = 38
USN_ERROR_JOURNAL_ENTRY_DELETED = 1181
USN_MAX_PAGES = 1_000_000


def usn_scan_coverage(read_page: Callable, start_usn, end_usn, frns, dir_frns,
                      max_pages: int = USN_MAX_PAGES) -> dict:
    """R15 (A02): varredura PURA do diário USN de [start_usn, end_usn) com PROVA de cobertura.

    `read_page(cursor) -> (ok, winerror, raw)` devolve a página de FSCTL_READ_USN_JOURNAL a partir
    de `cursor` (8 bytes do próximo USN seguidos de registros USN_RECORD_V2/V3). A camada nativa só
    adapta DeviceIoControl; toda a decisão de completude vive aqui, testável sem Win32.

    A leitura só é completa quando a cobertura chega inequivocamente a end_usn: cursor estritamente
    progressivo em cada página, registros estruturalmente válidos (comprimento alinhado e dentro da
    página, versão suportada, nome dentro do registro, USN monotônico dentro de [cursor, próximo)),
    FRN 128 bits mapeável em 64 bits (NTFS). Qualquer outra situação — EOF antes do fim, erro de
    IOCTL, registro apagado/expurgado, página truncada, cursor parado — devolve INCOMPLETO com a
    razão; nunca levanta."""
    def result(complete, reason, cur, pages, nrec, hits):
        return {"read_complete": bool(complete), "reason": reason, "start_usn": start_usn,
                "end_usn": end_usn, "covered_to": cur, "pages": pages, "records_parsed": nrec,
                "hits": hits}

    if not isinstance(start_usn, int) or not isinstance(end_usn, int):
        return result(False, "USN_BOUNDS_ABSENT", start_usn, 0, 0, [])
    if end_usn < start_usn:
        return result(False, "USN_END_BEFORE_START", start_usn, 0, 0, [])
    frns, dir_frns = set(frns), set(dir_frns)
    cur, pages, nrec, hits = start_usn, 0, 0, []
    while cur < end_usn:
        if pages >= max_pages:
            return result(False, "USN_PAGE_LIMIT_EXCEEDED", cur, pages, nrec, hits)
        pages += 1
        try:
            ok, err, raw = read_page(cur)
        except Exception as exc:  # adaptador nativo falhou: incompleto, com causa
            return result(False, "USN_READ_EXCEPTION:%s" % type(exc).__name__, cur, pages, nrec, hits)
        if not ok:
            if err == USN_ERROR_HANDLE_EOF:
                return result(False, "USN_EOF_BEFORE_END", cur, pages, nrec, hits)
            if err == USN_ERROR_JOURNAL_ENTRY_DELETED:
                return result(False, "USN_JOURNAL_ENTRY_DELETED", cur, pages, nrec, hits)
            return result(False, "USN_READ_FAILED:%s" % err, cur, pages, nrec, hits)
        raw = bytes(raw or b"")
        if len(raw) < 8:
            return result(False, "USN_PAGE_TRUNCATED", cur, pages, nrec, hits)
        nxt = int.from_bytes(raw[:8], "little", signed=True)
        if nxt <= cur:
            return result(False, "USN_CURSOR_NOT_ADVANCING", cur, pages, nrec, hits)
        off, last, reached_end = 8, None, False
        while off < len(raw):
            if len(raw) - off < 8:
                return result(False, "USN_RECORD_TRUNCATED", cur, pages, nrec, hits)
            rl = int.from_bytes(raw[off:off + 4], "little")
            major = int.from_bytes(raw[off + 4:off + 6], "little")
            if major == 2:
                hdr = 60
            elif major == 3:
                hdr = 76
            else:
                return result(False, "USN_RECORD_VERSION_UNSUPPORTED:%d" % major, cur, pages, nrec, hits)
            if rl < hdr or rl % 8 != 0 or off + rl > len(raw):
                return result(False, "USN_RECORD_MALFORMED", cur, pages, nrec, hits)
            rec = raw[off:off + rl]
            if major == 2:
                frn = int.from_bytes(rec[8:16], "little")
                par = int.from_bytes(rec[16:24], "little")
                usn = int.from_bytes(rec[24:32], "little", signed=True)
                reason = int.from_bytes(rec[40:44], "little")
                nl, no = int.from_bytes(rec[56:58], "little"), int.from_bytes(rec[58:60], "little")
            else:
                if int.from_bytes(rec[16:24], "little") or int.from_bytes(rec[32:40], "little"):
                    return result(False, "USN_FRN128_UNMAPPABLE", cur, pages, nrec, hits)
                frn = int.from_bytes(rec[8:16], "little")
                par = int.from_bytes(rec[24:32], "little")
                usn = int.from_bytes(rec[40:48], "little", signed=True)
                reason = int.from_bytes(rec[56:60], "little")
                nl, no = int.from_bytes(rec[72:74], "little"), int.from_bytes(rec[74:76], "little")
            if no < hdr or nl % 2 or no + nl > rl:
                return result(False, "USN_RECORD_NAME_OUT_OF_BOUNDS", cur, pages, nrec, hits)
            if usn < cur or usn >= nxt or (last is not None and usn <= last):
                return result(False, "USN_RECORD_ORDER_INVALID", cur, pages, nrec, hits)
            last = usn
            nrec += 1
            if usn >= end_usn:
                reached_end = True
                break
            if frn in frns or frn in dir_frns or par in dir_frns:
                hits.append({"usn": usn, "frn": frn, "parent_frn": par, "reason": reason,
                             "name": rec[no:no + nl].decode("utf-16-le", "replace")})
            off += rl
        cur = max(nxt, end_usn) if reached_end else nxt
    return result(True, None, cur, pages, nrec, hits)


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


def tree_verified_empty(consecutive_empty: int) -> bool:
    """R15 (A01/INT-03): a árvore só é considerada vazia após DUAS observações consecutivas
    bem-sucedidas que a mostraram vazia. Observação que falha é UNKNOWN e zera a sequência —
    falha de consulta nunca autoriza TREE_EMPTY nem liberação de custódia."""
    return int(consecutive_empty) >= 2


def start_failure_disposition(*, child_created: bool, assigned: bool, resumed_threads: int) -> str:
    """R15 (INT-10): o que fazer quando a criação suspensa → Assign → Resume falha. PURO.

    - nenhum filho criado -> NO_CHILD_NO_EFFECT;
    - filho criado e NENHUMA thread retomada (Assign falhou ou Resume falhou antes da 1ª thread):
      é filho próprio que nunca executou código -> ROLLBACK_OWN_SUSPENDED_CHILD (único término
      admitido; não é kill de processo em execução nem atinge terceiros);
    - qualquer thread retomada: o filho EXECUTA -> CHILD_RUNNING_UNDER_CUSTODY (nunca terminar;
      supervisão e hold normais)."""
    if not child_created:
        return "NO_CHILD_NO_EFFECT"
    if int(resumed_threads) <= 0:
        return "ROLLBACK_OWN_SUSPENDED_CHILD"
    return "CHILD_RUNNING_UNDER_CUSTODY"


OWNER_DISPOSITION_SCHEMA = "PEGASUS_FULL_2026_V008_OWNER_CUSTODY_DISPOSITION"


def owner_disposition_verdict(doc, *, label: str, child_pid) -> dict:
    """R15 (A01/INT-19): disposição EXPLÍCITA do titular para uma árvore viva que não drena.
    Única via não automática de sair do hold sem árvore vazia. O software nunca mata: a única
    disposição de liberação deixa a árvore rodando (sem W04) e exige confirmação de rótulo e PID.
    Qualquer documento ausente/inválido equivale a WAIT."""
    if doc is None:
        return {"disposition": "WAIT", "reason": "ABSENT"}
    if not isinstance(doc, Mapping) or doc.get("schema") != OWNER_DISPOSITION_SCHEMA:
        return {"disposition": "WAIT", "reason": "INVALID_SCHEMA"}
    if doc.get("disposition") != "RELEASE_CUSTODY_LEAVE_TREE_RUNNING":
        return {"disposition": "WAIT", "reason": "UNSUPPORTED_DISPOSITION:%s" % doc.get("disposition")}
    if doc.get("ack_label") != label or _as_int(doc.get("ack_child_pid")) != _as_int(child_pid):
        return {"disposition": "WAIT", "reason": "ACK_MISMATCH"}
    if not str(doc.get("owner_statement", "")).strip():
        return {"disposition": "WAIT", "reason": "OWNER_STATEMENT_ABSENT"}
    return {"disposition": "RELEASE", "reason": "OWNER_EXPLICIT_RELEASE"}


def owner_release_plan(*, kill_on_close_cleared: bool) -> dict:
    """R15: liberação autorizada pelo titular só fecha os handles do Job se KILL_ON_JOB_CLOSE foi
    removido ANTES — fechar com o flag ativo mataria a árvore. Flag não removível => recusa e o
    hold continua (NO_KILL acima da disposição)."""
    if kill_on_close_cleared is True:
        return {"release": True, "close_job_handles": True, "kill_risk": False}
    return {"release": False, "close_job_handles": False, "kill_risk": True,
            "reason": "KILL_ON_JOB_CLOSE_NOT_CLEARABLE_RELEASE_REFUSED_HOLD_CONTINUES"}


def start_failure_effect_class(*, child_created: bool, assigned: bool, resumed_threads,
                               child_alive, rollback_confirmed: bool) -> str:
    """R16 (N1): classifica, por FATOS de criação/atribuição/retomada/rollback/incerteza, se uma
    falha de `start` pôde ou não produzir efeitos. PURA.

    Um filho que retomou >= 1 thread EXECUTOU código: efeitos são possíveis mesmo que esteja morto
    na consulta posterior (saída rápida). 'Sem efeito' só é declarável quando PROVADO:
      - nenhum filho foi criado; OU
      - um filho suspenso foi criado, NENHUMA thread foi retomada, o rollback do próprio suspenso
        foi confirmado e ele não está vivo.
    Qualquer outra combinação (retomada >=1, vivo, ou estado incerto sem rollback confirmado)
    conta como efeito possível/incerto e NUNCA pode sair como bloqueio pré-spawn sem efeito."""
    if not child_created:
        return "NO_EFFECT_NO_CHILD"
    if int(resumed_threads or 0) >= 1:
        return "EFFECTS_POSSIBLE_CHILD_EXECUTED"
    if child_alive is True:
        return "CHILD_ALIVE_NO_RESUME_SUPERVISE"
    if child_alive is False and rollback_confirmed is True:
        return "NO_EFFECT_SUSPENDED_ROLLED_BACK"
    return "EFFECTS_UNCERTAIN_FAIL_CLOSED"


def start_failure_is_no_effect(klass: str) -> bool:
    """O bloqueio pré-spawn SEM efeito (exit 2) só é admitido para classes provadamente sem efeito."""
    return str(klass).startswith("NO_EFFECT")


def custody_close_confirmed(close_result, *, tree_verified_empty: bool) -> bool:
    """R16 (N2): o fechamento do custodiante só é CONFIRMADO quando o adaptador PROVA o fechamento
    (`closed is True`), a contabilidade final não mostra processos ativos (`active_processes == 0`)
    e a árvore foi verificada vazia. Retorno None/ausente, `closed` != True, ou qualquer processo
    ativo NÃO são prova de fechamento — exigem hold observável com Job + W04 retidos (NO_KILL)."""
    if not isinstance(close_result, Mapping):
        return False
    if close_result.get("closed") is not True:
        return False
    if _as_int(close_result.get("active_processes")) != 0:
        return False
    return bool(tree_verified_empty)


def supervised_final_outcome(*, completed: bool, stopped: bool, receipt_persisted: bool) -> dict:
    """R16 (N3): desfecho ÚNICO e coerente de `_run_supervised`. A ausência do recibo canônico
    (evidência faltante) NUNCA é sucesso, qualquer que seja completed/stopped. `result`, `exit_code`
    e `exit_class` derivam todos desta decisão; o banner humano e a fase usam os MESMOS campos."""
    if not receipt_persisted:
        return {"exit_code": EXIT_FAIL, "result": "FAIL_SUPERVISED_RUN_RECEIPT_NOT_PERSISTED",
                "exit_class": classify_exit(EXIT_FAIL)}
    if completed:
        return {"exit_code": EXIT_PASS, "result": "PASS_SUPERVISED_RUN", "exit_class": classify_exit(EXIT_PASS)}
    if stopped:
        return {"exit_code": EXIT_SAFE_STOP, "result": "SAFE_STOP_CONFIRMED_SUPERVISED_RUN",
                "exit_class": classify_exit(EXIT_SAFE_STOP)}
    return {"exit_code": EXIT_FAIL, "result": "FAIL_SUPERVISED_RUN", "exit_class": classify_exit(EXIT_FAIL)}


def terminal_for_prespawn_block(receipt_persisted: bool) -> dict:
    """I-02 (R17): verdade terminal ÚNICA do ramo pré-spawn. BLOCKED/exit 2 (sem efeito) só é
    desfecho legítimo quando o recibo CANÔNICO foi persistido. Sem o canônico (persist_run_receipt
    caiu no fallback FAIL/exit 3), o desfecho terminal passa a FAIL/exit 3 — coerente com o recibo
    realmente gravado, nunca BLOCKED/exit 2 sobre um fallback FAIL. result/exit_code/exit_class/
    banner derivam todos DESTA decisão."""
    if receipt_persisted:
        return {"exit_code": EXIT_BLOCKED, "result": "BLOCKED_PRESPAWN_NO_EFFECT",
                "exit_class": classify_exit(EXIT_BLOCKED), "effects_started": False}
    return {"exit_code": EXIT_FAIL, "result": "FAIL_PRESPAWN_RECEIPT_NOT_PERSISTED",
            "exit_class": classify_exit(EXIT_FAIL), "effects_started": False}


def terminal_for_post_spawn_fail(receipt_persisted: bool, *, effects_started: bool) -> dict:
    """I-02 (R17): verdade terminal ÚNICA do ramo de falha técnica APÓS o spawn. Sempre FAIL/exit 3
    (há/pode haver efeito), persistido o canônico ou degradado ao fallback — o recibo ausente nunca
    vira sucesso nem bloqueio sem efeito."""
    result = "FAIL_TECHNICAL_SUPERVISION" if receipt_persisted else "FAIL_TECHNICAL_RECEIPT_NOT_PERSISTED"
    return {"exit_code": EXIT_FAIL, "result": result, "exit_class": classify_exit(EXIT_FAIL),
            "effects_started": bool(effects_started)}


def _emit_summary(obj) -> None:
    """I-02 (R17): emissão do resumo terminal à prova de falha — nunca altera o desfecho (exit_code
    já decidido) nem derruba o processo. Vale para TODOS os ramos (pré-spawn, pós-spawn, sucesso)."""
    try:
        print(json.dumps(obj, sort_keys=True, default=str))
    except Exception as exc:
        try:
            sys.stderr.write("PEGASUS_SUPERVISOR_SUMMARY_EMIT_FAILED %s exit_code=%s\n"
                             % (type(exc).__name__, obj.get("exit_code") if isinstance(obj, Mapping) else "?"))
        except Exception:
            pass


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


STATUS_SCHEMA_V003 = "MINOTAURO_R1R11_RUNTIME_STATUS_V001"
STATUS_REQUIRED_V003 = ("schema", "PHASE", "COMMITTED", "TOTAL", "PCT", "RATE", "ETA", "FINISH",
                        "ACTIVE", "READY_WAITING", "CHECKPOINT", "SAFE_STOP", "PROCESS_TREE_CLEAN",
                        "run_instance", "out_root", "mode", "updated_at")


def _as_int(value, default=None):
    """Inteiro estrito para campos de telemetria: bool/str/None/float não são aceitos."""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def terminal_evidence_verdict(*, mode: str, status: Mapping, status_state: str, pre_run_instance,
                              supervised_pids, expected_out_root, checkpoint_ok: bool,
                              checkpoint_completed) -> dict:
    """R15 (A03/INT-14): evidência terminal do filho VINCULADA a esta tentativa.

    Contrato V003 (r1r11_runtime_status / coordenador): STATUS com esquema e campos obrigatórios,
    `run_instance = "<pid>_<ns>"` do processo dono do RunLock, `PROCESS_TREE_CLEAN=YES` e `ACTIVE=0`
    gravados por `close()`; na conclusão `COMMITTED == TOTAL > 0`; no SAFE_STOP `SAFE_STOP=YES`; e
    `CHECKPOINT.json` autoverificável com o mesmo nº de sessões. O vínculo à tentativa exige
    `run_instance` diferente do existente antes do spawn e PID produtor dentro da árvore
    supervisionada — STATUS de execução anterior (raiz reutilizada) ou de outro processo não conta.
    mode: "COMPLETION" | "SAFE_STOP"."""
    gaps = []
    st = status if isinstance(status, Mapping) else {}
    if status_state != "OK":
        gaps.append("STATUS_" + str(status_state))
    if st.get("schema") != STATUS_SCHEMA_V003:
        gaps.append("STATUS_SCHEMA_INVALID")
    missing = [k for k in STATUS_REQUIRED_V003 if k not in st]
    if missing:
        gaps.append("STATUS_FIELDS_MISSING:%d" % len(missing))
    try:
        same_root = Path(str(st.get("out_root"))).resolve() == Path(expected_out_root).resolve()
    except Exception:
        same_root = False
    if not same_root:
        gaps.append("STATUS_OUT_ROOT_MISMATCH")
    inst = st.get("run_instance")
    producer = None
    if isinstance(inst, str) and "_" in inst:
        producer = _as_int(int(inst.split("_", 1)[0]) if inst.split("_", 1)[0].isdigit() else None)
    if not isinstance(inst, str) or producer is None:
        gaps.append("STATUS_RUN_INSTANCE_INVALID")
    elif pre_run_instance is not None and inst == pre_run_instance:
        gaps.append("STATUS_NOT_FRESH_FOR_THIS_ATTEMPT")
    if producer is not None and producer not in {int(p) for p in (supervised_pids or [])}:
        gaps.append("STATUS_PRODUCER_NOT_IN_SUPERVISED_TREE")
    if st.get("PROCESS_TREE_CLEAN") != "YES":
        gaps.append("STATUS_PROCESS_TREE_NOT_CLEAN")
    if _as_int(st.get("ACTIVE")) != 0:
        gaps.append("STATUS_ACTIVE_NONZERO")
    committed, total = _as_int(st.get("COMMITTED")), _as_int(st.get("TOTAL"))
    if not checkpoint_ok:
        gaps.append("CHECKPOINT_INVALID")
    elif committed is None or _as_int(checkpoint_completed) != committed:
        gaps.append("CHECKPOINT_COMMITTED_MISMATCH")
    if mode == "COMPLETION":
        if total is None or total <= 0 or committed != total:
            gaps.append("STATUS_NOT_FULLY_COMMITTED")
        if st.get("SAFE_STOP") == "YES" or st.get("STOP_REQUESTED") is True:
            gaps.append("STATUS_STOPPED_NOT_COMPLETED")
    elif mode == "SAFE_STOP":
        if st.get("SAFE_STOP") != "YES":
            gaps.append("STATUS_NOT_SAFE_STOP")
    else:
        gaps.append("TERMINAL_MODE_INVALID")
    return {"terminal": "COMPLETE" if not gaps else "INCOMPLETE", "mode": mode, "gaps": gaps,
            "run_instance": inst, "producer_pid": producer, "committed": committed, "total": total}


def safestop_verdict(*, stop_requested: bool, child_exit: Optional[int], tree_empty: bool,
                     status: Mapping, checkpoint_valid: bool, run_lock_present: bool,
                     w04: Mapping, terminal: Optional[Mapping] = None, lineage: Optional[Mapping] = None,
                     jit: Optional[Mapping] = None) -> dict:
    """Confirmação INDEPENDENTE do SAFE_STOP (o filho não se autoconfirma). R15: exige também a
    evidência terminal vinculada a esta tentativa (`terminal_evidence_verdict(mode="SAFE_STOP")`)
    e linhagem/JIT provados, como a conclusão."""
    gaps = []
    if (terminal or {}).get("terminal") != "COMPLETE" or (terminal or {}).get("mode") != "SAFE_STOP":
        gaps.append("TERMINAL_EVIDENCE_NOT_PROVEN:%s" % ",".join((terminal or {}).get("gaps", ["ABSENT"])))
    lin = (lineage or {}).get("lineage")
    native_w04 = (w04 or {}).get("w04_full") == "PASS_NATIVE_SAME_ATTEMPT"
    if lin != "GAPLESS_NATIVE_JOB" and (native_w04 or lin != "OBSERVATIONAL_POSIX_SESSION_NOT_NATIVE_PROOF"):
        gaps.append("LINEAGE_NOT_PROVEN:%s" % (lineage or {}).get("cause", lin))
    if not str((jit or {}).get("jit", "")).startswith("W04_ARMED_BEFORE_CHILD_CREATION"):
        gaps.append("JIT_ORDER_NOT_PROVEN:%s" % (jit or {}).get("cause"))
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
                       inventory_a: Mapping, inventory_b: Mapping, w04: Mapping,
                       terminal: Optional[Mapping] = None, lineage: Optional[Mapping] = None,
                       jit: Optional[Mapping] = None) -> dict:
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
    # R15 (A03): conclusão exige a evidência terminal do filho vinculada a esta tentativa.
    if (terminal or {}).get("terminal") != "COMPLETE" or (terminal or {}).get("mode") != "COMPLETION":
        gaps.append("TERMINAL_EVIDENCE_NOT_PROVEN:%s" % ",".join((terminal or {}).get("gaps", ["ABSENT"])))
    # R15 (INT-06/INT-18): linhagem e ordem JIT são dados obrigatórios, não exceções laterais.
    lin = (lineage or {}).get("lineage")
    native_w04 = (w04 or {}).get("w04_full") == "PASS_NATIVE_SAME_ATTEMPT"
    if lin != "GAPLESS_NATIVE_JOB" and (native_w04 or lin != "OBSERVATIONAL_POSIX_SESSION_NOT_NATIVE_PROOF"):
        gaps.append("LINEAGE_NOT_PROVEN:%s" % (lineage or {}).get("cause", lin))
    if not str((jit or {}).get("jit", "")).startswith("W04_ARMED_BEFORE_CHILD_CREATION"):
        gaps.append("JIT_ORDER_NOT_PROVEN:%s" % (jit or {}).get("cause"))
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


def checkpoint_evidence(out_root: Path) -> dict:
    """CHECKPOINT.json autoverificável (verificador do próprio V003) e nº de sessões concluídas.
    R15 (INT-16): `CODE/` entra em sys.path uma única vez."""
    cp = Path(out_root) / "CHECKPOINT.json"
    if not cp.is_file():
        return {"valid": False, "completed": None, "reason": "ABSENT"}
    if str(CODE) not in sys.path:
        sys.path.insert(0, str(CODE))
    try:
        doc = json.loads(cp.read_text(encoding="utf-8"))
        from minotauro_v004_runner import _verify_checkpoint_self
        _verify_checkpoint_self(doc)
    except Exception as exc:
        return {"valid": False, "completed": None, "reason": "INVALID:%s" % type(exc).__name__}
    comp = doc.get("completed") if isinstance(doc, dict) else None
    return {"valid": True, "completed": len(comp) if isinstance(comp, list) else None, "reason": None}


def checkpoint_valid(out_root: Path) -> bool:
    return checkpoint_evidence(out_root)["valid"]


# =====================================================================================
# 3) CUSTÓDIA DE PROCESSOS
# =====================================================================================
class PosixCustody:
    """Camada de teste/portabilidade: sessão própria (setsid). Observacional — NÃO é prova
    nativa de Job; serve para qualificar offline a orquestração com o runtime real. Mesma
    interface de custódia da camada Windows (R15): observe_tree tri-estado, request_stop
    estruturado, child_state e liberação explícita pelo titular."""
    native_job = False

    def __init__(self, log: Callable[[str], None]):
        self.log = log
        self.proc: Optional[subprocess.Popen] = None
        self.seen: Dict[int, int] = {}
        self.marks: List[dict] = []
        self._closed = False
        self.child_created = False
        self.resumed_threads = 0
        self.released_by_owner = False

    def mark(self, name: str) -> None:
        self.marks.append({"mark": name, "mono_ns": time.monotonic_ns()})

    @staticmethod
    def _stat(pid: int):
        try:
            raw = Path("/proc/%d/stat" % pid).read_text()
            rest = raw[raw.rindex(")") + 2:].split()
            # campos após comm: state(3) ppid(4) pgrp(5) session(6) ... starttime(22)
            return {"pid": pid, "ppid": int(rest[1]), "sid": int(rest[3]), "start": int(rest[19])}
        except (OSError, ValueError, IndexError):
            return None

    def start(self, argv: Sequence[str], cwd: Path, env: Mapping, stdout_path: Path) -> int:
        # R15 (INT-17): marco CHILD_CREATED só após o Popen ter sucesso; handle de stdout sempre fechado.
        fh = stdout_path.open("xb")
        try:
            self.proc = subprocess.Popen(list(argv), cwd=str(cwd), env=dict(env), stdout=fh,
                                         stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            fh.close()
        self.child_created = True
        self.resumed_threads = 1
        self.mark("CHILD_CREATED")
        self.mark("CHILD_RESUMED")
        try:
            self.sample()
        except Exception as exc:  # amostragem é corroboração; a supervisão reamostra
            self.log("POSIX_SAMPLE_AFTER_START_FAILED %s: %s" % (type(exc).__name__, exc))
        return self.proc.pid

    def child_state(self) -> dict:
        alive = self.proc is not None and self.proc.poll() is None
        return {"child_created": self.child_created, "assigned": self.child_created,
                "resumed_threads": self.resumed_threads, "rollback": None, "child_alive": alive,
                "pid": self.proc.pid if self.proc is not None else None}

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

    def request_stop(self) -> dict:
        # Somente o coordenador recebe o sinal (workers V003 ignoram SIGINT). R15 (INT-11): corrida
        # com a saída do filho não é exceção — é entrega não realizada, registrada pelo supervisor.
        try:
            os.kill(self.proc.pid, signal.SIGINT)
            return {"delivered": True}
        except ProcessLookupError:
            return {"delivered": False, "error": "CHILD_ALREADY_EXITED"}
        except OSError as exc:
            return {"delivered": False, "error": "%s: %s" % (type(exc).__name__, exc)}

    def _assert_open(self) -> None:
        # Contrato espelhado do Windows (lá o handle do Job fica inválido após close): nenhuma
        # consulta ao custodiante é válida depois de close().
        if getattr(self, "_closed", False):
            raise RuntimeError("CUSTODY_QUERIED_AFTER_CLOSE")

    def observe_tree(self) -> str:
        self._assert_open()
        try:
            return "EMPTY" if not self.members() else "LIVE"
        except Exception:
            return "UNKNOWN"

    def tree_empty(self) -> bool:
        return self.observe_tree() == "EMPTY"

    def accounting(self) -> dict:
        self._assert_open()
        return {"TotalProcesses": len(self.seen), "ActiveProcesses": len(self.members())}

    def new_process_events(self) -> List[dict]:
        self._assert_open()
        return [{"pid": p, "ctime": c} for p, c in sorted(self.seen.items())]

    def release_live_tree_by_owner(self) -> dict:
        # Sem Job no POSIX: a sessão continua após a saída do supervisor (não há kill-on-close).
        plan = owner_release_plan(kill_on_close_cleared=True)
        self.released_by_owner = True
        self._closed = True
        return {"released": True, "kill_on_close_cleared": True, "plan": plan}

    def close(self) -> dict:
        # N2: devolve PROVA de fechamento. No POSIX não há handle de Job (sem kill-on-close); ainda
        # assim o fechamento só é declarado com a sessão sem membros ativos.
        try:
            active = len(self.members())
        except Exception as exc:
            return {"closed": False, "handles_closed": False, "active_processes": None,
                    "reason": "POSIX_MEMBERS_QUERY_FAILED:%s" % type(exc).__name__}
        if active == 0:
            self._closed = True
            return {"closed": True, "handles_closed": True, "active_processes": 0,
                    "reason": "POSIX_SESSION_CLOSED"}
        return {"closed": False, "handles_closed": False, "active_processes": active,
                "reason": "POSIX_CLOSE_REFUSED_LIVE_MEMBERS"}


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

    def evaluate(self, tree_empty: bool) -> dict:
        """I-01 (R17): produz o VEREDITO W04 SEM liberar fisicamente os handles da lease. A
        liberação física (release) fica para DEPOIS de a custódia do Job estar comprovadamente
        fechada — assim um close recusado/UNKNOWN mantém W04+Job retidos de fato (NO_KILL),
        fechando o ramo em que a R16 prometia o hold de emergência sem demonstrá-lo fisicamente."""
        if self.impl is not None:
            rep = self.impl.disarm(tree_empty, release=False)
            return w04_verdict(native=True, lease=rep["lease"], dirs=rep["dirs"], usn=rep["usn"],
                               identity=rep["identity"], census=rep["census"])
        after = inventory(self.root)
        same = {k: v for k, v in after.items()} == self.baseline
        v = w04_verdict(native=False, lease={}, dirs={}, usn={}, identity={}, census={})
        v["hash_continuity"] = "UNCHANGED" if same else "CHANGED"
        if not same:
            v["w04_full"] = "BLOCKED"
        return v

    def disarm(self, tree_empty: bool) -> dict:
        # Retrocompatível (qualificação direta da lease): avalia e LIBERA num único passo. O caminho
        # de produção do supervisor usa evaluate()+release() separados para o contrato de retenção.
        v = self.evaluate(tree_empty)
        self.release()
        return v


# =====================================================================================
# 5) EXECUÇÃO SUPERVISIONADA DE UM FILHO
# =====================================================================================
CUSTODY_STATE_SCHEMA = "PEGASUS_FULL_2026_V008_CUSTODY_STATE"
MAX_RECORDED_ERRORS = 200
_NO_RESULT = object()


class Supervision:
    """Execução supervisionada de UM filho como máquina de estados (R15).

    PRESPAWN -> SPAWNING -> RUNNING -> STOP_REQUESTED -> DRAINING -> (LIVE_TREE_BLOCKED) ->
    TREE_EMPTY -> W04_DISARMED -> CUSTODIAN_CLOSED (-> RESULT_PERSISTED, em _run_supervised).

    Invariantes:
      I1 a custódia (Job + lease W04) só é liberada com a árvore VERIFICADA vazia (duas observações
         consecutivas bem-sucedidas), quando nenhum filho chegou a existir, ou por disposição
         explícita do titular aplicada só se KILL_ON_JOB_CLOSE pôde ser removido antes;
      I2 depois que um filho existe, nenhuma exceção sai de run(): cada falha é registrada (a 1ª
         é a causa primária), persistida no CUSTODY_STATE e a supervisão continua; um defeito do
         próprio código estruturado cai no hold de emergência antes de qualquer liberação;
      I3 o supervisor nunca termina processo (exceção única: rollback do próprio filho que nunca
         executou código, decidido por start_failure_disposition na camada de custódia);
      I4 observação que falha é UNKNOWN, nunca vazio;
      I5 o hold nunca é mudo: CUSTODY_STATE é regravado a cada heartbeat com fase, causa primária,
         erros e a ação disponível ao titular.
    """

    def __init__(self, *, evidence: Path, protected_root: Path, out_root: Path, label: str,
                 stop_after_committed: Optional[int] = None, log=print):
        self.evidence = Path(evidence)
        self.protected_root = Path(protected_root)
        self.out_root = Path(out_root)
        self.label = label
        self.stop_after_committed = stop_after_committed
        self._raw_log = log
        self.log_failures = 0
        self.stop_requested = False
        self._prev_sigint = None
        self.phase = "PRESPAWN"
        self.errors: List[dict] = []
        self.error_counts: Dict[str, int] = {}
        self.primary_error: Optional[dict] = None
        self.state_write_failures = 0
        self._last_state_write = 0.0
        self.custody_state_path = self.evidence / (label + "_CUSTODY_STATE.json")
        self.disposition_path = self.evidence / (label + "_OWNER_CUSTODY_DISPOSITION.json")
        self.ctx: Dict[str, object] = {}

    # ------------------------------------------------------------ observabilidade que não derruba a custódia
    def log(self, msg: str) -> None:
        try:
            self._raw_log(msg)
        except Exception as exc:
            self.log_failures += 1
            try:
                sys.stderr.write("PEGASUS_SUPERVISOR_LOG_FAILED %s | %s\n" % (type(exc).__name__, msg))
            except Exception:
                self.log_failures += 1

    def _record_error(self, where: str, exc: BaseException) -> None:
        text = ("%s: %s" % (type(exc).__name__, exc))[:800]
        key = where + "|" + text
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
        if self.error_counts[key] != 1:
            return
        rec = {"phase": self.phase, "where": where, "error": text, "mono_ns": time.monotonic_ns()}
        if len(self.errors) < MAX_RECORDED_ERRORS:
            self.errors.append(rec)
        if self.primary_error is None:
            self.primary_error = rec
        self.log("SUPERVISION_ERROR phase=%s where=%s error=%s" % (self.phase, where, text))
        self._persist_state(force=True)

    def _guard(self, where: str, fn, default=None):
        try:
            return fn()
        except Exception as exc:
            self._record_error(where, exc)
            return default

    def _set_phase(self, phase: str) -> None:
        if phase != self.phase:
            self.phase = phase
            self.log("SUPERVISION_PHASE=%s label=%s" % (phase, self.label))
            self._persist_state(force=True)

    def summary(self) -> dict:
        return {"phase": self.phase, "primary_error": self.primary_error, "errors": list(self.errors),
                "error_occurrences": sum(self.error_counts.values()), "log_failures": self.log_failures,
                "custody_state_write_failures": self.state_write_failures,
                "custody_state_file": str(self.custody_state_path), **{k: v for k, v in self.ctx.items()}}

    def _persist_state(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_state_write < HEARTBEAT_S:
            return
        self._last_state_write = now
        doc = {"schema": CUSTODY_STATE_SCHEMA, "label": self.label, "wall_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "stop_requested": self.stop_requested, "owner_disposition_file": str(self.disposition_path),
               "no_kill": "SUPERVISOR_NEVER_TERMINATES_RUNNING_PROCESSES", **self.summary(), **GATES}
        if self.phase == "LIVE_TREE_BLOCKED":
            doc["owner_action"] = (
                "Arvore viva nao drena; o custodiante segue VIVO com W04+Job e nunca mata. Opcoes do titular: "
                "aguardar a drenagem; ou gravar %s com schema=%s, disposition=RELEASE_CUSTODY_LEAVE_TREE_RUNNING, "
                "ack_label, ack_child_pid e owner_statement (a arvore continua rodando SEM W04; aplicado so se "
                "KILL_ON_JOB_CLOSE puder ser removido antes)." % (self.disposition_path.name, OWNER_DISPOSITION_SCHEMA))
        try:
            self.evidence.mkdir(parents=True, exist_ok=True)
            write_json_atomic(self.custody_state_path, doc)
        except Exception as exc:
            self.state_write_failures += 1
            if self.state_write_failures in (1, 10, 100) or self.state_write_failures % 1000 == 0:
                try:
                    sys.stderr.write("PEGASUS_CUSTODY_STATE_WRITE_FAILED n=%d %s: %s\n"
                                     % (self.state_write_failures, type(exc).__name__, exc))
                except Exception:
                    self.log_failures += 1

    # ------------------------------------------------------------ telemetria tipada
    def _status_read(self):
        p = self.out_root / "TELEMETRY" / "R1R11_STATUS.json"
        try:
            raw = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}, "ABSENT"
        except Exception:
            return {}, "IO_ERROR"
        try:
            doc = json.loads(raw)
        except Exception:
            return {}, "CORRUPT"
        if not isinstance(doc, dict):
            return {}, "CORRUPT"
        return doc, "OK"

    def _status(self) -> dict:
        return self._status_read()[0]

    def _on_sigint(self, *_):
        # Ctrl+C no supervisor = pedido de SAFE_STOP; nunca kill. 2º Ctrl+C: espera.
        if not self.stop_requested:
            self.log("SUPERVISOR_SAFE_STOP_REQUESTED=YES ADMISSION=CLOSED_BY_COORDINATOR NO_KILL")
        self.stop_requested = True

    def _owner_disposition(self, child_pid) -> dict:
        if not self.disposition_path.exists():
            return owner_disposition_verdict(None, label=self.label, child_pid=child_pid)
        try:
            doc = json.loads(self.disposition_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"disposition": "WAIT", "reason": "UNREADABLE:%s" % type(exc).__name__}
        return owner_disposition_verdict(doc, label=self.label, child_pid=child_pid)

    # ------------------------------------------------------------ ciclo
    def _observe(self, cust) -> str:
        """Observação tri-estado da árvore; custodiante sem observe_tree usa tree_empty().
        Qualquer exceção (inclusive atributo ausente) é contida pelo _guard chamador -> UNKNOWN."""
        fn = getattr(cust, "observe_tree", None)
        if fn is not None:
            return fn()
        return "EMPTY" if cust.tree_empty() else "LIVE"

    def _prespawn_cleanup(self, cust, guard) -> None:
        if guard is not None:
            self._guard("prespawn_w04_release", lambda: guard.release())
        self._guard("prespawn_custody_close", lambda: cust.close())

    def run(self, argv: Sequence[str], env: Mapping, timeout_s: Optional[float] = 900.0,
            stale_after_s: float = 120.0) -> dict:
        """Levanta somente `PrespawnBlocked` (nenhum filho vivo; nenhum efeito). Depois que um filho
        existe, sempre devolve um resultado estruturado. `timeout_s` é só da qualificação (None em
        produção); `stale_after_s` é o watchdog do heartbeat do coordenador (pede SAFE_STOP)."""
        try:
            cust = make_custody(self.log)
        except Exception as exc:
            raise PrespawnBlocked("CUSTODY_INIT_FAILED_NO_SPAWN:%s: %s" % (type(exc).__name__, exc)) from exc
        guard = None
        arm = None
        try:
            guard = W04Guard(self.protected_root, self.log)
            arm = guard.arm()
            cust.mark("W04_ARM")
            # F02: gate PRÉ-SPAWN fail-closed — a lease tem de estar EFETIVAMENTE adquirida.
            prespawn = guard.prespawn_verdict()
            if prespawn.get("prespawn") != "ACQUIRED_CLEAN":
                raise PrespawnBlocked("W04_ARM_INCOMPLETE_NO_SPAWN_NO_PROTECTED_EFFECTS:"
                                      + ";".join(prespawn.get("gaps", [])))
            pre_status, pre_state = self._status_read()
            inst = pre_status.get("run_instance")
            self.ctx["pre_run_instance"] = inst if isinstance(inst, str) else None
            self.ctx["pre_status_state"] = pre_state
        except BaseException as exc:
            # R15 (INT-08): toda falha pré-spawn libera a lease parcial e fecha o custodiante vazio.
            self._prespawn_cleanup(cust, guard)
            if isinstance(exc, PrespawnBlocked):
                raise
            raise PrespawnBlocked("PRESPAWN_FAILED_NO_SPAWN:%s: %s" % (type(exc).__name__, exc)) from exc
        if threading.current_thread() is threading.main_thread():
            try:
                self._prev_sigint = signal.signal(signal.SIGINT, self._on_sigint)
            except Exception as exc:
                self._record_error("sigint_install", exc)
        try:
            return self._run_spawned(cust, guard, arm, argv, env, timeout_s, stale_after_s)
        finally:
            if self._prev_sigint is not None:
                try:
                    signal.signal(signal.SIGINT, self._prev_sigint)
                except Exception as exc:
                    self._record_error("sigint_restore", exc)

    def _run_spawned(self, cust, guard, arm, argv, env, timeout_s, stale_after_s) -> dict:
        stdout = self.evidence / (self.label + ".child.log")
        t0 = time.monotonic()
        self._set_phase("SPAWNING")
        try:
            pid = cust.start(argv, self.evidence, env, stdout)
        except BaseException as exc:
            cs = self._guard("child_state", lambda: cust.child_state(), {}) or {}
            klass = start_failure_effect_class(
                child_created=bool(cs.get("child_created")), assigned=bool(cs.get("assigned")),
                resumed_threads=_as_int(cs.get("resumed_threads"), 0),
                child_alive=cs.get("child_alive"), rollback_confirmed=isinstance(cs.get("rollback"), Mapping))
            self.ctx["start_failure"] = {"error": ("%s: %s" % (type(exc).__name__, exc))[:800],
                                         "effect_class": klass,
                                         **{k: cs.get(k) for k in ("child_created", "assigned", "resumed_threads",
                                                                   "rollback", "child_alive", "pid")}}
            if start_failure_is_no_effect(klass):
                # N1: desfecho SEM efeito só é admitido quando PROVADO (nenhum filho; ou suspenso
                # revertido que nunca retomou thread). Libera a lease parcial, fecha o custodiante
                # vazio e sai BLOCKED sem efeito (exit 2).
                self._prespawn_cleanup(cust, guard)
                raise PrespawnBlocked("CHILD_START_FAILED_NO_EFFECT:%s:%s: %s rollback=%s"
                                      % (klass, type(exc).__name__, exc, cs.get("rollback"))) from exc
            # N1: o filho retomou thread (EXECUTOU), está vivo, ou o estado é incerto — efeitos são
            # POSSÍVEIS. A custódia assume e NUNCA sai sem efeito: marca effects_started e segue à
            # supervisão/finalização (hold se a árvore viver; FAIL exit 3 se já estiver vazia).
            self._record_error("start", exc)
            self.ctx["effects_started"] = True
            pid = cs.get("pid")
        self.ctx["child_pid"] = pid
        self.ctx["effects_started"] = True
        self._set_phase("RUNNING")
        try:
            loop = self._supervise_loop(cust, guard, pid, t0, timeout_s, stale_after_s)
            return self._finalize(cust, guard, arm, pid, loop)
        except BaseException as exc:  # defesa em profundidade: defeito no código estruturado
            self._record_error("supervision_unexpected", exc)
            return self._emergency_hold_and_result(cust, guard, arm, pid)

    def _supervise_loop(self, cust, guard, pid, t0, timeout_s, stale_after_s) -> dict:
        rc = None
        status_initial = None
        last_hb = 0.0
        stop_deliveries = stop_failures = 0
        last_stop_delivery = 0.0
        stop_requested_at = None
        last_updated, last_change = None, time.monotonic()
        reconcile_reason = None
        reconcile_deadline = None
        reserved_reported = False
        consecutive_empty = unknown_streak = 0
        last_disposition_check = 0.0
        release_refusals = 0
        draining = False
        while True:
            now = time.monotonic()
            if rc is None:
                rc = self._guard("poll", lambda: cust.poll(), None)
                if rc is not None:
                    self.ctx["child_exit"] = rc
            self._guard("sample", lambda: cust.sample())
            st, st_state = self._status_read()
            self.ctx["status_state"] = st_state
            committed = _as_int(st.get("COMMITTED"))
            active = _as_int(st.get("ACTIVE"), 0)
            if status_initial is None and committed is not None:
                status_initial = committed
            if st.get("updated_at") != last_updated:
                last_updated, last_change = st.get("updated_at"), now
            elif rc is None and now - last_change > stale_after_s and not self.stop_requested:
                self.stop_requested = True
                self.log("WATCHDOG_STALE_HEARTBEAT seconds=%.1f ACTION=SAFE_STOP_REQUEST NO_KILL" % (now - last_change))
            if (self.stop_after_committed is not None and not self.stop_requested and committed is not None
                    and committed >= self.stop_after_committed and rc is None):
                self.stop_requested = True
                self.log("SUPERVISOR_SAFE_STOP_INJECTED after_committed=%d" % committed)
            if self.stop_requested and stop_requested_at is None:
                stop_requested_at = now
                if not draining:
                    self._set_phase("STOP_REQUESTED")
            latched = st.get("STOP_REQUESTED") is True
            if should_deliver_safe_stop(stop_requested=self.stop_requested, child_running=(rc is None),
                                        latched=latched, active=active, require_active_window=(os.name == "nt"),
                                        now=now, last_delivery=last_stop_delivery, deliveries=stop_deliveries):
                # A01: entrega cooperativa; qualquer falha (nonzero, timeout, spawn do helper, corrida)
                # é ERRO PERSISTIDO e contado — nunca encerra a custódia nem vira PASS.
                stop_deliveries += 1
                last_stop_delivery = now
                res = self._guard("request_stop", lambda: cust.request_stop(), _NO_RESULT)
                delivered = res is None or (isinstance(res, Mapping) and res.get("delivered") is True)
                if not delivered:
                    stop_failures += 1
                    if isinstance(res, Mapping):
                        self._record_error("request_stop", RuntimeError("SAFE_STOP_DELIVERY_FAILED %s"
                                                                         % (res.get("error") or res.get("helper_exit"))))
                self.ctx.update(stop_deliveries=stop_deliveries, stop_delivery_failures=stop_failures)
                self.log("SAFE_STOP_DELIVERY n=%d delivered=%s active=%s" % (stop_deliveries, delivered, active))
            if not draining:
                if (self.stop_requested and not latched and rc is None and stop_requested_at is not None
                        and now - stop_requested_at > SAFE_STOP_HONOR_DEADLINE_S):
                    reconcile_reason = "SAFE_STOP_NOT_HONORED_NO_LATCH"
                elif rc is not None:
                    reconcile_reason = "CHILD_EXITED"
                elif timeout_s is not None and now - t0 > timeout_s:
                    reconcile_reason = "QUALIFICATION_TIMEOUT"
                if reconcile_reason is not None:
                    draining = True
                    reconcile_deadline = now + RECONCILE_HOLD_S
                    self.ctx["reconcile_reason"] = reconcile_reason
                    self._set_phase("DRAINING")
            if draining:
                obs = self._guard("observe_tree", lambda: self._observe(cust), "UNKNOWN")
                if obs not in ("EMPTY", "LIVE", "UNKNOWN"):
                    obs = "UNKNOWN"
                consecutive_empty = consecutive_empty + 1 if obs == "EMPTY" else 0
                unknown_streak = unknown_streak + 1 if obs == "UNKNOWN" else 0
                self.ctx.update(tree=obs, consecutive_empty=consecutive_empty, tree_unknown_streak=unknown_streak)
                action = reconcile_step_action(tree_empty=tree_verified_empty(consecutive_empty),
                                               deadline_reached=(now > reconcile_deadline),
                                               production=(timeout_s is None), reserved_reported=reserved_reported)
                if action == "FINALIZE_SAFE":
                    if rc is None:
                        rc = self._guard("poll_final", lambda: cust.poll(), None)
                        self.ctx["child_exit"] = rc
                    self.ctx["tree_verified_empty"] = True
                    return {"exit": "TREE_EMPTY", "rc": rc, "reconcile_reason": reconcile_reason,
                            "reserved_reported": reserved_reported}
                if not reserved_reported and (action == "REPORT_RESERVED_THEN_HOLD" or now > reconcile_deadline):
                    reserved_reported = True
                    reconcile_reason = reconcile_reason + "+RESERVED_DECISION_HELD_ALIVE_NO_KILL"
                    self.ctx["reconcile_reason"] = reconcile_reason
                    self._set_phase("LIVE_TREE_BLOCKED")
                    self._report_live_tree_blocked(pid, reconcile_reason)
                if unknown_streak in (1, 50) or (unknown_streak and unknown_streak % 500 == 0):
                    self.log("CUSTODY_TREE_OBSERVATION_UNKNOWN streak=%d HOLD_CONTINUES_NO_RELEASE" % unknown_streak)
                if now - last_disposition_check >= 2.0:
                    last_disposition_check = now
                    disp = self._guard("owner_disposition", lambda: self._owner_disposition(pid), {"disposition": "WAIT"})
                    if (disp or {}).get("disposition") == "RELEASE":
                        rel = self._guard("owner_release", lambda: cust.release_live_tree_by_owner(), None)
                        if isinstance(rel, Mapping) and rel.get("released") is True:
                            self.ctx["owner_release"] = dict(rel)
                            return {"exit": "OWNER_RELEASED", "rc": rc, "reconcile_reason": reconcile_reason,
                                    "reserved_reported": reserved_reported}
                        release_refusals += 1
                        self.ctx["owner_release_refusals"] = release_refusals
                        self._record_error("owner_release", RuntimeError("OWNER_RELEASE_REFUSED_HOLD_CONTINUES %s"
                                                                         % (rel or {}).get("reason")))
            if now - last_hb >= HEARTBEAT_S:
                self._guard("w04_revalidate", lambda: guard.revalidate())
                if committed is not None:
                    total = _as_int(st.get("TOTAL"), 0)
                    e = self._guard("telemetry_eta", lambda: eta_status(
                        committed=committed, total=total, started_mono=t0, now_mono=now,
                        initial_committed=status_initial or 0), None)
                    if e is not None:
                        self.log("PEGASUS_SUPERVISOR_HEARTBEAT label=%s child=%s phase=%s committed=%s/%s eta_s=%s"
                                 % (self.label, pid, self.phase, e["committed"], e["total"], e["eta_s"]))
                self._persist_state(force=True)
                last_hb = now
            time.sleep(0.2 if draining else 0.05)

    def _report_live_tree_blocked(self, pid, reason) -> None:
        # R13-ORIGIN-01/R15: surge à origem UMA vez; o custodiante continua VIVO (W04+Job, handle do
        # Job aberto => KILL_ON_JOB_CLOSE ativo ou removido não dispara). Falha de escrita é ERRO
        # registrado (nunca `except: pass` mudo) e o hold continua observável pelo CUSTODY_STATE.
        rec = {"schema": "PEGASUS_FULL_2026_V008_W04_NOKILL_LIVE_TREE_RESERVED_DECISION",
               "label": self.label, "child_pid": pid, "reconcile_reason": reason,
               "custodian": "ALIVE_SUPERVISING_HOLDS_W04_AND_JOB_NO_KILL",
               "disposition": "RESERVED_FOR_OWNER_ORIGIN (aguardar drenagem / disposicao explicita do titular)",
               "owner_disposition_file": str(self.disposition_path),
               "supervisor_never": ["KILL", "CLOSE_JOB_HANDLE_ON_LIVE_TREE", "RELEASE_W04_ON_LIVE_TREE",
                                    "SELF_TERMINATE_ON_LIVE_TREE"],
               "external_failure_note": "termino forcado do proprio supervisor e falha externa irrecuperavel: o kernel fecha os handles (fail-safe KILL_ON_JOB_CLOSE); estado V003 consistente a falhas, nunca PASS"}
        self._guard("reserved_decision_receipt",
                    lambda: write_json_atomic(self.evidence / (self.label + "_W04_NOKILL_RESERVED_DECISION.json"), rec))
        self.log("CUSTODY_LIVE_TREE_BLOCKED pid=%s reason=%s: supervisor permanece VIVO (W04+Job retidos, NO_KILL); "
                 "estado em %s" % (pid, reason, self.custody_state_path.name))

    def _finalize(self, cust, guard, arm, pid, loop) -> dict:
        acc = events = None
        marks = []
        if loop["exit"] == "TREE_EMPTY":
            self._set_phase("TREE_EMPTY")
            self._guard("mark_tree_empty", lambda: cust.mark("TREE_EMPTY"))
            # N2: colher a evidência terminal e a contabilidade final ANTES de qualquer disarm/close
            # (após close() não há consulta válida). A contabilidade final tem de CONFIRMAR a árvore
            # vazia; se a observação contradizer TREE_EMPTY (ativos>0, consulta falha/UNKNOWN), NADA é
            # liberado — nem disarm, nem close, nem transição terminal: hold observável (W04+Job sob
            # custódia, NO_KILL).
            acc = self._guard("final_accounting", lambda: cust.accounting(), None)
            events = self._guard("final_events", lambda: cust.new_process_events(), None)
            acc_active = _as_int(acc.get("ActiveProcesses")) if isinstance(acc, Mapping) else None
            if acc_active != 0:
                self.ctx["finalize_contradiction"] = {"final_accounting": acc, "active": acc_active}
                self.ctx["tree_verified_empty"] = False
                self._record_error("finalize_tree_not_empty",
                                   RuntimeError("FINAL_ACCOUNTING_NOT_EMPTY active=%s" % acc_active))
                return self._emergency_hold_and_result(cust, guard, arm, pid)
            # I-01 (R17): AVALIA a W04 com os handles da lease AINDA RETIDOS (evaluate não libera) e
            # só então confirma o fechamento do Job. A liberação física (guard.release) ocorre
            # EXCLUSIVAMENTE depois de custody_close_confirmed; um close recusado/UNKNOWN cai no hold
            # de emergência com W04+Job fisicamente retidos (NO_KILL), fechando causalmente o ramo em
            # que a R16 prometia o hold sem o demonstrar (a disarm soltava a lease antes do close).
            w04 = self._guard("w04_evaluate", lambda: guard.evaluate(tree_empty=True), None)
            if not isinstance(w04, Mapping) or "w04_full" not in w04:
                w04 = {"w04_full": "BLOCKED", "gaps": ["W04_EVALUATE_FAILED"]}
            self._set_phase("W04_EVALUATED_HELD")
            self._guard("mark_w04_disarm", lambda: cust.mark("W04_DISARM"))
            # Marks colhidas APÓS registrar W04_DISARM (a ordem JIT exige esta marca) e ANTES do close
            # (após close não há consulta válida à custódia).
            marks = list(getattr(cust, "marks", []) or [])
            # N2: close() devolve PROVA estruturada; CUSTODIAN_CLOSED só com prova (closed=True,
            # active_processes=0). Retorno None/closed!=True/ativo!=0 => sem fechamento provado => hold.
            close_result = self._guard("custody_close", lambda: cust.close(), None)
            self.ctx["custody_close_result"] = close_result if isinstance(close_result, Mapping) else {"closed": None}
            if not custody_close_confirmed(close_result, tree_verified_empty=bool(self.ctx.get("tree_verified_empty"))):
                # Job NÃO fechado com prova: a W04 permanece RETIDA (não liberada) — hold observável.
                self.ctx["custody_closed"] = False
                self.ctx["w04_held_pending_close"] = True
                self._record_error("custody_close_unconfirmed",
                                   RuntimeError("CUSTODY_CLOSE_NOT_CONFIRMED result=%s" % (close_result,)))
                return self._emergency_hold_and_result(cust, guard, arm, pid)
            # Job fechado COM prova: agora é fisicamente seguro liberar a lease W04.
            self._guard("w04_release_after_close", lambda: guard.release())
            self._set_phase("W04_DISARMED")
            self.ctx["custody_closed"] = True
            self._set_phase("CUSTODIAN_CLOSED")
            outcome = "TREE_EMPTY_CUSTODY_CLOSED"
        else:
            # Disposição explícita do titular já aplicada pelo custodiante (flag removido antes).
            w04 = {"w04_full": "BLOCKED", "gaps": ["LEASE_RELEASED_BEFORE_TREE_EMPTY_BY_OWNER_DISPOSITION"]}
            self._guard("owner_release_w04", lambda: guard.release())
            marks = list(getattr(cust, "marks", []) or [])
            self.ctx["custody_closed"] = True
            self._set_phase("CUSTODIAN_RELEASED_BY_OWNER")
            outcome = "LIVE_TREE_RELEASED_BY_OWNER_NO_KILL"
        return self._compute_result(cust, arm, pid, loop.get("rc"), w04, acc, events, marks, outcome,
                                    loop.get("reconcile_reason"))

    def _compute_result(self, cust, arm, pid, rc, w04, acc, events, marks, outcome, reconcile_reason) -> dict:
        native_job = bool(getattr(cust, "native_job", False))
        events = list(events or [])
        acc_ok = isinstance(acc, Mapping)
        final_tree_empty = acc_ok and _as_int(acc.get("ActiveProcesses")) == 0 and bool(self.ctx.get("tree_verified_empty"))
        try:
            lineage = lineage_verdict(native_job=native_job, new_process=events, accounting=acc if acc_ok else {},
                                      active_zero_seen=final_tree_empty,
                                      breakaway_allowed=getattr(cust, "breakaway_allowed", False))
        except Exception as exc:
            lineage = {"lineage": "BLOCKED", "cause": ("%s: %s" % (type(exc).__name__, exc))[:400]}
        try:
            jit = jit_verdict([m for m in marks if m.get("mark") != "W04_ARM_BEGIN"])
        except Exception as exc:
            jit = {"jit": "BLOCKED", "cause": ("%s: %s" % (type(exc).__name__, exc))[:400]}
        run_lock = self._guard("run_lock_probe", lambda: (self.out_root / "RUN.lock").exists(), True)
        inv_a = self._guard("inventory_a", lambda: inventory(self.out_root), None)
        inv_b = self._guard("inventory_b", lambda: inventory(self.out_root), None)
        if inv_a is None or inv_b is None:
            inv_a, inv_b = {"<inventory_read_failed>": {"type": "error"}}, {}
        status, st_state = self._status_read()
        cp = self._guard("checkpoint_evidence", lambda: checkpoint_evidence(self.out_root),
                         {"valid": False, "completed": None, "reason": "EXCEPTION"})
        pids = {int(e["pid"]) for e in events if isinstance(e, Mapping) and _as_int(e.get("pid")) is not None}
        if _as_int(pid) is not None:
            pids.add(int(pid))
        mode = "SAFE_STOP" if self.stop_requested else "COMPLETION"
        terminal = terminal_evidence_verdict(mode=mode, status=status, status_state=st_state,
                                             pre_run_instance=self.ctx.get("pre_run_instance"),
                                             supervised_pids=pids, expected_out_root=self.out_root,
                                             checkpoint_ok=bool(cp.get("valid")), checkpoint_completed=cp.get("completed"))
        result = {"label": self.label, "child_pid": pid, "child_exit": rc, "w04_arm": arm, "w04": dict(w04),
                  "jit": jit, "lineage": lineage, "run_lock_present": run_lock,
                  "job_pids": sorted({int(e["pid"]) for e in events if isinstance(e, Mapping) and "pid" in e}),
                  # F03: identidades (pid, creation_time) observadas no Job — prova por identidade temporal.
                  "job_idents": sorted([int(e["pid"]), int(e.get("ctime") or 0)] for e in events
                                       if isinstance(e, Mapping) and "pid" in e),
                  "status": status, "status_state": st_state, "checkpoint": cp, "terminal_evidence": terminal,
                  "stop_requested": self.stop_requested, "reconcile_reason": reconcile_reason,
                  "outcome": outcome, "effects_started": True}
        if self.stop_requested:
            result["safe_stop"] = safestop_verdict(
                stop_requested=True, child_exit=rc, tree_empty=final_tree_empty, status=status,
                checkpoint_valid=bool(cp.get("valid")), run_lock_present=run_lock, w04=w04, terminal=terminal,
                lineage=lineage, jit=jit)
        else:
            result["completion"] = completion_verdict(child_exit=rc, tree_empty=final_tree_empty,
                                                      run_lock_present=run_lock, inventory_a=inv_a, inventory_b=inv_b,
                                                      w04=w04, terminal=terminal, lineage=lineage, jit=jit)
        result["supervision"] = self.summary()
        return result

    def _emergency_hold_and_result(self, cust, guard, arm, pid) -> dict:
        """Hold mínimo quando o próprio código estruturado falhou: nada é liberado sem árvore
        verificada vazia (ou disposição explícita do titular). Só primitivas protegidas."""
        w04 = {"w04_full": "BLOCKED", "gaps": ["SUPERVISION_UNEXPECTED_EXCEPTION"]}
        outcome = "FAIL_TECHNICAL_AFTER_SPAWN_TREE_EMPTY"
        if not self.ctx.get("custody_closed"):
            if not self.ctx.get("tree_verified_empty"):
                self._set_phase("LIVE_TREE_BLOCKED")
                consecutive = 0
                released = False
                while True:
                    obs = self._guard("emergency_observe", lambda: self._observe(cust), "UNKNOWN")
                    consecutive = consecutive + 1 if obs == "EMPTY" else 0
                    self.ctx.update(tree=obs, consecutive_empty=consecutive)
                    if tree_verified_empty(consecutive):
                        self.ctx["tree_verified_empty"] = True
                        break
                    disp = self._guard("emergency_disposition", lambda: self._owner_disposition(pid), None) or {}
                    if disp.get("disposition") == "RELEASE":
                        rel = self._guard("emergency_owner_release", lambda: cust.release_live_tree_by_owner(), None)
                        if isinstance(rel, Mapping) and rel.get("released") is True:
                            self.ctx["owner_release"] = dict(rel)
                            released = True
                            break
                    self._persist_state()
                    time.sleep(0.5)
                if released:
                    self._guard("emergency_w04_release", lambda: guard.release())
                    outcome = "LIVE_TREE_RELEASED_BY_OWNER_NO_KILL"
                    self.ctx["custody_closed"] = True
            if not self.ctx.get("custody_closed"):
                # I-01 (R17): AVALIA a W04 sem liberar; confirma o fechamento do Job; só LIBERA a
                # lease depois da prova de fechamento. Close recusado/UNKNOWN => W04+Job retidos.
                got = self._guard("emergency_w04_evaluate", lambda: guard.evaluate(tree_empty=True), None)
                if isinstance(got, Mapping) and got.get("w04_full") == "BLOCKED":
                    w04 = dict(got)
                close_result = self._guard("emergency_custody_close", lambda: cust.close(), None)
                self.ctx["custody_close_result"] = close_result if isinstance(close_result, Mapping) else {"closed": None}
                # N2: mesmo no hold de emergência, CUSTODIAN_CLOSED exige prova de fechamento.
                if custody_close_confirmed(close_result, tree_verified_empty=bool(self.ctx.get("tree_verified_empty"))):
                    self._guard("emergency_w04_release_after_close", lambda: guard.release())
                    self.ctx["custody_closed"] = True
                    self.ctx["w04_held_pending_close"] = False
                else:
                    self.ctx["w04_held_pending_close"] = True
        self._set_phase("CUSTODIAN_CLOSED" if self.ctx.get("custody_closed") else "LIVE_TREE_BLOCKED")
        verdict = {"completed": False, "gaps": ["SUPERVISION_UNEXPECTED_EXCEPTION"]}
        res = {"label": self.label, "child_pid": pid, "child_exit": self.ctx.get("child_exit"), "w04_arm": arm,
               "w04": w04, "jit": {"jit": "BLOCKED", "cause": "SUPERVISION_UNEXPECTED_EXCEPTION"},
               "lineage": {"lineage": "BLOCKED", "cause": "SUPERVISION_UNEXPECTED_EXCEPTION"},
               "run_lock_present": True, "job_pids": [], "job_idents": [], "status": self._status(),
               "stop_requested": self.stop_requested, "reconcile_reason": self.ctx.get("reconcile_reason"),
               "outcome": outcome, "effects_started": True}
        if self.stop_requested:
            res["safe_stop"] = {"safe_stop": "NOT_CONFIRMED", "gaps": verdict["gaps"]}
        else:
            res["completion"] = verdict
        res["supervision"] = self.summary()
        return res


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


# =====================================================================================
# I-03 — ADMISSÃO DE PRODUÇÃO REAL E ENCADEAMENTO B->C->FULL (fail-closed)
# =====================================================================================
# A rota executável REAL de autorização de produção. Fecha a lacuna "FULL econômico inexistente
# como rota executável": existe, é alcançável e encadeia B->C->FULL, vinculada aos contratos
# técnicos exigidos (R01–R06, QS4 sucessor, QS5/B06, PolicyRoot como ENTRADA técnica, qualificação
# Windows dirigida, admissão de fontes por hash, volume/espaço, runtime). NÃO promove nada: mesmo um
# pacote de autorização completo e válido em SHA termina no selo final `entry.release_admission`,
# que bloqueia enquanto RELEASE_STATE != RUN_RELEASED. Nunca fabrica credenciais/recibos, nunca
# antecipa QS4/Phase B/C, nunca cria aprovação administrativa de Owner Gate. PolicyRoot permanece
# entrada técnica obrigatória (verificada só por presença + SHA do recibo), não autoridade canônica
# adicional — este código NÃO lê, baixa, autentica nem revalida MASTER/HEAD/política.
PRODUCTION_AUTH_SCHEMA = "PEGASUS_FULL_2026_V008_PRODUCTION_AUTHORIZATION_BUNDLE"

# Gates técnicos OBRIGATÓRIOS da liberação futura (01_IMPLEMENTATION_CONTRACT / gate ledger).
REQUIRED_PRODUCTION_GATES = (
    "R01_R06_PHYSICAL_DEFINITIONS",
    "QS4_SUCCESSOR_QUALIFICATION",
    "QS5_B06_INDEPENDENT_AUDIT",
    "POLICYROOT_LIVE_CAPTURE",
    "WINDOWS_DIRECTED_QUALIFICATION",
    "SOURCE_ADMISSION_BY_HASH",
    "VOLUME_SERIAL_AND_FREE_SPACE",
    "RUNTIME_PYTHON_3_14_7_PS_5_1",
)
PHASE_CHAIN_PREDECESSORS = {"B": (), "C": ("B",), "FULL": ("B", "C")}
_HEXSET = set("0123456789ABCDEF")


def production_admission_verdict(bundle, *, phase) -> dict:
    """PURO/testável offline. Verifica o pacote de autorização de produção fornecido EXTERNAMENTE
    pelo titular: schema, fase e cada gate técnico obrigatório presente com recibo vinculado por
    SHA-256 (sha + status=PASS). Verifica o encadeamento (C exige B; FULL exige B e C). NUNCA
    promove: o veredito ADMITTED_PENDING_FINAL_SEAL apenas HABILITA o supervisor a chamar o selo
    final (entry.release_admission), que bloqueia enquanto RUN_RELEASED=NO. Qualquer ausência,
    schema inválido, gate faltante, SHA inválido/divergente ou status != PASS => BLOCKED com causa."""
    if not isinstance(bundle, Mapping):
        return {"admission": "BLOCKED", "gaps": ["AUTHORIZATION_BUNDLE_ABSENT"]}
    if bundle.get("schema") != PRODUCTION_AUTH_SCHEMA:
        return {"admission": "BLOCKED", "gaps": ["AUTHORIZATION_BUNDLE_SCHEMA_INVALID"]}
    if phase not in PHASE_CHAIN_PREDECESSORS:
        return {"admission": "BLOCKED", "gaps": ["PHASE_INVALID:%s" % phase]}
    gates = bundle.get("gates") if isinstance(bundle.get("gates"), Mapping) else {}
    chain = bundle.get("phase_chain") if isinstance(bundle.get("phase_chain"), Mapping) else {}
    gaps: List[str] = []
    satisfied: Dict[str, str] = {}
    for g in REQUIRED_PRODUCTION_GATES:
        rec = gates.get(g)
        if not isinstance(rec, Mapping):
            gaps.append("GATE_MISSING:%s" % g)
            continue
        sha = str(rec.get("sha256", "")).upper()
        if len(sha) != 64 or any(c not in _HEXSET for c in sha):
            gaps.append("GATE_SHA_INVALID:%s" % g)
            continue
        if rec.get("status") != "PASS":
            gaps.append("GATE_NOT_PASS:%s" % g)
            continue
        satisfied[g] = sha
    for pre in PHASE_CHAIN_PREDECESSORS[phase]:
        if chain.get(pre) != "PASS":
            gaps.append("PHASE_CHAIN_PREDECESSOR_NOT_PASS:%s" % pre)
    if gaps:
        return {"admission": "BLOCKED", "gaps": sorted(gaps)}
    return {"admission": "ADMITTED_PENDING_FINAL_SEAL", "phase": phase, "gates": satisfied}


class ProductionReleaseAdmission:
    """Admissão de produção REAL (I-03). Lê o pacote de autorização externo do titular (JSON, FORA
    do pacote selado), verifica os gates técnicos por SHA via production_admission_verdict e SÓ ENTÃO
    chama o selo final do V003. Mesmo um pacote completo bloqueia em entry.release_admission enquanto
    RELEASE_STATE != RUN_RELEASED. Não fabrica nada; não antecipa QS4/B/C; não cria Owner Gate."""
    schema = "PEGASUS_FULL_2026_V008_PRODUCTION_RELEASE_ADMISSION"

    def __init__(self, bundle_path):
        self.bundle_path = bundle_path

    def _load_bundle(self, package_root: Path):
        if not self.bundle_path:
            return None
        p = Path(self.bundle_path).resolve()
        # Auto-autorização proibida: o pacote de autorização NUNCA pode estar dentro do pacote selado.
        if p.is_relative_to(Path(package_root).resolve()):
            raise SupervisorBlocked("AUTHORIZATION_BUNDLE_INSIDE_SEALED_PACKAGE_FORBIDDEN")
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SupervisorBlocked("AUTHORIZATION_BUNDLE_UNREADABLE:%s" % type(exc).__name__)

    def admit(self, *, phase, package_root, entry, ns):
        bundle = self._load_bundle(package_root)
        verdict = production_admission_verdict(bundle, phase=phase)
        if verdict["admission"] != "ADMITTED_PENDING_FINAL_SEAL":
            raise entry.Blocked("PRODUCTION_ADMISSION_BLOCKED:" + ";".join(verdict["gaps"]))
        # Gates técnicos presentes: ainda assim o selo final do runtime V003 decide — e bloqueia aqui
        # (RUN_RELEASED=NO). O encadeamento econômico não existe sem a liberação legítima da origem.
        entry.release_admission({"production_admission": verdict}, phase if phase in ("B", "C") else "C")
        raise SupervisorBlocked("PRODUCTION_RELEASE_ADMISSION_REACHED_FINAL_SEAL_STILL_BLOCKED")


SEALED_SYNTHETIC_ADMISSION_REL = "supervisor/tests/pegasus_synthetic_admission_v008.py"
ECONOMIC_ENTRY_MODULES = ("pegasus_entry", "r1r11_full_2026", "r1r11_correct_full_controller",
                          "r1r11_perf_next_controller", "r1r11_activation_controller", "r1r11_owner_gates",
                          "r1r11_postpilot_promotion", "r1r11_full_homologation")


def plan_isolation_verdict(plan: Mapping, *, package_root: Path) -> dict:
    """R15 (C4/INT-13): isolamento EFETIVO, verificado no código, entre um plano não econômico e
    os caminhos econômicos/produtivos: o argv não pode apontar arquivo sob `CODE/` (runtime
    econômico) nem módulo/entrypoint econômico (`-m`, `-c` ou caminho), e a saída tem de ficar
    fora do pacote selado. Não substitui a dupla barreira econômica; é a prova do lado sintético."""
    gaps = []
    root = Path(package_root).resolve()
    code_dir = (root / "CODE").resolve()
    if plan.get("economic"):
        gaps.append("PLAN_MARKED_ECONOMIC")
    try:
        if Path(str(plan.get("out_root"))).resolve().is_relative_to(root):
            gaps.append("OUT_ROOT_INSIDE_SEALED_PACKAGE")
    except Exception:
        gaps.append("OUT_ROOT_UNRESOLVABLE")
    argv = [str(a) for a in (plan.get("argv") or [])]
    if not argv:
        gaps.append("ARGV_EMPTY")
    for i, a in enumerate(argv):
        if i == 0:
            continue  # o interpretador
        lowered = a.replace("\\", "/")
        if "/" in lowered or lowered.endswith(".py"):
            try:
                if Path(a).resolve().is_relative_to(code_dir):
                    gaps.append("ARGV_TARGETS_ECONOMIC_RUNTIME:" + Path(a).name)
            except Exception:
                gaps.append("ARGV_PATH_UNRESOLVABLE")
        if argv[i - 1] in ("-m", "-c") or i == 1:
            for mod in ECONOMIC_ENTRY_MODULES:
                if mod in a:
                    gaps.append("ARGV_REFERENCES_ECONOMIC_ENTRY:" + mod)
    return {"isolation": "ISOLATED_NON_ECONOMIC" if not gaps else "NOT_ISOLATED", "gaps": sorted(set(gaps))}


def _load_admission(ns):
    """Default: DefaultReleaseAdmission. `--admission <arquivo.py>` injeta um módulo de
    admissão — permitido SOMENTE para qualificação sintética isolada. R15 (INT-13): só é aceito o
    módulo sintético SELADO do próprio pacote (caminho exato + SHA do manifesto); qualquer outro
    arquivo é recusado ANTES de ser carregado (nenhum código arbitrário é executado)."""
    # I-03: `--authorization <bundle.json>` seleciona a admissão de PRODUÇÃO real (fail-closed no selo
    # final). Mutuamente exclusivo com `--admission` (qualificação sintética). Sem nenhum, é a
    # admissão de produção DEFAULT (DefaultReleaseAdmission), que bloqueia incondicionalmente.
    auth = getattr(ns, "authorization", None)
    path = getattr(ns, "admission", None)
    if auth and path:
        raise SupervisorBlocked("ADMISSION_AND_AUTHORIZATION_MUTUALLY_EXCLUSIVE")
    if auth:
        return ProductionReleaseAdmission(auth)
    if not path:
        return DefaultReleaseAdmission()
    sealed = (ROOT / SEALED_SYNTHETIC_ADMISSION_REL).resolve()
    if Path(path).resolve() != sealed:
        raise SupervisorBlocked("ADMISSION_MODULE_NOT_SEALED_SYNTHETIC:" + str(Path(path).resolve()))
    expected = json.loads((ROOT / "MANIFEST_SHA256.json").read_text(encoding="utf-8")).get(SEALED_SYNTHETIC_ADMISSION_REL)
    if not expected or str(expected).upper() != sha256_file(sealed):
        raise SupervisorBlocked("ADMISSION_MODULE_IDENTITY_MISMATCH")
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


SUPERVISED_RUN_SCHEMA = "PEGASUS_FULL_2026_V008_SUPERVISED_RUN_RESULT"


def persist_run_receipt(evidence: Path, label: str, doc: dict) -> dict:
    """R15 (A04): persiste o recibo no caminho canônico; se falhar, grava um recibo alternativo
    exclusivo com a causa. Só o caminho canônico conta para 0/130 — nunca levanta."""
    primary = Path(evidence) / (label + "_SUPERVISED_RUN_RESULT.json")
    try:
        Path(evidence).mkdir(parents=True, exist_ok=True)
        write_json_atomic(primary, doc)
        return {"persisted": True, "path": str(primary), "error": None}
    except Exception as exc:
        err = ("%s: %s" % (type(exc).__name__, exc))[:600]
    try:
        alt = Path(evidence) / ("%s_SUPERVISED_RUN_RESULT.FALLBACK_%d_%d.json" % (label, os.getpid(), time.time_ns()))
        write_json_new(alt, {**doc, "result": "FAIL_SUPERVISED_RUN", "exit_code": EXIT_FAIL,
                             "exit_class": classify_exit(EXIT_FAIL), "receipt_write_error": err})
        return {"persisted": False, "path": str(alt), "error": err}
    except Exception as exc2:
        return {"persisted": False, "path": None, "error": err + " | fallback %s: %s" % (type(exc2).__name__, exc2)}


def _run_supervised(plan, *, evidence: Path, entry, log=print) -> int:
    """Executa o argv admitido sob supervisão plena: W04 armado antes do filho, Job com
    linhagem, SAFE_STOP cooperativo, watchdog, retomada e porta de conclusão/evidência.
    R15: todo desfecho tem recibo estruturado; 0 e 130 exigem recibo persistido no caminho
    canônico; bloqueio sem filho vivo é 2 (sem efeito); qualquer outro desfecho após o spawn é 3,
    com causa primária e estado de efeitos."""
    if plan.get("schema") != RUN_PLAN_SCHEMA:
        raise SupervisorBlocked("RUN_PLAN_SCHEMA_INVALID")
    if plan["economic"]:
        if not plan.get("external_authorization_proven"):
            raise SupervisorBlocked("ECONOMIC_PLAN_WITHOUT_PROVEN_EXTERNAL_AUTHORIZATION")
        # Dupla barreira: mesmo com plano econômico "autorizado", o executor econômico real
        # revalida `release_admission` por dentro; neste artefato isso bloqueia de novo.
        entry.release_admission({}, "C" if "run-c" in plan["argv"] else "B")
        raise SupervisorBlocked("ECONOMIC_EXECUTION_STILL_BLOCKED_BY_ENTRY_RELEASE_ADMISSION")
    iso = plan_isolation_verdict(plan, package_root=ROOT)
    if iso["isolation"] != "ISOLATED_NON_ECONOMIC":
        raise SupervisorBlocked("RUN_PLAN_NOT_ISOLATED:" + ";".join(iso["gaps"]))
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    out_root = Path(plan["out_root"])
    label = plan["label"]
    plan_view = {k: plan[k] for k in ("label", "economic", "admission_schema", "admission_sha256")}
    s = Supervision(evidence=evidence, protected_root=Path(plan["protected_root"]), out_root=out_root,
                    label=label, stop_after_committed=plan.get("stop_after_committed"), log=log)
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    try:
        result = s.run(plan["argv"], env, timeout_s=plan.get("timeout_s"))
    except PrespawnBlocked as exc:
        # I-02 (R17): grava-se o recibo canônico com o desfecho otimista (BLOCKED/exit 2) e, em
        # seguida, o desfecho é RECALCULADO com o resultado REAL da persistência. Se o canônico não
        # foi gravado (fallback FAIL), result/exit_code/exit_class/banner passam todos a FAIL/exit 3.
        doc = {"schema": SUPERVISED_RUN_SCHEMA, "result": "BLOCKED_PRESPAWN_NO_EFFECT", "cause": str(exc),
               "effects_started": False, "exit_code": EXIT_BLOCKED, "exit_class": classify_exit(EXIT_BLOCKED),
               "plan": plan_view, "isolation": iso, "supervision": s.summary(), **GATES}
        rec = persist_run_receipt(evidence, label, doc)
        final = terminal_for_prespawn_block(bool(rec["persisted"]))
        s._set_phase("RESULT_PERSISTED" if rec["persisted"] else "RESULT_PERSIST_FAILED")
        _emit_summary({"schema": SUPERVISED_RUN_SCHEMA, "result": final["result"], "cause": doc["cause"],
                       "effects_started": final["effects_started"], "exit_code": final["exit_code"],
                       "exit_class": final["exit_class"], "receipt": rec})
        return final["exit_code"]
    except BaseException as exc:  # run() não levanta após o spawn; defesa com recibo técnico
        doc = {"schema": SUPERVISED_RUN_SCHEMA, "result": "FAIL_TECHNICAL_SUPERVISION",
               "cause": ("%s: %s" % (type(exc).__name__, exc))[:800],
               "effects_started": bool(s.ctx.get("effects_started")), "exit_code": EXIT_FAIL,
               "exit_class": classify_exit(EXIT_FAIL), "plan": plan_view, "supervision": s.summary(), **GATES}
        rec = persist_run_receipt(evidence, label, doc)
        final = terminal_for_post_spawn_fail(bool(rec["persisted"]), effects_started=bool(s.ctx.get("effects_started")))
        s._set_phase("RESULT_PERSISTED" if rec["persisted"] else "RESULT_PERSIST_FAILED")
        _emit_summary({"schema": SUPERVISED_RUN_SCHEMA, "result": final["result"], "cause": doc["cause"],
                       "effects_started": final["effects_started"], "exit_code": final["exit_code"],
                       "exit_class": final["exit_class"], "receipt": rec})
        return final["exit_code"]
    result["schema"] = SUPERVISED_RUN_SCHEMA
    result["plan"] = plan_view
    result["isolation"] = iso
    completed = (result.get("completion") or {}).get("completed") is True
    stopped = str((result.get("safe_stop") or {}).get("safe_stop", "")).startswith("CONFIRMED_BY_SUPERVISOR")
    # N2/N3: a custódia tem de estar comprovadamente encerrada (ou liberada pelo titular) para um
    # desfecho terminal; se o fechamento não foi provado, nunca é sucesso, qualquer que seja o
    # veredito de conclusão.
    custody_resolved = bool(s.ctx.get("custody_closed")) or bool(s.ctx.get("owner_release"))
    if not custody_resolved:
        completed = False
        stopped = False
        result.setdefault("gaps", []).append("CUSTODY_NOT_PROVEN_CLOSED")
    result["primary_cause"] = (s.primary_error or {}).get("error")
    result["custody_resolved"] = custody_resolved
    # N3: desfecho ÚNICO e coerente. Grava-se o recibo canônico com o desfecho otimista (assume
    # persistência); em seguida o desfecho é RECALCULADO com o resultado REAL da persistência e TODOS
    # os campos (result, exit_code, exit_class, banner e fase) passam a exprimir o MESMO desfecho.
    optimistic = supervised_final_outcome(completed=completed, stopped=stopped, receipt_persisted=True)
    result.update(optimistic)
    rec = persist_run_receipt(evidence, label, result)
    final = supervised_final_outcome(completed=completed, stopped=stopped, receipt_persisted=bool(rec["persisted"]))
    result.update(final)
    result["receipt"] = rec
    code = final["exit_code"]
    s._set_phase("RESULT_PERSISTED" if rec["persisted"] else "RESULT_PERSIST_FAILED")
    # N3/I-02: a falha de emissão do PRÓPRIO resumo não pode alterar o desfecho nem derrubar o
    # processo. _emit_summary encapsula o print à prova de falha, usado por TODOS os ramos.
    _emit_summary({k: result[k] for k in ("schema", "result", "label", "child_exit", "outcome") if k in result}
                  | {"w04_full": (result.get("w04") or {}).get("w04_full"),
                     "lineage": (result.get("lineage") or {}).get("lineage"),
                     "exit_code": code, "exit_class": result["exit_class"],
                     "custody_resolved": custody_resolved, "receipt": rec})
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


def cmd_run_full(ns) -> int:
    """I-03: caminho FULL ENCADEADO B -> C -> FULL (antes `run-full` escolhia só phase=B). Cada fase
    passa pela admissão única; C exige o PASS de B e FULL exige B e C. Neste artefato a admissão
    bloqueia já em B (sem autorização legítima / RUN_RELEASED=NO), então a cadeia devolve BLOCKED
    identificando a fase e a causa — sem efeito econômico, sem antecipar fases, fail-closed real."""
    entry = _import_entry()
    entry.verify_tree(ROOT)
    verify_supervisor_parents()
    admission = _load_admission(ns)
    adm_name = getattr(admission, "schema", type(admission).__name__)
    chain: List[dict] = []
    for phase in ("B", "C", "FULL"):
        try:
            plan = admission.admit(phase=phase, package_root=ROOT, entry=entry, ns=ns)
        except entry.Blocked as exc:
            chain.append({"phase": phase, "result": "BLOCKED", "cause": str(exc)})
            print(json.dumps({"schema": SCHEMA, "result": "FULL_CHAIN_BLOCKED", "blocked_at": phase,
                              "chain": chain, "admission": adm_name, "effects": "NONE", **GATES},
                             sort_keys=True))
            return EXIT_BLOCKED
        except SupervisorBlocked as exc:
            chain.append({"phase": phase, "result": "BLOCKED_FINAL_SEAL", "cause": str(exc)})
            print(json.dumps({"schema": SCHEMA, "result": "FULL_CHAIN_BLOCKED_AT_FINAL_SEAL",
                              "blocked_at": phase, "chain": chain, "admission": adm_name,
                              "effects": "NONE", **GATES}, sort_keys=True))
            return EXIT_BLOCKED
        # Admissão concedida (inalcançável neste artefato): executa supervisionado e exige o PASS do
        # predecessor antes da próxima fase. Mantido para completude estrutural da rota.
        if getattr(ns, "evidence", None):
            evidence = Path(ns.evidence) / ("PHASE_%s_EVIDENCE" % phase)
        else:
            evidence = Path(plan["out_root"]).parent / (plan["label"] + "_EVIDENCE")
        rc = _run_supervised(plan, evidence=evidence, entry=entry)
        chain.append({"phase": phase, "result": "RAN", "exit_code": rc, "exit_class": classify_exit(rc)})
        if rc != EXIT_PASS:
            print(json.dumps({"schema": SCHEMA, "result": "FULL_CHAIN_HALTED", "halted_at": phase,
                              "chain": chain, "admission": adm_name, **GATES}, sort_keys=True))
            return rc
    print(json.dumps({"schema": SCHEMA, "result": "FULL_CHAIN_COMPLETE", "chain": chain,
                      "admission": adm_name, **GATES}, sort_keys=True))
    return EXIT_PASS


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
        # qualificação sintética isolada; nunca pode produzir plano econômico. --authorization
        # (I-03) seleciona a admissão de produção real sobre um pacote de autorização externo do
        # titular; mesmo completo, bloqueia no selo final (RUN_RELEASED=NO).
        rp.add_argument("--admission", default=None)
        rp.add_argument("--authorization", default=None)
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
        if ns.cmd == "run-full":
            return cmd_run_full(ns)          # I-03: encadeia B -> C -> FULL
        if ns.cmd in ("run-b", "run-c"):
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
        print(json.dumps({"schema": SCHEMA, "result": "FAIL_TECHNICAL", "cause": ("%s: %s" % (type(exc).__name__, exc))[:800],
                          "exit_code": EXIT_FAIL, "exit_class": classify_exit(EXIT_FAIL), **GATES}, sort_keys=True), flush=True)
        return EXIT_FAIL
    except KeyboardInterrupt:
        # Ctrl+C fora da supervisão (que o converte em SAFE_STOP): falha técnica explícita, nunca 0/1.
        print(json.dumps({"schema": SCHEMA, "result": "FAIL_TECHNICAL", "cause": "KEYBOARD_INTERRUPT_OUTSIDE_SUPERVISION",
                          "exit_code": EXIT_FAIL, "exit_class": classify_exit(EXIT_FAIL), **GATES}, sort_keys=True), flush=True)
        return EXIT_FAIL
    return EXIT_BLOCKED


if __name__ == "__main__":
    sys.exit(main())
