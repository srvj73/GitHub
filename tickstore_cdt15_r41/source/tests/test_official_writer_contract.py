import importlib.util, pathlib, sys, unittest, copy
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'candidate'/'control'))
from MENU_OFFICIAL_ADMISSION_READONLY import MENU, BAT, MENU_SHA, BAT_SHA, CANDIDATE_MENU_SHA, SOURCE_POLICY_SHA, SCHEMA as OBS_SCHEMA
from MENU_OFFICIAL_WRITER_CONTRACT_SOURCE_ONLY import prepare_source_only, recovery_decision, Blocked, SCHEMA
APP=r'C:\Users\silvi\AppData\Local'
ACTIVE=APP+r'\TICKSTORE'

def obs():
    return {'menu':dict(path=MENU,status='PRESENT',sha256=MENU_SHA,reparse=False,final_path_match=True,nlink=1),
        'bat':dict(path=BAT,status='PRESENT',sha256=BAT_SHA,reparse=False,final_path_match=True,nlink=1),
        'active_root':dict(path=ACTIVE,status='ABSENT'),
        'active':dict(path=ACTIVE+r'\ACTIVE_DEPLOYMENT.json',status='ABSENT'),
        'transaction':dict(path=ACTIVE+r'\MENU_TRANSACTION',status='ABSENT')}

def receipt():
    return {'verdict': {'schema':OBS_SCHEMA,'status':'PASS_READONLY_IDENTITY_ONLY','menu_before_sha256':MENU_SHA,
        'bat_sha256':BAT_SHA,'candidate_menu_sha256':CANDIDATE_MENU_SHA,'policy_master_sha256_source':SOURCE_POLICY_SHA,
        'active_target_status':'ABSENT','effects_authorized':False,'production_modified':False,'full_started':False},
        'observation':obs()}

def intent():
    return {'schema':'TICKSTORE_INERT_INTENT_VERIFICATION_V001','status':'PASS_SOURCE_ONLY_NO_EFFECT_AUTHORITY',
      'package_sha256':'A'*64,'intent_sha256':'B'*64,'candidate_menu_sha256':CANDIDATE_MENU_SHA,
      'active_deployment_sha256':'C'*64,'activation_authorized':False,'production_started':False}

def run(r=None,i=None,p=SOURCE_POLICY_SHA,a=APP):
    return prepare_source_only(windows_receipt=r if r is not None else receipt(),
        installed_intent_verification=i if i is not None else intent(),local_appdata=a,policy_master_sha256=p)

class TestOfficialWriterContract(unittest.TestCase):
    def blocked(self, reason, *, r=None,i=None,p=SOURCE_POLICY_SHA,a=APP):
        with self.assertRaisesRegex(Blocked,reason):run(r,i,p,a)
    def test_01_baseline_no_effect(self):
        x=run();self.assertEqual(x['schema'],SCHEMA);self.assertIs(x['effectful_authorized'],False)
    def test_02_layout_cross_volume(self):
        x=run()['paths']; self.assertEqual(x['menu_backup_same_volume'][:2],'D:');self.assertEqual(x['active_pending_same_volume'][:2],'C:')
    def test_03_plan_field_identity(self):
        p=run()['plan'];self.assertEqual(set(p),{'schema','menu_before_sha256','menu_after_sha256','active_before_sha256','active_after_sha256'})
    def test_04_verified_menu_pin(self):self.assertEqual(run()['plan']['menu_after_sha256'],CANDIDATE_MENU_SHA)
    def test_05_policy_drift(self):self.blocked('ACTIVE_POLICY',p='F'*64)
    def test_06_bad_policy_hash(self):self.blocked('ACTIVE_POLICY',p='INVALID')
    def test_07_unexpanded_appdata(self):self.blocked('LOCALAPPDATA',a=r'%USERPROFILE%\AppData\Local')
    def test_08_same_volume_layout(self):self.blocked('CROSS_VOLUME',a=r'D:\User\AppData\Local')
    def test_09_wrong_observation_schema(self):
        r=receipt();r['verdict']['schema']='BAD';self.blocked('WINDOWS_RECEIPT',r=r)
    def test_10_effectful_false_required(self):
        r=receipt();r['verdict']['effects_authorized']=True;self.blocked('WINDOWS_RECEIPT',r=r)
    def test_11_menu_drift(self):
        r=receipt();r['observation']['menu']['sha256']='F'*64;self.blocked('BASELINE_DRIFT',r=r)
    def test_12_ambiguity_active(self):
        r=receipt();r['observation']['active']['status']='PRESENT';self.blocked('TARGET_',r=r)
    def test_13_ambiguity_transaction(self):
        r=receipt();r['observation']['transaction']['status']='PRESENT';self.blocked('TARGET_',r=r)
    def test_14_symlink(self):
        r=receipt();r['observation']['menu']['reparse']=True;self.blocked('TARGET_REDIRECTION',r=r)
    def test_15_hardlink(self):
        r=receipt();r['observation']['menu']['nlink']=2;self.blocked('TARGET_FILE_IDENTITY',r=r)
    def test_16_receipt_observation_mismatch(self):
        r=receipt();r['verdict']['menu_before_sha256']='F'*64;self.blocked('WINDOWS_RECEIPT_BINDING',r=r)
    def test_17_wrong_intent_menu(self):
        i=intent();i['candidate_menu_sha256']='D'*64;self.blocked('MENU_CANDIDATE',i=i)
    def test_18_intent_authorized(self):
        i=intent();i['activation_authorized']=True;self.blocked('INSTALLED_INTENT',i=i)
    def test_19_intent_not_started(self):
        i=intent();i['status']='COMMITTED';self.blocked('INSTALLED_INTENT',i=i)
    def test_20_bad_package_sha(self):
        i=intent();i['package_sha256']='ZZ';self.blocked('INSTALLED_INTENT_HASH',i=i)
    def test_21_unknown_record(self):
        r=receipt();r['outside']={};self.blocked('WINDOWS_RECEIPT_FIELDS',r=r)
    def test_22_prepared_rollback_classification(self):
        p=run()['plan'];self.assertEqual(recovery_decision('PREPARED',menu_digest=p['menu_before_sha256'],active_digest=None,plan=p),'BLOCK_NEW_ATTEMPTS_REQUIRE_LOCKED_RECOVERY')
    def test_23_menu_written_before_journal_classification(self):
        p=run()['plan'];self.assertEqual(recovery_decision('PREPARED',menu_digest=p['menu_after_sha256'],active_digest=None,plan=p),'BLOCK_NEW_ATTEMPTS_REQUIRE_LOCKED_RECOVERY')
    def test_24_two_written_not_commit(self):
        p=run()['plan'];self.assertEqual(recovery_decision('ACTIVE_PUBLISHED',menu_digest=p['menu_after_sha256'],active_digest=p['active_after_sha256'],plan=p),'BLOCK_NEW_ATTEMPTS_REQUIRE_LOCKED_RECOVERY')
    def test_25_committed_readback(self):
        p=run()['plan'];self.assertEqual(recovery_decision('COMMITTED',menu_digest=p['menu_after_sha256'],active_digest=p['active_after_sha256'],plan=p),'RECONCILE_COMMITTED_WITH_FULL_EVIDENCE_ONLY')
    def test_26_committed_old_blocks(self):
        p=run()['plan']
        with self.assertRaisesRegex(Blocked,'COMMITTED_READBACK'):recovery_decision('COMMITTED',menu_digest=p['menu_before_sha256'],active_digest=p['active_after_sha256'],plan=p)
    def test_27_rolled_back_old(self):
        p=run()['plan'];self.assertEqual(recovery_decision('ROLLED_BACK',menu_digest=p['menu_before_sha256'],active_digest=None,plan=p),'RECONCILE_ROLLED_BACK_WITH_FULL_EVIDENCE_ONLY')
    def test_28_rolled_back_new_blocks(self):
        p=run()['plan']
        with self.assertRaisesRegex(Blocked,'ROLLBACK_READBACK'):recovery_decision('ROLLED_BACK',menu_digest=p['menu_after_sha256'],active_digest=None,plan=p)
    def test_29_unexpected_drift(self):
        p=run()['plan']
        with self.assertRaisesRegex(Blocked,'MENU_TARGET_DRIFT'):recovery_decision('MENU_PUBLISHED',menu_digest='F'*64,active_digest=None,plan=p)
    def test_30_phase_invalid(self):
        p=run()['plan']
        with self.assertRaisesRegex(Blocked,'UNKNOWN_PHASE'):recovery_decision('MYSTERY',menu_digest=p['menu_before_sha256'],active_digest=None,plan=p)
    def test_31_package_digest_determines_backup_name(self):
        x=run();self.assertTrue(x['paths']['menu_backup_same_volume'].endswith('AAAAAAAAAAAAAAAA.backup'))
    def test_32_dont_have_writer_cli(self):
        m=ROOT/'candidate/control/MENU_OFFICIAL_WRITER_CONTRACT_SOURCE_ONLY.py'
        s=m.read_text();self.assertNotIn('ReplaceFileW',s);self.assertNotIn('subprocess.run(',s)


class TestOfficialWriterPlanAdversarial(unittest.TestCase):
    def rejected(self, p, reason='PLAN_'):
        with self.assertRaisesRegex(Blocked, reason):
            recovery_decision('COMMITTED', menu_digest=p['menu_after_sha256'],
                              active_digest=p['active_after_sha256'], plan=p)

    def test_33_reject_missing_menu_hash(self):
        p=run()['plan'].copy();p['menu_before_sha256']='INVALID';self.rejected(p)

    def test_34_reject_missing_active_hash(self):
        p=run()['plan'].copy();p['active_after_sha256']=None;self.rejected(p)

    def test_35_reject_malformed_previous_active(self):
        p=run()['plan'].copy();p['active_before_sha256']='BAD';self.rejected(p)

    def test_36_reject_same_menu_before_and_after(self):
        p=run()['plan'].copy();p['menu_before_sha256']=p['menu_after_sha256'];self.rejected(p,'PLAN_NOT_TRANSITION')

    def test_37_reject_same_active_before_and_after(self):
        p=run()['plan'].copy();p['active_before_sha256']=p['active_after_sha256'];self.rejected(p,'PLAN_NOT_TRANSITION')

    def test_38_reject_fake_committed_with_none(self):
        p=run()['plan'].copy();p['menu_before_sha256']='BAD';p['menu_after_sha256']='BAD';p['active_after_sha256']=None
        self.rejected(p)

    def test_39_reject_non_string_hash(self):
        p=run()['plan'].copy();p['menu_after_sha256']=123;self.rejected(p)

    def test_40_real_committed_still_classifies(self):
        p=run()['plan'];out=recovery_decision('COMMITTED',menu_digest=p['menu_after_sha256'],
                        active_digest=p['active_after_sha256'],plan=p)
        self.assertEqual(out,'RECONCILE_COMMITTED_WITH_FULL_EVIDENCE_ONLY')

if __name__=='__main__':unittest.main(verbosity=2)
