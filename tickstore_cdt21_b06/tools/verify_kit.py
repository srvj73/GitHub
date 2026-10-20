import sys, json, hashlib, zipfile, io, collections
kit_dir = sys.argv[1]
out = sys.argv[2]
def sha(b): return hashlib.sha256(b).hexdigest().upper()
R = {}
man = json.load(open(f"{kit_dir}/KIT_TRANSPORT_MANIFEST.json", encoding='utf-8'))
km = []
for f in man['files']:
    b = open(f"{kit_dir}/{f['path']}", 'rb').read()
    km.append({'path': f['path'], 'bytes_ok': len(b)==f['bytes'], 'sha_ok': sha(b)==f['sha256'].upper(), 'sha_actual': sha(b)})
R['kit_manifest'] = km
R['kit_manifest_all_ok'] = all(x['bytes_ok'] and x['sha_ok'] for x in km)
hb = open(f"{kit_dir}/ORIGINAL_HANDOFF_TICKS20_TO_TICKS21_V002.zip",'rb').read()
R['handoff_sha'] = sha(hb); R['handoff_bytes'] = len(hb)
hz = zipfile.ZipFile(io.BytesIO(hb))
R['handoff_testzip'] = hz.testzip()
infos = hz.infolist()
names = [i.filename for i in infos]
R['handoff_entries'] = len(names)
R['handoff_dup_casefold'] = [k for k,v in collections.Counter(n.rstrip('/').casefold() for n in names).items() if v>1]
R['handoff_unsafe'] = [n for n in names if n.startswith('/') or '..' in n.replace('\\','/').split('/') or ':' in n.split('/')[0]]
files = {i.filename: i for i in infos if not i.is_dir()}
cand = hz.read('CANDIDATE/FINAL_PACKAGE_V002.zip')
R['candidate_sha'] = sha(cand); R['candidate_bytes'] = len(cand)
cz = zipfile.ZipFile(io.BytesIO(cand))
R['candidate_testzip'] = cz.testzip(); R['candidate_entries'] = len(cz.namelist())
commits = sorted(n for n in files if n.startswith('NATIVE_EVIDENCE/COMMITS/') and n.endswith('.json'))
R['commit_count'] = len(commits)
links = {}; per_commit = {}; conflicts = []; raw_refs = 0
for c in commits:
    j = json.loads(hz.read(c))
    arts = j.get('artifacts', [])
    raw_refs += len(arts)
    present = 0; missing = 0; bad = []
    for a in arts:
        m = 'NATIVE_EVIDENCE/' + a['member'].replace('\\','/')
        rec = (int(a['bytes']), a['sha256'].upper())
        if m in links and links[m]['id'] != rec: conflicts.append(m)
        links.setdefault(m, {'id': rec, 'commits': []})['commits'].append(c)
        if m in files:
            b = hz.read(m)
            if (len(b), sha(b)) == rec: present += 1
            else: bad.append(m)
        else: missing += 1
    per_commit[c] = {'artifacts': len(arts), 'present_ok': present, 'missing': missing, 'corrupt': bad, 'keys': sorted(k for k in j.keys() if k!='artifacts')}
R['raw_artifact_refs'] = raw_refs
R['unique_links'] = len(links)
R['conflicting_links'] = conflicts
pres = {m:v for m,v in links.items() if m in files}
miss = {m:v for m,v in links.items() if m not in files}
okp = [m for m,v in pres.items() if (lambda b:(len(b),sha(b)))(hz.read(m))==v['id']]
R['links_present_verified'] = len(okp)
R['links_present_corrupt'] = sorted(set(pres)-set(okp))
R['links_missing'] = len(miss)
R['links_missing_bytes'] = sum(v['id'][0] for v in miss.values())
R['missing_outside_g3g6'] = [m for m in miss if not m.startswith('NATIVE_EVIDENCE/WORK/G3_G6_NATIVE/')]
R['missing_by_commit'] = collections.Counter(c for v in miss.values() for c in v['commits'])
req = json.load(open(f"{kit_dir}/REQUIRED_223_PRIMARY_FILES.json", encoding='utf-8'))
reqset = {('NATIVE_EVIDENCE/'+f['member'] if not f['member'].startswith('NATIVE_EVIDENCE/') else f['member'], f['bytes'], f['sha256'].upper()) for f in req['files']}
myset = {(m, v['id'][0], v['id'][1]) for m,v in miss.items()}
R['required223_count'] = len(req['files'])
R['required223_equals_independent_missing_set'] = reqset == myset
R['required223_sym_diff'] = sorted(map(str, reqset ^ myset))[:10]
R['per_commit'] = per_commit
json.dump(R, open(out,'w'), indent=2, default=str, ensure_ascii=False)
for k,v in R.items():
    if k not in ('per_commit','kit_manifest'): print(k, '=', v)
print('kit_manifest', [(x['path'], x['bytes_ok'], x['sha_ok']) for x in km])
