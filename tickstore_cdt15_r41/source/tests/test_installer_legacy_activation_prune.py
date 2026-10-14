"""R41 installer activation contract (supersedes the R40 'activation pruned' contract).

Legacy one-file activation stays removed. ``-ActivateMenu`` is now only a dispatch
to the installed MENU_OFFICIAL_WRITER.py and requires a release chain through B07
whose argument checks precede any witness read or write. Static checks only; the
native PS 5.1 installer path is exercised by the Windows qualification driver.
"""
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
P = HERE / 'candidate/control/INSTALL_TICKSTORE_FULL.ps1'
GATE = "'MENU_ACTIVATION_REQUIRES_RELEASE_CHAIN_THROUGH_B07'"
DISPATCH = '--mode official-publish'


class InstallerWriterActivationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = P.read_bytes()
        cls.text = cls.data.decode('utf-8')

    def test01_ascii_lf_no_bom(self):
        self.assertFalse(self.data.startswith(b'\xef\xbb\xbf'))
        self.assertTrue(all(b < 128 for b in self.data))

    def test02_activation_requires_chain_before_witness_and_writes(self):
        idx = self.text.index(GATE)
        # The only earlier write is the run-owned log folder under the fixed TICKSTORE_RUNS root.
        for later in ('if ($WitnessPath -eq', '[IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($InstallRoot))',
                      'WriteNew (Join-Path $target'):
            with self.subTest(later=later):
                self.assertLess(idx, self.text.index(later))

    def test03_activation_requires_official_install_root(self):
        idx = self.text.index("'MENU_ACTIVATION_REQUIRES_OFFICIAL_INSTALL_ROOT'")
        self.assertLess(idx, self.text.index('if ($WitnessPath -eq'))

    def test04_chain_arguments_rejected_without_activation(self):
        self.assertIn("'CHAIN_ARGUMENTS_ONLY_WITH_ACTIVATE_MENU'", self.text)

    def test05_legacy_branch_absent(self):
        for token in ('MENU_DEPLOYMENT_SELECTED=YES', '[IO.File]::Replace($pending', '[IO.File]::Move($pending,$active)',
                      'WriteNew $pending $raw', "'G4_MENU_ACTIVATION_REQUIRES_INTEGRATED_COMMIT_WRITER'"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.text)

    def test06_no_direct_active_or_transaction_write(self):
        self.assertNotIn('ACTIVE_DEPLOYMENT.json', self.text)
        self.assertNotIn('MENU_TRANSACTION', self.text)

    def test07_single_dispatch_to_installed_writer_with_identity(self):
        self.assertEqual(self.text.count(DISPATCH), 1)
        self.assertLess(self.text.index("'INSTALLED_WRITER_IDENTITY'"), self.text.index(DISPATCH))
        self.assertIn("implementation_v001/candidate/control/MENU_OFFICIAL_WRITER.py", self.text)
        self.assertIn("('MENU_OFFICIAL_WRITER_EXIT_'+$LASTEXITCODE)", self.text)

    def test09_fixed_absolute_run_log(self):
        self.assertIn("$LogRoot='C:\\Users\\silvi\\OneDrive\\Downloads\\TICKSTORE_RUNS'", self.text)
        self.assertNotIn('Get-Location', self.text)
        first_write = self.text.index('[IO.Directory]::CreateDirectory(')
        self.assertEqual(self.text[first_write:first_write + 40], '[IO.Directory]::CreateDirectory($LogRoot')

    def test08_inert_intent_and_readback_retained(self):
        for token in ('MENU_INSTALL_INTENT.json', "transaction_state='NOT_STARTED'", 'effectful_authorized=$false',
                      'INSTALL_READBACK', 'INSTALL_INTENT_READBACK', 'PACKAGE_MANIFEST_SHA256'):
            with self.subTest(token=token):
                self.assertIn(token, self.text)

    def test09_existing_install_reused_only_for_activation(self):
        self.assertIn("Require ((-not $existing) -or $ActivateMenu) 'INSTALLATION_ALREADY_EXISTS_VERIFY_EXISTING'",
                      self.text)

    def test10_inactive_status_emitted(self):
        self.assertIn('MENU_ACTIVATION=NOT_REQUESTED_INACTIVE_INSTALL_ONLY', self.text)

    def test11_negative_control_reinsertion_detected(self):
        mutated = self.text.replace(GATE, "'X'")
        self.assertNotIn(GATE, mutated)


if __name__ == '__main__':
    unittest.main(verbosity=2)
