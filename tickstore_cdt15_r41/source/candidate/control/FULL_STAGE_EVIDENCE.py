"""Physical, immutable evidence bridging the existing stage implementations.

This module cannot approve B06 or admit an instance. Its caller must hold the
release chain and STATE boundary. Mutable STATE/checkpoint bytes are snapshotted;
later stages never retain a write-denying handle on their predecessors' STATE.
"""
from pathlib import Path
import re
import time

from D4_FIRST_ADMISSION_PREP import Reads, canonical, require, sha, strict_json, validate_journal
from FULL_RELEASE_CHAIN import REQUIRED_CHECKS


def closed_results(journal_raw, nodes, runs, read):
    validate_journal(journal_raw)
    latest = {}
    for line in journal_raw.splitlines():
        item = strict_json(line); node = item.get('node')
        if node not in nodes:
            continue
        if item.get('phase') == 'STARTED':
            run = item.get('run_id')
            require(isinstance(run, str) and re.fullmatch(r'[A-Za-z0-9_-]+', run), 'STAGE_RESULT_RUN_ID')
            latest[node] = {'run': run, 'finished': None}
        elif item.get('phase') == 'FINISHED':
            require(node in latest and latest[node]['finished'] is None, 'STAGE_UNPAIRED_FINISH:' + node)
            require(item.get('run_id', latest[node]['run']) == latest[node]['run'], 'STAGE_FINISH_RUN_MISMATCH:' + node)
            latest[node]['finished'] = item
    results, evidence = {}, []
    for node in nodes:
        attempt = latest.get(node, {})
        finish = attempt.get('finished')
        require(isinstance(finish, dict) and finish.get('status') == 'PASS', 'STAGE_UNCLOSED_OR_FAILED:' + node)
        path = Path(runs)/attempt['run']/('RESULT_' + node + '.json')
        raw = read(path, finish.get('result_sha256'))
        # The explicit comparison also protects callers with a simple fixture reader.
        require(sha(raw) == finish.get('result_sha256'), 'STAGE_RESULT_JOURNAL_HASH:' + node)
        results[node] = strict_json(raw)
        evidence.append({'path': str(path), 'sha256': sha(raw)})
    return results, evidence


def publish(stage, admission, output, writer, snapshots, evidence, *, checks, extra=None):
    require(set(checks) == set(REQUIRED_CHECKS[stage]) and all(v is True for v in checks.values()),
            'STAGE_PHYSICAL_CHECKS_INCOMPLETE')
    require(stage not in admission.descriptor['receipts'], 'STAGE_ALREADY_PUBLISHED')
    admission.revalidate()
    evidence = list(evidence)
    # Immutable inputs are pinned on the chain through the publication commit.
    # Mutable STATE/journal enter only through the snapshots supplied by caller.
    for item in evidence:
        admission.read(item['path'], item['sha256'])
    for name, raw in snapshots.items():
        require(Path(name).name == name and name not in ('.', '..'), 'STAGE_SNAPSHOT_NAME')
        path = Path(output)/name; writer(path, raw)
        admission.read(path, sha(raw))
        evidence.append({'path': str(path), 'sha256': sha(raw)})
    receipt = dict(schema='TICKSTORE_STAGE_RECEIPT_V001', stage=stage, status='PASS',
                   environment='WINDOWS_PRODUCTION',
                   code_manifest_sha256=admission.descriptor['code_manifest_sha256'],
                   instance_sha256=admission.descriptor['instance_sha256'],
                   previous_receipt_sha256=admission.receipt_sha, blockers=[], checks=checks,
                   evidence=evidence, created_unix_ns=time.time_ns())
    extra = extra or {}
    require(not set(extra) & set(receipt), 'STAGE_RESERVED_FIELD')
    receipt.update(extra)
    receipt_path = Path(output)/('STAGE_' + stage + '.json')
    admission.revalidate()
    raw = canonical(receipt); writer(receipt_path, raw)
    admission.read(receipt_path, sha(raw))
    descriptor = dict(admission.descriptor, receipts=dict(admission.descriptor['receipts']))
    require(stage not in descriptor['receipts'], 'STAGE_ALREADY_PUBLISHED')
    descriptor['receipts'][stage] = {'path': str(receipt_path), 'sha256': sha(raw)}
    admission.revalidate()
    path = Path(output)/'EXECUTION_CHAIN.json'; raw = canonical(descriptor); writer(path, raw)
    admission.read(path, sha(raw)); admission.revalidate()
    print('NEXT_CHAIN_FILE=' + str(path) + '\nNEXT_CHAIN_SHA256=' + sha(raw), flush=True)
    return path, sha(raw)
