#!/usr/bin/env python3
# coding: utf-8
"""Sandbox harness for PERSEU_C2_SOURCE_LOCATOR_V002.ps1 (pwsh/Linux; NOT Windows PowerShell 5.1).

A: delivered bytes -> BLOCKED WINDOWS_TARGET_REQUIRED, exit 2, no file created.
B: PATCHED COPY (labelled; gates neutralized; roots redirected; Get-Disk/Get-Partition stubbed with
   the real HD2 serial/model): SelfTest, Locate, HD2Index, HD2Deep. The fake cold archive holds REAL
   recovered bytes with known SHA-256 (some renamed), so content identification is checked end-to-end
   with production labels. Also: HD2 absent (only HD1 serial present) -> BLOCKED.

Usage: python -I -B sandbox_locator_v002_harness.py <locator.ps1> <pwsh> <scratch> <file_with_known_sha>...
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

FOOTER = 'RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION'


def stubs(serial):
    return (r'''
function Get-Disk {
    @([pscustomobject]@{ Number = 2; FriendlyName = '%s'; SerialNumber = '  %s'; Size = [uint64]500107862016; OperationalStatus = 'Online' },
      [pscustomobject]@{ Number = 3; FriendlyName = 'Lexar SSD NM800PRO 512GB'; SerialNumber = '0000_0002'; Size = [uint64]512110190592; OperationalStatus = 'Online' })
}
function Get-Partition {
    @([pscustomobject]@{ DiskNumber = 2; PartitionNumber = 1; DriveLetter = [char]'F' },
      [pscustomobject]@{ DiskNumber = 3; PartitionNumber = 3; DriveLetter = [char]'C' })
}
''' % (('WDC WD5000AAKX-003CA0', serial) if serial.startswith('WD') else ('ST3500418AS', serial))).replace('\n', '\r\n')


def patched(src, scratch, od, hd2root, serial):
    reps = [
        ("    if ($env:OS -ne 'Windows_NT') { Stop-CslBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }\r\n", ''),
        ("    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) {", '    if ($false) {'),
        ("Set-StrictMode -Version 2.0\r\n", "Set-StrictMode -Version 2.0\r\n" + stubs(serial)),
        ("$OneDriveDownloads = 'C:\\Users\\silvi\\OneDrive\\Downloads'", "$OneDriveDownloads = '" + str(od) + "'"),
        ("$LegacyDownloads = 'C:\\Users\\silvi\\Downloads'", "$LegacyDownloads = '" + str(scratch / 'Legacy_absent') + "'"),
        ("$EvidenceRoot = 'C:\\Users\\silvi\\OneDrive\\Downloads\\PERSEU_C2_SOURCE_LOCATOR_V002_RUNS'", "$EvidenceRoot = '" + str(od / 'RUNS') + "'"),
        ("$PerseuRuns = 'D:\\PerseuRuns'", "$PerseuRuns = '" + str(scratch / 'PerseuRuns_absent') + "'"),
        ("        $archive = [System.IO.Path]::Combine(($hd2.letter + ':\\'), $Hd2ArchiveRel)\r\n",
         "        $archive = '" + str(hd2root / 'ARQUIVO_FRIO' / 'CHATGPT_DLS_20261007_093221') + "'\r\n"),
        ("        $mediaId = [System.IO.Path]::Combine(($hd2.letter + ':\\'), 'ARQUIVO_FRIO\\00_AF2_MEDIA_IDENTITY.json')\r\n",
         "        $mediaId = '" + str(hd2root / 'ARQUIVO_FRIO' / '00_AF2_MEDIA_IDENTITY.json') + "'\r\n"),
    ]
    text = src
    for old, new in reps:
        if text.count(old) != 1:
            raise SystemExit('PATCH_ANCHOR_CARDINALITY:' + old[:60])
        text = text.replace(old, new)
    return text


def run(pwsh, script, mode, cwd):
    p = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-File', str(script), '-Mode', mode],
                       cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    return p.returncode, p.stdout.decode('utf-8', 'replace')


def doc_of(od, mode):
    runs = sorted((od / 'RUNS').glob(mode.upper() + '_*'))
    if not runs:
        return None, None
    raw = (runs[-1] / ('LOCATOR_RESULT_' + mode.upper() + '.json')).read_bytes()
    return json.loads(raw.decode('utf-8')), raw


def main(argv):
    script, pwsh, scratch = Path(argv[1]), argv[2], Path(argv[3])
    known_files = [Path(x) for x in argv[4:]]
    scratch.mkdir(parents=True, exist_ok=False)
    src = script.read_bytes().decode('ascii')
    report = {'scope': 'PASS_SANDBOX_PWSH_LINUX_PATCHED_COPY_NOT_PS51', 'cases': {}}
    cwd = scratch / 'cwd_a'
    cwd.mkdir()
    rc, out = run(pwsh, script, 'HD2Deep', cwd)
    lines = [x for x in out.splitlines() if x.strip()]
    report['cases']['A_delivered_non_windows'] = {'exit': rc, 'pass': rc == 2 and 'WINDOWS_TARGET_REQUIRED' in out
                                                  and not any(cwd.iterdir()) and lines[-1] == FOOTER}
    hd2 = scratch / 'HD2'
    data = hd2 / 'ARQUIVO_FRIO' / 'CHATGPT_DLS_20261007_093221' / 'DATA' / 'OneDrive_Downloads'
    data.mkdir(parents=True)
    (hd2 / 'ARQUIVO_FRIO' / '00_AF2_MEDIA_IDENTITY.json').write_text('{"media":"AF2"}', encoding='utf-8')
    expected = {}
    for i, f in enumerate(known_files):
        name = f.name if i % 2 == 0 else ('renamed_%02d.bin' % i)
        shutil.copyfile(f, data / name)
        expected[hashlib.sha256(f.read_bytes()).hexdigest().upper()] = name
    (data / 'unrelated.txt').write_text('noise', encoding='utf-8')
    (hd2 / 'ARQUIVO_FRIO' / 'CHATGPT_DLS_20261007_093221' / 'COPY_MANIFEST.csv').write_text(
        'rel,sha\nX,' + next(iter(expected)) + '\n', encoding='utf-8')
    for serial, tag in (('WD-WCAYUS916314', 'hd2'), ('6VMCLT3M', 'only_hd1')):
        od = scratch / ('od_' + tag)
        od.mkdir()
        p = scratch / ('PATCHED_' + tag + '.ps1')
        p.write_bytes(patched(src, scratch, od, hd2, serial).encode('ascii'))
        modes = ('SelfTest', 'Locate', 'HD2Index', 'HD2Deep') if tag == 'hd2' else ('HD2Index',)
        for mode in modes:
            cwd = scratch / ('cwd_' + tag + '_' + mode)
            cwd.mkdir()
            rc, out = run(pwsh, p, mode, cwd)
            (scratch / ('console_' + tag + '_' + mode + '.txt')).write_text(out, encoding='utf-8')
            doc, raw = doc_of(od, mode)
            lines = [x for x in out.splitlines() if x.strip()]
            case = {'exit': rc, 'cwd_untouched': not any(cwd.iterdir()), 'footer_last': bool(lines) and lines[-1].endswith(FOOTER),
                    'bom_free': raw is not None and not raw.startswith(b'\xef\xbb\xbf'), 'result': doc and doc['RESULT'],
                    'gate': doc and doc['C2_SOURCE_GATE']}
            if tag == 'only_hd1':
                ok = rc == 2 and doc['REASON'] == 'HD2_SERIAL_CARDINALITY_0'
            elif mode == 'SelfTest':
                checks = doc['body']['checks']
                case['failed_checks'] = [(c['name'], c['detail']) for c in checks if not c['pass']]
                case['check_count'] = len(checks)
                ok = rc == 0 and not case['failed_checks']
            elif mode == 'Locate':
                ok = rc == 0 and doc['RESULT'] == 'PASS_INVENTORY_ONLY' and doc['C2_SOURCE_GATE'] == 'BLOCKED'
            elif mode == 'HD2Index':
                idx = doc['body']['scan']['index_files']
                hits = [h for f in idx for h in f['hits']]
                case['index_hits'] = [(h['label'], h['occurrences']) for h in hits]
                ok = rc == 0 and doc['body']['scan']['deep_scan'] is None and len(hits) == 1 \
                    and 'HD2_CONTENT_SCAN_NOT_RUN_INDEX_ONLY' in doc['c2_blockers'] and doc['body']['media_identity_file']['hash_status'] == 'HASHED'
            else:
                ds = doc['body']['scan']['deep_scan']
                got = {k['sha256']: k['label'] for k in ds['known_hits']}
                case['known_hits'] = sorted(got.values())
                case['recovered_ok'] = sum(1 for r in ds['recovered'] if r['status'] == 'RECOVERED_SHA_VERIFIED')
                rec_dir = sorted((od / 'RUNS').glob('HD2DEEP_*'))[-1] / 'RECOVERED'
                rec_ok = all(hashlib.sha256(x.read_bytes()).hexdigest().upper() in expected for x in rec_dir.iterdir())
                sources_intact = all(hashlib.sha256((data / n).read_bytes()).hexdigest().upper() == s for s, n in expected.items())
                ok = rc == 0 and set(got) == set(expected) and all(v != 'UNKNOWN_IDENTITY' for v in got.values()) \
                    and case['recovered_ok'] == len(expected) and rec_ok and sources_intact and ds['files_scanned'] == len(expected) + 1 \
                    and doc['C2_SOURCE_GATE'] == 'BLOCKED'
            case['pass'] = bool(ok and case['cwd_untouched'] and case['footer_last'] and case['bom_free'])
            report['cases']['B_' + tag + '_' + mode] = case
    report['verdict'] = 'PASS_SANDBOX_SCOPE' if all(c['pass'] for c in report['cases'].values()) else 'FAIL'
    print(json.dumps(report, indent=1))
    return 0 if report['verdict'] == 'PASS_SANDBOX_SCOPE' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
