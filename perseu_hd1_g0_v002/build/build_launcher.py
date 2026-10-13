#!/usr/bin/env python3
# coding: utf-8
"""Deterministic builder: template (ASCII, LF) -> dist/PERSEU_C2_FULL_LAUNCHER_V001.ps1 (ASCII, CRLF, no BOM)."""
import hashlib
from pathlib import Path
import sys


def main(argv):
    root = Path(argv[1]).resolve(strict=True)
    src = (root / 'build' / 'PERSEU_C2_FULL_LAUNCHER_V001.ps1.template').read_bytes()
    src.decode('ascii')
    if b'\r' in src or src.startswith(b'\xef\xbb\xbf') or b'@@' in src:
        sys.stderr.write('TEMPLATE_CONTRACT_VIOLATION\n')
        return 2
    data = src.replace(b'\n', b'\r\n')
    out = root / 'dist' / 'PERSEU_C2_FULL_LAUNCHER_V001.ps1'
    with open(out, 'xb') as dst:
        dst.write(data)
    print(f'LAUNCHER={out}')
    print(f'LAUNCHER_SHA256={hashlib.sha256(data).hexdigest().upper()}')
    print(f'LAUNCHER_BYTES={len(data)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
