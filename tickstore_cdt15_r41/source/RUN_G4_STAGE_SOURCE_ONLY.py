"""Isolated directed test runner. Never loads productive ENTRY or performs admission."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import unittest

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest().upper()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence',required=True)
    # Offline mode is solely for producer preflight and cannot emit Windows PASS.
    parser.add_argument('--offline-preflight-only',action='store_true')
    a=parser.parse_args()
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'SOURCE_MANIFEST.json').read_text('utf-8'))
    if manifest.get('schema') != 'TICKSTORE_CDT15_G4_STAGE_NATIVE_SOURCE_MANIFEST_V001':
        raise RuntimeError('SOURCE_SCHEMA_MISMATCH')
    paths={x['path'] for x in manifest['files']}
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='SOURCE_MANIFEST.json' and '__pycache__' not in p.parts}
    if paths!=actual or len(paths)!=len(manifest['files']): raise RuntimeError('SOURCE_CLOSED_FILE_SET')
    for x in manifest['files']:
        p=root/x['path']
        if p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:
            raise RuntimeError('SOURCE_COMPONENT_HASH:'+x['path'])
    native = os.name=='nt' and platform.system()=='Windows'
    if not native and not a.offline_preflight_only:
        raise RuntimeError('WINDOWS_NATIVE_REQUIRED')
    loader=unittest.TestLoader()
    suite=loader.discover(str(root/'tests'),pattern='test_*.py',top_level_dir=str(root/'tests'))
    number=suite.countTestCases()
    if number!=49: raise RuntimeError('TEST_CARDINALITY_49:'+str(number))
    stream=io.StringIO()
    begin=time.time()
    result=unittest.TextTestRunner(stream=stream,verbosity=2,failfast=False).run(suite)
    evidence=Path(a.evidence).resolve()
    evidence.mkdir(parents=True,exist_ok=False)
    logfile=evidence/'TEST_LOG.txt'
    logfile.write_text(stream.getvalue(),encoding='utf-8')
    receipt={
        'schema':'TICKSTORE_CDT15_G4_STAGE_NATIVE_RECEIPT_V001',
        'native_windows':native, 'mode':'OFFLINE_PREFLIGHT' if a.offline_preflight_only else 'NATIVE_WINDOWS',
        'tests_run':result.testsRun,'test_cardinality':number,
        'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
        'successful':result.wasSuccessful() and result.testsRun==49 and not result.skipped,
        'source_manifest_sha256':sha(root/'SOURCE_MANIFEST.json'),
        'python_sha256':sha(sys.executable), 'python':sys.version,'platform':platform.platform(),
        'full_started':False,'G4_integral':'INCOMPLETE','G5':'NOT_PROVEN','B06':'NOT_STARTED',
        'elapsed_seconds':round(time.time()-begin,6),'test_log_sha256':sha(logfile),
        'runtime_members':sum(1 for p in paths if p.startswith('candidate/')),
    }
    (evidence/'TEST_RECEIPT.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('SOURCE_MANIFEST=PASS')
    print('G4_STAGE_TESTS='+str(result.testsRun)+'_'+('PASS' if receipt['successful'] else 'FAIL'))
    print('G4_STAGE_NATIVE='+('PASS_ISOLATED' if native and receipt['successful'] else 'OFFLINE_ONLY' if not native and receipt['successful'] else 'FAIL'))
    print('TEST_RECEIPT='+str(evidence/'TEST_RECEIPT.json'))
    return 0 if receipt['successful'] else 2

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as e:
        print('G4_STAGE_TARGET_BLOCKED='+str(e),flush=True)
        sys.exit(2)
