"""Sandbox contract tests of RUN_CDT20_R08Q1.py (campaign bootstrap). NOT native evidence."""
from pathlib import Path
import importlib.util,unittest,tempfile,zipfile,copy,json,os
from unittest import mock
import sys
STAGE=Path(sys.argv.pop(1)).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('cdt20_bootstrap',STAGE/'RUN_CDT20_R08Q1.py')
M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
class Transport(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def test_exact_package_and_frozen_core(self):
  w=M.read(STAGE/'CDT20_R08Q1_WITNESS.json');cm=M.verify_package(STAGE/w['package_name'],w)
  self.assertTrue(any(r['path']=='g5proof/PRE_G06_NATIVE_SCENARIOS.py' for r in cm['files']))
  self.assertTrue(any(r['path']=='g5proof/PRE_G06_COMPLETENESS.py' for r in cm['files']))
 def test_review_bound_to_exact_package(self):
  w=M.read(STAGE/'CDT20_R08Q1_WITNESS.json');r=M.read(STAGE/'CDT20_SOURCE_REVIEW.json')
  self.assertEqual((r['package_sha256'],r['code_manifest_sha256']),(w['package_sha256'],w['code_manifest_sha256']))
  self.assertEqual(r['known_fixable_blockers'],[]);self.assertIs(r['independent_b06_audit'],False)
 def test_wrong_package_hash(self):
  w=M.read(STAGE/'CDT20_R08Q1_WITNESS.json');w['package_sha256']='F'*64
  with self.assertRaisesRegex(RuntimeError,'PACKAGE_HASH'):M.verify_package(STAGE/w['package_name'],w)
 def test_wrong_runtime_manifest(self):
  w=M.read(STAGE/'CDT20_R08Q1_WITNESS.json');w['code_manifest_sha256']='F'*64
  with self.assertRaisesRegex(RuntimeError,'MANIFEST_BINDING'):M.verify_package(STAGE/w['package_name'],w)
 def test_traversal_duplicate_drive_and_backslash_blocked(self):
  for names in [['../outside'],['a','A'],['C:/foreign'],['a\\b'],['/absolute'],['folder/']]:
   with self.subTest(names=names):
    with self.assertRaises(RuntimeError):M.safe_names([zipfile.ZipInfo(n) for n in names])
 def test_zip_symlink_rejected(self):
  i=zipfile.ZipInfo('link');i.external_attr=0xA000<<16
  with self.assertRaisesRegex(RuntimeError,'ZIP_PATH'):M.safe_names([i])
 def test_no_clobber_publishing(self):
  p=self.root/'record.json';M.publish(p,{'original':True});before=p.read_bytes()
  with self.assertRaises(FileExistsError):M.publish(p,{'forged':True})
  self.assertEqual(before,p.read_bytes())
 def test_symlink_ancestor_rejected(self):
  target=self.root/'target';target.mkdir();link=self.root/'alias'
  try:link.symlink_to(target,target_is_directory=True)
  except (OSError,NotImplementedError):self.skipTest('Host symlink privilege unavailable')
  with self.assertRaisesRegex(RuntimeError,'REPARSE'):M.no_alias(link)
 def test_owner_requires_both_volumes_and_exact_package(self):
  root=self.root/'C'/'R08_Q1_20261020000000_abcdef123456';d=self.root/'D'/root.name
  root.mkdir(parents=True);d.mkdir(parents=True)
  owner={'schema':'CDT19_ENGINEERING_RUN_OWNER_V001','package_sha256':'A'*64,'run_id':root.name,'production_authorized':False}
  for p in (root,d):M.publish(p/'OWNER.json',owner)
  self.assertEqual(M.verify_resume_owner(root,d,'A'*64),owner)
  with self.assertRaisesRegex(RuntimeError,'RESUME_OWNER'):M.verify_resume_owner(root,d,'B'*64)
  (d/'OWNER.json').write_text(json.dumps(dict(owner,production_authorized=True)))
  with self.assertRaisesRegex(RuntimeError,'RESUME_OWNER'):M.verify_resume_owner(root,d,'A'*64)
 def test_cross_volume_env_and_profile_restored(self):
  root=self.root/'run';d=self.root/'d';root.mkdir();d.mkdir();(root/'TEMP').mkdir()
  env={'LOCALAPPDATA':str(self.root),'USERPROFILE':str(self.root)}
  import tempfile
  before=tempfile.tempdir
  self.addCleanup(setattr,tempfile,'tempdir',before)
  with mock.patch.dict(os.environ,env),mock.patch.object(M,'long_path',side_effect=Path):
   result=M.configure_environment(root,d)
   self.assertEqual(os.environ['TEMP'],str(root/'TEMP'))
   self.assertEqual(os.environ['TICKSTORE_QUAL_C_PARENT'],str(root/'QUAL_C'))
   self.assertEqual(os.environ['TICKSTORE_QUAL_D_PARENT'],str(d/'WRITER_EFFECTFUL'))
   self.assertEqual(result['userprofile'],str(self.root))
 def test_live_prior_process_blocks_without_killing(self):
  M.publish(self.root/'BOOTSTRAP_OWNER_prior.json',{'process':{'pid':123,'creation_filetime':456}})
  recovery=mock.Mock();recovery.read=lambda p:(M.read(p),p.read_bytes())
  recovery.dead.side_effect=RuntimeError('OWNER_OR_CHILD_LIVE')
  with self.assertRaisesRegex(RuntimeError,'OWNER_OR_CHILD_LIVE'):M.reconcile_processes(self.root,recovery)
  self.assertFalse(list(self.root.glob('PROCESS_READBACK_*.json')))
 def test_linux_cannot_start_native_campaign(self):
  if os.name=='nt':self.skipTest('POSIX negative only')
  with self.assertRaisesRegex(RuntimeError,'WINDOWS_REQUIRED'):M.run(mock.Mock())
if __name__=='__main__':unittest.main(verbosity=2)
