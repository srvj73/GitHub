import sys, json, hashlib, os, pathlib, types, tempfile, shutil
cand, outp = sys.argv[1], sys.argv[2]
src = pathlib.Path(cand)/'recovery/modules/orchestrator.py'
raw = src.read_bytes()
R = {'orchestrator_sha256': hashlib.sha256(raw).hexdigest().upper(), 'python': sys.version}
ns = {'__name__': 'audit_probe_library', '__file__': str(src)}
try:
    exec(compile(raw, str(src), 'exec'), ns)
    R['module_load'] = 'OK'
except Exception as e:
    R['module_load'] = 'FAIL:' + repr(e)
    json.dump(R, open(outp, 'w'), indent=2); print(R); sys.exit(0)
State = ns['State']
base = pathlib.Path(tempfile.mkdtemp(prefix='b06probe_', dir=os.path.dirname(outp)))
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper() if p.exists() else None
# P1: missing STATE -> constructor fabricates NEW/A0 and writes it
r1 = base/'p1'; s = State(r1); sp = r1/'state/STATE.json'
R['P1_missing_state'] = {'state_file_created': sp.exists(), 'next_node': s.d.get('next_node'), 'status': s.d.get('status')}
# P2: existing STATE (progress at D4/FAIL, pretty-printed) -> constructor rewrites bytes
r2 = base/'p2'; (r2/'state').mkdir(parents=True)
sp2 = r2/'state/STATE.json'; sp2.write_text(json.dumps({'schema':'TICKSTORE_ORCH_STATE_V001','next_node':'D4','completed':['A0'],'status':'FAIL','engine':None}, indent=4)+'\n')
before = h(sp2); State(r2); after = h(sp2)
R['P2_constructor_rewrite'] = {'sha_before': before, 'sha_after': after, 'rewritten': before != after}
# P3: STATE deleted after progress, journal kept -> silently restarts at A0, journal not consulted
r3 = base/'p3'; s3 = State(r3); s3.log('D3','FINISHED',status='PASS'); s3.d.update({'next_node':'D4','status':'FAIL'}); ns['atomj'](s3.sp, s3.d)
jl_before = (r3/'state/STATE_JOURNAL.jsonl').read_bytes()
(r3/'state/STATE.json').unlink()
s3b = State(r3)
R['P3_state_lost_journal_kept'] = {'journal_lines': len(jl_before.splitlines()), 'reinitialized_next_node': s3b.d.get('next_node'), 'reinitialized_status': s3b.d.get('status'), 'journal_unchanged': (r3/'state/STATE_JOURNAL.jsonl').read_bytes()==jl_before}
# P4: read-only commands construct State too (main() builds State before dispatching plan/status)
R['P4_main_constructs_state_before_plan_status'] = 'st=State(cfg["control_root"])' in raw.decode('utf-8')
# P5: O.gate hard-codes authorized True
R['P5_gate_self_authorized'] = '"authorized":True' in raw.decode('utf-8')
shutil.rmtree(base)
json.dump(R, open(outp, 'w'), indent=2)
print(json.dumps(R, indent=2))
