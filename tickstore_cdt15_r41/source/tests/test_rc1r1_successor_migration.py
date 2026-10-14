"""RC1R1 successor migration tool: dry run by default, gated apply, no deletion, crash resume.

Disposable temporary resume roots only; never the production D4 resume root.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
CAND = HERE.parent / 'candidate'
sys.path.insert(0, str(CAND / 'control'))
import RC1R1_SUCCESSOR_MIGRATION as M  # noqa: E402

FIX = HERE / 'fixtures' / 'RC1R1_HISTORICAL'


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def build_successor_zip(path):
    """Documented deterministic recipe (build/build_rc1r1_successor.py): stored, fixed metadata, sorted."""
    root = CAND / 'recovery'
    members = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED; info.create_system = 0; info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    return path


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.t = Path(self.temp.name)
        self.zip = build_successor_zip(self.t / M.SUCCESSOR_ZIP_NAME)
        self.rr = self.t / 'TICKSTORE_D4_RESUMABLE_V002R22'
        pkg = self.rr / 'SUCCESSOR_PACKAGE'
        (pkg / 'engine').mkdir(parents=True); (pkg / 'modules').mkdir()
        (pkg / M.RELEASE_REL).write_bytes((FIX / 'tickstore_publisher_recovery_v004_release.BFC44DA9.py.txt').read_bytes())
        (pkg / '99_MANIFEST_SHA256.json').write_bytes((CAND / 'recovery/history/V002R22/99_MANIFEST_SHA256.json').read_bytes())
        (pkg / 'modules/postfull_verifier.py').write_bytes((FIX / 'postfull_verifier.B5E753C3.py.txt').read_bytes())
        (pkg / 'docs').mkdir(); (pkg / 'docs/README_EXECUCAO.md').write_bytes(b'historical documentary file\n')
        (self.rr / 'checkpoint').mkdir(); (self.rr / 'checkpoint/CHECKPOINT.json').write_bytes(b'{"untouched":true}\n')
        (self.rr / 'authority').mkdir()
        self.before = snapshot(self.rr)

    def inspect(self):
        return M.inspect(self.rr, self.zip)


class PinsAndPackaging(Base):
    def test_pins_equal_wrapper_and_bootstrap(self):
        wrapper = (CAND / 'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1').read_text(encoding='utf-8')
        boot = (CAND / 'control/D4_FIRST_ADMISSION_BOOTSTRAP.py').read_text(encoding='utf-8')
        self.assertIn("$ExpectedPackageZipSha = '%s'" % M.SUCCESSOR_ZIP_SHA256, wrapper)
        self.assertIn("'%s'" % M.SUCCESSOR_ZIP_NAME, wrapper)
        self.assertIn("'%s'" % M.REVIEW_PACK_NAME, wrapper)
        self.assertIn("reads.read(a.package_zip,'%s')" % M.SUCCESSOR_ZIP_SHA256, boot)
        manifest = sha((CAND / 'recovery/99_MANIFEST_SHA256.json').read_bytes())
        self.assertIn("$ExpectedPackageManifestSha = '%s'" % manifest, wrapper)
        release = sha((CAND / 'recovery' / M.RELEASE_REL).read_bytes())
        self.assertIn("$ExpectedReleaseSha = '%s'" % release, wrapper)
        self.assertEqual(sha((CAND / 'recovery/history/V002R22/99_MANIFEST_SHA256.json').read_bytes()),
                         M.PARENT_PACKAGE_MANIFEST_SHA256)

    def test_successor_zip_reproduced_from_the_final_recovery_tree(self):
        self.assertEqual(sha(self.zip.read_bytes()), M.SUCCESSOR_ZIP_SHA256)


class DryRun(Base):
    def test_dry_run_plans_and_writes_nothing(self):
        report, members, _ = self.inspect()
        self.assertEqual((report['installed_state'], report['status']), ('V002R22', 'READY'))
        self.assertEqual(report['plan'], ['RENAME_V002R22_TO_BACKUP', 'EXTRACT_TO_STAGING_AND_VERIFY',
                                          'PROMOTE_STAGING_BY_RENAME', 'COPY_SUCCESSOR_ZIP_TO_ARTIFACTS',
                                          'WRITE_MIGRATION_RECEIPT'])
        self.assertEqual(report['successor_release_sha256'], sha((CAND / 'recovery' / M.RELEASE_REL).read_bytes()))
        self.assertEqual(snapshot(self.rr), self.before)

    def test_main_dry_run_default(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = M.main(['--resume-root', str(self.rr), '--successor-zip', str(self.zip)])
        self.assertEqual(rc, 0); self.assertIn('RC1R1_MIGRATION_DRY_RUN=READY', out.getvalue())
        self.assertIn('RESULT_RETURN_TO=ChatGPT', out.getvalue())
        self.assertEqual(snapshot(self.rr), self.before)


class Blockers(Base):
    def assert_blocked(self, reason):
        report, _, _ = self.inspect()
        self.assertEqual(report['status'], 'BLOCKED'); self.assertIn(reason, report['blockers'])
        before = snapshot(self.rr)
        with self.assertRaisesRegex(M.Blocked, 'MIGRATION_BLOCKED'):
            M.apply(report, {}, b'')
        self.assertEqual(snapshot(self.rr), before)

    def test_admitted_run_authority_blocks(self):
        (self.rr / 'authority/RUN_AUTHORITY.json').write_bytes(b'{}')
        self.assert_blocked('ADMITTED_RUN_AUTHORITY_PRESENT_REQUIRES_ORIGIN_DECISION')

    def test_pending_authority_blocks(self):
        (self.rr / 'authority/RUN_AUTHORITY.json.tmp.1').write_bytes(b'{}')
        self.assert_blocked('AUTHORITY_PENDING_FILES_REQUIRE_DIAGNOSIS')

    def test_unknown_installed_package_blocks(self):
        p = self.rr / 'SUCCESSOR_PACKAGE' / M.RELEASE_REL; p.write_bytes(p.read_bytes() + b'#tamper\n')
        self.assert_blocked('SUCCESSOR_PACKAGE_UNKNOWN_CONTENT')

    def test_absent_without_backup_blocks(self):
        os.rename(self.rr / 'SUCCESSOR_PACKAGE', self.t / 'elsewhere')
        self.assert_blocked('SUCCESSOR_PACKAGE_ABSENT_WITHOUT_V002R22_BACKUP')

    def test_foreign_artifact_zip_blocks(self):
        (self.rr / 'artifacts').mkdir(); (self.rr / 'artifacts' / M.SUCCESSOR_ZIP_NAME).write_bytes(b'other')
        self.assert_blocked('ARTIFACT_ZIP_PRESENT_WITH_OTHER_BYTES')

    def test_wrong_or_open_successor_zip_refused(self):
        bad = self.t / 'bad.zip'; bad.write_bytes(self.zip.read_bytes() + b'x')
        with self.assertRaisesRegex(M.Blocked, 'SUCCESSOR_ZIP_SHA256'):
            M.inspect(self.rr, bad)
        extra = self.t / 'extra.zip'
        with zipfile.ZipFile(self.zip) as z, zipfile.ZipFile(extra, 'w') as w:
            for n in z.namelist():
                w.writestr(n, z.read(n))
            w.writestr('engine/planted.py', b'print(1)\n')
        with mock.patch.object(M, 'SUCCESSOR_ZIP_SHA256', sha(extra.read_bytes())), \
             self.assertRaisesRegex(M.Blocked, 'SUCCESSOR_ZIP_CLOSED_SET'):
            M.inspect(self.rr, extra)
        trav = self.t / 'trav.zip'
        with zipfile.ZipFile(trav, 'w') as w:
            w.writestr('../escape.py', b'')
            w.writestr('99_MANIFEST_SHA256.json', b'{"files":[]}')
        with mock.patch.object(M, 'SUCCESSOR_ZIP_SHA256', sha(trav.read_bytes())), \
             self.assertRaisesRegex(M.Blocked, 'SUCCESSOR_MEMBER_PATH'):
            M.inspect(self.rr, trav)

    def test_successor_must_equal_this_final_recovery_tree(self):
        with tempfile.TemporaryDirectory() as other:
            o = Path(other)
            for rel, raw in snapshot(CAND / 'recovery').items():
                (o / rel).parent.mkdir(parents=True, exist_ok=True); (o / rel).write_bytes(raw)
            p = o / 'modules/orchestrator.py'; p.write_bytes(p.read_bytes() + b'#drift\n')
            with self.assertRaisesRegex(M.Blocked, 'SUCCESSOR_FINAL_BYTES:modules/orchestrator.py'):
                M.inspect(self.rr, self.zip, recovery_root=o)


class Apply(Base):
    def test_apply_backs_up_never_deletes_and_promotes_verified_successor(self):
        old_pkg = snapshot(self.rr / 'SUCCESSOR_PACKAGE')
        report, members, zraw = self.inspect()
        receipt = M.apply(report, members, zraw, run_id='R1')
        self.assertEqual(receipt['status'], 'APPLIED')
        self.assertEqual(snapshot(self.rr / 'SUCCESSOR_PACKAGE'), members)
        self.assertEqual(snapshot(self.rr / (M.BACKUP_PREFIX + 'R1')), old_pkg)
        self.assertEqual(sha((self.rr / 'artifacts' / M.SUCCESSOR_ZIP_NAME).read_bytes()), M.SUCCESSOR_ZIP_SHA256)
        rec_raw = Path(receipt['receipt_path']).read_bytes()
        self.assertEqual(sha(rec_raw), receipt['receipt_sha256'])
        rec = json.loads(rec_raw)
        self.assertEqual((rec['schema'], rec['run_id']), (M.RECEIPT_SCHEMA, 'R1'))
        self.assertFalse(rec['touches_state_checkpoint_authority_dest_or_scratch'])
        self.assertEqual((self.rr / 'checkpoint/CHECKPOINT.json').read_bytes(), b'{"untouched":true}\n')
        self.assertEqual(list((self.rr / 'authority').iterdir()), [])
        again, members, zraw = self.inspect()
        self.assertEqual((again['installed_state'], again['plan']), ('V002R23', ['NO_OP_ALREADY_MIGRATED', 'WRITE_MIGRATION_RECEIPT']))
        second = M.apply(again, members, zraw, run_id='R2')
        self.assertEqual(second['effects'], [])
        self.assertEqual(snapshot(self.rr / (M.BACKUP_PREFIX + 'R1')), old_pkg)

    def test_crash_after_backup_rename_resumes_without_deleting(self):
        report, members, zraw = self.inspect()
        real = os.rename
        calls = []

        def crash_on_promote(src, dst):
            calls.append((src, dst))
            if Path(src).name.startswith(M.STAGING_PREFIX):
                raise KeyboardInterrupt('simulated crash before promotion')
            return real(src, dst)
        with mock.patch.object(M.os, 'rename', crash_on_promote), self.assertRaises(KeyboardInterrupt):
            M.apply(report, members, zraw, run_id='C1')
        self.assertFalse((self.rr / 'SUCCESSOR_PACKAGE').exists())
        self.assertTrue((self.rr / (M.BACKUP_PREFIX + 'C1')).is_dir())
        self.assertTrue((self.rr / (M.STAGING_PREFIX + 'C1')).is_dir())
        resumed, members, zraw = self.inspect()
        self.assertEqual((resumed['installed_state'], resumed['status']), ('ABSENT', 'READY'))
        self.assertEqual(resumed['existing_staging_left_untouched'], [M.STAGING_PREFIX + 'C1'])
        M.apply(resumed, members, zraw, run_id='C2')
        self.assertEqual(snapshot(self.rr / 'SUCCESSOR_PACKAGE'), members)
        self.assertTrue((self.rr / (M.STAGING_PREFIX + 'C1')).is_dir())
        self.assertTrue((self.rr / (M.BACKUP_PREFIX + 'C1')).is_dir())

    def test_main_apply_requires_native_and_release_chain_until_b07(self):
        base = ['--resume-root', str(self.rr), '--successor-zip', str(self.zip), '--apply']
        for native, extra, reason in ((False, [], 'NATIVE_WINDOWS_REQUIRED'),
                                      (True, [], 'APPLY_REQUIRES_RELEASE_CHAIN_UNTIL_B07')):
            out = io.StringIO()
            with mock.patch.object(M, 'native_windows', return_value=native), contextlib.redirect_stdout(out):
                self.assertEqual(M.main(base + extra), 2)
            self.assertIn('REASON=' + reason, out.getvalue())
        import FULL_RELEASE_CHAIN
        seen = {}

        def refused(*args, **kwargs):
            seen.update(kwargs, args=args)
            raise FULL_RELEASE_CHAIN.Blocked('B07_NOT_PASS')
        out = io.StringIO()
        with mock.patch.object(M, 'native_windows', return_value=True), mock.patch.object(FULL_RELEASE_CHAIN, 'ReleaseChain', refused), \
             contextlib.redirect_stdout(out):
            self.assertEqual(M.main(base + ['--chain-file', 'c.json', '--chain-sha256', 'A' * 64, '--b06-sha256', 'B' * 64]), 2)
        self.assertIn('REASON=B07_NOT_PASS', out.getvalue())
        self.assertEqual(seen['until'], 'B07'); self.assertEqual(seen['args'][3], M.CANDIDATE)
        self.assertEqual(snapshot(self.rr), self.before)

    def test_main_apply_inside_release_chain_pins(self):
        events = []

        class Chain:
            receipt_sha = 'C' * 64
            def __init__(self, *args, **kwargs): events.append(('open', kwargs['until']))
            def __enter__(self): return self
            def __exit__(self, *exc): events.append(('close',)); return False
            def revalidate(self): events.append(('revalidate',))
        import FULL_RELEASE_CHAIN
        out = io.StringIO()
        with mock.patch.object(M, 'native_windows', return_value=True), mock.patch.object(FULL_RELEASE_CHAIN, 'ReleaseChain', Chain), \
             contextlib.redirect_stdout(out):
            rc = M.main(['--resume-root', str(self.rr), '--successor-zip', str(self.zip), '--apply',
                         '--chain-file', 'c.json', '--chain-sha256', 'A' * 64, '--b06-sha256', 'B' * 64])
        self.assertEqual(rc, 0); self.assertIn('RC1R1_MIGRATION=APPLIED', out.getvalue())
        self.assertEqual(events, [('open', 'B07'), ('revalidate',), ('close',)])
        receipts = list((self.rr / 'migration').glob('*/MIGRATION_RECEIPT.json'))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_bytes())['chain_receipt_sha256'], 'C' * 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
