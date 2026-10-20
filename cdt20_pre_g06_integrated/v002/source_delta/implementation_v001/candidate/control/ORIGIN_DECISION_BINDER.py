"""R44-B2D: bind an ORIGIN-ISSUED G5/B07 decision into a TICKSTORE_STAGE_RECEIPT_V001 (copy only).

This module never decides.  It materializes a stage receipt only from a decision record
issued by the stage authority (G5: OWNER_RELEASE_AUTHORITY; B07: CHATGPT_ORIGIN), whose SHA-256 is supplied separately by the operator (same
trust pattern as the independent B06 digest), after re-verifying every binding against
physical bytes.  A REJECT, a missing field, a drifted digest or any blocker refuses to
write anything.  No administrative OWNER_GATE is created, required or accepted, and the
implementer can never be the issuer.

Bindings (all mandatory): stage, policy capture (master/head/revision + origin
reconciliation), code manifest, FINAL package, instance, evidence (re-read and hashed),
blockers (empty), predecessor receipt chain and, for B07, the independent B06 verdict.

The policy identity is never taken from the caller (R45, B2D analogue of B07-PROVENANCE-01):
materialize() verifies the capture folder and the origin reconciliation record itself through
POLICY_PHYSICAL_VERIFY (sealed reader, sealed verifier module, separately supplied digest).
Only native protected reads produce an operational WINDOWS_PRODUCTION receipt; any other read
mode yields environment FIXTURE_NOT_NATIVE, which FULL_RELEASE_CHAIN never consumes.
Operator entry: python ORIGIN_DECISION_BINDER.py --stage G5|B07 ... (see main()).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

DECISION_SCHEMA = 'TICKSTORE_ORIGIN_STAGE_DECISION_V001'
STAGE_RECEIPT_SCHEMA = 'TICKSTORE_STAGE_RECEIPT_V001'
MATERIALIZABLE = ('G5', 'B07')
PREDECESSORS = {'G5': (), 'B07': ('G5', 'B06')}
REQUIRED_CHECKS = {
    'G5': ('features_implemented', 'blockers_closed', 'tested_equals_packaged', 'adversarial_completeness', 'byte_freeze'),
    'B07': ('native_windows', 'physical_policy_capture', 'state_continuity', 'vss_identity', 'negative_controls',
            'process_tree_cleanup'),
}
# Evidence roles the binder re-reads and checks semantically, per stage.
REQUIRED_EVIDENCE = {'G5': ('G5_EVIDENCE_PACK', 'ENGINEERING_COMPLETENESS', 'G5_STAGE_COMPLETENESS', 'G5_INTEGRATION_SOURCE', 'G5_INTEGRATION_MANIFEST', 'NATIVE_RETURN_ZIP'),
                     'B07': ('B07_TECHNICAL_RECEIPT', 'NATIVE_RETURN_ZIP')}
HEX64 = re.compile('[0-9A-F]{64}')
HERE = Path(__file__).resolve().parent
OPERATIONAL_ENVIRONMENT = 'WINDOWS_PRODUCTION'
FIXTURE_ENVIRONMENT = 'FIXTURE_NOT_NATIVE'


def verified_policy(policy_root, reconciliation, reconciliation_sha256, now=None):
    """Physically verified capture plus the receipt environment it allows."""
    spec = importlib.util.spec_from_file_location('b2d_policy_physical_verify', HERE / 'POLICY_PHYSICAL_VERIFY.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    capture, mode, findings = mod.verify_policy(policy_root, reconciliation, reconciliation_sha256, now=now)
    hard = [f for f in findings if f != mod.NOT_NATIVE]
    _require(capture is not None and not hard, 'DECISION_POLICY_NOT_VERIFIED:' + ';'.join(hard or findings))
    return capture, (OPERATIONAL_ENVIRONMENT if mode == mod.NATIVE_MODE and not findings else FIXTURE_ENVIRONMENT)


class DecisionBlocked(RuntimeError):
    pass


def _require(ok, reason):
    if not ok:
        raise DecisionBlocked(reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def _hex(value, label):
    _require(isinstance(value, str) and HEX64.fullmatch(value) is not None, 'DECISION_DIGEST:' + label)
    return value


def _strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            _require(k not in out, 'DECISION_JSON_DUPLICATE_KEY:' + str(k))
            out[k] = v
        return out
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def _canonical(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


# The G5 issuer basis is an explicit owner declaration in chat, identified by its
# calendar date. Owner-authorized on 2026-10-20: any valid declaration date is
# accepted (2026-10-16 is no longer the only basis). Arbitrary labels stay refused;
# the decision itself remains pinned by current hashes and a second-channel SHA.
OWNER_BASIS = re.compile(r'EXPLICIT_OWNER_DECLARATION_CHAT_([0-9]{8})')


def _owner_basis(value):
    match = OWNER_BASIS.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return False
    import datetime
    try:
        datetime.date(int(match.group(1)[:4]), int(match.group(1)[4:6]), int(match.group(1)[6:]))
    except ValueError:
        return False
    return True


def verify_decision(decision_raw, decision_sha256, *, stage, code_sha, final_package_sha, instance_sha,
                    policy_capture, predecessor_hashes, b06_sha=None, b06_verdict_sha=None):
    """Pure verification of the origin decision bindings; returns the parsed decision."""
    _require(stage in MATERIALIZABLE, 'DECISION_STAGE_NOT_MATERIALIZABLE:' + str(stage))
    _require(_sha(decision_raw) == _hex(decision_sha256, 'decision'), 'DECISION_SHA256_SUPPLIED_SEPARATELY')
    d = _strict_json(decision_raw)
    _require(d.get('schema') == DECISION_SCHEMA and d.get('issuer') == ('OWNER_RELEASE_AUTHORITY' if stage == 'G5' else 'CHATGPT_ORIGIN'), 'DECISION_SCHEMA_ISSUER')
    if stage == 'G5':
        _require(_owner_basis(d.get('issuer_basis')) and d.get('owner_is_independent_b06_auditor') is False, 'G5_OWNER_SCOPE_AND_NO_FAKE_INDEPENDENCE')
    _require(d.get('implementation_participant_is_issuer') is False, 'DECISION_IMPLEMENTER_CANNOT_ISSUE')
    _require(d.get('administrative_owner_gate') is False, 'DECISION_NO_ADMINISTRATIVE_OWNER_GATE')
    _require(d.get('stage') == stage, 'DECISION_STAGE')
    _require(d.get('decision') in ('PASS', 'REJECT'), 'DECISION_VALUE')
    _require(d['decision'] == 'PASS', 'ORIGIN_DECISION_REJECT')
    _require(isinstance(d.get('decision_id'), str) and d['decision_id'].strip(), 'DECISION_ID')
    for key, want in (('code_manifest_sha256', code_sha), ('final_package_sha256', final_package_sha),
                      ('instance_sha256', instance_sha)):
        _require(d.get(key) == _hex(want, key), 'DECISION_BINDING:' + key)
    pol = d.get('policy') if isinstance(d.get('policy'), dict) else {}
    _require(isinstance(policy_capture, dict) and policy_capture.get('schema') == 'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001',
             'DECISION_POLICY_CAPTURE_REQUIRED')
    for key in ('master_sha256', 'head_sha256', 'revision_id', 'reconciliation_sha256'):
        _require(pol.get(key) == policy_capture.get(key) and bool(pol.get(key)), 'DECISION_POLICY_BINDING:' + key)
    names = PREDECESSORS[stage]
    _require(isinstance(predecessor_hashes, dict) and tuple(predecessor_hashes) == names, 'DECISION_PREDECESSOR_SET')
    _require(d.get('predecessors') == {n: _hex(predecessor_hashes[n], n) for n in names}, 'DECISION_PREDECESSORS')
    previous = predecessor_hashes[names[-1]] if names else None
    _require(d.get('previous_receipt_sha256') == previous, 'DECISION_PREVIOUS_RECEIPT')
    if stage == 'B07':
        # Two distinct B06 digests (R45 B2D-B06): the B06 STAGE RECEIPT (chain predecessor) and the
        # independent B06 VERDICT text that the B07 producer and the D4 transaction bind.
        _require(d.get('b06_receipt_sha256') == _hex(b06_sha, 'b06') and predecessor_hashes['B06'] == b06_sha,
                 'DECISION_B06_BINDING')
        _require(d.get('b06_verdict_sha256') == _hex(b06_verdict_sha, 'b06_verdict'), 'DECISION_B06_VERDICT_BINDING')
        _require(d.get('b06_independent') is True, 'DECISION_B06_INDEPENDENCE')
    _require(d.get('blockers') == [], 'DECISION_BLOCKERS')
    checks = d.get('checks')
    _require(isinstance(checks, dict) and set(checks) == set(REQUIRED_CHECKS[stage])
             and all(v is True for v in checks.values()), 'DECISION_CHECKS')
    ev = d.get('evidence')
    _require(isinstance(ev, list) and ev, 'DECISION_EVIDENCE_REQUIRED')
    roles = [e.get('role') for e in ev if isinstance(e, dict)]
    _require(len(roles) == len(ev) and len(set(roles)) == len(roles) and set(REQUIRED_EVIDENCE[stage]) <= set(roles),
             'DECISION_EVIDENCE_ROLES')
    shas = [e.get('sha256') for e in ev]
    _require(all(isinstance(s, str) and HEX64.fullmatch(s) for s in shas) and len(set(shas)) == len(shas),
             'DECISION_EVIDENCE_DIGESTS')
    return d


def _check_evidence_semantics(stage, role, raw, *, code_sha, final_package_sha, b06_sha, b06_verdict_sha=None):
    if role == 'NATIVE_RETURN_ZIP':
        return
    if role == 'G5_INTEGRATION_MANIFEST':
        from pathlib import PurePosixPath
        obj = _strict_json(raw)
        if obj.get('binding_mode') == 'FINAL_CANDIDATE':
            # Explicit new code manifest and FINAL package binding. Legacy
            # scoped manifests remain historical and cannot assert this role.
            _require(obj.get('schema') == 'CDT17_G5_FINAL_INTEGRATED_CODE_MANIFEST_V001'
                     and obj.get('code_manifest_sha256') == code_sha
                     and obj.get('final_package_sha256') == final_package_sha,
                     'DECISION_FINAL_INTEGRATION_IDENTITY')
            rows = obj.get('files')
            _require(isinstance(rows,list) and len(rows) >= 6 and
                     len({e.get('path') for e in rows if isinstance(e,dict)}) == len(rows),
                     'DECISION_FINAL_INTEGRATION_MANIFEST_SET')
            root=HERE.parent
            for e in rows:
                name=e.get('path')
                _require(isinstance(name,str) and name.startswith(('control/','SUPPORT/'))
                         and '..' not in PurePosixPath(name).parts and
                         ':' not in name and '\\' not in name,
                         'DECISION_FINAL_INTEGRATION_MANIFEST_PATH')
                body=(root/name).read_bytes()
                _require(len(body)==e.get('bytes') and _sha(body)==e.get('sha256'),
                         'DECISION_FINAL_INTEGRATION_MODULE_SHA:'+name)
            _require({'control/FULL_RELEASE_CHAIN.py','control/FULL_G5_COMPLETE_PROOF_GATE.py',
                      'control/ORIGIN_DECISION_BINDER.py','control/G5_C6_FORMAL_CONTRACT.py'}
                     <= {e['path'] for e in rows}, 'DECISION_FINAL_INTEGRATION_REQUIRED_MODULES')
            return
        _require(obj.get('schema') == 'CDT17_G5_FORMAL_INTEGRATED_CODE_MANIFEST_V001',
                 'DECISION_INTEGRATION_MANIFEST_SCHEMA')
        root=HERE.parent
        declared=obj.get('files')
        _require(isinstance(declared,list) and len(declared)>=6 and
                 len({e.get('path') for e in declared})==len(declared),
                 'DECISION_INTEGRATION_MANIFEST_EXACT_SET')
        for e in declared:
            name=e.get('path')
            _require(isinstance(name,str) and name.startswith(('CONTROL/','SUPPORT/'))
                     and '..' not in PurePosixPath(name).parts, 'DECISION_INTEGRATION_MANIFEST_PATH')
            body=(root/name).read_bytes()
            _require(len(body)==e.get('bytes') and _sha(body)==e.get('sha256'),
                     'DECISION_INTEGRATION_MODULE_SHA:'+name)
        _require(obj.get('original_full_zip_sha256') == '2A522667D2592E848E055C8374C9453660D774276ED4522DF82B15F30523F660',
                 'DECISION_INTEGRATION_PARENT_IDENTITY')
        return
    if role == 'G5_INTEGRATION_SOURCE':
        expected = (HERE/'G5_C6_FORMAL_CONTRACT.py').read_bytes()
        _require(raw == expected, 'DECISION_INTEGRATION_SOURCE_NOT_TESTED_BYTES')
        return
    obj = _strict_json(raw)
    if role == 'G5_EVIDENCE_PACK':
        _require(obj.get('schema') == 'TICKSTORE_G5_EVIDENCE_PACK_V001' and obj.get('completeness_status') in ('COMPLETE_SCOPED', 'COMPLETE_FINAL')
                 and obj.get('known_blockers') == [] and obj.get('consumer_self_check') in ('ACCEPTS_FORMAL_B1_SCOPED', 'ACCEPTS_FINAL_CANDIDATE')
                 and obj.get('code_manifest_sha256') == code_sha and obj.get('gate_verdict_issued') is False,
                 'DECISION_EVIDENCE_G5_PACK')
    elif role == 'ENGINEERING_COMPLETENESS':
        if obj.get('schema') == 'TICKSTORE_ENGINEERING_COMPLETENESS_V003' and obj.get('status') == 'COMPLETE':
            _require(obj.get('known_blockers') == [] and obj.get('code_manifest_sha256') == code_sha
                     and obj.get('full_started') is False and obj.get('formal_audit_started') is False,
                     'DECISION_FINAL_COMPLETENESS_BINDING')
        else:
            _require(obj.get('schema') == 'TICKSTORE_ENGINEERING_COMPLETENESS_V002' and obj.get('status') == 'INCOMPLETE'
                     and obj.get('known_blockers') == ['FULL_CANDIDATE_COMPLETENESS_NOT_YET_PROVEN']
                     and obj.get('g5_stage_scope_status') == 'COMPLETE_SCOPED' and obj.get('code_manifest_sha256') == code_sha,
                     'DECISION_EVIDENCE_COMPLETENESS')
            _require(obj.get('full_started') is False and obj.get('gate_verdict_issued') is False, 'DECISION_G5_SCOPED_ONLY')
    elif role == 'G5_STAGE_COMPLETENESS':
        _require(obj.get('schema') == 'TICKSTORE_CDT17_G5_STAGE_COMPLETENESS_V001' and
                 obj.get('original_full_sha256') == final_package_sha,
                 'DECISION_G5_STAGE_PACKAGE_BINDING')
        if obj.get('status') == 'COMPLETE_SCOPED':
            _require(obj.get('full_candidate_completeness') == 'NOT_PROVEN' and
                     obj.get('formal_gate_verdict_issued') is False, 'DECISION_G5_STAGE_SCOPED_INTEGRITY')
        else:
            _require(obj.get('status') == 'COMPLETE_FINAL' and
                     obj.get('full_candidate_completeness') == 'PASS', 'DECISION_G5_STAGE_FINAL_INTEGRITY')
    elif role == 'G5_INTEGRATION_SOURCE':
        # Guarded by the origin decision role+hash, verified at the evidence loop.
        _require(len(raw) > 100 and b'def verify_provenance' in raw and b'COMPLETE_SCOPED' in raw,
                 'DECISION_G5_INTEGRATION_CODE_INVALID')
    elif role == 'B07_TECHNICAL_RECEIPT':
        _require(obj.get('schema') == 'TICKSTORE_B07_TECHNICAL_RECEIPT_V001' and obj.get('status') == 'PASS'
                 and obj.get('platform') == 'WINDOWS_NTFS_PS51' and obj.get('code_manifest_sha256') == code_sha
                 and obj.get('review_verdict_sha256') == b06_verdict_sha
                 and obj.get('b06_stage_receipt_sha256') == b06_sha
                 and obj.get('produced_after_independent_b06') is True, 'DECISION_EVIDENCE_B07_RECEIPT')


def _qualification_contract():
    spec = importlib.util.spec_from_file_location('b2d_full_qualification_contract', HERE / 'FULL_QUALIFICATION_CONTRACT.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _check_native_chain(stage, bodies, *, code_sha, final_package_sha, instance_sha=None, evidence_paths=None, read=None, decision_raw=None, g5_base=None):
    """G11: G4 is a deliberate PRE-CHAIN stage without its own stage receipt; its proof is the closed
    native RETURN ZIP itself.  G5 is materialized only on that exact ZIP: closed RETURN_MANIFEST, a native
    QUAL receipt bound to these FINAL/code bytes, and the same ZIP and QUAL receipt that the engineering
    completeness names as its native provenance.  B07 binds the RETURN ZIP its technical receipt names."""
    zraw = bodies['NATIVE_RETURN_ZIP']
    if stage == 'B07':
        b07 = _strict_json(bodies['B07_TECHNICAL_RECEIPT'])
        _require(b07.get('return_zip_sha256') == _sha(zraw), 'DECISION_B07_RETURN_ZIP_NOT_THE_TECHNICAL_RECEIPT_ZIP')
        return
    # G5 formal-B1 evidence is a NEW scoped contract. The old B1 R44 harness is
    # deliberately absent: never invent RESULT.json/TESTS.log or 126 new executions.
    comp = _strict_json(bodies['ENGINEERING_COMPLETENESS'])
    pack = _strict_json(bodies['G5_EVIDENCE_PACK'])
    stage_obj = _strict_json(bodies['G5_STAGE_COMPLETENESS'])
    if comp.get('schema') == 'TICKSTORE_ENGINEERING_COMPLETENESS_V003' and comp.get('status') == 'COMPLETE':
        # A FINAL G5 decision must contain the exact role set the operational
        # FULL_RELEASE_CHAIN later consumes, not only the six legacy scoped roles.
        from FULL_G5_COMPLETE_PROOF_GATE import validate_g5_complete_proof, ROLES, G5Incomplete
        required = set(ROLES) - {'ORIGIN_DECISION'}
        _require(required <= set(bodies) and decision_raw is not None, 'DECISION_FINAL_PROOFS_MISSING')
        _require(read is not None and evidence_paths is not None, 'DECISION_FINAL_PINNED_READER_MISSING')
        all_bodies = dict(bodies, ORIGIN_DECISION=decision_raw)
        role_records=[]
        for role in ROLES:
            if role == 'ORIGIN_DECISION':
                continue
            raw=all_bodies[role]
            role_records.append({'role':role,'path':evidence_paths[role], 'sha256':_sha(raw)})
        role_records.append({'role':'ORIGIN_DECISION', 'path':'DECISION_SOURCE_ONLY', 'sha256':_sha(decision_raw)})
        def checked_read(path, claimed):
            if path == 'DECISION_SOURCE_ONLY':
                raw=decision_raw
            else:
                raw=read(path)
            _require(_sha(raw) == claimed, 'DECISION_FINAL_PINNED_SHA')
            return raw
        preview = {'stage':'G5','status':'PASS','environment':'WINDOWS_PRODUCTION',
                   'code_manifest_sha256':code_sha,'instance_sha256':instance_sha,
                   'full_candidate_completeness':'PASS','final_package_sha256':final_package_sha,
                   'origin_decision_sha256':_sha(decision_raw),'evidence':role_records}
        try:
            validate_g5_complete_proof(preview, code_sha, instance_sha, checked_read)
        except (G5Incomplete, OSError, ValueError, KeyError, TypeError) as error:
            raise DecisionBlocked('DECISION_FINAL_G5_PHYSICAL_PROOF:'+str(error)) from error
        return
    _require(comp.get('status') == 'INCOMPLETE', 'DECISION_FALSE_FULL_COMPLETENESS')
    _require(stage_obj.get('g4_return_sha256') == _sha(zraw) and
             stage_obj.get('original_full_sha256') == final_package_sha,
             'DECISION_G5_SOURCE_BINDING')
    _require(pack.get('g5_stage_completeness_sha256') == _sha(bodies['G5_STAGE_COMPLETENESS']),
             'DECISION_G5_PACK_STAGE_BINDING')
    _require(pack.get('code_manifest_sha256') == code_sha, 'DECISION_G5_CODE_BINDING')
    _require(g5_base is not None, 'DECISION_G5_STAGED_INPUTS_REQUIRED')
    from G5_C6_FORMAL_CONTRACT import verify_provenance
    import importlib.util
    spec=importlib.util.spec_from_file_location('cdt17_g5_formal_qualifier',HERE/'FULL_QUALIFICATION_CONTRACT.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    from pathlib import Path as _Path
    delta = _strict_json((_Path(g5_base)/'DELTA_QUALIFICATION.json').read_bytes())
    # The real G5 physical contract re-opens FIVE exact upstream archives.
    try:
        mod.evaluate_formal_g5_stage(comp, pack, stage_obj, g5_base, delta)
    except (ValueError, OSError, KeyError) as exc:
        raise DecisionBlocked('DECISION_G5_FORMAL_PHYSICAL_CONTRACT:'+str(exc)) from exc
    # Closing proof remains origin-controlled and requires complete upstream files.
    # No automatic gate PASS is issued by a builder or by this preflight.


def materialize(decision_path, decision_sha256, *, stage, code_sha, final_package_sha, instance_sha, policy_root,
                policy_reconciliation, policy_reconciliation_sha256, predecessor_hashes, evidence_paths, out_path,
                b06_sha=None, b06_verdict_sha=None, b06_receipt_path=None, read=None, now=None):
    """Write the stage receipt (no-clobber) only if the origin decision binds everything."""
    read = read or (lambda p: Path(p).read_bytes())
    policy_capture, environment = verified_policy(policy_root, policy_reconciliation, policy_reconciliation_sha256, now=now)
    raw = read(decision_path)
    d = verify_decision(raw, decision_sha256, stage=stage, code_sha=code_sha, final_package_sha=final_package_sha,
                        instance_sha=instance_sha, policy_capture=policy_capture,
                        predecessor_hashes=predecessor_hashes, b06_sha=b06_sha, b06_verdict_sha=b06_verdict_sha)
    if stage == 'B07':
        # The B06 stage receipt itself must cite the verdict text as evidence.
        _require(b06_receipt_path is not None, 'DECISION_B06_RECEIPT_REQUIRED')
        b06_raw = read(b06_receipt_path)
        _require(_sha(b06_raw) == b06_sha, 'DECISION_B06_RECEIPT_SHA256')
        b06_obj = _strict_json(b06_raw)
        _require(b06_obj.get('stage') == 'B06' and b06_obj.get('status') == 'PASS'
                 and b06_obj.get('implementation_participant') is False, 'DECISION_B06_RECEIPT_CONTENT')
        _require(any(isinstance(e, dict) and e.get('sha256') == b06_verdict_sha for e in b06_obj.get('evidence') or []),
                 'DECISION_B06_RECEIPT_DOES_NOT_CITE_VERDICT')
    _require(isinstance(evidence_paths, dict) and set(evidence_paths) == {e['role'] for e in d['evidence']},
             'DECISION_EVIDENCE_FILES_SET')
    evidence = []; bodies = {}
    for e in d['evidence']:
        body = read(evidence_paths[e['role']])
        _require(_sha(body) == e['sha256'], 'DECISION_EVIDENCE_SHA256:' + e['role'])
        _check_evidence_semantics(stage, e['role'], body, code_sha=code_sha, final_package_sha=final_package_sha,
                                  b06_sha=b06_sha, b06_verdict_sha=b06_verdict_sha)
        bodies[e['role']] = body
        evidence.append({'path': str(Path(evidence_paths[e['role']]).absolute()), 'sha256': e['sha256'], 'role': e['role']})
    if stage == 'G5' and _strict_json(bodies['ENGINEERING_COMPLETENESS']).get('status') == 'COMPLETE':
        from FULL_G5_COMPLETE_PROOF_GATE import ROLES
        _require((set(ROLES)-{'ORIGIN_DECISION'}) <= set(bodies), 'DECISION_FINAL_REQUIRED_ROLES')
    _check_native_chain(stage, bodies, code_sha=code_sha, final_package_sha=final_package_sha,
                        instance_sha=instance_sha, evidence_paths=evidence_paths, read=read, decision_raw=raw,
                        g5_base=Path(evidence_paths['G5_EVIDENCE_PACK']).parent if stage == 'G5' else None)
    evidence.append({'path': str(Path(decision_path).absolute()), 'sha256': decision_sha256, 'role': 'ORIGIN_DECISION'})
    receipt = {'schema': STAGE_RECEIPT_SCHEMA, 'stage': stage, 'status': 'PASS', 'environment': environment,
               'code_manifest_sha256': code_sha, 'instance_sha256': instance_sha,
               'previous_receipt_sha256': d['previous_receipt_sha256'], 'blockers': [],
               'checks': {k: True for k in REQUIRED_CHECKS[stage]}, 'evidence': evidence,
               'origin_decision_sha256': decision_sha256, 'origin_decision_id': d['decision_id'],
               'final_package_sha256': final_package_sha, 'policy': dict(d['policy']),
               'policy_verification': {'read_mode': policy_capture['read_mode'],
                                       'binding_module_sha256': policy_capture['binding_module_sha256'],
                                       'verified_by': 'POLICY_CAPTURE_BINDING.verify_capture'},
               'materialized_by': 'ORIGIN_DECISION_BINDER_COPY_ONLY', 'decision_owner': d['issuer'],
               'implementation_participant_is_issuer': False}
    if stage == 'G5':
        engineering = _strict_json(bodies['ENGINEERING_COMPLETENESS'])
        if engineering.get('schema') == 'TICKSTORE_ENGINEERING_COMPLETENESS_V003' and engineering.get('status') == 'COMPLETE':
            receipt['full_candidate_completeness'] = 'PASS'
    if stage == 'B07':
        receipt['b06_receipt_sha256'] = b06_sha
        receipt['b06_verdict_sha256'] = b06_verdict_sha
    raw_out = _canonical(receipt)
    out = Path(out_path)
    _require(not os.path.lexists(out), 'STAGE_RECEIPT_EXISTS')
    with open(out, 'xb') as f:
        f.write(raw_out); f.flush(); os.fsync(f.fileno())
    _require(out.read_bytes() == raw_out, 'STAGE_RECEIPT_READBACK')
    return {'path': str(out.absolute()), 'sha256': _sha(raw_out), 'stage': stage, 'environment': environment}


def _file_sha(path):
    return _sha(Path(path).read_bytes())


def main(argv=None):
    """Operator entry: identities are hashed from the physical files; trust anchors are supplied separately."""
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--stage', required=True, choices=MATERIALIZABLE)
    ap.add_argument('--decision', required=True)
    ap.add_argument('--decision-sha256', required=True)
    ap.add_argument('--code-manifest', required=True)
    ap.add_argument('--final-zip', required=True)
    ap.add_argument('--instance', required=True)
    ap.add_argument('--policy-root', required=True)
    ap.add_argument('--policy-reconciliation', required=True)
    ap.add_argument('--policy-reconciliation-sha256', required=True)
    ap.add_argument('--predecessor', action='append', default=[], help='STAGE=RECEIPT_PATH, in chain order')
    ap.add_argument('--b06-receipt', default=None, help='B06 stage receipt (B07 only); its digest is computed')
    ap.add_argument('--b06-verdict-sha256', default=None, help='digest of the independent B06 verdict text (B07 only)')
    ap.add_argument('--evidence', action='append', default=[], help='ROLE=PATH')
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    try:
        preds = {}
        for item in a.predecessor:
            name, _, path = item.partition('=')
            _require(name and path and name not in preds, 'CLI_PREDECESSOR:' + item)
            preds[name] = _file_sha(path)
        evidence = {}
        for item in a.evidence:
            role, _, path = item.partition('=')
            _require(role and path and role not in evidence, 'CLI_EVIDENCE:' + item)
            evidence[role] = path
        r = materialize(a.decision, a.decision_sha256.upper(), stage=a.stage, code_sha=_file_sha(a.code_manifest),
                        final_package_sha=_file_sha(a.final_zip), instance_sha=_file_sha(a.instance),
                        policy_root=a.policy_root, policy_reconciliation=a.policy_reconciliation,
                        policy_reconciliation_sha256=a.policy_reconciliation_sha256.upper(), predecessor_hashes=preds,
                        evidence_paths=evidence, out_path=a.out,
                        b06_sha=_file_sha(a.b06_receipt) if a.b06_receipt else None,
                        b06_verdict_sha=a.b06_verdict_sha256.upper() if a.b06_verdict_sha256 else None,
                        b06_receipt_path=a.b06_receipt)
    except (DecisionBlocked, OSError, ValueError, KeyError) as exc:
        print('ORIGIN_DECISION_BINDER=BLOCKED REASON=%s:%s' % (type(exc).__name__, exc))
        return 2
    print('ORIGIN_DECISION_BINDER=MATERIALIZED STAGE=%s ENVIRONMENT=%s RECEIPT_SHA256=%s PATH=%s'
          % (r['stage'], r['environment'], r['sha256'], r['path']))
    return 0 if r['environment'] == OPERATIONAL_ENVIRONMENT else 3


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log('ORIGIN_DECISION_BINDER', main))
