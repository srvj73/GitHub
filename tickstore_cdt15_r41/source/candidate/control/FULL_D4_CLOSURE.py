"""Read-only D4 closure proof, followed only by immutable evidence publication.

Never activates the engine: _d4r_activate_runtime and checkpoint reconciliation
write files and are deliberately not called. Frozen signature/semantic validators
are reused with an in-memory context and existing files pinned throughout.
"""
import base64
import os
from pathlib import Path
import re
import sys
import types
import uuid

from D4_FIRST_ADMISSION_PREP import Reads, require, sha, strict_json, RELEASE_SHA
from FULL_STAGE_EVIDENCE import closed_results, publish


def verify_complete_checkpoint(ns, authority_raw, descriptor, key, checkpoint_raw, read, *, expected_shadow_root):
    ra = strict_json(authority_raw)
    require(isinstance(expected_shadow_root, str) and expected_shadow_root, 'D4_CLOSURE_EXPECTED_SHADOW_ROOT')
    inventory = descriptor.get('s0_inventory')
    require(isinstance(inventory, dict) and inventory, 'D4_CLOSURE_EMPTY_INVENTORY')
    require(all(re.fullmatch(r'[0-9]{8}', k) for k in inventory), 'D4_CLOSURE_DATE_KEY')
    require(len(key) == 32 and sha(key) == ra['key_sha256'], 'D4_CLOSURE_KEY_IDENTITY')
    context = dict(run_id=ra['run_id'], run_authority_sha256=sha(authority_raw), key=key,
                   successor_release_sha256=ra['successor_release_sha256'], config_sha256=ra['config_sha256'],
                   owner_gate_sha256=ra['owner_gate_sha256'], generation=ra['generation'],
                   generation_sha256=ns['_d4r_sha_obj'](ra['generation']),
                   inventory=inventory, total=len(inventory), resume_root=Path(ra['resume_root']))
    signed = strict_json(checkpoint_raw)
    import hmac
    cp = signed.get('payload')
    require(signed.get('schema') == 'TICKSTORE_D4_SIGNED_CHECKPOINT_V003' and isinstance(cp, dict), 'D4_CLOSURE_CHECKPOINT_SCHEMA')
    require(hmac.compare_digest(str(signed.get('hmac_sha256', '')), ns['_d4r_hmac_hex'](key, cp)), 'D4_CLOSURE_CHECKPOINT_HMAC')
    require(cp.get('schema') == 'TICKSTORE_D4_CERTIFY_CHECKPOINT_V003', 'D4_CLOSURE_PAYLOAD_SCHEMA')
    for name in ('run_id', 'run_authority_sha256', 'successor_release_sha256', 'config_sha256',
                 'owner_gate_sha256', 'generation_sha256', 'total'):
        require(cp.get(name) == context[name], 'D4_CLOSURE_CHECKPOINT_BINDING:' + name)
    keys = sorted(inventory)
    require(cp.get('status') == 'ALL_CHUNKS_COMMITTED' and cp.get('committed') == keys
            and type(cp.get('committed_count')) is int and cp['committed_count'] == len(keys)
            and cp.get('last_committed') == keys[-1] and isinstance(cp.get('commit_map'), dict)
            and set(cp['commit_map']) == set(keys), 'D4_CLOSURE_INCOMPLETE_CHECKPOINT')
    previous = ns.get('_D4R_RUNTIME_AUTHORITY')
    ns['_D4R_RUNTIME_AUTHORITY'] = context
    evidence = []
    try:
        for date in keys:
            receipt = Path(descriptor['recovery_root'])/('d4_resume_prepared.' + ra['run_id'] + '.' + date + '.json')
            local = Path(ra['resume_root'])/'chunks'/(date + '.json')
            raw = read(receipt, cp['commit_map'][date]); mirror = read(local, cp['commit_map'][date])
            require(raw == mirror and sha(raw) == cp['commit_map'][date], 'D4_CLOSURE_CHUNK_READBACK:' + date)
            obj = strict_json(raw)
            # shadow_root was recorded in the signed binding, but must identify the
            # exact snapshot locator used by the qualified D4 instance.
            binding = obj.get('payload', {}).get('binding', {})
            require(binding.get('shadow_root') == expected_shadow_root, 'D4_CLOSURE_SHADOW_ROOT_BINDING')
            context['shadow_root'] = expected_shadow_root
            result = ns['_d4r_validate_attestation_obj'](obj, date, inventory[date])
            payload = obj['payload']; observed = payload.get('input_evidence')
            require(isinstance(observed, dict) and set(observed) == {'journal', 'partial'}, 'D4_CLOSURE_INPUT_EVIDENCE')
            for kind in ('journal', 'partial'):
                require(all(observed[kind].get(f) == inventory[date][kind][f] for f in ('path', 'sha256', 'bytes')),
                        'D4_CLOSURE_INPUT_BINDING:' + date)
            ns['_d4r_validate_result'](result, date, inventory[date], observed)
            evidence.append({'path': str(receipt), 'sha256': sha(raw)})
    finally:
        ns['_D4R_RUNTIME_AUTHORITY'] = previous
    return cp, evidence


def close_d4(admission):
    require(os.name == 'nt', 'D4_CLOSURE_WINDOWS_REQUIRED')
    root = admission.root; instance = admission.instance
    sys.path.insert(0, str(root/'adapter'))
    import runtime_locator_orchestrator_entry as entry
    import runtime_locator_adapter as adapter
    from FULL_STAGE_CONTINUATION import load
    from D4_FIRST_ADMISSION_BOOTSTRAP import dpapi
    state_path = Path(instance['state_path'])
    release = entry.acquire_state_boundary(state_path)
    try:
        entry.require_no_cas_debris(state_path)
        with Reads() as reads:
            state_raw = reads.read(state_path); state = strict_json(state_raw)
            require(state.get('schema') == 'TICKSTORE_ORCH_STATE_V001' and state.get('status') == 'PASS'
                    and state.get('next_node') == 'D5' and 'D4' in state.get('completed', [])
                    and 'D5' not in state['completed'], 'D4_CLOSURE_STATE_NOT_FINISHED')
            journal_raw = reads.read(state_path.with_name('STATE_JOURNAL.jsonl'))
            results, evidence = closed_results(journal_raw, ('D4',), state_path.parent.parent/'runs', reads.read)
            ra_path = Path(instance['d4_resume_root'])/'authority/RUN_AUTHORITY.json'
            ra_raw = reads.read(ra_path); ra = strict_json(ra_raw)
            require(ra.get('schema') == 'TICKSTORE_D4_RUN_AUTHORITY_V005' and ra.get('status') == 'ACTIVE'
                    and ra.get('effect_scope') == 'D4_ONLY' and ra.get('d5_authorized') is False
                    and ra.get('full_authorized') is False, 'D4_CLOSURE_AUTHORITY_SCOPE')
            require(ra.get('final_code_manifest_sha256') == admission.descriptor['code_manifest_sha256'], 'D4_CLOSURE_CODE_IDENTITY')
            require(re.fullmatch(r'[0-9A-F]{32}', ra.get('run_id', '')), 'D4_CLOSURE_RUN_ID')
            require(Path(ra['resume_root']).absolute() == (Path(instance['d4_resume_root'])/'checkpoint').absolute(), 'D4_CLOSURE_CHECKPOINT_ROOT')
            cfg_raw = reads.read(ra['config_path'], instance['config_sha256']); cfg = strict_json(cfg_raw)
            require(sha(cfg_raw) == ra['config_sha256'] and Path(cfg['control_root'])/'state/STATE.json' == state_path,
                    'D4_CLOSURE_CONFIG_IDENTITY')
            eraw = admission.read(root/'recovery/engine/tickstore_publisher_recovery_v004_release.py', RELEASE_SHA)
            ns = load(eraw, root/'recovery/engine/tickstore_publisher_recovery_v004_release.py')
            require(ra['successor_release_sha256'] == RELEASE_SHA, 'D4_CLOSURE_ENGINE')
            descriptor_raw = reads.read(ra['owner_gate_path'], ra['owner_gate_sha256']); descriptor = strict_json(descriptor_raw)
            binding = strict_json(reads.read(ra['adapter_binding_path'], ra['adapter_binding_sha256']))
            locator = strict_json(reads.read(ra['gca_recovery_receipt_path'], ra['gca_recovery_receipt_sha256']))
            adapter.validate_binding(binding); adapter.validate_locator_receipt(locator, binding)
            cp_raw = reads.read(Path(ra['resume_root'])/'CHECKPOINT.json')
            key = dpapi(base64.b64decode(ra['protected_key_b64'], validate=True), False)
            admitted = types.SimpleNamespace(state_raw=state_raw, config_sha256=sha(cfg_raw))
            entry.reconcile_resume_identity(entry.RunIdentity(ra, ra_raw, descriptor_raw), binding, admitted, locator, eraw, key.hex())
            entry.validate_first_admission_commit(ra, state_raw, state_path)
            # Retain all transitive admission inputs after the legacy readback,
            # whose temporary handles otherwise end before receipt publication.
            manifest_path = Path(ra['first_admission_manifest_path'])
            commit = strict_json(reads.read(manifest_path, ra['first_admission_manifest_sha256']))
            for name, digest in commit['files'].items():
                reads.read(manifest_path.parent/name, digest)
            for pk, hk in (('b07_receipt_path', 'b07_receipt_sha256'),
                           ('completeness_path', 'completeness_sha256'),
                           ('final_code_manifest_path', 'final_code_manifest_sha256'),
                           ('policy_master_path', 'policy_master_sha256'),
                           ('policy_head_path', 'policy_head_sha256'),
                           ('origin_witness_path', 'origin_witness_sha256')):
                reads.read(ra[pk], ra[hk])
            require(len(descriptor['s0_inventory']) == ns['S0_COUNT'], 'D4_CLOSURE_INVENTORY_CARDINALITY')
            # Derive from the separately hash-bound admitted locator and STATE
            # scratch root, never from the attestation being checked itself.
            shadow_view = object.__new__(ns['NativeVSS']); shadow_view.profile = state['cprof']
            expected_shadow = str(shadow_view.shadow_root(locator['generation'], state['canary']['scratch']))
            native_vss = ns['NativeVSS'](ns['Win32Store'](), state['cprof'])
            try:
                current = adapter.reconcile_generation(native_vss, ra['generation'], binding)
                require(current == locator['generation'], 'D4_CLOSURE_LOCATOR_RECONCILIATION_REQUIRED')
                native_vss.assert_present(current)
            finally:
                native_vss.close()
            cp, chunk_evidence = verify_complete_checkpoint(ns, ra_raw, descriptor, key, cp_raw, reads.read,
                                                           expected_shadow_root=expected_shadow)
            del key
            cert_raw = base64.b64decode(state['canary_scratch_cert'], validate=True); cert = strict_json(cert_raw)
            require(sha(cert_raw) == results['D4'].get('cert_sha256') and cert.get('schema') == 'SCRATCH_ADMISSION_CERT_V004'
                    and cert.get('result') == 'PASS_1399_1399' and cert.get('generation') == ra['generation']
                    and cert.get('source_sha256') == RELEASE_SHA and cert.get('ledger_sha256') == ns['LEDGER_SHA']
                    and cert.get('days') == descriptor['s0_inventory'], 'D4_CLOSURE_CERTIFICATE_BINDING')
            require(ns['recovery_process_census']()['known_recovery_supervisor_or_workers'] == 0, 'D4_CLOSURE_PROCESS_NOT_CLEAR')
            reads.revalidate(); admission.revalidate()
            writer = adapter.make_no_clobber_receipt_writer(lambda why: require(False, why))
            output = state_path.parent.parent/'evidence'/('D4_CLOSURE_' + uuid.uuid4().hex.upper())
            # Only after every physical proof. No authority, STATE or checkpoint mutation.
            output.mkdir(exist_ok=False)
            for pk, hk in (('gca_recovery_receipt_path', 'gca_recovery_receipt_sha256'),
                           ('adapter_binding_path', 'adapter_binding_sha256')):
                evidence.append({'path': ra[pk], 'sha256': ra[hk]})
            evidence += chunk_evidence + [{'path': str(ra_path), 'sha256': sha(ra_raw)}]
            return publish('D4', admission, output, writer,
                {'STATE_AFTER.json': state_raw, 'JOURNAL_AFTER.jsonl': journal_raw,
                 'CHECKPOINT_AFTER.json': cp_raw, 'SCRATCH_CERT.json': cert_raw}, evidence,
                checks={'scratch_certification': True, 'checkpoint_readback': True, 'journal_closed': True},
                extra={'state_after_sha256': sha(state_raw), 'run_authority_path': str(ra_path),
                       'run_authority_sha256': sha(ra_raw), 'd4_run_id': ra['run_id'],
                       'g_ca_receipt_path': ra['gca_recovery_receipt_path'],
                       'g_ca_receipt_sha256': ra['gca_recovery_receipt_sha256'],
                       'adapter_binding_path': ra['adapter_binding_path'],
                       'adapter_binding_sha256': ra['adapter_binding_sha256']})
    finally:
        release()
