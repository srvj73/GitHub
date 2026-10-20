"""Run one hash-verified suite exactly as PRE_G06_CAMPAIGN.unit_child does.

Invoked by G0 as `python -I -B G0_SUITE_RUNNER.py`: same isolated flags, same
candidate import order, same unittest discovery, an owned TEMP set by the
caller. Writes a closed log and a JSON result with every failure traceback,
so a non-PASS is never reported only as a log path.
"""
from __future__ import annotations
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys
import traceback
import unittest


def main(argv=None):
    p=argparse.ArgumentParser(allow_abbrev=False)
    for name in ('test','candidate','log','result'):p.add_argument('--'+name,required=True)
    a=p.parse_args(argv)
    test=Path(a.test);candidate=Path(a.candidate)
    # Same order as RUN_CDT20_R08Q1.load_candidate + PRE_G06_CAMPAIGN import.
    for _ in range(2):
        for folder in ('full','control','adapter','g5proof'):sys.path.insert(0,str(candidate/folder))
    sys.path.insert(0,str(test.parent))
    import tempfile
    tempfile.tempdir=os.environ['TEMP']
    result={'schema':'CDT20_G0_SUITE_RESULT_V001','suite':test.name,'status':'BLOCKED',
            'temp':os.environ['TEMP'],'cwd':os.getcwd(),'flags_isolated':sys.flags.isolated}
    with open(a.log,'x',encoding='utf8',buffering=1) as stream,\
         contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try:
            suite=unittest.defaultTestLoader.discover(str(test.parent),pattern=test.name,top_level_dir=str(test.parent))
            count=suite.countTestCases()
            ran=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
            result.update(declared=count,tests_run=ran.testsRun,
                          failures=[[t.id(),tb] for t,tb in ran.failures],
                          errors=[[t.id(),tb] for t,tb in ran.errors],
                          skipped=[[t.id(),reason] for t,reason in ran.skipped],
                          expected_failures=len(ran.expectedFailures),
                          unexpected_successes=len(ran.unexpectedSuccesses),
                          successful=ran.wasSuccessful())
            ok=(count>0 and ran.testsRun==count and ran.wasSuccessful()
                and not ran.expectedFailures and not ran.unexpectedSuccesses)
            result['status']='PASS' if ok else 'FAIL'
        except BaseException as exc:
            result.update(status='CRASH',crash=type(exc).__name__+':'+str(exc),traceback=traceback.format_exc())
            traceback.print_exc()
        finally:
            stream.flush();os.fsync(stream.fileno())
    with open(a.result,'xb') as f:
        f.write((json.dumps(result,sort_keys=True,ensure_ascii=True,indent=1)+'\n').encode('ascii'))
        f.flush();os.fsync(f.fileno())
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
