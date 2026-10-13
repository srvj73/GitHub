"""CDT15 G4, SOURCE_ONLY: one kernel-locked stage -> commit in disposable sandbox.

This is NOT the official MENU/ACTIVE publisher. No CLI and no arbitrary
publish paths. A successful result means only sandbox fixture completion.
No release/authorization or native power-loss durability claim is conveyed.
"""
from __future__ import annotations
from pathlib import Path
from MENU_TX_INTERPROCESS_SANDBOX import SandboxKernelLock, EXACT_SANDBOX
from MENU_INTENT_TO_TX_SANDBOX import stage_verified_inert_intent, begin_sandbox_only
from TX_SANDBOX_MODEL import Blocked, SandboxedTransaction, read_pinned


def locked_stage_commit_sandbox(*, installed_root: Path, sandbox_root: Path,
                                trusted_package_sha256: str,
                                trusted_witness_sha256: str,
                                expected_old_menu_sha256: str,
                                expected_old_active_sha256: str | None,
                                inject: str = '') -> dict:
    """Keep same kernel lock through BOTH stage and commit, with final readback.

    Exception/crash leaves existing transaction state to explicit locked_reconcile;
    no auto-successor and no automatic deletion of forensic evidence.
    """
    root = Path(sandbox_root)
    if root.name != EXACT_SANDBOX:
        raise Blocked('FUSED_SANDBOX_EXACT_NAME_REQUIRED')
    with SandboxKernelLock(root):
        staged = stage_verified_inert_intent(
            installed_root=Path(installed_root), sandbox_root=root,
            trusted_package_sha256=trusted_package_sha256,
            trusted_witness_sha256=trusted_witness_sha256,
            expected_old_menu_sha256=expected_old_menu_sha256,
            expected_old_active_sha256=expected_old_active_sha256,
        )
        result = begin_sandbox_only(sandbox_root=root, staged=staged, inject=inject)
        if result != 'PASS_SANDBOX_ONLY':
            raise Blocked('FUSED_BEGIN_UNEXPECTED_RESULT')
        tx = SandboxedTransaction(root)
        plan, phase = tx._load()
        if phase != 'COMMITTED':
            raise Blocked('FUSED_NOT_COMMITTED')
        if (plan['menu_after_sha256'] != staged['menu_after_sha256'] or
                plan['active_after_sha256'] != staged['active_after_sha256'] or
                plan['menu_before_sha256'] != staged['menu_before_sha256'] or
                plan['active_before_sha256'] != staged['active_before_sha256']):
            raise Blocked('FUSED_PLAN_DRIFT')
        read_pinned(tx.menu, staged['menu_after_sha256'])
        read_pinned(tx.active, staged['active_after_sha256'])
        return {
            'schema': 'CDT15_G4_FUSED_TX_SANDBOX_RESULT_V001',
            'status': 'PASS_SANDBOX_ONLY',
            'phase': 'COMMITTED',
            'intent_sha256': staged['intent_sha256'],
            'package_sha256': staged['package_sha256'],
            'menu_sha256': staged['menu_after_sha256'],
            'active_sha256': staged['active_after_sha256'],
            'effectful_authorized': False,
            'production_started': False,
        }
