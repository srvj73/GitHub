"""Windows-only 22-worker synthetic concurrency/pin/build/resume smoke for MULTIWORK RC4.
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


def recv_messages(q, expected_count, wanted, timeout=240):
    out=[]
    while len(out)<expected_count:
        msg=q.get(timeout=timeout)
        typ=msg.get('type')
        if typ=='ERROR':
            raise RuntimeError('WORKER_ERROR:'+str(msg))
        if typ in wanted:
            out.append(msg)
    return out


def dates_22():
    out=[]
    year=2024
    month=1
    for _ in range(22):
        out.append(f"{year:04d}{month:02d}15")
        month += 1
        if month==13:
            month=1;year+=1
    return tuple(out)


def run_wave(source,scratch,days,months,ids,expect_status):
    ctx=mp.get_context('spawn')
    eq=ctx.Queue();stop=ctx.Event()
    procs={};cmds={};day_by_month={}
    for month_id in sorted(months):
        ds=[d for d in days if d['month_id']==month_id]
        assert len(ds)==1
        day_by_month[month_id]=ds[0]
        q=ctx.Queue();cmds[month_id]=q
        wid='SMOKE22-'+month_id
        p=ctx.Process(target=mw._worker_main,args=(wid,str(source),str(scratch),month_id,months[month_id],ds,core.EXPECTED_P4A_LEDGER_SHA256,ids,eq,q,stop))
        p.start();procs[month_id]=p

    opened=recv_messages(eq,22,{'OPENED'})
    if len({m['month_id'] for m in opened})!=22:
        raise AssertionError('OPENED_MONTH_COUNT')

    # All 22 workers are concurrently alive and pinned before any START.
    if sum(1 for p in procs.values() if p.is_alive()) != 22:
        raise AssertionError('NOT_ALL_22_ALIVE_WHILE_PINNED')

    # Prove at least one actual worker source pin denies mutation on Windows.
    first_month=sorted(months)[0]
    first_source=source/f"WIN@N_ticks_{first_month}.csv"
    denied=False
    try:
        with first_source.open('ab') as f:
            f.write(b'X')
    except OSError:
        denied=True
    if not denied:
        raise AssertionError('WORKER_SOURCE_PIN_DID_NOT_DENY_WRITE')

    for month_id,q in cmds.items():
        q.put({'type':'START','build_keys':[day_by_month[month_id]['date_key']]})

    verified=recv_messages(eq,22,{'MONTH_VERIFIED'})
    if len({m['month_id'] for m in verified})!=22:
        raise AssertionError('MONTH_VERIFIED_COUNT')
    for msg in verified:
        staged=msg.get('staged') or []
        if len(staged)!=1:
            raise AssertionError(('BAD_STAGED_COUNT',msg.get('month_id'),len(staged)))
        item=staged[0]
        if item.get('scratch_status')!=expect_status:
            raise AssertionError(('BAD_SCRATCH_STATUS',msg.get('month_id'),item.get('scratch_status'),expect_status))
        month_id=msg['month_id'];c=day_by_month[month_id]
        pp=mw._scratch_day_paths(scratch,month_id,c['date_key'])
        j=core.read_json_strict(pp['journal'])
        if j.get('state')!='VALIDATED_PENDING_PUBLISH':
            raise AssertionError('BAD_SCRATCH_STATE:'+str(j.get('state')))
        pinmsg=next(x for x in opened if x['month_id']==month_id)
        oracle=core.make_oracle(c,months[month_id],pinmsg['identity'],core.EXPECTED_P4A_LEDGER_SHA256,ids)
        zstd=core.require_windows_pilot_runtime()
        core.validate_validated_partial(pp['partial'],pp['journal'],c,oracle,zstd,('VALIDATED_PENDING_PUBLISH',))
        if msg.get('actual_sha256') != months[month_id]['source_sha256']:
            raise AssertionError('MONTH_SHA_NOT_VERIFIED:'+month_id)

    for p in procs.values():
        p.join(120)
        if p.is_alive() or p.exitcode!=0:
            raise AssertionError('WORKER_EXIT:'+str(p.exitcode))


def main():
    if sys.platform!='win32':
        print('WINDOWS_MULTIWORK_22_SMOKE=SKIP_NON_WINDOWS')
        return 0
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        source,dest,days,months,contract,ids,cert=fixture(root,dates=dates_22())
        if len(months)!=22:
            raise AssertionError('SYNTH_MONTH_COUNT:'+str(len(months)))
        scratch=root/'scratch';scratch.mkdir()
        run_wave(source,scratch,days,months,ids,'BUILT')
        run_wave(source,scratch,days,months,ids,'RESUMED')
        print('WINDOWS_MULTIWORK_22_CONCURRENT_SPAWN=PASS')
        print('WINDOWS_MULTIWORK_22_CONCURRENT_PINNED=PASS')
        print('WINDOWS_MULTIWORK_22_NO_DAY_ACK_BARRIER=PASS')
        print('WINDOWS_MULTIWORK_22_INLINE_SOURCE_SHA=PASS')
        print('WINDOWS_MULTIWORK_22_SOURCE_WRITE_DENIAL=PASS')
        print('WINDOWS_MULTIWORK_22_SCRATCH_BUILD=PASS')
        print('WINDOWS_MULTIWORK_22_SCRATCH_RESUME=PASS')
        print('REAL_CSV_READ=NO')
        print('PRODUCTION_DEST_WRITE=NO')
        print('WINDOWS_MULTIWORK_22_SMOKE=PASS')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
