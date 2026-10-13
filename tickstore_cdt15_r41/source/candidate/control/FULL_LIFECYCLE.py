"""Overlay for MULTIWORK completion and technical readmission of the same instance.

The frozen orchestrator is never edited. G3 produces physical reconciliation
evidence; H1/H2/H4/H5/H6 retain their original implementations. H3 consumes the
exact G3 result named by the journal, never the newest file from another run.
"""
from pathlib import Path
import time

from D4_FIRST_ADMISSION_PREP import Reads, canonical, require, sha, strict_json
from FULL_RELEASE_CHAIN import REQUIRED_CHECKS
from FULL_STAGE_EVIDENCE import closed_results, publish


def verify_postfull(reconciliation, h2):
    require(reconciliation.get('schema') == 'TICKSTORE_MULTIWORK_RECONCILIATION_V001'
            and reconciliation.get('status') == 'PASS', 'FULL_RECONCILIATION_NOT_PASS')
    deep = h2.get('deep', {}); independent = h2.get('independent', {})
    require(isinstance(deep, dict) and isinstance(independent, dict)
            and deep.get('POST_FULL_AUDIT') == 'PASS'
            and independent.get('schema') == 'POSTFULL_INDEPENDENT_VERIFIER_V001'
            and independent.get('status') == 'PASS', 'FULL_POSTVERIFY_NOT_PASS')
    # The native frozen postverify() and independent verifier must agree on the
    # same published bytes and on the exact certified dataset, not only on rows.
    expected_counts = {'days': 1550, 'rows': 7049522162, 'namespace': 3101}
    for key, expected in expected_counts.items():
        require(type(deep.get(key)) is int and deep[key] == expected,
                'FULL_POSTVERIFY_EXPECTED:' + key)
    for key in ('days', 'rows', 'manifest_sha256'):
        require(deep.get(key) is not None and deep[key] == reconciliation.get(key),
                'FULL_POSTVERIFY_MISMATCH:' + key)
    require(isinstance(deep.get('manifest_sha256'), str)
            and len(deep['manifest_sha256']) == 64
            and all(c in '0123456789ABCDEF' for c in deep['manifest_sha256']),
            'FULL_POSTVERIFY_MANIFEST_SHA256')
    require(type(independent.get('days')) is int and independent['days'] == deep['days']
            and type(independent.get('rows')) is int and independent['rows'] == deep['rows']
            and type(independent.get('namespace_files')) is int
            and independent['namespace_files'] == deep['namespace']
            and independent.get('manifest_sha256') == deep['manifest_sha256'],
            'FULL_INDEPENDENT_READBACK_MISMATCH')
    return {'FINAL_VS_POSTFULL': 'PASS', 'manifest_sha256': deep['manifest_sha256']}


def install(o, ns, admission, workers):
    """Install only after chain, config, STATE and native boundary are held."""
    import tickstore_full_multiwork as multi
    original = o.runnode

    def dispatch(node):
        if node == 'G3':
            instance = admission.instance; bindings = instance['bindings']; limits = instance['resources']
            received = []

            def complete(result):
                require(not received, 'FULL_DUPLICATE_RECONCILIATION')
                raw = canonical(result); path = o.rd/'MULTIWORK_RECONCILIATION.json'
                ns['immutable_receipt'](path, raw)
                admission.read(path, sha(raw)); admission.revalidate()
                received.append({'path': str(path), 'sha256': sha(raw)})

            try:
                code = multi._execute_admitted_multiwork(
                    *(Path(bindings[k + '_root']) for k in ('source', 'dest', 'scratch')),
                    Path(instance['ledger_path']), workers, limits['max_workers'],
                    limits['ram_target_percent'], admission, completion=complete)
            except multi.CooperativeSafeStop:
                # MULTIWORK raises this only after its cooperative cleanup succeeds;
                # forced termination or cleanup failure is a non-resumable error.
                o.st.d['full_safe_stop'] = True
                raise ns['SafeStopFlow']('MULTIWORK_COOPERATIVE_STOP')
            require(code == 0 and len(received) == 1, 'FULL_RECONCILIATION_RECEIPT_MISSING')
            o.st.d['full_safe_stop'] = False
            return {'FULL': 'PASS', 'reconciliation': received[0], 'run_id': instance['run_id']}
        if node == 'G5':
            require(o.st.d.get('full_safe_stop') is False, 'FULL_RESUME_MUST_REENTER_G3')
            return {'RESUME': 'NOT_REQUIRED', 'resume_node': 'G3', 'engine': 'MULTIWORK'}
        if node == 'G6':
            # The legacy recovery path can launch a different engine and is not
            # an admissible fallback for a MULTIWORK instance.
            require(not (Path(o.cfg['production_dest_root'])/'TICKSTORE_WRITER.lock').exists(),
                    'FULL_WRITER_LOCK_RECONCILIATION_REQUIRED')
            require(o.eng.recovery_process_census()['known_recovery_supervisor_or_workers'] == 0,
                    'FULL_PROCESS_RECONCILIATION_REQUIRED')
            return {'RECONCILE': 'PASS', 'writer_lock': 'ABSENT', 'action': 'NONE'}
        if node == 'G7':
            # The frozen node publishes FULL_COMPLETE before H*. Preserve its
            # position in STATE, but reserve the completion claim for H6 closure.
            return {'schema': 'TICKSTORE_FULL_ENGINE_COMPLETE_V001',
                    'status': 'ENGINE_RECONCILED_POSTFULL_PENDING',
                    'run_id': admission.instance['run_id'], 'full_complete': False}
        if node == 'H3':
            with Reads() as proof:
                results, _ = closed_results(proof.read(o.st.jp), ('G3',), o.st.runs, proof.read)
                meta = results['G3']['reconciliation']
                result = strict_json(proof.read(meta['path'], meta['sha256']))
                require(result.get('run_id') == admission.instance['run_id']
                        and result.get('instance_sha256') == admission.descriptor['instance_sha256']
                        and result.get('code_manifest_sha256') == admission.descriptor['code_manifest_sha256'],
                        'FULL_RECONCILIATION_INSTANCE')
                checked = verify_postfull(result, o.st.d.get('postfull_h2', {}))
                proof.revalidate()
                return dict(checked, reconciliation=meta)
        return original(node)

    o.runnode = dispatch


def publish_completion(o, ns, admission, nodes):
    with Reads() as proof:
        state_raw = proof.read(o.st.sp); state = strict_json(state_raw)
        require(state == o.st.d and state.get('status') == 'PASS' and state.get('next_node') == 'I1'
                and all(n in state.get('completed', []) for n in nodes), 'FULL_FINAL_STATE')
        journal = proof.read(o.st.jp)
        results, evidence = closed_results(journal, nodes, o.st.runs, proof.read)
        meta = results['G3']['reconciliation']; evidence.append(meta)
        reconciliation = strict_json(proof.read(meta['path'], meta['sha256']))
        verify_postfull(reconciliation, results['H2'])
        require(results['H3'].get('FINAL_VS_POSTFULL') == 'PASS'
                and results['H3'].get('reconciliation') == meta, 'FULL_H3_NOT_BOUND')
        pack = results['H6']; proof.read(pack['path'], pack['sha256']); evidence.append(pack)
        for name, raw in [('FULL_STATE_AFTER.json', state_raw), ('FULL_JOURNAL_AFTER.jsonl', journal)]:
            path = o.rd/name; ns['immutable_receipt'](path, raw)
            evidence.append({'path': str(path), 'sha256': sha(raw)})
        for item in evidence: admission.read(item['path'], item['sha256'])
        proof.revalidate(); admission.revalidate()
        receipt = dict(schema='TICKSTORE_FULL_COMPLETION_V001', status='PASS',
                       environment='WINDOWS_PRODUCTION', run_id=admission.instance['run_id'],
                       instance_sha256=admission.descriptor['instance_sha256'],
                       code_manifest_sha256=admission.descriptor['code_manifest_sha256'],
                       full_admission_sha256=admission.receipt_hashes['FULL_ADMISSION'],
                       state_after_sha256=sha(state_raw), evidence=evidence,
                       created_unix_ns=time.time_ns(), next_node='I1',
                       csv_deletion_authorized=False, format_promotion_authorized=False)
        path = o.rd/'FULL_COMPLETION.json'; raw = canonical(receipt)
        ns['immutable_receipt'](path, raw); admission.read(path, sha(raw)); admission.revalidate()
        print('FULL_COMPLETION_FILE=' + str(path) + '\nFULL_COMPLETION_SHA256=' + sha(raw), flush=True)
        return path, sha(raw)


def refresh_admission(o, ns, admission, facts, nodes):
    """New immutable descriptor, same instance; no rewind or scratch replacement."""
    with Reads() as proof:
        state_raw = proof.read(o.st.sp); state = strict_json(state_raw)
        require(state == o.st.d, 'READMISSION_STATE_DRIFT')
        journal = proof.read(o.st.jp)
        # All completed FULL nodes must have current, hash-bound results. The
        # pending node must have no STARTED without FINISHED (checked by caller).
        completed = tuple(n for n in nodes if n in state['completed'])
        _, evidence = closed_results(journal, completed, o.st.runs, proof.read)
        old = admission.descriptor['receipts']['FULL_ADMISSION']
        evidence.append(old)
        evidence += admission.receipts['FULL_ADMISSION']['evidence']
        # publish() keeps its no-replacement invariant. A view exposes the exact
        # immutable prefix, while the original receipt remains explicit evidence.
        class Prefix:
            descriptor = dict(admission.descriptor, receipts={k: v for k, v in admission.descriptor['receipts'].items()
                                                             if k != 'FULL_ADMISSION'})
            receipt_sha = admission.receipt_hashes['FULL_PREP']
            read = admission.read
            revalidate = admission.revalidate
        proof.revalidate()
        return publish('FULL_ADMISSION', Prefix(), o.rd, ns['immutable_receipt'],
                       {'STATE_AFTER.json': state_raw, 'JOURNAL_AFTER.jsonl': journal}, evidence,
                       checks={k: True for k in REQUIRED_CHECKS['FULL_ADMISSION']},
                       extra=dict(facts, state_after_sha256=sha(state_raw),
                                  readmission_of_sha256=old['sha256'],
                                  resumed_node=state['next_node'], run_id=admission.instance['run_id']))
