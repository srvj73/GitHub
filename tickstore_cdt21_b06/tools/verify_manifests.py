import sys, json, hashlib, os
C = sys.argv[1]; out = sys.argv[2]
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest().upper()
def check(man, base):
    res = {'total': len(man['files']), 'ok': 0, 'missing': [], 'mismatch': []}
    for f in man['files']:
        p = os.path.join(base, f['path'])
        if not os.path.isfile(p): res['missing'].append(f['path']); continue
        if os.path.getsize(p) != f['bytes'] or sha(p) != f['sha256'].upper(): res['mismatch'].append(f['path']); continue
        res['ok'] += 1
    return res
R = {}
pm = json.load(open(f"{C}/PACKAGE_MANIFEST.json", encoding='utf-8'))
R['PACKAGE'] = check(pm, C)
allfiles = sorted(os.path.relpath(os.path.join(d,f), C).replace(os.sep,'/') for d,_,fs in os.walk(C) for f in fs)
R['PACKAGE_unlisted'] = sorted(set(allfiles) - {f['path'] for f in pm['files']})
sm = json.load(open(f"{C}/implementation_v001/SOURCE_MANIFEST.json", encoding='utf-8'))
R['SOURCE'] = check(sm, f"{C}/implementation_v001")
impl = sorted(os.path.relpath(os.path.join(d,f), f"{C}/implementation_v001").replace(os.sep,'/') for d,_,fs in os.walk(f"{C}/implementation_v001") for f in fs)
R['SOURCE_unlisted'] = sorted(set(impl) - {f['path'] for f in sm['files']})
rm = json.load(open(f"{C}/implementation_v001/RUNTIME_CODE_MANIFEST.json", encoding='utf-8'))
R['RUNTIME'] = check(rm, f"{C}/implementation_v001/candidate")
cdir = f"{C}/implementation_v001/candidate"
cfiles = sorted(os.path.relpath(os.path.join(d,f), cdir).replace(os.sep,'/') for d,_,fs in os.walk(cdir) for f in fs)
R['RUNTIME_unlisted_in_candidate_dir'] = sorted(set(cfiles) - {f['path'] for f in rm['files']})
R['RUNTIME_manifest_sha'] = sha(f"{C}/implementation_v001/RUNTIME_CODE_MANIFEST.json")
R['SOURCE_manifest_sha'] = sha(f"{C}/implementation_v001/SOURCE_MANIFEST.json")
json.dump(R, open(out,'w'), indent=2)
for k,v in R.items():
    if isinstance(v, dict): print(k, {kk:(vv if not isinstance(vv,list) else len(vv)) for kk,vv in v.items()}, v.get('missing')[:5], v.get('mismatch')[:5])
    else: print(k, v)
