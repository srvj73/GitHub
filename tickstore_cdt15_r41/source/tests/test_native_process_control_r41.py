"""R41 native Windows process control: SAFE_STOP event, Job containment, RAM census, lease.

These tests are Windows-only by nature.  The R41 qualification driver runs them
natively and refuses any skip there; on POSIX they are reported as skipped.
"""
import multiprocessing as mp
import os
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

R = Path(__file__).resolve().parents[1]
FULL = R / 'candidate/full'
sys.path.insert(0, str(FULL))

NATIVE = os.name == 'nt'


@unittest.skipUnless(NATIVE, 'native Windows process-control proof')
class NativeProcessControl(unittest.TestCase):
    def test_01_safe_stop_event_crosses_processes(self):
        from FULL_PROCESS_CONTROL import StopEvent
        run_id = 'R41Q' + uuid.uuid4().hex[:16].upper()
        ev = StopEvent(run_id)
        try:
            self.assertFalse(ev.requested())
            with self.assertRaisesRegex(RuntimeError, 'FULL_STOP_EVENT_PREEXISTS'):
                StopEvent(run_id)
            code = ('import sys;sys.path.insert(0,sys.argv[1]);from FULL_PROCESS_CONTROL import StopEvent;'
                    'e=StopEvent(sys.argv[2],request=True);e.close();print("REQUESTED")')
            r = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(FULL), run_id],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(ev.requested())
        finally:
            ev.close()

    def test_02_job_close_kills_admitted_child_tree(self):
        from FULL_PROCESS_CONTROL import ProcessJob
        ctx = mp.get_context('spawn')
        job = ProcessJob()
        proc = job.start(ctx, time.sleep, args=(120,), name='R41-JOB-CHILD')
        started = time.monotonic()
        try:
            time.sleep(1.0)
            self.assertTrue(proc.is_alive())
            snap = job.memory_snapshot()
            self.assertIn(proc.pid, [p['pid'] for p in snap['processes']])
            self.assertGreater(snap['working_set_bytes'], 0)
        finally:
            job.close()
        proc.join(20)
        self.assertFalse(proc.is_alive())
        # KILL_ON_JOB_CLOSE terminates members with exit code 0 (observed natively,
        # R41 run 20261013_174923). Proof of containment is death far before 120 s.
        self.assertIsNotNone(proc.exitcode)
        self.assertLess(time.monotonic() - started, 30)

    def test_03_full_lease_is_exclusive_and_released(self):
        from tickstore_full_multiwork import FullProcessLease, MultiworkBlocked
        dest = Path(os.environ.get('TEMP', 'C:\\')) / ('R41_LEASE_' + uuid.uuid4().hex)
        a = FullProcessLease(dest)
        try:
            with self.assertRaisesRegex(MultiworkBlocked, 'FULL_LEASE_LIVE_SUPERVISOR'):
                FullProcessLease(dest)
        finally:
            a.close()
        FullProcessLease(dest).close()

    def test_04_autocpu_probe_matches_affinity(self):
        from tickstore_full_multiwork import available_logical_cpus, windows_memory_status
        n = available_logical_cpus()
        self.assertGreaterEqual(n, 1)
        self.assertLessEqual(n, os.cpu_count())
        mem = windows_memory_status()
        self.assertGreater(mem['total'], mem['available'] // 2)
        print('R41_NATIVE_CPU_AVAILABLE=%d CPU_LOGICAL=%d RAM_TOTAL_GIB=%.2f RAM_AVAILABLE_GIB=%.2f' % (
            n, os.cpu_count(), mem['total'] / 1024**3, mem['available'] / 1024**3), flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
