"""Native lifetime containment; child code starts only after Job assignment."""
import ctypes
from ctypes import wintypes as w
import os
import re


class StopEvent:
    def __init__(self, run_id, *, request=False):
        if not isinstance(run_id, str) or re.fullmatch('[a-zA-Z0-9_-]{1,80}', run_id) is None:
            raise RuntimeError('FULL_RUN_ID_INVALID')
        self.k = k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]; k.CreateEventW.restype = w.HANDLE
        k.OpenEventW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]; k.OpenEventW.restype = w.HANDLE
        k.SetEvent.argtypes = [w.HANDLE]; k.SetEvent.restype = w.BOOL
        k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; k.WaitForSingleObject.restype = w.DWORD
        k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL
        name = 'Global\\TICKSTORE_FULL_STOP_' + run_id
        ctypes.set_last_error(0)
        self.handle = k.OpenEventW(0x00100002, False, name) if request else k.CreateEventW(None, True, False, name)
        error = ctypes.get_last_error()
        if not self.handle:
            raise RuntimeError('FULL_STOP_EVENT_OPEN:' + str(error))
        if not request and error == 183:
            self.close(); raise RuntimeError('FULL_STOP_EVENT_PREEXISTS')
        if request and not k.SetEvent(self.handle):
            self.close(); raise RuntimeError('FULL_STOP_EVENT_SET')

    def requested(self):
        result = self.k.WaitForSingleObject(self.handle, 0)
        if result not in (0, 258):
            raise RuntimeError('FULL_STOP_EVENT_WAIT')
        return result == 0

    def close(self):
        if self.handle:
            if not self.k.CloseHandle(self.handle): raise RuntimeError('FULL_STOP_EVENT_CLOSE')
            self.handle = None


def _admitted_child(start, target, args, kwargs):
    # A parent dying before assignment cannot leave a child performing work.
    if not start.wait(30):
        raise RuntimeError('PROCESS_START_ADMISSION_TIMEOUT')
    target(*args, **kwargs)


class ProcessJob:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('JOB_WINDOWS_REQUIRED')
        self.k = k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        k.CreateJobObjectW.restype = w.HANDLE
        k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        k.SetInformationJobObject.restype = w.BOOL
        k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        k.AssignProcessToJobObject.restype = w.BOOL
        k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL

        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                        ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', w.DWORD),
                        ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
                        ('ActiveProcessLimit', w.DWORD), ('Affinity', ctypes.c_size_t),
                        ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('ReadOperationCount', 'WriteOperationCount',
                         'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise RuntimeError('JOB_CREATE:' + str(ctypes.get_last_error()))
        limits = Extended(); limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error(); self.close()
            raise RuntimeError('JOB_LIMITS:' + str(error))

    def start(self, ctx, target, *, args=(), kwargs=None, name=None):
        event = ctx.Event()
        proc = ctx.Process(target=_admitted_child, args=(event, target, args, kwargs or {}), name=name)
        proc.start()
        try:
            if not self.k.AssignProcessToJobObject(self.handle, proc.sentinel):
                raise RuntimeError('JOB_ASSIGN:' + str(ctypes.get_last_error()))
            event.set()
            return proc
        except BaseException:
            # Target has not been admitted; terminating the waiting bootstrap has no data effects.
            proc.terminate(); proc.join(10)
            if proc.is_alive():
                raise RuntimeError('UNADMITTED_PROCESS_CLEANUP_FAILED')
            raise

    def close(self):
        if self.handle:
            if not self.k.CloseHandle(self.handle):
                raise RuntimeError('JOB_CLOSE:' + str(ctypes.get_last_error()))
            self.handle = None

    def memory_snapshot(self):
        """Measure this job tree and coordinator; never sample unrelated processes.

        JobObjectBasicProcessIdList includes nested jobs (Microsoft Win32 API).
        Memory is sampled using held process handles and includes creation times.
        Working sets may share pages: their sum is a conservative RAM measure.
        """
        k = self.k
        k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
        k.QueryInformationJobObject.restype = w.BOOL
        capacity = 64
        for _ in range(8):
            class PIDs(ctypes.Structure):
                _fields_ = [('assigned', w.DWORD), ('count', w.DWORD), ('pids', ctypes.c_size_t * capacity)]
            info = PIDs()
            ok = k.QueryInformationJobObject(self.handle, 3, ctypes.byref(info), ctypes.sizeof(info), None)
            if ok and info.count == info.assigned:
                pids = list(info.pids[:info.count]); break
            if not ok and ctypes.get_last_error() != 234:
                raise RuntimeError('JOB_PROCESS_CENSUS:' + str(ctypes.get_last_error()))
            capacity = max(capacity * 2, info.assigned)
        else:
            raise RuntimeError('JOB_PROCESS_CENSUS_UNSTABLE')
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
        k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]; k.IsProcessInJob.restype = w.BOOL
        k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4; k.GetProcessTimes.restype = w.BOOL
        k.K32GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD]; k.K32GetProcessMemoryInfo.restype = w.BOOL
        class Memory(ctypes.Structure):
            _fields_ = [('cb', w.DWORD), ('PageFaultCount', w.DWORD)] + [(n, ctypes.c_size_t) for n in (
                'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
        result = []
        for pid in sorted(set(pids + [os.getpid()])):
            handle = k.OpenProcess(0x0400, False, pid)
            if not handle:
                if ctypes.get_last_error() == 87 and pid != os.getpid(): continue  # exited before open
                raise RuntimeError('MEMORY_PROCESS_OPEN:' + str(ctypes.get_last_error()))
            try:
                if pid != os.getpid():
                    member = w.BOOL()
                    if not k.IsProcessInJob(handle, self.handle, ctypes.byref(member)):
                        raise RuntimeError('MEMORY_JOB_MEMBERSHIP_QUERY')
                    if not member.value: continue  # PID reused outside this job
                created, exited, kernel, user = (w.FILETIME() for _ in range(4))
                if not k.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
                    raise RuntimeError('MEMORY_PROCESS_TIMES')
                if exited.dwHighDateTime or exited.dwLowDateTime: continue
                m = Memory(); m.cb = ctypes.sizeof(m)
                if not k.K32GetProcessMemoryInfo(handle, ctypes.byref(m), ctypes.sizeof(m)):
                    raise RuntimeError('MEMORY_COUNTERS_QUERY:' + str(ctypes.get_last_error()))
                result.append({'pid': pid, 'creation_filetime': (created.dwHighDateTime << 32) | created.dwLowDateTime,
                               'working_set_bytes': m.WorkingSetSize, 'private_bytes': m.PrivateUsage})
            finally:
                k.CloseHandle(handle)
        return {'processes': result, 'working_set_bytes': sum(p['working_set_bytes'] for p in result),
                'private_bytes': sum(p['private_bytes'] for p in result)}
