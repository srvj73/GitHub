"""G4 source-only inert installer->transaction intent verifier.

Checks installed instance and upstream identities. NEVER writes any file, publishes
MENU, opens an active deployment, or supplies release authority. The producer
must separately enforce physical target admission, transactional locking,
independent witnessed final identity, recovery and Windows qualification.
"""
from __future__ import annotations
import hashlib
import json
import re
import stat
from pathlib import Path

SCHEMA = 'TICKSTORE_MENU_INSTALL_INTENT_V001'
MENU_REL = 'implementation_v001/candidate/menu/MENU.py'
LAUNCHER_REL = 'implementation_v001/candidate/control/RUN_TICKSTORE_FULL.ps1'
KEYS = {'schema','installation_root','package_sha256','package_manifest_sha256',
        'witness_sha256','candidate_menu_relative_path','candidate_menu_sha256',
        'active_deployment_sha256','launcher_sha256','transaction_state',
        'effectful_authorized','production_started'}
HASH = re.compile(r'[0-9A-F]{64}\Z')

class Blocked(RuntimeError):
    pass

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()

def _guard(path: Path, *, file=False) -> None:
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (getattr(info, 'st_file_attributes', 0) & 0x400):
            raise Blocked('REPARSE_PATH')
    if file:
        try:
            info = path.stat()
        except (OSError, ValueError) as exc:
            raise Blocked('MISSING_INPUT') from exc
        if not stat.S_ISREG(info.st_mode):
            raise Blocked('NOT_REGULAR_FILE')
        if info.st_nlink != 1:
            raise Blocked('HARDLINK_INPUT')

def _load(path: Path) -> tuple[dict, bytes]:
    _guard(path, file=True)
    def no_duplicate_keys(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise Blocked('INPUT_DUPLICATE_KEY')
            seen[key] = value
        return seen
    try:
        raw = path.read_bytes()
        obj = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    except (UnicodeDecodeError, OSError, ValueError) as exc:
        raise Blocked('INPUT_INVALID') from exc
    if not isinstance(obj, dict):
        raise Blocked('INPUT_NOT_OBJECT')
    return obj, raw

def verify_inert_intent(root: Path, *, trusted_package_sha256: str,
                        trusted_witness_sha256: str) -> dict:
    """Read-only check; supplied trusted hashes must come from external witness.

    No return value constitutes authority to install MENU or select deployment.
    """
    if not isinstance(trusted_package_sha256, str) or not HASH.fullmatch(trusted_package_sha256):
        raise Blocked('EXTERNAL_PACKAGE_PIN_REQUIRED')
    if not isinstance(trusted_witness_sha256, str) or not HASH.fullmatch(trusted_witness_sha256):
        raise Blocked('EXTERNAL_WITNESS_PIN_REQUIRED')
    root = Path(root).absolute()
    _guard(root)
    if (root.name != trusted_package_sha256 or root.parent.name != 'Candidates'
            or not root.is_dir()):
        raise Blocked('INSTALLATION_ROOT_BINDING')
    intent, iraw = _load(root/'MENU_INSTALL_INTENT.json')
    if set(intent) != KEYS or intent['schema'] != SCHEMA:
        raise Blocked('INTENT_SCHEMA')
    if (intent['transaction_state'] != 'NOT_STARTED'
            or intent['effectful_authorized'] is not False
            or intent['production_started'] is not False):
        raise Blocked('INTENT_PREMATURE_EFFECT')
    if (intent['installation_root'] != str(root)
            or intent['package_sha256'] != trusted_package_sha256
            or intent['witness_sha256'] != trusted_witness_sha256
            or intent['candidate_menu_relative_path'] != MENU_REL):
        raise Blocked('INTENT_EXTERNAL_BINDING')
    for key in ('package_manifest_sha256','candidate_menu_sha256',
                'active_deployment_sha256','launcher_sha256'):
        if not isinstance(intent[key], str) or not HASH.fullmatch(intent[key]):
            raise Blocked('INTENT_BAD_DIGEST')
    manifest, mraw = _load(root/'PACKAGE_MANIFEST.json')
    if _sha(mraw) != intent['package_manifest_sha256']:
        raise Blocked('MANIFEST_DIGEST')
    if manifest.get('schema') != 'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001' or not isinstance(manifest.get('files'), list):
        raise Blocked('MANIFEST_SCHEMA')
    members = {}
    for f in manifest['files']:
        if not isinstance(f,dict) or set(f) != {'path','bytes','sha256'}:
            raise Blocked('MANIFEST_MEMBER_SCHEMA')
        name=f['path']
        if not isinstance(name,str) or name in members:
            raise Blocked('MANIFEST_DUPLICATE')
        members[name]=f
    for rel, pin in ((MENU_REL,intent['candidate_menu_sha256']),
                     (LAUNCHER_REL,intent['launcher_sha256'])):
        if rel not in members or members[rel]['sha256'] != pin:
            raise Blocked('MANIFEST_MEMBER_MISMATCH')
        path = root/rel
        _guard(path,file=True)
        raw = path.read_bytes()
        if _sha(raw)!=pin or len(raw)!=members[rel]['bytes']:
            raise Blocked('INSTALLED_MEMBER_DRIFT')
    deployment, draw = _load(root/'DEPLOYMENT.json')
    if _sha(draw) != intent['active_deployment_sha256']:
        raise Blocked('DEPLOYMENT_DIGEST')
    if (deployment.get('schema') != 'TICKSTORE_DEPLOYMENT_V001'
            or deployment.get('installation_root') != str(root)
            or deployment.get('package_sha256') != trusted_package_sha256
            or deployment.get('package_manifest_sha256') != intent['package_manifest_sha256']
            or deployment.get('witness_sha256') != trusted_witness_sha256
            or deployment.get('launcher_sha256') != intent['launcher_sha256']
            or deployment.get('status') != 'INSTALLED_NOT_PRODUCTION_ADMISSION'
            or deployment.get('production_started') is not False):
        raise Blocked('DEPLOYMENT_BINDING')
    # Readback identity: detect modifications between independent reads.
    for path, pinned in ((root/'MENU_INSTALL_INTENT.json',_sha(iraw)),
                         (root/'PACKAGE_MANIFEST.json',_sha(mraw)),
                         (root/'DEPLOYMENT.json',_sha(draw))):
        _guard(path,file=True)
        if _sha(path.read_bytes()) != pinned:
            raise Blocked('READBACK_DRIFT')
    return {'schema':'TICKSTORE_INERT_INTENT_VERIFICATION_V001',
            'status':'PASS_SOURCE_ONLY_NO_EFFECT_AUTHORITY',
            'package_sha256':trusted_package_sha256,
            'intent_sha256':_sha(iraw),
            'candidate_menu_sha256':intent['candidate_menu_sha256'],
            'active_deployment_sha256':intent['active_deployment_sha256'],
            'activation_authorized':False,'production_started':False}
