"""PEGASUS FULL 2026 V008 — camada nativa Windows do supervisor (somente os.name == 'nt').

  * WindowsJobCustody: filho criado SUSPENSO -> AssignProcessToJobObject -> ResumeThread (JIT);
    Job anônimo (nenhum processo externo obtém handle de ASSIGN), sem BREAKAWAY; porta de
    conclusão do Job para NEW_PROCESS/EXIT/ACTIVE_PROCESS_ZERO, identidade (PID, creation
    FILETIME) e contabilidade TotalProcesses/ActiveProcesses. KILL_ON_JOB_CLOSE é somente o
    fail-safe de queda do supervisor (sem supervisor não há lease W04); nunca é usado como
    SAFE_STOP e o supervisor jamais termina processo por iniciativa própria.
  * W04NativeLease: antes de criar o filho, abre TODO arquivo protegido (e cada stream nomeado)
    com compartilhamento somente-leitura (nega WRITE e DELETE) e cada diretório protegido sem
    DELETE-share; registra (volume serial, FRN, nº de links); marca o USN inicial do volume.
    Uma abertura falha com ERROR_SHARING_VIOLATION se já houver handle com escrita/remoção
    ou seção mapeada gravável — prova kernel, independente de nome/tipo do handle. No fim
    (árvore vazia), lê o USN do início ao fim e exige zero registros sobre o conjunto.
  * Census de handles: R14R3 `native_handle_backend_v001` (bytes 8FEF1313…) como corroboração.

Requer Windows x64, Python 3.14.7 alvo, execução elevada (volume USN e SeDebugPrivilege).
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path

if os.name != "nt":  # pragma: no cover - importado só no Windows
    raise ImportError("WINDOWS_ONLY_MODULE")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
HANDLE = wintypes.HANDLE
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# ---------------------------------------------------------------- constantes
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NEW_PROCESS_GROUP = 0x00000200
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
JobObjectBasicAccountingInformation = 1
JobObjectBasicProcessIdList = 3
CENSUS_MAX_ATTEMPTS = 3      # novas tentativas do census (corroboração) se a enumeração vier truncada
JobObjectAssociateCompletionPortInformation = 7
JobObjectExtendedLimitInformation = 9
MSG_ACTIVE_PROCESS_ZERO, MSG_NEW_PROCESS, MSG_EXIT_PROCESS, MSG_ABNORMAL_EXIT = 4, 6, 7, 8
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

GENERIC_READ = 0x80000000
FILE_LIST_DIRECTORY = 0x0001
FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_READ, FILE_SHARE_WRITE, FILE_SHARE_DELETE = 1, 2, 4
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
ERROR_SHARING_VIOLATION = 32
ERROR_HANDLE_EOF = 38
ERROR_JOURNAL_NOT_ACTIVE = 1179
FSCTL_QUERY_USN_JOURNAL = 0x000900F4
FSCTL_READ_USN_JOURNAL = 0x000900BB
WRITE_ACCESS_BITS = (0x0002 | 0x0004 | 0x0010 | 0x0100 | 0x00010000 | 0x00040000 | 0x00080000
                     | 0x40000000 | 0x10000000)


# ---------------------------------------------------------------- estruturas (x64)
class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class JOBOBJECT_ASSOCIATE_COMPLETION_PORT(ctypes.Structure):
    _fields_ = [("CompletionKey", ctypes.c_void_p), ("CompletionPort", HANDLE)]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]


class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [("dwFileAttributes", wintypes.DWORD), ("ftCreationTime", wintypes.FILETIME),
                ("ftLastAccessTime", wintypes.FILETIME), ("ftLastWriteTime", wintypes.FILETIME),
                ("dwVolumeSerialNumber", wintypes.DWORD), ("nFileSizeHigh", wintypes.DWORD),
                ("nFileSizeLow", wintypes.DWORD), ("nNumberOfLinks", wintypes.DWORD),
                ("nFileIndexHigh", wintypes.DWORD), ("nFileIndexLow", wintypes.DWORD)]


class WIN32_FIND_STREAM_DATA(ctypes.Structure):
    _fields_ = [("StreamSize", ctypes.c_longlong), ("cStreamName", wintypes.WCHAR * 296)]


class USN_JOURNAL_DATA_V0(ctypes.Structure):
    _fields_ = [("UsnJournalID", ctypes.c_ulonglong), ("FirstUsn", ctypes.c_longlong),
                ("NextUsn", ctypes.c_longlong), ("LowestValidUsn", ctypes.c_longlong),
                ("MaxUsn", ctypes.c_longlong), ("MaximumSize", ctypes.c_ulonglong),
                ("AllocationDelta", ctypes.c_ulonglong)]


class READ_USN_JOURNAL_DATA_V0(ctypes.Structure):
    _fields_ = [("StartUsn", ctypes.c_longlong), ("ReasonMask", wintypes.DWORD),
                ("ReturnOnlyOnClose", wintypes.DWORD), ("Timeout", ctypes.c_ulonglong),
                ("BytesToWaitFor", ctypes.c_ulonglong), ("UsnJournalID", ctypes.c_ulonglong)]


def _sig(fn, argtypes, restype):
    fn.argtypes, fn.restype = argtypes, restype
    return fn


CreateJobObjectW = _sig(k32.CreateJobObjectW, [ctypes.c_void_p, wintypes.LPCWSTR], HANDLE)
SetInformationJobObject = _sig(k32.SetInformationJobObject, [HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL)
QueryInformationJobObject = _sig(k32.QueryInformationJobObject, [HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
AssignProcessToJobObject = _sig(k32.AssignProcessToJobObject, [HANDLE, HANDLE], wintypes.BOOL)
CreateIoCompletionPort = _sig(k32.CreateIoCompletionPort, [HANDLE, HANDLE, ctypes.c_size_t, wintypes.DWORD], HANDLE)
GetQueuedCompletionStatus = _sig(k32.GetQueuedCompletionStatus, [HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD], wintypes.BOOL)
CreateToolhelp32Snapshot = _sig(k32.CreateToolhelp32Snapshot, [wintypes.DWORD, wintypes.DWORD], HANDLE)
Thread32First = _sig(k32.Thread32First, [HANDLE, ctypes.POINTER(THREADENTRY32)], wintypes.BOOL)
Thread32Next = _sig(k32.Thread32Next, [HANDLE, ctypes.POINTER(THREADENTRY32)], wintypes.BOOL)
OpenThread = _sig(k32.OpenThread, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], HANDLE)
ResumeThread = _sig(k32.ResumeThread, [HANDLE], wintypes.DWORD)
OpenProcess = _sig(k32.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], HANDLE)
GetProcessTimes = _sig(k32.GetProcessTimes, [HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL)
TerminateProcess = _sig(k32.TerminateProcess, [HANDLE, wintypes.UINT], wintypes.BOOL)
CloseHandle = _sig(k32.CloseHandle, [HANDLE], wintypes.BOOL)
CreateFileW = _sig(k32.CreateFileW, [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, HANDLE], HANDLE)
GetFileInformationByHandle = _sig(k32.GetFileInformationByHandle, [HANDLE, ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)], wintypes.BOOL)
GetFileAttributesW = _sig(k32.GetFileAttributesW, [wintypes.LPCWSTR], wintypes.DWORD)
FindFirstStreamW = _sig(k32.FindFirstStreamW, [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], HANDLE)
FindNextStreamW = _sig(k32.FindNextStreamW, [HANDLE, ctypes.c_void_p], wintypes.BOOL)
FindClose = _sig(k32.FindClose, [HANDLE], wintypes.BOOL)
DeviceIoControl = _sig(k32.DeviceIoControl, [HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p], wintypes.BOOL)


def _err(tag: str):
    return RuntimeError("%s winerror=%d" % (tag, ctypes.get_last_error()))


def process_ctime(pid: int):
    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        if not GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return (c.dwHighDateTime << 32) | c.dwLowDateTime
    finally:
        CloseHandle(h)


# =====================================================================================
# Job custody (JIT)
# =====================================================================================
class WindowsJobCustody:
    native_job = True
    breakaway_allowed = False

    def __init__(self, log):
        self.log = log
        self.marks = []
        self.proc = None
        self.events = {}            # (pid, ctime) -> True; protegido por _events_lock (INT-20)
        self._events_lock = threading.Lock()
        self.exits = 0
        self.active_zero = False
        self._closed = False
        self._stop = threading.Event()
        self.job = None
        self.port = None
        self._pump = None
        self.child_created = False
        self.assigned = False
        self.resumed_threads = 0
        self.rollback = None
        self.env = {}
        # R15 (INT-09): falha parcial na construção fecha o que já foi aberto (idempotente) e
        # levanta — nenhum filho existe ainda, logo nenhum efeito.
        try:
            self.job = CreateJobObjectW(None, None)
            if not self.job:
                raise _err("CREATE_JOB_FAILED")
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not SetInformationJobObject(self.job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)):
                raise _err("SET_JOB_LIMITS_FAILED")
            self.port = CreateIoCompletionPort(INVALID_HANDLE_VALUE, None, 0, 1)
            if not self.port:
                raise _err("CREATE_IOCP_FAILED")
            assoc = JOBOBJECT_ASSOCIATE_COMPLETION_PORT(ctypes.c_void_p(1), self.port)
            if not SetInformationJobObject(self.job, JobObjectAssociateCompletionPortInformation, ctypes.byref(assoc), ctypes.sizeof(assoc)):
                raise _err("ASSOCIATE_IOCP_FAILED")
            self._pump = threading.Thread(target=self._pump_loop, name="PEGASUS_JOB_IOCP", daemon=True)
            self._pump.start()
        except BaseException:
            self._init_cleanup()
            raise

    def _init_cleanup(self):
        self._stop.set()
        for name in ("port", "job"):
            h = getattr(self, name, None)
            if h:
                CloseHandle(h)
                setattr(self, name, None)
        self._closed = True

    def mark(self, name):
        self.marks.append({"mark": name, "mono_ns": time.monotonic_ns()})

    def _add_event(self, pid, ct):
        with self._events_lock:
            if ct and (pid, 0) in self.events:
                self.events.pop((pid, 0), None)
            if not any(p == pid and c == ct for (p, c) in self.events):
                self.events[(pid, ct or 0)] = True

    def _pump_loop(self):
        msg, key, ov = wintypes.DWORD(), ctypes.c_size_t(), ctypes.c_void_p()
        while not self._stop.is_set():
            if not GetQueuedCompletionStatus(self.port, ctypes.byref(msg), ctypes.byref(key), ctypes.byref(ov), 200):
                continue
            pid = int(ov.value or 0)
            if msg.value == MSG_NEW_PROCESS:
                self._add_event(pid, process_ctime(pid) or 0)
            elif msg.value in (MSG_EXIT_PROCESS, MSG_ABNORMAL_EXIT):
                self.exits += 1
            elif msg.value == MSG_ACTIVE_PROCESS_ZERO:
                self.active_zero = True

    def _resume_threads(self, pid: int) -> int:
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snap == INVALID_HANDLE_VALUE or not snap:
            raise _err("THREAD_SNAPSHOT_FAILED")
        resumed = 0
        try:
            te = THREADENTRY32()
            te.dwSize = ctypes.sizeof(THREADENTRY32)
            ok = Thread32First(snap, ctypes.byref(te))
            while ok:
                if te.th32OwnerProcessID == pid:
                    th = OpenThread(THREAD_SUSPEND_RESUME, False, te.th32ThreadID)
                    if not th:
                        raise _err("OPEN_THREAD_FAILED")
                    try:
                        if ResumeThread(th) == 0xFFFFFFFF:
                            raise _err("RESUME_THREAD_FAILED")
                        resumed += 1
                        self.resumed_threads = resumed
                    finally:
                        CloseHandle(th)
                ok = Thread32Next(snap, ctypes.byref(te))
        finally:
            CloseHandle(snap)
        return resumed

    def _rollback_own_suspended_child(self, cause: str) -> None:
        # Único término admitido (start_failure_disposition): filho PRÓPRIO, criado SUSPENSO, com
        # zero threads retomadas — nunca executou código. Confirma a saída antes de declarar.
        ok = bool(TerminateProcess(int(self.proc._handle), 1))
        exited = False
        try:
            self.proc.wait(timeout=10)
            exited = True
        except Exception:
            exited = self.proc.poll() is not None
        self.rollback = {"cause": cause, "terminate_ok": ok, "exited": exited}
        self.log("START_ROLLBACK_OWN_SUSPENDED_CHILD_NEVER_RESUMED cause=%s terminate_ok=%s exited=%s"
                 % (cause, ok, exited))

    def start(self, argv, cwd, env, stdout_path) -> int:
        import subprocess
        from pegasus_supervisor_v008 import start_failure_disposition
        # Console próprio OCULTO: o Ctrl+C do SAFE_STOP é entregue só ao coordenador e aos seus
        # workers (que o ignoram), nunca ao supervisor nem ao PowerShell do bootstrap.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= STARTF_USESHOWWINDOW
        si.wShowWindow = SW_HIDE
        self.env = dict(env)
        fh = Path(stdout_path).open("xb")
        try:
            self.proc = subprocess.Popen(list(argv), cwd=str(cwd), env=self.env, stdout=fh, stderr=subprocess.STDOUT,
                                         creationflags=CREATE_SUSPENDED | CREATE_NEW_CONSOLE, startupinfo=si,
                                         close_fds=True)
        finally:
            fh.close()
        self.child_created = True
        self.mark("CHILD_CREATED")
        if not AssignProcessToJobObject(self.job, int(self.proc._handle)):
            code = ctypes.get_last_error()
            disp = start_failure_disposition(child_created=True, assigned=False, resumed_threads=0)
            if disp == "ROLLBACK_OWN_SUSPENDED_CHILD":
                self._rollback_own_suspended_child("ASSIGN_TO_JOB_FAILED winerror=%d" % code)
            raise RuntimeError("ASSIGN_TO_JOB_FAILED_SUSPENDED_CHILD_ROLLED_BACK winerror=%d" % code)
        self.assigned = True
        try:
            if self._resume_threads(self.proc.pid) < 1:
                raise RuntimeError("NO_THREAD_RESUMED")
        except Exception as exc:
            disp = start_failure_disposition(child_created=True, assigned=True, resumed_threads=self.resumed_threads)
            if disp == "ROLLBACK_OWN_SUSPENDED_CHILD":
                self._rollback_own_suspended_child("RESUME_FAILED %s" % exc)
            # CHILD_RUNNING_UNDER_CUSTODY: não termina; o supervisor segura a árvore (child_state).
            raise
        self.mark("CHILD_RESUMED")
        return self.proc.pid

    def child_state(self) -> dict:
        alive = None
        if self.proc is None:
            alive = False
        else:
            try:
                alive = self.proc.poll() is None
                if not alive and self.assigned:
                    alive = self.observe_tree() != "EMPTY"   # netos ainda no Job contam como vivos
            except Exception:
                alive = None
        return {"child_created": self.child_created, "assigned": self.assigned,
                "resumed_threads": self.resumed_threads, "rollback": self.rollback, "child_alive": alive,
                "pid": self.proc.pid if self.proc is not None else None}

    def sample(self):
        n = 4096
        buf = (ctypes.c_byte * (8 + 8 * n))()
        ret = wintypes.DWORD()
        if QueryInformationJobObject(self.job, JobObjectBasicProcessIdList, buf, ctypes.sizeof(buf), ctypes.byref(ret)):
            listed = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[1]
            ids = ctypes.cast(ctypes.addressof(buf) + 8, ctypes.POINTER(ctypes.c_size_t))
            for i in range(listed):
                pid = int(ids[i])
                ct = process_ctime(pid)
                if ct:
                    self._add_event(pid, ct)

    def _assert_open(self):
        # Após close() o handle do Job é fechado; consultá-lo daria ERROR_INVALID_HANDLE.
        if self._closed:
            raise RuntimeError("CUSTODY_QUERIED_AFTER_CLOSE")

    def _accounting_raw(self) -> dict:
        info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        if not QueryInformationJobObject(self.job, JobObjectBasicAccountingInformation, ctypes.byref(info), ctypes.sizeof(info), None):
            raise _err("JOB_ACCOUNTING_FAILED")
        return {"TotalProcesses": int(info.TotalProcesses), "ActiveProcesses": int(info.ActiveProcesses),
                "TotalTerminatedProcesses": int(info.TotalTerminatedProcesses)}

    def accounting(self) -> dict:
        self._assert_open()
        return self._accounting_raw()

    def poll(self):
        return None if self.proc is None else self.proc.poll()

    def observe_tree(self) -> str:
        # R15 (A01/INT-03): consulta que falha é UNKNOWN — nunca vazio. Filho não associado ao Job
        # (assign falhou) é observado pelo próprio handle do processo.
        if self._closed:
            return "UNKNOWN"
        if self.proc is None:
            return "EMPTY"
        try:
            if not self.assigned:
                return "LIVE" if self.proc.poll() is None else "EMPTY"
            return "EMPTY" if self._accounting_raw()["ActiveProcesses"] == 0 else "LIVE"
        except Exception:
            return "UNKNOWN"

    def tree_empty(self) -> bool:
        return self.observe_tree() == "EMPTY"

    def request_stop(self) -> dict:
        # Ctrl+C REAL somente no console privado do coordenador, pelo helper do próprio V003
        # (CODE/r1r11_signal.py: FreeConsole -> AttachConsole(pid) -> ignora em si -> CTRL_C).
        # R15 (A01): nonzero, timeout e falha de spawn do helper viram resultado estruturado —
        # nunca exceção que encerre a custódia.
        import subprocess
        import sys as _sys
        helper = Path(__file__).resolve().parent.parent / "CODE" / "r1r11_signal.py"
        try:
            p = subprocess.run([_sys.executable, "-I", "-B", str(helper), "--pid", str(self.proc.pid)],
                               env=self.env, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            self.log("SAFE_STOP_CTRL_C_HELPER_TIMEOUT")
            return {"delivered": False, "error": "HELPER_TIMEOUT_60S"}
        except Exception as exc:
            self.log("SAFE_STOP_CTRL_C_HELPER_SPAWN_FAILED %s" % exc)
            return {"delivered": False, "error": "HELPER_SPAWN_FAILED %s: %s" % (type(exc).__name__, exc)}
        self.log("SAFE_STOP_CTRL_C_DELIVERED_TO_CHILD_CONSOLE helper_exit=%d" % p.returncode)
        if p.returncode != 0:
            return {"delivered": False, "helper_exit": p.returncode,
                    "error": "CTRL_C_DELIVERY_FAILED helper_exit=%d stderr=%s" % (p.returncode, (p.stderr or "")[-300:])}
        return {"delivered": True, "helper_exit": 0}

    def new_process_events(self):
        with self._events_lock:
            snapshot = list(self.events)
        return [{"pid": p, "ctime": c} for (p, c) in sorted(snapshot)]

    def release_live_tree_by_owner(self) -> dict:
        # Disposição EXPLÍCITA do titular (owner_disposition_verdict). Remove KILL_ON_JOB_CLOSE ANTES;
        # só então fecha os handles (a árvore continua rodando, sem W04). Flag não removível => recusa.
        from pegasus_supervisor_v008 import owner_release_plan
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0
        cleared = bool(SetInformationJobObject(self.job, JobObjectExtendedLimitInformation,
                                               ctypes.byref(info), ctypes.sizeof(info)))
        plan = owner_release_plan(kill_on_close_cleared=cleared)
        if not plan["release"]:
            self.log("OWNER_RELEASE_REFUSED KILL_ON_JOB_CLOSE_NOT_CLEARABLE winerror=%d HOLD_CONTINUES" % ctypes.get_last_error())
            return {"released": False, "kill_on_close_cleared": False, "plan": plan, "reason": plan["reason"]}
        self._stop.set()
        if self._pump is not None:
            self._pump.join(2)
        self._closed = True
        CloseHandle(self.port)
        CloseHandle(self.job)
        self.log("OWNER_RELEASE_APPLIED KILL_ON_JOB_CLOSE_CLEARED JOB_HANDLES_CLOSED TREE_LEFT_RUNNING_NO_KILL")
        return {"released": True, "kill_on_close_cleared": True, "plan": plan}

    def close(self) -> dict:
        # N2 (R16): close() devolve PROVA ESTRUTURADA do desfecho; o supervisor nunca declara
        # CUSTODIAN_CLOSED sem closed=True + active_processes=0. Retorno None jamais é prova.
        if self._closed:
            return {"closed": True, "handles_closed": True, "active_processes": 0, "reason": "ALREADY_CLOSED"}
        self._stop.set()
        if self._pump is not None:
            self._pump.join(2)
        # O supervisor só chama close() com a árvore VERIFICADA vazia (R15). Defesa: se ainda assim
        # houver árvore viva (ou a consulta falhar), o handle NÃO é fechado (fechar acionaria o
        # KILL_ON_JOB_CLOSE): job_close_plan decide antes de qualquer CloseHandle.
        from pegasus_supervisor_v008 import job_close_plan
        try:
            active = self._accounting_raw()["ActiveProcesses"]
        except Exception as exc:
            self.close_disposition = {"close_handles": False, "reason": "ACCOUNTING_FAILED %s" % exc}
            self.live_tree_at_close = True
            self.log("JOB_CLOSE_REFUSED_ACCOUNTING_FAILED_HANDLES_RETAINED %s" % exc)
            return {"closed": False, "handles_closed": False, "active_processes": None,
                    "reason": "ACCOUNTING_FAILED_HANDLES_RETAINED:%s" % type(exc).__name__}
        plan = job_close_plan(active, False)
        self.close_disposition = plan
        self.live_tree_at_close = active > 0
        if not plan["close_handles"]:
            self.log("JOB_LIVE_TREE_CUSTODY_RETAINED_NO_CLOSE active=%d (supervisor nao fecha nem mata)" % active)
            return {"closed": False, "handles_closed": False, "active_processes": int(active),
                    "reason": "LIVE_TREE_HANDLES_RETAINED_NO_KILL"}
        self._closed = True
        CloseHandle(self.port)
        CloseHandle(self.job)
        return {"closed": True, "handles_closed": True, "active_processes": 0,
                "reason": "TREE_EMPTY_JOB_HANDLES_CLOSED"}


# =====================================================================================
# W04 nativo: lease + diretórios + USN + identidade + census
# =====================================================================================
def _open(path: str, access: int, share: int, flags: int):
    h = CreateFileW(path, access, share, None, OPEN_EXISTING, flags, None)
    if h == INVALID_HANDLE_VALUE or not h:
        return None, ctypes.get_last_error()
    return h, 0


def _info(h):
    bi = BY_HANDLE_FILE_INFORMATION()
    if not GetFileInformationByHandle(h, ctypes.byref(bi)):
        raise _err("GET_FILE_INFORMATION_FAILED")
    return {"vol": int(bi.dwVolumeSerialNumber), "frn": (int(bi.nFileIndexHigh) << 32) | int(bi.nFileIndexLow),
            "links": int(bi.nNumberOfLinks), "attrs": int(bi.dwFileAttributes)}


def _named_streams(path: str):
    data = WIN32_FIND_STREAM_DATA()
    h = FindFirstStreamW(path, 0, ctypes.byref(data), 0)
    if h == INVALID_HANDLE_VALUE or not h:
        return []
    out = []
    try:
        while True:
            name = data.cStreamName
            if name and name != "::$DATA":
                out.append(name)
            if not FindNextStreamW(h, ctypes.byref(data)):
                break
    finally:
        FindClose(h)
    return out


class W04NativeLease:
    def __init__(self, root: Path, log):
        self.root = Path(root).resolve()
        self.log = log
        self.files = {}     # path -> (handle, info)
        self.dirs = {}
        self.violations, self.errors, self.reval_fail = [], [], []
        self.reparse, self.id_changes, self.link_changes = [], [], []
        self.volume = None
        self.usn_start = None
        self.census_start = None

    # ---- USN
    def _volume_handle(self):
        drive = str(self.root)[:2]
        h, e = _open("\\\\.\\" + drive, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, 0)
        if not h:
            raise RuntimeError("VOLUME_OPEN_FAILED_ELEVATION_REQUIRED winerror=%d" % e)
        return h

    def _query_usn(self):
        jd, ret = USN_JOURNAL_DATA_V0(), wintypes.DWORD()
        if not DeviceIoControl(self.volume, FSCTL_QUERY_USN_JOURNAL, None, 0, ctypes.byref(jd), ctypes.sizeof(jd), ctypes.byref(ret), None):
            code = ctypes.get_last_error()
            raise RuntimeError("USN_JOURNAL_NOT_ACTIVE" if code == ERROR_JOURNAL_NOT_ACTIVE else "USN_QUERY_FAILED winerror=%d" % code)
        return {"journal_id": int(jd.UsnJournalID), "first_usn": int(jd.FirstUsn), "next_usn": int(jd.NextUsn)}

    def _read_usn(self, start_usn: int, end_usn: int, journal_id: int, frns: set, dir_frns: set) -> dict:
        # R15 (A02): adaptador fino. Só traduz DeviceIoControl em páginas; a decisão de cobertura
        # (cursor progressivo, EOF antes do fim, registros malformados, FRN 128) é da função pura
        # usn_scan_coverage, qualificada offline. Nunca levanta: falha => cobertura incompleta.
        from pegasus_supervisor_v008 import usn_scan_coverage
        buf = ctypes.create_string_buffer(1 << 16)

        def read_page(cursor):
            rq = READ_USN_JOURNAL_DATA_V0(cursor, 0xFFFFFFFF, 0, 0, 0, journal_id)
            ret = wintypes.DWORD()
            if not DeviceIoControl(self.volume, FSCTL_READ_USN_JOURNAL, ctypes.byref(rq), ctypes.sizeof(rq),
                                   buf, len(buf), ctypes.byref(ret), None):
                return False, ctypes.get_last_error(), b""
            return True, 0, buf.raw[:ret.value]

        return usn_scan_coverage(read_page, start_usn, end_usn, frns, dir_frns)

    # ---- census (corroboração)
    def _census(self):
        import native_handle_backend_v001 as nhb
        nhb.enable_se_debug_privilege()
        # Truncamento é intermitente: consultas de nome que travam são abandonadas e, acima de
        # 8 por chamada, a enumeração vem truncada (contador por chamada). Nova tentativa
        # limitada; se TODAS truncarem, o resultado segue truncado e o W04 bloqueia
        # (fail-closed inalterado). Corroboração apenas; a prova primária é a lease do kernel.
        attempts = 0
        for attempts in range(1, CENSUS_MAX_ATTEMPTS + 1):
            enum = nhb.enumerate_file_handle_observations()
            if not enum["enumeration_truncated"]:
                break
        me = (os.getpid(), process_ctime(os.getpid()))
        owned = {me}
        root = str(self.root)
        ext_writers, ext_readers, unresolved = [], 0, 0
        for o in enum["observations"]:
            if o.get("name_status") == "VERIFIED_NONDISK_FILETYPE":
                continue
            if o.get("name_status") != "RESOLVED":
                unresolved += 1
                continue
            if nhb.path_under_targets(o.get("resolved_path") or "", [root]) is None:
                continue
            ident = (o.get("owner_pid"), o.get("owner_creation_filetime"))
            if ident in owned:
                continue
            if int(o.get("granted_access") or 0) & WRITE_ACCESS_BITS:
                ext_writers.append({"pid": ident[0], "ctime": ident[1], "path": o.get("resolved_path")})
            else:
                ext_readers += 1
        return {"truncated": bool(enum["enumeration_truncated"]), "external_writers_under_target": ext_writers,
                "external_readers_under_target": ext_readers, "unresolved": unresolved, "stats": enum.get("stats"),
                "attempts": attempts}

    # ---- ciclo
    def arm(self) -> dict:
        for part in [self.root, *self.root.parents]:
            a = GetFileAttributesW(str(part))
            if a == INVALID_FILE_ATTRIBUTES or a & FILE_ATTRIBUTE_REPARSE_POINT:
                if str(part) != part.anchor:
                    self.reparse.append(str(part))
        self.volume = self._volume_handle()
        self.usn_start = self._query_usn()
        targets = sorted(p for p in self.root.rglob("*"))
        for d in [self.root] + [p for p in targets if p.is_dir()]:
            h, e = _open(str(d), FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE,
                         FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
            if not h:
                self.errors.append({"path": str(d), "winerror": e})
                continue
            info = _info(h)
            if info["attrs"] & FILE_ATTRIBUTE_REPARSE_POINT:
                self.reparse.append(str(d))
            self.dirs[str(d)] = (h, info)
        for f in [p for p in targets if p.is_file()]:
            names = [str(f)] + [str(f) + s for s in _named_streams(str(f))]
            for n in names:
                h, e = _open(n, GENERIC_READ, FILE_SHARE_READ, FILE_FLAG_OPEN_REPARSE_POINT)
                if not h:
                    (self.violations if e == ERROR_SHARING_VIOLATION else self.errors).append({"path": n, "winerror": e})
                    continue
                info = _info(h)
                if info["attrs"] & FILE_ATTRIBUTE_REPARSE_POINT:
                    self.reparse.append(n)
                self.files[n] = (h, info)
        self.census_start = self._census()
        self.log("W04_ARMED files=%d dirs=%d violations=%d errors=%d usn_start=%d"
                 % (len(self.files), len(self.dirs), len(self.violations), len(self.errors), self.usn_start["next_usn"]))
        return {"armed": "NATIVE_LEASE_DIRS_USN", "files": len(self.files), "dirs": len(self.dirs),
                "usn_journal_id": self.usn_start["journal_id"], "usn_start": self.usn_start["next_usn"]}

    def prespawn_state(self) -> dict:
        # F02: estado de aquisição efetiva da lease, consultado ANTES do spawn. census_start é
        # corroboração (tratado no disarm/subprocesso), exposto mas não decisivo para o spawn.
        return {"sharing_violations": list(self.violations), "open_errors": list(self.errors),
                "reparse": list(self.reparse), "files": len(self.files), "dirs": len(self.dirs),
                "census_truncated": bool((self.census_start or {}).get("truncated"))}

    def release(self) -> None:
        # Libera todos os handles parciais adquiridos (lease + diretórios + volume) sem tocar no
        # conteúdo protegido. Chamado quando o pré-spawn bloqueia: nenhum filho foi criado.
        for (h, _i) in list(self.files.values()) + list(self.dirs.values()):
            try:
                CloseHandle(h)
            except Exception:
                pass
        self.files.clear()
        self.dirs.clear()
        if self.volume:
            try:
                CloseHandle(self.volume)
            except Exception:
                pass
            self.volume = None

    def revalidate(self) -> None:
        for n, (h, info) in list(self.files.items()) + list(self.dirs.items()):
            try:
                now = _info(h)
            except Exception as exc:  # R15 (INT-04): toda falha de verificação vira lacuna W04
                self.reval_fail.append({"path": n, "error": "%s: %s" % (type(exc).__name__, exc)})
                continue
            if now["frn"] != info["frn"] or now["vol"] != info["vol"]:
                self.id_changes.append(n)
            if now["links"] != info["links"]:
                self.link_changes.append(n)

    def disarm(self, tree_empty: bool) -> dict:
        # R15 (INT-05/INT-22): o desarme nunca levanta. Cada falha (consulta/leitura USN, census,
        # contagem) vira causa registrada e o veredito W04 resulta BLOCKED — nunca PASS por omissão.
        disarm_errors = []
        self.revalidate()
        try:
            end = self._query_usn()
        except Exception as exc:
            end = {"journal_id": None, "first_usn": None, "next_usn": None}
            disarm_errors.append("USN_QUERY_FAILED:%s" % exc)
        frns = {i["frn"] for (_h, i) in self.files.values()}
        dfrns = {i["frn"] for (_h, i) in self.dirs.values()}
        if end["next_usn"] is not None:
            cov = self._read_usn(self.usn_start["next_usn"], end["next_usn"], self.usn_start["journal_id"], frns, dfrns)
        else:
            cov = {"read_complete": False, "reason": "USN_END_UNAVAILABLE", "start_usn": self.usn_start["next_usn"],
                   "end_usn": None, "covered_to": None, "pages": 0, "records_parsed": 0, "hits": []}
        hits, complete = cov["hits"], cov["read_complete"]
        try:
            census_end = self._census()
        except Exception as exc:
            census_end = {"truncated": True, "external_writers_under_target": [], "unresolved": 0,
                          "stats": None, "attempts": None}
            disarm_errors.append("CENSUS_FAILED:%s" % exc)
        try:
            n_files = sum(1 for p in self.root.rglob("*") if p.is_file())
        except Exception as exc:
            n_files = None
            disarm_errors.append("FILE_COUNT_FAILED:%s" % exc)
        if disarm_errors:
            self.reval_fail.extend({"path": "<disarm>", "error": e} for e in disarm_errors)
        rep = {
            "lease": {"targets": len(self.files) + len(self.violations) + len([e for e in self.errors if not Path(e["path"]).is_dir()]),
                      "acquired": len(self.files), "sharing_violations": self.violations,
                      "errors": [e for e in self.errors if not Path(e["path"]).is_dir()],
                      "held_until_tree_empty": bool(tree_empty), "revalidation_failures": self.reval_fail,
                      "files_on_disk_at_disarm": n_files},
            "dirs": {"targets": len(self.dirs) + len([e for e in self.errors if Path(e["path"]).is_dir()]),
                     "acquired": len(self.dirs), "errors": [e for e in self.errors if Path(e["path"]).is_dir()],
                     "held_until_tree_empty": bool(tree_empty)},
            "usn": {"journal_id_start": self.usn_start["journal_id"], "journal_id_end": end["journal_id"],
                    "first_usn_end": end["first_usn"], "start_usn": self.usn_start["next_usn"],
                    "end_usn": end["next_usn"], "read_complete": complete, "records_on_protected": hits,
                    "coverage": {k: v for k, v in cov.items() if k != "hits"}},
            "identity": {"reparse_points": self.reparse, "id_changes": self.id_changes, "sha_mismatch": [],
                         "link_count_changes": self.link_changes},
            "census": {"truncated": self.census_start["truncated"] or census_end["truncated"],
                       "external_writers_under_target": self.census_start["external_writers_under_target"]
                       + census_end["external_writers_under_target"],
                       "unresolved": max(self.census_start["unresolved"], census_end["unresolved"]),
                       "stats_start": self.census_start["stats"], "stats_end": census_end["stats"],
                       "attempts": [self.census_start.get("attempts"), census_end.get("attempts")]},
        }
        self.release()
        self.log("W04_DISARMED usn_hits=%d read_complete=%s reason=%s errors=%d"
                 % (len(hits), complete, cov.get("reason"), len(disarm_errors)))
        return rep
