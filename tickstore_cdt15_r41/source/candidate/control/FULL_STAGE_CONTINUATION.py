"""Bounded continuation of the existing frozen orchestrator after D4.

No D4_ONLY authority is accepted here. Receipt admission precedes STATE access;
the V38 CAS guard is reused with an explicit, narrower node transition contract.
"""
from __future__ import annotations
import argparse
import base64
import ctypes
import json
import os
import re
from pathlib import Path
import sys
import types
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from D4_FIRST_ADMISSION_PREP import require, sha, strict_json, canonical, validate_journal
from FULL_RELEASE_CHAIN import ReleaseChain, REQUIRED_CHECKS
from FULL_STAGE_EVIDENCE import closed_results, publish

RANGES = {
    'D5': ('D5',),
    'CANARY': ('D6', 'D7', 'D8', 'D9', 'D10', 'D11', 'E1'),
    'FULL_PREP': ('E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8', 'E9'),
    'FULL_ADMIT': ('F1', 'F2', 'F3', 'G1', 'G2'),
    'FULL': ('G3', 'G4', 'G5', 'G6', 'G7', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6'),
}
NEXT = {'D5': 'D6', 'CANARY': 'E2', 'FULL_PREP': 'F1', 'FULL_ADMIT': 'G3', 'FULL': 'I1'}
PREVIOUS = {'D5': ('D4', 'D4'), 'CANARY': ('D5', 'D5'), 'FULL_PREP': ('CANARY', 'E1'),
            'FULL_ADMIT': ('FULL_PREP', 'E9'), 'FULL': ('FULL_ADMISSION', 'G2')}


class StageBoundary:
    def __init__(self, stage, *, close_only=False):
        require(stage in RANGES, 'CONTINUATION_STAGE')
        self.stage = stage; self.nodes = RANGES[stage]; self.close_only = close_only

    def validate(self, state):
        require(isinstance(state, dict) and state.get('schema') == 'TICKSTORE_ORCH_STATE_V001', 'CONTINUATION_STATE_SCHEMA')
        require(state.get('status') in ('PASS', 'FAIL', 'SAFE_STOP', 'BLOCKED'), 'CONTINUATION_STATE_STATUS')
        require(state.get('next_node') in (NEXT[self.stage],) if self.close_only else state.get('next_node') in self.nodes, 'CONTINUATION_NODE_OUTSIDE_STAGE')
        completed = state.get('completed')
        require(isinstance(completed, list) and len(completed) == len(set(completed)), 'CONTINUATION_COMPLETED_SET')
        require(PREVIOUS[self.stage][1] in completed and 'D4' in completed, 'CONTINUATION_PREVIOUS_STAGE_INCOMPLETE')
        require(isinstance(state.get('canary_scratch_cert'), str) and bool(state['canary_scratch_cert']), 'CONTINUATION_D4_CERTIFICATE')
        pos = len(self.nodes) if self.close_only else self.nodes.index(state['next_node'])
        require(all(n in completed for n in self.nodes[:pos]) and all(n not in completed for n in self.nodes[pos:]),
                'CONTINUATION_SEQUENCE')

    def transition(self, before, after):
        require(not self.close_only, 'CLOSURE_CANNOT_MUTATE_STATE')
        self.validate(before)
        node = before['next_node']; old = before['completed']; new = after.get('completed')
        require(isinstance(new, list) and new in (old, old + [node]), 'CONTINUATION_COMPLETION_JUMP')
        if new == old:
            require(after.get('next_node') == node, 'CONTINUATION_UNPROVEN_ADVANCE')
        else:
            pos = self.nodes.index(node)
            successor = self.nodes[pos + 1] if pos + 1 < len(self.nodes) else NEXT[self.stage]
            require(after.get('next_node') == successor and after.get('status') == 'PASS', 'CONTINUATION_NEXT_NODE')
        # Earlier stage evidence and physical instance roots cannot be replaced by a continuation.
        for key in ('schema', 'G_CA', 'cprof', 'canary', 'canary_scratch_cert', 'created_at'):
            require(after.get(key) == before.get(key), 'CONTINUATION_INSTANCE_DRIFT:' + key)
        for key in ('G_PA', 'pprof', 'canary_canonical_cert', 'prod_scratch_cert', 'prod_canonical_cert'):
            if before.get(key) is not None:
                require(after.get(key) == before[key], 'CONTINUATION_SEALED_VALUE_DRIFT:' + key)


def load(raw, path):
    ns = {'__name__': 'tickstore_admitted_continuation_library', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), ns)
    return ns


def last_closed_node(raw, node):
    validate_journal(raw)
    records = [strict_json(line) for line in raw.splitlines()]
    latest = [r for r in records if r.get('node') == node]
    require(bool(latest) and latest[-1].get('phase') == 'FINISHED'
            and latest[-1].get('status') == 'PASS', 'CONTINUATION_JOURNAL_NOT_CLOSED:' + node)


def validate_stage_history(raw, boundary, state):
    """A crash gap is a reconciliation boundary, never permission to replay."""
    validate_journal(raw)
    attempts = {}
    for line in raw.splitlines():
        item = strict_json(line); node = item.get('node')
        if node not in boundary.nodes: continue
        previous = attempts.get(node)
        if item.get('phase') == 'STARTED':
            require(isinstance(item.get('run_id'), str)
                    and re.fullmatch(r'[A-Za-z0-9_-]+', item['run_id']), 'CONTINUATION_RUN_ID:' + node)
            require(previous is None or previous.get('phase') == 'FINISHED',
                    'CONTINUATION_UNCLOSED_STARTED:' + node)
            attempts[node] = item
        elif item.get('phase') == 'FINISHED':
            require(item.get('status') in ('PASS', 'FAIL', 'SAFE_STOP', 'BLOCKED'),
                    'CONTINUATION_FINISH_STATUS:' + node)
            require(previous is not None and previous.get('phase') == 'STARTED',
                    'CONTINUATION_UNPAIRED_FINISH:' + node)
            require(item.get('run_id', previous.get('run_id')) == previous.get('run_id'),
                    'CONTINUATION_FINISH_RUN:' + node)
            attempts[node] = item
        else: require(False, 'CONTINUATION_JOURNAL_PHASE:' + node)
    for node in boundary.nodes:
        require(node not in state['completed'] or node in attempts,
                'CONTINUATION_COMPLETED_WITHOUT_ATTEMPT:' + node)
    for node, item in attempts.items():
        require(item['phase'] == 'FINISHED', 'CONTINUATION_UNCLOSED_STARTED:' + node)
        require((item.get('status') == 'PASS') == (node in state['completed']),
                'CONTINUATION_JOURNAL_STATE_RECONCILIATION:' + node)
    pending = state['next_node']
    if pending in attempts:
        require(attempts[pending].get('status') == state['status'], 'CONTINUATION_PENDING_STATUS')
    elif state['status'] != 'PASS':
        require(False, 'CONTINUATION_FAILURE_WITHOUT_ATTEMPT')


def execute_nodes(o, ns, boundary, revalidate, heartbeat=None):
    """Dispatch only a prevalidated finite range; never calls frozen execute/main."""
    boundary.validate(o.st.d)
    start = boundary.nodes.index(o.st.d['next_node'])
    writer = ns['immutable_receipt']
    for node in boundary.nodes[start:]:
        if heartbeat is not None:
            heartbeat.update(phase=node, completed_nodes=len([n for n in boundary.nodes if n in o.st.d['completed']]))
        revalidate()
        require(o.st.d['next_node'] == node, 'CONTINUATION_DISPATCH_STATE')
        o.st.log(node, 'STARTED', run_id=o.id)
        try:
            try:
                result = o.runnode(node)
            except RuntimeError as exc:
                # E9 deliberately stops after packing. Completion here means only
                # that evidence preparation finished; F1 still consumes the review.
                if node != 'E9' or str(exc) != 'AWAITING_STAGE_B':
                    raise
                from D4_FIRST_ADMISSION_PREP import Reads
                with Reads() as proof:
                    for key in ('stage_b_pack', 'stage_b_orchestrator_package'):
                        meta = o.st.d[key]
                        proof.read(meta['path'], meta['sha256'])
                    proof.revalidate()
                result = {'evidence_prepared': True, 'review_required': True,
                          'stage_b_pack': o.st.d['stage_b_pack'],
                          'stage_b_orchestrator_package': o.st.d['stage_b_orchestrator_package']}
            if heartbeat is not None: heartbeat.check()
            # Publish evidence before the durable STATE advance. Receipt collisions block.
            writer(o.rd / ('RESULT_' + node + '.json'), ns['jb'](result))
            writer(o.rd / ('RECEIPT_' + node + '.json'), ns['jb']({
                'schema': 'TICKSTORE_NODE_RECEIPT_V001', 'node': node,
                'run_id': o.id, 'status': 'PASS', 'result_sha256': sha(ns['jb'](result))}))
            o.st.finish(node, 'PASS', result)
        except ns['SafeStopFlow']:
            # No skipped node on SAFE_STOP; freeze the exact node for reconciliation/resume.
            o.st.finish(node, 'SAFE_STOP', error='COOPERATIVE_STOP')
            return 130
        except BaseException as exc:
            # Preserve original failure even if STATE CAS itself cannot complete.
            try: o.st.finish(node, 'FAIL', error=type(exc).__name__ + ':' + str(exc))
            except BaseException as state_error:
                print('CONTINUATION_STATE_RECONCILIATION_REQUIRED=' + str(state_error), flush=True)
            raise
    return 0


def publish_stage(o, ns, boundary, admission):
    """Technical receipt derived from completed nodes and physical readback."""
    from D4_FIRST_ADMISSION_PREP import Reads
    with Reads() as proof:
        state_raw = proof.read(o.st.sp); state = strict_json(state_raw)
        require(state == o.st.d and state.get('status') == 'PASS'
                and state.get('next_node') == NEXT[boundary.stage], 'STAGE_FINAL_STATE_READBACK')
        journal_raw = proof.read(o.st.jp); validate_journal(journal_raw)
        results, evidence = closed_results(journal_raw, boundary.nodes, o.st.runs, proof.read)
        if boundary.stage == 'D5':
            cert = base64.b64decode(state['canary_canonical_cert'], validate=True)
            require(sha(cert) == results['D5']['cert_sha256'], 'D5_CERTIFICATE_READBACK')
        elif boundary.stage == 'CANARY':
            require(results['D9'] == {k: 'PASS' for k in ('R1', 'R2', 'R3', 'R4', 'R5')}, 'CANARY_CONTROLS_INCOMPLETE')
            require(results['D6'] == {'PASS': True} and results['D7'] == {'PASS': True}, 'CANARY_PRECHECKS')
            deep = results['E1'].get('deep', {})
            independent = results['E1'].get('independent', {})
            require(isinstance(deep, dict) and isinstance(independent, dict)
                    and deep.get('POST_FULL_AUDIT') == 'PASS'
                    and independent.get('schema') == 'POSTFULL_INDEPENDENT_VERIFIER_V001'
                    and independent.get('status') == 'PASS', 'CANARY_READBACK')
            # Both frozen verifiers must agree on the same actual source ledger,
            # aggregate row count, published manifest and namespace inventory.
            require(type(deep.get('days')) is int and deep['days'] == 1550
                    and type(deep.get('rows')) is int and deep['rows'] == 7049522162
                    and type(deep.get('namespace')) is int and deep['namespace'] == 3101
                    and type(independent.get('days')) is int and independent['days'] == deep['days']
                    and type(independent.get('rows')) is int and independent['rows'] == deep['rows']
                    and type(independent.get('namespace_files')) is int
                    and independent['namespace_files'] == deep['namespace']
                    and isinstance(deep.get('manifest_sha256'), str)
                    and len(deep['manifest_sha256']) == 64
                    and independent.get('manifest_sha256') == deep['manifest_sha256'],
                    'CANARY_INDEPENDENT_READBACK_MISMATCH')
        extra = {}
        stage = 'FULL_ADMISSION' if boundary.stage == 'FULL_ADMIT' else boundary.stage
        if boundary.stage == 'FULL_PREP':
            require(results['E9'].get('evidence_prepared') is True and results['E9'].get('review_required') is True,
                    'FULL_PREP_STAGE_B_NOT_PREPARED')
            # The actual frozen E3..E8 nodes already reject failed certifications and
            # simulations. Their closed results remain explicit evidence, not an audit.
            for key in ('stage_b_pack', 'stage_b_orchestrator_package'):
                meta = results['E9'][key]
                evidence.append({'path': meta['path'], 'sha256': meta['sha256']})
        if boundary.stage == 'FULL_ADMIT':
            require(results['F1'].get('FULL_GO') == 'PASS', 'FULL_STAGE_B_REVIEW_NOT_PASSED')
            evidence += [{'path': str(o.st.inbox/'STAGE_B_REVIEW_V001.txt'), 'sha256': sha((o.st.inbox/'STAGE_B_REVIEW_V001.txt').read_bytes())},
                         {'path': str(o.st.inbox/'FULL_GO.txt'), 'sha256': sha((o.st.inbox/'FULL_GO.txt').read_bytes())},
                         {'path': str(o.control/'PRODUCTION_FREEZE_V004R1.json'), 'sha256': results['F2']['freeze_sha256']}]
            extra = full_admission_facts(o, admission)
        for item in evidence: proof.read(item['path'], item['sha256'])
        proof.revalidate()
        return publish(stage, admission, o.rd, ns['immutable_receipt'],
                       {'STATE_AFTER.json': state_raw, 'JOURNAL_AFTER.jsonl': journal_raw}, evidence,
                       checks={k: True for k in REQUIRED_CHECKS[stage]},
                       extra={'state_after_sha256': sha(state_raw), **extra})


def full_admission_facts(o, admission):
    state = o.st.d
    sys.path.insert(0, str(Path(__file__).parent.parent/'full'))
    import tickstore_serial_runner as core
    import tickstore_full_multiwork as multi
    i = admission.instance; b = i['bindings']; limits = i['resources']
    contract, cert, ids = core.full_release_materials(Path(core.__file__).parent)
    days, months, ledger_sha = core.load_ledgers(Path(i['ledger_path']))
    core.validate_full_plan(days, months, ledger_sha, contract)
    actual = core.full_gate_bindings(*(Path(b[k+'_root']) for k in ('source','dest','scratch')), ids, contract)
    require(all(actual[k] == b.get(k) for k in actual if k not in ('schema','authorized')), 'FULL_PREP_BINDINGS')
    multi.choose_workers('AUTO', len(months), limits['max_workers'], limits['ram_target_percent'])
    require(o.eng.recovery_process_census()['known_recovery_supervisor_or_workers'] == 0, 'FULL_PREP_PROCESS_CENSUS')
    identities = {}
    for label in ('source', 'dest', 'scratch'):
        path = Path(b[label+'_root'])
        handle = admission.enter_context(o.eng.Win32Store().open(path, directory=True))
        identities[label] = handle.info()
        require(not (path/'TICKSTORE_WRITER.lock').exists(), 'FULL_PREP_WRITER_LOCK')
    vss = o.eng.NativeVSS(o.eng.Win32Store(), state['pprof'])
    try: vss.assert_present(state['G_PA'])
    finally: vss.close()
    extra = {'generation': state['G_PA'], 'vss_profile': state['pprof'], 'root_identities': identities}
    return extra


def run(a):
    refresh = a.stage == 'FULL_READMIT'
    close_only = getattr(a, 'close_only', False)
    require(not (refresh and close_only), 'READMISSION_NOT_CLOSURE')
    stage = 'FULL' if refresh else a.stage
    require(stage in RANGES, 'CONTINUATION_STAGE')
    require(os.name == 'nt' and ctypes.WinDLL('shell32').IsUserAnAdmin(), 'CONTINUATION_NATIVE_ELEVATION')
    require(os.environ.get('TICKSTORE_D4_RESUME_ENABLE') != '1', 'POST_D4_CANNOT_USE_D4_AUTHORITY')
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root/'adapter'))
    import runtime_locator_orchestrator_entry as entry
    import runtime_locator_adapter as adapter
    import D4_FIRST_ADMISSION_BOOTSTRAP as boot
    import D4_FIRST_ADMISSION_TRANSACTION as tx
    boundary = StageBoundary(stage, close_only=close_only)
    with ReleaseChain(a.chain_file, a.chain_sha256, a.b06_sha256, root,
                      until=PREVIOUS[stage][0]) as admission:
        instance = admission.instance; package = root/'recovery'
        # Same physical capture checks as the qualified first admission, no administrative issuer;
        # every effectful stage needs a CURRENT origin reconciliation (R44-B2C), and the policy may
        # have legitimately moved since admission: the verified identity is recorded, not pinned.
        capmod = boot.lib(admission.read(root/'control/POLICY_CAPTURE_BINDING.py'), root/'control/POLICY_CAPTURE_BINDING.py')
        policy_capture = boot.policy_current(admission, instance['policy_root'], getattr(a, 'policy_reconciliation', ''),
                                             getattr(a, 'policy_reconciliation_sha256', ''), capmod)
        config_path = package/'config/STAGE_A_SEALED_VALUES_V001.json'
        config_raw = admission.read(config_path, instance['config_sha256'])
        cfg = strict_json(config_raw)
        state_path = Path(cfg['control_root'])/'state/STATE.json'
        require(str(state_path.absolute()) == instance['state_path'], 'CONTINUATION_STATE_PATH')
        state_raw, state_ident = entry.read_pinned_regular(state_path, 'CONTINUATION_STATE')
        state = strict_json(state_raw); boundary.validate(state)
        if state['next_node'] == boundary.nodes[0] and state['status'] == 'PASS':
            require(sha(state_raw) == admission.receipts[PREVIOUS[stage][0]].get('state_after_sha256'),
                    'CONTINUATION_PREDECESSOR_STATE_DRIFT')
        journal = state_path.with_name('STATE_JOURNAL.jsonl')
        journal_raw, _ = entry.read_pinned_regular(journal, 'CONTINUATION_JOURNAL')
        last_closed_node(journal_raw, PREVIOUS[stage][1])
        # Failed or interrupted work needs reconciliation; never infer completion from STARTED.
        validate_stage_history(journal_raw, boundary, state)
        closed_results(journal_raw, tuple(n for n in boundary.nodes if n in state['completed']),
                       state_path.parent.parent/'runs', admission.read)
        d4 = admission.receipts['D4']
        binding_path = Path(d4['adapter_binding_path'])
        binding = strict_json(admission.read(binding_path, d4['adapter_binding_sha256']))
        locator_path = Path(d4['g_ca_receipt_path'])
        locator = strict_json(admission.read(locator_path, d4['g_ca_receipt_sha256']))
        adapter.validate_binding(binding); adapter.validate_locator_receipt(locator, binding)
        eraw = admission.read(package/'engine/tickstore_publisher_recovery_v004_release.py', binding['frozen_release_sha256'])
        oraw = admission.read(package/'modules/orchestrator.py', binding['frozen_orchestrator_sha256'])
        ns = load(oraw, package/'modules/orchestrator.py')
        admitted = entry.AdmittedStart(state_path, state_path.parent.parent, config_path,
                       config_raw, sha(config_raw), entry._ident(os.lstat(config_path)), state_raw, state_ident)
        entry.guard_frozen_state_reads(ns, admitted, state_validator=boundary.validate,
                                      transition_validator=boundary.transition)
        entry.pin_frozen_engine_load(ns, package/'engine/tickstore_publisher_recovery_v004_release.py', eraw)
        def with_locator(p):
            require(Path(p).resolve() == (package/'engine/tickstore_publisher_recovery_v004_release.py').resolve(), 'CONTINUATION_ENGINE_PATH')
            engine_ns = load(eraw, p)
            adapter.install_engine_namespace(engine_ns, binding, locator, state['G_CA'])
            return types.SimpleNamespace(**engine_ns)
        ns['load_engine'] = with_locator
        # The first admission materializes the binding with the real D4 descriptor.
        # Its directory also contains the hash-bound adapter used by child bundles.
        adapter.install_orchestrator_namespace(ns, binding, binding_path.parent, locator_path, post_d4=True)
        ns['immutable_receipt'] = adapter.make_no_clobber_receipt_writer(lambda why: require(False, why))
        if stage in ('FULL_ADMIT', 'FULL'):
            inbox = state_path.parent.parent/'inbox'
            for name in ('STAGE_B_REVIEW_V001.txt', 'FULL_GO.txt'):
                admission.read(inbox/name)
            for key in ('pb', 'pa', 'psb', 'psa'):
                admission.read(state[key])
            for key in ('stage_b_pack', 'stage_b_orchestrator_package'):
                meta = state[key]; admission.read(meta['path'], meta['sha256'])
        admission.revalidate()
        heartbeat = None
        outcome = 'FAILED'
        try:
            o = ns['O'](types.SimpleNamespace(package=str(package), python=sys.executable))
            sys.path.insert(0, str(root/'full'))
            from FULL_OBSERVABILITY import Heartbeat
            from tickstore_full_multiwork import _atomic_coordinator_state
            heartbeat = Heartbeat(o.rd/'STAGE_HEARTBEAT.json', _atomic_coordinator_state,
                dict(run_id=instance['run_id'], attempt_id=o.id, stage=a.stage,
                     code_manifest_sha256=admission.descriptor['code_manifest_sha256'],
                     instance_sha256=admission.descriptor['instance_sha256'])).start()
            heartbeat.update(phase='CLOSURE' if close_only else 'READMISSION' if refresh else 'ADMITTED',
                             total_nodes=len(boundary.nodes),
                             completed_nodes=len([n for n in boundary.nodes if n in state['completed']]))
            if close_only:
                if stage == 'FULL':
                    import FULL_LIFECYCLE as lifecycle
                    lifecycle.publish_completion(o, ns, admission, boundary.nodes)
                else:
                    publish_stage(o, ns, boundary, admission)
                outcome = 'FULL_COMPLETE' if stage == 'FULL' else 'STAGE_COMPLETE'
                return 0
            if refresh:
                import FULL_LIFECYCLE as lifecycle
                # Reconsume existing review and freeze bindings; no documents are generated.
                o.stageb()
                freeze = o.control/'PRODUCTION_FREEZE_V004R1.json'
                old = admission.receipts['FULL_ADMISSION']
                matching = [e for e in old['evidence'] if Path(e['path']) == freeze]
                require(len(matching) == 1, 'READMISSION_FREEZE_EVIDENCE')
                admission.read(freeze, matching[0]['sha256'])
                lifecycle.refresh_admission(o, ns, admission, full_admission_facts(o, admission), boundary.nodes)
                outcome = 'READMITTED_NOT_STARTED'
                return 0
            if stage == 'FULL':
                # Every launch, including a post-H retry, consumes a fresh receipt
                # for the exact current STATE. SAFE_STOP cannot reuse the old one.
                require(sha(state_raw) == admission.receipts['FULL_ADMISSION'].get('state_after_sha256'),
                        'FULL_CURRENT_STATE_REQUIRES_READMISSION')
                age = (time.time_ns() - admission.receipts['FULL_ADMISSION'].get('created_unix_ns', 0))/1e9
                require(0 <= age <= 300, 'FULL_ADMISSION_NOT_FRESH_300S')
                import FULL_LIFECYCLE as lifecycle
                sys.path.insert(0, str(root/'full'))
                full_admission_facts(o, admission)
                lifecycle.install(o, ns, admission, getattr(a, 'workers', 'AUTO'))
            code = execute_nodes(o, ns, boundary, admission.revalidate, heartbeat)
            if code == 0:
                heartbeat.update(phase='CLOSURE', completed_nodes=len(boundary.nodes))
                if stage == 'FULL':
                    lifecycle.publish_completion(o, ns, admission, boundary.nodes)
                else:
                    publish_stage(o, ns, boundary, admission)
                print('CONTINUATION_STAGE_PASS=' + a.stage + ' RUN_DIR=' + str(o.rd), flush=True)
                outcome = 'FULL_COMPLETE' if stage == 'FULL' else 'STAGE_COMPLETE'
            elif code == 130:
                outcome = 'SAFE_STOP'
            return code
        finally:
            try:
                if heartbeat is not None:
                    heartbeat.update(pipeline_complete=outcome == 'FULL_COMPLETE', phase=outcome)
                    heartbeat.close(outcome)
            finally:
                ns['_TICKSTORE_D4_ENTRY_RELEASE_STATE_BOUNDARY']()


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--stage', choices=(*RANGES, 'FULL_READMIT'), required=True)
    ap.add_argument('--close-only', action='store_true')
    for name in ('chain-file', 'chain-sha256', 'b06-sha256'): ap.add_argument('--' + name, required=True)
    # R45 G5: same inputs as FULL_RUNNER, so this direct entry is usable (current origin policy
    # reconciliation, worker request); the launcher route remains RUN_TICKSTORE_FULL.ps1.
    ap.add_argument('--policy-reconciliation', default='')
    ap.add_argument('--policy-reconciliation-sha256', default='')
    ap.add_argument('--workers', default='AUTO')
    try: return run(ap.parse_args(argv))
    except (RuntimeError, OSError, KeyError, ValueError, TypeError) as exc:
        print('CONTINUATION_BLOCKED=' + str(exc), flush=True); return 2


if __name__ == '__main__':
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log('STAGE_CONTINUATION', main))
