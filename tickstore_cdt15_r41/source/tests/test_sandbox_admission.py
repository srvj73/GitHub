"""R44-DROOT-01: sandbox root admission (portable part; native junction/swap probes run in R44D)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'qual'))
import SANDBOX_ADMISSION as A  # noqa: E402


class Admission(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.t = Path(os.path.realpath(t.name))

    def test_plain_directory_admitted_and_revalidated(self):
        d = self.t / 'PLAIN'; d.mkdir()
        rec = A.admit_root(d, require_ntfs=False)
        self.assertEqual(rec['path'], str(d)); A.revalidate(rec)

    def test_symlink_root_and_ancestor_rejected(self):
        target = self.t / 'T'; target.mkdir(); link = self.t / 'L'; os.symlink(target, link)
        with self.assertRaisesRegex(A.AdmissionBlocked, 'REPARSE_COMPONENT'):
            A.admit_root(link, require_ntfs=False)
        (target / 'C').mkdir()
        with self.assertRaisesRegex(A.AdmissionBlocked, 'REPARSE_COMPONENT'):
            A.admit_root(link / 'C', require_ntfs=False)

    def test_file_missing_relative_rejected(self):
        f = self.t / 'F'; f.write_bytes(b'x')
        for p, needle in ((f, 'NOT_DIRECTORY'), (self.t / 'M', 'ROOT_MISSING'), ('rel/path', 'NOT_ABSOLUTE')):
            with self.assertRaisesRegex(A.AdmissionBlocked, needle):
                A.admit_root(p, require_ntfs=False)

    def test_swap_detected_on_revalidate(self):
        d = self.t / 'S'; d.mkdir(); rec = A.admit_root(d, require_ntfs=False)
        os.rename(d, self.t / 'S0'); target = self.t / 'T2'; target.mkdir(); os.symlink(target, d)
        with self.assertRaisesRegex(A.AdmissionBlocked, 'REPARSE_COMPONENT'):
            A.revalidate(rec)
        os.unlink(d); d.mkdir()
        with self.assertRaisesRegex(A.AdmissionBlocked, 'IDENTITY_CHANGED'):
            A.revalidate(rec)

    def test_tree_census_reports_internal_links(self):
        root = self.t / 'R'; (root / 'a').mkdir(parents=True); os.symlink(root / 'a', root / 'lnk')
        census = A.audit_tree(root)
        self.assertEqual([os.path.basename(x['path']) for x in census['reparse_points']], ['lnk'])


class HeldAdmission(unittest.TestCase):
    """R44D-ORIGIN-01: nothing is created before admission; run dir exclusive; identity bound."""
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.t = Path(os.path.realpath(t.name))

    def test_absent_root_refused_and_not_created(self):
        with self.assertRaisesRegex(A.AdmissionBlocked, 'ROOT_MISSING'):
            A.HeldChain(self.t / 'ABSENT', require_ntfs=False)
        self.assertFalse(os.path.lexists(self.t / 'ABSENT'))

    def test_redirected_ancestor_refused_without_write(self):
        real = self.t / 'REAL'; (real / 'DROOT').mkdir(parents=True); os.symlink(real, self.t / 'J')
        before = sorted(os.listdir(real / 'DROOT'))
        with self.assertRaisesRegex(A.AdmissionBlocked, 'REPARSE_COMPONENT'):
            A.HeldChain(self.t / 'J' / 'DROOT', require_ntfs=False)
        self.assertEqual(sorted(os.listdir(real / 'DROOT')), before)

    def test_run_dir_exclusive_refuses_preexisting_plain_and_link(self):
        root = self.t / 'DROOT'; root.mkdir(); other = self.t / 'OTHER'; other.mkdir()
        (root / 'RUN_PRE').mkdir(); os.symlink(other, root / 'RUN_LINK')
        with A.HeldChain(root, require_ntfs=False) as chain:
            for name in ('RUN_PRE', 'RUN_LINK'):
                with self.assertRaisesRegex(A.AdmissionBlocked, 'RUN_DIR_PREEXISTS'):
                    A.create_run_dir_exclusive(chain, name)
            with self.assertRaisesRegex(A.AdmissionBlocked, 'RUN_DIR_NAME'):
                A.create_run_dir_exclusive(chain, '../escape')
            held = A.create_run_dir_exclusive(chain, 'RUN_OK')
            self.assertEqual(held.verify(), held.identity); held.close()
        self.assertEqual(os.listdir(other), [])

    def test_identity_drift_of_held_root_detected(self):
        root = self.t / 'DROOT'; root.mkdir()
        chain = A.HeldChain(root, require_ntfs=False)
        try:
            os.rename(root, self.t / 'MOVED'); root.mkdir()  # POSIX cannot deny; must be detected
            with self.assertRaisesRegex(A.AdmissionBlocked, 'HOLD_PATH_NO_LONGER_REACHES_HELD_OBJECT'):
                chain.verify()
        finally:
            chain.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
