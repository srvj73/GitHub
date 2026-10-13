"""G4 source-only official-writer contract and cross-volume crash-state table.

This module HAS NO installation, mutation, CLI, activation or native write API.
It binds the independent Windows read-only target receipt, installed intent,
canonical policy identity, and a two-volume layout. A PASS is a blueprint for
writing/qualifying an official writer, NEVER authorization to publish it.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import re
from dataclasses import dataclass

from MENU_OFFICIAL_ADMISSION_READONLY import (
    MENU, BAT, MENU_SHA, BAT_SHA, CANDIDATE_MENU_SHA, SOURCE_POLICY_SHA,
    SCHEMA as OBS_SCHEMA, Blocked as AdmissionBlocked,
)

HEX64 = re.compile(r'[0-9A-F]{64}\Z')
SCHEMA = 'TICKSTORE_G4_OFFICIAL_WRITER_CONTRACT_SOURCE_ONLY_V001'
INTENT_SCHEMA = 'TICKSTORE_INERT_INTENT_VERIFICATION_V001'
TX_SCHEMA = 'TICKSTORE_MENU_INSTALL_TRANSACTION_V001'
PHASES = ('PREPARED', 'MENU_PUBLISHED', 'ACTIVE_PUBLISHED', 'COMMITTED', 'ROLLED_BACK')

class Blocked(ValueError):
    pass


def _hash(x):
    return isinstance(x, str) and HEX64.fullmatch(x) is not None


def _require(condition, error):
    if not condition:
        raise Blocked(error)


def canonical_json(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def _absolute_localappdata(value):
    _require(isinstance(value, str) and re.fullmatch(r'[A-Za-z]:\\[^%]+', value) is not None,
             'LOCALAPPDATA_INVALID')
    norm = ntpath.normpath(value)
    _require(norm.casefold() == value.casefold() and not value.endswith('\\'), 'LOCALAPPDATA_NOT_CANONICAL')
    _require(ntpath.splitdrive(norm)[0].casefold() != ntpath.splitdrive(MENU)[0].casefold(),
             'CROSS_VOLUME_LAYOUT_NOT_PROVEN')
    return norm


def prepare_source_only(*, windows_receipt, installed_intent_verification,
                        local_appdata, policy_master_sha256):
    """Compose an inert layout with independent source pins; never acquire write authority.

    The Windows receipt is historical, not a JIT admission under a writer lock.
    A writer MUST re-probe live under its own lock and preserve backup/readback.
    """
    _require(_hash(policy_master_sha256) and policy_master_sha256 == SOURCE_POLICY_SHA,
             'ACTIVE_POLICY_DRIFT_OR_MISSING')
    app = _absolute_localappdata(local_appdata)
    _require(isinstance(windows_receipt, dict), 'WINDOWS_RECEIPT_TYPE')
    _require(set(windows_receipt) == {'verdict','observation'}, 'WINDOWS_RECEIPT_FIELDS')
    verdict, observation = windows_receipt['verdict'], windows_receipt['observation']
    _require(isinstance(verdict, dict) and verdict.get('schema') == OBS_SCHEMA
             and verdict.get('status') == 'PASS_READONLY_IDENTITY_ONLY'
             and verdict.get('effects_authorized') is False
             and verdict.get('production_modified') is False
             and verdict.get('full_started') is False, 'WINDOWS_RECEIPT_NOT_READONLY_PASS')
    _require(verdict.get('menu_before_sha256') == MENU_SHA
             and verdict.get('bat_sha256') == BAT_SHA
             and verdict.get('candidate_menu_sha256') == CANDIDATE_MENU_SHA
             and verdict.get('policy_master_sha256_source') == SOURCE_POLICY_SHA,
             'WINDOWS_RECEIPT_BINDING')
    # Reapply existing pure validation, including paths, reparse, hardlinks, target absence.
    from MENU_OFFICIAL_ADMISSION_READONLY import validate_observation
    try:
        independent = validate_observation(observation, local_appdata=app)
    except AdmissionBlocked as exc:
        # Keep one machine-readable error type across module boundaries, while
        # preserving the original reason for negative controls.
        raise Blocked(str(exc)) from exc
    _require(independent == verdict, 'WINDOWS_RECEIPT_OBSERVATION_DIVERGENCE')
    _require(isinstance(installed_intent_verification, dict)
             and installed_intent_verification.get('schema') == INTENT_SCHEMA
             and installed_intent_verification.get('status') == 'PASS_SOURCE_ONLY_NO_EFFECT_AUTHORITY'
             and installed_intent_verification.get('activation_authorized') is False
             and installed_intent_verification.get('production_started') is False,
             'INSTALLED_INTENT_INELIGIBLE')
    for key in ('package_sha256','intent_sha256','candidate_menu_sha256','active_deployment_sha256'):
        _require(_hash(installed_intent_verification.get(key)), 'INSTALLED_INTENT_HASH_'+key.upper())
    _require(installed_intent_verification['candidate_menu_sha256'] == CANDIDATE_MENU_SHA,
             'MENU_CANDIDATE_NOT_SAME_BYTES')
    pkg = installed_intent_verification['package_sha256']
    active_root = ntpath.join(app, 'TICKSTORE')
    candidate_root = ntpath.join(active_root, 'Candidates', pkg)
    # Backups and temporary MENU artifacts must be on D:, adjacent to MENU.
    # ACTIVE and transaction records belong to C: (LOCALAPPDATA).
    token = pkg[:16]
    menu_parent = ntpath.dirname(MENU)
    plan = {
        'schema': TX_SCHEMA,
        'menu_before_sha256': MENU_SHA,
        'menu_after_sha256': CANDIDATE_MENU_SHA,
        'active_before_sha256': None,
        'active_after_sha256': installed_intent_verification['active_deployment_sha256'],
    }
    artifact_paths = {
        'menu': MENU,
        'bat_readonly': BAT,
        'menu_pending_same_volume': ntpath.join(menu_parent, '.TICKSTORE_MENU_' + token + '.pending'),
        'menu_backup_same_volume': ntpath.join(menu_parent, '.TICKSTORE_MENU_' + token + '.backup'),
        'active_root': active_root,
        'active': ntpath.join(active_root, 'ACTIVE_DEPLOYMENT.json'),
        'active_pending_same_volume': ntpath.join(active_root, '.TICKSTORE_ACTIVE_' + token + '.pending'),
        'transaction': ntpath.join(active_root, 'MENU_TRANSACTION'),
        'journal': ntpath.join(active_root, 'MENU_TRANSACTION', 'JOURNAL.json'),
        'plan': ntpath.join(active_root, 'MENU_TRANSACTION', 'PLAN.json'),
        'installed_candidate_root': candidate_root,
    }
    _require(ntpath.splitdrive(artifact_paths['menu_backup_same_volume'])[0].casefold() == ntpath.splitdrive(MENU)[0].casefold()
             and ntpath.splitdrive(artifact_paths['active_pending_same_volume'])[0].casefold() == ntpath.splitdrive(app)[0].casefold(),
             'BACKUP_VOLUME_BINDING')
    _require(verdict.get('active_target_status') == 'ABSENT', 'ACTIVE_PREEXISTING')
    return {
        'schema': SCHEMA,
        'status': 'PASS_SOURCE_ONLY_LAYOUT_NOT_EFFECT_AUTHORITY',
        'effectful_authorized': False,
        'production_modified': False,
        'full_started': False,
        'historical_windows_receipt_not_live_writer_admission': True,
        'precommit_live_readmission_under_lock_required': True,
        'native_acl_backup_persistence_and_recovery_pending': True,
        'package_sha256': pkg,
        'intent_sha256': installed_intent_verification['intent_sha256'],
        'policy_master_sha256': SOURCE_POLICY_SHA,
        'plan': plan,
        'plan_sha256': sha(canonical_json(plan)),
        'paths': artifact_paths,
    }


def recovery_decision(phase, *, menu_digest, active_digest, plan):
    """Pure phase classification only; no filesystem actions or automatic successor.

    Drift is always BLOCKED, even if journal says COMMITTED. Never infer COMMITTED
    solely from both destination files containing the candidate bytes.
    """
    _require(phase in PHASES, 'UNKNOWN_PHASE')
    _require(isinstance(plan, dict) and set(plan) == {
        'schema', 'menu_before_sha256','menu_after_sha256','active_before_sha256','active_after_sha256'
    } and plan.get('schema') == TX_SCHEMA, 'PLAN_NOT_EXACT')
    # A recovery classification cannot trust an unbound or degenerate plan.
    # Otherwise arbitrary identical values (including None) could make COMMITTED
    # appear valid without physical target hashes or a real state transition.
    _require(_hash(plan['menu_before_sha256'])
             and _hash(plan['menu_after_sha256'])
             and _hash(plan['active_after_sha256'])
             and (plan['active_before_sha256'] is None
                  or _hash(plan['active_before_sha256'])), 'PLAN_HASH_INVALID')
    _require(plan['menu_before_sha256'] != plan['menu_after_sha256']
             and plan['active_before_sha256'] != plan['active_after_sha256'],
             'PLAN_NOT_TRANSITION')
    _require(menu_digest in (plan['menu_before_sha256'], plan['menu_after_sha256']), 'MENU_TARGET_DRIFT')
    _require(active_digest in (plan['active_before_sha256'], plan['active_after_sha256']), 'ACTIVE_TARGET_DRIFT')
    if phase == 'COMMITTED':
        _require(menu_digest == plan['menu_after_sha256']
                 and active_digest == plan['active_after_sha256'], 'COMMITTED_READBACK_FAILED')
        return 'RECONCILE_COMMITTED_WITH_FULL_EVIDENCE_ONLY'
    if phase == 'ROLLED_BACK':
        _require(menu_digest == plan['menu_before_sha256']
                 and active_digest == plan['active_before_sha256'], 'ROLLBACK_READBACK_FAILED')
        return 'RECONCILE_ROLLED_BACK_WITH_FULL_EVIDENCE_ONLY'
    return 'BLOCK_NEW_ATTEMPTS_REQUIRE_LOCKED_RECOVERY'
