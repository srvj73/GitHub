"""Bounded genuine runtime module exercises. Never a production/complete G5 attestation."""
import argparse, hashlib, json, pathlib, os, stat, sys, unittest, tempfile

def h(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest().upper()

def no_link_chain(path, stop):
 # CDT18: every component from the run root down to the owned directory is a
 # plain directory; a symlink, junction or reparse point anywhere blocks.
 for q in (path,*path.parents):
  s=os.lstat(q)
  assert not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&0x400, 'OWNED_PROOF_ROOT_REPARSE'
  if q==stop:return
 raise AssertionError('OWNED_PROOF_ROOT')

def owned_topology(run_root, work, output):
 """WORK and EVIDENCE are separate siblings, both inside the bound run root."""
 run=pathlib.Path(run_root).resolve(strict=True);root=pathlib.Path(work).resolve(strict=True)
 outdir=pathlib.Path(output).parent.resolve(strict=True)
 assert run.is_dir() and root.is_dir() and outdir.is_dir(), 'OWNED_PROOF_ROOT'
 assert root!=run and outdir!=run and root.is_relative_to(run) and outdir.is_relative_to(run), 'OWNED_PROOF_ROOT'
 assert not root.is_relative_to(outdir) and not outdir.is_relative_to(root), 'OWNED_PROOF_ROOT_OVERLAP'
 assert not os.path.lexists(output), 'OWNED_PROOF_OUTPUT_EXISTS'
 for q in (pathlib.Path(os.path.abspath(work)),pathlib.Path(os.path.abspath(output)).parent):
  no_link_chain(q,pathlib.Path(os.path.abspath(run_root)))
 return run,root

def main():
 p=argparse.ArgumentParser(allow_abbrev=False)
 p.add_argument('--tests',required=True);p.add_argument('--run-owned',required=True)
 p.add_argument('--output',required=True);p.add_argument('--suites',required=True)
 p.add_argument('--run-root',required=True)
 a=p.parse_args();t=pathlib.Path(a.tests).resolve()
 run,root=owned_topology(a.run_root,a.run_owned,a.output)
 assert t.is_dir(), 'OWNED_PROOF_ROOT'
 suits=json.loads(a.suites);report={};logs=[];result=0
 for name in suits:
  q=t/name;assert q.is_file() and q.suffix=='.py'
  s=unittest.defaultTestLoader.discover(str(t),pattern=name,top_level_dir=str(t))
  log=root/(name+'.tests.log')
  with log.open('x',encoding='utf8') as stream:
   r=unittest.TextTestRunner(stream=stream,verbosity=2).run(s)
  report[name]={'run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skips':len(r.skipped),
                'source_sha256':h(q)}
  logs.append({'path':str(log),'sha256':h(log),'bytes':log.stat().st_size})
  if not r.wasSuccessful() or r.skipped:result=1
 with open(a.output,'x',encoding='utf8') as f:
  f.write(json.dumps({'schema':'TICKSTORE_PRE_G06_REAL_CODE_NATIVE_BOUNDED_V001',
   'suites':report,'physical_artifacts':logs,'production_execution':False},sort_keys=True,indent=2)+'\n')
 return result
if __name__=='__main__':raise SystemExit(main())
