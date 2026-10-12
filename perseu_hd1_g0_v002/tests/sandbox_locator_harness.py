#!/usr/bin/env python3
# coding: utf-8
"""Sandbox harness for PERSEU_C2_SOURCE_LOCATOR_V001.ps1 (pwsh on Linux; NOT Windows PowerShell 5.1).

A: delivered bytes -> BLOCKED WINDOWS_TARGET_REQUIRED, exit 2, cwd untouched, context+footer lines.
B: PATCHED COPY (environment gates neutralized, absolute roots redirected to scratch) runs
   SelfTest (exit 0) and Locate over an empty fake environment (exit 0, C2_SOURCE_GATE=BLOCKED).
   The patched copy is never TESTED=DELIVERED evidence.

Usage: python -I -B sandbox_locator_harness.py <locator.ps1> <pwsh> <scratch_dir>
"""
import json
from pathlib import Path
import subprocess
import sys

FOOTER = 'RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION'


def run(pwsh, script, mode, cwd):
    p = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-File', str(script), '-Mode', mode],
                       cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    return p.returncode, p.stdout.decode('utf-8', 'replace')


def main(argv):
    script, pwsh, scratch = Path(argv[1]), argv[2], Path(argv[3])
    scratch.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'PASS_SANDBOX_PWSH_LINUX_ONLY_NOT_PS51', 'cases': {}}
    cwd = scratch / 'cwd_a'
    cwd.mkdir()
    rc, out = run(pwsh, script, 'Locate', cwd)
    lines = [x for x in out.splitlines() if x.strip()]
    report['cases']['A_delivered_non_windows_blocked'] = {
        'exit': rc, 'pass': rc == 2 and 'WINDOWS_TARGET_REQUIRED' in out and not any(cwd.iterdir())
        and lines[0].startswith('RESULT_CONTEXT=ChatGPT') and lines[-1] == FOOTER}
    od = scratch / 'OneDriveDownloads'
    od.mkdir()
    text = script.read_bytes().decode('ascii')
    reps = [
        ("    if ($env:OS -ne 'Windows_NT') { Stop-CslBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }\r\n", ''),
        ("    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) {", '    if ($false) {'),
        ("$OneDriveDownloads = 'C:\\Users\\silvi\\OneDrive\\Downloads'", "$OneDriveDownloads = '" + str(od) + "'"),
        ("$LegacyDownloads = 'C:\\Users\\silvi\\Downloads'", "$LegacyDownloads = '" + str(scratch / 'LegacyDownloads_absent') + "'"),
        ("$EvidenceRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads\\PERSEU_C2_SOURCE_LOCATOR_V001_RUNS'",
         "$EvidenceRoot = '" + str(od / 'PERSEU_C2_SOURCE_LOCATOR_V001_RUNS') + "'"),
        ("$PerseuRuns = 'D:\\PerseuRuns'", "$PerseuRuns = '" + str(scratch / 'PerseuRuns_absent') + "'"),
    ]
    for old, new in reps:
        if text.count(old) != 1:
            raise SystemExit('PATCH_ANCHOR_CARDINALITY:' + old[:50])
        text = text.replace(old, new)
    patched = scratch / 'PATCHED_COPY_NOT_DELIVERED.ps1'
    patched.write_bytes(text.encode('ascii'))
    for mode, want in (('SelfTest', 0), ('Locate', 0)):
        cwd = scratch / ('cwd_' + mode)
        cwd.mkdir()
        rc, out = run(pwsh, patched, mode, cwd)
        (scratch / ('console_' + mode + '.txt')).write_text(out, encoding='utf-8')
        runs = sorted((od / 'PERSEU_C2_SOURCE_LOCATOR_V001_RUNS').glob(mode.upper() + '_*'))
        raw = (runs[-1] / ('LOCATOR_RESULT_' + mode.upper() + '.json')).read_bytes() if runs else b''
        doc = json.loads(raw.decode('utf-8')) if raw else {}
        lines = [x for x in out.splitlines() if x.strip()]
        case = {'exit': rc, 'expected_exit': want, 'cwd_untouched': not any(cwd.iterdir()),
                'footer_last': bool(lines) and lines[-1].endswith(FOOTER), 'bom_free': not raw.startswith(b'\xef\xbb\xbf'),
                'result': doc.get('RESULT'), 'gate': doc.get('C2_SOURCE_GATE'), 'blockers': doc.get('c2_blockers')}
        if mode == 'SelfTest':
            checks = doc['body']['checks']
            case['checks'] = [(c['name'], c['pass'], c['detail']) for c in checks]
            case['pass'] = rc == 0 and all(c['pass'] for c in checks) and doc['RESULT'] == 'PASS_SELFTEST_ONLY'
        else:
            case['pass'] = rc == 0 and doc['RESULT'] == 'PASS_INVENTORY_ONLY' and doc['C2_SOURCE_GATE'] == 'BLOCKED'
        case['pass'] = case['pass'] and case['cwd_untouched'] and case['footer_last'] and case['bom_free']
        report['cases']['B_patched_' + mode] = case
    report['verdict'] = 'PASS_SANDBOX_SCOPE' if all(c['pass'] for c in report['cases'].values()) else 'FAIL'
    print(json.dumps(report, indent=1))
    return 0 if report['verdict'] == 'PASS_SANDBOX_SCOPE' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
