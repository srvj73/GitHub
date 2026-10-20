import json,sys,os,hashlib,re
H,C,out=sys.argv[1],sys.argv[2],sys.argv[3]
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest().upper()
er=json.load(open(f"{H}/NATIVE_EVIDENCE/ENGINEERING_RESULT.json",encoding='utf-8'))
idx={}
for d,_,fs in os.walk(C):
    for f in fs: idx.setdefault(f,[]).append(os.path.relpath(os.path.join(d,f),C))
commits=set(f[:-5] for f in os.listdir(f"{H}/NATIVE_EVIDENCE/COMMITS"))
R=[]
for role,t in er['tests'].items():
    rec={'role':role,'status':t.get('status'),'exit':t.get('exit_code'),'own_commit':role in commits}
    if 'log' in t:
        cands=[os.path.join(d,t['log']) for d in (f"{H}/NATIVE_EVIDENCE/LOGS",f"{H}/NATIVE_EVIDENCE/FINAL_G5/PROOF_NATIVE/LOGS")]
        rec['log_matches']=[os.path.relpath(p,H) for p in cands if os.path.isfile(p) and sha(p)==t['sha256'].upper()]
        src=role.replace('SUITE_','',1)
        rec['test_source_in_pkg']=idx.get(src,[])
        if rec['log_matches']:
            txt=open(os.path.join(H,rec['log_matches'][0]),encoding='utf-8',errors='replace').read()
            m=re.search(r'Ran (\d+) tests?',txt); rec['ran']=int(m.group(1)) if m else None
            rec['ok_line']=bool(re.search(r'^OK\b',txt,re.M)); rec['skips']=len(re.findall(r'\.\.\. skipped',txt))
            rec['count_consistent']= rec['ran']==t.get('test_count')
    R.append(rec)
json.dump(R,open(out,'w'),indent=2)
for r in R: print(r['role'][:48].ljust(48), r['status'], 'own_commit' if r['own_commit'] else 'NO_COMMIT', 'log' if r.get('log_matches') else ('-' if 'log_matches' not in r else 'LOG_MISSING'), r.get('ran'), r.get('count_consistent'), r.get('skips'), (r.get('test_source_in_pkg') or [''])[0][:60])
print('roles',len(R),'with own commit',sum(r['own_commit'] for r in R))
