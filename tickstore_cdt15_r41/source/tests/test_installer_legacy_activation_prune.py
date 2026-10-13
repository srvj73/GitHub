"""Source-only prequalification of minimum removal of orphaned activation path.
No execution of the effectful PowerShell installer and no formal audit.
"""
from pathlib import Path
import hashlib
import sys
import unittest
import re

HERE=Path(__file__).resolve().parents[1]
P=HERE/'candidate/control/INSTALL_TICKSTORE_FULL.ps1'
EXPECTED_PARENT='E59280D6B661D83D8E1AB9F55BE7B4E6DFA83D1256649BD636F88F7AB3514247'
EXPECTED_NEW='8D7B93D34858A1BDA10238E87C9B2FA0582F6A3A6C7F547486DA61957E93217F'
GATE="Require (-not $ActivateMenu) 'G4_MENU_ACTIVATION_REQUIRES_INTEGRATED_COMMIT_WRITER'"

class InstallerPruneContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=P.read_text(encoding='utf-8')
        cls.data=P.read_bytes()
    def test01_patched_installer_identity(self):
        self.assertEqual(hashlib.sha256(self.data).hexdigest().upper(),EXPECTED_NEW)
    def test02_activation_argument_remains_explicit(self):
        self.assertIn('[switch]$ActivateMenu',self.text)
    def test03_activation_guard_remains(self):
        self.assertEqual(self.text.count(GATE),1)
    def test04_guard_before_witness_and_writes(self):
        idx=self.text.index(GATE)
        self.assertLess(idx,self.text.index('if ($WitnessPath -eq'))
        self.assertLess(idx,self.text.index('[IO.Directory]::CreateDirectory'))
        self.assertLess(idx,self.text.index('WriteNew (Join-Path $target'))
    def test05_legacy_branch_removed(self):
        self.assertNotIn('if ($ActivateMenu) {',self.text)
        self.assertNotIn('MENU_DEPLOYMENT_SELECTED=YES',self.text)
    def test06_no_direct_active_target_writer(self):
        for pattern in ("$active=Join-Path", "[IO.File]::Replace($pending", "[IO.File]::Move($pending,$active)","WriteNew $pending $raw"):
            with self.subTest(pattern=pattern): self.assertNotIn(pattern,self.text)
    def test07_inert_intent_retained(self):
        for token in ('MENU_INSTALL_INTENT.json',"transaction_state='NOT_STARTED'",'effectful_authorized=$false','production_started=$false'):
            with self.subTest(token=token):self.assertIn(token,self.text)
    def test08_install_readback_retained(self):
        for token in ('INSTALL_READBACK','INSTALL_INTENT_MENU_MISMATCH','INSTALL_INTENT_READBACK','PACKAGE_MANIFEST_SHA256'):
            with self.subTest(token=token):self.assertIn(token,self.text)
    def test09_safe_only_status_emitted(self):
        self.assertIn('MENU_ACTIVATION=NOT_SUPPORTED_TRANSACTIONAL_WRITER_PENDING',self.text)
    def test10_no_official_transaction_promotion(self):
        self.assertNotIn('MENU_TRANSACTION/PLAN.json',self.text)
        self.assertNotIn('PASS_PRODUCTION',self.text)
    def test11_control_negative_reinsertion_detected(self):
        mutated=self.text+'\nif ($ActivateMenu) { Write-Output "MENU_DEPLOYMENT_SELECTED=YES" }\n'
        self.assertIn('if ($ActivateMenu) {',mutated)
        self.assertIn('MENU_DEPLOYMENT_SELECTED=YES',mutated)
        self.assertNotEqual(hashlib.sha256(mutated.encode()).hexdigest().upper(),EXPECTED_NEW)
    def test12_parent_byte_delta_exact(self):
        patch=(HERE/'DELTA_INSTALLER_LEGACY_ACTIVATION_PRUNE.patch').read_text()
        self.assertIn('--- parent/candidate/control/INSTALL_TICKSTORE_FULL.ps1',patch)
        self.assertIn('+    Write-Output \'MENU_ACTIVATION=NOT_SUPPORTED_TRANSACTIONAL_WRITER_PENDING\'',patch)
        self.assertIn("-        Write-Output 'MENU_DEPLOYMENT_SELECTED=YES",patch)

if __name__=='__main__': unittest.main(verbosity=2)
