"""Windows-only synthetic spawn/pin/build/resume smoke for MULTIWORK RC4.
No real CSV or production destination is used.
"""
from pathlib import Path
import multiprocessing as mp
import tempfile
import queue
import sys

import tickstore_serial_runner as core
import tickstore_full_multiwork as mw
from test_full_serial_r9 import fixture


def recv_until(q, wanted, timeout=120):
    while True:
        msg=q.get(timeout=timeout)
        typ=msg.get('type')
        if typ=='ERROR':
            raise RuntimeError('WORKER_ERROR:'+str(msg))
        if typ in wanted:
            return msg


def run_once(source,scratch,month_id,month,days,ids,expect_status):
    ctx=mp.get_context('spawn')
    eq=ctx.Queue();cq=ctx.Queue();stop=ctx.Event()
    wid='SMOKE-'+month_id
    p=ctx.Process(target=mw._worker_main,args=(wid,str(source),str(scratch),month_id,month,days,core.EXPECTED_P4A_LEDGER_SHA256,ids,eq,cq,stop))
    p.start()
    opened=recv_until(eq,{'OPENED'})
    key=days[0]['date_key']
    cq.put({'type':'START','build_keys':[key]})
    verified=recv_until(eq,{'MONTH_VERIFIED'})
    staged=verified.get('staged') or []
    if len(staged)!=1 or staged[0].get('scratch_status')!=expect_status:
        raise AssertionError((staged,expect_status))
    pp=mw._scratch_day_paths(scratch,month_id,key)
    j=core.read_json_strict(pp['journal'])
    if j.get('state')!='VALIDATED_PENDING_PUBLISH':
        raise AssertionError('BAD_SCRATCH_STATE:'+str(j.get('state')))
    zstd=core.require_windows_pilot_runtime()
    identity=opened['identity']
    oracle=core.make_oracle(days[0],month,identity,core.EXPECTED_P4A_LEDGER_SHA256,ids)
    core.validate_validated_partial(pp['partial'],pp['journal'],days[0],oracle,zstd,('VALIDATED_PENDING_PUBLISH',))
    if verified.get('actual_sha256') != month['source_sha256']:
        raise AssertionError('MONTH_SHA_NOT_VERIFIED')
    p.join(120)
    if p.is_alive() or p.exitcode!=0:
        raise AssertionError('WORKER_EXIT:'+str(p.exitcode))
    return staged[0]


def main():
    if sys.platform!='win32':
        print('WINDOWS_MULTIWORK_SMOKE=SKIP_NON_WINDOWS')
        return 0
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        source,dest,days,months,contract,ids,cert=fixture(root,dates=('20260730','20260731'))
        scratch=root/'scratch';scratch.mkdir()
        month_id='2026_07';month_days=[d for d in days if d['month_id']==month_id]
        # Use one day only so the same validated scratch transaction can prove restart reuse.
        one=[month_days[0]]
        first=run_once(source,scratch,month_id,months[month_id],one,ids,'BUILT')
        second=run_once(source,scratch,month_id,months[month_id],one,ids,'RESUMED')
        print('WINDOWS_MULTIWORK_SPAWN=PASS')
        print('WINDOWS_MULTIWORK_SOURCE_PIN=PASS')
        print('WINDOWS_MULTIWORK_INLINE_SOURCE_SHA=PASS')
        print('WINDOWS_MULTIWORK_NO_DAY_ACK_BARRIER=PASS')
        print('WINDOWS_MULTIWORK_NATIVE_ZSTD=PASS')
        print('WINDOWS_MULTIWORK_SCRATCH_BUILD=PASS')
        print('WINDOWS_MULTIWORK_SCRATCH_RESUME=PASS')
        print('REAL_CSV_READ=NO')
        print('PRODUCTION_DEST_WRITE=NO')
        print('WINDOWS_MULTIWORK_SMOKE=PASS')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
