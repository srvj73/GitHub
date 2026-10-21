#!/usr/bin/env python3
"""Rebuild CDT21_V003_B06_INDEPENDENT_DISPATCH_READY.zip byte-for-byte from its transport parts.
Usage: python RECONSTRUIR_PACOTE_B06.py <PARTE_01.zip> ... <PARTE_NN.zip> <NEW_OUTPUT_DIR>
Reads only the transport ZIPs; writes one new file; executes nothing from the package.
"""
import hashlib, io, json, sys, zipfile
from pathlib import Path
H = lambda b: hashlib.sha256(b).hexdigest().upper()
def main(argv):
    if len(argv) < 3:
        raise SystemExit('USAGE: RECONSTRUIR_PACOTE_B06.py <PARTE_01.zip> ... <NEW_OUTPUT_DIR>')
    parts, out = [Path(p) for p in argv[:-1]], Path(argv[-1])
    if not out.is_dir():
        raise SystemExit('OUTPUT_DIR_MUST_EXIST')
    chunks, manifests = {}, set()
    for p in parts:
        with zipfile.ZipFile(p) as z:
            if z.testzip() is not None:
                raise SystemExit('TRANSPORT_CRC_FAILED:' + p.name)
            raw_m = z.read('TRANSPORT_MANIFEST.json'); manifests.add(raw_m); m = json.loads(raw_m)
            mine = [c for c in m['chunks'] if c['chunk'] in z.namelist()]
            if len(mine) != 1:
                raise SystemExit('TRANSPORT_PART_SHAPE:' + p.name)
            c = mine[0]; data = z.read(c['chunk'])
            if len(data) != c['bytes'] or H(data) != c['sha256']:
                raise SystemExit('CHUNK_SHA_MISMATCH:' + c['chunk'])
            if c['index'] in chunks:
                raise SystemExit('DUPLICATE_PART:' + str(c['index']))
            chunks[c['index']] = data
    if len(manifests) != 1:
        raise SystemExit('TRANSPORT_MANIFEST_DIFFERS')
    m = json.loads(manifests.pop())
    if sorted(chunks) != list(range(1, len(m['chunks']) + 1)):
        raise SystemExit('MISSING_PARTS:have=' + str(sorted(chunks)) + ':need=' + str(len(m['chunks'])))
    original = b''.join(chunks[i] for i in sorted(chunks))
    if len(original) != m['original_bytes'] or H(original) != m['original_sha256']:
        raise SystemExit('ORIGINAL_SHA_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        if z.testzip() is not None:
            raise SystemExit('ORIGINAL_CRC_FAILED')
        dm = json.loads(z.read('DISPATCH_MANIFEST.json'))
        for e in dm['members']:
            if H(z.read(e['path'])) != e['sha256']:
                raise SystemExit('DISPATCH_MEMBER_SHA:' + e['path'])
    target = out / m['original_name']
    with open(target, 'xb') as f:
        f.write(original)
    if H(target.read_bytes()) != m['original_sha256']:
        raise SystemExit('POST_WRITE_MISMATCH')
    print('RECONSTRUCTION=PASS_BYTES_EXACT')
    print('ORIGINAL=' + str(target))
    print('ORIGINAL_SHA256=' + m['original_sha256'])
    print('DISPATCH_MEMBERS_VERIFIED=' + str(len(dm['members'])))
if __name__ == '__main__':
    main(sys.argv[1:])
