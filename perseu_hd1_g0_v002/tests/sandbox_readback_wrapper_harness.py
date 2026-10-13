#!/usr/bin/env python3
# coding: utf-8
"""Sandbox harness for PERSEU_HD1_TOP4_READBACK_V001.ps1 (pwsh/Linux; NOT Windows PowerShell 5.1).

A: delivered bytes -> BLOCKED WINDOWS_TARGET_REQUIRED, exit 2, no file created.
B (PATCHED COPIES, labelled, never TESTED=DELIVERED evidence): gates neutralized, disk cmdlets stubbed:
   SelfTest (exit 0); Readback without owner decisions (BLOCKED, no snapshot written);
   Readback with decisions on non-Windows payload (BLOCKED WINDOWS_TARGET_REQUIRED, exit 2);
   payload outcome substitution -> FAIL exit 1 / SAFE_STOP exit 130 propagated;
   real SIGINT to the process group while the payload runs -> wrapper SAFE_STOP 130, child reconciled.

Usage: python -I -B sandbox_readback_wrapper_harness.py <wrapper.ps1> <pwsh> <python3.14> <scratch>
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

FOOTER = 'RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION'
STUBS = r'''
function Get-Disk { @([pscustomobject]@{ Number = 3; FriendlyName = 'Lexar'; SerialNumber = 'X'; Size = [uint64]1; OperationalStatus = 'Online'; IsOffline = $false; IsReadOnly = $false; PartitionStyle = 'GPT'; BusType = 'NVMe' }) }
function Get-Partition { @([pscustomobject]@{ DiskNumber = 3; PartitionNumber = 1; DriveLetter = [char]'C'; Size = [uint64]1; Type = 'Basic' }) }
function Get-Volume { @([pscustomobject]@{ DriveLetter = [char]'C'; FileSystemLabel = 'OS'; FileSystem = 'NTFS'; Size = [uint64]1; SizeRemaining = [uint64]1 }) }
'''
RB_ANCHOR = "foreach ($x in @('--readback', '--snapshot', $snapPre, '--state-root', $StateRoot, '--report-json', $readbackReport)) { $rbArgs.Add($x) }"


def build(src, python, root, substitute=None):
    reps = [
        ("    if ($env:OS -ne 'Windows_NT') { Stop-PhrBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }\r\n", ''),
        ("    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) {", '    if ($false) {'),
        ("Set-StrictMode -Version 2.0\r\n", "Set-StrictMode -Version 2.0\r\n" + STUBS.replace('\n', '\r\n')),
        ("$PinnedPython = 'C:\\Users\\silvi\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe'", "$PinnedPython = '" + python + "'"),
        ("$DownloadsRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads'", "$DownloadsRoot = '" + str(root) + "'"),
        ("$EvidenceRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads\\PERSEU_HD1_TOP4_READBACK_V001_RUNS'", "$EvidenceRoot = '" + str(root / 'RUNS') + "'"),
        ("$StateParent = 'C:\\Users\\silvi'", "$StateParent = '" + str(root) + "'"),
        ("$StateRoot = 'C:\\Users\\silvi\\PERSEU_STATE\\TOP4_READBACK_V001'", "$StateRoot = '" + str(root / 'STATE') + "'"),
    ]
    if substitute:
        reps.append((RB_ANCHOR, "foreach ($x in @('--fixture-child', '" + substitute + "')) { $rbArgs.Add($x) }"))
    text = src
    for old, new in reps:
        if text.count(old) != 1:
            raise SystemExit('PATCH_ANCHOR_CARDINALITY:' + old[:60])
        text = text.replace(old, new)
    if text.count("'PASS_WINDOWS_") != 2:
        raise SystemExit('PATCH_LABEL_CARDINALITY')
    return text.replace("'PASS_WINDOWS_", "'SANDBOX_PATCHED_COPY_NOT_WINDOWS_")


def receipt(root, mode):
    runs = sorted((root / 'RUNS').glob(mode.upper() + '_*'))
    if not runs:
        return None, None
    rp = runs[-1] / ('RECEIPT_' + mode.upper() + '.json')
    return (json.loads(rp.read_text(encoding='utf-8')) if rp.exists() else None), runs[-1]


def main(argv):
    script, pwsh, python, scratch = Path(argv[1]), argv[2], argv[3], Path(argv[4])
    scratch.mkdir(parents=True, exist_ok=False)
    src = script.read_bytes().decode('ascii')
    rep = {'scope': 'PASS_SANDBOX_PWSH_LINUX_PATCHED_COPIES_NOT_PS51', 'cases': {}}
    cwd = scratch / 'cwd_a'
    cwd.mkdir()
    p = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-File', str(script), '-Mode', 'SelfTest'], cwd=str(cwd),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    out = p.stdout.decode('utf-8', 'replace')
    rep['cases']['A_delivered_non_windows'] = {'exit': p.returncode, 'pass': p.returncode == 2 and 'WINDOWS_TARGET_REQUIRED' in out
                                               and not any(cwd.iterdir()) and out.strip().splitlines()[-1] == FOOTER}
    plan = [
        ('selftest', None, ['-Mode', 'SelfTest'], 0),
        ('no_decisions', None, ['-Mode', 'Readback'], 2),
        ('nonwindows_payload', None, ['-Mode', 'Readback', '-D1Connection', 'USB_DOCK', '-D2WriteProtection', 'ACCEPT_OS_METADATA_EFFECTS'], 2),
        ('outcome_fail', 'fail', ['-Mode', 'Readback', '-D1Connection', 'USB_DOCK', '-D2WriteProtection', 'HARDWARE_WRITE_BLOCKER'], 1),
        ('outcome_safe_stop', 'safe-stop', ['-Mode', 'Readback', '-D1Connection', 'SATA_INTERNAL_POWERED_OFF', '-D2WriteProtection', 'ACCEPT_OS_METADATA_EFFECTS'], 130),
        ('sigint_during_child', 'sleep', ['-Mode', 'Readback', '-D1Connection', 'USB_DOCK', '-D2WriteProtection', 'ACCEPT_OS_METADATA_EFFECTS'], 130),
    ]
    for name, sub, args, want in plan:
        root = scratch / ('root_' + name)
        root.mkdir()
        ps = scratch / ('PATCHED_' + name + '.ps1')
        ps.write_bytes(build(src, python, root, sub).encode('utf-8'))
        cwd = scratch / ('cwd_' + name)
        cwd.mkdir()
        cmd = [pwsh, '-NoProfile', '-NonInteractive', '-File', str(ps)] + args
        if name == 'sigint_during_child':
            pr = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            t0 = time.time()
            started = False
            while time.time() - t0 < 120:
                if any((root / 'RUNS').glob('READBACK_*/RUN_LOG.txt')):
                    log = next((root / 'RUNS').glob('READBACK_*/RUN_LOG.txt')).read_text(encoding='utf-8', errors='replace')
                    if 'CHILD_START LABEL=READBACK' in log:
                        started = True
                        break
                time.sleep(0.1)
            time.sleep(1.0)
            os.killpg(pr.pid, signal.SIGINT)
            o, _ = pr.communicate(timeout=300)
            rc, out = pr.returncode, o.decode('utf-8', 'replace')
        else:
            q = subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
            rc, out = q.returncode, q.stdout.decode('utf-8', 'replace')
        (scratch / ('console_' + name + '.txt')).write_text(out, encoding='utf-8')
        mode = 'SelfTest' if name == 'selftest' else 'Readback'
        rec, rdir = receipt(root, mode)
        lines = [x for x in out.splitlines() if x.strip()]
        case = {'exit': rc, 'expected_exit': want, 'result': rec and rec['RESULT'], 'reason': rec and rec['REASON'],
                'readback_status': rec and rec.get('READBACK_STATUS'), 'exact_set': rec and (rec.get('run_dir_exact_set') or {}).get('status'),
                'footer_last': bool(lines) and lines[-1].endswith(FOOTER), 'cwd_untouched': not any(cwd.iterdir())}
        ok = rc == want and case['footer_last'] and case['cwd_untouched'] and rec is not None
        if name == 'selftest':
            fx = rec['fixture_matrix']
            case['fixtures'] = [(f['scenario'], f['pass']) for f in fx]
            ok = ok and all(f['pass'] for f in fx) and rec['argv_probe']['pass'] and rec['CLEANUP_STATUS'] == 'RETAINED_EMPTY_BY_DESIGN' \
                and case['exact_set'] == 'PASS'
        elif name == 'no_decisions':
            ok = ok and rec['REASON'] == 'OWNER_DECISIONS_D1_D2_REQUIRED_NO_EFFECT' and not list(rdir.glob('SNAPSHOT_*'))
        elif name == 'nonwindows_payload':
            st = [s for s in rec['stages'] if s['label'] == 'READBACK'][0]
            ok = ok and st['child_reason'] == 'WINDOWS_TARGET_REQUIRED' and case['readback_status'] == 'BLOCKED' and case['exact_set'] == 'PASS'
        elif name == 'outcome_fail':
            ok = ok and rec['RESULT'] == 'FAIL' and case['readback_status'] == 'FAIL'
        elif name == 'outcome_safe_stop':
            ok = ok and rec['RESULT'] == 'SAFE_STOP' and case['readback_status'] == 'SAFE_STOP'
        else:
            case['child_after_interrupt'] = rec.get('child_after_interrupt')
            case['started_before_signal'] = started
            cai = rec.get('child_after_interrupt') or {}
            ok = ok and started and rec['RESULT'] == 'SAFE_STOP' and cai.get('exited') is True and cai.get('killed') is False
        case['pass'] = bool(ok)
        rep['cases']['B_' + name] = case
    rep['verdict'] = 'PASS_SANDBOX_SCOPE' if all(c['pass'] for c in rep['cases'].values()) else 'FAIL'
    print(json.dumps(rep, indent=1))
    return 0 if rep['verdict'] == 'PASS_SANDBOX_SCOPE' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
