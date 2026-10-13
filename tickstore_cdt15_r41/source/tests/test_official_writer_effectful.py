"""R41: effectful official writer in disposable qualification sandboxes.

Every crash case kills a separate writer process abruptly (os._exit) at a
protocol point and recovers with a NEW process.  On Windows the same tests use
the native ReplaceFileW/MoveFileExW/share-none lock path and two volumes when
TICKSTORE_QUAL_D_PARENT/TICKSTORE_QUAL_C_PARENT name sandbox parents on D:/C:.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = R / 'candidate' / 'control'
sys.path.insert(0, str(C))
import MENU_OFFICIAL_WRITER as W  # noqa: E402
from MENU_INSTALL_INTENT_VERIFY import MENU_REL, LAUNCHER_REL  # noqa: E402

PKG = 'C0FFEE' + 'A' * 58
WIT = 'B' * 64
OLD = b'# historical MENU fixture\nprint("old")\n'
BAT = 'echo fixture\r\n'.encode('ascii')
NEW = (R / 'candidate/menu/MENU.py').read_bytes()
LAUNCH = b'LAUNCHER_FIXTURE\n'
WRITER = str(C / 'MENU_OFFICIAL_WRITER.py')
CRASH_POINTS = ('AFTER_PREPARED', 'AFTER_MENU_PENDING', 'BEFORE_MENU_REPLACE',
                'AFTER_MENU_REPLACE_BEFORE_JOURNAL', 'AFTER_MENU_PUBLISHED', 'AFTER_ACTIVE_PENDING',
                'AFTER_ACTIVE_MOVE_BEFORE_JOURNAL', 'AFTER_ACTIVE_PUBLISHED')


def raw(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def load_menu_consumer():
    """Import the candidate MENU with its D: pipeline siblings stubbed."""
    paths = types.ModuleType('paths')
    paths.PATHS = types.SimpleNamespace(BIBLIOTECA_ROOT=R, BASE_ROOT=R)
    orq = types.ModuleType('GERAR_BASE_COMPLETA'); orq.ETAPAS = []
    saved = {k: sys.modules.get(k) for k in ('paths', 'GERAR_BASE_COMPLETA')}
    sys.modules['paths'] = paths; sys.modules['GERAR_BASE_COMPLETA'] = orq
    try:
        spec = importlib.util.spec_from_file_location('candidate_menu_r41', R / 'candidate/menu/MENU.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None: sys.modules.pop(k, None)
            else: sys.modules[k] = v


MENU_CONSUMER = load_menu_consumer()


class WriterSandbox(unittest.TestCase):
    def setUp(self):
        d_parent = os.environ.get('TICKSTORE_QUAL_D_PARENT')
        c_parent = os.environ.get('TICKSTORE_QUAL_C_PARENT')
        tmp = tempfile.TemporaryDirectory(prefix='R41_WRITER_')
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        tag = uuid.uuid4().hex[:12].upper()
        self.d = Path(d_parent or base) / (W.SANDBOX_PREFIX + 'D_' + tag)
        self.c = Path(c_parent or base) / (W.SANDBOX_PREFIX + 'C_' + tag)
        for root in (self.d, self.c):
            root.mkdir(parents=True)
            (root / 'SANDBOX_ONLY.txt').write_bytes(W.SANDBOX_SENTINEL)
        menu = self.d / 'Base CSV/Scripts/Biblioteca/MENU.py'
        menu.parent.mkdir(parents=True); menu.write_bytes(OLD)
        (self.d / 'Base CSV/Manutenção Base de Dados.bat').write_bytes(BAT)
        self.inst = self.c / 'TICKSTORE/Candidates' / PKG
        for rel, data in ((MENU_REL, NEW), (LAUNCHER_REL, LAUNCH)):
            p = self.inst / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        manifest = {'schema': 'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001', 'files': [
            {'path': MENU_REL, 'bytes': len(NEW), 'sha256': W.sha(NEW)},
            {'path': LAUNCHER_REL, 'bytes': len(LAUNCH), 'sha256': W.sha(LAUNCH)}]}
        (self.inst / 'PACKAGE_MANIFEST.json').write_bytes(raw(manifest))
        dep = {'schema': 'TICKSTORE_DEPLOYMENT_V001', 'installation_root': str(self.inst),
               'package_sha256': PKG, 'package_manifest_sha256': W.sha(raw(manifest)),
               'witness_sha256': WIT, 'launcher_sha256': W.sha(LAUNCH),
               'status': 'INSTALLED_NOT_PRODUCTION_ADMISSION', 'production_started': False}
        self.dep = raw(dep)
        (self.inst / 'DEPLOYMENT.json').write_bytes(self.dep)
        intent = {'schema': 'TICKSTORE_MENU_INSTALL_INTENT_V001', 'installation_root': str(self.inst),
                  'package_sha256': PKG, 'package_manifest_sha256': W.sha(raw(manifest)),
                  'witness_sha256': WIT, 'candidate_menu_relative_path': MENU_REL,
                  'candidate_menu_sha256': W.sha(NEW), 'active_deployment_sha256': W.sha(self.dep),
                  'launcher_sha256': W.sha(LAUNCH), 'transaction_state': 'NOT_STARTED',
                  'effectful_authorized': False, 'production_started': False}
        (self.inst / 'MENU_INSTALL_INTENT.json').write_bytes(raw(intent))
        self.layout = W.qualification_layout(self.d, self.c, W.sha(OLD), W.sha(BAT))
        if d_parent and os.name == 'nt':
            # Windows qualification proves the real cross-volume binding.
            self.assertTrue(self.layout.cross_volume_required)

    # helpers ------------------------------------------------------------------
    def cli(self, mode, *extra):
        args = [sys.executable, '-I', '-B', WRITER, '--mode', mode, '--d-root', str(self.d),
                '--c-root', str(self.c), '--menu-before-sha256', W.sha(OLD), '--bat-sha256', W.sha(BAT)]
        if mode == 'qualification-publish':
            args += ['--installed-root', str(self.inst), '--package-sha256', PKG, '--witness-sha256', WIT]
        return subprocess.run(args + list(extra), capture_output=True, text=True, timeout=120)

    def publish(self, **kw):
        return W.publish(self.layout, installed_root=self.inst, trusted_package_sha256=PKG,
                         trusted_witness_sha256=WIT, **kw)

    def state(self):
        return (W.sha(self.layout.menu.read_bytes()) if self.layout.menu.exists() else None,
                W.sha(self.layout.active.read_bytes()) if self.layout.active.exists() else None)

    def consumer(self):
        return MENU_CONSUMER._tickstore_committed_deployment(self.layout.active, self.layout.menu)

    def assert_before(self):
        self.assertEqual(self.state(), (W.sha(OLD), None))

    def assert_after(self):
        self.assertEqual(self.state(), (W.sha(NEW), W.sha(self.dep)))


class Nominal(WriterSandbox):
    def test_01_publish_commits_and_consumer_accepts(self):
        out = self.publish()
        self.assertEqual(out['status'], 'COMMITTED')
        self.assert_after()
        self.assertEqual(self.consumer()['package_sha256'], PKG)
        backup = self.layout.token_paths(PKG)['menu_backup']
        self.assertEqual(backup.read_bytes(), OLD)
        self.assertEqual(backup.parent, self.layout.menu.parent)
        phases = sorted(p.name for p in self.layout.tx.iterdir() if p.name.startswith('PHASE_'))
        self.assertEqual(phases, ['PHASE_01_PREPARED.json', 'PHASE_02_MENU_PUBLISHED.json',
                                  'PHASE_03_ACTIVE_PUBLISHED.json', 'PHASE_04_COMMITTED.json'])

    def test_02_recover_committed_is_read_only(self):
        self.publish()
        snap = {p: p.read_bytes() for p in self.layout.tx.iterdir()}
        self.assertEqual(W.recover(self.layout)['status'], 'COMMITTED_VERIFIED_NO_WRITE')
        self.assertEqual(snap, {p: p.read_bytes() for p in self.layout.tx.iterdir()})

    def test_03_second_publish_blocks_on_existing_transaction(self):
        self.publish()
        with self.assertRaisesRegex(W.Blocked, 'MENU_BEFORE_DRIFT|EXISTING_TRANSACTION'):
            self.publish()
        self.assert_after()

    def test_04_cli_child_process_publish(self):
        r = self.cli('qualification-publish')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('MENU_WRITER_STATUS=COMMITTED', r.stdout)
        self.assert_after(); self.consumer()


class CrashRecovery(WriterSandbox):
    def crash_then_recover(self, point):
        r = self.cli('qualification-publish', '--inject', point)
        self.assertEqual(r.returncode, 77, point + r.stdout + r.stderr)
        with self.assertRaises(ValueError):
            self.consumer()  # never COMMITTED during an interrupted transaction
        with self.assertRaisesRegex(W.Blocked, 'EXISTING_TRANSACTION|MENU_BEFORE_DRIFT'):
            self.publish()
        r = self.cli('qualification-recover')
        self.assertEqual(r.returncode, 0, point + r.stdout + r.stderr)
        self.assertIn('MENU_WRITER_STATUS=ROLLED_BACK', r.stdout)
        self.assert_before()
        with self.assertRaises(ValueError):
            self.consumer()
        r = self.cli('qualification-recover')
        self.assertIn('MENU_WRITER_STATUS=ROLLED_BACK_VERIFIED_NO_WRITE', r.stdout)
        r = self.cli('qualification-archive')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.layout.tx.exists())
        # The retry is a fresh transaction, not a resurrected one.
        self.assertEqual(self.publish()['status'], 'COMMITTED')
        self.assert_after(); self.consumer()

    def test_10_each_crash_point_recovers_by_new_process(self):
        for point in CRASH_POINTS:
            with self.subTest(point=point):
                self.setUp()
                self.crash_then_recover(point)

    def test_11_crash_after_committed_is_never_rolled_back(self):
        r = self.cli('qualification-publish', '--inject', 'AFTER_COMMITTED')
        self.assertEqual(r.returncode, 77)
        r = self.cli('qualification-recover')
        self.assertIn('COMMITTED_VERIFIED_NO_WRITE', r.stdout)
        self.assert_after(); self.consumer()

    def test_12_orphan_staging_blocks_then_archives(self):
        r = self.cli('qualification-publish', '--inject', 'AFTER_STAGING_WRITTEN')
        self.assertEqual(r.returncode, 77)
        self.assertFalse(self.layout.tx.exists())
        with self.assertRaisesRegex(W.Blocked, 'ORPHAN_STAGING'):
            self.publish()
        self.assertEqual(W.recover(self.layout)['status'], 'STAGING_ABORTED_ARCHIVED')
        self.assertEqual(self.publish()['status'], 'COMMITTED')

    def test_13_crash_during_recovery_is_recoverable(self):
        for point in ('RECOVERY_AFTER_ACTIVE_DISPLACED', 'RECOVERY_AFTER_MENU_RESTORED'):
            with self.subTest(point=point):
                self.setUp()
                self.assertEqual(self.cli('qualification-publish', '--inject', 'AFTER_ACTIVE_PUBLISHED').returncode, 77)
                self.assertEqual(self.cli('qualification-recover', '--inject', point).returncode, 77)
                r = self.cli('qualification-recover')
                self.assertIn('MENU_WRITER_STATUS=ROLLED_BACK', r.stdout, r.stdout + r.stderr)
                self.assert_before()

    def test_14_partial_replacefile_menu_only_under_backup_name(self):
        # Emulate ReplaceFileW ERROR_UNABLE_TO_MOVE_REPLACEMENT_2 (1177).
        self.assertEqual(self.cli('qualification-publish', '--inject', 'BEFORE_MENU_REPLACE').returncode, 77)
        paths = self.layout.token_paths(PKG)
        os.rename(self.layout.menu, paths['menu_backup'])
        out = W.recover(self.layout)
        self.assertEqual(out['status'], 'ROLLED_BACK')
        self.assertIn('MENU_REINSTATED_AFTER_PARTIAL_REPLACE', out['actions'])
        self.assert_before()
        self.assertEqual(paths['menu_backup'].read_bytes(), OLD)

    def test_15_one_trailing_phase_record_tolerated_two_block(self):
        self.assertEqual(self.cli('qualification-publish', '--inject', 'AFTER_PREPARED').returncode, 77)
        rec = W.canonical({'schema': W.PHASE_RECORD_SCHEMA, 'phase': 'MENU_PUBLISHED'})
        (self.layout.tx / 'PHASE_02_MENU_PUBLISHED.json').write_bytes(rec)
        self.assertEqual(W.load_transaction(self.layout.tx)[1], 'PREPARED')
        (self.layout.tx / 'PHASE_03_ACTIVE_PUBLISHED.json').write_bytes(rec)
        with self.assertRaisesRegex(W.Blocked, 'TX_PHASE_HISTORY_GAP'):
            W.recover(self.layout)


class Concurrency(WriterSandbox):
    def holder(self, *, die):
        code = ('import sys,os\nsys.path.insert(0,sys.argv[1])\nimport MENU_OFFICIAL_WRITER as W\n'
                'from pathlib import Path\n'
                'lock=W.ExclusiveLock(Path(sys.argv[2])).__enter__()\nprint("HELD",flush=True)\n'
                + ('os._exit(9)\n' if die else 'sys.stdin.readline()\n'))
        return subprocess.Popen([sys.executable, '-I', '-B', '-c', code, str(C), str(self.layout.lock)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def test_20_concurrent_writer_is_refused_without_effect(self):
        self.layout.tickstore_root.mkdir(parents=True, exist_ok=True)
        p = self.holder(die=False)
        try:
            self.assertEqual(p.stdout.readline().strip(), 'HELD')
            with self.assertRaisesRegex(W.Blocked, 'WRITER_LOCK_BUSY'):
                self.publish()
            with self.assertRaisesRegex(W.Blocked, 'WRITER_LOCK_BUSY'):
                W.recover(self.layout)
            self.assert_before()
            self.assertFalse(self.layout.tx.exists())
        finally:
            p.stdin.write('\n'); p.stdin.flush(); p.wait(30); p.stdin.close(); p.stdout.close()
        self.assertEqual(self.publish()['status'], 'COMMITTED')

    def test_21_lock_released_by_abrupt_owner_death(self):
        self.layout.tickstore_root.mkdir(parents=True, exist_ok=True)
        p = self.holder(die=True)
        self.assertEqual(p.stdout.readline().strip(), 'HELD'); p.wait(30); p.stdin.close(); p.stdout.close()
        self.assertEqual(p.returncode, 9)
        self.assertEqual(self.publish()['status'], 'COMMITTED')

    def test_22_two_simultaneous_writer_processes_one_winner(self):
        procs = [subprocess.Popen([sys.executable, '-I', '-B', WRITER, '--mode', 'qualification-publish',
                                   '--d-root', str(self.d), '--c-root', str(self.c),
                                   '--menu-before-sha256', W.sha(OLD), '--bat-sha256', W.sha(BAT),
                                   '--installed-root', str(self.inst), '--package-sha256', PKG,
                                   '--witness-sha256', WIT], stdout=subprocess.PIPE, text=True)
                 for _ in range(4)]
        outs = [p.communicate(timeout=120)[0] for p in procs]
        self.assertEqual(sum('MENU_WRITER_STATUS=COMMITTED' in o for o in outs), 1, outs)
        self.assertTrue(all(('COMMITTED' in o) or ('MENU_WRITER_BLOCKED=' in o) for o in outs))
        self.assert_after(); self.consumer()


class Negative(WriterSandbox):
    def nothing_written(self):
        self.assert_before()
        self.assertFalse(self.layout.tx.exists())
        for p in self.layout.token_paths(PKG).values():
            self.assertFalse(p.exists(), p)

    def test_30_menu_drift_blocks_before_write(self):
        self.layout.menu.write_bytes(OLD + b'#drift\n')
        with self.assertRaisesRegex(W.Blocked, 'MENU_BEFORE_DRIFT'):
            self.publish()
        self.assertFalse(self.layout.tx.exists())

    def test_31_bat_drift_blocks(self):
        self.layout.bat.write_bytes(BAT + b'rem\r\n')
        with self.assertRaisesRegex(W.Blocked, 'BAT_DRIFT'):
            self.publish()
        self.nothing_written()

    def test_32_preexisting_active_blocks(self):
        self.layout.tickstore_root.mkdir(parents=True, exist_ok=True)
        self.layout.active.write_bytes(b'{}\n')
        with self.assertRaisesRegex(W.Blocked, 'ACTIVE_PREEXISTING'):
            self.publish()
        self.assertFalse(self.layout.tx.exists())

    def test_33_hardlinked_menu_blocks(self):
        os.link(self.layout.menu, self.d / 'alias.py')
        with self.assertRaisesRegex(Exception, 'HARDLINK'):
            self.publish()
        self.assertFalse(self.layout.tx.exists())

    def test_34_redirected_ancestor_blocks(self):
        # Windows: NTFS junction (no privilege needed); POSIX: symlink.
        real = self.d / 'Base CSV/Scripts'
        os.rename(real, self.d / 'Scripts_real')
        if os.name == 'nt':
            r = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(real), str(self.d / 'Scripts_real')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        else:
            os.symlink(self.d / 'Scripts_real', real)
        with self.assertRaises(Exception):
            self.publish()
        self.assertFalse(self.layout.tx.exists())
        self.assertEqual((self.d / 'Scripts_real/Biblioteca/MENU.py').read_bytes(), OLD)

    def test_35_installed_candidate_drift_blocks(self):
        (self.inst / MENU_REL).write_bytes(NEW + b'#tamper\n')
        with self.assertRaisesRegex(W.Blocked, 'INSTALLED_INTENT'):
            self.publish()
        self.nothing_written()

    def test_36_artifact_name_collision_blocks(self):
        self.layout.token_paths(PKG)['menu_backup'].write_bytes(b'stale')
        with self.assertRaisesRegex(W.Blocked, 'ARTIFACT_NAME_COLLISION'):
            self.publish()
        self.assertFalse(self.layout.tx.exists())

    def test_37_hostile_swap_inside_replace_window_detected(self):
        hook = W.Injector(self.layout, 'BEFORE_MENU_REPLACE', 'SWAP', b'HOSTILE\n')
        with self.assertRaisesRegex(W.Blocked, 'MENU_CONCURRENT_SWAP_DETECTED'):
            self.publish(inject=hook)
        backup = self.layout.token_paths(PKG)['menu_backup']
        self.assertEqual(backup.read_bytes(), b'HOSTILE\n')
        with self.assertRaisesRegex(W.Blocked, 'RECOVERY_MENU_BACKUP_INVALID'):
            W.recover(self.layout)
        self.assertEqual(self.layout.menu.read_bytes(), NEW)  # nothing automatic over hostile state

    def test_38_forged_committed_journal_is_not_trusted(self):
        self.assertEqual(self.cli('qualification-publish', '--inject', 'AFTER_PREPARED').returncode, 77)
        plan_sha = W.sha((self.layout.tx / 'PLAN.json').read_bytes())
        (self.layout.tx / 'JOURNAL.json').write_bytes(W.canonical(
            {'schema': W.TX_SCHEMA, 'plan_sha256': plan_sha, 'phase': 'COMMITTED'}))
        (self.layout.tx / 'PHASE_02_COMMITTED.json').write_bytes(b'{}\n')
        with self.assertRaisesRegex(W.Blocked, 'COMMITTED_READBACK_FAILED'):
            W.recover(self.layout)
        with self.assertRaises(ValueError):
            self.consumer()

    def test_39_tampered_plan_breaks_binding(self):
        self.assertEqual(self.cli('qualification-publish', '--inject', 'AFTER_PREPARED').returncode, 77)
        plan = json.loads((self.layout.tx / 'PLAN.json').read_bytes())
        plan['menu_before_sha256'] = 'F' * 64
        (self.layout.tx / 'PLAN.json').write_bytes(W.canonical(plan))
        with self.assertRaisesRegex(W.Blocked, 'TX_JOURNAL_BINDING'):
            W.recover(self.layout)

    def test_40_sandbox_identity_required(self):
        bad = self.d.with_name('NOT_A_SANDBOX'); bad.mkdir()
        (bad / 'SANDBOX_ONLY.txt').write_bytes(W.SANDBOX_SENTINEL)
        with self.assertRaisesRegex(W.Blocked, 'QUALIFICATION_SANDBOX_NAME'):
            W.qualification_layout(bad, self.c, W.sha(OLD), W.sha(BAT))
        (self.c / 'SANDBOX_ONLY.txt').write_bytes(b'x')
        with self.assertRaisesRegex(W.Blocked, 'QUALIFICATION_SENTINEL'):
            W.qualification_layout(self.d, self.c, W.sha(OLD), W.sha(BAT))

    def test_41_official_modes_fail_closed_here(self):
        r = subprocess.run([sys.executable, '-I', '-B', WRITER, '--mode', 'official-publish',
                            '--installed-root', str(self.inst), '--package-sha256', PKG,
                            '--witness-sha256', WIT, '--inject', 'AFTER_PREPARED'],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn('INJECTION_FORBIDDEN_OFFICIAL', r.stdout)
        with self.assertRaisesRegex(W.Blocked, 'INJECTION_FORBIDDEN_OFFICIAL'):
            W.Injector(W.Layout('OFFICIAL', self.layout.menu, self.layout.bat, self.layout.tickstore_root,
                                W.sha(OLD), W.sha(BAT), False), 'AFTER_PREPARED')
        if os.name != 'nt':
            with self.assertRaisesRegex(W.Blocked, 'OFFICIAL_WRITER_WINDOWS_REQUIRED'):
                W.official_admission(self.inst, 'x', 'A' * 64, 'B' * 64)

    def test_42_official_layout_targets_are_fixed(self):
        src = (C / 'MENU_OFFICIAL_WRITER.py').read_text(encoding='utf-8')
        self.assertIn("from MENU_OFFICIAL_ADMISSION_READONLY import MENU, BAT, MENU_SHA, BAT_SHA", src)
        self.assertIn("until='B07'", src)
        self.assertNotIn('--menu-path', src)
        self.assertNotIn('unlink(', src.replace('os.unlink(src)', ''))

    def test_43_real_target_overlap_is_component_wise(self):
        app = 'C:\\Users\\x\\AppData\\Local'
        for bad in (r'D:\Base CSV\CDT15_R41_WRITER_QUAL_D_1', r'D:\Base CSV', 'D:\\',
                    app + '\\TICKSTORE\\CDT15_R41_WRITER_QUAL_C_1', app):
            with self.subTest(bad=bad):
                self.assertTrue(W.touches_real_target(bad, app))
        for ok in (app + '\\TICKSTORE_QUAL_R41\\CDT15_R41_WRITER_QUAL_C_1',
                   r'D:\TICKSTORE_QUALIFICATION_SANDBOX\R41\CDT15_R41_WRITER_QUAL_D_1',
                   r'D:\Base CSV2\CDT15_R41_WRITER_QUAL_D_1'):
            with self.subTest(ok=ok):
                self.assertFalse(W.touches_real_target(ok, app))


if __name__ == '__main__':
    unittest.main(verbosity=2)
