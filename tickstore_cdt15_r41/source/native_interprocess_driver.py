"""Windows-only sandbox test harness. Does not install/activate TICKSTORE."""
from __future__ import annotations
import hashlib, io, json, os, sys, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest().upper()

def flatten(tests):
    for t in tests:
        if isinstance(t,unittest.TestSuite):yield from flatten(t)
        else:yield t

def main():
    if os.name!='nt':
        print('INTERPROCESS_NATIVE=BLOCKED_NOT_WINDOWS')
        return 2
    if len(sys.argv)!=2:
        print('INTERPROCESS_NATIVE=BLOCKED_USAGE')
        return 2
    evidence=Path(sys.argv[1]);evidence.mkdir(parents=True,exist_ok=True)
    suite=unittest.TestLoader().discover(str(ROOT/'tests'),pattern='test_menu_tx_interprocess.py')
    ids=[x.id() for x in flatten(suite)]
    buf=io.StringIO()
    result=unittest.TextTestRunner(stream=buf,verbosity=2).run(suite)
    log=buf.getvalue()
    (evidence/'TEST_LOG.txt').write_text(log,encoding='utf-8')
    ok=(len(ids)==17 and len(set(ids))==17 and result.testsRun==17
        and result.wasSuccessful() and not result.skipped)
    rec={
      'schema':'CDT15_G4_INTERPROCESS_WINDOWS_DIAG_V001',
      'status':'PASS_SANDBOX_ONLY' if ok else 'FAIL_SANDBOX_ONLY',
      'ran':result.testsRun,'discovered':len(ids),'unique_ids':len(set(ids)),
      'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
      'test_ids':ids,
      'module_sha256':sha((ROOT/'candidate/control/MENU_TX_INTERPROCESS_SANDBOX.py').read_bytes()),
      'test_source_sha256':sha((ROOT/'tests/test_menu_tx_interprocess.py').read_bytes()),
      'test_log_sha256':sha((evidence/'TEST_LOG.txt').read_bytes()),
      'production_modified':False,'full_started':False,
      'windows_native_file_lock':'EXECUTED_IN_SANDBOX' if ok else 'NOT_QUALIFIED',
      'installer_official_transaction':'NOT_IMPLEMENTED',
      'g4':'INCOMPLETE','g5':'NOT_PROVEN','b06':'BLOCKED_INCOMPLETE'}
    (evidence/'TEST_RECEIPT.json').write_text(json.dumps(rec,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('INTERPROCESS_NATIVE_STATUS='+rec['status'])
    print('INTERPROCESS_NATIVE_TESTS='+str(result.testsRun))
    print('PRODUCTION_MODIFIED=NO;FULL_STARTED=NO')
    return 0 if ok else 2

if __name__=='__main__':
    sys.exit(main())
