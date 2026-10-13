#!/usr/bin/env python3
# coding: utf-8
"""Real interrupt test for the TOP4 readback engine (POSIX SIGINT == Ctrl+C KeyboardInterrupt path).

A child process imports the payload by exact path and runs readback() over a synthetic volume large
enough to be interrupted mid-run; the parent sends SIGINT after several commits. Then:
  * journal holds only complete, fsynced records; lock released; no partial commit;
  * a second run resumes without re-hashing committed files and ends with all files matched.
Usage: python -I -B sandbox_readback_sigint_test.py <payload.py> <scratch>
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

DRIVER = r'''
import importlib.util, json, sys, hashlib, csv, io
from pathlib import Path
sp = importlib.util.spec_from_file_location('rb', sys.argv[1]); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
root = Path(sys.argv[2]); state = Path(sys.argv[3]); sets = ('SET_ONE', 'SET_TWO')
payload = root / 'ARQUIVO_FRIO' / 'TOP4_V001' / 'PAYLOAD'
rows = []
for s in sets:
    for f in sorted((payload / 'PerseuRuns' / s).iterdir()):
        b = f.read_bytes(); rows.append((f'D:\\PerseuRuns\\{s}\\{f.name}', len(b), hashlib.sha256(b).hexdigest().upper()))
buf = io.StringIO(); w = csv.writer(buf); w.writerow(('path', 'size', 'sha256')); [w.writerow(r) for r in rows]
mp = root / 'm.csv'; mp.write_text(buf.getvalue(), encoding='utf-8')
man = m.load_manifest(mp, hashlib.sha256(mp.read_bytes()).hexdigest().upper(), len(rows), sum(r[1] for r in rows))
m.HEARTBEAT_S = 0.0
try:
    res = m.readback(payload, man, state, 'P' * 64, sets, root)
    print(json.dumps({'status': 'DONE', 'resumed': res['resumed_files'], 'hashed': res['hashed_this_session'], 'matched': res['matched'], 'total': res['total_files']}))
except KeyboardInterrupt:
    print(json.dumps({'status': 'SAFE_STOP'})); sys.exit(130)
'''


def main(argv):
    payload, scratch = Path(argv[1]).resolve(), Path(argv[2])
    scratch.mkdir(parents=True, exist_ok=False)
    for s in ('SET_ONE', 'SET_TWO'):
        d = scratch / 'vol' / 'ARQUIVO_FRIO' / 'TOP4_V001' / 'PAYLOAD' / 'PerseuRuns' / s
        d.mkdir(parents=True)
        for i in range(40):
            (d / f'f{i:03d}.bin').write_bytes(os.urandom(4 * 1024 * 1024))
    drv = scratch / 'driver.py'
    drv.write_text(DRIVER, encoding='utf-8')
    state = scratch / 'state'
    cmd = [sys.executable, '-I', '-B', str(drv), str(payload), str(scratch / 'vol'), str(state)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    j = state / 'JOURNAL.jsonl'
    t0 = time.time()
    while time.time() - t0 < 60:
        if j.exists() and j.read_bytes().count(b'\n') >= 8:
            break
        time.sleep(0.02)
    p.send_signal(signal.SIGINT)
    out, err = p.communicate(timeout=60)
    lines = [x for x in j.read_bytes().split(b'\n') if x]
    recs = [json.loads(x) for x in lines[1:]]
    first = {'exit': p.returncode, 'stdout': out.decode().strip(), 'commits': len(recs), 'lock_released': not (state / 'LOCK.json').exists(),
             'journal_complete_lines': j.read_bytes().endswith(b'\n'), 'heartbeats': err.decode().count('HEARTBEAT')}
    q = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    second = json.loads(q.stdout.decode().strip().splitlines()[-1])
    ok = (first['exit'] == 130 and 'SAFE_STOP' in first['stdout'] and 0 < first['commits'] < 80 and first['lock_released']
          and first['journal_complete_lines'] and second['status'] == 'DONE' and second['resumed'] == first['commits']
          and second['hashed'] == 80 - first['commits'] and second['matched'] == 80 and first['heartbeats'] > 0)
    print(json.dumps({'scope': 'PASS_SANDBOX_LINUX_SIGINT', 'first_run': first, 'second_run': second,
                      'verdict': 'PASS_SANDBOX_SCOPE' if ok else 'FAIL'}, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
