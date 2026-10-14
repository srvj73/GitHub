"""RC1R1 successor migration: V002R22 -> V002R23 in the D4 resume root (R46 origin decision Option A).

SOURCE_ONLY tool shipped inside the FINAL candidate. It never runs D4, never touches STATE, the
checkpoint, the authority directory, the canonical destination or the scratch roots.

Default mode is a read-only dry run: it proves that the supplied successor ZIP is exactly the
packaging of this FINAL's candidate/recovery tree (which the B06/B07 chain covers), classifies the
installed SUCCESSOR_PACKAGE (V002R22, V002R23 or absent) and prints the plan and its blockers.

--apply additionally requires the technical release chain validated until B07 on these exact FINAL
bytes (independent B06 digest as trust anchor). The installed V002R22 package is never deleted: it
is renamed to a run-owned backup; the successor is extracted into a run-owned staging directory,
re-read and verified, then promoted by rename. A technical migration receipt is written create-new.
A crash leaves either the old package, or a backup plus a staging directory; re-running resumes
from that state and never deletes anything.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath

HOME = Path(__file__).resolve().parent
CANDIDATE = HOME.parent
REPORT_SCHEMA = 'TICKSTORE_RC1R1_SUCCESSOR_MIGRATION_REPORT_V001'
RECEIPT_SCHEMA = 'TICKSTORE_RC1R1_SUCCESSOR_MIGRATION_RECEIPT_V001'
DEFAULT_RESUME_ROOT = r'D:\Base CSV\Scripts\TICKSTORE_R9_DEV\TICKSTORE_D4_RESUMABLE_V002R22'
SUCCESSOR_ZIP_NAME = 'TICKSTORE_V004R1_D4_RESUMABLE_V002R23_PACKAGE.zip'
SUCCESSOR_ZIP_SHA256 = '5B1D8338D26F407A043665636EA79300AD6E4C79FDFE3397CE1CC79FDBD9656F'
REVIEW_PACK_NAME = 'TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R23.zip'
REVIEW_PACK_SHA256 = 'EC281FEAC71A0A9EF79D4A98C6FA3533EC40F9B3359C4243F296971A1A14A03E'
PARENT_RELEASE_SHA256 = 'BFC44DA9A375ED565D8DA2DA7E34EC376C25DEAFE15ED2F3C063CE635CEBCD4C'
PARENT_PACKAGE_MANIFEST_SHA256 = '5199C7B03A442F0D33C1250E3E2A68A5A213377E012A902336502453CAAA18D6'
RELEASE_REL = 'engine/tickstore_publisher_recovery_v004_release.py'
PACKAGE = 'SUCCESSOR_PACKAGE'
BACKUP_PREFIX = 'SUCCESSOR_PACKAGE.V002R22_BACKUP.'
STAGING_PREFIX = 'SUCCESSOR_PACKAGE.V002R23_STAGING.'
ROUTE = 'ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 15'


class Blocked(RuntimeError):
    pass


def require(cond, why):
    if not cond:
        raise Blocked(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'JSON_DUPLICATE_KEY:' + str(k))
            out[k] = v
        return out
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def safe_member(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and not name.endswith('/'),
            'SUCCESSOR_MEMBER_PATH:' + repr(name))
    rel = PurePosixPath(name)
    require(not rel.is_absolute() and all(p not in ('', '.', '..') for p in name.split('/'))
            and all(re.search(r'[\x00-\x1f<>"|?*]', p) is None and not p.endswith((' ', '.')) for p in rel.parts),
            'SUCCESSOR_MEMBER_PATH:' + name)
    return rel.parts


def tree(root):
    root = Path(root)
    out = {}
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(), 'REPARSE_OR_SYMLINK:' + str(p))
        if p.is_file() and '__pycache__' not in p.parts:
            out[p.relative_to(root).as_posix()] = p
    return out


def read_successor_zip(path, recovery_root):
    raw = Path(path).read_bytes()
    require(sha(raw) == SUCCESSOR_ZIP_SHA256, 'SUCCESSOR_ZIP_SHA256')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(z.testzip() is None, 'SUCCESSOR_ZIP_CRC')
        names = z.namelist()
        require(len(names) == len(set(names)) and len({n.casefold() for n in names}) == len(names), 'SUCCESSOR_ZIP_DUPLICATE')
        members = {n: z.read(n) for n in names}
    for n in members:
        safe_member(n)
    manifest = strict_json(members['99_MANIFEST_SHA256.json'])
    listed = {r['path']: r for r in manifest['files']}
    require(set(listed) | {'99_MANIFEST_SHA256.json'} == set(members), 'SUCCESSOR_ZIP_CLOSED_SET')
    for p, r in listed.items():
        require(sha(members[p]) == r['sha256'] and len(members[p]) == r['bytes'], 'SUCCESSOR_ZIP_MEMBER:' + p)
    # The successor is the packaging of this FINAL's candidate/recovery tree, which B06/B07 cover.
    local = tree(recovery_root)
    require(set(local) == set(members), 'SUCCESSOR_NOT_EQUAL_TO_FINAL_RECOVERY_TREE')
    for p, q in local.items():
        require(q.read_bytes() == members[p], 'SUCCESSOR_FINAL_BYTES:' + p)
    return raw, members, manifest


def classify(pkg, members):
    if not os.path.lexists(pkg):
        return 'ABSENT'
    require(pkg.is_dir() and not pkg.is_symlink(), 'SUCCESSOR_ROOT_NOT_DIRECTORY')
    files = tree(pkg)
    if set(files) == set(members) and all(files[p].read_bytes() == members[p] for p in files):
        return 'V002R23'
    release = files.get(RELEASE_REL)
    if (release is not None and sha(release.read_bytes()) == PARENT_RELEASE_SHA256
            and sum(1 for p in files.values() if p.suffix.lower() == '.json'
                    and sha(p.read_bytes()) == PARENT_PACKAGE_MANIFEST_SHA256) == 1):
        return 'V002R22'
    return 'UNKNOWN'


def inspect(resume_root, successor_zip, recovery_root=None):
    rr = Path(resume_root)
    require(rr.is_dir() and not rr.is_symlink(), 'RESUME_ROOT_MISSING')
    zraw, members, manifest = read_successor_zip(successor_zip, recovery_root or CANDIDATE / 'recovery')
    state = classify(rr / PACKAGE, members)
    names = sorted(x.name for x in rr.iterdir())
    backups = [n for n in names if n.startswith(BACKUP_PREFIX)]
    staging = [n for n in names if n.startswith(STAGING_PREFIX)]
    authority = rr / 'authority'
    admitted = (authority / 'RUN_AUTHORITY.json').exists()
    pending = sorted(x.name for x in authority.glob('RUN_AUTHORITY.json.tmp.*')) if authority.is_dir() else []
    art = rr / 'artifacts' / SUCCESSOR_ZIP_NAME
    blockers = []
    if state == 'UNKNOWN':
        blockers.append('SUCCESSOR_PACKAGE_UNKNOWN_CONTENT')
    if state == 'ABSENT' and not backups:
        blockers.append('SUCCESSOR_PACKAGE_ABSENT_WITHOUT_V002R22_BACKUP')
    if admitted:
        blockers.append('ADMITTED_RUN_AUTHORITY_PRESENT_REQUIRES_ORIGIN_DECISION')
    if pending:
        blockers.append('AUTHORITY_PENDING_FILES_REQUIRE_DIAGNOSIS')
    if art.exists() and sha(art.read_bytes()) != SUCCESSOR_ZIP_SHA256:
        blockers.append('ARTIFACT_ZIP_PRESENT_WITH_OTHER_BYTES')
    plan = []
    if state == 'V002R22':
        plan.append('RENAME_V002R22_TO_BACKUP')
    if state in ('V002R22', 'ABSENT'):
        plan += ['EXTRACT_TO_STAGING_AND_VERIFY', 'PROMOTE_STAGING_BY_RENAME']
    if not art.exists():
        plan.append('COPY_SUCCESSOR_ZIP_TO_ARTIFACTS')
    if state == 'V002R23' and art.exists():
        plan.append('NO_OP_ALREADY_MIGRATED')
    plan.append('WRITE_MIGRATION_RECEIPT')
    return {'schema': REPORT_SCHEMA, 'mode': 'DRY_RUN', 'resume_root': str(rr), 'installed_state': state,
            'successor_zip': str(Path(successor_zip)), 'successor_zip_sha256': sha(zraw),
            'successor_manifest_sha256': sha(members['99_MANIFEST_SHA256.json']),
            'successor_release_sha256': sha(members[RELEASE_REL]), 'successor_members': len(members),
            'not_carried_from_parent': len(manifest.get('not_carried_from_parent', [])),
            'existing_backups': backups, 'existing_staging_left_untouched': staging,
            'admitted_run_authority_present': admitted, 'checkpoint_present': (rr / 'checkpoint').exists(),
            'artifact_zip_present': art.exists(), 'plan': plan, 'blockers': blockers,
            'status': 'BLOCKED' if blockers else 'READY', 'effects': [],
            'touches_state_checkpoint_authority_dest_or_scratch': False}, members, zraw


def native_windows():
    return os.name == 'nt'


def write_new(path, raw):
    with open(path, 'xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())


def apply(report, members, zraw, review_raw=None, run_id=None, now=None):
    require(report['status'] == 'READY' and not report['blockers'], 'MIGRATION_BLOCKED:' + ','.join(report['blockers']))
    run_id = run_id or uuid.uuid4().hex.upper()
    rr = Path(report['resume_root']); pkg = rr / PACKAGE; effects = []
    state = report['installed_state']
    backup = None
    if state == 'V002R22':
        backup = rr / (BACKUP_PREFIX + run_id)
        os.rename(pkg, backup); effects.append({'rename': str(pkg), 'to': str(backup)})
    if state in ('V002R22', 'ABSENT'):
        stage = rr / (STAGING_PREFIX + run_id)
        stage.mkdir()
        for name, raw in sorted(members.items()):
            target = stage.joinpath(*safe_member(name))
            target.parent.mkdir(parents=True, exist_ok=True)
            write_new(target, raw)
        staged = tree(stage)
        require(set(staged) == set(members) and all(staged[p].read_bytes() == members[p] for p in staged),
                'STAGING_READBACK')
        require(not os.path.lexists(pkg), 'SUCCESSOR_PACKAGE_APPEARED_DURING_MIGRATION')
        os.rename(stage, pkg); effects.append({'rename': str(stage), 'to': str(pkg)})
    require(classify(pkg, members) == 'V002R23', 'PROMOTED_PACKAGE_READBACK')
    art_dir = rr / 'artifacts'; art_dir.mkdir(exist_ok=True)
    for name, raw, digest in ((SUCCESSOR_ZIP_NAME, zraw, SUCCESSOR_ZIP_SHA256), (REVIEW_PACK_NAME, review_raw, REVIEW_PACK_SHA256)):
        if raw is None:
            continue
        require(sha(raw) == digest, 'ARTIFACT_SHA256:' + name)
        target = art_dir / name
        if target.exists():
            require(sha(target.read_bytes()) == digest, 'ARTIFACT_PRESENT_WITH_OTHER_BYTES:' + name)
        else:
            write_new(target, raw); effects.append({'created': str(target), 'sha256': digest})
    receipt = dict(report, mode='APPLIED', status='APPLIED', run_id=run_id, effects=effects,
                   backup=str(backup) if backup else None,
                   applied_at=(now or dt.datetime.now(dt.timezone.utc)).isoformat(),
                   schema=RECEIPT_SCHEMA, route=ROUTE)
    receipt.pop('plan', None)
    out = rr / 'migration' / run_id
    out.mkdir(parents=True)
    raw = (json.dumps(receipt, indent=1, sort_keys=True) + '\n').encode('utf-8')
    write_new(out / 'MIGRATION_RECEIPT.json', raw)
    receipt['receipt_path'] = str(out / 'MIGRATION_RECEIPT.json'); receipt['receipt_sha256'] = sha(raw)
    return receipt


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.splitlines()[0])
    ap.add_argument('--resume-root', default=DEFAULT_RESUME_ROOT)
    ap.add_argument('--successor-zip', required=True)
    ap.add_argument('--review-pack')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--chain-file'); ap.add_argument('--chain-sha256'); ap.add_argument('--b06-sha256')
    a = ap.parse_args(argv)
    try:
        report, members, zraw = inspect(a.resume_root, a.successor_zip)
        if not a.apply:
            print(json.dumps(report, indent=1, sort_keys=True))
            print('RC1R1_MIGRATION_DRY_RUN=' + report['status'])
            return 0 if report['status'] == 'READY' else 2
        require(native_windows(), 'NATIVE_WINDOWS_REQUIRED')
        require(all((a.chain_file, a.chain_sha256, a.b06_sha256)), 'APPLY_REQUIRES_RELEASE_CHAIN_UNTIL_B07')
        review_raw = Path(a.review_pack).read_bytes() if a.review_pack else None
        sys.path.insert(0, str(HOME))
        from FULL_RELEASE_CHAIN import ReleaseChain
        # Pins on the FINAL code and on every receipt are held while the package is replaced.
        with ReleaseChain(a.chain_file, a.chain_sha256, a.b06_sha256, CANDIDATE, until='B07') as chain:
            report['chain_receipt_sha256'] = chain.receipt_sha
            receipt = apply(report, members, zraw, review_raw)
            chain.revalidate()
        print(json.dumps(receipt, indent=1, sort_keys=True))
        print('RC1R1_MIGRATION=APPLIED')
        return 0
    except RuntimeError as e:  # this tool's Blocked and the release chain's Blocked
        print('RC1R1_MIGRATION=BLOCKED')
        print('REASON=' + str(e))
        return 2
    finally:
        print('RESULT_RETURN_TO=' + ROUTE)


if __name__ == '__main__':
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log('RC1R1_MIGRATION', main))
