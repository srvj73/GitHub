"""Consume hash-bound historical baseline plus delta proof of final bytes.

This validator issues no qualification, completeness receipt or audit verdict.
Historical tests are evidence about their own bytes and are never recounted as
tests executed on the new candidate.

B2-G5-01 (origin audit 20261013): structure alone is not provenance.  When the
contract requires the typed G5 target proofs, the delta must carry a native
provenance block and this consumer re-reads the physical bytes itself: the closed
native RETURN ZIP (harness RESULT.json, TESTS.log, QUAL_RECEIPT, B1 result, return
manifest, typed proof receipts and their artifacts) and the FINAL package with the
complete runtime code manifest.  Declared booleans never substitute for those bytes.
"""
import collections
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

HEX64 = re.compile('[0-9A-F]{64}')
PROVENANCE_SCHEMA = 'TICKSTORE_G5_NATIVE_PROVENANCE_V001'
PROOF_RECEIPT_SCHEMA = 'TICKSTORE_G5_TARGET_PROOF_RECEIPT_V001'
POWERLOSS_EMULATED_KIND = 'TICKSTORE_G5_POWERLOSS_EMULATED_V001'
HARNESS_SCHEMA = 'TICKSTORE_CDT15_EXECUTED_DELTA_V001'
QUAL_RECEIPT_SCHEMAS = ('TICKSTORE_CDT15_WINDOWS_QUALIFICATION_RECEIPT_V003',)
B1_RESULT_SCHEMAS = ('TICKSTORE_CDT15_R44_B1_RESULT_V001',)
RETURN_MANIFEST_SCHEMA = 'TICKSTORE_CDT15_RETURN_MANIFEST_V001'
CODE_MANIFEST_SCHEMA = 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001'
FINAL_PACKAGE_MANIFEST_SCHEMA = 'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001'
FINAL_ROOT = 'implementation_v001/'
FINAL_CODE_ROOT = 'implementation_v001/candidate'
MEMBERS = {'qual_receipt': 'QUAL_RECEIPT.json', 'return_manifest': 'RETURN_MANIFEST.json',
           'harness_result': 'EVIDENCE/B1_HARNESS/RESULT.json', 'tests_log': 'EVIDENCE/B1_HARNESS/TESTS.log',
           'b1_result': 'EVIDENCE/B1_RESULT.json'}
PROOF_PREFIX = 'EVIDENCE/PROOFS/'
PROOF_RUNNER = 'g5proof/G5_PROOF_RUNNERS.py'
# Typed target proofs.  A proof is satisfied only by a receipt of its own kind, from
# its own runner function in the packaged code, with exactly its own named checks.
TYPED_PROOFS = {
    'PROCESS_TREE_CRASH_CONTAINMENT': {
        'kind': 'TICKSTORE_G5_PROOF_PROCESS_TREE_CRASH_V001', 'function': 'proof_process_tree_crash',
        'checks': ('job_child_alive_before_crash', 'coordinator_terminated_abruptly',
                   'job_child_dead_after_coordinator_crash', 'no_job_descendant_survives', 'sandbox_only')},
    'SAFE_STOP_RESUME_ROW_GROUP': {
        'kind': 'TICKSTORE_G5_PROOF_SAFE_STOP_RESUME_V001', 'function': 'proof_safe_stop_resume',
        'checks': ('named_stop_honoured', 'partial_day_preserved', 'resume_reused_completed_days',
                   'resume_completed_partial_day', 'no_duplicate_or_lost_rows', 'resume_worker_count_changed',
                   'sandbox_only')},
    'PS51_INSTALL_MENU': {
        'kind': 'TICKSTORE_G5_PROOF_PS51_INSTALL_MENU_V001', 'function': 'proof_ps51_install_menu',
        'checks': ('ps51_host_version', 'inactive_install_readback', 'menu_not_activated_without_chain',
                   'official_menu_untouched', 'qualification_layout_writer_committed', 'sandbox_only')},
    'D4_CLOSURE_NATIVE_1399': {
        'kind': 'TICKSTORE_G5_PROOF_D4_CLOSURE_SYNTHETIC_1399_V001', 'function': 'proof_d4_closure_synthetic_1399',
        'checks': ('inventory_entries_1399', 'ntfs_sandbox_volume', 'closure_complete_readback',
                   'closure_rejects_missing_entry', 'closure_rejects_tampered_entry', 'no_production_target',
                   'sandbox_only')},
    'STAGE_B_FULL_CHAIN_NATIVE': {
        'kind': 'TICKSTORE_G5_PROOF_STAGE_B_SYNTHETIC_CHAIN_V001', 'function': 'proof_stage_b_synthetic_chain',
        'checks': ('stage_b_suites_executed_natively', 'no_skips', 'physical_publication_readback',
                   'no_production_target', 'sandbox_only')},
    # Physical power loss cannot be produced by software.  No runner is accepted until the
    # origin specifies a sacrificial-media experiment; POWERLOSS_EMULATED never satisfies it.
    'CHECKPOINT_POWERLOSS_RECOVERY': {
        'kind': 'TICKSTORE_G5_PROOF_PHYSICAL_POWERLOSS_V001', 'function': None, 'checks': ()},
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def _strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('JSON_DUPLICATE_KEY:' + str(k))
            out[k] = v
        return out
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def harness_findings(h, wanted, code_sha):
    """Every reason the native harness RESULT.json does not prove the contract; [] if it does."""
    f = []
    if not isinstance(h, dict):
        return ['HARNESS_NOT_OBJECT']
    if h.get('schema') != HARNESS_SCHEMA:
        f.append('HARNESS_SCHEMA')
    if h.get('native_windows') is not True or h.get('selection') != 'NATIVE':
        f.append('HARNESS_NOT_NATIVE_WINDOWS_SELECTION')
    if not str(h.get('platform', '')).startswith('Windows'):
        f.append('HARNESS_PLATFORM_NOT_WINDOWS')
    if 'MSC v.' not in str(h.get('python', '')):
        f.append('HARNESS_PYTHON_NOT_WINDOWS_BUILD')
    if h.get('code_manifest_sha256') != code_sha:
        f.append('HARNESS_CODE_MANIFEST_MISMATCH')
    if h.get('tested_code_unchanged') is not True:
        f.append('HARNESS_CODE_CHANGED_DURING_RUN')
    if h.get('production_execution') is not False:
        f.append('HARNESS_PRODUCTION_EXECUTION')
    if h.get('success') is not True:
        f.append('HARNESS_SUCCESS_NOT_TRUE')
    if h.get('interruption') is not None or h.get('byte_revalidation_error') is not None:
        f.append('HARNESS_INTERRUPTED_OR_BYTE_REVALIDATION')
    tests = h.get('tests')
    if not isinstance(tests, list) or not all(isinstance(t, dict) and isinstance(t.get('id'), str) for t in tests):
        return f + ['HARNESS_TEST_RECORDS']
    ids = [t['id'] for t in tests]
    if len(ids) != len(wanted):
        f.append('HARNESS_RECORD_COUNT:%d!=%d' % (len(ids), len(wanted)))
    dup = sorted(i for i, n in collections.Counter(ids).items() if n > 1)
    if dup:
        f.append('HARNESS_DUPLICATE_RECORDS:' + ','.join(dup))
    if set(ids) != set(wanted):
        f.append('HARNESS_ID_SET_NOT_CONTRACT')
    non_pass = sorted({t['id'] for t in tests if t.get('status') != 'PASS'} | (set(wanted) - set(ids)))
    if non_pass:
        f.append('NON_PASS_IDS:' + ','.join(non_pass))
    if h.get('totals') != {'tests_run': len(wanted), 'failures': 0, 'errors': 0, 'skips': 0}:
        f.append('HARNESS_TOTALS:' + json.dumps(h.get('totals'), sort_keys=True))
    if (h.get('tests_expected'), h.get('tests_not_run'), h.get('tests_interrupted')) != (len(wanted), 0, 0):
        f.append('HARNESS_EXPECTED_COUNTS')
    return f


def tests_log_findings(text, wanted):
    """The unittest log must show each contract ID exactly once as ok, Ran N, OK."""
    f = []
    text = text.replace('\r\n', '\n')
    for marker in ('IMMEDIATE_DIAGNOSTIC', 'CAMPAIGN_INTERRUPTED', 'CODE_REVALIDATION_FAILED'):
        if marker in text:
            f.append('TESTS_LOG_' + marker)
    bad = [i for i in wanted
           if len(re.findall(r'\(' + re.escape(i) + r'\)(?:\n[^\n]*)? \.\.\. ok\n', text)) != 1
           or text.count('(' + i + ')') != 1]
    if bad:
        f.append('TESTS_LOG_RECORDS:%d' % len(bad))
    ran = re.findall(r'^Ran (\d+) tests? in [0-9.]+s$', text, re.M)
    if ran != [str(len(wanted))]:
        f.append('TESTS_LOG_RAN:' + ','.join(ran))
    lines = [x for x in text.split('\n') if x.strip()]
    if not lines or lines[-1] != 'OK':
        f.append('TESTS_LOG_NOT_OK')
    return f


def qual_receipt_findings(q, final_sha, code_sha):
    f = []
    if not isinstance(q, dict):
        return ['QUAL_RECEIPT_NOT_OBJECT']
    if q.get('schema') not in QUAL_RECEIPT_SCHEMAS:
        f.append('QUAL_RECEIPT_SCHEMA')
    if q.get('mode') != 'NATIVE_WINDOWS':
        f.append('QUAL_RECEIPT_NOT_NATIVE')
    if q.get('SOURCE_SHA256') != final_sha:
        f.append('QUAL_RECEIPT_FINAL_ZIP_BINDING')
    if q.get('RUNTIME_CODE_MANIFEST_SHA256') != code_sha:
        f.append('QUAL_RECEIPT_CODE_MANIFEST_BINDING')
    if not str(q.get('TESTED_CODE_EQUALS_PACKAGED_CODE', '')).startswith('PASS'):
        f.append('QUAL_RECEIPT_TESTED_NOT_PACKAGED')
    if q.get('PRODUCTION_MODIFIED') is not False or q.get('FULL_STARTED') is not False:
        f.append('QUAL_RECEIPT_PRODUCTION_OR_FULL')
    if not isinstance(q.get('RUN_ID'), str) or not q['RUN_ID']:
        f.append('QUAL_RECEIPT_RUN_ID')
    pre = q.get('PRECHECK') if isinstance(q.get('PRECHECK'), dict) else {}
    if not str(pre.get('platform', '')).startswith('Windows'):
        f.append('QUAL_PRECHECK_PLATFORM')
    if not str(pre.get('powershell', '')).startswith('5.1.'):
        f.append('QUAL_PRECHECK_PS51')
    if 'MSC v.' not in str(pre.get('python', '')):
        f.append('QUAL_PRECHECK_PYTHON')
    vols = pre.get('volumes') if isinstance(pre.get('volumes'), dict) else {}
    if not vols or not all(isinstance(v, dict) and v.get('filesystem') == 'NTFS' for v in vols.values()):
        f.append('QUAL_PRECHECK_NTFS')
    if pre.get('elevated') is not True or pre.get('symlink_privilege') != 'PASS':
        f.append('QUAL_PRECHECK_ELEVATION_SYMLINK')
    return f


def _zip_members(raw, label):
    """Open a closed ZIP from bytes; reject CRC errors, unsafe or duplicate names."""
    f = []
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        bad = z.testzip()
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        return None, {}, [label + '_ZIP_UNREADABLE:' + type(exc).__name__]
    if bad is not None:
        f.append(label + '_ZIP_CRC:' + bad)
    names = [i.filename for i in z.infolist()]
    if len(names) != len(set(names)):
        f.append(label + '_ZIP_DUPLICATE_MEMBER')
    for n in names:
        p = PurePosixPath(n)
        if n.startswith('/') or '\\' in n or ':' in n or '..' in p.parts:
            f.append(label + '_ZIP_UNSAFE_MEMBER:' + n)
    files = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    return z, files, f


def final_zip_findings(raw, code_sha):
    """FINAL package: exact package manifest and complete, non-empty runtime code manifest."""
    z, files, f = _zip_members(raw, 'FINAL')
    if z is None:
        return f, None
    try:
        pm = _strict_json(files['PACKAGE_MANIFEST.json'])
        recs = {r['path']: r for r in pm['files']}
        if pm.get('schema') != FINAL_PACKAGE_MANIFEST_SCHEMA or set(recs) != set(files) - {'PACKAGE_MANIFEST.json'}:
            f.append('FINAL_PACKAGE_MANIFEST_COVERAGE')
        for name, r in recs.items():
            body = files.get(name)
            if body is None or len(body) != r['bytes'] or _sha(body) != r['sha256']:
                f.append('FINAL_PACKAGE_MEMBER:' + name)
    except (KeyError, TypeError, ValueError):
        f.append('FINAL_PACKAGE_MANIFEST_UNREADABLE')
    mraw = files.get(FINAL_ROOT + 'RUNTIME_CODE_MANIFEST.json')
    if mraw is None or _sha(mraw) != code_sha:
        return f + ['FINAL_RUNTIME_MANIFEST_NOT_CODE_SHA'], None
    try:
        m = _strict_json(mraw)
        recs = m['files']
        paths = [r['path'] for r in recs]
    except (KeyError, TypeError, ValueError):
        return f + ['FINAL_RUNTIME_MANIFEST_UNREADABLE'], None
    if m.get('schema') != CODE_MANIFEST_SCHEMA or m.get('root') != FINAL_CODE_ROOT:
        f.append('FINAL_RUNTIME_MANIFEST_SCHEMA')
    if not recs:
        f.append('FINAL_RUNTIME_MANIFEST_EMPTY')
    if len(paths) != len(set(paths)):
        f.append('FINAL_RUNTIME_MANIFEST_DUPLICATE_PATH')
    prefix = FINAL_CODE_ROOT + '/'
    packaged = {n[len(prefix):] for n in files if n.startswith(prefix)}
    if set(paths) != packaged:
        f.append('FINAL_RUNTIME_MANIFEST_NOT_CLOSED:%d!=%d' % (len(set(paths)), len(packaged)))
    for r in recs:
        body = files.get(prefix + str(r.get('path')))
        if body is None or len(body) != r.get('bytes') or _sha(body) != r.get('sha256'):
            f.append('FINAL_RUNTIME_MEMBER:' + str(r.get('path')))
    return f, {r['path']: r['sha256'] for r in recs}


def return_zip_findings(raw):
    """Closed native RETURN ZIP with an exact recursive member manifest."""
    z, files, f = _zip_members(raw, 'RETURN')
    if z is None:
        return f, {}
    try:
        rm = _strict_json(files[MEMBERS['return_manifest']])
        recs = {r['path']: r for r in rm['files']}
        if rm.get('schema') != RETURN_MANIFEST_SCHEMA or set(recs) != set(files) - {MEMBERS['return_manifest']}:
            f.append('RETURN_MANIFEST_COVERAGE')
        for name, r in recs.items():
            body = files.get(name)
            if body is None or len(body) != r['bytes'] or _sha(body) != r['sha256']:
                f.append('RETURN_MANIFEST_MEMBER:' + name)
    except (KeyError, TypeError, ValueError):
        f.append('RETURN_MANIFEST_UNREADABLE')
    for key in ('qual_receipt', 'harness_result', 'tests_log', 'b1_result'):
        if MEMBERS[key] not in files:
            f.append('RETURN_MEMBER_MISSING:' + MEMBERS[key])
    return f, files


def proof_receipt_findings(name, receipt, member, rfiles, code_index, final_sha, code_sha, run_id):
    """A typed receipt from the named runner of this proof, with its own checks and artifacts."""
    spec = TYPED_PROOFS[name]
    f = []
    if not isinstance(receipt, dict):
        return [name + ':RECEIPT_NOT_OBJECT']
    if receipt.get('kind') == POWERLOSS_EMULATED_KIND:
        f.append(name + ':POWERLOSS_EMULATED_IS_NOT_PHYSICAL_POWERLOSS')
    if spec['function'] is None:
        return f + [name + ':PHYSICAL_PROOF_NOT_SPECIFIED_BY_ORIGIN']
    if receipt.get('schema') != PROOF_RECEIPT_SCHEMA or receipt.get('kind') != spec['kind']:
        f.append(name + ':RECEIPT_KIND')
    if receipt.get('proof') != name or member != PROOF_PREFIX + name + '/PROOF_RECEIPT.json':
        f.append(name + ':RECEIPT_PROOF_NAME')
    if receipt.get('status') != 'PASS':
        f.append(name + ':RECEIPT_STATUS:' + str(receipt.get('status')))
    if receipt.get('native_windows') is not True or not str(receipt.get('platform', '')).startswith('Windows'):
        f.append(name + ':RECEIPT_NOT_NATIVE')
    if receipt.get('production_execution') is not False:
        f.append(name + ':RECEIPT_PRODUCTION')
    if (receipt.get('code_manifest_sha256'), receipt.get('final_zip_sha256'), receipt.get('run_id')) != (
            code_sha, final_sha, run_id):
        f.append(name + ':RECEIPT_RUN_BINDING')
    runner = receipt.get('runner') if isinstance(receipt.get('runner'), dict) else {}
    if (runner.get('path') != PROOF_RUNNER or runner.get('function') != spec['function']
            or code_index is None or code_index.get(PROOF_RUNNER) != runner.get('sha256')):
        f.append(name + ':RECEIPT_RUNNER_NOT_PACKAGED')
    if not isinstance(receipt.get('scenario'), str) or not receipt['scenario']:
        f.append(name + ':RECEIPT_SCENARIO')
    checks = receipt.get('checks') if isinstance(receipt.get('checks'), dict) else {}
    if set(checks) != set(spec['checks']) or not all(v == 'PASS' for v in checks.values()):
        f.append(name + ':RECEIPT_CHECKS')
    arts = receipt.get('artifacts')
    if not isinstance(arts, list) or not arts:
        return f + [name + ':RECEIPT_NO_ARTIFACTS']
    for a in arts:
        m = a.get('member') if isinstance(a, dict) else None
        body = rfiles.get(m) if isinstance(m, str) else None
        if (not isinstance(m, str) or not m.startswith(PROOF_PREFIX + name + '/') or body is None or not body
                or _sha(body) != a.get('sha256')):
            f.append(name + ':RECEIPT_ARTIFACT:' + str(m))
    return f


def _resolve(entry, base):
    p = Path(str(entry.get('path', '')))
    if p.is_file():
        return p
    rel = entry.get('pack_relative')
    if base is not None and isinstance(rel, str) and rel and '..' not in PurePosixPath(rel).parts:
        q = Path(base) / rel
        if q.is_file():
            return q
    return p


def physical_findings(delta, contract, code_sha, base=None):
    """Re-read every physical input named by delta['native_provenance']; [] only if all bind."""
    prov = delta.get('native_provenance')
    if not isinstance(prov, dict) or prov.get('schema') != PROVENANCE_SCHEMA:
        return ['NATIVE_PROVENANCE_MISSING']
    wanted = contract['required_tests']
    f = []
    blobs = {}
    for key in ('return_zip', 'final_zip'):
        e = prov.get(key)
        if not isinstance(e, dict) or HEX64.fullmatch(str(e.get('sha256'))) is None:
            f.append('PROVENANCE_' + key.upper())
            continue
        try:
            raw = _resolve(e, base).read_bytes()
        except OSError:
            f.append('PROVENANCE_' + key.upper() + '_UNREADABLE')
            continue
        if _sha(raw) != e['sha256']:
            f.append('PROVENANCE_' + key.upper() + '_SHA256')
            continue
        blobs[key] = raw
    if len(blobs) != 2:
        return f
    final_sha = prov['final_zip']['sha256']
    ff, code_index = final_zip_findings(blobs['final_zip'], code_sha)
    f += ff
    rf, rfiles = return_zip_findings(blobs['return_zip'])
    f += rf
    if rf:
        return f
    parsed = {}
    for key in ('qual_receipt', 'harness_result', 'b1_result'):
        try:
            parsed[key] = _strict_json(rfiles[MEMBERS[key]])
        except ValueError:
            parsed[key] = None
        if not isinstance(parsed[key], dict):
            f.append('RETURN_MEMBER_UNREADABLE:' + MEMBERS[key])
            parsed[key] = {}
        if prov.get(key + '_sha256') != _sha(rfiles[MEMBERS[key]]):
            f.append('PROVENANCE_MEMBER_BINDING:' + key)
    if prov.get('tests_log_sha256') != _sha(rfiles[MEMBERS['tests_log']]):
        f.append('PROVENANCE_MEMBER_BINDING:tests_log')
    h = parsed['harness_result']
    f += harness_findings(h, wanted, code_sha)
    f += tests_log_findings(rfiles[MEMBERS['tests_log']].decode('utf-8', 'replace'), wanted)
    q = parsed['qual_receipt']
    f += qual_receipt_findings(q, final_sha, code_sha)
    if 'MSC v.' in str(h.get('python', '')) and h.get('python') != (q.get('PRECHECK') or {}).get('python'):
        f.append('HARNESS_PYTHON_NOT_PRECHECK_PYTHON')
    b1 = parsed['b1_result']
    if (b1.get('schema') not in B1_RESULT_SCHEMAS or b1.get('status') != 'PASS'
            or b1.get('counts') != {'pass': len(wanted), 'expected_executed': len(wanted), 'non_pass': 0}):
        f.append('B1_RESULT_NOT_PASS')
    if isinstance(h.get('tests'), list):
        physical = {t.get('id'): t.get('status') for t in h['tests'] if isinstance(t, dict)}
        if [(t.get('id'), t.get('status')) for t in delta.get('tests', []) if isinstance(t, dict)] != [
                (i, physical.get(i)) for i in wanted]:
            f.append('DELTA_TESTS_NOT_PHYSICAL_HARNESS')
    if prov.get('code_manifest_files') != (len(code_index) if code_index else None) or not code_index:
        f.append('PROVENANCE_CODE_MANIFEST_FILES')
    # Typed target proofs: distinct receipts, each re-read from the closed RETURN ZIP.
    seen = {}
    for name in contract['required_target_proofs']:
        proof = (delta.get('target_proofs') or {}).get(name) or {}
        ev = proof.get('evidence') if isinstance(proof.get('evidence'), list) else []
        if len(ev) != 1 or not isinstance(ev[0], dict):
            unspecified = TYPED_PROOFS[name]['function'] is None
            f.append(name + (':PHYSICAL_PROOF_NOT_SPECIFIED_BY_ORIGIN' if unspecified
                             else ':EVIDENCE_NOT_SINGLE_TYPED_RECEIPT'))
            continue
        e = ev[0]
        member = e.get('return_zip_member')
        body = rfiles.get(member) if isinstance(member, str) else None
        if body is None or _sha(body) != e.get('sha256'):
            f.append(name + ':EVIDENCE_NOT_IN_RETURN_ZIP')
            continue
        try:
            if _resolve(e, base).read_bytes() != body:
                f.append(name + ':EVIDENCE_PACK_COPY_DIFFERS')
        except OSError:
            f.append(name + ':EVIDENCE_PACK_COPY_UNREADABLE')
        if e['sha256'] in seen:
            f.append(name + ':EVIDENCE_REUSED_FROM:' + seen[e['sha256']])
        seen[e['sha256']] = name
        try:
            receipt = _strict_json(body)
        except ValueError:
            f.append(name + ':RECEIPT_UNREADABLE')
            continue
        if e.get('kind') != receipt.get('kind'):
            f.append(name + ':EVIDENCE_KIND_NOT_RECEIPT_KIND')
        f += proof_receipt_findings(name, receipt, member, rfiles, code_index, final_sha, code_sha, q.get('RUN_ID'))
    return f


def validate(completeness, contract, delta, code_sha, require):
    require(contract.get('schema') == 'TICKSTORE_QUALIFICATION_CONTRACT_V001', 'QUALIFICATION_CONTRACT_SCHEMA')
    require(completeness.get('baseline') == contract.get('baseline') and bool(contract.get('baseline')),
            'QUALIFICATION_BASELINE_BINDING')
    baseline = contract['baseline']
    require(isinstance(baseline, dict) and baseline.get('status') == 'PASS_HISTORICAL_BYTES_ONLY',
            'QUALIFICATION_BASELINE_SCHEMA')
    for key in ('archive_sha256', 'run_sha256', 'tests_sha256', 'code_manifest_sha256'):
        require(re.fullmatch('[0-9A-F]{64}', str(baseline.get(key))) is not None,
                'QUALIFICATION_BASELINE_DIGEST:' + key)
    meta = completeness.get('baseline_archive_evidence', {})
    require(isinstance(meta, dict) and isinstance(meta.get('path'), str) and bool(meta['path'])
            and meta.get('sha256') == baseline['archive_sha256'], 'QUALIFICATION_BASELINE_PHYSICAL_EVIDENCE')
    require(delta.get('schema') == 'TICKSTORE_CDT15_DELTA_QUALIFICATION_V001', 'DELTA_QUALIFICATION_SCHEMA')
    require(delta.get('platform') == 'WINDOWS_NTFS_PS51' and delta.get('native_windows') is True,
            'DELTA_NATIVE_WINDOWS_REQUIRED')
    require(delta.get('code_manifest_sha256') == code_sha
            and delta.get('tested_code_equals_packaged_code') == 'PASS', 'DELTA_FINAL_BYTES')
    require(delta.get('production_execution') is False and delta.get('success') is True,
            'DELTA_ISOLATED_QUALIFICATION')
    wanted = contract.get('required_tests')
    require(isinstance(wanted, list) and bool(wanted) and all(isinstance(x, str) and x for x in wanted)
            and len(set(wanted)) == len(wanted), 'DELTA_REQUIRED_TESTS')
    results = delta.get('tests')
    require(isinstance(results, list) and len(results) == len(wanted), 'DELTA_TEST_CARDINALITY')
    require(all(isinstance(r, dict) and isinstance(r.get('id'), str) for r in results), 'DELTA_TEST_RECORD')
    require(len({r['id'] for r in results}) == len(results) and {r['id'] for r in results} == set(wanted),
            'DELTA_TEST_SET')
    require(all(r.get('status') == 'PASS' for r in results), 'DELTA_FAILURE_ERROR_OR_SKIP')
    required_proofs = contract.get('required_target_proofs')
    require(isinstance(required_proofs, list) and bool(required_proofs)
            and all(isinstance(x, str) and x for x in required_proofs)
            and len(set(required_proofs)) == len(required_proofs), 'DELTA_TARGET_PROOFS_CONTRACT')
    proofs = delta.get('target_proofs', {})
    require(isinstance(proofs, dict) and set(proofs) == set(required_proofs), 'DELTA_TARGET_PROOFS_SET')
    reused = {}
    for name, proof in proofs.items():
        require(isinstance(proof, dict) and proof.get('status') == 'PASS'
                and isinstance(proof.get('evidence'), list) and bool(proof['evidence']),
                'DELTA_TARGET_PROOF:' + name)
        for item in proof['evidence']:
            require(isinstance(item, dict) and isinstance(item.get('path'), str) and bool(item['path'])
                    and re.fullmatch('[0-9A-F]{64}', str(item.get('sha256'))) is not None,
                    'DELTA_TARGET_EVIDENCE:' + name)
            # One physical artifact cannot prove two different requirements (B2-G5-01).
            require(reused.setdefault(item['sha256'], name) == name, 'DELTA_TARGET_EVIDENCE_REUSED:' + name)
    require(completeness.get('delta_test_totals') == {'run': len(results), 'failures': 0, 'errors': 0, 'skips': 0},
            'DELTA_TOTALS_PARITY')
    require(completeness.get('baseline_results_counted_as_delta') is False, 'BASELINE_NOT_NEW_QUALIFICATION')
    if 'harness_totals' in delta:
        require(delta['harness_totals'] == {'tests_run': len(wanted), 'failures': 0, 'errors': 0, 'skips': 0},
                'DELTA_HARNESS_TOTALS')
    typed = [p for p in required_proofs if p in TYPED_PROOFS]
    if typed:
        # Contracts naming the typed G5 proofs are satisfied only by physical native provenance.
        require(len(typed) == len(required_proofs), 'DELTA_TARGET_PROOFS_UNTYPED')
        ev = completeness.get('delta_qualification_evidence')
        base = Path(ev['path']).parent if isinstance(ev, dict) and isinstance(ev.get('path'), str) else None
        findings = physical_findings(delta, contract, code_sha, base)
        require(not findings, 'DELTA_NATIVE_PROVENANCE:' + ';'.join(findings[:12]))
