#!/usr/bin/env python3
# coding: utf-8
"""Sandbox harness for the generated wrapper (pwsh on Linux; NOT Windows PowerShell 5.1).

Part A runs the exact delivered bytes and expects a fail-closed BLOCKED with no file created.
Part B runs a PATCHED COPY (environment gates neutralized, Get-Disk/Get-Partition/Get-Volume
stubbed, paths redirected to a scratch root). Part B exercises wrapper logic only; its bytes
differ from the delivered wrapper and it is never evidence of TESTED=DELIVERED.

Usage: python -I -B sandbox_wrapper_harness.py <wrapper.ps1> <pwsh> <python3.14> <scratch_dir>
"""
import json
import os
from pathlib import Path
import subprocess
import sys

STUBS = r'''
function Get-Disk {
    @(
        [pscustomobject]@{ Number = 2; FriendlyName = 'WDC WD5000AAKX-003CA0'; SerialNumber = '     WD-WCAYUS916314'; Size = [uint64]500107862016; OperationalStatus = 'Online'; IsOffline = $false; IsReadOnly = $false; PartitionStyle = 'GPT'; BusType = 'SATA' },
        [pscustomobject]@{ Number = 3; FriendlyName = 'Lexar SSD NM800PRO 512GB'; SerialNumber = '0000_0002'; Size = [uint64]512110190592; OperationalStatus = 'Online'; IsOffline = $false; IsReadOnly = $false; PartitionStyle = 'GPT'; BusType = 'NVMe' }
    )
}
function Get-Partition {
    @(
        [pscustomobject]@{ DiskNumber = 2; PartitionNumber = 1; DriveLetter = [char]'F'; Size = [uint64]500105217024; Type = 'Basic' },
        [pscustomobject]@{ DiskNumber = 3; PartitionNumber = 1; DriveLetter = [char]0; Size = [uint64]104857600; Type = 'System' },
        [pscustomobject]@{ DiskNumber = 3; PartitionNumber = 3; DriveLetter = [char]'C'; Size = [uint64]511000000000; Type = 'Basic' }
    )
}
function Get-Volume {
    @([pscustomobject]@{ DriveLetter = [char]'F'; FileSystemLabel = 'ARQUIVO_FRIO_2_500GB'; FileSystem = 'NTFS'; Size = [uint64]500105211904; SizeRemaining = [uint64]348901234688 })
}
'''


def patch(text: str, python: str, root: Path) -> str:
    reps = [
        ("    if ($env:OS -ne 'Windows_NT') { Stop-PhrBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }\r\n", ''),
        ("    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) {", '    if ($false) {'),
        ("$PinnedPython = 'C:\\Users\\silvi\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe'",
         "$PinnedPython = '" + python + "'"),
        ("$DownloadsRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads'", "$DownloadsRoot = '" + str(root) + "'"),
        ("$EvidenceRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads\\PERSEU_HD1_RECON_V002_RUNS'",
         "$EvidenceRoot = '" + str(root / 'RUNS') + "'"),
        ("Set-StrictMode -Version 2.0\r\n", "Set-StrictMode -Version 2.0\r\n" + STUBS.replace('\n', '\r\n')),
    ]
    for old, new in reps:
        if text.count(old) != 1:
            raise SystemExit('PATCH_ANCHOR_CARDINALITY:' + old[:60])
        text = text.replace(old, new)
    # Patched-copy receipts must never carry a Windows target-runtime claim.
    if text.count("'PASS_WINDOWS_") != 3:
        raise SystemExit('PATCH_LABEL_CARDINALITY')
    return text.replace("'PASS_WINDOWS_", "'SANDBOX_PATCHED_COPY_NOT_WINDOWS_")


def run(pwsh: str, script: Path, mode: str, cwd: Path) -> tuple:
    p = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-File', str(script), '-Mode', mode],
                       cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    return p.returncode, p.stdout.decode('utf-8', 'replace')


def main(argv: list) -> int:
    wrapper, pwsh, python, scratch = Path(argv[1]), argv[2], argv[3], Path(argv[4])
    scratch.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'PASS_SANDBOX_PWSH_LINUX_ONLY_NOT_PS51', 'cases': {}}
    empty_cwd = scratch / 'empty_cwd'
    empty_cwd.mkdir()
    rc, out = run(pwsh, wrapper, 'SelfTest', empty_cwd)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    a_ok = (rc == 2 and 'WINDOWS_TARGET_REQUIRED' in out and not any(empty_cwd.iterdir())
            and lines[0].startswith('RESULT_CONTEXT=ChatGPT | PROJECT=Perseu MT5 (Astra)')
            and lines[-1] == 'RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION')
    report['cases']['A_delivered_bytes_non_windows_blocked'] = {'exit': rc, 'pass': a_ok, 'cwd_untouched': not any(empty_cwd.iterdir())}
    root = scratch / 'downloads'
    root.mkdir()
    patched = scratch / 'PATCHED_COPY_NOT_DELIVERED.ps1'
    patched.write_bytes(patch(wrapper.read_bytes().decode('ascii'), python, root).encode('ascii'))
    expectations = {'SelfTest': 0, 'Inventory': 0, 'Probe': 2}
    for mode, want in expectations.items():
        cwd = scratch / ('cwd_' + mode)
        cwd.mkdir()
        rc, out = run(pwsh, patched, mode, cwd)
        runs = sorted((root / 'RUNS').glob(mode.upper() + '_*'))
        receipt = json.loads((runs[-1] / ('RECEIPT_' + mode.upper() + '.json')).read_text(encoding='utf-8')) if runs else None
        lines = [ln for ln in out.splitlines() if ln.strip()]
        case = {'exit': rc, 'expected_exit': want, 'cwd_untouched': not any(cwd.iterdir()),
                'footer_last': lines[-1].endswith('RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION'),
                'receipt_result': receipt and receipt['RESULT'], 'receipt_reason': receipt and receipt['REASON'],
                'stages': receipt and [(s['label'], s['status'], s['reason']) for s in receipt['stages']]}
        if mode == 'SelfTest' and receipt:
            case['argv_probe'] = receipt['argv_probe']
            case['int64'] = receipt['int64_vector']
            case['fixtures'] = [(f['scenario'], f['status'], f['reason'], f['pass']) for f in receipt['fixture_matrix']]
            case['reconcile'] = receipt['fixture_reconcile']
            case['bom_free_receipt'] = not (runs[-1] / 'RECEIPT_SELFTEST.json').read_bytes().startswith(b'\xef\xbb\xbf')
            case['selftest_work_removed'] = not (runs[-1] / 'SELFTEST_WORK').exists()
        if mode == 'Probe' and receipt:
            case['binding_stability'] = receipt['binding_stability']
        case['pass'] = rc == want and case['cwd_untouched'] and case['footer_last']
        if mode == 'SelfTest':
            case['pass'] = case['pass'] and receipt['argv_probe']['pass'] and receipt['int64_vector']['pass'] \
                and all(f[3] for f in case['fixtures']) and case['bom_free_receipt'] and case['selftest_work_removed']
        if mode == 'Probe':
            probe_stage = [s for s in receipt['stages'] if s['label'] == 'PROBE']
            case['probe_child_reason'] = probe_stage[0]['child_reason'] if probe_stage else None
            case['pass'] = case['pass'] and case['probe_child_reason'] == 'WINDOWS_TARGET_REQUIRED' \
                and receipt['binding_stability']['stable'] is False
        report['cases']['B_patched_' + mode] = case
        (scratch / ('console_' + mode + '.txt')).write_text(out, encoding='utf-8')
    report['verdict'] = 'PASS_SANDBOX_SCOPE' if all(c['pass'] for c in report['cases'].values()) else 'FAIL'
    print(json.dumps(report, indent=1, ensure_ascii=True, default=str))
    return 0 if report['verdict'] == 'PASS_SANDBOX_SCOPE' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
