import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tickstore_full_multiwork as m


class TestFullMultiworkHelpers(unittest.TestCase):
    def test_progress_bar(self):
        self.assertEqual(m._progress_bar(0,10), '[----------]')
        self.assertEqual(m._progress_bar(50,10), '[#####-----]')
        self.assertEqual(m._progress_bar(100,10), '[##########]')

    def test_workers_auto_respects_cpu_ram_and_max(self):
        fake_mem={'total':32*1024**3,'available':24*1024**3,'load_percent':25}
        with mock.patch.object(m,'windows_memory_status',return_value=fake_mem), \
             mock.patch.object(m,'available_logical_cpus',return_value=24):
            n,mem=m.choose_workers('AUTO',75,22,60)
        self.assertGreaterEqual(n,2)
        self.assertLessEqual(n,22)
        self.assertEqual(mem,fake_mem)


    def test_workers_auto_can_reach_22_on_24_cpu_when_ram_allows(self):
        fake_mem={'total':64*1024**3,'available':60*1024**3,'load_percent':6}
        with mock.patch.object(m,'windows_memory_status',return_value=fake_mem), \
             mock.patch.object(m,'available_logical_cpus',return_value=24):
            n,_=m.choose_workers('AUTO',75,22,60)
        self.assertEqual(n,22)

    def test_workers_explicit_bound(self):
        fake_mem={'total':32*1024**3,'available':24*1024**3,'load_percent':25}
        with mock.patch.object(m,'windows_memory_status',return_value=fake_mem), \
             mock.patch.object(m,'available_logical_cpus',return_value=24):
            n,_=m.choose_workers('7',75,22,60)
        self.assertEqual(n,7)
        with mock.patch.object(m,'windows_memory_status',return_value=fake_mem), \
             mock.patch.object(m,'available_logical_cpus',return_value=24):
            with self.assertRaises(m.MultiworkBlocked):
                m.choose_workers('23',75,22,60)

    def test_workers_explicit_cannot_bypass_ram_budget(self):
        fake_mem={'total':16*1024**3,'available':8*1024**3,'load_percent':50}
        with mock.patch.object(m,'windows_memory_status',return_value=fake_mem), \
             mock.patch.object(m,'available_logical_cpus',return_value=24):
            with self.assertRaisesRegex(m.MultiworkBlocked,'WORKER_COUNT_EXCEEDS_RAM_BUDGET'):
                m.choose_workers('22',75,22,60)

    def test_gate_sha_strict(self):
        self.assertEqual(m._strict_gate_sha('a'*64),'A'*64)
        for value in ('', 'A'*63, 'G'*64):
            with self.assertRaises(m.MultiworkBlocked):
                m._strict_gate_sha(value)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(m.MultiworkBlocked):
            json.loads('{"a":1,"a":2}', object_pairs_hook=m._reject_duplicate_pairs)

    def test_day_state_ignores_global_manifest(self):
        state={'manifest':True,'manifest_atomic':False,'container':False,'commit':False,
               'partial':False,'journal':False,'journal_atomic':False,
               'commit_partial':False,'commit_stage':False}
        self.assertFalse(m._day_state_present(state))
        state['partial']=True
        self.assertTrue(m._day_state_present(state))

    def test_template_closed(self):
        p=Path(__file__).with_name('FULL_MULTIWORK_OWNER_GATE_TEMPLATE_DO_NOT_USE.json')
        obj=json.loads(p.read_text(encoding='utf-8'))
        self.assertFalse(obj['authorized'])
        self.assertEqual(obj['schema'],m.MULTIWORK_GATE_SCHEMA)
        self.assertEqual(obj['wrapper_schema'],m.WRAPPER_SCHEMA)
        self.assertIsNone(obj['wrapper_sha256'])
        self.assertIsNone(obj['core_owner_gate_sha256'])

    def test_core_runner_is_frozen_rc1(self):
        core_path=Path(__file__).with_name('tickstore_serial_runner.py')
        self.assertEqual(
            m.sha256_file(core_path),
            'D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0'
        )


    def test_full_serial_recovery_bridge_uses_full_release_ids_not_generic_run_one_day(self):
        c={"date_key":"20200709","month_id":"2020_07"}
        month={"source_size":"1","source_sha256":"A"*64}
        full_ids={"runner_sha256":"R","spec_sha256":"FULL"}
        sentinel=object()
        with mock.patch.object(m,'_canonical_transient_dates',return_value=['20200709']), \
             mock.patch.object(m,'_recover_full_serial_day',return_value='RESUMED') as recover, \
             mock.patch.object(m.core,'run_one_day',side_effect=AssertionError('generic route must not be used')):
            count=m._normalize_interrupted_canonical_transactions(
                Path('source'),Path('dest'),[c],{'2020_07':month},'L'*64,full_ids,sentinel
            )
        self.assertEqual(count,1)
        recover.assert_called_once_with(Path('source'),Path('dest'),c,month,'L'*64,full_ids,sentinel)

    def test_wrapper_has_no_source_deletion_option(self):
        text=Path(__file__).with_name('tickstore_full_multiwork.py').read_text(encoding='utf-8')
        self.assertNotIn('--delete',text.lower())
        self.assertNotIn('csv_deletion_authorized=yes',text.lower())
        self.assertIn('mp.get_context("spawn")',text)
        self.assertIn('PUBLICATION=DEDICATED_SINGLE_WRITER_PROCESS_AFTER_MONTH_SHA_VERIFIED',text)
        self.assertIn('SAFE_STOP=GROUP_OR_SCAN_CHUNK_BOUNDARY_PLUS_PUBLISH_DAY_BOUNDARY',text)

    def test_productive_architecture_has_no_day_ack_barrier_or_month_prehash(self):
        text=Path(__file__).with_name('tickstore_full_multiwork.py').read_text(encoding='utf-8')
        self.assertIn('SOURCE_PASS=ONE_PHYSICAL_PASS_PER_MONTH',text)
        self.assertIn('SOURCE_HASH=INLINE_WITH_SCAN_AND_BUILD',text)
        self.assertIn('WORKER_DAY_ACK_BARRIER=NO',text)
        self.assertNotIn('DAY_READY',text)
        self.assertNotIn('WORKER_BAD_ACK',text)
        self.assertNotIn('core.FullSerialMonth(',text)

    def test_streaming_month_source_single_pass_hash(self):
        import hashlib, os
        data=(b'a,b,c\n'*1000)+(b'z'*12345)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'m.csv';path.write_bytes(data)
            expected=hashlib.sha256(data).hexdigest().upper()
            real_open=m.core.secure_open_existing_fd
            with mock.patch.object(m.core,'secure_open_existing_fd',side_effect=lambda p,writable=False,source_pin=False: os.open(p,os.O_RDONLY)):
                with m.StreamingMonthSource(path,len(data),expected) as v:
                    v.scan_to(1000)
                    v.scan_to(len(data)//2)
                    v.scan_to(len(data))
                    self.assertEqual(v.finish_and_verify(),expected)
                    self.assertEqual(v._hashed,len(data))
                    self.assertTrue(v.verified)

    def test_streaming_month_source_rejects_backward_seek(self):
        import hashlib, os
        data=b'x'*4096
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'m.csv';path.write_bytes(data)
            expected=hashlib.sha256(data).hexdigest().upper()
            with mock.patch.object(m.core,'secure_open_existing_fd',side_effect=lambda p,writable=False,source_pin=False: os.open(p,os.O_RDONLY)):
                with m.StreamingMonthSource(path,len(data),expected) as v:
                    v.scan_to(2048)
                    with self.assertRaisesRegex(m.core.Blocked,'BACKWARD_SEEK'):
                        v.seek(1024)

    def test_rc4_dedicated_publisher_decouples_worker_admission(self):
        text=Path(__file__).with_name('tickstore_full_multiwork.py').read_text(encoding='utf-8')
        self.assertIn('def _publisher_main(',text)
        self.assertIn('name="TICKSTORE-RC4R2-PUBLISHER"',text)
        self.assertIn('PUBLICATION_OVERLAPS_WORKER_BUILD=YES',text)
        self.assertIn('MONTH_VERIFIED_QUEUED',text)
        self.assertIn('publish_q.put({',text)

    def test_rc4_worker_start_is_prequeued_under_parent_pin(self):
        text=Path(__file__).with_name('tickstore_full_multiwork.py').read_text(encoding='utf-8')
        self.assertIn('ParentMonthPin.open_from_expected(',text)
        self.assertIn('command_q.put({"type":"START","build_keys":build_keys})',text)
        self.assertIn('START_PREQUEUED=YES',text)
        self.assertIn('WORKER_PRESTART_IDENTITY_MISMATCH',text)

    def test_rc4r2_scratch_namespace_and_legacy_compat(self):
        text=Path(__file__).with_name('tickstore_full_multiwork.py').read_text(encoding='utf-8')
        self.assertIn('FULL_MULTIWORK_RC4R2',text)
        self.assertIn('FULL_MULTIWORK_RC4',text)
        self.assertIn('FULL_MULTIWORK_RC3',text)
        self.assertIn('FULL_MULTIWORK_RC2R3',text)
        self.assertIn('SCRATCH_REVISION_CONFLICT',text)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            got=m._scratch_day_paths(root,'2026_07','20260731')
            self.assertEqual(got['namespace'],'RC4R2')
            self.assertEqual(
                got['root'],
                root/'FULL_MULTIWORK_RC4R2'/'2026_07'/'20260731'
            )
            self.assertTrue(got['root'].is_dir())

    def test_rc4_publisher_stop_preempts_queued_month(self):
        class FakeQ:
            def __init__(self,items=None): self.items=list(items or []);self.out=[]
            def get(self): return self.items.pop(0)
            def put(self,item): self.out.append(item)
        class Stop:
            def is_set(self): return True
        cq=FakeQ([{'type':'PUBLISH_MONTH'}]);eq=FakeQ()
        with mock.patch.object(m.core,'require_windows_pilot_runtime',return_value=object()), \
             mock.patch.object(m.signal,'signal'), \
             mock.patch.object(m.ParentMonthPin,'open',side_effect=AssertionError('must not open')):
            m._publisher_main(
                cq,eq,Stop(),dest_root='dest',coordinator_path='coord',all_keys=set(),
                months={},by_month={},ledger_sha='L',ids={'runner_sha256':'R'},cert={},
                workers_effective=22,total_days=0,total_rows=0
            )
        self.assertEqual(eq.out[0]['type'],'PUBLISHER_READY')
        self.assertEqual(eq.out[1]['type'],'PUBLISHER_STOPPED')


    def test_rc4r1_shutdown_is_bounded_and_second_ctrl_c_is_masked(self):
        text=Path(__file__).with_name('tickstore_full_multiwork.py').read_text(encoding='utf-8')
        self.assertIn('SAFE_STOP_JOIN_TIMEOUT_SECONDS = 60.0',text)
        self.assertIn('signal.signal(signal.SIGINT, signal.SIG_IGN)',text)
        self.assertIn('SAFE_STOP_PROCESS_TREE=PASS',text)
        self.assertIn('SAFE_STOP_FORCED_TERMINATE=',text)
        self.assertIn('SHUTDOWN_PROCESS_TREE_STILL_ALIVE',text)

    def test_rc4r1_shutdown_escalates_stubborn_process(self):
        class FakeQ:
            def __init__(self): self.closed=False; self.cancelled=False; self.items=[]
            def put(self,x): self.items.append(x)
            def close(self): self.closed=True
            def cancel_join_thread(self): self.cancelled=True
            def get_nowait(self):
                raise m.queue.Empty
        class Stop:
            def __init__(self): self.v=False
            def set(self): self.v=True
        class Proc:
            def __init__(self): self.alive=True; self.terminated=False; self.killed=False; self.pid=4242; self.exitcode=None
            def is_alive(self): return self.alive
            def join(self,timeout=None): return
            def terminate(self): self.terminated=True; self.alive=False; self.exitcode=-15
            def kill(self): self.killed=True; self.alive=False; self.exitcode=-9
        worker=Proc();publisher=Proc();cq=FakeQ();pq=FakeQ();eq=FakeQ();stop=Stop()
        active={'W001-X':{'process':worker,'command_q':cq}}
        with mock.patch.object(m.signal,'getsignal',return_value='OLD'), \
             mock.patch.object(m.signal,'signal'):
            report=m._bounded_shutdown_process_tree(
                active,publisher,pq,eq,stop,'TEST',
                timeout_seconds=0.01,terminate_grace_seconds=0.01,kill_grace_seconds=0.01
            )
        self.assertTrue(stop.v)
        self.assertFalse(worker.is_alive())
        self.assertFalse(publisher.is_alive())
        self.assertIn('WORKER:W001-X',report['forced_terminate'])
        self.assertIn('PUBLISHER',report['forced_terminate'])
        self.assertEqual(report['forced_kill'],[])
        self.assertTrue(cq.closed and pq.closed and eq.closed)
        self.assertEqual(report['child_exit_codes'],{'WORKER:W001-X':-15,'PUBLISHER':-15})
        self.assertFalse(m._cooperative_stop_confirmed(report))

    def test_r41_autocpu_uses_process_available_cpus(self):
        with mock.patch.object(m.os,'process_cpu_count',create=True,return_value=6), \
             mock.patch.object(m.os,'cpu_count',return_value=24):
            self.assertEqual(m.available_logical_cpus(),6)
        with mock.patch.object(m,'available_logical_cpus',return_value=6), \
             mock.patch.object(m,'windows_memory_status',return_value={'total':256*1024**3,'available':200*1024**3,'load_percent':10}):
            workers,_=m.choose_workers('AUTO',75,22,60)
        self.assertEqual(workers,4)

    def test_r42_autocpu_never_exceeds_system_count(self):
        # Historical contract (tests_delta.test_auto_cpu_zero_one_n_and_invalid_request)
        # bounds the machine through os.cpu_count; affinity may only lower it.
        with mock.patch.object(m.os,'process_cpu_count',create=True,return_value=24), \
             mock.patch.object(m.os,'cpu_count',return_value=8):
            self.assertEqual(m.available_logical_cpus(),8)
        mem={'total':32*1024**3,'available':24*1024**3}
        with mock.patch.object(m,'windows_memory_status',return_value=mem), \
             mock.patch.object(m.os,'process_cpu_count',create=True,return_value=24), \
             mock.patch.object(m.os,'cpu_count',return_value=8):
            self.assertEqual(m.choose_workers('AUTO',20,32,60)[0],6)
            with self.assertRaisesRegex(RuntimeError,'CPU_BUDGET'): m.choose_workers('7',20,32,60)

    def test_r41_watchdog_requests_cooperative_stop_once(self):
        class Stop:
            def __init__(self): self.n=0
            def set(self): self.n+=1
        stop=Stop()
        w=m.MainLoopWatchdog(stop,limit_seconds=0.05,poll_seconds=0.01).start()
        import time as _t; _t.sleep(0.3); w.close()
        self.assertTrue(w.fired); self.assertEqual(stop.n,1)
        stop2=Stop(); w=m.MainLoopWatchdog(stop2,limit_seconds=5,poll_seconds=0.01).start()
        for _ in range(5): w.tick(); _t.sleep(0.02)
        w.close(); self.assertFalse(w.fired); self.assertEqual(stop2.n,0)

    def test_r41_watchdog_scoped_to_event_loop(self):
        text=Path(__file__).with_name('tickstore_full_multiwork.py').read_text(encoding='utf-8')
        loop=text.index('while active or months_done < len(months):')
        close=text.index('watchdog.close()\n        if watchdog.fired: raise KeyboardInterrupt()')
        reconcile=text.index('core.reconcile_full_readonly(dest_root')
        self.assertLess(loop,close); self.assertLess(close,reconcile)
        self.assertIn("print('SAFE_STOP_REASON=WATCHDOG_MAIN_LOOP_STALL', flush=True)",text)

    def test_r42_finalize_without_publisher_keeps_primary_error_and_releases(self):
        # R42 finding: an error before publisher start made finalization raise
        # AttributeError, masking the cause and skipping lock/lease release.
        released=[];closed=[]
        class Lease:
            def close(self): closed.append(True)
        primary=(RuntimeError,RuntimeError('ORIGINAL_CAUSE'),None)
        with mock.patch.object(m.core,'release_lock',side_effect=lambda lock: released.append(lock)):
            out=m._finalize_coordinator_resources({},{},None,'LOCK',Lease(),primary)
        self.assertIs(out,primary)
        self.assertEqual(released,['LOCK']); self.assertEqual(closed,[True])

if __name__=='__main__':
    unittest.main(verbosity=2)
