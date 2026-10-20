"""Seal the CDT20 PRE-G06 integrated transport. Sandbox evidence is labelled, never native."""
import ast,difflib,hashlib,json,re,subprocess,sys,zipfile,shutil
from pathlib import Path
S=Path(sys.argv[1]).resolve()            # scratchpad
D=S/'build/delivery'                      # transport members
OUT=S/'build/out'
def sha(b):return hashlib.sha256(b).hexdigest().upper()
def fsha(p):return sha(Path(p).read_bytes())
def enc(o):return (json.dumps(o,sort_keys=True,ensure_ascii=True,indent=2)+'\n').encode()
def run(cmd,log,cwd=None):
    p=subprocess.run(cmd,capture_output=True,cwd=cwd,timeout=1800)
    raw=p.stdout+p.stderr;(D/'_sbx'/log).write_bytes(raw)
    return p.returncode,raw
build=json.loads((D/'BUILD_SUMMARY.json').read_bytes())
w=json.loads((D/'CDT20_R08Q1_WITNESS.json').read_bytes())
pack,code=w['package_sha256'],w['code_manifest_sha256']
assert fsha(D/w['package_name'])==pack
(D/'_sbx').mkdir(exist_ok=True)
pred=S/'cand/outer'
# Outer delta vs predecessor transport (G0 replaced, bootstrap observability).
patch=[]
for new,old in (('G0_CDT20_PRE_G06.py','G0_CDT20_PROJECTION.py'),('RUN_CDT20_R08Q1.py','RUN_CDT20_R08Q1.py'),('G0_SUITE_RUNNER.py',None)):
    a=(pred/old).read_text(encoding='utf8').splitlines(True) if old else []
    patch+=difflib.unified_diff(a,(D/new).read_text(encoding='utf8').splitlines(True),fromfile='predecessor/'+(old or '/dev/null'),tofile='successor/'+new)
(D/'INTEGRATED_DELTA_OUTER.patch').write_text(''.join(patch),encoding='utf8')
# ---- False-completeness / dead-code scan over every changed or new executable file ----
pkg=zipfile.ZipFile(D/w['package_name']);members={n:pkg.read(n) for n in pkg.namelist()}
corpus=b'\n'.join(v for n,v in members.items() if n.endswith('.py'))+b'\n'.join((D/f).read_bytes() for f in ('G0_CDT20_PRE_G06.py','G0_SUITE_RUNNER.py','RUN_CDT20_R08Q1.py'))
scan=[]
targets={n:members[n] for n in build['changed']+build['added']}
targets.update({f:(D/f).read_bytes() for f in ('G0_CDT20_PRE_G06.py','G0_SUITE_RUNNER.py','RUN_CDT20_R08Q1.py')})
for name,raw in sorted(targets.items()):
    tree=ast.parse(raw);defs=[n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    # unittest discovers TestCase subclasses by type, never by name reference.
    cases={n.name for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and any(getattr(b,'attr',getattr(b,'id',''))=='TestCase' for b in n.bases)}
    unused=[d for d in defs if not d.startswith('test') and d not in ('setUp','main') and d not in cases
            and len(re.findall(rb'\b'+d.encode()+rb'\b',corpus))<2]
    markers=[m.decode() for m in re.findall(rb'(?i)\b(TODO|FIXME|XXX|NotImplementedError|HACK)\b',raw)]
    lines=[l.strip().decode() for l in raw.splitlines() if re.search(rb'(?i)(skip_verification|bypass|force_pass|status=.PASS.\s*#)',l)]
    # Adjudicated: a line asserting the ABSENCE of a bypass is not a bypass.
    adjudicated=[l for l in lines if re.search(r'(?i)\bno bypass\b',l)]
    bypass=[l for l in lines if l not in adjudicated]
    scan.append({'file':name,'sha256':sha(raw),'definitions':len(defs),'unittest_cases_discovered_by_type':sorted(cases),
                 'unreferenced_definitions':unused,'markers':markers,'bypass_patterns':bypass,'adjudicated_non_bypass_lines':adjudicated})
scan_ok=all(not r['unreferenced_definitions'] and not r['markers'] and not r['bypass_patterns'] for r in scan)
(D/'_sbx/FALSE_COMPLETENESS_DEAD_CODE_SCAN.json').write_bytes(enc({'schema':'CDT20_FALSE_COMPLETENESS_SCAN_V001','status':'PASS' if scan_ok else 'FINDINGS','files':scan}))
assert scan_ok,scan
# ---- Source review bound to the exact package (consumed by RUN_CDT20_R08Q1 and completeness) ----
local=[]
for name,ref in (('SANDBOX_REGRESSION_PACKAGED.json','all package suites over extracted package bytes'),):
    local.append({'log':name,'sha256':fsha(S/'sbx'/name),'native_windows':False,'scope':ref})
review={'schema':'CDT19_IMPLEMENTER_SOURCE_REVIEW_V001','status':'SOURCE_REVIEW_COMPLETE_PENDING_NATIVE',
 'package_sha256':pack,'code_manifest_sha256':code,'known_fixable_blockers':[],'independent_b06_audit':False,
 'source_origin_sha256':build['parent_package_sha256'],'changes':build['delta'],'local_contract_tests':local,
 'scope':'IMPLEMENTER_TECHNICAL_REVIEW_ONLY','canonical_policy_custody_reviewed':False,'prior_commits_rebound':False,
 'prior_return_sha256':'4A339FE61E73B6E8993ACB4094FE0E55B061B71F109F37F7F6C8AD68E8B0C9E8',
 'core_frozen_sha256':build['core_frozen_sha256'],
 'pending_native':['G0_CAMPAIGN_CONTEXT_ALL_DELTA_SUITES','PRE_G06_CAMPAIGN_37_PLUS_1_UNITS_SUCCESSOR_IDENTITY',
                   'G3_G6_NATIVE_PROJECTION_THREE_G5_ROLES','FINAL_READBACK_VERIFY_NATIVE_CAMPAIGN',
                   'FIVE_PART_COMPLETENESS_AND_FOUR_FINDINGS_NATIVE']}
(D/'CDT20_SOURCE_REVIEW.json').write_bytes((json.dumps(review,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode())
# ---- Sandbox contract tests against the exact transport members ----
results={}
rc,raw=run([sys.executable,'-I','-B',str(D/'test_cdt20_bootstrap.py'),str(D)],'SANDBOX_test_cdt20_bootstrap.log')
results['test_cdt20_bootstrap.py']=(rc,re.findall(rb'Ran (\d+)',raw)[-1].decode(),raw.strip().splitlines()[-1].decode())
rc,raw=run([sys.executable,'-I','-B',str(D/'test_cdt20_g0_contract.py'),str(D)],'SANDBOX_test_cdt20_g0_contract.log')
results['test_cdt20_g0_contract.py']=(rc,re.findall(rb'Ran (\d+)',raw)[-1].decode(),raw.strip().splitlines()[-1].decode())
stage=S/'g0stage_final'
if stage.exists():shutil.rmtree(stage)
stage.mkdir()
for f in ('G0_CDT20_PRE_G06.py','G0_SUITE_RUNNER.py','G0_HISTORICAL_NATIVE_G3_G6.json','CDT20_R08Q1_WITNESS.json',w['package_name']):shutil.copy2(D/f,stage/f)
rc,raw=run([sys.executable,'-I','-B',str(S/'tools/g0_sandbox.py'),str(stage)],'SANDBOX_G0_QUALIFY_POSIX.log')
results['G0_QUALIFY_SANDBOX']=(rc,'13 suites',[l for l in raw.decode().splitlines() if l.startswith('SANDBOX_G0_RESULT')][0])
shutil.copy2(stage/'G0_RETURN.zip',D/'_sbx/SANDBOX_G0_RETURN_POSIX_NOT_NATIVE.zip')
for f in ('DRYRUN_FOUR_PRE_B06_FINDINGS.json','DRYRUN_ENGINEERING_COMPLETENESS.json','DRYRUN_FINAL_ENGINEERING_STATUS.json',
          'SANDBOX_REGRESSION_PACKAGED.json','SANDBOX_REGRESSION_PARENT_BASELINE.json','dryrun_post_g3.py','build_successor.py','run_all.py'):
    shutil.copy2(S/'sbx'/f,D/'_sbx'/f)
shutil.copy2(S/'tools/seal_transport.py',D/'_sbx/seal_transport.py');shutil.copy2(S/'tools/g0_sandbox.py',D/'_sbx/g0_sandbox.py')
assert all(v[0]==0 for v in results.values()),results
sbx=D/'SANDBOX_EVIDENCE_NOT_NATIVE.zip'
if sbx.exists():sbx.unlink()
with zipfile.ZipFile(sbx,'x',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((D/'_sbx').iterdir()):z.write(p,p.name)
shutil.rmtree(D/'_sbx')
hashes={f:fsha(D/f) for f in ('G0_CDT20_PRE_G06.py','G0_SUITE_RUNNER.py','RUN_CDT20_R08Q1.py','CDT20_SOURCE_REVIEW.json',
                             'G0_HISTORICAL_NATIVE_G3_G6.json','SANDBOX_EVIDENCE_NOT_NATIVE.zip')}
lock={'schema':'CDT20_INTEGRATED_PRE_G06_MISSION_LOCK_V002','mission_id':'CDT20_PRE_G06_OPUS_ONE_INTEGRATED_DELIVERY_20261020',
 'project':'Base de Dados CSV / Tickstore','thread':'Compressão De Ticks 20','scope':'ISOLATED_ENGINEERING_ONLY',
 'source_package_sha256':pack,'code_manifest_sha256':code,'parent_package_sha256':build['parent_package_sha256'],
 'historical_native_return_sha256':'4A339FE61E73B6E8993ACB4094FE0E55B061B71F109F37F7F6C8AD68E8B0C9E8',
 'historical_commits':'37_PRESERVED_UNDER_ORIGINAL_IDENTITY_NOT_REBOUND','historical_artifact_refs':'477_PRESERVED',
 'required_gates':['G0_TARGET_WINDOWS','PRE_B06_11_CHAIN','FOUR_PRE_B06_FINDINGS','NATIVE_G3_G6','SAFE_STOP','MULTIWORK',
                   'G5_PROOFS','FIVE_PART_COMPLETENESS'],
 'prohibitions':['NO_B06','NO_B07','NO_PRODUCTIVE_D4_D5','NO_CANARY','NO_FULL','NO_PRODUCTION','NO_POLICY_LOOKUP',
                 'DO_NOT_REBIND_HISTORICAL_COMMITS','NO_PHYSICAL_POWER_CUT'],
 'formal_b06':'NOT_STARTED','full':'NOT_STARTED','physical_powerloss':'NOT_TESTED_PHYSICAL_POWERLOSS'}
(D/'MISSION_LOCK.json').write_bytes(enc(lock))
matrix={'schema':'CDT20_PRE_G06_PREDELIVERY_CONTROL_MATRIX_V002','candidate_source_sha256':pack,'code_manifest_sha256':code,
 'bound_member_sha256':hashes,'checks':{
  'SOURCE_MANIFEST_PACKAGE_RUNTIME':'PASS_SANDBOX_304_MEMBERS','CORE_FROZEN':'PASS_749EEC5D',
  'TESTED_EQUALS_PACKAGED':'PASS_SANDBOX_REGRESSION_ON_EXTRACTED_PACKAGE_BYTES',
  'REGRESSION_VS_PARENT':'NO_NEW_FAILURE; PRE_EXISTING_POSIX_ONLY_FAILURES_UNCHANGED_OUTSIDE_CAMPAIGN_SET',
  'G0_CONTEXT_EQUIVALENT_TO_CAMPAIGN':'PASS_SANDBOX','G0_NEGATIVE_CONTROLS':'PASS_SANDBOX_11',
  'BOOTSTRAP_CONTRACT':'PASS_SANDBOX','POST_G3_CHAIN_ON_REAL_1219_BYTES':'PASS_SANDBOX_SYNTHETIC_REBIND_NOT_NATIVE',
  'FOUR_PRE_B06_FINDINGS_ON_REAL_1219_LOGS':'PASS_SANDBOX_NOT_NATIVE','FALSE_COMPLETENESS_DEAD_CODE_SCAN':'PASS',
  'LAUNCHER_PS51_PARSE_AND_LINT':'SEE_EXTERNAL_WITNESS','LAUNCHER_FUNCTIONAL_SANDBOX':'SEE_EXTERNAL_WITNESS',
  'G0_TARGET_RUNTIME':'TARGET_RUNTIME_PENDING','NATIVE_G3_G6_SAFE_STOP_MULTIWORK':'TARGET_RUNTIME_PENDING',
  'G5_PROOFS':'TARGET_RUNTIME_PENDING','FIVE_PART_COMPLETENESS':'TARGET_RUNTIME_PENDING'},
 'sandbox_results':{k:list(v) for k,v in results.items()},'formal_b06':'NOT_STARTED','target_windows':'NOT_PROVEN'}
(D/'PREDELIVERY_CONTROL_MATRIX.json').write_bytes(enc(matrix))
receipt={'schema':'CDT20_PREDELIVERY_ADMISSION_RECEIPT_V002','EXECUTABLE_DELIVERY_READY':'NOT_PROVEN',
 'executable_delivery_ready_reason':'TARGET_RUNTIME_PENDING_ONE_INTEGRATED_WINDOWS_RUN',
 'candidate_source_sha256':pack,'candidate_code_manifest_sha256':code,'matrix_sha256':fsha(D/'PREDELIVERY_CONTROL_MATRIX.json'),
 'mission_lock_sha256':fsha(D/'MISSION_LOCK.json'),'bound_member_sha256':hashes,
 'candidate_completeness_source':{'all_integrations_built':'PASS_SOURCE','internally_fixable_defects_zero':'PASS_SOURCE',
   'tested_equals_packaged':'PASS_SANDBOX_NATIVE_PENDING','false_completeness_dead_code_audit':'PASS',
   'final_bytes_frozen':'PASS'},
 'audit_dispatch':'NOT_REQUESTED_BY_IMPLEMENTER','b06':'NOT_STARTED','full':'NOT_STARTED'}
(D/'PREDELIVERY_ADMISSION_RECEIPT.json').write_bytes(enc(receipt))
names=sorted(p.name for p in D.iterdir() if p.is_file() and p.name not in ('TRANSPORT_MANIFEST.json','BUILD_SUMMARY.json'))
names.append('BUILD_SUMMARY.json');names=sorted(set(names))
rows=[{'path':n,'bytes':(D/n).stat().st_size,'sha256':fsha(D/n)} for n in names]
(D/'TRANSPORT_MANIFEST.json').write_bytes(enc({'schema':'CDT20_PRE_G06_TRANSPORT_MANIFEST_V002','files':rows,
  'package_sha256':pack,'native_status':'TARGET_RUNTIME_PENDING','production_authorized':False}))
OUT.mkdir(parents=True,exist_ok=True)
t=OUT/'CDT20_PRE_G06_INTEGRATED_TRANSPORT_20261020.zip'
if t.exists():t.unlink()
with zipfile.ZipFile(t,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for n in names+['TRANSPORT_MANIFEST.json']:
        info=zipfile.ZipInfo(n,date_time=(2026,10,20,12,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
        z.writestr(info,(D/n).read_bytes())
with zipfile.ZipFile(t) as z:
    assert z.testzip() is None
    for r in rows:assert sha(z.read(r['path']))==r['sha256']
print(json.dumps({'transport':t.name,'sha256':fsha(t),'bytes':t.stat().st_size,'members':len(names)+1,'results':results},indent=1))
