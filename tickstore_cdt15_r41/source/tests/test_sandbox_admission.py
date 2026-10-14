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


if __name__ == '__main__':
    unittest.main(verbosity=2)
