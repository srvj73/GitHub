"""Directed CDT15 engineering tests. No productive gate or corpus is admitted."""
from pathlib import Path
import copy
import contextlib
import hashlib
import io
import json
import multiprocessing as mp
import os
import sys
import tempfile
import time
import unittest
import uuid
import threading
import types
from unittest.mock import patch

ROOT = Path(os.environ.get('TICKSTORE_TEST_CANDIDATE', str(Path(__file__).parent/'work/implementation_v001/candidate')))
sys.path[:0] = [str(ROOT/'full'), str(ROOT/'control'), str(ROOT/'adapter')]
import tickstore_full_multiwork as mw
import tickstore_serial_runner as core
from FULL_RELEASE_CHAIN import STAGES, REQUIRED_CHECKS, validate_chain, member_path
from FULL_PROCESS_CONTROL import ProcessJob, StopEvent
from FULL_STAGE_CONTINUATION import StageBoundary, load as load_library
import runtime_locator_orchestrator_entry as entry
import runtime_locator_adapter as adapter
from test_full_serial_r9 import fixture


def receipt_fixture():
    receipts, hashes = {}, {}
    previous = None
    for stage in STAGES:
        obj = dict(schema='TICKSTORE_STAGE_RECEIPT_V001', stage=stage, status='PASS',
                   environment='ISOLATED_TEST', code_manifest_sha256='A'*64,
                   instance_sha256='B'*64, previous_receipt_sha256=previous, blockers=[],
                   checks={k: True for k in REQUIRED_CHECKS[stage]},
                   evidence=[dict(path='fixture-only', sha256='C'*64)],
                   reviewer='ISOLATED_FIXTURE_NOT_AN_AUDIT', implementation_participant=False)
        receipts[stage] = obj
        previous = hashlib.sha256(json.dumps(obj).encode()).hexdigest().upper()
        hashes[stage] = previous
    return receipts, hashes


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.r, self.h = receipt_fixture()

    def validate(self, environment='ISOLATED_TEST'):
        return validate_chain(self.r, self.h, code_sha='A'*64, instance_sha='B'*64,
                              b06_sha=self.h['B06'], environment=environment)

    def test_complete_fixture_chain(self):
        self.assertEqual(self.validate(), self.h['FULL_ADMISSION'])

    def test_fixture_cannot_admit_production(self):
        with self.assertRaisesRegex(RuntimeError, 'ENVIRONMENT'):
            self.validate('WINDOWS_PRODUCTION')

    def test_each_missing_stage_blocks(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                self.r, self.h = receipt_fixture(); del self.r[stage]
                with self.assertRaisesRegex(RuntimeError, 'STAGE_ORDER'): self.validate()

    def test_each_nonpass_blocks(self):
        for stage in STAGES:
            self.r, self.h = receipt_fixture(); self.r[stage]['status'] = 'PENDING'
            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, 'NOT_PASS'): self.validate()

    def test_each_code_drift_blocks(self):
        for stage in STAGES:
            self.r, self.h = receipt_fixture(); self.r[stage]['code_manifest_sha256'] = 'D'*64
            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, 'CODE_DRIFT'): self.validate()

    def test_each_instance_drift_blocks(self):
        for stage in STAGES:
            self.r, self.h = receipt_fixture(); self.r[stage]['instance_sha256'] = 'D'*64
            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, 'INSTANCE_DRIFT'): self.validate()

    def test_each_missing_check_blocks(self):
        for stage in STAGES:
            for name in REQUIRED_CHECKS[stage]:
                self.r, self.h = receipt_fixture(); self.r[stage]['checks'][name] = 'PASS'
                with self.subTest(stage=stage, check=name), self.assertRaisesRegex(RuntimeError, 'CHECKS'): self.validate()

    def test_predecessor_drift_blocks(self):
        self.r['D5']['previous_receipt_sha256'] = 'D'*64
        with self.assertRaisesRegex(RuntimeError, 'PREDECESSOR'): self.validate()

    def test_self_audit_blocks(self):
        self.r['B06']['implementation_participant'] = True
        with self.assertRaisesRegex(RuntimeError, 'IMPLEMENTER_CANNOT'): self.validate()

    def test_external_anchor_mismatch(self):
        with self.assertRaisesRegex(RuntimeError, 'EXTERNAL_DIGEST'):
            validate_chain(self.r, self.h, code_sha='A'*64, instance_sha='B'*64,
                           b06_sha='D'*64, environment='ISOLATED_TEST')

    def test_no_evidence_blocks(self):
        self.r['D4']['evidence'] = []
        with self.assertRaisesRegex(RuntimeError, 'EVIDENCE_REQUIRED'): self.validate()

    def test_blocker_blocks(self):
        self.r['G5']['blockers'] = ['INCOMPLETE']
        with self.assertRaisesRegex(RuntimeError, 'BLOCKERS'): self.validate()

    def test_path_escape_blocks(self):
        for value in ('../x', '/x', 'C:/x', 'a\\b', 'a/./b', 'a//b', ''):
            with self.subTest(value=value), self.assertRaises(RuntimeError): member_path(ROOT, value)

    def test_legacy_admission_rejected_before_any_data_access(self):
        with patch.object(core, 'load_ledgers', side_effect=AssertionError('DATA_ACCESS')):
            with self.assertRaisesRegex(RuntimeError, 'LEGACY_ADMINISTRATIVE'):
                mw.execute_multiwork(None, None, None, None, 'old-gate', 'A'*64)

    def test_missing_chain_rejected_before_any_data_access(self):
        with patch.object(core, 'load_ledgers', side_effect=AssertionError('DATA_ACCESS')):
            with self.assertRaisesRegex(RuntimeError, 'TECHNICAL_RELEASE_CHAIN_REQUIRED'):
                mw.execute_multiwork(None, None, None, None)


def child_write(path):
    Path(path).write_text('admitted-child')


def child_wait(ready, finished):
    ready.set()
    time.sleep(120)
    finished.set()


class NativeJobTests(unittest.TestCase):
    def test_admitted_child_executes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'marker'
            job = ProcessJob()
            try:
                child = job.start(mp.get_context('spawn'), child_write, args=(str(p),))
                child.join(20)
                self.assertEqual(child.exitcode, 0)
                self.assertEqual(p.read_text(), 'admitted-child')
            finally: job.close()

    def test_job_close_contains_survivor(self):
        ctx = mp.get_context('spawn'); ready = ctx.Event(); finished = ctx.Event(); job = ProcessJob()
        try:
            child = job.start(ctx, child_wait, args=(ready, finished))
            self.assertTrue(ready.wait(20))
        finally: job.close()
        child.join(20)
        self.assertFalse(child.is_alive())
        self.assertFalse(finished.is_set())


class FixtureAdmission:
    """Test-only dependency for engine integration; never an operational receipt."""
    def __init__(self):
        self.instance = {"run_id": "fixture_"+uuid.uuid4().hex}
        self.descriptor = {'code_manifest_sha256': 'A'*64, 'instance_sha256': 'B'*64}
    def validate_full(self, bindings, workers, maximum, ram):
        assert workers > 0
    def revalidate(self): pass


class NativePipelineTests(unittest.TestCase):
    def test_two_months_publish_readback_repeat_without_duplicate_ticks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, dest, days, months, contract, ids, cert = fixture(root)
            scratch = root/'scratch'; scratch.mkdir()
            csv_before = {p.name: core.sha256_file(p) for p in source.iterdir()}
            with patch.object(core, 'full_release_materials', return_value=(contract, cert, ids)), \
                 patch.object(core, 'load_ledgers', return_value=(days, months, core.EXPECTED_P4A_LEDGER_SHA256)):
                for attempt in range(2):
                    self.assertEqual(mw._execute_admitted_multiwork(source, dest, scratch, root/'fixture-ledger',
                                                '2', 2, 60, FixtureAdmission()), 0)
                    manifest = core.load_manifest(dest)
                    self.assertEqual(len(manifest['records']), 3)
                    self.assertEqual({p.name: core.sha256_file(p) for p in source.iterdir()}, csv_before)
                    self.assertFalse((dest/'TICKSTORE_WRITER.lock').exists())
                    if attempt == 0:
                        manifest_sha = core.sha256_file(dest/'TICKSTORE_GLOBAL_MANIFEST.json')
                    else:
                        self.assertEqual(core.sha256_file(dest/'TICKSTORE_GLOBAL_MANIFEST.json'), manifest_sha)


class CheckpointFailureTests(unittest.TestCase):
    def test_failed_checkpoint_publish_can_retry_preserving_previous(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'COORDINATOR_STATE.json'
            mw._atomic_coordinator_state(path, {'generation': 1})
            before = path.read_bytes()
            with patch.object(core, 'secure_replace', side_effect=OSError('INJECTED_BEFORE_PUBLISH')):
                with self.assertRaises(OSError): mw._atomic_coordinator_state(path, {'generation': 2})
            self.assertEqual(path.read_bytes(), before)
            mw._atomic_coordinator_state(path, {'generation': 2})
            self.assertEqual(json.loads(path.read_bytes()), {'generation': 2})


class StageGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root/'state').mkdir()
        self.sp = self.root/'state/STATE.json'
        self.state = dict(schema='TICKSTORE_ORCH_STATE_V001', status='PASS', next_node='D5',
                          completed=['D4'], canary_scratch_cert='PHYSICAL_FIXTURE_ONLY',
                          G_CA={}, cprof={}, canary={})
        self.sp.write_text(json.dumps(self.state))
        self.cfg = self.root/'config.json'; self.cfg.write_text(json.dumps({'control_root': str(self.root)}))
        self.ns = load_library((ROOT/'recovery/modules/orchestrator.py').read_bytes(), ROOT/'recovery/modules/orchestrator.py')
        raw, ident = entry.read_pinned_regular(self.sp, 'FIXTURE_STATE')
        cr, ci = entry.read_pinned_regular(self.cfg, 'FIXTURE_CONFIG')
        admitted = entry.AdmittedStart(self.sp, self.root, self.cfg, cr, entry._sha(cr), ci, raw, ident)
        boundary = StageBoundary('D5')
        entry.guard_frozen_state_reads(self.ns, admitted, state_validator=boundary.validate,
                                      transition_validator=boundary.transition)
        self.addCleanup(self.ns['_TICKSTORE_D4_ENTRY_RELEASE_STATE_BOUNDARY'])
        self.obj = self.ns['State'](self.root)

    def test_state_constructor_does_not_rewrite(self):
        before = self.sp.read_bytes(); stat_before = self.sp.stat()
        self.ns['State'](self.root)
        self.assertEqual(self.sp.read_bytes(), before)
        self.assertEqual(self.sp.stat().st_mtime_ns, stat_before.st_mtime_ns)

    def test_missing_state_never_recreated(self):
        self.sp.unlink()
        with self.assertRaisesRegex(RuntimeError, 'CONCURRENT_CHANGE'):
            self.ns['atomj'](self.sp, self.state)
        self.assertFalse(self.sp.exists())

    def test_changed_config_never_consumed(self):
        self.cfg.write_text('{"control_root":"unadmitted"}')
        with self.assertRaisesRegex(RuntimeError, 'CONFIG_DRIFT'): self.ns['rj'](self.cfg)
        self.assertEqual(json.loads(self.cfg.read_text())['control_root'], 'unadmitted')

    def test_config_negative_control_unchanged_buffer(self):
        self.assertEqual(self.ns['rj'](self.cfg), {'control_root': str(self.root)})

    def test_cannot_skip_to_full(self):
        obj = copy.deepcopy(self.state); obj['completed'].append('G3'); obj['next_node'] = 'G4'
        before = self.sp.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'COMPLETION_JUMP'): self.ns['atomj'](self.sp, obj)
        self.assertEqual(self.sp.read_bytes(), before)

    def test_single_stage_commit_and_native_readback(self):
        self.obj.finish('D5', 'PASS', {'fixture': True})
        actual = json.loads(self.sp.read_bytes())
        self.assertEqual(actual['next_node'], 'D6'); self.assertEqual(actual['completed'], ['D4', 'D5'])
        self.assertFalse(any('.cas-' in p.name for p in self.sp.parent.iterdir()))

    def test_d4_default_rejects_post_d4(self):
        with self.assertRaisesRegex(RuntimeError, 'STATE_NOT_D4_ONLY'): entry.validate_d4_state(self.state)

    def test_no_receipt_clobber_under_race(self):
        path = self.root/'receipt.json'; gate = threading.Barrier(2); results = []
        writer = adapter.make_no_clobber_receipt_writer(lambda why: (_ for _ in ()).throw(RuntimeError(why)))
        def compete(data):
            gate.wait()
            try: writer(path, data); results.append(('PASS', data))
            except RuntimeError: results.append(('BLOCKED', data))
        ts = [threading.Thread(target=compete, args=(v,)) for v in (b'one', b'two')]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(sorted(x[0] for x in results), ['BLOCKED', 'PASS'])
        winner = next(x[1] for x in results if x[0] == 'PASS')
        self.assertEqual(path.read_bytes(), winner)
        with self.assertRaisesRegex(RuntimeError, 'ALREADY_EXISTS'): writer(path, b'three')
        self.assertEqual(path.read_bytes(), winner)


class NativeResumeTests(unittest.TestCase):
    def test_named_stop_then_resume_with_different_worker_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, dest, days, months, contract, ids, cert = fixture(root)
            scratch = root/'scratch'; scratch.mkdir(); admission = FixtureAdmission()
            original_progress = mw._print_progress
            stopped = []
            def request(**kwargs):
                original_progress(**kwargs)
                if not stopped:
                    e = StopEvent(admission.instance['run_id'], request=True); e.close(); stopped.append(True)
            with patch.object(core, 'full_release_materials', return_value=(contract, cert, ids)), \
                 patch.object(core, 'load_ledgers', return_value=(days, months, core.EXPECTED_P4A_LEDGER_SHA256)):
                with patch.object(mw, '_print_progress', side_effect=request):
                    with self.assertRaises(KeyboardInterrupt):
                        mw._execute_admitted_multiwork(source, dest, scratch, root/'fixture-ledger', '2', 2, 60, admission)
                self.assertFalse((dest/'TICKSTORE_WRITER.lock').exists())
                self.assertEqual(mw._execute_admitted_multiwork(source, dest, scratch, root/'fixture-ledger', '1', 2, 60, admission), 0)
                before = {p.relative_to(dest).as_posix(): core.sha256_file(p) for p in dest.rglob('*') if p.is_file()}
                self.assertEqual(mw._execute_admitted_multiwork(source, dest, scratch, root/'fixture-ledger', '2', 2, 60, admission), 0)
                after = {p.relative_to(dest).as_posix(): core.sha256_file(p) for p in dest.rglob('*') if p.is_file()}
                self.assertEqual(before, after)


class InstallerAndLauncherTests(unittest.TestCase):
    def setUp(self):
        import subprocess
        self.subprocess = subprocess
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ps = str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')

    def package(self, member=None, corrupt_file_hash=False):
        import zipfile
        from D4_FIRST_ADMISSION_PREP import canonical, sha
        name = member or 'implementation_v001/candidate/control/RUN_TICKSTORE_FULL.ps1'
        payload = b'# ISOLATED INSTALLER FIXTURE; NOT A RUNNER\n'
        # R43-B1B: since R40 the installer requires the MENU member before any write.
        menu_name = 'implementation_v001/candidate/menu/MENU.py'
        menu_payload = b'# ISOLATED INSTALLER FIXTURE MENU; NOT A MENU\n'
        manifest = canonical(dict(schema='TICKSTORE_FINAL_PACKAGE_MANIFEST_V001',
                    files=[dict(path=menu_name, bytes=len(menu_payload), sha256=sha(menu_payload)),
                           dict(path=name, bytes=len(payload), sha256='0'*64 if corrupt_file_hash else sha(payload))]))
        archive = self.root/'fixture.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr(menu_name, menu_payload); z.writestr(name, payload); z.writestr('PACKAGE_MANIFEST.json', manifest)
        witness = self.root/'witness.json'
        witness.write_bytes(canonical(dict(schema='TICKSTORE_FINAL_PACKAGE_WITNESS_V001',
            package_name=archive.name, package_sha256=sha(archive.read_bytes()), manifest_sha256=sha(manifest))))
        return witness, sha(archive.read_bytes()), payload

    def install(self, witness):
        return self.subprocess.run([self.ps, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
             str(ROOT/'control/INSTALL_TICKSTORE_FULL.ps1'), '-WitnessPath', str(witness),
             '-InstallRoot', str(self.root/'isolated-install')], capture_output=True, text=True, timeout=40)

    def test_native_ps51_extract_readback_and_collision_preserved(self):
        witness, digest, payload = self.package(); result = self.install(witness)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.root/'isolated-install'/digest
        self.assertEqual((target/'implementation_v001/candidate/control/RUN_TICKSTORE_FULL.ps1').read_bytes(), payload)
        self.assertFalse(json.loads((target/'DEPLOYMENT.json').read_text())['production_started'])
        before = {p: p.read_bytes() for p in target.rglob('*') if p.is_file()}
        again = self.install(witness)
        self.assertEqual(again.returncode, 2); self.assertIn('ALREADY_EXISTS', again.stdout)
        self.assertEqual(before, {p: p.read_bytes() for p in target.rglob('*') if p.is_file()})

    def test_zip_path_escape_rejected_before_extraction(self):
        witness, _, _ = self.package('../escape.txt'); result = self.install(witness)
        self.assertEqual(result.returncode, 2); self.assertIn('MEMBER_SEGMENT', result.stdout)
        self.assertFalse((self.root/'isolated-install').exists())

    def test_file_hash_mismatch_preserves_partial_no_deployment(self):
        witness, digest, _ = self.package(corrupt_file_hash=True); result = self.install(witness)
        self.assertEqual(result.returncode, 2); self.assertIn('INSTALL_READBACK', result.stdout)
        target = self.root/'isolated-install'/digest
        self.assertTrue(target.exists()); self.assertFalse((target/'DEPLOYMENT.json').exists())

    def test_zip_hash_mismatch_prevents_extraction(self):
        witness, _, _ = self.package()
        with (self.root/'fixture.zip').open('ab') as f: f.write(b'changed')
        result = self.install(witness)
        self.assertEqual(result.returncode, 2); self.assertIn('PACKAGE_SHA256', result.stdout)
        self.assertFalse((self.root/'isolated-install').exists())

    def test_readonly_launcher_missing_chain_never_dispatches_d4(self):
        result = self.subprocess.run([self.ps, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
             str(ROOT/'control/RUN_TICKSTORE_FULL.ps1'), '-Stage', 'Check', '-ChainFile', str(self.root/'absent.json'),
             '-ChainSha256', 'A'*64, '-B06Sha256', 'B'*64], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('FULL_RUNNER_BLOCKED', result.stdout)
        self.assertEqual(list(self.root.iterdir()), [])


class ResourceAndNamespaceTests(unittest.TestCase):
    def test_native_job_memory_contains_coordinator_and_child(self):
        ctx = mp.get_context('spawn'); ready = ctx.Event(); finished = ctx.Event(); job = ProcessJob()
        child = None
        try:
            child = job.start(ctx, child_wait, args=(ready, finished))
            self.assertTrue(ready.wait(20))
            snap = job.memory_snapshot()
            self.assertEqual({r['pid'] for r in snap['processes']}, {os.getpid(), child.pid})
            self.assertGreater(snap['working_set_bytes'], 0); self.assertGreater(snap['private_bytes'], 0)
            self.assertTrue(all(r['creation_filetime'] > 0 for r in snap['processes']))
        finally:
            job.close()
            if child: child.join(20)
        self.assertFalse(child.is_alive())

    def test_launch_drain_stop_controls(self):
        gib = 1024**3; memory = {'total': 10*gib, 'available': 8*gib}
        self.assertEqual(mw.memory_decision({'working_set_bytes': gib, 'private_bytes': gib}, memory, 60), 'LAUNCH')
        self.assertEqual(mw.memory_decision({'working_set_bytes': 5*gib, 'private_bytes': gib}, memory, 60), 'DRAIN')
        self.assertEqual(mw.memory_decision({'working_set_bytes': gib, 'private_bytes': 6*gib}, memory, 60), 'SAFE_STOP')
        self.assertEqual(mw.memory_decision({'working_set_bytes': gib, 'private_bytes': gib}, dict(memory, available=gib), 60), 'SAFE_STOP')

    def test_namespace_reuse_and_history_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); old = root/'FULL_MULTIWORK_RC4R2'; old.mkdir()
            marker = old/'COORDINATOR_STATE.json'; marker.write_bytes(b'historical-do-not-mutate')
            a = FixtureAdmission(); selected = mw.instance_scratch(root, a, {'source_root': 'fixture'})
            self.assertEqual(selected.parent, root/'RUN_INSTANCES')
            self.assertEqual(mw.instance_scratch(root, a, {'source_root': 'fixture'}), selected)
            a.descriptor['code_manifest_sha256'] = 'C'*64
            with self.assertRaisesRegex(RuntimeError, 'INSTANCE_DRIFT'):
                mw.instance_scratch(root, a, {'source_root': 'fixture'})
            self.assertEqual(marker.read_bytes(), b'historical-do-not-mutate')

    def test_auto_cpu_zero_one_n_and_invalid_request(self):
        mem = {'total': 32*1024**3, 'available': 24*1024**3}
        with patch.object(mw, 'windows_memory_status', return_value=mem), patch.object(mw.os, 'cpu_count', return_value=8):
            self.assertEqual(mw.choose_workers('AUTO', 1, 32, 60)[0], 1)
            self.assertEqual(mw.choose_workers('AUTO', 20, 32, 60)[0], 6)
            with self.assertRaisesRegex(RuntimeError, 'OUT_OF_RANGE'): mw.choose_workers('0', 20, 32, 60)
            with self.assertRaisesRegex(RuntimeError, 'CPU_BUDGET'): mw.choose_workers('7', 20, 32, 60)

    def test_resource_stop_uses_checkpoint_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source, dest, days, months, contract, ids, cert = fixture(root)
            scratch = root/'scratch'; scratch.mkdir(); admission = FixtureAdmission()
            with patch.object(core, 'full_release_materials', return_value=(contract, cert, ids)), \
                 patch.object(core, 'load_ledgers', return_value=(days, months, core.EXPECTED_P4A_LEDGER_SHA256)), \
                 patch.object(mw, 'memory_decision', return_value='SAFE_STOP'):
                with self.assertRaises(mw.CooperativeSafeStop) as stopped:
                    mw._execute_admitted_multiwork(source, dest, scratch, root/'fixture-ledger', '1', 1, 60, admission)
            self.assertIsInstance(stopped.exception.__cause__, mw.ResourceSafeStop)
            self.assertEqual(str(stopped.exception.__cause__), 'RAM_PRESSURE')
            self.assertFalse((dest/'TICKSTORE_WRITER.lock').exists())


class D4ClosureProofTests(unittest.TestCase):
    def setUp(self):
        from FULL_D4_CLOSURE import verify_complete_checkpoint
        from D4_FIRST_ADMISSION_PREP import canonical, sha
        self.verify = verify_complete_checkpoint; self.canon = canonical; self.sha = sha
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'checkpoint/chunks').mkdir(parents=True); (self.root/'recovery').mkdir()
        self.ns = load_library((ROOT/'recovery/engine/tickstore_publisher_recovery_v004_release.py').read_bytes(),
                               ROOT/'recovery/engine/tickstore_publisher_recovery_v004_release.py')
        self.key = b'F'*32  # Isolated signature fixture, never persisted as a productive authority.
        self.day = '20260730'
        entry = {'namespace': 'FIXTURE', 'contract': {'date_key': self.day},
                 'journal': {'path': 'FIXTURE/day.jsonl', 'sha256': '1'*64, 'bytes': 10},
                 'partial': {'path': 'FIXTURE/day.partial', 'sha256': '2'*64, 'bytes': 20}}
        self.descriptor = {'s0_inventory': {self.day: entry}, 'recovery_root': str(self.root/'recovery')}
        self.ra = dict(run_id='C'*32, key_sha256=sha(self.key), successor_release_sha256='A'*64,
                       config_sha256='B'*64, owner_gate_sha256='D'*64,
                       generation={'fixture': True}, resume_root=str(self.root/'checkpoint'))
        self.ra_raw = canonical(self.ra)
        self.ctx = dict(self.ra, key=self.key, total=1, run_authority_sha256=sha(self.ra_raw),
                        generation_sha256=self.ns['_d4r_sha_obj'](self.ra['generation']),
                        shadow_root='FIXTURE_SHADOW', inventory=self.descriptor['s0_inventory'])
        self.ns['_D4R_RUNTIME_AUTHORITY'] = self.ctx
        observed = {kind: dict(entry[kind], identity={'fixture': True}) for kind in ('journal', 'partial')}
        result = dict(date_key=self.day, oracle=entry['contract'], evidence=observed,
                      container_sha256=entry['partial']['sha256'], container_bytes=20)
        self.att = self.ns['_d4r_attestation'](self.day, entry, result, observed, 1, 2)
        self.receipt = self.root/'recovery'/('d4_resume_prepared.' + self.ra['run_id'] + '.' + self.day + '.json')
        self.mirror = self.root/'checkpoint/chunks'/(self.day + '.json')
        self.update_attestation()

    def update_attestation(self):
        raw = self.canon(self.att); self.receipt.write_bytes(raw); self.mirror.write_bytes(raw)
        self.cp = self.ns['_d4r_checkpoint_payload']({self.day: self.sha(raw)}, 'ALL_CHUNKS_COMMITTED')

    def run_proof(self, sign_key=None):
        signed = self.ns['_d4r_sign'](self.cp, sign_key or self.key, 'TICKSTORE_D4_SIGNED_CHECKPOINT_V003')
        return self.verify(self.ns, self.ra_raw, self.descriptor, self.key, self.canon(signed),
                           lambda p, expected: Path(p).read_bytes())

    def test_complete_checkpoint_readback_without_mutation(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        cp, evidence = self.run_proof()
        self.assertEqual(cp['committed_count'], 1); self.assertEqual(len(evidence), 1)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertIs(self.ns['_D4R_RUNTIME_AUTHORITY'], self.ctx)

    def test_wrong_signature(self):
        with self.assertRaisesRegex(RuntimeError, 'CHECKPOINT_HMAC'): self.run_proof(b'X'*32)

    def test_wrong_run_with_valid_signature(self):
        self.cp['run_id'] = 'E'*32
        with self.assertRaisesRegex(RuntimeError, 'BINDING:run_id'): self.run_proof()

    def test_incomplete_checkpoint(self):
        self.cp['status'] = 'RUNNING'
        with self.assertRaisesRegex(RuntimeError, 'INCOMPLETE_CHECKPOINT'): self.run_proof()

    def test_missing_immutable_receipt(self):
        self.receipt.unlink()
        with self.assertRaises(FileNotFoundError): self.run_proof()

    def test_chunk_mirror_mismatch(self):
        self.mirror.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'CHUNK_READBACK'): self.run_proof()

    def test_attestation_signature_mismatch(self):
        self.att['hmac_sha256'] = '0'*64; self.update_attestation()
        with self.assertRaisesRegex(RuntimeError, 'ATTESTATION_HMAC'): self.run_proof()

    def test_signed_semantic_divergence(self):
        p = self.att['payload']; p['result']['container_bytes'] = 19
        p['result_sha256'] = self.ns['_d4r_sha_obj'](p['result'])
        self.att = self.ns['_d4r_sign'](p, self.key, 'TICKSTORE_D4_SIGNED_ATTESTATION_V003')
        self.update_attestation()
        with self.assertRaisesRegex(RuntimeError, 'RESULT_CONTAINER_BYTES'): self.run_proof()


class ClosedStageEvidenceTests(unittest.TestCase):
    def journal(self, items):
        from D4_FIRST_ADMISSION_PREP import canonical, sha
        lines = []; previous = ''
        for item in items:
            raw = canonical(dict(item, prev_line_sha256=previous)).rstrip(b'\n')
            lines.append(raw); previous = sha(raw)
        return b'\n'.join(lines) + b'\n'

    def test_latest_started_cannot_reuse_previous_pass(self):
        from FULL_STAGE_EVIDENCE import closed_results
        journal = self.journal([dict(node='D4', phase='STARTED', run_id='old'),
                    dict(node='D4', phase='FINISHED', status='PASS', result_sha256='A'*64),
                    dict(node='D4', phase='STARTED', run_id='new')])
        def forbidden(*args): self.fail('unclosed attempt must fail before result access')
        with self.assertRaisesRegex(RuntimeError, 'UNCLOSED_OR_FAILED'): closed_results(journal, ('D4',), Path('fixture'), forbidden)

    def test_finished_without_started_blocks(self):
        from FULL_STAGE_EVIDENCE import closed_results
        journal = self.journal([dict(node='D4', phase='FINISHED', status='PASS')])
        with self.assertRaisesRegex(RuntimeError, 'UNPAIRED_FINISH'):
            closed_results(journal, ('D4',), Path('fixture'), lambda *a: b'{}')

    def test_current_finished_attempt_exact_bytes(self):
        from FULL_STAGE_EVIDENCE import closed_results
        from D4_FIRST_ADMISSION_PREP import canonical, sha
        raw = canonical({'cert_sha256': 'C'*64}); opened = []
        journal = self.journal([dict(node='D4', phase='STARTED', run_id='new'),
                               dict(node='D4', phase='FINISHED', status='PASS', result_sha256=sha(raw))])
        def read(path, expected): opened.append(path); return raw
        result, evidence = closed_results(journal, ('D4',), Path('fixture'), read)
        self.assertEqual(result['D4']['cert_sha256'], 'C'*64)
        self.assertEqual(opened, [Path('fixture/new/RESULT_D4.json')]); self.assertEqual(len(evidence), 1)

    def test_result_hash_drift_blocks(self):
        from FULL_STAGE_EVIDENCE import closed_results
        journal = self.journal([dict(node='D4', phase='STARTED', run_id='new'),
                               dict(node='D4', phase='FINISHED', status='PASS', result_sha256='A'*64)])
        with self.assertRaisesRegex(RuntimeError, 'JOURNAL_HASH'):
            closed_results(journal, ('D4',), Path('fixture'), lambda *a: b'{}')


class RunnerDispatchTests(unittest.TestCase):
    def test_d4_safe_stop_does_not_close_or_advance(self):
        import FULL_RUNNER as runner
        from unittest.mock import MagicMock
        admission = MagicMock(); admission.instance = {}
        context = MagicMock(); context.__enter__.return_value = admission
        args = types.SimpleNamespace(stage='D4', chain_file='fixture', chain_sha256='A'*64, b06_sha256='B'*64, resume=True)
        with patch.object(runner, 'ReleaseChain', return_value=context), patch.object(runner, 'd4_command', return_value=['fixture']), \
             patch.object(runner.subprocess, 'call', return_value=130), patch('FULL_D4_CLOSURE.close_d4') as close:
            self.assertEqual(runner.run(args), 130); close.assert_not_called()

    def test_d4_exit_zero_requires_closure(self):
        import FULL_RUNNER as runner
        from unittest.mock import MagicMock
        admission = MagicMock(); admission.instance = {}
        context = MagicMock(); context.__enter__.return_value = admission
        args = types.SimpleNamespace(stage='D4', chain_file='fixture', chain_sha256='A'*64, b06_sha256='B'*64, resume=False)
        with patch.object(runner, 'ReleaseChain', return_value=context), patch.object(runner, 'd4_command', return_value=['fixture']), \
             patch.object(runner.subprocess, 'call', return_value=0), \
             patch('FULL_D4_CLOSURE.close_d4', side_effect=RuntimeError('UNPROVEN')) as close:
            with self.assertRaisesRegex(RuntimeError, 'UNPROVEN'): runner.run(args)
            close.assert_called_once_with(admission)

    def test_no_unbounded_or_foreign_d4_arguments(self):
        import FULL_RUNNER as runner
        d = {name: 'fixture' for name in runner.D4_PARAMETERS}; d['Until'] = 'FULL'
        with self.assertRaisesRegex(RuntimeError, 'PARAMETER_SET'): runner.d4_command({'d4_parameters': d}, ROOT)


if __name__ == '__main__':
    unittest.main(verbosity=2)
