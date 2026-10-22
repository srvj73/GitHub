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
        self.events = {}            # (pid, ctime) -> True
        self.exits = 0
        self.active_zero = False
        self._stop = threading.Event()
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

    def mark(self, name):
        self.marks.append({"mark": name, "mono_ns": time.monotonic_ns()})

    def _pump_loop(self):
        msg, key, ov = wintypes.DWORD(), ctypes.c_size_t(), ctypes.c_void_p()
        while not self._stop.is_set():
            if not GetQueuedCompletionStatus(self.port, ctypes.byref(msg), ctypes.byref(key), ctypes.byref(ov), 200):
                continue
            pid = int(ov.value or 0)
            if msg.value == MSG_NEW_PROCESS:
                self.events[(pid, process_ctime(pid) or 0)] = True
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
                    finally:
                        CloseHandle(th)
                ok = Thread32Next(snap, ctypes.byref(te))
        finally:
            CloseHandle(snap)
        return resumed

    def start(self, argv, cwd, env, stdout_path) -> int:
        import subprocess
        fh = Path(stdout_path).open("xb")
        self.mark("CHILD_CREATED")
        # Console próprio OCULTO: o Ctrl+C do SAFE_STOP é entregue só ao coordenador e aos seus
        # workers (que o ignoram), nunca ao supervisor nem ao PowerShell do bootstrap.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= STARTF_USESHOWWINDOW
        si.wShowWindow = SW_HIDE
        self.env = dict(env)
        self.proc = subprocess.Popen(list(argv), cwd=str(cwd), env=self.env, stdout=fh, stderr=subprocess.STDOUT,
                                     creationflags=CREATE_SUSPENDED | CREATE_NEW_CONSOLE, startupinfo=si,
                                     close_fds=True)
        fh.close()
        if not AssignProcessToJobObject(self.job, int(self.proc._handle)):
            code = ctypes.get_last_error()
            # Filho próprio, SUSPENSO, que nunca executou código: abortado antes do Resume.
            TerminateProcess(int(self.proc._handle), 1)
            raise RuntimeError("ASSIGN_TO_JOB_FAILED_SUSPENDED_CHILD_ABORTED winerror=%d" % code)
        if self._resume_threads(self.proc.pid) < 1:
            raise RuntimeError("NO_THREAD_RESUMED")
        self.mark("CHILD_RESUMED")
        return self.proc.pid

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
                if ct and not any(p == pid and c == ct for (p, c) in self.events):
                    # Mesma identidade vista antes sem ctime: substitui o registro incompleto.
                    self.events.pop((pid, 0), None)
                    self.events[(pid, ct)] = True

    def accounting(self) -> dict:
        info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        if not QueryInformationJobObject(self.job, JobObjectBasicAccountingInformation, ctypes.byref(info), ctypes.sizeof(info), None):
            raise _err("JOB_ACCOUNTING_FAILED")
        return {"TotalProcesses": int(info.TotalProcesses), "ActiveProcesses": int(info.ActiveProcesses),
                "TotalTerminatedProcesses": int(info.TotalTerminatedProcesses)}

    def poll(self):
        return None if self.proc is None else self.proc.poll()

    def tree_empty(self) -> bool:
        return self.accounting()["ActiveProcesses"] == 0

    def request_stop(self):
        # Ctrl+C REAL somente no console privado do coordenador, pelo helper do próprio V003
        # (CODE/r1r11_signal.py: FreeConsole -> AttachConsole(pid) -> ignora em si -> CTRL_C).
        # O coordenador fecha a admissão na fronteira de commit; workers ignoram SIGINT.
        import subprocess
        helper = Path(__file__).resolve().parent.parent / "CODE" / "r1r11_signal.py"
        import sys as _sys
        rc = subprocess.run([_sys.executable, "-I", "-B", str(helper), "--pid", str(self.proc.pid)],
                            env=self.env, capture_output=True, text=True, timeout=60).returncode
        self.log("SAFE_STOP_CTRL_C_DELIVERED_TO_CHILD_CONSOLE helper_exit=%d" % rc)
        if rc != 0:
            raise RuntimeError("CTRL_C_DELIVERY_FAILED helper_exit=%d" % rc)

    def new_process_events(self):
        return [{"pid": p, "ctime": c} for (p, c) in sorted(self.events)]

    def close(self):
        self._stop.set()
        self._pump.join(2)
        if self.tree_empty():
            CloseHandle(self.port)
            CloseHandle(self.job)
        else:
            # Handle retido: a árvore própria continua sob o Job até o supervisor terminar.
            self.log("JOB_HANDLE_RETAINED_LIVE_OWNED_TREE_RECONCILE_REQUIRED")


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

    def _read_usn(self, start_usn: int, end_usn: int, journal_id: int, frns: set, dir_frns: set):
        hits, complete = [], False
        buf = ctypes.create_string_buffer(1 << 16)
        cur = start_usn
        while cur < end_usn:
            rq = READ_USN_JOURNAL_DATA_V0(cur, 0xFFFFFFFF, 0, 0, 0, journal_id)
            ret = wintypes.DWORD()
            if not DeviceIoControl(self.volume, FSCTL_READ_USN_JOURNAL, ctypes.byref(rq), ctypes.sizeof(rq), buf, len(buf), ctypes.byref(ret), None):
                if ctypes.get_last_error() == ERROR_HANDLE_EOF:
                    complete = True
                    break
                raise _err("USN_READ_FAILED")
            raw = buf.raw[:ret.value]
            nxt = int.from_bytes(raw[:8], "little", signed=True)
            off = 8
            while off + 60 <= len(raw):
                rl = int.from_bytes(raw[off:off + 4], "little")
                major = int.from_bytes(raw[off + 4:off + 6], "little")
                if rl == 0:
                    break
                if major == 2:
                    frn = int.from_bytes(raw[off + 8:off + 16], "little")
                    par = int.from_bytes(raw[off + 16:off + 24], "little")
                    usn = int.from_bytes(raw[off + 24:off + 32], "little", signed=True)
                    reason = int.from_bytes(raw[off + 40:off + 44], "little")
                    nl, no = (int.from_bytes(raw[off + 56:off + 58], "little"), int.from_bytes(raw[off + 58:off + 60], "little"))
                else:  # USN_RECORD_V3 (FRN 128 bits; NTFS usa os 64 bits baixos)
                    frn = int.from_bytes(raw[off + 8:off + 16], "little")
                    par = int.from_bytes(raw[off + 24:off + 32], "little")
                    usn = int.from_bytes(raw[off + 40:off + 48], "little", signed=True)
                    reason = int.from_bytes(raw[off + 56:off + 60], "little")
                    nl, no = (int.from_bytes(raw[off + 72:off + 74], "little"), int.from_bytes(raw[off + 74:off + 76], "little"))
                if usn >= end_usn:
                    complete = True
                    break
                if frn in frns or frn in dir_frns or par in dir_frns:
                    name = raw[off + no:off + no + nl].decode("utf-16-le", "replace")
                    hits.append({"usn": usn, "frn": frn, "parent_frn": par, "reason": reason, "name": name})
                off += rl
            if nxt <= cur:
                complete = True
                break
            cur = nxt
        if cur >= end_usn:
            complete = True
        return hits, complete

    # ---- census (corroboração)
    def _census(self):
        import native_handle_backend_v001 as nhb
        nhb.enable_se_debug_privilege()
        enum = nhb.enumerate_file_handle_observations()
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
                "external_readers_under_target": ext_readers, "unresolved": unresolved, "stats": enum.get("stats")}

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

    def revalidate(self) -> None:
        for n, (h, info) in list(self.files.items()) + list(self.dirs.items()):
            try:
                now = _info(h)
            except RuntimeError as exc:
                self.reval_fail.append({"path": n, "error": str(exc)})
                continue
            if now["frn"] != info["frn"] or now["vol"] != info["vol"]:
                self.id_changes.append(n)
            if now["links"] != info["links"]:
                self.link_changes.append(n)

    def disarm(self, tree_empty: bool) -> dict:
        self.revalidate()
        end = self._query_usn()
        frns = {i["frn"] for (_h, i) in self.files.values()}
        dfrns = {i["frn"] for (_h, i) in self.dirs.values()}
        hits, complete = self._read_usn(self.usn_start["next_usn"], end["next_usn"], self.usn_start["journal_id"], frns, dfrns)
        census_end = self._census()
        n_files = sum(1 for p in self.root.rglob("*") if p.is_file())
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
                    "end_usn": end["next_usn"], "read_complete": complete, "records_on_protected": hits},
            "identity": {"reparse_points": self.reparse, "id_changes": self.id_changes, "sha_mismatch": [],
                         "link_count_changes": self.link_changes},
            "census": {"truncated": self.census_start["truncated"] or census_end["truncated"],
                       "external_writers_under_target": self.census_start["external_writers_under_target"]
                       + census_end["external_writers_under_target"],
                       "unresolved": max(self.census_start["unresolved"], census_end["unresolved"]),
                       "stats_start": self.census_start["stats"], "stats_end": census_end["stats"]},
        }
        for h, _i in list(self.files.values()) + list(self.dirs.values()):
            CloseHandle(h)
        CloseHandle(self.volume)
        self.log("W04_DISARMED usn_hits=%d read_complete=%s" % (len(hits), complete))
        return rep
