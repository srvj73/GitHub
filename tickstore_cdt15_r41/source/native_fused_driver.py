"""CDT15 G4 sandbox-only native test harness for NEW fused writer delta.

No product files, installer, MENU or deployment outside TemporaryDirectory.
"""
from __future__ import annotations
import hashlib, io, json, os, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()

def flatten(suite):
    for child in suite:
        if isinstance(child, unittest.TestSuite):
            yield from flatten(child)
        else:
            yield child

def main():
    if os.name!='nt' or len(sys.argv)!=2:
        print('FUSED_NATIVE=BLOCKED_OS_OR_ARGUMENTS')
        return 2
    evidence=Path(sys.argv[1])
    evidence.mkdir(parents=True,exist_ok=True)
    suite=unittest.TestLoader().discover(str(ROOT/'tests'),pattern='test_fused_sandbox_writer.py')
    ids=[t.id() for t in flatten(suite)]
    out=io.StringIO()
    res=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
    log=out.getvalue()
    log_path=evidence/'TEST_LOG.txt';log_path.write_text(log,encoding='utf-8')
    passed=(len(ids)==18 and len(set(ids))==18 and res.testsRun==18 and res.wasSuccessful() and not res.skipped)
    receipt={
      'schema':'CDT15_G4_FUSED_SANDBOX_WINDOWS_V001',
      'status':'PASS_SANDBOX_ONLY' if passed else 'FAIL_SANDBOX_ONLY',
      'ran':res.testsRun,'discovered':len(ids),'unique_ids':len(set(ids)),
      'failures':len(res.failures),'errors':len(res.errors),'skips':len(res.skipped),
      'test_ids':ids,
      'delta_sha256':digest(ROOT/'candidate/control/MENU_TX_FUSED_SANDBOX.py'),
      'test_sha256':digest(ROOT/'tests/test_fused_sandbox_writer.py'),
      'log_sha256':digest(log_path),
      'official_installer':'NOT_QUALIFIED',
      'sandbox_only':True,'production_modified':False,'full_started':False,
      'g4':'INCOMPLETE','g5':'NOT_PROVEN','b06':'BLOCKED_INCOMPLETE'}
    (evidence/'TEST_RECEIPT.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('FUSED_NATIVE_STATUS='+receipt['status'])
    print('FUSED_NATIVE_TESTS='+str(res.testsRun))
    print('PRODUCTION_MODIFIED=NO;FULL_STARTED=NO')
    return 0 if passed else 2

if __name__=='__main__':sys.exit(main())
