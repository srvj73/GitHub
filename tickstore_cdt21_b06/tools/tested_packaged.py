import json,sys,os,hashlib
H,C,out=sys.argv[1],sys.argv[2],sys.argv[3]
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest().upper()
idx={}
for d,_,fs in os.walk(C):
    for f in fs:
        p=os.path.join(d,f); idx.setdefault(sha(p),[]).append(os.path.relpath(p,C))
R=[]
cd=f"{H}/NATIVE_EVIDENCE/COMMITS"
for f in sorted(os.listdir(cd)):
    j=json.load(open(f"{cd}/{f}",encoding='utf-8')); r=j['result']
    t=r.get('test_source_sha256')
    unit=r['unit']; name=unit.split('_',1)[1] if '_' in unit else unit
    R.append({'commit':f,'unit':unit,'test_source_sha256':t,'in_package':idx.get(t.upper(),[]) if t else None,
              'skipped':r.get('skipped'),'status':r.get('status'),'exit':r.get('exit_code'),
              'code_sha_ok':j['code_sha256']=='3C97A2D732F4430E8C5BAB30138ED422D1070B73F43AD1DFAD5D5CB2BBDF25B5',
              'pkg_sha_ok':j['package_sha256']=='4942871541629C3B38F47EDA55EA2C9E310361533887CB55E577D9641542E7C5'})
json.dump(R,open(out,'w'),indent=2)
for x in R: print(x['unit'][:50].ljust(50), 'PKG' if x['in_package'] else ('n/a' if x['in_package'] is None else 'NOT_IN_PKG'), (x['in_package'] or [''])[0][:70], x['skipped'], x['code_sha_ok'], x['pkg_sha_ok'])
print('tests with sha:',sum(1 for x in R if x['test_source_sha256']),'matched:',sum(1 for x in R if x['in_package']))
