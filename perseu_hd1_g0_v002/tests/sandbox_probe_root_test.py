#!/usr/bin/env python3
# coding: utf-8
"""Sandbox integration of probe_root() on a synthetic HD1 volume made of SPARSE files.

Builds <scratch>/vol/ARQUIVO_FRIO/TOP4_V001/PAYLOAD with the exact TOP4 set names, file
counts and byte totals (apparent size via truncate; no data blocks), then checks:
  positive: PASS path, 1530 files / 414020605824 bytes, receipts hashed at TOP4 level
  negatives: one byte short, missing set, extra unknown file inside a set, symlink inside,
             payload absent, manifest NOT_PROVEN
Loads the payload module from its exact physical path (no cwd/sys.path authority).

Usage: python -I -B sandbox_probe_root_test.py <payload.py> <scratch_dir>
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys


def load(path: Path):
    spec = importlib.util.spec_from_file_location('phr_v002_under_test', str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_volume(mod, vol: Path) -> Path:
    payload = vol / 'ARQUIVO_FRIO' / 'TOP4_V001' / 'PAYLOAD'
    for name, (n, total) in mod.EXPECTED_SETS.items():
        base = payload / ('PerseuRuns' if name.startswith('PERSEU') else 'MinotauroRuns') / name
        sizes = [total // n] * n
        sizes[-1] += total - sum(sizes)
        for i, size in enumerate(sizes):
            sub = base / ('chunk_%02d' % (i // 100))
            sub.mkdir(parents=True, exist_ok=True)
            with open(sub / ('f%04d.bin' % i), 'wb') as fh:
                fh.truncate(size)
    (vol / 'ARQUIVO_FRIO' / 'TOP4_V001' / 'HD500_V003_COPY_RESULT_SYNTHETIC.json').write_bytes(b'{"synthetic":true}\n')
    return payload


def main(argv: list) -> int:
    mod = load(Path(argv[1]).resolve(strict=True))
    scratch = Path(argv[2])
    scratch.mkdir(parents=True, exist_ok=False)
    vol = scratch / 'vol'
    payload = build_volume(mod, vol)
    manifest_ok = {'identity': 'PASS', 'row_count_match': True}
    cases = {}

    blockers, fields = mod.probe_root(vol, manifest_ok)
    c = fields['metadata_census']
    top4 = fields['first_level_listings'][2]['entries']
    receipt = [e for e in top4 if e['name'].startswith('HD500_V003')]
    cases['positive'] = (blockers == [] and c['ALL_SETS_METADATA_MATCH'] and c['set_files_total'] == 1530
                         and c['set_bytes_total'] == 414020605824 and c['outside_set_files'] == 0
                         and len(receipt) == 1
                         and receipt[0]['sha256'] == hashlib.sha256(b'{"synthetic":true}\n').hexdigest().upper())

    victim = sorted(payload.rglob('f0000.bin'))[0]
    size = victim.stat().st_size
    with open(victim, 'r+b') as fh:
        fh.truncate(size - 1)
    b, f = mod.probe_root(vol, manifest_ok)
    cases['one_byte_short'] = b == ['TOP4_METADATA_MISMATCH'] and not f['metadata_census']['ALL_SETS_METADATA_MATCH']
    with open(victim, 'r+b') as fh:
        fh.truncate(size)

    extra = victim.parent / 'UNKNOWN_EXTRA.bin'
    extra.write_bytes(b'x')
    b, _ = mod.probe_root(vol, manifest_ok)
    cases['extra_file_in_set'] = b == ['TOP4_METADATA_MISMATCH']
    extra.unlink()

    link = victim.parent / 'LINK'
    os.symlink(victim.parent, link, target_is_directory=True)
    b, _ = mod.probe_root(vol, manifest_ok)
    cases['symlink_inside'] = len(b) == 1 and b[0].startswith('CENSUS_PAYLOAD_REPARSE_REFUSED:')
    link.unlink()

    b, _ = mod.probe_root(vol, {'identity': 'NOT_PROVEN'})
    cases['manifest_not_proven'] = b == ['SOURCE_MANIFEST_IDENTITY_NOT_PROVEN']

    minotauro = next(payload.rglob('MINOTAURO_R1R11_FULL_CORRECT_C1_V001_20260928'))
    moved = scratch / 'moved_out'
    shutil.move(str(minotauro), str(moved))
    b, f = mod.probe_root(vol, manifest_ok)
    cases['missing_set'] = (b == ['TOP4_METADATA_MISMATCH']
                            and f['metadata_census']['sets']['MINOTAURO_R1R11_FULL_CORRECT_C1_V001_20260928']['occurrences'] == 0)
    shutil.move(str(moved), str(minotauro))

    b, _ = mod.probe_root(vol, manifest_ok)
    cases['restored_positive'] = b == []

    shutil.rmtree(vol / 'ARQUIVO_FRIO' / 'TOP4_V001' / 'PAYLOAD')
    b, f = mod.probe_root(vol, manifest_ok)
    cases['payload_absent'] = b == ['TOP4_PAYLOAD_NOT_FOUND_AT_DOCUMENTED_PATH'] and f['metadata_census'] is None

    shutil.rmtree(vol)
    report = {'scope': 'PASS_SANDBOX_LINUX_SPARSE_FIXTURE_NOT_WINDOWS_NTFS', 'python': sys.version.split()[0],
              'cases': cases, 'scratch_cleanup': 'VOLUME_FIXTURE_REMOVED',
              'verdict': 'PASS_SANDBOX_SCOPE' if all(cases.values()) else 'FAIL'}
    print(json.dumps(report, indent=1))
    return 0 if report['verdict'] == 'PASS_SANDBOX_SCOPE' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
