"""New delta tests only: verified installer intent -> sandbox producer -> exact MENU guard."""
import ast, hashlib, json, re, stat, sys, tempfile, unittest, os
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'candidate/control'))
from MENU_INSTALL_INTENT_VERIFY import MENU_REL,LAUNCHER_REL
from MENU_INTENT_TO_TX_SANDBOX import stage_verified_inert_intent, begin_sandbox_only
from TX_SANDBOX_MODEL import SENTINEL, SandboxedTransaction, Blocked, SimulatedCrash, sha

SRC=(R/'candidate/menu/MENU.py').read_text('utf-8')
FUNCS=[x for x in ast.parse(SRC).body if isinstance(x,ast.FunctionDef) and x.name in ('_reject_deployment_reparse','_tickstore_committed_deployment')]
assert len(FUNCS)==2
ns={'Path':Path,'json':json,'hashlib':hashlib,'stat':stat,'re':re}
exec(compile(ast.fix_missing_locations(ast.Module(body=FUNCS,type_ignores=[])),str(R/'candidate/menu/MENU.py'),'exec'),ns)
read_committed=ns['_tickstore_committed_deployment']
PKG='A'*64; WIT='B'*64; OLD=b'OLD_OFFICIAL_MENU\n';NEW=(R/'candidate/menu/MENU.py').read_bytes(); LAUNCH=b'LAUNCHER\n'

def raw_json(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()

class IntentProducerConsumerNewDelta(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='CDT15_G4_INSTALL_INTENT_BRIDGE_')
        self.addCleanup(self.tmp.cleanup)
        t=Path(self.tmp.name)
        self.inst=t/'Candidates'/PKG;self.inst.mkdir(parents=True)
        self.menu=self.inst/MENU_REL;self.menu.parent.mkdir(parents=True)
        self.menu.write_bytes(NEW)
        self.launch=self.inst/LAUNCHER_REL;self.launch.parent.mkdir(parents=True)
        self.launch.write_bytes(LAUNCH)
        self.manifest={'schema':'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001','files':[
            {'path':MENU_REL,'bytes':len(NEW),'sha256':sha(NEW)},
            {'path':LAUNCHER_REL,'bytes':len(LAUNCH),'sha256':sha(LAUNCH)}]}
        self.write('PACKAGE_MANIFEST.json',raw_json(self.manifest))
        self.deploy={'schema':'TICKSTORE_DEPLOYMENT_V001','installation_root':str(self.inst),
            'package_sha256':PKG,'package_manifest_sha256':sha(raw_json(self.manifest)),
            'witness_sha256':WIT,'launcher_sha256':sha(LAUNCH),
            'status':'INSTALLED_NOT_PRODUCTION_ADMISSION','production_started':False}
        self.write('DEPLOYMENT.json',raw_json(self.deploy))
        self.intent={'schema':'TICKSTORE_MENU_INSTALL_INTENT_V001','installation_root':str(self.inst),
            'package_sha256':PKG,'package_manifest_sha256':sha(raw_json(self.manifest)),
            'witness_sha256':WIT,'candidate_menu_relative_path':MENU_REL,
            'candidate_menu_sha256':sha(NEW),'active_deployment_sha256':sha(raw_json(self.deploy)),
            'launcher_sha256':sha(LAUNCH),'transaction_state':'NOT_STARTED',
            'effectful_authorized':False,'production_started':False}
        self.write('MENU_INSTALL_INTENT.json',raw_json(self.intent))
        self.sandbox=t/'CDT15_G4_TXN_SANDBOX_INTENT';self.sandbox.mkdir()
        (self.sandbox/'SANDBOX_ONLY.txt').write_bytes(SENTINEL)
        for child in ['menu','active','candidate']:(self.sandbox/child).mkdir()
        self.menu_target=self.sandbox/'menu/MENU.py';self.menu_target.write_bytes(OLD)
        self.active_target=self.sandbox/'active/ACTIVE_DEPLOYMENT.json'
    def write(self,p,data): (self.inst/p).write_bytes(data)
    def stage(self,old_active=None,old_menu=None,pk=PKG,wit=WIT):
        return stage_verified_inert_intent(installed_root=self.inst,sandbox_root=self.sandbox,
            trusted_package_sha256=pk,trusted_witness_sha256=wit,
            expected_old_menu_sha256=old_menu or sha(OLD),expected_old_active_sha256=old_active)
    def begin(self,st,inject=''):return begin_sandbox_only(sandbox_root=self.sandbox,staged=st,inject=inject)
    def test01_end_to_end_new_deployment_committed(self):
        st=self.stage();self.assertFalse(st['activation_authorized'])
        self.assertEqual(self.begin(st),'PASS_SANDBOX_ONLY')
        self.assertEqual(read_committed(self.active_target,self.menu_target),self.deploy)
    def test02_end_to_end_existing_active(self):
        old=b'PREVIOUS\n';self.active_target.write_bytes(old)
        st=self.stage(old_active=sha(old));self.begin(st)
        self.assertEqual(read_committed(self.active_target,self.menu_target),self.deploy)
        self.assertEqual((self.sandbox/'active/MENU_TRANSACTION/ACTIVE.old').read_bytes(),old)
    def test03_prepared_not_admitted_and_recovered(self):
        st=self.stage()
        with self.assertRaises(SimulatedCrash):self.begin(st,'AFTER_PREPARED')
        with self.assertRaisesRegex(ValueError,'TX_NOT_COMMITTED'):read_committed(self.active_target,self.menu_target)
        self.assertEqual(SandboxedTransaction(self.sandbox).reconcile(),'PASS_RECOVERED_SANDBOX_ONLY')
    def test04_menu_written_not_admitted_and_recovered(self):
        st=self.stage()
        with self.assertRaises(SimulatedCrash):self.begin(st,'AFTER_MENU_WRITE_BEFORE_JOURNAL')
        with self.assertRaisesRegex(ValueError,'TX_NOT_COMMITTED'):read_committed(self.active_target,self.menu_target)
        self.assertEqual(SandboxedTransaction(self.sandbox).reconcile(),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertEqual(self.menu_target.read_bytes(),OLD)
    def test05_active_written_not_admitted_and_recovered(self):
        st=self.stage()
        with self.assertRaises(SimulatedCrash):self.begin(st,'AFTER_ACTIVE_WRITE_BEFORE_JOURNAL')
        with self.assertRaisesRegex(ValueError,'TX_NOT_COMMITTED'):read_committed(self.active_target,self.menu_target)
        self.assertEqual(SandboxedTransaction(self.sandbox).reconcile(),'PASS_RECOVERED_SANDBOX_ONLY')
        self.assertFalse(self.active_target.exists())
    def test06_committed_menu_tamper_not_admitted(self):
        st=self.stage();self.begin(st);self.menu_target.write_bytes(b'INVALID\n')
        with self.assertRaisesRegex(ValueError,'TX_MENU_DRIFT'):read_committed(self.active_target,self.menu_target)
    def test07_committed_deployment_tamper_not_admitted(self):
        st=self.stage();self.begin(st);self.active_target.write_bytes(b'INVALID\n')
        with self.assertRaisesRegex(ValueError,'TX_ACTIVE_DRIFT'):read_committed(self.active_target,self.menu_target)
    def test08_invalid_inert_effect_flag_blocks_before_staging(self):
        self.intent['effectful_authorized']=True;self.write('MENU_INSTALL_INTENT.json',raw_json(self.intent))
        with self.assertRaises(Exception):self.stage()
        self.assertFalse((self.sandbox/'candidate/MENU.py').exists())
    def test09_wrong_trusted_witness_blocks(self):
        with self.assertRaises(Exception):self.stage(wit='C'*64)
        self.assertFalse((self.sandbox/'candidate/MENU.py').exists())
    def test10_wrong_old_official_menu_pin_blocks(self):
        with self.assertRaises(Exception):self.stage(old_menu='F'*64)
        self.assertFalse((self.sandbox/'candidate/MENU.py').exists())
    def test11_old_active_unexpected_blocks(self):
        self.active_target.write_bytes(b'EXISTING\n')
        with self.assertRaises(Exception):self.stage()
        self.assertFalse((self.sandbox/'candidate/MENU.py').exists())
    def test12_installed_menu_drift_blocks(self):
        self.menu.write_bytes(NEW+b'TAMPER')
        with self.assertRaises(Exception):self.stage()
        self.assertFalse((self.sandbox/'candidate/MENU.py').exists())
    def test13_duplicate_stage_fails_closed(self):
        self.stage()
        with self.assertRaisesRegex(Blocked,'SANDBOX_CANDIDATE_ALREADY_STAGED'):self.stage()
    def test14_wrong_sandbox_name_fails(self):
        x=self.sandbox.with_name('CDT15_G4_TXN_SANDBOX_CHANGED');self.sandbox.rename(x);self.sandbox=x
        with self.assertRaisesRegex(Blocked,'INTENT_SANDBOX_EXACT_NAME_REQUIRED'):self.stage()
    def test15_malformed_staged_authority_fails_before_commit(self):
        st=self.stage();st['activation_authorized']=True
        with self.assertRaisesRegex(Blocked,'STAGED_PLAN_NOT_INERT'):self.begin(st)
    def test16_source_only_no_official_publisher(self):
        src=(R/'candidate/control/MENU_INTENT_TO_TX_SANDBOX.py').read_text()
        self.assertNotIn('ReplaceFileW',src);self.assertNotIn('MoveFileExW',src)
        self.assertNotIn('RUN_TICKSTORE_FULL',src)
        self.assertFalse((self.inst/'MENU_TRANSACTION').exists())

if __name__=='__main__':unittest.main()
