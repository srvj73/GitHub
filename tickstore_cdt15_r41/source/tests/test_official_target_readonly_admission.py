"""Pure negative controls only: native handle semantics require Windows target."""
import importlib.util, pathlib, unittest, os, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
SRC=ROOT/'candidate/control/MENU_OFFICIAL_ADMISSION_READONLY.py'
spec=importlib.util.spec_from_file_location('cdt15_admission_source',SRC)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
APP=r'C:\Users\silvi\AppData\Local'
ROOT_ACTIVE=APP+r'\TICKSTORE'
def present(path,sha=None,dir=False):
    d=dict(path=path,status='PRESENT',reparse=False,final_path_match=True,nlink=1)
    if not dir:d['sha256']=sha or 'B'*64
    return d

def absent(path):return dict(path=path,status='ABSENT')

def observation():
    return dict(menu=present(a.MENU,a.MENU_SHA),bat=present(a.BAT,a.BAT_SHA),
       active_root=absent(ROOT_ACTIVE),active=absent(ROOT_ACTIVE+r'\ACTIVE_DEPLOYMENT.json'),
       transaction=absent(ROOT_ACTIVE+r'\MENU_TRANSACTION'))

class TestAdmission(unittest.TestCase):
    def check_block(self,o,reason):
        with self.assertRaisesRegex(a.Blocked,reason):a.validate_observation(o,local_appdata=APP)
    def test_baseline_readonly(self):
        r=a.validate_observation(observation(),local_appdata=APP)
        self.assertEqual(r['status'],'PASS_READONLY_IDENTITY_ONLY')
        self.assertIs(r['effects_authorized'],False)
        self.assertIs(r['production_modified'],False)
    def test_menu_drift(self):
        o=observation();o['menu']['sha256']='0'*64;self.check_block(o,'BASELINE_DRIFT_MENU')
    def test_bat_drift(self):
        o=observation();o['bat']['sha256']='0'*64;self.check_block(o,'BASELINE_DRIFT_BAT')
    def test_menu_missing(self):
        o=observation();o['menu']=absent(a.MENU);self.check_block(o,'HISTORICAL_TARGET_MISSING_MENU')
    def test_bat_reparse(self):
        o=observation();o['bat']['reparse']=True;self.check_block(o,'TARGET_REDIRECTION_BAT')
    def test_menu_final_alias(self):
        o=observation();o['menu']['final_path_match']=False;self.check_block(o,'TARGET_REDIRECTION_MENU')
    def test_menu_hardlink(self):
        o=observation();o['menu']['nlink']=2;self.check_block(o,'TARGET_FILE_IDENTITY_MENU')
    def test_active_exists(self):
        o=observation();o['active']=present(ROOT_ACTIVE+r'\ACTIVE_DEPLOYMENT.json');self.check_block(o,'EXISTING_BOUNDARY_REQUIRES_RECONCILIATION_ACTIVE')
    def test_transaction_exists(self):
        o=observation();o['transaction']=present(ROOT_ACTIVE+r'\MENU_TRANSACTION',dir=True);self.check_block(o,'EXISTING_BOUNDARY_REQUIRES_RECONCILIATION_TRANSACTION')
    def test_unknown_active_root_link(self):
        o=observation();o['active_root']=present(ROOT_ACTIVE,dir=True);o['active_root']['reparse']=True;self.check_block(o,'TARGET_REDIRECTION_ACTIVE_ROOT')
    def test_extra_fields(self):
        o=observation();o['extra']='X';self.check_block(o,'OBSERVATION_FIELDS')
    def test_wrong_target_path(self):
        o=observation();o['menu']['path']=r'E:\Alien\MENU.py';self.check_block(o,'PATH_IDENTITY_MENU')
    def test_localappdata_unexpanded(self):
        with self.assertRaisesRegex(a.Blocked,'LOCALAPPDATA_NOT_ABSOLUTE'):
            a.validate_observation(observation(),local_appdata=r'%USERPROFILE%\AppData\Local')
    def test_hash_invalid(self):
        o=observation();o['menu']['sha256']='fake';self.check_block(o,'TARGET_FILE_IDENTITY_MENU')
    def test_windows_only_effectless(self):
        if os.name!='nt':
            with self.assertRaisesRegex(a.Blocked,'WINDOWS_ONLY'):a.run_readonly()
        self.assertNotIn('activate',SRC.read_text().lower())
    def test_target_immutable_constants(self):
        self.assertEqual(a.MENU,r'D:\Base CSV\Scripts\Biblioteca\MENU.py')
        self.assertEqual(a.BAT,r'D:\Base CSV\Manutenção Base de Dados.bat')
if __name__=='__main__':unittest.main(verbosity=2)
