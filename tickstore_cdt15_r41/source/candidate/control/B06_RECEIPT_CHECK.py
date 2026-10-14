"""Read-only conformance check of an INDEPENDENT B06 stage receipt (never issues, never repairs).

B06 is performed by an independent reviewer, never by the implementer.  Before the operator uses the
receipt (chain until B06 for the B07 runner; B07 decision binding; D4 review verdict), this tool
verifies, from physical files only:
  * the receipt validates in the production chain consumer (FULL_RELEASE_CHAIN.validate_chain) as the
    successor of the G5 stage receipt, bound to the same code manifest and instance;
  * reviewer named, implementation_participant false, all three B06 checks true, no blockers;
  * the receipt cites the B06 VERDICT text as evidence (digest supplied separately) and that verdict
    states VERDICT=PASS, INDEPENDENT_REVIEW=YES, TESTED_CODE_EQUALS_PACKAGED_CODE=YES and
    zero critical/major findings (same rule as B07_TECHNICAL_PRODUCER).
Output: the two digests the later stages need (receipt and verdict), or B06_RECEIPT_CHECK=BLOCKED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from FULL_RELEASE_CHAIN import validate_chain  # noqa: E402

VERDICT_FIELDS = (('VERDICT', 'PASS'), ('INDEPENDENT_REVIEW', 'YES'), ('TESTED_CODE_EQUALS_PACKAGED_CODE', 'YES'),
                  ('CRITICAL_FINDINGS', '0'), ('MAJOR_FINDINGS', '0'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise RuntimeError('B06_JSON_DUPLICATE_KEY:' + str(k))
            out[k] = v
        return out
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def check(*, b06_receipt, g5_receipt, code_manifest, instance, verdict, verdict_sha256, environment='WINDOWS_PRODUCTION'):
    raws = {k: Path(v).read_bytes() for k, v in (('b06', b06_receipt), ('g5', g5_receipt), ('code', code_manifest),
                                                ('instance', instance), ('verdict', verdict))}
    if sha(raws['verdict']) != verdict_sha256:
        raise RuntimeError('B06_VERDICT_SHA256_SUPPLIED_SEPARATELY')
    fields = {}
    for line in raws['verdict'].decode('utf-8').splitlines():
        if '=' in line:
            k, v = line.strip().split('=', 1)
            if k.strip() in fields:
                raise RuntimeError('B06_VERDICT_DUPLICATE_FIELD:' + k.strip())
            fields[k.strip()] = v.strip()
    for k, want in VERDICT_FIELDS:
        if fields.get(k) != want:
            raise RuntimeError('B06_VERDICT_FIELD:' + k)
    receipts = {'G5': strict_json(raws['g5']), 'B06': strict_json(raws['b06'])}
    hashes = {'G5': sha(raws['g5']), 'B06': sha(raws['b06'])}
    validate_chain(receipts, hashes, code_sha=sha(raws['code']), instance_sha=sha(raws['instance']),
                   b06_sha=hashes['B06'], until='B06', environment=environment)
    cited = [e for e in receipts['B06']['evidence'] if e.get('sha256') == verdict_sha256]
    if not cited:
        raise RuntimeError('B06_RECEIPT_DOES_NOT_CITE_VERDICT')
    return {'schema': 'TICKSTORE_B06_RECEIPT_CHECK_V001', 'status': 'CONFORMANT', 'b06_receipt_sha256': hashes['B06'],
            'b06_verdict_sha256': verdict_sha256, 'g5_receipt_sha256': hashes['G5'], 'reviewer': receipts['B06']['reviewer'],
            'issued_by_this_tool': False}


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for k in ('b06-receipt', 'g5-receipt', 'code-manifest', 'instance', 'verdict', 'verdict-sha256'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args(argv)
    try:
        r = check(b06_receipt=a.b06_receipt, g5_receipt=a.g5_receipt, code_manifest=a.code_manifest,
                  instance=a.instance, verdict=a.verdict, verdict_sha256=a.verdict_sha256.upper())
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print('B06_RECEIPT_CHECK=BLOCKED REASON=' + type(exc).__name__ + ':' + str(exc))
        return 2
    print(json.dumps(r, indent=1, sort_keys=True))
    print('B06_RECEIPT_CHECK=CONFORMANT B06_RECEIPT_SHA256=%s B06_VERDICT_SHA256=%s'
          % (r['b06_receipt_sha256'], r['b06_verdict_sha256']))
    return 0


if __name__ == '__main__':
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log('B06_RECEIPT_CHECK', main))
