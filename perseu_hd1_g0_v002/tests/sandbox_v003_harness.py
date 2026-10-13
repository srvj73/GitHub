#!/usr/bin/env python3
# coding: utf-8
"""Adversarial sandbox harness for PERSEU_HD1_RECON_PROBE_V003.ps1 (pwsh/Linux, NOT Windows PS 5.1).

Every case runs a PATCHED COPY (labelled, never TESTED=DELIVERED evidence): environment gates
neutralized, Get-Disk/Get-Partition/Get-Volume stubbed, roots redirected, plus one injected fault.
Case A runs the delivered bytes and expects fail-closed BLOCKED with no file created.

Usage: python -I -B sandbox_v003_harness.py <V003.ps1> <pwsh> <python3.14> <scratch_dir>
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
function Get-Disk {
    @([pscustomobject]@{ Number = 2; FriendlyName = 'WDC WD5000AAKX-003CA0'; SerialNumber = '     WD-WCAYUS916314'; Size = [uint64]500107862016; OperationalStatus = 'Online'; IsOffline = $false; IsReadOnly = $false; PartitionStyle = 'GPT'; BusType = 'SATA' },
      [pscustomobject]@{ Number = 3; FriendlyName = 'Lexar SSD NM800PRO 512GB'; SerialNumber = '0000_0002'; Size = [uint64]512110190592; OperationalStatus = 'Online'; IsOffline = $false; IsReadOnly = $false; PartitionStyle = 'GPT'; BusType = 'NVMe' })
}
function Get-Partition {
    @([pscustomobject]@{ DiskNumber = 2; PartitionNumber = 1; DriveLetter = [char]'F'; Size = [uint64]500105217024; Type = 'Basic' },
      [pscustomobject]@{ DiskNumber = 3; PartitionNumber = 3; DriveLetter = [char]'C'; Size = [uint64]511000000000; Type = 'Basic' })
}
function Get-Volume {
    @([pscustomobject]@{ DriveLetter = [char]'F'; FileSystemLabel = 'ARQUIVO_FRIO_2_500GB'; FileSystem = 'NTFS'; Size = [uint64]500105211904; SizeRemaining = [uint64]348901234688 })
}
'''

BASE = [
    ("    if ($env:OS -ne 'Windows_NT') { Stop-PhrBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }\r\n", ''),
    ("    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) {", '    if ($false) {'),
    ("Set-StrictMode -Version 2.0\r\n", "Set-StrictMode -Version 2.0\r\n" + STUBS.replace('\n', '\r\n')),
]
WORKSPACE_ANCHOR = "        $cleanupInfo.path = $workDir\r\n"
INSPECT_ANCHOR = "            $leftovers = @([System.IO.Directory]::GetFileSystemEntries($workDir))\r\n"
EXACT_ANCHOR = "    $script:Phase = 'RUN_DIR_EXACT_SET'\r\n"
RECEIPT_ANCHOR = "            Write-PhrNewText -LiteralPath $receiptPath -Text (ConvertTo-Json -InputObject $receipt -Depth 8)\r\n"
RUNID_ANCHOR = "    $runId = (Get-Date).ToString('yyyyMMdd_HHmmss_fff', $Invariant) + '_' + $PID\r\n"

FAULTS = {
    'normal': [],
    'inspection_denied': [(INSPECT_ANCHOR, "            throw (New-Object System.UnauthorizedAccessException('SIMULATED_ACCESS_DENIED'))\r\n")],
    'workspace_nonempty': [(WORKSPACE_ANCHOR, WORKSPACE_ANCHOR + "        [System.IO.File]::WriteAllText([System.IO.Path]::Combine($workDir, 'stray.tmp'), 'x')\r\n")],
    'unknown_byproduct': [(EXACT_ANCHOR, "    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($script:RunDir, 'desktop.ini'), 'x')\r\n" + EXACT_ANCHOR)],
    'receipt_write_fails': [(RECEIPT_ANCHOR, "            throw (New-Object System.IO.IOException('SIMULATED_RECEIPT_DISK_FULL'))\r\n")],
    'run_dir_preexists': [(RUNID_ANCHOR, "    $runId = 'FIXED_RUN_ID'\r\n")],
    'python_missing_primary': [],
    'unicode_space_root': [],
    'sigint_during_child': [],
}


def build(src: str, python: str, root: Path, fault: str) -> str:
    text = src
    reps = list(BASE) + [
        ("$PinnedPython = 'C:\\Users\\silvi\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe'",
         "$PinnedPython = '" + (str(root / 'no_python_here') if fault == 'python_missing_primary' else python) + "'"),
        ("$DownloadsRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads'", "$DownloadsRoot = '" + str(root) + "'"),
        ("$EvidenceRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads\\PERSEU_HD1_RECON_V003_RUNS'", "$EvidenceRoot = '" + str(root / 'RUNS') + "'"),
    ] + FAULTS[fault]
    for old, new in reps:
        if text.count(old) != 1:
            raise SystemExit(f'PATCH_ANCHOR_CARDINALITY[{fault}]:' + old[:60])
        text = text.replace(old, new)
    if text.count("'PASS_WINDOWS_") != 3:
        raise SystemExit('PATCH_LABEL_CARDINALITY')
    return text.replace("'PASS_WINDOWS_", "'SANDBOX_PATCHED_COPY_NOT_WINDOWS_")


def run(pwsh, script, mode, cwd):
    p = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-File', str(script), '-Mode', mode],
                       cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    return p.returncode, p.stdout.decode('utf-8', 'replace')


def receipt_of(root: Path, mode: str):
    runs = sorted((root / 'RUNS').glob(mode.upper() + '_*'))
    if not runs:
        return None, None
    rp = runs[-1] / ('RECEIPT_' + mode.upper() + '.json')
    return (json.loads(rp.read_text(encoding='utf-8')) if rp.exists() else None), runs[-1]


def stages(rc):
    return {s['label']: s['status'] for s in rc['stages']} if rc else {}


def main(argv):
    script, pwsh, python, scratch = Path(argv[1]), argv[2], argv[3], Path(argv[4])
    scratch.mkdir(parents=True, exist_ok=False)
    src = script.read_bytes().decode('ascii')
    report = {'scope': 'PASS_SANDBOX_PWSH_LINUX_PATCHED_COPIES_NOT_PS51', 'cases': {}}
    cwd = scratch / 'cwd_delivered'
    cwd.mkdir()
    rc, out = run(pwsh, script, 'SelfTest', cwd)
    lines = [x for x in out.splitlines() if x.strip()]
    report['cases']['A_delivered_non_windows'] = {'exit': rc, 'pass': rc == 2 and 'WINDOWS_TARGET_REQUIRED' in out
                                                  and not any(cwd.iterdir()) and lines[-1] == FOOTER}
    for fault in FAULTS:
        root = scratch / ('Down loads ação Δ' if fault == 'unicode_space_root' else 'dl_' + fault)
        root.mkdir()
        if fault == 'run_dir_preexists':
            (root / 'RUNS' / 'SELFTEST_FIXED_RUN_ID').mkdir(parents=True)
            (root / 'RUNS' / 'SELFTEST_FIXED_RUN_ID' / 'PREEXISTING_EVIDENCE.txt').write_text('keep', encoding='utf-8')
        patched = scratch / ('PATCHED_' + fault + '.ps1')
        patched.write_bytes(build(src, python, root, fault).encode('utf-8'))
        cwd = scratch / ('cwd_' + fault)
        cwd.mkdir()
        if fault == 'sigint_during_child':
            pr = subprocess.Popen([pwsh, '-NoProfile', '-NonInteractive', '-File', str(patched), '-Mode', 'SelfTest'], cwd=str(cwd),
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            t0 = time.time()
            while time.time() - t0 < 120:
                logs = list((root / 'RUNS').glob('SELFTEST_*/RUN_LOG.txt'))
                if logs and 'CHILD_START LABEL=FIXTURE_SLEEP' in logs[0].read_text(encoding='utf-8', errors='replace'):
                    break
                time.sleep(0.1)
            time.sleep(1.0)
            os.killpg(pr.pid, signal.SIGINT)
            o, _ = pr.communicate(timeout=300)
            rc, out = pr.returncode, o.decode('utf-8', 'replace')
        else:
            rc, out = run(pwsh, patched, 'SelfTest', cwd)
        (scratch / ('console_' + fault + '.txt')).write_text(out, encoding='utf-8')
        rec, rdir = receipt_of(root, 'SelfTest')
        lines = [x for x in out.splitlines() if x.strip()]
        st = stages(rec)
        case = {'exit': rc, 'footer_last': bool(lines) and lines[-1].endswith(FOOTER), 'cwd_untouched': not any(cwd.iterdir()),
                'result': rec and rec['RESULT'], 'reason': rec and rec['REASON'], 'cleanup': rec and rec['CLEANUP_STATUS'],
                'exact_set': rec and (rec['run_dir_exact_set'] or {}).get('status'), 'stages': st}
        inv_ran = st.get('INVENTORY_CHECK') == 'PASS'
        common = case['footer_last'] and case['cwd_untouched']
        if fault in ('normal', 'unicode_space_root'):
            ok = rc == 0 and rec['RESULT'] == 'PASS' and case['cleanup'] == 'RETAINED_EMPTY_BY_DESIGN' and case['exact_set'] == 'PASS' \
                and inv_ran and st.get('PAYLOAD_SELFTEST') == 'PASS' and (rdir / 'SELFTEST_WORK').is_dir() \
                and not any((rdir / 'SELFTEST_WORK').iterdir())
        elif fault == 'inspection_denied':
            ok = rc == 2 and case['cleanup'] == 'INSPECTION_FAILED_PRESERVED' and inv_ran and 'SIMULATED_ACCESS_DENIED' in json.dumps(rec)
        elif fault == 'workspace_nonempty':
            ok = rc == 2 and case['cleanup'] == 'FAILED_PRESERVED_NONEMPTY' and inv_ran and case['exact_set'] == 'FAIL_CARDINALITY' \
                and (rdir / 'SELFTEST_WORK' / 'stray.tmp').exists()
        elif fault == 'unknown_byproduct':
            ok = rc == 2 and case['exact_set'] == 'FAIL_CARDINALITY' and inv_ran and case['cleanup'] == 'RETAINED_EMPTY_BY_DESIGN' \
                and any(x.endswith('desktop.ini') for x in rec['run_dir_exact_set']['extra'])
        elif fault == 'receipt_write_fails':
            ok = rc == 2 and rec is None and 'RECEIPT_WRITE_FAILED:SIMULATED_RECEIPT_DISK_FULL PRIMARY=ALL_STAGES_PASS' in out
        elif fault == 'run_dir_preexists':
            pre = root / 'RUNS' / 'SELFTEST_FIXED_RUN_ID'
            ok = rc == 2 and 'RUN_DIR_PREEXISTS' in out and sorted(x.name for x in pre.iterdir()) == ['PREEXISTING_EVIDENCE.txt']
        elif fault == 'sigint_during_child':
            ok = rc == 130 and rec is not None and rec['RESULT'] == 'SAFE_STOP' and rec['INTERRUPTED'] is True
        elif fault == 'python_missing_primary':
            ok = rc == 2 and rec is not None and rec['REASON'].startswith('PINNED_PYTHON_NOT_FOUND') and rec['LAST_PHASE'] == 'RECEIPT'
        case['pass'] = bool(ok and common)
        report['cases']['B_' + fault] = case
    report['verdict'] = 'PASS_SANDBOX_SCOPE' if all(c['pass'] for c in report['cases'].values()) else 'FAIL'
    print(json.dumps(report, indent=1, ensure_ascii=True))
    return 0 if report['verdict'] == 'PASS_SANDBOX_SCOPE' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
