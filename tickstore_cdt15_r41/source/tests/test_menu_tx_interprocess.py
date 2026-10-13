"""G4 new delta: sandbox coordinator under real separate-process contention."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = R / 'candidate' / 'control'
sys.path.insert(0, str(C))
from TX_SANDBOX_MODEL import SENTINEL, Blocked, sha, SimulatedCrash
from MENU_INTENT_TO_TX_SANDBOX import begin_sandbox_only
from MENU_TX_INTERPROCESS_SANDBOX import (
    SandboxKernelLock, LOCK_NAME, LOCK_MAGIC, locked_begin, locked_reconcile,
    locked_stage_intent,
)
from MENU_INSTALL_INTENT_VERIFY import MENU_REL, LAUNCHER_REL

PKG='A'*64
WIT='B'*64
OLD=b'OLD_MENU_STABLE\n'
NEW=(R/'candidate/menu/MENU.py').read_bytes()
LAUNCH=b'LAUNCHER_STABLE\n'

def raw(obj):
    return (json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')


class CoordinatorInterprocessDelta(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='CDT15_G4_COORDINATOR_TEST_')
        self.addCleanup(t.cleanup)
        self.base=Path(t.name)
        self.inst=self.base/'Candidates'/PKG
        self.inst.mkdir(parents=True)
        p=self.inst/MENU_REL
        p.parent.mkdir(parents=True)
        p.write_bytes(NEW)
        p=self.inst/LAUNCHER_REL
        p.parent.mkdir(parents=True)
        p.write_bytes(LAUNCH)
        manifest={'schema':'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001','files':[
            {'path':MENU_REL,'bytes':len(NEW),'sha256':sha(NEW)},
            {'path':LAUNCHER_REL,'bytes':len(LAUNCH),'sha256':sha(LAUNCH)}]}
        (self.inst/'PACKAGE_MANIFEST.json').write_bytes(raw(manifest))
        deployment={'schema':'TICKSTORE_DEPLOYMENT_V001','installation_root':str(self.inst),
            'package_sha256':PKG,'package_manifest_sha256':sha(raw(manifest)),
            'witness_sha256':WIT,'launcher_sha256':sha(LAUNCH),
            'status':'INSTALLED_NOT_PRODUCTION_ADMISSION','production_started':False}
        (self.inst/'DEPLOYMENT.json').write_bytes(raw(deployment))
        intent={'schema':'TICKSTORE_MENU_INSTALL_INTENT_V001','installation_root':str(self.inst),
            'package_sha256':PKG,'package_manifest_sha256':sha(raw(manifest)),
            'witness_sha256':WIT,'candidate_menu_relative_path':MENU_REL,
            'candidate_menu_sha256':sha(NEW),
            'active_deployment_sha256':sha(raw(deployment)),
            'launcher_sha256':sha(LAUNCH),'transaction_state':'NOT_STARTED',
            'effectful_authorized':False,'production_started':False}
        (self.inst/'MENU_INSTALL_INTENT.json').write_bytes(raw(intent))
        self.sandbox=self.base/'CDT15_G4_TXN_SANDBOX_INTENT'
        self.sandbox.mkdir()
        (self.sandbox/'SANDBOX_ONLY.txt').write_bytes(SENTINEL)
        for a in ('menu','active','candidate'):
            (self.sandbox/a).mkdir()
        (self.sandbox/'menu/MENU.py').write_bytes(OLD)
        self.menu=self.sandbox/'menu/MENU.py'
        self.active=self.sandbox/'active/ACTIVE_DEPLOYMENT.json'
        self.lockpath=self.sandbox/'active'/LOCK_NAME

    def stage(self,old_active=None):
        return locked_stage_intent(installed_root=self.inst,sandbox_root=self.sandbox,
            trusted_package_sha256=PKG,trusted_witness_sha256=WIT,
            expected_old_menu_sha256=sha(OLD),expected_old_active_sha256=old_active)

    def _child(self, body, *args):
        script='import sys,os,json\nsys.path.insert(0,sys.argv[1])\n' + body
        return subprocess.Popen([sys.executable,'-I','-B','-c',script,str(C),*map(str,args)],
                                stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,text=True)

    def _crash(self, stage, phase):
        pth=self.base/'stage.json';pth.write_bytes(raw(stage))
        body=('from pathlib import Path;from MENU_TX_INTERPROCESS_SANDBOX import locked_begin;'
              'from TX_SANDBOX_MODEL import SimulatedCrash;'
              'r=Path(sys.argv[2]);st=json.loads(Path(sys.argv[3]).read_text())\n'
              'try:locked_begin(sandbox_root=r,staged=st,inject=sys.argv[4])\n'
              'except SimulatedCrash:os._exit(77)\n')
        p=self._child(body,self.sandbox,pth,phase)
        _,err=p.communicate(timeout=10)
        self.assertEqual(p.returncode,77,err)

    def test01_lock_stage_then_begin(self):
        st=self.stage()
        self.assertTrue(self.lockpath.is_file())
        self.assertEqual(self.lockpath.read_bytes(),LOCK_MAGIC)
        self.assertEqual(locked_begin(sandbox_root=self.sandbox,staged=st),'PASS_SANDBOX_ONLY')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_ALREADY_COMMITTED_NO_WRITE')

    def test02_second_begin_blocks_without_overwrite(self):
        st=self.stage();locked_begin(sandbox_root=self.sandbox,staged=st)
        with self.assertRaisesRegex(Blocked,'EXISTING_TRANSACTION'):
            locked_begin(sandbox_root=self.sandbox,staged=st)
        self.assertEqual(self.menu.read_bytes(),NEW)

    def test03_interprocess_crash_after_prepared(self):
        st=self.stage();self._crash(st,'AFTER_PREPARED')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.menu.read_bytes(),OLD)
        self.assertFalse(self.active.exists())

    def test04_interprocess_crash_after_menu_write(self):
        st=self.stage();self._crash(st,'AFTER_MENU_WRITE_BEFORE_JOURNAL')
        self.assertEqual(self.menu.read_bytes(),NEW)
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.menu.read_bytes(),OLD)
        self.assertFalse(self.active.exists())

    def test05_interprocess_crash_after_active_write(self):
        st=self.stage();self._crash(st,'AFTER_ACTIVE_WRITE_BEFORE_JOURNAL')
        self.assertTrue(self.active.is_file())
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.menu.read_bytes(),OLD)
        self.assertFalse(self.active.exists())

    def test06_interprocess_crash_after_active_published(self):
        st=self.stage();self._crash(st,'AFTER_ACTIVE_PUBLISHED')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test07_interprocess_contender_blocked(self):
        body=('from pathlib import Path;from MENU_TX_INTERPROCESS_SANDBOX import SandboxKernelLock;'
              'r=Path(sys.argv[2])\n'
              'with SandboxKernelLock(r):\n print("LOCK_HELD",flush=True);sys.stdin.readline()\n')
        p=self._child(body,self.sandbox)
        try:
            ready=p.stdout.readline().strip()
            self.assertEqual(ready,'LOCK_HELD',p.stderr.read() if p.poll() is not None else ready)
            with self.assertRaisesRegex(Blocked,'SANDBOX_COORDINATOR_BUSY'):
                with SandboxKernelLock(self.sandbox): pass
            self.assertFalse((self.sandbox/'active/MENU_TRANSACTION').exists())
        finally:
            p.stdin.write('\n');p.stdin.flush()
            _,err=p.communicate(timeout=10)
            self.assertEqual(p.returncode,0,err)
        with SandboxKernelLock(self.sandbox): pass

    def test08_corrupted_lock_rejected_without_change(self):
        self.lockpath.write_bytes(b'WRONG\n')
        with self.assertRaisesRegex(Blocked,'LOCK_MAGIC_SIZE_INVALID'):
            self.stage()
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test09_hardlink_lock_rejected(self):
        other=self.base/'otherlock';other.write_bytes(LOCK_MAGIC)
        try:os.link(other,self.lockpath)
        except OSError:self.skipTest('hardlink unavailable')
        with self.assertRaisesRegex(Blocked,'HARDLINK_FILE|LOCK_NOT_SINGLE_REGULAR_FILE'):
            self.stage()

    def test10_symlink_lock_or_os_denial(self):
        other=self.base/'otherlock';other.write_bytes(LOCK_MAGIC)
        try:
            self.lockpath.symlink_to(other)
        except OSError:
            # Restricted Windows user: the OS prevented creation of the unsafe link.
            # This does NOT count as a successful native reparse-guard probe.
            self.assertFalse(self.lockpath.exists())
            return
        with self.assertRaisesRegex(Blocked,'REPARSE_PATH'):
            self.stage()

    def test11_wrong_sandbox_name_rejected(self):
        self.sandbox.rename(self.sandbox.with_name('CDT15_G4_TXN_SANDBOX_UNAUTHORIZED'))
        self.sandbox=self.sandbox.with_name('CDT15_G4_TXN_SANDBOX_UNAUTHORIZED')
        with self.assertRaisesRegex(Blocked,'COORDINATOR_EXACT_SANDBOX_REQUIRED'):
            self.stage()

    def test12_mutation_of_old_menu_after_staging_blocked(self):
        st=self.stage();self.menu.write_bytes(b'UNEXPECTED_DRIFT\n')
        with self.assertRaisesRegex(Blocked,'HASH_MISMATCH'):
            locked_begin(sandbox_root=self.sandbox,staged=st)
        self.assertFalse((self.sandbox/'active/MENU_TRANSACTION').exists())

    def test13_reacquire_from_independent_process(self):
        self.stage()
        body=('from pathlib import Path;from MENU_TX_INTERPROCESS_SANDBOX import SandboxKernelLock;'
              '\nwith SandboxKernelLock(Path(sys.argv[2])):print("PASS_REACQUIRE",flush=True)\n')
        p=self._child(body,self.sandbox)
        out,err=p.communicate(timeout=10)
        self.assertEqual(p.returncode,0,err)
        self.assertIn('PASS_REACQUIRE',out)

    def test14_existing_active_restored_after_child_crash(self):
        oldactive=b'OLD_DEPLOYMENT\n';self.active.write_bytes(oldactive)
        st=self.stage(old_active=sha(oldactive))
        self._crash(st,'AFTER_ACTIVE_WRITE_BEFORE_JOURNAL')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.active.read_bytes(),oldactive)
        self.assertEqual(self.menu.read_bytes(),OLD)

    def test15_repeat_reconcile_idempotent_after_exit(self):
        st=self.stage();self._crash(st,'AFTER_MENU_PUBLISHED')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(locked_reconcile(sandbox_root=self.sandbox),'PASS_ALREADY_ROLLED_BACK_NO_WRITE')

    def test16_never_remove_lock_file(self):
        st=self.stage();self.assertTrue(self.lockpath.exists())
        self.assertEqual(locked_begin(sandbox_root=self.sandbox,staged=st),'PASS_SANDBOX_ONLY')
        self.assertEqual(self.lockpath.read_bytes(),LOCK_MAGIC)

    def test17_no_generic_effectful_cli(self):
        s=(C/'MENU_TX_INTERPROCESS_SANDBOX.py').read_text()
        self.assertNotIn('if __name__',s)
        self.assertNotIn('INSTALL_TICKSTORE_FULL',s)
        self.assertNotIn('ACTIVE_DEPLOYMENT.json',s)

if __name__ == '__main__':unittest.main()
