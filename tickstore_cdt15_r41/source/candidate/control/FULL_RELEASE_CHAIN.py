"""Technical stage admission for the existing FULL runner.

This module never issues an audit verdict or an administrative owner gate.
An independently supplied B06 digest is the trust anchor. Every later receipt
binds the same code, instance and predecessor bytes. Fixture receipts have a
different environment and cannot be consumed by the operational entrypoint.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import os
import re
import time

from D4_FIRST_ADMISSION_PREP import Reads, Blocked, require, sha, strict_json

STAGES = ('G5', 'B06', 'B07', 'D4', 'D5', 'CANARY', 'FULL_PREP', 'FULL_ADMISSION')
REQUIRED_CHECKS = {
    'G5': ('features_implemented', 'blockers_closed', 'tested_equals_packaged',
           'adversarial_completeness', 'byte_freeze'),
    'B06': ('independent_review', 'final_bytes', 'no_critical_or_major_findings'),
    'B07': ('native_windows', 'physical_policy_capture', 'state_continuity',
            'vss_identity', 'negative_controls', 'process_tree_cleanup'),
    'D4': ('scratch_certification', 'checkpoint_readback', 'journal_closed'),
    'D5': ('canonical_certification', 'checkpoint_readback', 'journal_closed'),
    'CANARY': ('readback', 'safe_stop_resume', 'no_duplicate_ticks',
               'failure_recovery', 'source_reconciliation', 'process_tree_cleanup'),
    'FULL_PREP': ('production_certificates', 'manifest_rederivation', 'live_equality',
                  'admission_simulation', 'stage_b_evidence_pack'),
    'FULL_ADMISSION': ('fresh_instance', 'source_plan', 'resource_limits',
                       'locks_and_leases', 'vss_identity', 'root_identities', 'stage_b_review', 'production_freeze'),
}


def digest(value, label):
    require(isinstance(value, str) and re.fullmatch('[0-9A-F]{64}', value) is not None,
            label + '_SHA256')
    return value


def validate_chain(receipts, hashes, *, code_sha, instance_sha, b06_sha,
                   until='FULL_ADMISSION', environment='WINDOWS_PRODUCTION'):
    """Pure validation; called before opening STATE or any output directory."""
    require(until in STAGES, 'CHAIN_UNKNOWN_STAGE')
    needed = STAGES[:STAGES.index(until) + 1]
    require(tuple(receipts) == needed and tuple(hashes) == needed, 'CHAIN_STAGE_ORDER')
    digest(code_sha, 'CODE'); digest(instance_sha, 'INSTANCE'); digest(b06_sha, 'B06')
    previous = None
    for stage in needed:
        obj = receipts[stage]
        digest(hashes[stage], stage)
        require(isinstance(obj, dict) and obj.get('schema') == 'TICKSTORE_STAGE_RECEIPT_V001',
                stage + '_SCHEMA')
        require(obj.get('stage') == stage and obj.get('status') == 'PASS', stage + '_NOT_PASS')
        require(obj.get('environment') == environment, stage + '_ENVIRONMENT')
        require(obj.get('code_manifest_sha256') == code_sha, stage + '_CODE_DRIFT')
        require(obj.get('instance_sha256') == instance_sha, stage + '_INSTANCE_DRIFT')
        require(obj.get('previous_receipt_sha256') == previous, stage + '_PREDECESSOR')
        require(obj.get('blockers') == [], stage + '_BLOCKERS')
        checks = obj.get('checks')
        require(isinstance(checks, dict) and all(checks.get(k) is True for k in REQUIRED_CHECKS[stage]),
                stage + '_CHECKS')
        evidence = obj.get('evidence')
        require(isinstance(evidence, list) and bool(evidence), stage + '_EVIDENCE_REQUIRED')
        for item in evidence:
            require(isinstance(item, dict) and isinstance(item.get('path'), str), stage + '_EVIDENCE_PATH')
            digest(item.get('sha256'), stage + '_EVIDENCE')
        if stage == 'B06':
            require(hashes[stage] == b06_sha, 'B06_EXTERNAL_DIGEST_MISMATCH')
            require(isinstance(obj.get('reviewer'), str) and bool(obj['reviewer'].strip()), 'B06_REVIEWER')
            require(obj.get('implementation_participant') is False, 'B06_IMPLEMENTER_CANNOT_APPROVE')
        previous = hashes[stage]
    return previous


def member_path(root, name):
    require(isinstance(name, str) and '\\' not in name and ':' not in name, 'CODE_MEMBER_PATH')
    rel = PurePosixPath(name)
    require(not rel.is_absolute() and name and all(p not in ('', '.', '..') for p in name.split('/')),
            'CODE_MEMBER_PATH')
    require(all(not p.endswith((' ', '.')) and not re.search(r'[\x00-\x1f<>"|?*]', p)
                and re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p) is None
                for p in rel.parts), 'CODE_MEMBER_PATH')
    return Path(root).joinpath(*rel.parts)


class ReleaseChain(Reads):
    """Retain write/delete-denying native pins until the runner has shut down."""
    def __init__(self, descriptor, descriptor_sha, b06_sha, code_root, *, until='FULL_ADMISSION'):
        super().__init__()
        try:
            self.root = Path(code_root)
            self.descriptor = strict_json(self.read(descriptor, digest(descriptor_sha, 'DESCRIPTOR')))
            d = self.descriptor
            require(d.get('schema') == 'TICKSTORE_EXECUTION_CHAIN_V001', 'CHAIN_SCHEMA')
            require(d.get('environment') == 'WINDOWS_PRODUCTION', 'CHAIN_ENVIRONMENT')
            instance_raw = self.read(d['instance_path'], digest(d['instance_sha256'], 'INSTANCE'))
            self.instance = strict_json(instance_raw)
            require(self.instance.get('schema') == 'TICKSTORE_FULL_INSTANCE_V001', 'INSTANCE_SCHEMA')
            manifest_raw = self.read(d['code_manifest_path'], digest(d['code_manifest_sha256'], 'CODE'))
            manifest = strict_json(manifest_raw)
            require(manifest.get('schema') == 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001', 'CODE_SCHEMA')
            listed = set()
            for item in manifest['files']:
                p = member_path(self.root, item['path'])
                key = item['path'].casefold()
                require(key not in listed, 'CODE_DUPLICATE_MEMBER')
                listed.add(key)
                raw = self.read(p, digest(item['sha256'], 'CODE_MEMBER'))
                require(type(item['bytes']) is int and len(raw) == item['bytes'], 'CODE_MEMBER_SIZE')
            physical = {p.relative_to(self.root).as_posix().casefold()
                        for p in self.root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
            require(listed == physical, 'CODE_CLOSED_FILE_SET')
            required = {'full/tickstore_full_multiwork.py', 'full/tickstore_serial_runner.py',
                        'control/full_release_chain.py'}
            require(required <= listed, 'CODE_REQUIRED_MEMBERS')
            require(until in STAGES, 'CHAIN_UNKNOWN_STAGE')
            needed = STAGES[:STAGES.index(until) + 1]
            require(set(d['receipts']) == set(needed), 'CHAIN_RECEIPT_SET')
            receipts, hashes = {}, {}
            for stage in needed:
                item = d['receipts'][stage]
                raw = self.read(item['path'], digest(item['sha256'], stage))
                receipts[stage] = strict_json(raw); hashes[stage] = sha(raw)
            self.receipt_sha = validate_chain(receipts, hashes, code_sha=sha(manifest_raw),
                    instance_sha=sha(instance_raw), b06_sha=b06_sha, until=until)
            self.receipts = receipts
            self.receipt_hashes = hashes
            for obj in receipts.values():
                for ev in obj['evidence']:
                    self.read(ev['path'], ev['sha256'])
            require(sha(Path(os.sys.executable).read_bytes()) == self.instance['python_sha256'], 'INSTANCE_PYTHON')
            self.read(os.sys.executable, self.instance['python_sha256'])
            self.revalidate()
        except BaseException:
            self.close()
            raise

    def validate_full(self, bindings, workers, max_workers, ram_target_percent):
        i = self.instance
        # These are technical identity constraints. No authorized flag is generated.
        for key, value in bindings.items():
            if key not in ('authorized', 'schema'):
                require(type(i.get('bindings', {}).get(key)) is type(value)
                        and i['bindings'][key] == value, 'FULL_INSTANCE_BINDING:' + key)
        limits = i.get('resources', {})
        require(type(max_workers) is int and type(ram_target_percent) is int
                and 1 <= workers <= max_workers <= limits.get('max_workers', 0) <= 32,
                'FULL_RESOURCE_WORKERS')
        require(20 <= ram_target_percent <= limits.get('ram_target_percent', 0) <= 80,
                'FULL_RESOURCE_RAM')
        final = self.receipts['FULL_ADMISSION']
        age = (time.time_ns() - final.get('created_unix_ns', 0)) / 1e9
        require(0 <= age <= 300, 'FULL_ADMISSION_NOT_FRESH_300S')
        for label in ('source', 'dest', 'scratch'):
            handle = self.enter_context(self.store.open(Path(bindings[label + '_root']), directory=True))
            require(handle.info() == final['root_identities'][label], 'FULL_ROOT_IDENTITY:' + label)
        from D4_FIRST_ADMISSION_PREP import library
        engine = library(self.read(self.root/'recovery/engine/tickstore_publisher_recovery_v004_release.py'),
                         'full_admission_native_recheck')
        vss = engine.NativeVSS(self.store, final['vss_profile'])
        try: vss.assert_present(final['generation'])
        finally: vss.close()
        require(engine.recovery_process_census()['known_recovery_supervisor_or_workers'] == 0,
                'FULL_RECOVERY_PROCESS_NOT_CLEAR')
        self.revalidate()
