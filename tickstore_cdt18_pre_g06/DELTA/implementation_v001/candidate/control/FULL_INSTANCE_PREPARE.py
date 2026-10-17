"""Compile physical instance inputs and assemble existing technical receipts.

INSTANCE is data, never RUN_AUTHORITY or an approval. This tool cannot issue
G5/B06/B07 receipts and cannot dispatch D4, canary or FULL.
"""
import argparse
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent))
from D4_FIRST_ADMISSION_PREP import Reads, require, canonical, sha, strict_json
from FULL_RELEASE_CHAIN import ReleaseChain, STAGES, digest, validate_chain
from FULL_RUNNER import D4_PARAMETERS


def compile_instance(inputs, bindings, config, code_sha, python_sha, *, run_id):
    require(inputs.get('schema') == 'TICKSTORE_INSTANCE_INPUTS_V001', 'INSTANCE_INPUT_SCHEMA')
    require(isinstance(inputs.get('d4_parameters'), dict) and set(inputs['d4_parameters']) == D4_PARAMETERS,
            'INSTANCE_D4_PARAMETERS')
    p = inputs['d4_parameters']; limits = inputs.get('resources', {})
    for key in ('source_root','dest_root','scratch_root','ledger_path','d4_resume_root','policy_root','origin_witness'):
        require(isinstance(inputs.get(key), str) and Path(inputs[key]).is_absolute(), 'INSTANCE_ABSOLUTE_PATH:' + key)
    require(Path(config['control_root']).is_absolute(), 'INSTANCE_CONTROL_ROOT')
    for key, value in p.items():
        if not key.endswith('Sha'):
            require(isinstance(value, str) and Path(value).is_absolute(), 'INSTANCE_D4_ABSOLUTE_PATH:' + key)
    require(type(limits.get('max_workers')) is int and 1 <= limits['max_workers'] <= 32
            and type(limits.get('ram_target_percent')) is int and 20 <= limits['ram_target_percent'] <= 80,
            'INSTANCE_RESOURCE_LIMITS')
    require(p['FinalCodeManifestSha'] == code_sha, 'INSTANCE_MANIFEST_BINDING')
    require(p['PolicyRoot'] == inputs['policy_root'] and p['OriginCapturePath'] == inputs['origin_witness'],
            'INSTANCE_POLICY_INPUTS')
    for label in ('source', 'dest', 'scratch'):
        require(bindings[label + '_root'] == os.path.normcase(os.path.abspath(inputs[label + '_root'])),
                'INSTANCE_ROOT_BINDING:' + label)
    # CDT18: the G5 final producer binds the instance to this exact runtime code manifest.
    return dict(schema='TICKSTORE_FULL_INSTANCE_V001', run_id=run_id, code_manifest_sha256=code_sha,
        bindings={k:v for k,v in bindings.items() if k not in ('schema','authorized')}, resources=dict(limits), ledger_path=inputs['ledger_path'],
        python_sha256=python_sha, config_sha256=inputs['config_sha256'],
        state_path=str(Path(config['control_root'])/'state/STATE.json'),
        d4_resume_root=inputs['d4_resume_root'], policy_root=inputs['policy_root'],
        origin_witness=inputs['origin_witness'], d4_parameters=dict(p),
        preparation_only=True, authority_created=False, production_started=False)


def write_new(path, raw):
    # Native no-clobber publication checks ancestors and keeps a readback handle.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'adapter'))
    from runtime_locator_adapter import make_no_clobber_receipt_writer
    make_no_clobber_receipt_writer(lambda why: require(False, why))(path, raw)


def prepare(inputs_path, inputs_sha, output):
    require(os.name == 'nt', 'INSTANCE_PREPARATION_WINDOWS_REQUIRED')
    root=Path(__file__).resolve().parent.parent
    import D4_FIRST_ADMISSION_BOOTSTRAP as boot
    import D4_FIRST_ADMISSION_TRANSACTION as tx
    with Reads() as reads:
        inputs = strict_json(reads.read(inputs_path, digest(inputs_sha, 'INPUTS')))
        params = inputs['d4_parameters']
        manifest_raw = reads.read(params['FinalCodeManifestPath'], params['FinalCodeManifestSha'])
        boot.read_code_set(reads, params['FinalCodeManifestPath'], sha(manifest_raw), root)
        capmod = boot.lib(reads.read(root/'control/POLICY_CAPTURE_BINDING.py'), root/'control/POLICY_CAPTURE_BINDING.py')
        boot.policy_current(reads, inputs['policy_root'], inputs['origin_witness'],
                            digest(inputs.get('origin_reconciliation_sha256'), 'POLICY_RECONCILIATION'), capmod)
        cfg = strict_json(reads.read(root/'recovery/config/STAGE_A_SEALED_VALUES_V001.json', inputs['config_sha256']))
        python_sha = sha(reads.read(sys.executable, cfg['python_exe_sha256']))
        sys.path.insert(0, str(root/'full'))
        import tickstore_serial_runner as core
        contract, cert, ids = core.full_release_materials(root/'full')
        reads.read(inputs['ledger_path'])
        days, months, ledger_sha = core.load_ledgers(Path(inputs['ledger_path']))
        core.validate_full_plan(days, months, ledger_sha, contract)
        bindings = core.full_gate_bindings(*(Path(inputs[k+'_root']) for k in ('source','dest','scratch')),ids,contract)
        for label in ('source','dest','scratch'):
            reads.enter_context(reads.store.open(Path(inputs[label+'_root']), directory=True))
        # Pin existing identity inputs without creating gates or changing STATE.
        reads.read(Path(cfg['control_root'])/'state/STATE.json')
        instance=compile_instance(inputs,bindings,cfg,sha(manifest_raw),python_sha,run_id=uuid.uuid4().hex.upper())
        reads.revalidate();raw=canonical(instance);write_new(Path(output),raw)
        reads.read(output,sha(raw));reads.revalidate()
        return dict(instance_path=str(Path(output).absolute()),instance_sha256=sha(raw),production_started=False)


def assemble_chain(instance_path, instance_sha, manifest_path, manifest_sha, receipt_spec, output, b06_sha, until='B07'):
    """Initial chain descriptor: until='B06' feeds the B07 runner (R45 G2), until='B07' feeds D4."""
    root=Path(__file__).resolve().parent.parent
    require(until in ('B06','B07'),'INITIAL_CHAIN_UNTIL')
    with Reads() as reads:
        reads.read(instance_path,digest(instance_sha,'INSTANCE'))
        reads.read(manifest_path,digest(manifest_sha,'CODE'))
        spec=strict_json(reads.read(receipt_spec));required=STAGES[:STAGES.index(until)+1]
        require(set(spec)==set(required),'INITIAL_CHAIN_REQUIRES_'+'_'.join(required))
        receipts={};hashes={}
        for stage in required:
            meta=spec[stage];raw=reads.read(meta['path'],digest(meta['sha256'],stage))
            receipts[stage]=strict_json(raw);hashes[stage]=sha(raw)
        validate_chain(receipts,hashes,code_sha=manifest_sha,instance_sha=instance_sha,b06_sha=b06_sha,until=until)
        descriptor=dict(schema='TICKSTORE_EXECUTION_CHAIN_V001',environment='WINDOWS_PRODUCTION',
            instance_path=str(Path(instance_path).absolute()),instance_sha256=instance_sha,
            code_manifest_path=str(Path(manifest_path).absolute()),code_manifest_sha256=manifest_sha,
            receipts={s:spec[s] for s in required})
        raw=canonical(descriptor);reads.revalidate()
        # Verify the complete consumer on temporary immutable descriptor first;
        # on failure preserve diagnostics, never expose a supposedly valid chain.
        pending=Path(output).with_name(Path(output).name+'.validation.'+uuid.uuid4().hex)
        write_new(pending,raw)
        with ReleaseChain(pending,sha(raw),b06_sha,root,until=until) as admitted:
            admitted.revalidate();write_new(Path(output),raw)
            admitted.read(output,sha(raw));admitted.revalidate()
        return dict(chain_file=str(Path(output).absolute()),chain_sha256=sha(raw),production_started=False)


def main():
    ap=argparse.ArgumentParser(allow_abbrev=False);sub=ap.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare');p.add_argument('--inputs',required=True);p.add_argument('--inputs-sha256',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('chain')
    for x in ('instance-path','instance-sha256','manifest-path','manifest-sha256','receipt-spec','output','b06-sha256'):p.add_argument('--'+x,required=True)
    p.add_argument('--until',choices=('B06','B07'),default='B07')
    a=ap.parse_args()
    try:
        result=prepare(a.inputs,a.inputs_sha256,a.output) if a.mode=='prepare' else assemble_chain(a.instance_path,a.instance_sha256,a.manifest_path,a.manifest_sha256,a.receipt_spec,a.output,a.b06_sha256,a.until)
        print(canonical(result).decode(),end='');return 0
    except (RuntimeError,OSError,KeyError,TypeError,ValueError) as exc:
        print('INSTANCE_PREPARATION_BLOCKED='+str(exc));return 2

if __name__=='__main__':
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log('INSTANCE_PREPARE', main))
