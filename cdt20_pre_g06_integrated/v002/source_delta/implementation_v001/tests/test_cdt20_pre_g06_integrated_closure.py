"""CDT20 integrated closure contracts. Synthetic inputs only, NOT native evidence."""
import datetime
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import zipfile

ROOT=Path(__file__).resolve().parents[1]
for name in ('g5proof','control','full'):sys.path.insert(0,str(ROOT/'candidate'/name))
import PRE_G06_CAMPAIGN as C
import PRE_G06_COMPLETENESS as F
import FULL_CRASH_RECOVERY as R
import FULL_G5_COMPLETE_PROOF_GATE as G


def native_logs():
    """Closed unittest logs carrying exactly the regressions bound to each finding."""
    lines={}
    for cases in F.FINDINGS.values():
        for key,test in cases:
            module=key.split('_',1)[1][:-3]
            lines.setdefault(key,[]).append('%s (%s.Case.%s) ... ok'%(test,module,test))
    native={};result={'tests':{},'additional_tests':{}}
    for key,rows in lines.items():
        raw=('\r\n'.join(rows)+'\r\n\r\n'+'-'*70+'\r\nRan %d tests in 0.010s\r\n\r\nOK\r\n'%len(rows)).encode('ascii')
        native['LOGS/'+key+'.log']=raw
        if key.startswith('SUITE_'):result['tests'][key]=dict(status='PASS_NATIVE_SCOPED',sha256=R.sha(raw))
        else:result['additional_tests'][key]=dict(status='PASS',test_count=len(rows))
    return native,result


class FourFindings(unittest.TestCase):
    def setUp(self):self.native,self.result=native_logs()

    def test_all_four_bound_to_native_regressions(self):
        rows=F.verify_four_findings(self.native,self.result)
        self.assertEqual(set(rows),{'STATE_RECREATION','CONFIG_TOCTOU','CONCURRENT_RECEIPT_OVERWRITE','FAILURE_AFTER_CHECKPOINT'})
        self.assertEqual(set(F.FINDINGS),set(G.NEGATIVE_CONTROLS))
        for row in rows.values():
            self.assertEqual(row['status'],'PASS_NATIVE_REGRESSION');self.assertTrue(row['evidence'])

    def rewrite(self,key,old,new):
        log='LOGS/'+key+'.log';self.native[log]=self.native[log].replace(old,new)
        if key in self.result['tests']:self.result['tests'][key]['sha256']=R.sha(self.native[log])

    def test_missing_regression_line_rejected(self):
        self.rewrite('SUITE_test_official_writer_effectful.py',b'test_37_hostile_swap_inside_replace_window_detected (','test_37_removed ('.encode())
        with self.assertRaisesRegex(Exception,'FINDING_TEST_NOT_PASSED:CONFIG_TOCTOU'):F.verify_four_findings(self.native,self.result)

    def test_failed_regression_rejected(self):
        self.rewrite('SUITE_test_state_cas_recovery.py',b'test_09_state_ahead_of_checkpoint_blocks) ... ok',
                     b'test_09_state_ahead_of_checkpoint_blocks) ... FAIL')
        with self.assertRaisesRegex(Exception,'FINDING_TEST_NOT_PASSED:FAILURE_AFTER_CHECKPOINT'):
            F.verify_four_findings(self.native,self.result)

    def test_unclosed_log_rejected(self):
        self.rewrite('DELTA_test_cdt19_integrated_crash_recovery.py',b'\r\nOK\r\n',b'\r\nFAILED (failures=1)\r\n')
        with self.assertRaisesRegex(Exception,'FINDING_LOG_NOT_CLOSED'):F.verify_four_findings(self.native,self.result)

    def test_suite_log_not_bound_by_result_rejected(self):
        self.native['LOGS/SUITE_test_cdt16_held_rename_failure.py.log']+=b'\r\n'
        with self.assertRaisesRegex(Exception,'FINDING_LOG_UNBOUND'):F.verify_four_findings(self.native,self.result)

    def test_duplicated_line_is_not_two_passes(self):
        key='SUITE_test_official_writer_effectful.py';log='LOGS/'+key+'.log'
        line=[l for l in self.native[log].split(b'\r\n') if l.startswith(b'test_20_')][0]
        self.rewrite(key,line,line+b'\r\n'+line)
        with self.assertRaisesRegex(Exception,'FINDING_TEST_NOT_PASSED:CONCURRENT_RECEIPT_OVERWRITE'):
            F.verify_four_findings(self.native,self.result)

    def test_missing_unit_rejected(self):
        del self.result['additional_tests']['DELTA_test_cdt19_durable_barrier_contract.py']
        with self.assertRaisesRegex(Exception,'FINDING_UNIT_MISSING:STATE_RECREATION'):
            F.verify_four_findings(self.native,self.result)

    def test_completeness_requires_this_suite_natively(self):
        self.assertIn('test_cdt20_pre_g06_integrated_closure.py',F.REQUIRED_DELTA)
        self.assertTrue(set(F.REQUIRED_DELTA)<=set(C.EXTRA))
        self.assertIn('test_cdt20_pre_g06_integrated_closure.py',C.EXTRA)


class Heartbeat(unittest.TestCase):
    now=datetime.datetime(2026,10,20,15,0,0,tzinfo=datetime.timezone.utc)

    def test_within_native_baseline(self):
        line=C.heartbeat_line('G3_G6_NATIVE',11.7,3,'36/38',(),self.now)
        for field in ('ACTIVE_TEST=G3_G6_NATIVE','UNIT_ELAPSED_S=11','OWNED_PIDS=3','PROGRESS_COMMITTED=36/38',
                      'UNIT_ETA_S=300','CAMPAIGN_ETA_S=300','ETA_BASIS=R08_1219_NATIVE_BASELINE',
                      'ETA_AS_OF=2026-10-20T15:00:00Z'):
            self.assertIn(field,line.split())

    def test_exceeded_baseline_is_unknown_not_zero(self):
        line=C.heartbeat_line('SUITE_test_state_cas_recovery.py',400,1,'1/38',('G3_G6_NATIVE',),self.now).split()
        self.assertIn('UNIT_ETA_S=UNKNOWN',line);self.assertIn('CAMPAIGN_ETA_S=UNKNOWN',line)
        self.assertIn('ETA_BASIS=UNIT_EXCEEDED_NATIVE_BASELINE',line)

    def test_unbaselined_unit_never_gets_invented_eta(self):
        new='DELTA_test_cdt20_pre_g06_integrated_closure.py'
        self.assertNotIn(new,C.UNIT_BASELINE_S)
        line=C.heartbeat_line('PRE_B06_11_CHAIN',4,2,'30/38',(new,'G3_G6_NATIVE'),self.now).split()
        self.assertIn('CAMPAIGN_ETA_S=UNKNOWN',line);self.assertIn('CAMPAIGN_ETA_OBSERVED_PART_S=321',line)
        self.assertIn('UNITS_WITHOUT_BASELINE=1',line)
        self.assertIn('UNIT_ETA_S=UNKNOWN',C.heartbeat_line(new,0,1,'0/1',(),self.now).split())


class ReturnBound(unittest.TestCase):
    def test_bound_is_resource_limit_and_still_enforced(self):
        self.assertGreaterEqual(G.NATIVE_ZIP_MAX_UNCOMPRESSED,1024**3)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('a.bin',b'x'*4096)
        with mock.patch.object(G,'NATIVE_ZIP_MAX_UNCOMPRESSED',1024):
            with self.assertRaisesRegex(Exception,'NATIVE_ZIP_BOUNDS'):G.native_zip_members(out.getvalue())
        self.assertEqual(G.native_zip_members(out.getvalue()),{'a.bin':b'x'*4096})


class OwnerBasis(unittest.TestCase):
    """Owner-authorized 2026-10-20: any valid owner declaration date; every other guard unchanged."""
    def setUp(self):
        import hashlib,json
        import ORIGIN_DECISION_BINDER as B
        self.B=B;self.H=lambda b:hashlib.sha256(b).hexdigest().upper();self.json=json
        self.ids=dict(code='A'*64,final='B'*64,instance='C'*64)
        self.policy={'schema':'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001','master_sha256':'SYNTHETIC_M',
                     'head_sha256':'SYNTHETIC_H','revision_id':'SYNTHETIC_R','reconciliation_sha256':'SYNTHETIC_C'}
        self.d={'schema':B.DECISION_SCHEMA,'issuer':'OWNER_RELEASE_AUTHORITY',
                'issuer_basis':'EXPLICIT_OWNER_DECLARATION_CHAT_20261020','owner_is_independent_b06_auditor':False,
                'implementation_participant_is_issuer':False,'administrative_owner_gate':False,'stage':'G5',
                'decision':'PASS','decision_id':'SYNTHETIC_UNIT_NOT_ISSUED','code_manifest_sha256':'A'*64,
                'final_package_sha256':'B'*64,'instance_sha256':'C'*64,
                'policy':{k:self.policy[k] for k in ('master_sha256','head_sha256','revision_id','reconciliation_sha256')},
                'predecessors':{},'previous_receipt_sha256':None,'blockers':[],
                'checks':{k:True for k in B.REQUIRED_CHECKS['G5']},
                'evidence':[{'role':r,'sha256':('%X'%n)*64} for n,r in enumerate(B.REQUIRED_EVIDENCE['G5'],1)]}
    def verify(self,sha=None,final='B'*64,**edits):
        d=dict(self.d,**edits);raw=self.json.dumps(d,sort_keys=True).encode()
        return self.B.verify_decision(raw,sha or self.H(raw),stage='G5',code_sha=self.ids['code'],final_package_sha=final,
                                      instance_sha=self.ids['instance'],policy_capture=self.policy,predecessor_hashes={})

    def test_current_owner_declaration_accepted(self):
        self.assertEqual(self.verify()['issuer_basis'],'EXPLICIT_OWNER_DECLARATION_CHAT_20261020')

    def test_historical_declaration_still_accepted(self):
        self.verify(issuer_basis='EXPLICIT_OWNER_DECLARATION_CHAT_20261016')

    def test_arbitrary_or_malformed_basis_rejected(self):
        for basis in ('FICTION',None,'',20261020,'EXPLICIT_OWNER_DECLARATION_CHAT_2026102',
                      'EXPLICIT_OWNER_DECLARATION_CHAT_20261020X','EXPLICIT_OWNER_DECLARATION_CHAT_20261332',
                      'EXPLICIT_OWNER_DECLARATION_CHAT_20260230','x EXPLICIT_OWNER_DECLARATION_CHAT_20261020',
                      'EXPLICIT_OWNER_DECLARATION_CHAT_20261020\n','EXPLICIT_OWNER_DECLARATION_CHAT_２０２６１０２０'):
            with self.subTest(basis=basis),self.assertRaisesRegex(self.B.DecisionBlocked,'G5_OWNER_SCOPE'):
                self.verify(issuer_basis=basis)

    def test_other_guards_unchanged(self):
        for edits,code in ((dict(owner_is_independent_b06_auditor=True),'G5_OWNER_SCOPE'),
                           (dict(issuer='CHATGPT_ORIGIN'),'DECISION_SCHEMA_ISSUER'),
                           (dict(implementation_participant_is_issuer=True),'DECISION_IMPLEMENTER_CANNOT_ISSUE'),
                           (dict(administrative_owner_gate=True),'DECISION_NO_ADMINISTRATIVE_OWNER_GATE'),
                           (dict(decision='REJECT'),'ORIGIN_DECISION_REJECT'),
                           (dict(instance_sha256='0'*64),'DECISION_BINDING:instance_sha256'),
                           (dict(blockers=['X']),'DECISION_BLOCKERS')):
            with self.subTest(edits=edits),self.assertRaisesRegex(self.B.DecisionBlocked,code):self.verify(**edits)

    def test_stale_package_and_wrong_pin_rejected(self):
        with self.assertRaisesRegex(self.B.DecisionBlocked,'DECISION_BINDING:final_package_sha256'):
            self.verify(final='2A522667D2592E848E055C8374C9453660D774276ED4522DF82B15F30523F660')
        with self.assertRaisesRegex(self.B.DecisionBlocked,'DECISION_SHA256_SUPPLIED_SEPARATELY'):self.verify(sha='F'*64)


if __name__=='__main__':unittest.main(verbosity=2)
