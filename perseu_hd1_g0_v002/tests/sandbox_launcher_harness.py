#!/usr/bin/env python3
# coding: utf-8
"""Sandbox harness for PERSEU_C2_FULL_LAUNCHER_V001.ps1 (pwsh/Linux; NOT Windows PowerShell 5.1).

A: delivered bytes -> BLOCKED WINDOWS_TARGET_REQUIRED, exit 2, no file created.
B (PATCHED COPIES, labelled): SelfTest; Preflight without lock; synthetic lock vs PRODUCTION invariants
   (must be rejected, nothing launched); Run positive path with FIXTURE invariants patched in (child via
   pwsh -File writes RUN_STATUS PASS -> exit 0, C2_FULL_STARTED=YES); Run with failing runner (rc 7 -> exit 3).

Usage: python -I -B sandbox_launcher_harness.py <launcher.ps1> <pwsh> <scratch>
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

FOOTER = 'RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION'
STUBS = r'''
function Get-CimInstance { param([string]$ClassName) if ($ClassName -eq 'Win32_ComputerSystem') { return [pscustomobject]@{ TotalPhysicalMemory = [uint64]34359738368 } }; return @() }
function py { }
'''
H = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()


def fixture(root: Path, rc: int):
    inst = root / 'INSTALL'
    inst.mkdir(parents=True)
    out = root / 'D' / 'PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C2_202608'
    for n in ('perseu_parallel_auto.py', 'perseu_r4r9_accel.py', 'perseu_exploratorio.py'):
        (inst / n).write_text('synthetic ' + n, encoding='utf-8')
    d1 = root / 'D1_CERT.json'
    d1.write_text('{"d1":1}', encoding='utf-8')
    pre = root / 'PREREG_V004.zip'
    pre.write_text('v004', encoding='utf-8')
    entry = inst / 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1'
    body = (f"$D1Cert = '{d1}'\r\n$Out = '{out}'\r\n& py -B (Join-Path $PSScriptRoot 'perseu_parallel_auto.py') --start 2026-08-01 --end 2026-08-31\r\n"
            f"[void][System.IO.Directory]::CreateDirectory($Out)\r\n")
    if rc == 'sleep':
        body += "Start-Sleep -Seconds 20\r\nexit 0\r\n"
    else:
        body += ("[System.IO.File]::WriteAllText([System.IO.Path]::Combine($Out, 'RUN_STATUS.json'), '{\"state\":\"PASS\"}')\r\nexit 0\r\n"
                 if rc == 0 else f"exit {rc}\r\n")
    entry.write_text(body, encoding='utf-8')
    inv = {'runner': H(inst / 'perseu_parallel_auto.py'), 'accel': H(inst / 'perseu_r4r9_accel.py'), 'core': H(inst / 'perseu_exploratorio.py'),
           'd1': H(d1), 'c2_wrapper': H(entry), 'out': str(out)}
    lock = {'schema': 'PERSEU_C2_SOURCE_LOCK_V001', 'install_root': str(inst), 'entry_wrapper': entry.name, 'out': str(out),
            'range': ['2026-08-01', '2026-08-31'],
            'files': {'perseu_parallel_auto.py': inv['runner'], 'perseu_r4r9_accel.py': inv['accel'], 'perseu_exploratorio.py': inv['core'], entry.name: inv['c2_wrapper']},
            'd1_cert': {'path': str(d1), 'sha256': inv['d1']}, 'prereg': {'version': 'V004', 'path': str(pre), 'sha256': H(pre)}, 'min_free_gb_out_drive': 0}
    lp = root / 'C2_SOURCE_LOCK_V001.json'
    lp.write_text(json.dumps(lock, indent=1), encoding='utf-8')
    return inv, lp, out


def build(src, pwsh, root, inv=None):
    reps = [
        ("    if ($env:OS -ne 'Windows_NT') { Stop-PflBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }\r\n", ''),
        ("    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) {", '    if ($false) {'),
        ("Set-StrictMode -Version 2.0\r\n", "Set-StrictMode -Version 2.0\r\n" + STUBS.replace('\n', '\r\n')),
        ("$DownloadsRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads'", "$DownloadsRoot = '" + str(root) + "'"),
        ("$EvidenceRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads\\PERSEU_C2_FULL_LAUNCHER_V001_RUNS'", "$EvidenceRoot = '" + str(root / 'RUNS') + "'"),
        ("$PowerShellExe = [System.IO.Path]::Combine([string]$env:WINDIR, 'System32\\WindowsPowerShell\\v1.0\\powershell.exe')", "$PowerShellExe = '" + pwsh + "'"),
        ("$MinFreeGbFloor = 100.0", "$MinFreeGbFloor = 0.0"),
    ]
    if inv:
        for k, v in inv.items():
            old = {'runner': "    runner = '28DF85A4BF87B859230C931042C493CD6B4E57FE8698135C3D771C56E466E68C'",
                   'accel': "    accel = '042FA9CB7DB2DE26BD64F82B41B2A1977B05C65509E2038239BDC972E766F2E5'",
                   'core': "    core = 'A331F308182766C299B067BE2035EB071E01019C28A6C20DD6DF09B1AB92607F'",
                   'd1': "    d1 = '93092E9A8FB656CF5696087CE863C1F7B5F1601B52621993081A98A49B2F628D'",
                   'c2_wrapper': "    c2_wrapper = '53C8A1FBAA0C836DCB616789BD0C1D7264CCA6E97C8780E364FA05204E088ADD'",
                   'out': "    out = 'D:\\PerseuRuns\\PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C2_202608'"}[k]
            reps.append((old, old.split('=')[0] + "= '" + v + "'"))
    text = src
    for old, new in reps:
        if text.count(old) != 1:
            raise SystemExit('PATCH_ANCHOR_CARDINALITY:' + old[:60])
        text = text.replace(old, new)
    return text


def run(pwsh, script, args, cwd):
    p = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-File', str(script)] + args, cwd=str(cwd),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    return p.returncode, p.stdout.decode('utf-8', 'replace')


def receipt(root, mode):
    runs = sorted((root / 'RUNS').glob(mode.upper() + '_*'))
    return json.loads((runs[-1] / ('RECEIPT_' + mode.upper() + '.json')).read_text(encoding='utf-8')) if runs else None


def main(argv):
    script, pwsh, scratch = Path(argv[1]), argv[2], Path(argv[3])
    scratch.mkdir(parents=True, exist_ok=False)
    src = script.read_bytes().decode('ascii')
    rep = {'scope': 'PASS_SANDBOX_PWSH_LINUX_PATCHED_COPIES_NOT_PS51', 'cases': {}}
    cwd = scratch / 'cwd_a'
    cwd.mkdir()
    rc, out = run(pwsh, script, ['-Mode', 'SelfTest'], cwd)
    rep['cases']['A_delivered_non_windows'] = {'exit': rc, 'pass': rc == 2 and 'WINDOWS_TARGET_REQUIRED' in out and not any(cwd.iterdir())
                                               and out.strip().splitlines()[-1] == FOOTER}
    inv_ok, lock_ok, out_ok = fixture(scratch / 'fx_ok', 0)
    inv_bad, lock_bad, out_bad = fixture(scratch / 'fx_fail', 7)
    inv_slp, lock_slp, out_slp = fixture(scratch / 'fx_sleep', 'sleep')
    lk = json.loads(lock_ok.read_text(encoding='utf-8'))
    src_dir = lk['install_root']
    lk['install_root'] = str(scratch / 'fx_ok' / 'INSTALL_RESTORED_CLI')
    lock_inst = scratch / 'fx_ok' / 'C2_SOURCE_LOCK_V001_INSTALL_CLI.json'
    lock_inst.write_text(json.dumps(lk, indent=1), encoding='utf-8')
    plan = [
        ('selftest', None, ['-Mode', 'SelfTest'], 0),
        ('preflight_no_lock', None, ['-Mode', 'Preflight'], 2),
        ('preflight_prod_invariants', None, ['-Mode', 'Preflight', '-SourceLockPath', str(lock_ok), '-SourceLockSha256', H(lock_ok)], 2),
        ('run_prod_invariants_blocked', None, ['-Mode', 'Run', '-SourceLockPath', str(lock_ok), '-SourceLockSha256', H(lock_ok)], 2),
        ('preflight_fixture_ready', inv_ok, ['-Mode', 'Preflight', '-SourceLockPath', str(lock_ok), '-SourceLockSha256', H(lock_ok)], 0),
        ('run_fixture_pass', inv_ok, ['-Mode', 'Run', '-SourceLockPath', str(lock_ok), '-SourceLockSha256', H(lock_ok)], 0),
        ('run_fixture_runner_fail', inv_bad, ['-Mode', 'Run', '-SourceLockPath', str(lock_bad), '-SourceLockSha256', H(lock_bad)], 3),
        ('install_fixture_cli', inv_ok, ['-Mode', 'Install', '-SourceLockPath', str(lock_inst), '-SourceLockSha256', H(lock_inst), '-SourceDir', src_dir], 0),
        ('run_fixture_sigint', inv_slp, ['-Mode', 'Run', '-SourceLockPath', str(lock_slp), '-SourceLockSha256', H(lock_slp)], 130),
    ]
    for name, inv, args, want in plan:
        root = scratch / ('root_' + name)
        root.mkdir()
        ps = scratch / ('PATCHED_' + name + '.ps1')
        ps.write_bytes(build(src, pwsh, root, inv).encode('utf-8'))
        cwd = scratch / ('cwd_' + name)
        cwd.mkdir()
        if name == 'run_fixture_sigint':
            pr = subprocess.Popen([pwsh, '-NoProfile', '-NonInteractive', '-File', str(ps)] + args, cwd=str(cwd),
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            t0 = time.time()
            while time.time() - t0 < 120:
                logs = list((root / 'RUNS').glob('RUN_*/RUN_LOG.txt'))
                if logs and 'CHILD_START' in logs[0].read_text(encoding='utf-8', errors='replace'):
                    break
                time.sleep(0.1)
            time.sleep(1.5)
            os.killpg(pr.pid, signal.SIGINT)
            o, _ = pr.communicate(timeout=300)
            rc, out = pr.returncode, o.decode('utf-8', 'replace')
        else:
            rc, out = run(pwsh, ps, args, cwd)
        (scratch / ('console_' + name + '.txt')).write_text(out, encoding='utf-8')
        rec = receipt(root, args[1])
        lines = [x for x in out.splitlines() if x.strip()]
        case = {'exit': rc, 'expected_exit': want, 'result': rec and rec['RESULT'], 'reason': rec and rec['REASON'],
                'full_started': rec and rec['C2_FULL_STARTED'], 'footer_last': bool(lines) and lines[-1].endswith(FOOTER),
                'cwd_untouched': not any(cwd.iterdir())}
        ok = rc == want and rec is not None and case['footer_last'] and case['cwd_untouched']
        if name == 'selftest':
            checks = rec['body']['selftest']['checks']
            case['checks'] = [(c['name'], c['pass']) for c in checks]
            ok = ok and len(checks) == 16 and all(c['pass'] for c in checks)
        elif name == 'preflight_no_lock':
            ok = ok and rec['REASON'] == 'SOURCE_LOCK_PATH_AND_SHA_REQUIRED'
        elif name in ('preflight_prod_invariants', 'run_prod_invariants_blocked'):
            bl = rec['body']['preflight']['lock']['blockers']
            case['blockers'] = bl
            ok = ok and rec['C2_FULL_STARTED'] == 'NO' and any('NOT_INVARIANT' in b for b in bl) and not out_ok.exists()
        elif name == 'preflight_fixture_ready':
            ok = ok and rec['RESULT'] == 'PASS_PREFLIGHT_DRY_RUN' and rec['C2_FULL_STARTED'] == 'NO' and not out_ok.exists()
        elif name == 'run_fixture_pass':
            ok = ok and rec['RESULT'] == 'PASS_C2_FULL_RUN_EXIT_0' and rec['C2_FULL_STARTED'] == 'YES' \
                and rec['body']['run']['identities_unchanged_after_run'] is True and (out_ok / 'RUN_STATUS.json').exists()
        elif name == 'install_fixture_cli':
            ok = ok and rec['RESULT'] == 'PASS_INSTALL_VERIFIED' and len(rec['body']['install']['copied']) == 4 \
                and all(x['verified'] for x in rec['body']['install']['copied']) and rec['C2_FULL_STARTED'] == 'NO'
        elif name == 'run_fixture_sigint':
            ok = ok and rec['RESULT'] == 'SAFE_STOP' and rec['INTERRUPTED'] is True and rec['C2_FULL_STARTED'] == 'YES' \
                and rec['PARTIAL_EFFECT'].startswith('YES')
        else:
            ok = ok and rec['RESULT'] == 'FAIL' and rec['body']['run']['child']['exit_code'] == 7 and rec['PARTIAL_EFFECT'].startswith('YES')
        case['pass'] = bool(ok)
        rep['cases']['B_' + name] = case
    rep['verdict'] = 'PASS_SANDBOX_SCOPE' if all(c['pass'] for c in rep['cases'].values()) else 'FAIL'
    print(json.dumps(rep, indent=1))
    return 0 if rep['verdict'] == 'PASS_SANDBOX_SCOPE' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
