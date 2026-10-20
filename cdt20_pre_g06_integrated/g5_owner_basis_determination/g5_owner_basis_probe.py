"""CDT20 G5_OWNER_BASIS_FINDING determination probe. SANDBOX, pure functions, NOT an owner decision.

Runs the ORIGINAL binder bytes (DC6182C9...) from the original inner package 6C952BD9...
Policy values are explicit synthetic placeholders: no policy/capture file is read.
Usage: python -I -B g5_owner_basis_probe.py <extracted-original-package-root> <historical-decision-out.json>
"""
import copy,hashlib,importlib.util,json,sys,zipfile
from pathlib import Path
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2])
H=lambda b:hashlib.sha256(b).hexdigest().upper()
binder_path=root/'implementation_v001/candidate/control/ORIGIN_DECISION_BINDER.py'
assert H(binder_path.read_bytes())=='DC6182C9CA339EECCA63EFDEAAC9EDF0FBCBA0F8C762E29B4D7410F2D13F23AB'
spec=importlib.util.spec_from_file_location('original_binder',binder_path);B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
fixture=root/'implementation_v001/tests/fixtures/CDT17_G5_OWNER_R2_SCOPED_IMMUTABLE_REFERENCE.zip'
assert H(fixture.read_bytes())=='3C5A99EF3F3714FDEF4DC1B8FD264736DE3E63122B0016F68827FAC6E8DA6D49'
with zipfile.ZipFile(fixture) as z:historical_raw=z.read('EVIDENCE/G5_OWNER_STAGE_DECISION.json')
historical=json.loads(historical_raw)
CUR=dict(code='CC7726742DD5DD72788AC6FD6D4CC1860DB7123F88599188E0A2B559F7FA3ECA',
         final='6C952BD9D0C0B7E13D7B5AD01E1563DA8AFC2FB641262835A0AABBC49778C064',
         instance='EBCC5F39F627C3AF26532ACBB625B20A829B15F00AA1AF6A6E2269FDE0A375FD')
SYN={'schema':'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001','master_sha256':'SYNTHETIC_PLACEHOLDER_NOT_POLICY_M',
     'head_sha256':'SYNTHETIC_PLACEHOLDER_NOT_POLICY_H','revision_id':'SYNTHETIC_PLACEHOLDER_NOT_POLICY_R',
     'reconciliation_sha256':'SYNTHETIC_PLACEHOLDER_NOT_POLICY_C'}
def verify(obj_or_raw,code=CUR['code'],final=CUR['final'],instance=CUR['instance'],policy=SYN,sha=None):
    raw=obj_or_raw if isinstance(obj_or_raw,bytes) else json.dumps(obj_or_raw,sort_keys=True).encode()
    try:
        B.verify_decision(raw,sha or H(raw),stage='G5',code_sha=code,final_package_sha=final,instance_sha=instance,
                          policy_capture=policy,predecessor_hashes={})
        return 'ACCEPTED_BY_PURE_VERIFIER'
    except B.DecisionBlocked as e:return 'BLOCKED:'+str(e)
def current(**edits):
    """A NEW synthetic record shaped as a current FINAL owner decision (never issued, never written as authority)."""
    d=copy.deepcopy(historical)
    d.update(code_manifest_sha256=CUR['code'],final_package_sha256=CUR['final'],instance_sha256=CUR['instance'],
             decision_id='SYNTHETIC_PROBE_NOT_ISSUED',policy={k:SYN[k] for k in ('master_sha256','head_sha256','revision_id','reconciliation_sha256')})
    d.pop('scope_limit',None);d.update(edits);return d
cases=[]
def case(name,expected,result,meaning):
    ok=result.startswith(expected);cases.append(dict(case=name,expected=expected,observed=result,match=ok,meaning=meaning));assert ok,(name,result)
# 1. The exact historical 16/10 decision bytes cannot be rebound to the current candidate.
case('historical_16_10_bytes_against_current_identities','BLOCKED:DECISION_BINDING:code_manifest_sha256',
     verify(historical_raw),'stale decision cannot authorize 6C952BD9: hash binding (checked before any policy field), independent of issuer_basis')
# 2. Relabelling only the identity fields of the old record = a NEW record with a new SHA.
case('relabelled_historical_record_old_sha_supplied','BLOCKED:DECISION_SHA256_SUPPLIED_SEPARATELY',
     verify(current(decision_id=historical['decision_id']),sha=H(historical_raw)),
     'editing the 16/10 record to current hashes changes its bytes; the operator-pinned SHA no longer matches')
# 3. A new current FINAL decision is expressible with the role basis.
case('new_current_decision_role_basis_16_10','ACCEPTED',verify(current()),
     'a NEW owner record binding current code/final/instance is accepted; issuer_basis names the role basis, not the decision date')
case('new_current_decision_role_basis_relabelled_20_10','BLOCKED:G5_OWNER_SCOPE_AND_NO_FAKE_INDEPENDENCE',
     verify(current(issuer_basis='EXPLICIT_OWNER_DECLARATION_CHAT_20261020')),
     'an unrecognised role basis is refused: designating a different G5 issuer basis is an origin/titular governance act')
for name,edit,exp in [('basis_missing',dict(issuer_basis=None),'BLOCKED:G5_OWNER_SCOPE'),
                      ('owner_claims_b06_independence',dict(owner_is_independent_b06_auditor=True),'BLOCKED:G5_OWNER_SCOPE'),
                      ('chatgpt_origin_as_g5_issuer',dict(issuer='CHATGPT_ORIGIN'),'BLOCKED:DECISION_SCHEMA_ISSUER'),
                      ('implementer_as_issuer',dict(implementation_participant_is_issuer=True),'BLOCKED:DECISION_IMPLEMENTER_CANNOT_ISSUE'),
                      ('reject_decision',dict(decision='REJECT'),'BLOCKED:ORIGIN_DECISION_REJECT'),
                      ('wrong_final_package',dict(final_package_sha256=historical['final_package_sha256']),'BLOCKED:DECISION_BINDING:final_package_sha256'),
                      ('wrong_instance',dict(instance_sha256='0'*64),'BLOCKED:DECISION_BINDING:instance_sha256'),
                      ('open_blocker',dict(blockers=['X']),'BLOCKED:DECISION_BLOCKERS'),
                      ('missing_check',dict(checks={'features_implemented':True}),'BLOCKED:DECISION_CHECKS')]:
    case(name,exp,verify(current(**edit)),'negative control')
case('wrong_separate_sha','BLOCKED:DECISION_SHA256_SUPPLIED_SEPARATELY',verify(current(),sha='F'*64),'second-channel pin required')
# 4. Downstream FINAL consumer independently requires current identities (source reference).
gate=(root/'implementation_v001/candidate/control/FULL_G5_COMPLETE_PROOF_GATE.py').read_text()
assert 'A historical G5 scoped owner decision is not re-issued for the final package.' in gate
assert '"ORIGIN_DECISION_OLD_OR_WRONG_CODE"' in gate
report=dict(schema='CDT20_G5_OWNER_BASIS_DETERMINATION_PROBE_V001',binder_sha256=H(binder_path.read_bytes()),
            fixture_sha256=H(fixture.read_bytes()),historical_decision_sha256=H(historical_raw),
            synthetic=True,owner_authorization_issued=False,policy_read=False,cases=cases,
            all_cases_match=all(c['match'] for c in cases))
out.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
for c in cases:print(('OK  ' if c['match'] else 'BAD ')+c['case']+' -> '+c['observed'])
print('ALL_CASES_MATCH=%s'%report['all_cases_match'])
