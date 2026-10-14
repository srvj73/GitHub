"""CHECKPOINT_POWERLOSS_RECOVERY physical lab tooling — SOURCE_ONLY, never run on the production PC.

Origin decision 20261014: physical power loss of the storage is mandatory; process death,
Job Objects, TerminateProcess or VM power-off are NOT equivalent.  This file only prepares
the separate-laboratory experiment.  It never cuts power itself: the cut is performed by
the operator with an EXTERNAL, isolable supply and recorded by an EXTERNAL logger.

Subcommands
  preflight   read-only isolation/risk gate on the LAB machine (refuses the production PC,
              system/production volumes, missing sacrificial sentinel, missing external
              logger declaration and missing SEPARATE user authorization for the cut).
  plan        deterministic, seeded schedule of cut windows + uninterrupted control rounds.
  arm         workload on the sacrificial volume that holds inside the requested transaction
              window and announces READY_TO_CUT (beacon fsync'd); refuses without a PASS preflight.
  inspect     after controlled power-on, read-only inspection BEFORE any resume (NTFS dirty bit,
              outputs, journals, locks, checkpoint, live processes) -> round receipt.
  reconcile   after the product's own resume, compare against the control and classify the round.

Every ambiguity is BLOCKED, never PASS.  Status without an identified lab:
PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

# Production identity observed natively in R43/R44 (QUAL_RECEIPT PRECHECK): the lab must not be this PC.
PRODUCTION_VOLUME_SERIALS = {'C4B23CE5', '7435A171'}
PRODUCTION_PATH_MARKERS = (r'D:\Base CSV', r'\TICKSTORE\ACTIVE_DEPLOYMENT.json')
SENTINEL_NAME = 'TICKSTORE_POWERLOSS_SACRIFICIAL_VOLUME.txt'
SENTINEL_TEXT = 'SACRIFICIAL NTFS VOLUME FOR TICKSTORE PHYSICAL POWERLOSS LAB. ALL DATA MAY BE DESTROYED.'
WINDOWS = ('PRE_COMMIT_WRITE', 'POST_COMMIT_PRE_CHECKPOINT', 'JOURNAL_RECEIPT_UPDATE')
AUTH_SCHEMA = 'TICKSTORE_PHYSICAL_POWERLOSS_USER_AUTHORIZATION_V001'
LOGGER_SCHEMA = 'TICKSTORE_PHYSICAL_POWERLOSS_EXTERNAL_LOGGER_V001'
ROUND_SCHEMA = 'TICKSTORE_PHYSICAL_POWERLOSS_ROUND_RECEIPT_V001'


class LabBlocked(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise LabBlocked(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def canonical(obj):
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, default=str) + '\n').encode('utf-8')


# ----------------------------------------------------------------------------- environment probes (injectable)

class Env:
    """Read-only observations; tests inject a fake."""
    def volumes(self):
        import ctypes, string
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        out = {}
        for letter in string.ascii_uppercase:
            root = letter + ':\\'
            if not os.path.exists(root):
                continue
            fs = ctypes.create_unicode_buffer(261); label = ctypes.create_unicode_buffer(261); serial = ctypes.c_uint32()
            if k.GetVolumeInformationW(root, label, 261, ctypes.byref(serial), None, None, fs, 261):
                out[letter] = {'serial': '%08X' % serial.value, 'filesystem': fs.value, 'label': label.value}
        return out

    def system_drive(self):
        return os.environ.get('SystemDrive', 'C:')[0].upper()

    def pagefile_drives(self):
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management')
            vals = winreg.QueryValueEx(k, 'PagingFiles')[0]
            return {v.strip()[0].upper() for v in vals if v.strip() and v.strip()[1:2] == ':'}
        except OSError:
            return set()

    def read(self, path):
        return Path(path).read_bytes()

    def exists(self, path):
        return os.path.exists(path)


# ----------------------------------------------------------------------------- preflight

def preflight(volume, logger_path, logger_sha, auth_path, auth_sha, env=None, now=None):
    """Return the preflight record; raises LabBlocked on any isolation/authorization gap."""
    env = env or Env()
    now = now or time.time()
    v = str(volume).rstrip(':\\').upper()
    require(re.fullmatch('[A-Z]', v) is not None, 'LAB_VOLUME_LETTER')
    vols = env.volumes()
    require(not (PRODUCTION_VOLUME_SERIALS & {x['serial'] for x in vols.values()}),
            'LAB_IS_PRODUCTION_PC_OR_HAS_PRODUCTION_DISK_ATTACHED')
    require(not any(env.exists(m) for m in PRODUCTION_PATH_MARKERS), 'LAB_HAS_PRODUCTION_TICKSTORE_PATHS')
    require(v in vols, 'LAB_VOLUME_ABSENT')
    require(vols[v]['filesystem'] == 'NTFS', 'LAB_VOLUME_NOT_NTFS')
    require(v != env.system_drive(), 'LAB_VOLUME_IS_SYSTEM_DRIVE')
    require(v not in env.pagefile_drives(), 'LAB_VOLUME_HAS_PAGEFILE')
    require(v not in ('C', 'D'), 'LAB_VOLUME_LETTER_RESERVED_C_D')
    require('TICKSTORE_POWERLOSS' in vols[v]['label'].upper(), 'LAB_VOLUME_LABEL_NOT_SACRIFICIAL')
    sentinel = v + ':\\' + SENTINEL_NAME
    require(env.exists(sentinel) and env.read(sentinel).decode('utf-8', 'replace').strip() == SENTINEL_TEXT,
            'LAB_SACRIFICIAL_SENTINEL_MISSING')
    lraw = env.read(logger_path)
    require(sha(lraw) == logger_sha, 'LAB_LOGGER_DECLARATION_SHA')
    logger = json.loads(lraw)
    require(logger.get('schema') == LOGGER_SCHEMA and logger.get('outside_equipment_under_test') is True
            and logger.get('records') == ['cut_instant', 'restore_instant', 'round_id', 'supply_state'],
            'LAB_EXTERNAL_LOGGER_DECLARATION')
    araw = env.read(auth_path)
    require(sha(araw) == auth_sha, 'LAB_USER_AUTHORIZATION_SHA')
    auth = json.loads(araw)
    require(auth.get('schema') == AUTH_SCHEMA and auth.get('issuer') == 'OWNER_USER'
            and auth.get('authorizes') == 'PHYSICAL_POWER_INTERRUPTION_OF_SEPARATE_LAB_ONLY'
            and auth.get('lab_volume_serial') == vols[v]['serial']
            and auth.get('production_pc') is False, 'PHYSICAL_POWERLOSS_EXECUTION_NOT_AUTHORIZED')
    require(float(auth.get('valid_until_unix', 0)) >= now, 'PHYSICAL_POWERLOSS_AUTHORIZATION_EXPIRED')
    return {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_PREFLIGHT_V001', 'status': 'PASS', 'volume': v,
            'volume_serial': vols[v]['serial'], 'logger_sha256': logger_sha, 'authorization_sha256': auth_sha,
            'volumes_seen': sorted(vols), 'production_serials_absent': True}


# ----------------------------------------------------------------------------- plan

def plan(seed, repetitions=3, controls=2, hold_range=(2.0, 20.0)):
    """Deterministic schedule: every window x repetitions cut rounds, plus uninterrupted controls."""
    rnd = random.Random(int(seed))
    rounds = []
    for w in WINDOWS:
        for i in range(repetitions):
            rounds.append({'round_id': '%s_%02d' % (w, i + 1), 'window': w, 'cut': True,
                           'hold_seconds': round(rnd.uniform(*hold_range), 3), 'fixture_seed': rnd.randrange(1 << 30)})
    for i in range(controls):
        rounds.append({'round_id': 'CONTROL_%02d' % (i + 1), 'window': None, 'cut': False, 'hold_seconds': 0.0,
                       'fixture_seed': rnd.randrange(1 << 30)})
    rnd.shuffle(rounds)
    body = {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_PLAN_V001', 'seed': int(seed), 'windows': list(WINDOWS),
            'rounds': rounds}
    body['plan_sha256'] = sha(canonical({k: v for k, v in body.items() if k != 'plan_sha256'}))
    return body


# ----------------------------------------------------------------------------- inspection / reconciliation

def classify_inspection(obs):
    """Pre-resume state after power-on.  obs: dict from the native inspector (or a test)."""
    reasons = []
    if obs.get('live_tickstore_processes'):
        reasons.append('LIVE_PROCESSES_AFTER_POWER_ON')
    if obs.get('ntfs_dirty') is None:
        reasons.append('NTFS_DIRTY_STATE_UNKNOWN')
    if obs.get('external_logger_cut_recorded') is not True:
        reasons.append('EXTERNAL_CUT_NOT_EVIDENCED')
    if obs.get('round_id') != obs.get('logger_round_id'):
        reasons.append('LOGGER_ROUND_MISMATCH')
    for c in obs.get('containers', []):
        if c.get('status') not in ('COMMITTED_VERIFIED', 'ABSENT', 'PARTIAL_UNCOMMITTED'):
            reasons.append('AMBIGUOUS_CONTAINER:' + str(c.get('date_key')))
    if obs.get('checkpoint_parse') not in ('VALID', 'ABSENT'):
        reasons.append('CHECKPOINT_UNREADABLE_OR_TORN')
    return ('INSPECTED_READY_FOR_PRODUCT_RESUME' if not reasons else 'BLOCKED'), reasons


def reconcile_round(control_containers, resumed_containers, resume_outcome, inspection_status):
    """Final classification after the product's own resume.  Anything not exact is not PASS."""
    reasons = []
    if inspection_status != 'INSPECTED_READY_FOR_PRODUCT_RESUME':
        reasons.append('INSPECTION_NOT_CLEAN')
    if resume_outcome not in ('PASS', 'FAIL_CLOSED_RECONCILIATION_REQUIRED'):
        reasons.append('RESUME_OUTCOME_UNEXPECTED:' + str(resume_outcome))
    if resume_outcome == 'PASS':
        if set(resumed_containers) != set(control_containers):
            reasons.append('CONTAINER_SET_DIFFERS_LOSS_OR_DUPLICATE')
        diff = sorted(k for k in control_containers if resumed_containers.get(k) != control_containers[k])
        if diff:
            reasons.append('CONTAINER_BYTES_DIFFER:' + ','.join(diff[:5]))
    status = 'ROUND_PASS' if not reasons and resume_outcome == 'PASS' else (
        'ROUND_FAIL_CLOSED' if not reasons else 'ROUND_BLOCKED')
    return status, reasons


def round_receipt(plan_body, rnd, preflight_rec, inspection, reconciliation, artifacts):
    return {'schema': ROUND_SCHEMA, 'plan_sha256': plan_body['plan_sha256'], 'round': rnd,
            'preflight_sha256': sha(canonical(preflight_rec)), 'inspection': inspection,
            'reconciliation': reconciliation, 'artifacts': artifacts, 'physical_power_interruption': rnd['cut'],
            'equivalent_to_process_death': False, 'gate_verdict_issued': False}


def environment_status(lab_identified=False):
    return {'schema': 'TICKSTORE_PHYSICAL_POWERLOSS_ENVIRONMENT_V001',
            'PHYSICAL_POWERLOSS_ENVIRONMENT': 'IDENTIFIED_PENDING_PREFLIGHT' if lab_identified else 'NOT_AVAILABLE',
            'status': 'BLOCKED', 'execution_authorized': False,
            'reason': 'No isolated laboratory machine with an externally isolable supply and a sacrificial NTFS '
                      'volume has been identified; the origin specification does not authorize execution.'}


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('preflight')
    for k in ('volume', 'logger', 'logger-sha256', 'authorization', 'authorization-sha256', 'out'):
        p.add_argument('--' + k, required=True)
    q = sub.add_parser('plan'); q.add_argument('--seed', required=True, type=int); q.add_argument('--out', required=True)
    s = sub.add_parser('status'); s.add_argument('--out', required=True)
    for name in ('arm', 'inspect', 'reconcile'):
        sub.add_parser(name)
    a = ap.parse_args(argv)
    if a.cmd in ('arm', 'inspect', 'reconcile'):
        # Workload/inspector bodies stay unwired until the lab is identified, the preflight passes,
        # and the owner signs the separate authorization; they then bind the frozen candidate bytes.
        print('PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED (%s not enabled in SOURCE_ONLY)' % a.cmd)
        return 2
    if a.cmd == 'status':
        Path(a.out).write_bytes(canonical(environment_status())); print('PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED')
        return 2
    if a.cmd == 'plan':
        Path(a.out).write_bytes(canonical(plan(a.seed))); print('PLAN_WRITTEN'); return 0
    try:
        rec = preflight(a.volume, a.logger, a.logger_sha256, a.authorization, a.authorization_sha256)
    except (LabBlocked, OSError, ValueError) as exc:
        print('LAB_PREFLIGHT_BLOCKED=' + str(exc)); return 2
    with open(a.out, 'xb') as f:
        f.write(canonical(rec))
    print('LAB_PREFLIGHT=PASS'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
