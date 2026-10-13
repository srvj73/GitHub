"""Consume hash-bound historical baseline plus delta proof of final bytes.

This validator issues no qualification, completeness receipt or audit verdict.
Historical tests are evidence about their own bytes and are never recounted as
tests executed on the new candidate.
"""
import re


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
    for name, proof in proofs.items():
        require(isinstance(proof, dict) and proof.get('status') == 'PASS'
                and isinstance(proof.get('evidence'), list) and bool(proof['evidence']),
                'DELTA_TARGET_PROOF:' + name)
        for item in proof['evidence']:
            require(isinstance(item, dict) and isinstance(item.get('path'), str)
                    and re.fullmatch('[0-9A-F]{64}', str(item.get('sha256'))) is not None,
                    'DELTA_TARGET_EVIDENCE:' + name)
    require(completeness.get('delta_test_totals') == {'run': len(results), 'failures': 0, 'errors': 0, 'skips': 0},
            'DELTA_TOTALS_PARITY')
    require(completeness.get('baseline_results_counted_as_delta') is False, 'BASELINE_NOT_NEW_QUALIFICATION')
