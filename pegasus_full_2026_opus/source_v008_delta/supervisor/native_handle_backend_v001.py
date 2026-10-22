"""PEGASUS W04 — Native handle/writer ownership backend (V001).

Objetivo (defensivo, integridade de dados): antes do filho QS4 escrever nos
caminhos-alvo (W04), provar NATIVAMENTE que nenhum ESCRITOR externo mantem handle
sob esses caminhos, identificando cada dono por (PID, creation_time). Isto previne
multiplos escritores, corrupcao e TOCTOU. NAO injeta, NAO encerra processo algum
(o PID reutilizado 38640 e qualquer outro JAMAIS sao mortos) — apenas observa e,
em qualquer lacuna, recusa a atestacao (fail-closed).

Este modulo tem DUAS camadas:

  1) NUCLEO DE DECISAO (puro, multiplataforma, testavel em qualquer SO):
       - normalize_path / path_under_targets
       - classify_observation
       - decide_coverage   <-- a regra fail-closed que emite (ou nega) a atestacao

  2) CAMADA NATIVA (somente Windows, os.name == 'nt'):
       - enable_se_debug_privilege
       - enumerate_file_handle_observations  (NtQuerySystemInformation + NtQueryObject)
       - qualified_native_probe              <-- a callable que o gate selado consome

O gate selado (native_admission_gate_v001.plan) aceita `native_probe=`; o driver
irmao injeta `qualified_native_probe` por esse seam, SEM alterar o arquivo selado.
A atestacao só e emitida quando:
   * a enumeracao foi completa (nao truncada);
   * TODO handle de arquivo foi definitivamente classificado (nome resolvido);
   * TODO dono sob caminho-alvo foi identificado por (PID, creation_time);
   * nenhum PID reutilizado sob alvo; nenhum ACCESS_DENIED/UNKNOWN sob alvo.
Caso contrario: BackendBlocked com motivo preciso.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Mapping, Optional

ATTESTATION = "ATTESTED_BY_QUALIFIED_WINDOWS_BACKEND"


class BackendBlocked(Exception):
    """Lacuna de cobertura ou condicao nao provada: fail-closed."""


# ===========================================================================
# 1) NUCLEO DE DECISAO — puro, sem dependencia de Windows (testavel aqui)
# ===========================================================================

def normalize_path(p: str) -> str:
    """Normaliza para comparacao: separadores, caixa (Windows), sem barra final."""
    if p is None:
        return ""
    s = str(p).replace("/", "\\")
    # colapsa barras repetidas sem destruir prefixo UNC (\\server\share)
    unc = s.startswith("\\\\")
    while "\\\\" in (s[2:] if unc else s):
        head = s[:2] if unc else ""
        tail = (s[2:] if unc else s).replace("\\\\", "\\")
        s = head + tail
    s = s.rstrip("\\")
    return s.casefold()


def path_under_targets(path: str, targets: Iterable[str]) -> Optional[str]:
    """Retorna o alvo que cobre `path` (o proprio arquivo ou um diretorio pai), ou None."""
    np = normalize_path(path)
    if not np:
        return None
    for t in targets:
        nt = normalize_path(t)
        if not nt:
            continue
        if np == nt:
            return t
        if np.startswith(nt + "\\"):
            return t
    return None


def identity_of(pid: Optional[int], creation_filetime: Optional[int]) -> Optional[tuple]:
    if pid is None or creation_filetime is None:
        return None
    return (int(pid), int(creation_filetime))


def classify_observation(
    obs: Mapping[str, Any],
    targets: Iterable[str],
    attempt_owned: Iterable[tuple],
    expected_identities: Mapping[int, int],
    strict_hangmask: bool = True,
) -> dict:
    """Classifica UMA observacao de handle.

    obs esperado:
        handle_id:int, owner_pid:int,
        name_status: 'RESOLVED'|'UNRESOLVED'|'SKIPPED_HANGMASK',
        resolved_path: str|None,
        owner_status: 'IDENTIFIED'|'ACCESS_DENIED'|'UNKNOWN',
        owner_creation_filetime: int|None, granted_access: int|None

    strict_hangmask=True (padrao, fail-closed): handle com a mascara de hang
    (0x0012019F, caracteristica de named pipe sincrono) cujo nome foi PULADO
    para nao travar a thread nativa e tratado como lacuna (BLOCK). Com
    strict_hangmask=False aplica-se a heuristica DOCUMENTADA de que tal handle
    e um objeto nao-disco (pipe) e, portanto, nunca esta sob um caminho-alvo.

    Retorna {'class': 'OWNED'|'EXTERNAL'|'IRRELEVANT'|'BLOCK', 'block': str|None, 'detail': {...}}
    """
    owned = set(tuple(x) for x in attempt_owned)
    pid = obs.get("owner_pid")
    name_status = obs.get("name_status")
    owner_status = obs.get("owner_status")
    hid = obs.get("handle_id")

    # Deteccao de reuso de PID (sob qualquer handle de arquivo cujo dono afirmamos conhecer):
    exp = expected_identities.get(int(pid)) if (pid is not None and int(pid) in expected_identities) else None
    if exp is not None and owner_status == "IDENTIFIED":
        ct = obs.get("owner_creation_filetime")
        if ct is not None and int(ct) != int(exp):
            return {"class": "BLOCK", "block": "PID_REUSE_DETECTED pid=%s" % pid,
                    "detail": {"pid": pid, "expected_ctime": exp, "observed_ctime": int(ct)}}

    # Handle cujo nome foi pulado pela mascara de hang (named pipe sincrono).
    if name_status == "SKIPPED_HANGMASK":
        if strict_hangmask:
            return {"class": "BLOCK", "block": "HANDLE_HANGMASK_UNRESOLVED pid=%s handle=%s" % (pid, hid),
                    "detail": {"pid": pid, "handle_id": hid, "granted_access": obs.get("granted_access")}}
        return {"class": "IRRELEVANT", "block": None,
                "detail": {"pid": pid, "handle_id": hid, "presumed": "NON_DISK_PIPE"}}

    # Prova nativa explicita: GetFileType determinou PIPE ou CHAR em um
    # handle DUPLICADO. Isto NAO e a antiga heuristica pela access-mask.
    if name_status == "VERIFIED_NONDISK_FILETYPE":
        if obs.get("file_type") in (_FILE_TYPE_CHAR, _FILE_TYPE_PIPE) and obs.get("file_type_source") == "WIN32_GETFILETYPE":
            return {"class": "IRRELEVANT", "block": None,
                    "detail": {"pid": pid, "handle_id": hid, "file_type": obs.get("file_type"),
                               "evidence": "WIN32_GETFILETYPE_NONDISK"}}
        return {"class": "BLOCK", "block": "FILE_TYPE_ATTESTATION_INVALID pid=%s handle=%s" % (pid, hid),
                "detail": {"pid": pid, "handle_id": hid}}

    # Nome nao resolvido => nao podemos provar que NAO e um escritor sob alvo => fail-closed.
    if name_status != "RESOLVED":
        return {"class": "BLOCK", "block": "HANDLE_NAME_UNRESOLVED pid=%s handle=%s" % (pid, hid),
                "detail": {"pid": pid, "handle_id": hid}}

    cover = path_under_targets(obs.get("resolved_path") or "", targets)
    if cover is None:
        return {"class": "IRRELEVANT", "block": None, "detail": {"pid": pid, "handle_id": hid}}

    # Handle SOB alvo: o dono precisa estar plenamente identificado.
    if owner_status == "ACCESS_DENIED":
        return {"class": "BLOCK", "block": "OWNER_ACCESS_DENIED pid=%s under=%s" % (pid, cover),
                "detail": {"pid": pid, "target": cover}}
    if owner_status != "IDENTIFIED":
        return {"class": "BLOCK", "block": "OWNER_UNKNOWN pid=%s under=%s" % (pid, cover),
                "detail": {"pid": pid, "target": cover}}

    ident = identity_of(pid, obs.get("owner_creation_filetime"))
    if ident is None:
        return {"class": "BLOCK", "block": "OWNER_IDENTITY_INCOMPLETE pid=%s" % pid,
                "detail": {"pid": pid}}

    if ident in owned:
        return {"class": "OWNED", "block": None,
                "detail": {"identity": ident, "target": cover, "handle_id": hid}}
    return {"class": "EXTERNAL", "block": None,
            "detail": {"identity": ident, "target": cover, "handle_id": hid}}


def decide_coverage(
    *,
    attempt_id: str,
    targets: list,
    observations: Iterable[Mapping[str, Any]],
    attempt_owned: Iterable[tuple],
    expected_identities: Optional[Mapping[int, int]] = None,
    enumeration_truncated: bool,
    strict_hangmask: bool = True,
) -> dict:
    """Regra fail-closed. Emite a atestacao APENAS sem lacunas; senao BackendBlocked."""
    expected_identities = dict(expected_identities or {})
    if not targets or len(set(normalize_path(p) for p in targets)) != len(targets):
        raise BackendBlocked("W04_EXACT_TARGET_FILE_SET_REQUIRED")
    if enumeration_truncated:
        raise BackendBlocked("HANDLE_ENUMERATION_TRUNCATED")

    external = []
    owned_hits = []
    blocks = []
    for obs in observations:
        r = classify_observation(obs, targets, attempt_owned, expected_identities,
                                 strict_hangmask=strict_hangmask)
        if r["class"] == "BLOCK":
            blocks.append(r["block"])
        elif r["class"] == "EXTERNAL":
            external.append(r["detail"])
        elif r["class"] == "OWNED":
            owned_hits.append(r["detail"])

    if blocks:
        # Fail-closed: expõe o primeiro motivo preciso e o total de lacunas.
        raise BackendBlocked("W04_HANDLE_COVERAGE_INCOMPLETE %d gap(s); first=%s"
                             % (len(blocks), blocks[0]))

    registered_users = len(external)
    return {
        "attempt_id": attempt_id,
        "result": "PASS_QUALIFIED_NATIVE_BACKEND",
        "targets": list(targets),
        "registered_users": registered_users,
        "full_handle_coverage": ATTESTATION,
        "coverage": {
            "owned_handles_under_target": len(owned_hits),
            "external_writers_under_target": registered_users,
            "external_detail": external,
            "enumeration_truncated": False,
        },
    }


# ===========================================================================
# 2) CAMADA NATIVA — somente Windows (os.name == 'nt')
# ===========================================================================

_SYSTEM_EXTENDED_HANDLE_INFORMATION = 0x40
_OBJECT_NAME_INFORMATION = 1
_OBJECT_TYPE_INFORMATION = 2
_STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_DUP_HANDLE = 0x0040
_DUPLICATE_SAME_ACCESS = 0x00000002


def enable_se_debug_privilege() -> bool:
    """Habilita SeDebugPrivilege para abrir/duplicar handles de outros processos.
    Retorna True se habilitado; False se nao foi possivel (backend seguira fail-closed)."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class LUID(ctypes.Structure):
        _fields_ = [("Low", wintypes.DWORD), ("High", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("Count", wintypes.DWORD), ("Privilege", LUID_AND_ATTRIBUTES * 1)]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    TOKEN_ADJUST_PRIVILEGES = 0x0020
    TOKEN_QUERY = 0x0008
    SE_PRIVILEGE_ENABLED = 0x00000002
    hTok = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(),
                                   TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, ctypes.byref(hTok)):
        return False
    try:
        luid = LUID()
        if not advapi.LookupPrivilegeValueW(None, "SeDebugPrivilege", ctypes.byref(luid)):
            return False
        tp = TOKEN_PRIVILEGES()
        tp.Count = 1
        tp.Privilege[0].Luid = luid
        tp.Privilege[0].Attributes = SE_PRIVILEGE_ENABLED
        if not advapi.AdjustTokenPrivileges(hTok, False, ctypes.byref(tp), 0, None, None):
            return False
        return ctypes.get_last_error() == 0
    finally:
        kernel.CloseHandle(hTok)


def _build_dos_device_map():
    """Mapa \\Device\\HarddiskVolumeN -> 'X:' para traduzir nomes NT em letras."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    QueryDosDeviceW = kernel.QueryDosDeviceW
    QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    QueryDosDeviceW.restype = wintypes.DWORD
    GetLogicalDriveStringsW = kernel.GetLogicalDriveStringsW
    buf = ctypes.create_unicode_buffer(1024)
    n = GetLogicalDriveStringsW(len(buf), buf)
    drives = [d for d in buf[:n].split("\x00") if d]
    mapping = {}
    for d in drives:
        letter = d.rstrip("\\")  # 'C:'
        target = ctypes.create_unicode_buffer(1024)
        if QueryDosDeviceW(letter, target, len(target)):
            mapping[target.value] = letter
    return mapping


def _nt_name_to_dos(nt_name: str, dos_map: Mapping[str, str]) -> Optional[str]:
    if not nt_name:
        return None
    for dev, letter in dos_map.items():
        if nt_name.startswith(dev + "\\"):
            return letter + nt_name[len(dev):]
        if nt_name == dev:
            return letter
    return None  # nomes fora de volumes de disco (ex.: \Device\NamedPipe\...) nao sao alvo


_HANGMASK = 0x0012019F               # GrantedAccess caracteristico de named pipe sincrono (trava NtQueryObject)
_MAX_ABANDONED_NAME_WORKERS = 8      # teto de threads abandonadas antes de declarar enumeracao incompleta

# Win32 GetFileType: only DISK requires an object-name query. FILE_TYPE_UNKNOWN
# may mean an error OR an unusual object: both remain unresolved (fail-closed).
_FILE_TYPE_DISK = 1
_FILE_TYPE_CHAR = 2
_FILE_TYPE_PIPE = 3

def _file_type_disposition(file_type: int) -> str:
    if file_type == _FILE_TYPE_DISK:
        return "DISK_QUERY_REQUIRED"
    if file_type in (_FILE_TYPE_CHAR, _FILE_TYPE_PIPE):
        return "VERIFIED_NONDISK_FILETYPE"
    return "UNRESOLVED_FILETYPE"


def enumerate_file_handle_observations(*, dos_map=None, name_timeout_s: float = 0.5) -> dict:
    """Enumera handles de arquivo do sistema e produz observacoes para o nucleo.

    CORRECOES (Windows; R14R3 disk-type prefilter added):
      (a) ORDEM DO SNAPSHOT: o handle-sonda e criado ANTES do snapshot, para que o
          indice de tipo "File" seja descoberto a partir de um handle presente na tabela.
      (b) ASSINATURAS WIN64: argtypes/restype explicitos em CreateFileW, OpenProcess,
          DuplicateHandle, CloseHandle, GetProcessTimes, GetCurrentProcess,
          NtQuerySystemInformation e NtQueryObject (HANDLE = ponteiro 64-bit; sem isto
          o retorno e truncado para int32 e o handle fica invalido).
      (c) CICLO DE VIDA DAS THREADS: um unico worker reutilizavel para NtQueryObject com
          timeout; em timeout a thread presa (segurando o handle duplicado) e ABANDONADA
          (bounded) e NAO e join-ada nem tem o handle fechado; svc.shutdown() em todos os
          caminhos de retorno; o worker e daemon.
    Retorna {'observations':[...], 'enumeration_truncated':bool, 'stats':{...}}. Somente Windows."""
    if os.name != "nt":
        raise BackendBlocked("TARGET_WINDOWS_RUNTIME_REQUIRED")
    import ctypes
    import threading
    from ctypes import wintypes

    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    if dos_map is None:
        dos_map = _build_dos_device_map()

    ULONG_PTR = ctypes.c_size_t

    # (b) assinaturas Win64 explicitas
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                       ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                       wintypes.BOOL, wintypes.DWORD]
    kernel.DuplicateHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    kernel.GetFileType.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                       ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                                       ctypes.POINTER(wintypes.FILETIME)]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    ntdll.NtQuerySystemInformation.argtypes = [wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
                                               ctypes.POINTER(wintypes.ULONG)]
    ntdll.NtQuerySystemInformation.restype = wintypes.LONG
    ntdll.NtQueryObject.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
                                    ctypes.POINTER(wintypes.ULONG)]
    ntdll.NtQueryObject.restype = wintypes.LONG

    OpenProcess = kernel.OpenProcess
    DuplicateHandle = kernel.DuplicateHandle
    CloseHandle = kernel.CloseHandle
    GetFileType = kernel.GetFileType
    GetProcessTimes = kernel.GetProcessTimes
    cur_proc = kernel.GetCurrentProcess()

    class SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX(ctypes.Structure):
        _fields_ = [
            ("Object", ctypes.c_void_p),
            ("UniqueProcessId", ULONG_PTR),
            ("HandleValue", ULONG_PTR),
            ("GrantedAccess", wintypes.ULONG),
            ("CreatorBackTraceIndex", wintypes.USHORT),
            ("ObjectTypeIndex", wintypes.USHORT),
            ("HandleAttributes", wintypes.ULONG),
            ("Reserved", wintypes.ULONG),
        ]

    def query_system_handles():
        size = 1 << 20
        while True:
            buf = ctypes.create_string_buffer(size)
            ret_len = wintypes.ULONG(0)
            status = ntdll.NtQuerySystemInformation(
                _SYSTEM_EXTENDED_HANDLE_INFORMATION, buf, size, ctypes.byref(ret_len))
            if status == 0:
                return buf
            if status & 0xFFFFFFFF == _STATUS_INFO_LENGTH_MISMATCH:
                size = max(size * 2, ret_len.value + (1 << 16))
                if size > (1 << 30):
                    return None
                continue
            return None

    def read_object_name(h):
        size = 0x1000
        buf = ctypes.create_string_buffer(size)
        ret = wintypes.ULONG(0)
        status = ntdll.NtQueryObject(wintypes.HANDLE(h), _OBJECT_NAME_INFORMATION, buf, size, ctypes.byref(ret))
        if status & 0xFFFFFFFF == _STATUS_INFO_LENGTH_MISMATCH and ret.value:
            buf = ctypes.create_string_buffer(ret.value)
            status = ntdll.NtQueryObject(wintypes.HANDLE(h), _OBJECT_NAME_INFORMATION, buf, ret.value, ctypes.byref(ret))
        if status != 0:
            return None
        length = ctypes.c_ushort.from_buffer_copy(buf, 0).value
        addr_off = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4
        buf_ptr = ctypes.c_void_p.from_buffer_copy(buf, addr_off).value
        if buf_ptr and length:
            return ctypes.wstring_at(buf_ptr, length // 2)
        return ""

    class NameService:
        """(c) worker unico reutilizavel; timeout => abandona (bounded) sem join nem close."""
        def __init__(self):
            self.abandoned = 0
            self._worker = None
            self._req = None
            self._resp = None
            self._in = None
            self._out = None

        def _spawn(self):
            req = threading.Event(); resp = threading.Event()
            inp = {"h": None}; out = {"name": None}

            def loop():
                while True:
                    req.wait(); req.clear()
                    h = inp["h"]
                    if h is None:
                        return
                    try:
                        out["name"] = read_object_name(h)
                    except Exception:
                        out["name"] = None
                    resp.set()
            self._req, self._resp, self._in, self._out = req, resp, inp, out
            self._worker = threading.Thread(target=loop, daemon=True)
            self._worker.start()

        def resolve(self, h, timeout):
            if self.abandoned > _MAX_ABANDONED_NAME_WORKERS:
                return ("ABANDONED", None)
            if self._worker is None or not self._worker.is_alive():
                self._spawn()
            self._out["name"] = None
            self._resp.clear()
            self._in["h"] = h
            self._req.set()
            if self._resp.wait(timeout):
                return ("OK", self._out["name"])
            self.abandoned += 1      # thread presa segurando h: abandona, NAO fecha h, NAO join
            self._worker = None
            return ("ABANDONED", None)

        def shutdown(self):
            if self._worker is not None and self._worker.is_alive():
                self._in["h"] = None
                self._req.set()

    svc = NameService()

    # (a) cria o handle-sonda ANTES do snapshot
    import tempfile
    probe_handle = None
    probe_name = None
    try:
        tf = tempfile.NamedTemporaryFile(prefix="w04probe_", delete=False)
        tf.close()
        probe_name = tf.name
        fh = kernel.CreateFileW(probe_name, 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
        INVALID = ctypes.cast(-1, wintypes.HANDLE).value
        if fh and fh != INVALID:
            probe_handle = fh
    except Exception:
        probe_handle = None

    raw = query_system_handles()
    if raw is None:
        if probe_handle:
            CloseHandle(wintypes.HANDLE(probe_handle))
        if probe_name:
            try: os.unlink(probe_name)
            except OSError: pass
        svc.shutdown()
        return {"observations": [], "enumeration_truncated": True, "stats": {"reason": "SYSTEM_HANDLE_QUERY_FAILED"}}

    number = ULONG_PTR.from_buffer(raw, 0).value
    entry_size = ctypes.sizeof(SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX)
    base = ctypes.sizeof(ULONG_PTR) * 2

    file_type_index = None
    if probe_handle is not None:
        my_pid = os.getpid()
        for i in range(number):
            e = SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX.from_buffer(raw, base + i * entry_size)
            if int(e.UniqueProcessId) == my_pid and int(e.HandleValue) == int(probe_handle):
                file_type_index = int(e.ObjectTypeIndex)
                break
        CloseHandle(wintypes.HANDLE(probe_handle))
    if probe_name:
        try: os.unlink(probe_name)
        except OSError: pass

    if file_type_index is None:
        svc.shutdown()
        return {"observations": [], "enumeration_truncated": True, "stats": {"reason": "FILE_TYPE_INDEX_UNRESOLVED"}}

    observations = []
    proc_cache = {}
    # R14R3: type-of-handle is verified by Win32 before NtQueryObject.
    # Legacy _HANGMASK is not used as a bypass; a DISK handle is always queried.
    skipped_hangmask = 0
    file_type_pipe = 0
    file_type_char = 0
    file_type_unknown = 0
    disk_name_queries = 0
    truncated = False

    def owner_creation_filetime(pid):
        if pid in proc_cache:
            return proc_cache[pid]
        hp = OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not hp:
            proc_cache[pid] = ("ACCESS_DENIED", None); return proc_cache[pid]
        try:
            c = wintypes.FILETIME(); x = wintypes.FILETIME(); k = wintypes.FILETIME(); u = wintypes.FILETIME()
            if GetProcessTimes(hp, ctypes.byref(c), ctypes.byref(x), ctypes.byref(k), ctypes.byref(u)):
                proc_cache[pid] = ("IDENTIFIED", (int(c.dwHighDateTime) << 32) | int(c.dwLowDateTime))
            else:
                proc_cache[pid] = ("UNKNOWN", None)
        finally:
            CloseHandle(hp)
        return proc_cache[pid]

    try:
        for i in range(number):
            e = SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX.from_buffer(raw, base + i * entry_size)
            if int(e.ObjectTypeIndex) != file_type_index:
                continue
            pid = int(e.UniqueProcessId)
            handle_value = int(e.HandleValue)
            granted = int(e.GrantedAccess)
            name_status = "UNRESOLVED"
            resolved_path = None
            file_type = None
            file_type_source = None
            hp = OpenProcess(_PROCESS_DUP_HANDLE, False, pid)
            if hp:
                try:
                    dup = wintypes.HANDLE()
                    if DuplicateHandle(hp, wintypes.HANDLE(handle_value), cur_proc,
                                       ctypes.byref(dup), 0, False, _DUPLICATE_SAME_ACCESS):
                        # GetFileType is independent of granted-access-mask heuristics.
                        # A non-disk result is an explicit OS proof, not a guessed pipe.
                        file_type = int(GetFileType(dup))
                        file_type_source = "WIN32_GETFILETYPE"
                        disposition = _file_type_disposition(file_type)
                        if disposition == "VERIFIED_NONDISK_FILETYPE":
                            name_status = disposition
                            if file_type == _FILE_TYPE_PIPE: file_type_pipe += 1
                            if file_type == _FILE_TYPE_CHAR: file_type_char += 1
                            CloseHandle(dup)
                        elif disposition == "DISK_QUERY_REQUIRED":
                            disk_name_queries += 1
                            status, nt_name = svc.resolve(dup.value, name_timeout_s)
                            if status == "OK":
                                # Unknown disk namespace / empty names MUST NOT
                                # be misclassified as outside target by string prefix.
                                dos = _nt_name_to_dos(nt_name, dos_map) if nt_name else None
                                if dos:
                                    resolved_path = dos
                                    name_status = "RESOLVED"
                                CloseHandle(dup)  # worker finished; safe to close
                            elif svc.abandoned > _MAX_ABANDONED_NAME_WORKERS:
                                truncated = True
                        else:
                            # FILE_TYPE_UNKNOWN is not a proof that target is irrelevant.
                            file_type_unknown += 1
                            CloseHandle(dup)
                finally:
                    CloseHandle(hp)
            owner_status, ctime = owner_creation_filetime(pid)
            observations.append({
                "handle_id": handle_value, "owner_pid": pid, "granted_access": granted,
                "name_status": name_status, "resolved_path": resolved_path,
                "file_type": file_type, "file_type_source": file_type_source,
                "owner_status": owner_status, "owner_creation_filetime": ctime,
            })
            if truncated:
                break
    finally:
        svc.shutdown()

    return {"observations": observations, "enumeration_truncated": truncated,
            "stats": {"file_handles": len(observations), "skipped_hangmask": skipped_hangmask,
                      "file_type_pipe": file_type_pipe, "file_type_char": file_type_char,
                      "file_type_unknown": file_type_unknown, "disk_name_queries": disk_name_queries,
                      "abandoned_name_workers": svc.abandoned}}


def _self_identity():
    """(PID, creation_filetime) do processo atual (dono legitimo por padrao)."""
    if os.name != "nt":
        return (os.getpid(), 0)
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    c = wintypes.FILETIME(); x = wintypes.FILETIME(); k = wintypes.FILETIME(); u = wintypes.FILETIME()
    kernel.GetProcessTimes(kernel.GetCurrentProcess(),
                           ctypes.byref(c), ctypes.byref(x), ctypes.byref(k), ctypes.byref(u))
    return (os.getpid(), (int(c.dwHighDateTime) << 32) | int(c.dwLowDateTime))


def _load_identity_map():
    """Mapa opcional pid->creation_filetime esperado (deteccao de reuso) e
    identidades donas legitimas, via env PEGASUS_W04_IDENTITY_MAP (JSON)."""
    import json
    path = os.environ.get("PEGASUS_W04_IDENTITY_MAP", "")
    expected = {}
    owned = set()
    if path and os.path.isfile(path):
        with open(path, "rb") as f:
            doc = json.loads(f.read().decode("utf-8-sig"))
        for rec in doc.get("expected_identities", []):
            expected[int(rec["pid"])] = int(rec["creation_filetime"])
        for rec in doc.get("attempt_owned", []):
            owned.add((int(rec["pid"]), int(rec["creation_filetime"])))
    return expected, owned


def qualified_native_probe(*, attempt_id: str, target_paths: list) -> dict:
    """Callable que o gate selado consome via `native_probe=`.
    Mesma assinatura de scoped_native_probe; fail-closed; nunca encerra processo.
    Politica: STRICT sempre. Apenas a classificacao Win32 FILE_TYPE_PIPE/CHAR
    do handle duplicado fornece prova de tipo nao-disco; UNKNOWN bloqueia."""
    if os.name != "nt":
        raise BackendBlocked("TARGET_WINDOWS_RUNTIME_REQUIRED")
    if not target_paths or len(set(p.casefold() for p in target_paths)) != len(target_paths):
        raise BackendBlocked("W04_EXACT_TARGET_FILE_SET_REQUIRED")
    enable_se_debug_privilege()  # best-effort; sem ele, donos viram ACCESS_DENIED -> block
    expected, owned = _load_identity_map()
    owned = owned or {_self_identity()}
    strict = True  # Source-only hardening: no environment bypass for productive admission.
    enum = enumerate_file_handle_observations()
    return decide_coverage(
        strict_hangmask=strict,
        attempt_id=attempt_id,
        targets=list(target_paths),
        observations=enum["observations"],
        attempt_owned=owned,
        expected_identities=expected,
        enumeration_truncated=enum["enumeration_truncated"],
    )
