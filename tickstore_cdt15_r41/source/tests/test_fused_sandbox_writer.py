"""New delta only: merged critical section on a disposable sandbox."""
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

R=Path(__file__).resolve().parents[1]
C=R/'candidate'/'control'
sys.path.insert(0,str(C))
sys.path.insert(0,str(R/'tests'))
from test_menu_tx_interprocess import CoordinatorInterprocessDelta, PKG, WIT, OLD, NEW, sha
from MENU_TX_FUSED_SANDBOX import locked_stage_commit_sandbox
from MENU_TX_INTERPROCESS_SANDBOX import SandboxKernelLock, locked_reconcile
from TX_SANDBOX_MODEL import Blocked, SimulatedCrash
import MENU_TX_FUSED_SANDBOX as fused

_setup_existing_fixture = CoordinatorInterprocessDelta.setUp
del CoordinatorInterprocessDelta  # avoid rediscovering its 17 historical cases

class FusedSandboxWriterTests(unittest.TestCase):
    def setUp(self):
        _setup_existing_fixture(self)

    def run_fused(self, **kw):
        opts={'installed_root':self.inst,'sandbox_root':self.sandbox,
              'trusted_package_sha256':PKG,'trusted_witness_sha256':WIT,
              'expected_old_menu_sha256':sha(OLD),'expected_old_active_sha256':None}
        opts.update(kw)
        return locked_stage_commit_sandbox(**opts)

    def test01_one_shot_commit(self):
        r=self.run_fused()
        self.assertEqual(r['status'],'PASS_SANDBOX_ONLY')
        self.assertEqual(r['phase'],'COMMITTED')
        self.assertFalse(r['effectful_authorized'])
        self.assertEqual(self.menu.read_bytes(),NEW)
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_ALREADY_COMMITTED_NO_WRITE')

    def test02_second_call_fail_closed_no_replacement(self):
        self.run_fused()
        with self.assertRaisesRegex(Blocked,'PRIOR_TRANSACTION'):
            self.run_fused()
        self.assertEqual(self.menu.read_bytes(),NEW)

    def test03_lock_held_across_stage_and_begin(self):
        reached=threading.Event()
        allow=threading.Event()
        failures=[]
        original=fused.stage_verified_inert_intent
        def paused(*args, **kwargs):
            x=original(*args,**kwargs)
            reached.set()
            if not allow.wait(10): raise RuntimeError('TEST_PAUSE_TIMEOUT')
            return x
        def work():
            try: self.run_fused()
            except BaseException as exc: failures.append(exc)
        with patch.object(fused,'stage_verified_inert_intent',side_effect=paused):
            thread=threading.Thread(target=work,daemon=True)
            thread.start()
            try:
                self.assertTrue(reached.wait(10))
                contender = (
                    'import sys;from pathlib import Path;'
                    'from MENU_TX_INTERPROCESS_SANDBOX import SandboxKernelLock;'
                    'from TX_SANDBOX_MODEL import Blocked\n'
                    'try:\n'
                    ' with SandboxKernelLock(Path(sys.argv[2])): pass\n'
                    ' sys.exit(9)\n'
                    'except Blocked as e:\n'
                    ' sys.exit(0 if str(e)=="SANDBOX_COORDINATOR_BUSY" else 8)\n'
                )
                proc=subprocess.run([sys.executable,'-I','-B','-c',
                                     'import sys;sys.path.insert(0,sys.argv[1]);\n' + contender,
                                     str(C),str(self.sandbox)],capture_output=True,text=True,timeout=10)
                self.assertEqual(proc.returncode,0,proc.stderr)
                self.assertFalse((self.sandbox/'active/MENU_TRANSACTION').exists())
            finally:
                allow.set();thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertFalse(failures,failures)
        self.assertEqual(self.menu.read_bytes(),NEW)

    def test04_staging_drift_blocks_before_transaction(self):
        self.menu.write_bytes(b'DRIFT')
        with self.assertRaisesRegex(Blocked,'HASH_MISMATCH'):
            self.run_fused()
        self.assertFalse((self.sandbox/'active/MENU_TRANSACTION').exists())

    def test05_wrong_package_pin_blocks(self):
        with self.assertRaisesRegex(Exception,'(INTENT_EXTERNAL_BINDING|INSTALLATION_ROOT_BINDING)'):
            self.run_fused(trusted_package_sha256='C'*64)
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test06_wrong_witness_pin_blocks(self):
        with self.assertRaisesRegex(Exception,'INTENT_EXTERNAL_BINDING'):
            self.run_fused(trusted_witness_sha256='C'*64)
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test07_wrong_sandbox_name_blocks(self):
        with self.assertRaisesRegex(Blocked,'FUSED_SANDBOX_EXACT_NAME_REQUIRED'):
            self.run_fused(sandbox_root=self.base/'not_sandbox')

    def test08_existing_active_preserved_as_input_and_commits(self):
        oldactive=b'OLD_DEPLOYMENT\n'
        self.active.write_bytes(oldactive)
        r=self.run_fused(expected_old_active_sha256=sha(oldactive))
        self.assertEqual(r['phase'],'COMMITTED')
        self.assertNotEqual(self.active.read_bytes(),oldactive)

    def test09_corrupt_staged_candidate_blocks_second_run(self):
        (self.sandbox/'candidate/MENU.py').write_bytes(b'STALE')
        with self.assertRaisesRegex(Blocked,'SANDBOX_CANDIDATE_ALREADY_STAGED'):
            self.run_fused()
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test10_intent_marked_authorized_blocks(self):
        import json
        p=self.inst/'MENU_INSTALL_INTENT.json'
        obj=json.loads(p.read_text());obj['effectful_authorized']=True
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(Exception,'INTENT_PREMATURE_EFFECT'):
            self.run_fused()
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test11_new_menu_corruption_blocks(self):
        p=self.inst/'implementation_v001/candidate/menu/MENU.py'
        p.write_bytes(b'ALTERED')
        with self.assertRaisesRegex(Exception,'INSTALLED_MEMBER_DRIFT'):
            self.run_fused()
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test12_crash_after_prepared_needs_explicit_reconcile(self):
        with self.assertRaisesRegex(SimulatedCrash,'AFTER_PREPARED'):
            self.run_fused(inject='AFTER_PREPARED')
        self.assertEqual(self.menu.read_bytes(),OLD)
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')

    def test13_crash_after_menu_write_recovers(self):
        with self.assertRaisesRegex(SimulatedCrash,'AFTER_MENU_WRITE_BEFORE_JOURNAL'):
            self.run_fused(inject='AFTER_MENU_WRITE_BEFORE_JOURNAL')
        self.assertEqual(self.menu.read_bytes(),NEW)
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test14_crash_after_active_write_recovers(self):
        with self.assertRaisesRegex(SimulatedCrash,'AFTER_ACTIVE_WRITE_BEFORE_JOURNAL'):
            self.run_fused(inject='AFTER_ACTIVE_WRITE_BEFORE_JOURNAL')
        self.assertTrue(self.active.exists())
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertFalse(self.active.exists())

    def test15_crash_after_active_published_recovers(self):
        with self.assertRaisesRegex(SimulatedCrash,'AFTER_ACTIVE_PUBLISHED'):
            self.run_fused(inject='AFTER_ACTIVE_PUBLISHED')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test16_lock_file_is_not_unlinked(self):
        self.run_fused()
        self.assertTrue(self.lockpath.is_file())
        self.assertEqual(self.lockpath.read_bytes(),b'CDT15_G4_INTERPROCESS_COORDINATOR_V001\n')

    def test17_reconcile_idempotent_after_recovery(self):
        with self.assertRaises(SimulatedCrash):
            self.run_fused(inject='AFTER_MENU_PUBLISHED')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_ALREADY_ROLLED_BACK_NO_WRITE')

    def test18_no_official_entrypoint_or_arbitrary_target(self):
        source=(C/'MENU_TX_FUSED_SANDBOX.py').read_text()
        self.assertNotIn("if __name__",source)
        self.assertNotIn('InstallRoot',source)
        self.assertNotIn('ACTIVE_DEPLOYMENT.json',source)
        self.assertIn('EXACT_SANDBOX',source)

if __name__=='__main__': unittest.main()
