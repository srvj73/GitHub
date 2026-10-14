"""R44-B2C: hash-bound verification of the CURRENT canonical policy capture (no revision pin).

Replaces the V37/V38 literals formerly embedded in the D4 first-admission consumers.
Nothing here names the current revision: the policy identity is derived from the bytes
of the captured pair and accepted only when ALL of the following hold:

  * the capture folder holds exactly one MASTER and one HEAD (cardinality 1+1);
  * HEAD binds MASTER by filename and SHA-256, state FROZEN, single active master/head,
    and declares that a project-local copy carries no operational authority;
  * revision_id is structurally bound to the MASTER digest (<stamp>-<MASTER[:16]>);
  * the MASTER covers the TICKSTORE scope;
  * the identity is not one of the historical (superseded) revisions kept for provenance;
  * an origin-issued reconciliation record, whose SHA-256 is supplied separately by the
    operator (same pattern as the independent B06 digest), states that exactly this
    MASTER/HEAD/revision is the live library state, is still within its validity window,
    and names the origin conversation that reconciled it (routing_project/routing_thread).

The policy admission receipt keeps project='PEGASUS_TICKSTORE' / thread='Compress\u00e3o De Ticks 7':
those are historical provenance fields required byte-for-byte by the frozen release engine
(_d4r ... POLICY_ADMISSION_SCOPE), i.e. receipt ABI, not a policy revision or routing pin.

A capture is never authority by itself; the reconciliation is issued by the ChatGPT
origin, never by this code.  No administrative OWNER_GATE approval is required or accepted.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

MASTER = 'POLITICA_CANONICA_UNIFICADA_OPERACIONAL.md'
HEAD = 'POLITICA_CANONICA_HEAD.json'
RECONCILIATION_SCHEMA = 'TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001'
SCOPE_MARKER = '### 13.2 TICKSTORE'
MAX_VALIDITY = dt.timedelta(hours=72)
# Frozen release engine ABI (tickstore_publisher_recovery_v004_release.py, POLICY_ADMISSION_SCOPE).
RECEIPT_PROVENANCE = {'project': 'PEGASUS_TICKSTORE', 'thread': 'Compress\u00e3o De Ticks 7'}
# Provenance only: superseded identities may be cited as history, never accepted as current.
HISTORICAL_POLICY_PROVENANCE = {
    'CADAF9068532EACBF4886CDE3BABE809B075480D8776AF15F3B395C31D9B2CD0': {
        'label': 'V37', 'head_sha256': '4F4D2B6028B291F9BD26C086817F56BDE22EBA4F3D8DDE54FD918EE2C92FF962',
        'revision_id': '20261011T204600-0300-CADAF9068532EACB'},
    '5B135DA0CA7C3BFE992F364720605522FB939977772C6D5A6FD3811A8288B302': {
        'label': 'V38', 'head_sha256': '2DA2939C88530B089D3E6D33418439B38A243EE776DAC151559199C2703B5BA9',
        'revision_id': '20261012T070600-0300-5B135DA0CA7C3BFE',
        'project': 'PEGASUS_TICKSTORE', 'thread': 'Compressão De Ticks 7'},
}


class PolicyBlocked(RuntimeError):
    pass


def _require(ok, reason):
    if not ok:
        raise PolicyBlocked(reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def _strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            _require(k not in out, 'POLICY_JSON_DUPLICATE_KEY:' + str(k))
            out[k] = v
        return out
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def _instant(value, name):
    try:
        t = dt.datetime.fromisoformat(str(value))
    except ValueError:
        raise PolicyBlocked('POLICY_RECONCILIATION_TIME:' + name)
    _require(t.tzinfo is not None, 'POLICY_RECONCILIATION_TIMEZONE:' + name)
    return t


def verify_capture(read, root, reconciliation_path, reconciliation_sha256, *, now=None):
    """Return the verified current-policy identity; raise PolicyBlocked otherwise.

    ``read(path, expected_sha_or_None) -> bytes`` is the caller's reader (on Windows the
    D4 Reads object, which keeps write/delete-denying handles open until revalidation).
    """
    root = Path(root)
    _require(sorted(p.name for p in root.iterdir()) == sorted([MASTER, HEAD]), 'POLICY_CARDINALITY_1_PLUS_1')
    master_raw = read(root / MASTER, None)
    head_raw = read(root / HEAD, None)
    master_sha, head_sha = _sha(master_raw), _sha(head_raw)
    _require(master_sha not in HISTORICAL_POLICY_PROVENANCE, 'POLICY_HISTORICAL_NOT_CURRENT:'
             + HISTORICAL_POLICY_PROVENANCE.get(master_sha, {}).get('label', ''))
    head = _strict_json(head_raw)
    _require(head.get('schema') == 'POLITICA_CANONICA_HEAD', 'POLICY_HEAD_SCHEMA')
    _require(head.get('master_filename') == MASTER and head.get('master_sha256') == master_sha, 'POLICY_HEAD_MASTER')
    _require(head.get('state') == 'FROZEN', 'POLICY_HEAD_NOT_FROZEN')
    _require(head.get('active_master_cardinality') == 'EXACTLY_ONE'
             and head.get('active_head_cardinality') == 'EXACTLY_ONE', 'POLICY_HEAD_CARDINALITY')
    _require(head.get('project_local_copy_operational_authority') is False, 'POLICY_CAPTURE_CLAIMS_AUTHORITY')
    revision = str(head.get('revision_id', ''))
    _require(re.fullmatch(r'[0-9]{8}T[0-9]{6}-[0-9]{4}-' + master_sha[:16], revision) is not None,
             'POLICY_REVISION_NOT_BOUND_TO_MASTER')
    _require(SCOPE_MARKER in master_raw.decode('utf-8'), 'POLICY_TICKSTORE_SCOPE')
    _require(re.fullmatch('[0-9A-F]{64}', str(reconciliation_sha256)) is not None, 'POLICY_RECONCILIATION_SHA_FORMAT')
    rec_raw = read(Path(reconciliation_path), reconciliation_sha256)
    _require(_sha(rec_raw) == reconciliation_sha256, 'POLICY_RECONCILIATION_SHA256')
    rec = _strict_json(rec_raw)
    _require(rec.get('schema') == RECONCILIATION_SCHEMA and rec.get('issuer') == 'CHATGPT_ORIGIN', 'POLICY_RECONCILIATION_SCHEMA')
    _require(rec.get('status') == 'CURRENT_AT_ORIGIN', 'POLICY_RECONCILIATION_NOT_CURRENT')
    _require((rec.get('policy_master_sha256'), rec.get('policy_head_sha256'), rec.get('policy_revision'))
             == (master_sha, head_sha, revision), 'POLICY_RECONCILIATION_BINDING')
    _require(rec.get('live_cardinality') == {'master': 1, 'head': 1} and rec.get('live_state') == 'FROZEN',
             'POLICY_RECONCILIATION_LIVE_STATE')
    _require(rec.get('capture_operational_authority') is False
             and rec.get('administrative_owner_gate_required') is False, 'POLICY_RECONCILIATION_AUTHORITY_FIELDS')
    _require(isinstance(rec.get('scope'), list) and 'D4_FIRST_ADMISSION' in rec['scope'], 'POLICY_RECONCILIATION_SCOPE')
    for key in ('routing_project', 'routing_thread'):
        _require(isinstance(rec.get(key), str) and rec[key].strip() == rec[key] and rec[key], 'POLICY_RECONCILIATION_' + key.upper())
    issued, until = _instant(rec.get('reconciled_at'), 'reconciled_at'), _instant(rec.get('valid_until'), 'valid_until')
    now = now or dt.datetime.now(dt.timezone.utc)
    _require(issued <= now <= until, 'POLICY_RECONCILIATION_EXPIRED_OR_FUTURE')
    _require(until - issued <= MAX_VALIDITY, 'POLICY_RECONCILIATION_WINDOW_TOO_LONG')
    return {'schema': 'TICKSTORE_VERIFIED_POLICY_CAPTURE_V001', 'master_sha256': master_sha, 'head_sha256': head_sha,
            'revision_id': revision, 'reconciliation_sha256': reconciliation_sha256,
            'receipt_project': RECEIPT_PROVENANCE['project'], 'receipt_thread': RECEIPT_PROVENANCE['thread'],
            'routing_project': rec['routing_project'], 'routing_thread': rec['routing_thread'],
            'valid_until': rec['valid_until'], 'capture_operational_authority': False,
            'administrative_owner_gate_required': False}


def expected_receipt_fields(capture):
    """Fields of TICKSTORE_D4_POLICY_ADMISSION_RECEIPT_V001 that must equal the verified capture."""
    return {'project': capture['receipt_project'], 'thread': capture['receipt_thread'],
            'active_master_sha256': capture['master_sha256'], 'active_head_sha256': capture['head_sha256'],
            'active_revision_id': capture['revision_id'],
            'origin_policy_reconciliation_sha256': capture['reconciliation_sha256']}
