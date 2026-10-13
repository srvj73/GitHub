"""Windows-only RC4 dedicated publisher + prequeued-start smoke.
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
        if typ in ('ERROR','PUBLISHER_ERROR'):
            raise RuntimeError(str(msg))
        if typ in wanted:
            return msg


def main():
    if sys.platform!='win32':
        print('WINDOWS_RC4_PUBLISHER_SMOKE=SKIP_NON_WINDOWS')
        return 0

    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        source,dest,days,months,contract,ids,cert=fixture(root,dates=('20260730',))
        scratch=root/'scratch';scratch.mkdir()
        month_id=next(iter(months))
        month=months[month_id]
        mdays=[d for d in days if d['month_id']==month_id]
        c=mdays[0]
        src=core.source_for(source,c)

        # Parent pin exists before worker spawn; START is already waiting when worker opens.
        parent_pin=mw.ParentMonthPin.open_from_expected(src,int(month['source_size']),month['source_sha256'])
        build_keys,existing_keys=mw._classify_month_build_keys(dest,mdays)
        if build_keys!=[c['date_key']] or existing_keys:
            raise AssertionError('BAD_INITIAL_CLASSIFICATION')

        ctx=mp.get_context('spawn')
        event_q=ctx.Queue(); command_q=ctx.Queue(); stop=ctx.Event()
        command_q.put({'type':'START','build_keys':build_keys})
        wid='RC4-PREQUEUE-'+month_id
        worker=ctx.Process(
            target=mw._worker_main,
            args=(wid,str(source),str(scratch),month_id,month,mdays,
                  core.EXPECTED_P4A_LEDGER_SHA256,ids,event_q,command_q,stop),
        )
        worker.start()
        opened=recv_until(event_q,{'OPENED'})
        if opened['identity']!=parent_pin.identity:
            raise AssertionError('PRESTART_PARENT_WORKER_IDENTITY_MISMATCH')
        verified=recv_until(event_q,{'MONTH_VERIFIED'})
        if verified.get('actual_sha256')!=month['source_sha256']:
            raise AssertionError('MONTH_SHA_NOT_VERIFIED')
        worker.join(120)
        if worker.is_alive() or worker.exitcode!=0:
            raise AssertionError('WORKER_EXIT:'+str(worker.exitcode))
        parent_pin.verify()

        all_keys={x['date_key'] for x in days}
        by_month={month_id:mdays}
        coordinator=scratch/'FULL_MULTIWORK_RC4'/'COORDINATOR_STATE.json'
        core.strict_directory(scratch/'FULL_MULTIWORK_RC4',create=True)

        pub_q=ctx.Queue(); pub_stop=ctx.Event()
        publisher=ctx.Process(
            target=mw._publisher_main,
            kwargs={
                'command_q':pub_q,'event_q':event_q,'stop_event':pub_stop,
                'dest_root':str(dest),'coordinator_path':str(coordinator),
                'all_keys':all_keys,'months':months,'by_month':by_month,
                'ledger_sha':core.EXPECTED_P4A_LEDGER_SHA256,'ids':ids,'cert':cert,
                'workers_effective':22,'total_days':len(days),
                'total_rows':sum(int(x['rows']) for x in days),
            },
        )

        lock=None
        try:
            with core.FullSerialLockBoundary():
                lock=core.acquire_lock(dest)
            core._full_manifest(dest,all_keys)
            publisher.start()
            recv_until(event_q,{'PUBLISHER_READY'})
            pub_q.put({
                'type':'PUBLISH_MONTH','month_id':month_id,
                'identity':dict(parent_pin.identity),
                'build_keys':build_keys,'existing_keys':existing_keys,
                'staged':verified['staged'],
            })
            recv_until(event_q,{'PUBLISH_MONTH_START'})
            done=recv_until(event_q,{'MONTH_PUBLISHED'})
            if done.get('published_days')!=1 or done.get('months_published')!=1:
                raise AssertionError('PUBLISH_COUNTS_BAD:'+str(done))
            pub_q.put({'type':'STOP'})
            publisher.join(120)
            if publisher.is_alive() or publisher.exitcode!=0:
                raise AssertionError('PUBLISHER_EXIT:'+str(publisher.exitcode))
        finally:
            if lock is not None:
                with core.FullSerialLockBoundary():
                    core.release_lock(lock)

        pp=core._full_day_paths(dest,c)
        if not pp['container'].is_file() or not pp['commit'].is_file():
            raise AssertionError('CANONICAL_PAIR_MISSING')
        if not coordinator.is_file():
            raise AssertionError('COORDINATOR_MISSING')
        state=core.read_json_strict(coordinator)
        if state.get('publisher')!='DEDICATED_SINGLE_WRITER_PROCESS':
            raise AssertionError('COORDINATOR_PUBLISHER_MARKER')
        parent_pin.verify()
        parent_pin.close()

        print('WINDOWS_RC4_PARENT_PIN_BEFORE_WORKER=PASS')
        print('WINDOWS_RC4_WORKER_START_PREQUEUED=PASS')
        print('WINDOWS_RC4_MONTH_SHA_BEFORE_PUBLISH=PASS')
        print('WINDOWS_RC4_DEDICATED_PUBLISHER_PROCESS=PASS')
        print('WINDOWS_RC4_CANONICAL_SINGLE_WRITER=PASS')
        print('WINDOWS_RC4_PUBLISHER_SMOKE=PASS')
        print('REAL_CSV_READ=NO')
        print('PRODUCTION_DEST_WRITE=NO')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
