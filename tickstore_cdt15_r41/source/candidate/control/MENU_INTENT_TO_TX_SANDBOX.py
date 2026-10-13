"""CDT15 G4 — inert intent -> producer fixture binding; SANDBOX_ONLY.

Not a production writer, not a Windows admission/lease/ACL implementation.
Requires a disposable, sentinel-marked sandbox. Does not accept arbitrary
publish targets; it stages two files ONLY within the sandbox candidate dir.
"""
from __future__ import annotations
from pathlib import Path
from MENU_INSTALL_INTENT_VERIFY import verify_inert_intent, Blocked as IntentBlocked, MENU_REL
from TX_SANDBOX_MODEL import (SandboxedTransaction, Blocked, guard, read_pinned,
                               write_once, sha)


def stage_verified_inert_intent(*, installed_root: Path, sandbox_root: Path,
                                trusted_package_sha256: str,
                                trusted_witness_sha256: str,
                                expected_old_menu_sha256: str,
                                expected_old_active_sha256: str | None) -> dict:
    """Only stage a disposable fixture after verifying installed request + old pins.

    The caller-supplied trusted hashes are NOT discovered or authorized here;
    effectful admission, mutual exclusion and native durability remain absent.
    """
    root = Path(sandbox_root)
    if root.name != 'CDT15_G4_TXN_SANDBOX_INTENT':
        raise Blocked('INTENT_SANDBOX_EXACT_NAME_REQUIRED')
    txn = SandboxedTransaction(root)
    txn._check_layout()
    if txn.tx.exists():
        raise Blocked('PRIOR_TRANSACTION_PRESENT')
    if txn.new_menu.exists() or txn.new_active.exists():
        raise Blocked('SANDBOX_CANDIDATE_ALREADY_STAGED')
    for path in (txn.new_menu, txn.new_active):
        guard(path, file=True)
    verified = verify_inert_intent(installed_root,
         trusted_package_sha256=trusted_package_sha256,
         trusted_witness_sha256=trusted_witness_sha256)
    # The old target identities are independently pinned by the fixture caller.
    old_menu = read_pinned(txn.menu, expected_old_menu_sha256)
    old_active = read_pinned(txn.active, expected_old_active_sha256)
    if old_menu is None:
        raise Blocked('OLD_MENU_MUST_EXIST')
    menu_src = Path(installed_root) / MENU_REL
    active_src = Path(installed_root) / 'DEPLOYMENT.json'
    menu_raw = read_pinned(menu_src, verified['candidate_menu_sha256'])
    active_raw = read_pinned(active_src, verified['active_deployment_sha256'])
    if menu_raw == old_menu:
        raise Blocked('OLD_AND_NEW_MENU_IDENTICAL')
    # No write before all read-only checks above have passed.
    write_once(txn.new_menu, menu_raw)
    write_once(txn.new_active, active_raw)
    read_pinned(txn.new_menu, verified['candidate_menu_sha256'])
    read_pinned(txn.new_active, verified['active_deployment_sha256'])
    # No implicit promotion of an inert request to authorized activity.
    return {
        'schema':'TICKSTORE_G4_INTENT_TO_SANDBOX_PLAN_V001',
        'status':'STAGED_SANDBOX_ONLY_NO_EFFECT_AUTHORITY',
        'package_sha256':verified['package_sha256'],
        'intent_sha256':verified['intent_sha256'],
        'menu_before_sha256':expected_old_menu_sha256,
        'menu_after_sha256':verified['candidate_menu_sha256'],
        'active_before_sha256':expected_old_active_sha256,
        'active_after_sha256':verified['active_deployment_sha256'],
        'activation_authorized':False,
        'production_started':False,
    }


def begin_sandbox_only(*, sandbox_root: Path, staged: dict, inject: str='') -> str:
    if staged.get('schema') != 'TICKSTORE_G4_INTENT_TO_SANDBOX_PLAN_V001' or \
       staged.get('status') != 'STAGED_SANDBOX_ONLY_NO_EFFECT_AUTHORITY' or \
       staged.get('activation_authorized') is not False or \
       staged.get('production_started') is not False:
        raise Blocked('STAGED_PLAN_NOT_INERT')
    root=Path(sandbox_root)
    if root.name != 'CDT15_G4_TXN_SANDBOX_INTENT':
        raise Blocked('INTENT_SANDBOX_EXACT_NAME_REQUIRED')
    tx=SandboxedTransaction(root)
    for key,path in [('menu_after_sha256',tx.new_menu),
                     ('active_after_sha256',tx.new_active)]:
        read_pinned(path, staged[key])
    return tx.begin(menu_before_sha256=staged['menu_before_sha256'],
                    menu_after_sha256=staged['menu_after_sha256'],
                    active_before_sha256=staged['active_before_sha256'],
                    active_after_sha256=staged['active_after_sha256'],inject=inject)
