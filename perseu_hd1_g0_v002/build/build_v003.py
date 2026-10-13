#!/usr/bin/env python3
# coding: utf-8
"""Deterministic builder: embeds the exact payload bytes into the PS1 wrapper.

Usage: python -I -B build_v003.py <candidate_root>
Writes <candidate_root>/dist/PERSEU_HD1_RECON_PROBE_V003.ps1 (ASCII, CRLF, no BOM).
Refuses to overwrite an existing output (new identity requires a new build dir).
"""
import base64
import hashlib
from pathlib import Path
import sys

PAYLOAD_REL = Path('src') / 'PERSEU_HD1_RECON_PROBE_V002.py'
TEMPLATE_REL = Path('build') / 'PERSEU_HD1_RECON_PROBE_V003.ps1.template'
OUT_REL = Path('dist') / 'PERSEU_HD1_RECON_PROBE_V003.ps1'


def main(argv: list) -> int:
    if len(argv) != 2:
        sys.stderr.write('usage: build_v003.py <candidate_root>\n')
        return 2
    root = Path(argv[1]).resolve(strict=True)
    payload = (root / PAYLOAD_REL).read_bytes()
    if payload.startswith(b'\xef\xbb\xbf') or b'\r' in payload:
        sys.stderr.write('PAYLOAD_MUST_BE_UTF8_NO_BOM_LF\n')
        return 2
    payload.decode('ascii')  # payload is kept ASCII-only on purpose
    template = (root / TEMPLATE_REL).read_bytes().decode('ascii')
    if '\r' in template:
        sys.stderr.write('TEMPLATE_MUST_BE_LF\n')
        return 2
    b64 = base64.b64encode(payload).decode('ascii')
    b64_lines = '\n'.join(b64[i:i + 76] for i in range(0, len(b64), 76))
    fills = {
        '@@PAYLOAD_SHA256@@': hashlib.sha256(payload).hexdigest().upper(),
        '@@PAYLOAD_BYTES@@': str(len(payload)),
        '@@PAYLOAD_B64@@': b64_lines,
    }
    text = template
    for key, value in fills.items():
        if text.count(key) != 1:
            sys.stderr.write(f'PLACEHOLDER_CARDINALITY_{key}_{text.count(key)}\n')
            return 2
        text = text.replace(key, value)
    if '@@' in text:
        sys.stderr.write('PLACEHOLDER_RESIDUE\n')
        return 2
    data = text.replace('\n', '\r\n').encode('ascii')
    out = root / OUT_REL
    out.parent.mkdir(exist_ok=True)
    with open(out, 'xb') as dst:
        dst.write(data)
    print(f'PAYLOAD_SHA256={fills["@@PAYLOAD_SHA256@@"]}')
    print(f'PAYLOAD_BYTES={len(payload)}')
    print(f'WRAPPER={out}')
    print(f'WRAPPER_SHA256={hashlib.sha256(data).hexdigest().upper()}')
    print(f'WRAPPER_BYTES={len(data)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
