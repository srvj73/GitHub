"""Directed new-delta tests only. Not native Windows or effectful production tests."""
import hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'candidate/control'))
from MENU_INSTALL_INTENT_VERIFY import (verify_inert_intent, Blocked, MENU_REL, LAUNCHER_REL)

def sha(b):return hashlib.sha256(b).hexdigest().upper()
PACKAGE='A'*64
WITNESS='B'*64
MENU=b'TICKSTORE_COMMITTED_MENU\n'
LAUNCHER=b'RUN_TICKSTORE_FULL.ps1\n'
class InstallerIntentTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(prefix='CDT15_G4_INTENT_SOURCE_ONLY_')
        self.addCleanup(self.td.cleanup)
        self.root=Path(self.td.name)/'Candidates'/PACKAGE
        self.root.mkdir(parents=True)
        self.write(MENU_REL,MENU)
        self.write(LAUNCHER_REL,LAUNCHER)
        manifest={'schema':'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001','files':[
            {'path':MENU_REL,'bytes':len(MENU),'sha256':sha(MENU)},
            {'path':LAUNCHER_REL,'bytes':len(LAUNCHER),'sha256':sha(LAUNCHER)}]}
        mraw=(json.dumps(manifest,sort_keys=True)+'\n').encode()
        self.write('PACKAGE_MANIFEST.json',mraw)
        deployment={'schema':'TICKSTORE_DEPLOYMENT_V001','installation_root':str(self.root),
            'package_sha256':PACKAGE,'package_manifest_sha256':sha(mraw),
            'witness_sha256':WITNESS,'launcher_sha256':sha(LAUNCHER),
            'status':'INSTALLED_NOT_PRODUCTION_ADMISSION','production_started':False}
        draw=(json.dumps(deployment,sort_keys=True)+'\n').encode()
        self.write('DEPLOYMENT.json',draw)
        intent={'schema':'TICKSTORE_MENU_INSTALL_INTENT_V001','installation_root':str(self.root),
            'package_sha256':PACKAGE,'package_manifest_sha256':sha(mraw),
            'witness_sha256':WITNESS,'candidate_menu_relative_path':MENU_REL,
            'candidate_menu_sha256':sha(MENU),'active_deployment_sha256':sha(draw),
            'launcher_sha256':sha(LAUNCHER),'transaction_state':'NOT_STARTED',
            'effectful_authorized':False,'production_started':False}
        self.intent=intent
        self.write('MENU_INSTALL_INTENT.json',json.dumps(intent,sort_keys=True).encode()+b'\n')
    def write(self,rel,raw):
        p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def check(self):return verify_inert_intent(self.root,trusted_package_sha256=PACKAGE,trusted_witness_sha256=WITNESS)
    def change_intent(self, **kwargs):
        a=dict(self.intent);a.update(kwargs);self.write('MENU_INSTALL_INTENT.json',(json.dumps(a,sort_keys=True)+'\n').encode())
    def test_good_source_only(self):
        out=self.check();self.assertEqual(out['status'],'PASS_SOURCE_ONLY_NO_EFFECT_AUTHORITY');self.assertFalse(out['activation_authorized'])
    def test_manifest_hash_tamper(self):
        (self.root/'PACKAGE_MANIFEST.json').write_bytes(b'{}');self.assertRaises(Blocked,self.check)
    def test_menu_tamper(self):
        self.write(MENU_REL,MENU+b'altered');self.assertRaisesRegex(Blocked,'INSTALLED_MEMBER_DRIFT',self.check)
    def test_launcher_tamper(self):
        self.write(LAUNCHER_REL,LAUNCHER+b'altered');self.assertRaises(Blocked,self.check)
    def test_deployment_tamper(self):
        p=self.root/'DEPLOYMENT.json';p.write_bytes(p.read_bytes()+b' ');self.assertRaisesRegex(Blocked,'DEPLOYMENT_DIGEST',self.check)
    def test_trusted_package_mismatch(self):
        with self.assertRaisesRegex(Blocked,'INSTALLATION_ROOT_BINDING|INTENT_EXTERNAL_BINDING'):
            verify_inert_intent(self.root,trusted_package_sha256='F'*64,trusted_witness_sha256=WITNESS)
    def test_trusted_witness_mismatch(self):
        with self.assertRaisesRegex(Blocked,'INTENT_EXTERNAL_BINDING'):
            verify_inert_intent(self.root,trusted_package_sha256=PACKAGE,trusted_witness_sha256='E'*64)
    def test_invalid_hash_pin(self):
        with self.assertRaisesRegex(Blocked,'EXTERNAL_PACKAGE_PIN_REQUIRED'):
            verify_inert_intent(self.root,trusted_package_sha256='',trusted_witness_sha256=WITNESS)
    def test_effectful_request_is_rejected(self):
        self.change_intent(effectful_authorized=True);self.assertRaisesRegex(Blocked,'INTENT_PREMATURE_EFFECT',self.check)
    def test_committed_request_is_rejected(self):
        self.change_intent(transaction_state='COMMITTED');self.assertRaises(Blocked,self.check)
    def test_prod_flag_rejected(self):
        self.change_intent(production_started=True);self.assertRaises(Blocked,self.check)
    def test_extra_field_rejected(self):
        self.change_intent(unknown=True);self.assertRaisesRegex(Blocked,'INTENT_SCHEMA',self.check)
    def test_duplicate_json_key_rejected(self):
        p=self.root/'MENU_INSTALL_INTENT.json'
        raw=p.read_bytes().rstrip()
        self.assertTrue(raw.endswith(b'}'))
        p.write_bytes(raw[:-1]+b',"production_started":false}\n')
        self.assertRaisesRegex(Blocked,'INPUT_DUPLICATE_KEY',self.check)

    def test_hardlink_intent_rejected(self):
        alias=self.root/'ALIAS';original=self.root/'MENU_INSTALL_INTENT.json'
        alias.hardlink_to(original);self.assertRaisesRegex(Blocked,'HARDLINK_INPUT',self.check)
    def test_symlink_manifest_rejected(self):
        original=self.root/'PACKAGE_MANIFEST.json';backup=self.root/'MANIFEST_SOURCE';original.rename(backup)
        try: original.symlink_to(backup)
        except (OSError,NotImplementedError): self.skipTest('symlink unavailable')
        self.assertRaisesRegex(Blocked,'REPARSE_PATH',self.check)
    def test_duplicate_manifest_member_rejected(self):
        p=self.root/'PACKAGE_MANIFEST.json';j=json.loads(p.read_bytes());j['files'].append(j['files'][0]);raw=(json.dumps(j,sort_keys=True)+'\n').encode();p.write_bytes(raw)
        self.change_intent(package_manifest_sha256=sha(raw))
        self.assertRaisesRegex(Blocked,'MANIFEST_DUPLICATE',self.check)
    def test_installer_source_pins_and_block(self):
        src=(ROOT/'candidate/control/INSTALL_TICKSTORE_FULL.ps1').read_text(encoding='utf-8')
        # R41: activation dispatches only to the installed official writer under a B07 chain.
        self.assertEqual(src.count("'MENU_ACTIVATION_REQUIRES_RELEASE_CHAIN_THROUGH_B07'"),1)
        self.assertLess(src.index('MENU_ACTIVATION_REQUIRES_RELEASE_CHAIN_THROUGH_B07'),src.index('WriteNew (Join-Path $target'))
        self.assertIn("'MENU_INSTALL_INTENT.json'",src)
        self.assertIn("'INSTALL_INTENT_MENU_MISMATCH'",src)
        self.assertIn("'INSTALL_INTENT_READBACK'",src)
        self.assertIn('effectful_authorized=$false',src)
        self.assertIn('production_started=$false',src)
        self.assertIn("$menuMatches.Count -eq 1",src)
        self.assertLess(src.index('INSTALL_INTENT_MENU_MANIFEST_CARDINALITY'),src.index('[IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($InstallRoot))'))
    def test_no_prod_writer_api_in_verifier(self):
        src=(ROOT/'candidate/control/MENU_INSTALL_INTENT_VERIFY.py').read_text()
        for text in ('ReplaceFileW','MoveFileExW','os.replace(','.unlink(','.write_bytes('):
            self.assertNotIn(text,src)

if __name__=='__main__':unittest.main()
