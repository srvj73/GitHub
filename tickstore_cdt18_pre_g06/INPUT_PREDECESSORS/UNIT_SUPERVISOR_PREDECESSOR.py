"""Owned qualification subprocesses; never a production process supervisor.

Windows admission reuses the packaged ProcessJob. The small multiprocessing
bootstrap waits for Job assignment before it starts the requested executable.
Timeout, interrupt and telemetry failures terminate only that owned Job and
require a zero-member census. An abrupt stop is never called SAFE_STOP.
"""
from __future__ import annotations

import ctypes
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import time


class QualificationStopped(RuntimeError):
    def __init__(self, reason, reconciliation):
        super().__init__(reason)
        self.reconciliation = reconciliation


def _execute(command, cwd, log_handle, environment, channel):
    try:
        import msvcrt
        # Transfer the exclusively created file handle. Reopening a pathname
        # after admission would reintroduce a name-swap window for the log.
        descriptor = msvcrt.open_osfhandle(log_handle.detach(), os.O_WRONLY | os.O_BINARY)
        with os.fdopen(descriptor, 'wb', buffering=0) as output:
            child = subprocess.Popen(command, cwd=cwd, env=environment,
                                     stdin=subprocess.DEVNULL, stdout=output,
                                     stderr=subprocess.STDOUT, close_fds=True)
            channel.send({'event': 'STARTED', 'pid': child.pid})
            code = child.wait()
            os.fsync(output.fileno())
        channel.send({'event': 'EXITED', 'exit_code': code})
    except BaseException as error:
        channel.send({'event': 'ERROR', 'reason': type(error).__name__ + ':' + str(error)})
        raise
    finally:
        channel.close()


def _members(job):
    from ctypes import wintypes as w
    k = job.k
    k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                          w.DWORD, ctypes.c_void_p]
    k.QueryInformationJobObject.restype = w.BOOL
    capacity = 64
    for _ in range(8):
        class Members(ctypes.Structure):
            _fields_ = [('assigned', w.DWORD), ('count', w.DWORD),
                        ('pids', ctypes.c_size_t * capacity)]
        info = Members()
        if k.QueryInformationJobObject(job.handle, 3, ctypes.byref(info), ctypes.sizeof(info), None):
            if info.assigned == info.count:
                return sorted(info.pids[:info.count])
        elif ctypes.get_last_error() != 234:
            raise ctypes.WinError(ctypes.get_last_error())
        capacity = max(capacity * 2, info.assigned)
    raise RuntimeError('QUAL_JOB_CENSUS_UNSTABLE')


def _terminate(job):
    from ctypes import wintypes as w
    job.k.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    job.k.TerminateJobObject.restype = w.BOOL
    if not job.k.TerminateJobObject(job.handle, 2):
        raise ctypes.WinError(ctypes.get_last_error())


def _drain_channel(channel, report):
    """Consume complete events; Windows EOF from PeekNamedPipe is not a verdict.

    Windows multiprocessing.Connection.poll() can raise WinError 109 if the
    writer has closed its pipe after sending the final EXITED event. This is
    end-of-channel transport state, not evidence of target success. A missing
    STARTED/EXITED still blocks in _terminal_result.
    """
    if report.get('channel_closed'):
        return
    while True:
        try:
            if not channel.poll():
                return
            event = channel.recv()
        except (EOFError, BrokenPipeError) as error:
            report['channel_closed'] = type(error).__name__
            return
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) in (109, 232):
                report['channel_closed'] = 'WIN_PIPE_CLOSED_' + str(error.winerror)
                return
            raise
        if not isinstance(event, dict) or event.get('event') not in ('STARTED', 'EXITED', 'ERROR'):
            raise RuntimeError('QUAL_UNEXPECTED_CONTROL_EVENT')
        report['events'].append(event)


def _terminal_result(report, coordinator_exit):
    """Fail closed: EOF, alone, can never certify a child execution."""
    events = report['events']
    started = [e for e in events if e.get('event') == 'STARTED']
    exited = [e for e in events if e.get('event') == 'EXITED']
    errors = [e for e in events if e.get('event') == 'ERROR']
    if coordinator_exit != 0 or len(started) != 1 or len(exited) != 1 or errors:
        raise RuntimeError('QUAL_COORDINATOR_NO_SINGLE_CLOSED_RESULT')
    if events.index(started[0]) >= events.index(exited[0]):
        raise RuntimeError('QUAL_CONTROL_EVENT_ORDER_INVALID')
    if not isinstance(started[0].get('pid'), int) or started[0]['pid'] <= 0:
        raise RuntimeError('QUAL_CHILD_PID_INVALID')
    if not isinstance(exited[0].get('exit_code'), int):
        raise RuntimeError('QUAL_CHILD_EXITCODE_INVALID')
    return exited[0]['exit_code']


def run(command, *, cwd, log, process_control_dir, heartbeat, timeout,
        stop_requested=lambda: False, environment=None, interval=2.0):
    if os.name != 'nt':
        raise RuntimeError('QUAL_SUPERVISOR_NATIVE_WINDOWS_REQUIRED')
    if not 0 < interval <= 5 or not 0 < timeout <= 86400:
        raise ValueError('QUAL_SUPERVISOR_BOUNDS')
    command = [str(x) for x in command]
    if not command or not Path(command[0]).is_absolute():
        raise ValueError('QUAL_EXECUTABLE_ABSOLUTE_REQUIRED')
    log, cwd = Path(log), Path(cwd)
    if not cwd.is_absolute() or not log.is_absolute():
        raise ValueError('QUAL_PATH_ABSOLUTE_REQUIRED')
    # The caller verifies this directory against the frozen code manifest.
    import sys
    sys.path.insert(0, str(process_control_dir))
    from FULL_PROCESS_CONTROL import ProcessJob
    env = dict(os.environ if environment is None else environment)
    ctx = mp.get_context('spawn')
    parent, child = ctx.Pipe(duplex=False)
    job = ProcessJob()
    proc = None
    output = None
    started = time.monotonic()
    report = {'schema': 'CDT18_OWNED_UNIT_PROCESS_RECONCILIATION_V001',
              'assignment': 'NOT_ADMITTED', 'safe_stop': False,
              'termination_requested': False, 'final_members': None,
              'events': [], 'samples': []}
    primary = None
    try:
        # Duplicate log names cannot truncate evidence from a prior attempt.
        import msvcrt
        from multiprocessing.reduction import DupHandle
        output = log.open('xb', buffering=0)
        output.flush()
        os.fsync(output.fileno())
        log_stat = os.fstat(output.fileno())
        report['log_identity'] = [log_stat.st_dev, log_stat.st_ino]
        log_handle = DupHandle(msvcrt.get_osfhandle(output.fileno()), 0x40000000)
        proc = job.start(ctx, _execute, args=(command, str(cwd), log_handle, env, child),
                         name='CDT18-QUAL-OWNED-UNIT')
        child.close()
        report['assignment'] = 'ADMITTED_BEFORE_TARGET'
        report['coordinator_pid'] = proc.pid
        while True:
            _drain_channel(parent, report)
            elapsed = time.monotonic() - started
            sample = {'elapsed_s': round(elapsed, 3), 'members': _members(job)}
            report['samples'].append(sample)
            heartbeat(sample)
            if stop_requested():
                raise RuntimeError('QUAL_STOP_REQUESTED_ABRUPT_NOT_SAFE_STOP')
            if elapsed >= timeout:
                raise RuntimeError('QUAL_WATCHDOG_TIMEOUT')
            if not proc.is_alive():
                break
            proc.join(interval)
        proc.join(0)
        _drain_channel(parent, report)
        report['exit_code'] = _terminal_result(report, proc.exitcode)
    except BaseException as error:
        primary = error
    finally:
        try:
            remaining = _members(job)
            if primary is None and remaining:
                # Windows can retain a console host briefly after a clean exit.
                drain_deadline = time.monotonic() + 5
                while remaining and time.monotonic() < drain_deadline:
                    heartbeat({'elapsed_s': round(time.monotonic() - started, 3),
                               'members': remaining, 'phase': 'NATURAL_TREE_DRAIN'})
                    time.sleep(min(interval, 1))
                    remaining = _members(job)
            if remaining:
                report['termination_requested'] = True
                report['members_before_termination'] = remaining
                _terminate(job)
                deadline = time.monotonic() + 15
                while True:
                    remaining = _members(job)
                    if not remaining:
                        break
                    heartbeat({'elapsed_s': round(time.monotonic() - started, 3),
                               'members': remaining, 'phase': 'TREE_RECONCILIATION'})
                    if time.monotonic() >= deadline:
                        raise RuntimeError('QUAL_JOB_ZERO_MEMBERS_NOT_PROVEN')
                    if proc is not None:
                        proc.join(min(interval, 1))
                    else:
                        time.sleep(min(interval, 1))
                if primary is None:
                    primary = RuntimeError('QUAL_RESIDUAL_DESCENDANT_AFTER_UNIT_EXIT')
            report['final_members'] = remaining
            report['tree_reconciled'] = remaining == []
            if proc is not None:
                proc.join(1)
                report['coordinator_exit_code'] = proc.exitcode
        except BaseException as cleanup_error:
            report['cleanup_error'] = type(cleanup_error).__name__ + ':' + str(cleanup_error)
            report['tree_reconciled'] = False
            if primary is None:
                primary = cleanup_error
        finally:
            # KILL_ON_JOB_CLOSE is a final fail-closed fallback, never evidence
            # of a clean census when the explicit reconciliation above failed.
            try:
                job.close()
            except BaseException as close_error:
                report['job_close_error'] = str(close_error)
                report['tree_reconciled'] = False
                if primary is None:
                    primary = close_error
            if output is not None:
                try:
                    os.fsync(output.fileno())
                    after = os.lstat(log)
                    if [after.st_dev, after.st_ino] != report['log_identity']:
                        raise RuntimeError('QUAL_LOG_NAME_IDENTITY_CHANGED')
                except BaseException as log_error:
                    report['log_close_error'] = str(log_error)
                    if primary is None:
                        primary = log_error
                finally:
                    output.close()
            parent.close()
            child.close()
    report['elapsed_s'] = round(time.monotonic() - started, 3)
    if primary is not None:
        raise QualificationStopped(type(primary).__name__ + ':' + str(primary), report) from primary
    return report
