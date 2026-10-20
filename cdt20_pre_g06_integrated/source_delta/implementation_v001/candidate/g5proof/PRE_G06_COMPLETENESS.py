"""Post-native engineering closure. No origin decision or independent B06 verdict.

The implementer's source review and native negative tests are separate inputs.
The existing G5 producer still refuses absent native proof or mismatched bytes.
"""
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
for folder in ('control','full'):sys.path.insert(0,str(ROOT/folder))
import G5_FINAL_COMPLETENESS_PRODUCER as producer
import FULL_G5_COMPLETE_PROOF_GATE as gate
import FULL_CRASH_RECOVERY as R


# Adversarial suites whose native DELTA commit is required (never skipped).
# G0 reads this same tuple, so its pre-effect gate cannot drift from closure.
REQUIRED_DELTA=('test_cdt19_final_transport_closure.py','test_cdt19_native_campaign_contract.py',
                'test_cdt19_integrated_crash_recovery.py','test_cdt19_g6_ownership_closure.py',
                'test_cdt19_durable_barrier_contract.py','test_cdt19_r07_g3_g6_integrated_causality.py',
                'test_integrated_evidence_contract.py','test_g5_producer_consumer_roundtrip.py',
                'test_cdt20_pre_g06_integrated_closure.py')

# Each pre-B06 finding is bound to named native regressions: the defect is
# reproduced by a negative test and the corrected path by a positive one. A
# label in the adversarial attestation is not evidence; the sealed native log
# line '<test> (<module>.<class>.<test>) ... ok' is.
FINDINGS={
  'STATE_RECREATION':(
    ('DELTA_test_cdt19_integrated_crash_recovery.py','test_dead_attempt_closes_fail_without_advancing_or_recreating_state'),
    ('DELTA_test_cdt19_integrated_crash_recovery.py','test_state_drift_blocks'),
    ('DELTA_test_cdt19_durable_barrier_contract.py','test_deleted_marker_not_recreated'),
    ('SUITE_test_state_cas_recovery.py','test_08_state_matching_neither_blocks')),
  'CONFIG_TOCTOU':(
    ('SUITE_test_official_writer_effectful.py','test_37_hostile_swap_inside_replace_window_detected'),
    ('SUITE_test_official_writer_effectful.py','test_30_menu_drift_blocks_before_write'),
    ('SUITE_test_official_writer_effectful.py','test_35_installed_candidate_drift_blocks')),
  'CONCURRENT_RECEIPT_OVERWRITE':(
    ('SUITE_test_official_writer_effectful.py','test_20_concurrent_writer_is_refused_without_effect'),
    ('SUITE_test_official_writer_effectful.py','test_22_two_simultaneous_writer_processes_one_winner'),
    ('SUITE_test_cdt16_held_rename_failure.py','test_atomic_checkpoint_roundtrip_and_no_overwrite')),
  'FAILURE_AFTER_CHECKPOINT':(
    ('SUITE_test_state_cas_recovery.py','test_09_state_ahead_of_checkpoint_blocks'),
    ('SUITE_test_state_cas_recovery.py','test_02_r1_restores_the_confirmed_previous_state'),
    ('SUITE_test_cdt16_held_rename_failure.py','test_accepted_rename_checkpoints_and_blocks'),
    ('SUITE_test_cdt16_held_rename_failure.py','test_without_checkpoint_blocks'),
    ('DELTA_test_cdt19_integrated_crash_recovery.py','test_false_crash_blocks_before_state_and_journal_changes'))}


def verify_four_findings(native,result):
    """Bind every finding to closed native logs already bound by the result."""
    rows={}
    for finding,cases in FINDINGS.items():
        evidence=[]
        for key,test in cases:
            unit=result['tests'].get(key) if key.startswith('SUITE_') else result['additional_tests'].get(key)
            R.require(isinstance(unit,dict),'FINDING_UNIT_MISSING:'+finding+':'+key)
            log='LOGS/'+key+'.log'
            R.require(log in native,'FINDING_LOG_MISSING:'+finding+':'+key)
            raw=native[log]
            if key.startswith('SUITE_'):
                R.require(unit.get('sha256')==R.sha(raw),'FINDING_LOG_UNBOUND:'+finding+':'+key)
            line=re.compile(rb'(?m)^'+re.escape(test.encode('ascii'))+rb' \([A-Za-z0-9_.]+\.'+
                            re.escape(test.encode('ascii'))+rb'\) \.\.\. ok\r?$')
            R.require(len(line.findall(raw))==1,'FINDING_TEST_NOT_PASSED:'+finding+':'+test)
            R.require(re.search(rb'(?m)^OK\r?$',raw) is not None and b'FAILED (' not in raw,
                      'FINDING_LOG_NOT_CLOSED:'+finding+':'+key)
            evidence.append(dict(unit=key,test=test,log=log,log_sha256=R.sha(raw)))
        rows[finding]=dict(status='PASS_NATIVE_REGRESSION',evidence=evidence)
    return rows


def close(final_zip,native_zip,review_path,run_root):
    root=Path(run_root)
    R.core.strict_directory(root)
    code,members=producer.verify_final_zip(final_zip)
    package=producer.hash_path(final_zip);native_hash=producer.hash_path(native_zip)
    review=gate.strict(Path(review_path).read_bytes())
    R.require(review.get('schema')=='CDT19_IMPLEMENTER_SOURCE_REVIEW_V001'
              and review.get('status')=='SOURCE_REVIEW_COMPLETE_PENDING_NATIVE'
              and review.get('package_sha256')==package
              and review.get('code_manifest_sha256')==code
              and review.get('known_fixable_blockers')==[]
              and review.get('independent_b06_audit') is False,'SOURCE_REVIEW_BINDING')
    index={r['path']:r for r in gate.strict(members['implementation_v001/RUNTIME_CODE_MANIFEST.json'])['files']}
    result,units,native=gate.verify_native_campaign(Path(native_zip).read_bytes(),code,package,index,final_members=members)
    R.require(result['run_id']==root.name,'COMPLETENESS_RUN_BINDING')
    # Additional adversarial suites are not silently counted as contracted roles.
    # Each source/log/result/COMMIT is bound to this exact candidate here.
    refs=[]
    for name in REQUIRED_DELTA:
        key='DELTA_'+name;commit_name='COMMITS/'+key+'.json'
        R.require(commit_name in native,'COMPLETENESS_COMMIT_MISSING:'+key)
        obj=gate.strict(native[commit_name]);ran=result['additional_tests'].get(key)
        R.require(isinstance(ran,dict) and obj.get('result')==ran and ran.get('status')=='PASS'
                  and ran.get('exit_code')==0 and type(ran.get('test_count')) is int and ran['test_count']>0
                  and ran.get('failures')==0 and ran.get('errors')==0 and ran.get('skipped') is False
                  and obj.get('package_sha256')==package and obj.get('code_sha256')==code
                  and obj.get('own_descendants_final')==[],'COMPLETENESS_NEGATIVE_SUITE:'+key)
        R.require(ran.get('test_source_sha256')==R.sha(members['implementation_v001/tests/'+name]),
                  'COMPLETENESS_TEST_SOURCE:'+key)
        artifacts=obj.get('artifacts',[])
        R.require(bool(artifacts),'COMPLETENESS_ARTIFACTS:'+key)
        for ref in artifacts:gate._physical_ref(ref,native,'COMPLETENESS_ADVERSARIAL_ARTIFACT')
        log='LOGS/'+key+'.log'
        R.require(log in {r['member'] for r in artifacts},'COMPLETENESS_LOG_NOT_COMMITTED')
        raw=native[log]
        import re
        counts=re.findall(rb'(?m)^Ran (\d+) tests? in [^\r\n]+\r?$',raw)
        R.require(len(counts)==1 and int(counts[0])==ran['test_count']
                  and re.search(rb'(?m)^OK\r?$',raw) is not None,'COMPLETENESS_NATIVE_LOG')
        refs.append(dict(member=commit_name,sha256=R.sha(native[commit_name]),bytes=len(native[commit_name])))
    findings=verify_four_findings(native,result)
    out=root/'FINAL_G5'
    if out.exists():
        # Retain prior complete or interrupted assembly; no replay of native tests.
        previous=root/'INTERRUPTED_ATTEMPTS'/('FINAL_G5_'+uuid.uuid4().hex)
        previous.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(out),str(previous))
    inputs=root/('G5_ASSEMBLY_INPUTS_'+uuid.uuid4().hex);inputs.mkdir()
    instance=inputs/'INSTANCE.json';adverse=inputs/'ADVERSARIAL.json'
    R.publish(instance,dict(schema='TICKSTORE_FULL_INSTANCE_V001',code_manifest_sha256=code,
        run_id=root.name,qualification_scope='OWNED_ISOLATED_NTFS_PRE_B06',operational_authority=False,
        production_authorized=False,native_return_sha256=native_hash,run_root=str(root)))
    R.publish(adverse,dict(schema='TICKSTORE_FINAL_ADVERSARIAL_ENGINEERING_ATTESTATION_V001',
        status='PASS',known_blockers=[],candidate_sha256=package,code_manifest_sha256=code,
        native_g5_return_sha256=native_hash,legacy_technical_consumer_count=11,
        false_completeness_search='PASS',state_toctou_receipt_checkpoint_negative_controls='PASS',
        final_bytes_freeze='PASS',independent_b06_audit=False,scope='IMPLEMENTER_ENGINEERING_REVIEW',
        source_review_sha256=producer.hash_path(review_path),native_negative_commits=refs,
        four_pre_b06_findings=findings))
    result=producer.produce(final_zip,native_zip,instance,adverse,out)
    # Physical readback of every proof and all references, including five criteria.
    comp=gate.strict((out/'ENGINEERING_COMPLETENESS.json').read_bytes())
    R.require(set(comp['five_part_completeness'])==set(gate.FIVE),'COMPLETENESS_FIVE_SET')
    for row in comp['five_part_completeness'].values():
        raw=Path(row['path']).read_bytes();R.require(R.sha(raw)==row['sha256'],'COMPLETENESS_PART_READBACK')
        for ref in gate.strict(raw)['evidence']:
            R.require(producer.hash_path(ref['path'])==ref['sha256'],'COMPLETENESS_REFERENCE_READBACK')
    R.publish(out/'FOUR_PRE_B06_FINDINGS.json',dict(schema='CDT20_FOUR_PRE_B06_FINDINGS_NATIVE_V001',
        native_return_sha256=native_hash,code_manifest_sha256=code,final_package_sha256=package,findings=findings))
    result.update(engineering_five_part_completeness='PASS',independent_b06_audit=False,
                  four_pre_b06_findings='PASS_NATIVE_REGRESSION',
                  physical_powerloss='NOT_TESTED_PHYSICAL_POWERLOSS')
    R.publish(out/'FINAL_ENGINEERING_STATUS.json',result)
    return result
