"""G4 SOURCE_ONLY: interprocess coordinator for disposable MENU transaction sandbox.

Windows msvcrt byte-range lock / POSIX flock. Not a production publisher,
installer hook, Windows ACL/TOCTOU authority, or power-loss durability proof.
No CLI, no official path targets. Lock file is never unlinked on release.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from TX_SANDBOX_MODEL import Blocked, SandboxedTransaction, guard
from MENU_INTENT_TO_TX_SANDBOX import stage_verified_inert_intent, begin_sandbox_only

LOCK_NAME = '.CDT15_G4_INTERPROCESS_COORDINATOR_V001.lock'
LOCK_MAGIC = b'CDT15_G4_INTERPROCESS_COORDINATOR_V001\n'
EXACT_SANDBOX = 'CDT15_G4_TXN_SANDBOX_INTENT'


def _same_identity(fd: int, path: Path) -> None:
    guard(path, file=True)
    a = os.fstat(fd)
    b = path.stat()
    if not stat.S_ISREG(a.st_mode) or a.st_nlink != 1:
        raise Blocked('LOCK_NOT_SINGLE_REGULAR_FILE')
    if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
        raise Blocked('LOCK_PATH_IDENTITY_CHANGED')


class SandboxKernelLock:
    """A reusable permanent sandbox lock whose kernel lease dies with the process."""
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.fd: int | None = None
        self.path = self.root / 'active' / LOCK_NAME

    def __enter__(self):
        if self.root.name != EXACT_SANDBOX:
            raise Blocked('COORDINATOR_EXACT_SANDBOX_REQUIRED')
        tx = SandboxedTransaction(self.root)
        tx._check_layout()
        guard(self.path, file=True)
        flags = os.O_RDWR | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        created = False
        try:
            try:
                fd = os.open(self.path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                fd = os.open(self.path, flags)
            self.fd = fd
            if created:
                # No writer may remove this file after it has been published.
                os.write(fd, LOCK_MAGIC)
                os.fsync(fd)
            _same_identity(fd, self.path)
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as exc:
                raise Blocked('SANDBOX_COORDINATOR_BUSY') from exc
            _same_identity(fd, self.path)
            if os.fstat(fd).st_size != len(LOCK_MAGIC):
                raise Blocked('LOCK_MAGIC_SIZE_INVALID')
            os.lseek(fd, 0, os.SEEK_SET)
            if os.read(fd, len(LOCK_MAGIC)) != LOCK_MAGIC:
                raise Blocked('LOCK_MAGIC_INVALID')
            os.lseek(fd, 0, os.SEEK_SET)
            return self
        except BaseException:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise

    def __exit__(self, exc_type, exc, tb):
        if self.fd is None:
            return False
        try:
            _same_identity(self.fd, self.path)
            os.lseek(self.fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None
        return False


def locked_stage_intent(*, installed_root: Path, sandbox_root: Path,
                        trusted_package_sha256: str, trusted_witness_sha256: str,
                        expected_old_menu_sha256: str,
                        expected_old_active_sha256: str | None) -> dict:
    with SandboxKernelLock(sandbox_root):
        return stage_verified_inert_intent(installed_root=installed_root,
             sandbox_root=sandbox_root,
             trusted_package_sha256=trusted_package_sha256,
             trusted_witness_sha256=trusted_witness_sha256,
             expected_old_menu_sha256=expected_old_menu_sha256,
             expected_old_active_sha256=expected_old_active_sha256)


def locked_begin(*, sandbox_root: Path, staged: dict, inject: str = '') -> str:
    with SandboxKernelLock(sandbox_root):
        return begin_sandbox_only(sandbox_root=sandbox_root, staged=staged, inject=inject)


def locked_reconcile(*, sandbox_root: Path, inject: str = '') -> str:
    with SandboxKernelLock(sandbox_root):
        return SandboxedTransaction(sandbox_root).reconcile(inject=inject)
