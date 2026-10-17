"""Probe D3: compile_instance output consumed by G5_FINAL_COMPLETENESS_PRODUCER binding check."""
import sys, json, pathlib
cand = pathlib.Path(sys.argv[1]) / 'candidate/control'
sys.path.insert(0, str(cand))
import FULL_INSTANCE_PREPARE as P
from FULL_RUNNER import D4_PARAMETERS
code = 'C' * 64
base = '/qual/sandbox'
params = {k: (code if k == 'FinalCodeManifestSha' else ('F' * 64 if k.endswith('Sha') else base + '/' + k)) for k in D4_PARAMETERS}
params['PolicyRoot'] = base + '/policy_root'; params['OriginCapturePath'] = base + '/origin_witness'
inputs = {'schema': 'TICKSTORE_INSTANCE_INPUTS_V001', 'd4_parameters': params, 'resources': {'max_workers': 4, 'ram_target_percent': 50},
          'config_sha256': 'D' * 64, 'ledger_path': base + '/ledger.zip', 'd4_resume_root': base + '/resume',
          'policy_root': base + '/policy_root', 'origin_witness': base + '/origin_witness'}
import os
for k in ('source', 'dest', 'scratch'): inputs[k + '_root'] = base + '/' + k
bindings = {k + '_root': os.path.normcase(os.path.abspath(inputs[k + '_root'])) for k in ('source', 'dest', 'scratch')}
inst = P.compile_instance(inputs, bindings, {'control_root': base + '/control'}, code, 'E' * 64, run_id='A' * 32)
ok = inst.get('schema') == 'TICKSTORE_FULL_INSTANCE_V001' and inst.get('code_manifest_sha256') == code   # producer predicate
print(json.dumps({'instance_keys': sorted(inst), 'producer_binding_predicate': ok}))
neg = P.compile_instance(inputs, bindings, {'control_root': base + '/control'}, code, 'E' * 64, run_id='A' * 32)
neg_ok = neg.get('code_manifest_sha256') == 'B' * 64
print('NEGATIVE_OTHER_CODE_ACCEPTED=' + str(neg_ok))
sys.exit(0 if ok and not neg_ok else 1)
