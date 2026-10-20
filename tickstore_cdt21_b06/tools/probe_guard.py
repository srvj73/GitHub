import sys, json, hashlib, os, pathlib, tempfile, shutil
cand, outp = pathlib.Path(sys.argv[1]), sys.argv[2]
def load(p, name):
    ns = {'__name__': name, '__file__': str(p)}; exec(compile(p.read_bytes(), str(p), 'exec'), ns); return ns
R = {}
try:
    entry = load(cand/'adapter/runtime_locator_orchestrator_entry.py', 'audit_probe_entry')
    R['entry_load'] = 'OK'
except Exception as e:
    R['entry_load'] = 'FAIL:' + repr(e); json.dump(R, open(outp,'w'), indent=2); print(R); sys.exit(0)
base = pathlib.Path(tempfile.mkdtemp(prefix='b06guard_', dir=os.path.dirname(outp)))
# G1: missing STATE under the adapter guard
ns = load(cand/'recovery/modules/orchestrator.py', 'audit_probe_orch')
root = base/'g1'; (root/'state').mkdir(parents=True)
try:
    entry['guard_frozen_state_reads'](ns, root/'state/STATE.json')
    st = ns['State'](root)
    R['G1_guarded_missing_state'] = {'outcome': 'CONSTRUCTED', 'state_exists': (root/'state/STATE.json').exists(), 'next_node': st.d.get('next_node')}
except Exception as e:
    R['G1_guarded_missing_state'] = {'outcome': 'FAIL_CLOSED', 'error': str(e)[:200], 'state_exists': (root/'state/STATE.json').exists()}
# G2: existing STATE under the guard -> constructor must not rewrite
ns2 = load(cand/'recovery/modules/orchestrator.py', 'audit_probe_orch2')
root2 = base/'g2'; (root2/'state').mkdir(parents=True); sp = root2/'state/STATE.json'
sp.write_text(json.dumps({'schema':'TICKSTORE_ORCH_STATE_V001','next_node':'D4','completed':['A0'],'status':'FAIL','engine':None}, indent=4)+'\n')
b = hashlib.sha256(sp.read_bytes()).hexdigest()
try:
    entry['guard_frozen_state_reads'](ns2, sp, state_validator=lambda o: None)
    ns2['State'](root2); a = hashlib.sha256(sp.read_bytes()).hexdigest()
    R['G2_guarded_existing_state'] = {'outcome': 'CONSTRUCTED', 'rewritten': a != b}
except Exception as e:
    R['G2_guarded_existing_state'] = {'outcome': 'ERROR', 'error': str(e)[:200], 'rewritten': hashlib.sha256(sp.read_bytes()).hexdigest() != b}
shutil.rmtree(base)
json.dump(R, open(outp,'w'), indent=2); print(json.dumps(R, indent=2))
