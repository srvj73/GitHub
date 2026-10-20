"""Synthetic V002 producer/consumer end-to-end tests, NOT native qualification."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
for name in ('g5proof','control','full'):sys.path.insert(0,str(ROOT/'candidate'/name))
import PRE_G06_COMPLETENESS as F
import PRE_G06_CAMPAIGN as C
import FULL_CRASH_RECOVERY as R
import FULL_G5_COMPLETE_PROOF_GATE as G
import test_cdt19_final_transport_closure as T
import test_cdt17_final_g5_complete_proof_gate as old_fixture


def archive(members):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(members.items()):z.writestr(n,b)
    return out.getvalue()


class IntegratedFive(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.root=base/'R08_Q1_20261019165536_ff043e3870e0';self.root.mkdir()
        prior=old_fixture.ClosedFixture();prior.generate()
        with zipfile.ZipFile(io.BytesIO(prior.objects['FINAL_PACKAGE_ZIP'])) as z:
            packaged={n:z.read(n) for n in z.namelist()}
        needed=('test_cdt19_final_transport_closure.py','test_cdt19_native_campaign_contract.py',
                'test_cdt19_integrated_crash_recovery.py','test_cdt19_g6_ownership_closure.py',
                'test_cdt19_durable_barrier_contract.py','test_cdt19_r07_g3_g6_integrated_causality.py',
                'test_integrated_evidence_contract.py','test_g5_producer_consumer_roundtrip.py',
                'test_cdt20_pre_g06_integrated_closure.py')
        for name in needed:packaged['implementation_v001/tests/'+name]=(ROOT/'tests'/name).read_bytes()
        packaged['PACKAGE_MANIFEST.json']=R.encoded(dict(schema='TICKSTORE_FINAL_PACKAGE_MANIFEST_V001',
            files=[dict(path=n,sha256=R.sha(b),bytes=len(b)) for n,b in sorted(packaged.items()) if n!='PACKAGE_MANIFEST.json']))
        self.final=base/'FINAL.zip';self.final.write_bytes(archive(packaged));pack=R.sha(self.final.read_bytes())
        code=R.sha(packaged['implementation_v001/RUNTIME_CODE_MANIFEST.json'])
        with zipfile.ZipFile(io.BytesIO(prior.objects['NATIVE_RETURN_ZIP'])) as z:
            native={n:z.read(n) for n in z.namelist()}
        x=T.ElevenArchive();x.setUp();self.addCleanup(x.doCleanups)
        x.dossier['code_manifest_sha256']=code
        for row in x.dossier['consumers']:
            raw=packaged['implementation_v001/candidate/'+row['source_path']];h=R.sha(raw);row['source_sha256']=h
            for k in ('execution_witness','internal_branch_execution','code_path_review'):
                obj=json.loads((x.ev/row[k]['member']).read_bytes());obj['source_sha256']=h;row[k]=x.put_json(obj)
        (x.ev/'ELEVEN_CONSUMERS.json').write_bytes(R.encoded(x.dossier))
        ref=C.project_consumer_refs(x.campaign)
        native.update({p.relative_to(x.campaign).as_posix():p.read_bytes() for p in (x.campaign/'EVIDENCE/PRE_B06').rglob('*') if p.is_file()})
        result=json.loads(native['ENGINEERING_RESULT.json'])
        result.update(schema='CDT19_PRE_B06_NATIVE_ENGINEERING_V002',status='PASS_NATIVE_INTEGRATED_PRE_B06',
          run_id=self.root.name,final_zip_sha256=pack,pre_b06_11_receipt=ref,
          pre_b06_11_evidence_class='ENGINEERING_READINESS_NOT_PRODUCTION',additional_tests={})
        result['tests'].pop('LEGACY_11_CHAIN')
        result['tests']['PRE_B06_11_CHAIN']=dict(status='PASS_PRE_B06_ENGINEERING',exit_code=0,receipt=ref)
        summary=T.causal_fixture();prefix='WORK/G3_G6_NATIVE/'
        native[prefix+'G3_G6_NATIVE_SCENARIOS.json']=R.encoded(summary)
        source_refs=[dict(member=prefix+'G3_G6_NATIVE_SCENARIOS.json',sha256=R.sha(native[prefix+'G3_G6_NATIVE_SCENARIOS.json']),
                          bytes=len(native[prefix+'G3_G6_NATIVE_SCENARIOS.json']))]
        for name in G.PROOFS:
            member='EVIDENCE/PROOFS/'+name+'/PROOF_RECEIPT.json';obj=json.loads(native[member]);obj['final_zip_sha256']=pack
            if name in ('D4_REAL_ISOLATED_PATH_NATIVE','STAGE_B_REAL_ISOLATED_PATH_NATIVE'):
                obj.update(boundary_scope='OWNED_ISOLATED_NTFS_PRE_B06',operational_authority=False,protected_effects=False,
                     real_packaged_code_invoked=True,isolated_physical_readback=True,protected_inventory_unchanged=True)
            if name in ('PROCESS_TREE_CRASH_CONTAINMENT','SAFE_STOP_RESUME_ROW_GROUP','POWERLOSS_EMULATED'):
                evidence='EVIDENCE/PROOFS/'+name+'/NATIVE_CAUSAL_EVIDENCE.json'
                native[evidence]=R.encoded(dict(schema='CDT19_SCOPED_NATIVE_PROOF_PROJECTION_V002',proof=name,summary=summary,
                      code_manifest_sha256=code,final_zip_sha256=pack,operational_authority=False,physical_files=source_refs))
                obj['artifacts']=[dict(member=evidence,sha256=R.sha(native[evidence]),bytes=len(native[evidence]))]
            native[member]=R.encoded(obj)
        # Synthetic lines for the four pre-B06 findings; the native campaign log
        # must carry them as real unittest results for the same exact names.
        finding_lines={}
        for cases in F.FINDINGS.values():
            for key,test in cases:
                finding_lines.setdefault(key,b'')
                finding_lines[key]+=('%s (fixture.Case.%s) ... ok\n'%(test,test)).encode('ascii')
        for key,record in result['tests'].items():
            if key in finding_lines:
                # Bind the role's own log, then expose it under the unit-key name
                # the native campaign writes (LOGS/<key>.log).
                own='LOGS/'+record['log'].replace('\\','/').split('/')[-1]
                raw=finding_lines[key]+native[own];native[own]=raw;native['LOGS/'+key+'.log']=raw
                record['sha256']=R.sha(raw)
        for name in needed:
            key='DELTA_'+name;log='LOGS/'+key+'.log'
            raw=finding_lines.get(key,b'')+b'CONTRACT FIXTURE ONLY\nRan 1 test in 0.001s\n\nOK\n';native[log]=raw
            ran=dict(status='PASS',exit_code=0,test_count=1,failures=0,errors=0,skipped=False,
                     test_source_sha256=R.sha(packaged['implementation_v001/tests/'+name]))
            result['additional_tests'][key]=ran
            native['COMMITS/'+key+'.json']=R.encoded(dict(result=ran,package_sha256=pack,code_sha256=code,own_descendants_final=[],
                      artifacts=[dict(member=log,sha256=R.sha(raw),bytes=len(raw))]))
        native['ENGINEERING_RESULT.json']=R.encoded(result)
        live=json.loads(native['LIVE_STATUS.json']);live.update(status=result['status']);native['LIVE_STATUS.json']=R.encoded(live)
        self.native_members=native;self.native=base/'NATIVE.zip';self.native.write_bytes(archive(native))
        self.review=base/'REVIEW.json';self.review.write_bytes(R.encoded(dict(schema='CDT19_IMPLEMENTER_SOURCE_REVIEW_V001',
             status='SOURCE_REVIEW_COMPLETE_PENDING_NATIVE',package_sha256=pack,code_manifest_sha256=code,
             known_fixable_blockers=[],independent_b06_audit=False)))

    def close(self):return F.close(self.final,self.native,self.review,self.root)
    def test_contract_all_five_and_no_origin_authority(self):
        result=self.close();self.assertEqual(result['engineering_five_part_completeness'],'PASS')
        self.assertEqual(result['g5'],'NOT_ISSUED');self.assertEqual(result['b06'],'NOT_STARTED')
        self.assertEqual(len(list((self.root/'FINAL_G5/FIVE_PART_PROOFS').glob('*.json'))),5)
        self.assertFalse(list(self.root.rglob('ORIGIN_DECISION*')))
        findings=R.read(self.root/'FINAL_G5/FOUR_PRE_B06_FINDINGS.json')[0]
        self.assertEqual(set(findings['findings']),set(G.NEGATIVE_CONTROLS))
        self.assertEqual(result['four_pre_b06_findings'],'PASS_NATIVE_REGRESSION')
    def test_missing_native_finding_regression_prevents_g5(self):
        key='SUITE_test_official_writer_effectful.py';log='LOGS/'+key+'.log'
        result=json.loads(self.native_members['ENGINEERING_RESULT.json'])
        own='LOGS/'+result['tests'][key]['log'].replace('\\','/').split('/')[-1]
        for name in {log,own}:
            self.native_members[name]=self.native_members[name].replace(b'test_37_hostile_swap_inside_replace_window_detected (',b'test_37_x (')
        result['tests'][key]['sha256']=R.sha(self.native_members[log])
        self.native_members['ENGINEERING_RESULT.json']=R.encoded(result)
        self.native.write_bytes(archive(self.native_members))
        with self.assertRaisesRegex(Exception,'FINDING_TEST_NOT_PASSED:CONFIG_TOCTOU'):self.close()
        self.assertFalse((self.root/'FINAL_G5').exists())
    def test_changed_native_negative_log_prevents_g5(self):
        self.native_members['LOGS/DELTA_test_cdt19_final_transport_closure.py.log']=b'FAILED'
        self.native.write_bytes(archive(self.native_members))
        with self.assertRaisesRegex(Exception,'COMPLETENESS_ADVERSARIAL_ARTIFACT'):self.close()
        self.assertFalse((self.root/'FINAL_G5').exists())
    def test_foreign_source_review_prevents_g5(self):
        obj=json.loads(self.review.read_bytes());obj['package_sha256']='F'*64;self.review.write_bytes(R.encoded(obj))
        with self.assertRaisesRegex(Exception,'SOURCE_REVIEW_BINDING'):self.close()
    def test_missing_causal_file_prevents_all_five(self):
        del self.native_members['WORK/G3_G6_NATIVE/G3_G6_NATIVE_SCENARIOS.json']
        self.native.write_bytes(archive(self.native_members))
        with self.assertRaisesRegex(Exception,'NATIVE_CAUSAL_SUMMARY_MISSING'):self.close()
    def test_interrupted_assembly_is_preserved(self):
        out=self.root/'FINAL_G5';out.mkdir();(out/'partial').write_bytes(b'preserve')
        self.close()
        kept=list((self.root/'INTERRUPTED_ATTEMPTS').glob('FINAL_G5_*/partial'))
        self.assertEqual(len(kept),1);self.assertEqual(kept[0].read_bytes(),b'preserve')


if __name__=='__main__':unittest.main(verbosity=2)
