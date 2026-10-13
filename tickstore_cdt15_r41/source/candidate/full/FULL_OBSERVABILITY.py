"""Attempt-scoped durable heartbeat. Liveness never implies completion."""
import datetime
import threading
import time


class Heartbeat:
    def __init__(self, path, writer, identity, *, interval=5.0):
        if interval <= 0: raise ValueError('HEARTBEAT_INTERVAL')
        self.path = path; self.writer = writer; self.interval = interval
        self.identity = dict(identity)
        self.lock = threading.Lock(); self.stop = threading.Event(); self.error = None
        self.started = time.monotonic(); self.sequence = 0
        self.state = dict(schema='TICKSTORE_HEARTBEAT_V001', **identity,
                          phase='STARTING', committed_rows=0, total_rows=None,
                          pipeline_complete=False, status='RUNNING')
        self.thread = None

    def sample(self):
        with self.lock: result = dict(self.state)
        elapsed = max(time.monotonic() - self.started, 1e-9)
        committed = result['committed_rows']; total = result['total_rows']
        if type(committed) is not int or committed < 0:
            raise RuntimeError('HEARTBEAT_COUNTS')
        if total is not None and (type(total) is not int or total <= 0 or not 0 <= committed <= total):
            raise RuntimeError('HEARTBEAT_COUNTS')
        percent = 100.0 * committed / total if total else None
        if percent is not None and not result['pipeline_complete']: percent = min(percent, 99.999)
        # Remaining verification has no measured work denominator. Never print
        # a zero ETA merely because all rows have been committed.
        eta = ((total - committed) / (committed / elapsed)
               if total and 0 < committed < total and result['phase'] == 'PIPELINE' else None)
        result.update(sequence=self.sequence, observed_unix_ns=time.time_ns(),
                      elapsed_seconds=elapsed, committed_percent=percent,
                      eta_seconds=eta, estimated_completion_utc=(datetime.datetime.fromtimestamp(
                          time.time() + eta, datetime.timezone.utc).isoformat() if eta is not None else None))
        return result

    def emit(self):
        self.sequence += 1
        self.writer(self.path, self.sample())

    def _run(self):
        while not self.stop.wait(self.interval):
            try: self.emit()
            except BaseException as exc:
                self.error = exc; self.stop.set(); return

    def check(self):
        if self.error is not None: raise RuntimeError('DURABLE_HEARTBEAT_FAILED') from self.error

    def update(self, **values):
        self.check()
        if any(key in self.identity and value != self.identity[key] for key, value in values.items()):
            raise RuntimeError('HEARTBEAT_IDENTITY_DRIFT')
        with self.lock: self.state.update(values)

    def start(self):
        self.emit()
        self.thread = threading.Thread(target=self._run, name='TICKSTORE_HEARTBEAT', daemon=True)
        self.thread.start(); return self

    def close(self, status):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=max(10, 2*self.interval))
            if self.thread.is_alive(): raise RuntimeError('HEARTBEAT_THREAD_NOT_CLOSED')
        self.check(); self.update(status=status); self.emit()
