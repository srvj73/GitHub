"""Synthetic closed RETURN ZIP + FINAL ZIP for unit tests of the G5 producer/consumer.

UNIT FIXTURE ONLY.  The Windows strings below are fabricated so that the mechanics can be
exercised on any platform; they are never evidence.  Real evidence is the R44 RETURN ZIP.
"""
import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((R / 'candidate/control/QUALIFICATION_CONTRACT.json').read_bytes())
PS = '5.1.26100.9444'
PY = '3.14.7 (tags/v3.14.7:823f032, Aug  5 2026, 10:51:32) [MSC v.1944 64 bit (AMD64)]'
PLAT = 'Windows-11-10.0.26200-SP0'
TIME = (2026, 10, 14, 0, 0, 0)


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def j(obj):
    return (json.dumps(obj, indent=1, sort_keys=True) + '\n').encode('utf-8')


def zip_bytes(members):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in members.items():
            z.writestr(zipfile.ZipInfo(name, TIME), raw)
    return b.getvalue()


class NativeFixture:
    """Mutable description; make() materialises both ZIPs from the current state."""

    def __init__(self, qual_ns):
        self.q = qual_ns
        self.code = {'control/EXAMPLE.py': b'print("candidate")\n',
                     'g5proof/G5_PROOF_RUNNERS.py': b'# runner bytes (fixture)\n'}
        self.wanted = CONTRACT['required_tests']
        self.harness = {'schema': 'TICKSTORE_CDT15_EXECUTED_DELTA_V001', 'platform': PLAT, 'python': PY,
                        'native_windows': True, 'selection': 'NATIVE', 'tested_code_unchanged': True,
                        'production_execution': False, 'success': True, 'interruption': None,
                        'byte_revalidation_error': None,
                        'tests': [{'id': i, 'status': 'PASS'} for i in self.wanted],
                        'totals': {'tests_run': len(self.wanted), 'failures': 0, 'errors': 0, 'skips': 0},
                        'tests_expected': len(self.wanted), 'tests_not_run': 0, 'tests_interrupted': 0}
        self.log_ids = list(self.wanted)
        self.log_tail = '\n' + '-' * 70 + '\nRan %d tests in 12.345s\n\nOK\n' % len(self.wanted)
        self.precheck = {'platform': PLAT, 'powershell': PS, 'python': PY, 'elevated': True,
                         'symlink_privilege': 'PASS',
                         'volumes': {'C': {'filesystem': 'NTFS'}, 'D': {'filesystem': 'NTFS'}}}
        self.receipt_extra = {}
        self.run_id = 'R44_QUAL_20261014_120000_000_1234'
        self.proofs = {n: {} for n, s in qual_ns['TYPED_PROOFS'].items() if s['function']}
        self.proof_override = {}      # name -> receipt dict replacing the generated one
        self.extra_return = {}        # extra members (not in RETURN_MANIFEST unless listed)
        self.drop_manifest_entry = None
        self.empty_code_manifest = False
        self.tamper_final_member = False
        self.final_extra = {}         # FINAL members outside the candidate root (e.g. packaged tests)

    def final_zip(self):
        files = [] if self.empty_code_manifest else [
            {'path': p, 'bytes': len(b), 'sha256': h(b)} for p, b in sorted(self.code.items())]
        man = j({'schema': 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001', 'revision': 'CDT15_FIXTURE',
                 'root': 'implementation_v001/candidate', 'files': files})
        members = {'implementation_v001/RUNTIME_CODE_MANIFEST.json': man}
        for p, b in self.code.items():
            members['implementation_v001/candidate/' + p] = b + (b'#tampered\n' if self.tamper_final_member
                                                                  and p.endswith('EXAMPLE.py') else b'')
        members.update(self.final_extra)
        pm = j({'schema': 'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001',
                'files': [{'path': n, 'bytes': len(b), 'sha256': h(b)} for n, b in sorted(members.items())]})
        return zip_bytes(dict({'PACKAGE_MANIFEST.json': pm}, **members)), h(man)

    def receipt(self, name, final_sha, code_sha):
        spec = self.q['TYPED_PROOFS'][name]
        art_member = self.q['PROOF_PREFIX'] + name + '/ARTIFACT_%s.json' % name
        art = j({'proof': name, 'observation': 'fixture-' + name})
        r = {'schema': self.q['PROOF_RECEIPT_SCHEMA'], 'kind': spec['kind'], 'proof': name, 'status': 'PASS',
             'native_windows': True, 'platform': PLAT, 'production_execution': False,
             'code_manifest_sha256': code_sha, 'final_zip_sha256': final_sha, 'run_id': self.run_id,
             'runner': {'path': self.q['PROOF_RUNNER'], 'function': spec['function'],
                        'sha256': h(self.code['g5proof/G5_PROOF_RUNNERS.py'])},
             'scenario': 'fixture scenario ' + name, 'checks': dict.fromkeys(spec['checks'], 'PASS'),
             'artifacts': [{'member': art_member, 'sha256': h(art), 'bytes': len(art)}]}
        r.update(self.proofs.get(name, {}))
        return r, {art_member: art}

    def make(self, tmp, tag='F'):
        tmp = Path(tmp)
        final_raw, code_sha = self.final_zip()
        final_sha = h(final_raw)
        harness = dict(self.harness, code_manifest_sha256=self.harness.get('code_manifest_sha256', code_sha))
        log = ''.join('%s (%s) ... ok\n' % (i.split('.')[-1], i) for i in self.log_ids) + self.log_tail
        qr = {'schema': 'TICKSTORE_CDT15_WINDOWS_QUALIFICATION_RECEIPT_V003', 'mode': 'NATIVE_WINDOWS',
              'RUN_ID': self.run_id, 'SOURCE_SHA256': final_sha, 'RUNTIME_CODE_MANIFEST_SHA256': code_sha,
              'TESTED_CODE_EQUALS_PACKAGED_CODE': 'PASS_TESTS_EXECUTED_FROM_EXTRACTED_FINAL_PACKAGE',
              'PRODUCTION_MODIFIED': False, 'FULL_STARTED': False, 'PRECHECK': self.precheck}
        qr.update(self.receipt_extra)
        b1 = {'schema': 'TICKSTORE_CDT15_R44_B1_RESULT_V001', 'status': 'PASS',
              'counts': {'pass': len(self.wanted), 'expected_executed': len(self.wanted), 'non_pass': 0},
              'derived': {'tests_full_lifecycle.py': '29981D15', 'tests_delta.py': '2E95CADE'}}
        m = self.q['MEMBERS']
        members = {m['qual_receipt']: j(qr), m['harness_result']: j(harness),
                   m['tests_log']: log.replace('\n', '\r\n').encode('utf-8'), m['b1_result']: j(b1),
                   'RUN_LOG.txt': b'fixture run log\r\n'}
        for name in self.proofs:
            rec, arts = self.receipt(name, final_sha, code_sha)
            rec = self.proof_override.get(name, rec)
            members[self.q['PROOF_PREFIX'] + name + '/PROOF_RECEIPT.json'] = j(rec)
            members.update(arts)
        members.update(self.extra_return)
        listed = {k: v for k, v in members.items() if k != self.drop_manifest_entry}
        rm = j({'schema': self.q['RETURN_MANIFEST_SCHEMA'],
                'files': [{'path': n, 'bytes': len(b), 'sha256': h(b)} for n, b in sorted(listed.items())]})
        members[m['return_manifest']] = rm
        rz = tmp / ('QUAL_RETURN_%s.zip' % tag)
        fz = tmp / ('TICKSTORE_FULL_FINAL_%s.zip' % tag)
        rz.write_bytes(zip_bytes(members))
        fz.write_bytes(final_raw)
        return rz, fz, code_sha, final_sha


def load_consumer():
    raw = (R / 'candidate/control/FULL_QUALIFICATION_CONTRACT.py').read_bytes()
    ns = {'__name__': 'fixture_consumer'}
    exec(compile(raw, 'FULL_QUALIFICATION_CONTRACT.py', 'exec'), ns)
    return ns


def with_physical_powerloss_spec():
    """Hypothetical origin specification, used only to show the mechanics can accept."""
    g = load_consumer()
    g['TYPED_PROOFS'] = copy.deepcopy(g['TYPED_PROOFS'])
    g['TYPED_PROOFS']['CHECKPOINT_POWERLOSS_RECOVERY'] = {
        'kind': 'TICKSTORE_G5_PROOF_PHYSICAL_POWERLOSS_V001',
        'function': 'hypothetical_origin_specified_physical_proof', 'checks': ('hypothetical_physical_check',)}
    return g
