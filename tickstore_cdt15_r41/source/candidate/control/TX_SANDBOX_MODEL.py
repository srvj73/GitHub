"""CDT15 G4: two-artifact transaction model restricted to disposable sandbox fixtures.

No install, no prod paths, no activation, no authority grants. No CLI entrypoint.
The model is a portable engineering proof; Windows durability/TOCTOU need native tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path

SCHEMA = "TICKSTORE_MENU_INSTALL_TRANSACTION_V001"
PHASES = {"PREPARED", "MENU_PUBLISHED", "ACTIVE_PUBLISHED", "COMMITTED", "ROLLED_BACK"}
SENTINEL = b"CDT15_G4_DISPOSABLE_SANDBOX_ONLY_V001\n"


class Blocked(RuntimeError):
    pass


class SimulatedCrash(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def write_once(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def replace_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".pending." + uuid.uuid4().hex)
    write_once(tmp, data)
    os.replace(tmp, path)


def guard(path: Path, *, file: bool = False) -> None:
    """Reject reparse and hardlinks for sandbox paths; not an effectful admission guard."""
    for item in (path, *path.parents):
        try:
            s = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(s.st_mode) or (getattr(s, "st_file_attributes", 0) & 0x400):
            raise Blocked("REPARSE_PATH")
    if file and path.exists():
        s = path.stat()
        if not stat.S_ISREG(s.st_mode):
            raise Blocked("NOT_REGULAR_FILE")
        if s.st_nlink != 1:
            raise Blocked("HARDLINK_FILE")


def read_pinned(path: Path, expected: str | None) -> bytes | None:
    guard(path, file=True)
    if expected is None:
        if path.exists():
            raise Blocked("EXPECTED_ABSENT")
        return None
    if not path.is_file():
        raise Blocked("EXPECTED_FILE_MISSING")
    data = path.read_bytes()
    if sha(data) != expected:
        raise Blocked("HASH_MISMATCH")
    return data


class SandboxedTransaction:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        # No arbitrary path argument can target an official Windows installation.
        if not self.root.name.startswith("CDT15_G4_TXN_SANDBOX_"):
            raise Blocked("SANDBOX_NAME_REQUIRED")
        guard(self.root)
        if (self.root / "SANDBOX_ONLY.txt").read_bytes() != SENTINEL:
            raise Blocked("SANDBOX_SENTINEL_INVALID")
        self.menu = self.root / "menu" / "MENU.py"
        self.active = self.root / "active" / "ACTIVE_DEPLOYMENT.json"
        self.new_menu = self.root / "candidate" / "MENU.py"
        self.new_active = self.root / "candidate" / "ACTIVE_DEPLOYMENT.json"
        self.tx = self.active.parent / "MENU_TRANSACTION"
        self.plan_path = self.tx / "PLAN.json"
        self.journal_path = self.tx / "JOURNAL.json"
        self.backup_menu = self.tx / "MENU.old"
        self.backup_active = self.tx / "ACTIVE.old"
        self.backup_active_absent = self.tx / "ACTIVE_WAS_ABSENT"

    def _check_layout(self) -> None:
        for p in [self.root, self.root / "menu", self.root / "active", self.root / "candidate"]:
            guard(p)
            if not p.is_dir():
                raise Blocked("LAYOUT_MISSING")

    def _check_candidate_active(self, data: bytes) -> None:
        try:
            d = json.loads(data)
        except (UnicodeDecodeError, ValueError) as exc:
            raise Blocked("ACTIVE_SCHEMA") from exc
        if not isinstance(d, dict) or d.get("schema") != "TICKSTORE_DEPLOYMENT_V001":
            raise Blocked("ACTIVE_SCHEMA")
        if d.get("status") != "INSTALLED_NOT_PRODUCTION_ADMISSION" or d.get("production_started") is not False:
            raise Blocked("ACTIVE_PREMATURE_PRODUCTION")
        digest = d.get("package_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789ABCDEF" for c in digest):
            raise Blocked("ACTIVE_PACKAGE_BINDING")

    def _read_current_status(self, path: Path, old: str | None, new: str) -> str:
        guard(path, file=True)
        if not path.exists():
            if old is None:
                return "old"
            raise Blocked("CURRENT_TARGET_MISSING")
        digest = sha(path.read_bytes())
        if digest == new:
            return "new"
        if digest == old:
            return "old"
        raise Blocked("UNEXPECTED_TARGET_DRIFT")

    def _journal(self, plan: dict, phase: str) -> None:
        if phase not in PHASES:
            raise Blocked("PHASE_UNKNOWN")
        obj = {"schema": SCHEMA, "plan_sha256": sha(canonical(plan)), "phase": phase}
        replace_atomic(self.journal_path, canonical(obj))
        if json.loads(self.journal_path.read_bytes()) != obj:
            raise Blocked("JOURNAL_READBACK")

    def _load(self) -> tuple[dict, str]:
        guard(self.tx)
        for p in (self.plan_path, self.journal_path, self.backup_menu):
            guard(p, file=True)
        try:
            plan = json.loads(self.plan_path.read_bytes())
            journal = json.loads(self.journal_path.read_bytes())
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise Blocked("TRANSACTION_RECORD_INVALID") from exc
        if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
            raise Blocked("PLAN_SCHEMA")
        if not isinstance(journal, dict) or set(journal) != {"schema", "plan_sha256", "phase"}:
            raise Blocked("JOURNAL_SCHEMA")
        if journal["schema"] != SCHEMA or journal["plan_sha256"] != sha(canonical(plan)) or journal["phase"] not in PHASES:
            raise Blocked("JOURNAL_PLAN_MISMATCH")
        if set(plan) != {"schema", "menu_before_sha256", "menu_after_sha256", "active_before_sha256", "active_after_sha256"}:
            raise Blocked("PLAN_FIELDS")
        if read_pinned(self.backup_menu, plan["menu_before_sha256"]) is None:
            raise Blocked("MENU_BACKUP_MISSING")
        if plan["active_before_sha256"] is None:
            if self.backup_active.exists() or self.backup_active_absent.read_bytes() != b"ABSENT\n":
                raise Blocked("ACTIVE_ABSENCE_MARKER_INVALID")
        else:
            read_pinned(self.backup_active, plan["active_before_sha256"])
            if self.backup_active_absent.exists():
                raise Blocked("ACTIVE_BACKUP_CARDINALITY")
        self._check_candidate_active(read_pinned(self.new_active, plan["active_after_sha256"]))
        read_pinned(self.new_menu, plan["menu_after_sha256"])
        return plan, journal["phase"]

    def _publish(self, path: Path, data: bytes) -> None:
        replace_atomic(path, data)

    def _remove_target(self, path: Path) -> None:
        guard(path, file=True)
        path.unlink()

    def begin(self, *, menu_before_sha256: str, menu_after_sha256: str,
              active_before_sha256: str | None, active_after_sha256: str, inject: str = "") -> str:
        self._check_layout()
        guard(self.tx)
        if self.tx.exists():
            raise Blocked("EXISTING_TRANSACTION_REQUIRES_RECONCILIATION")
        before = read_pinned(self.menu, menu_before_sha256)
        new_menu = read_pinned(self.new_menu, menu_after_sha256)
        old_active = read_pinned(self.active, active_before_sha256)
        new_active = read_pinned(self.new_active, active_after_sha256)
        self._check_candidate_active(new_active)
        if before == new_menu:
            raise Blocked("NOOP_MENU_NOT_A_TRANSACTION")
        self.tx.mkdir(mode=0o700)
        plan = {"schema": SCHEMA, "menu_before_sha256": menu_before_sha256,
                "menu_after_sha256": menu_after_sha256, "active_before_sha256": active_before_sha256,
                "active_after_sha256": active_after_sha256}
        write_once(self.plan_path, canonical(plan))
        write_once(self.backup_menu, before)
        if old_active is None:
            write_once(self.backup_active_absent, b"ABSENT\n")
        else:
            write_once(self.backup_active, old_active)
        self._journal(plan, "PREPARED")
        if inject == "AFTER_PREPARED":
            raise SimulatedCrash(inject)
        # check before publishing: all source/target bytes unchanged.
        read_pinned(self.menu, menu_before_sha256)
        read_pinned(self.active, active_before_sha256)
        self._publish(self.menu, new_menu)
        read_pinned(self.menu, menu_after_sha256)
        if inject == "AFTER_MENU_WRITE_BEFORE_JOURNAL":
            raise SimulatedCrash(inject)
        self._journal(plan, "MENU_PUBLISHED")
        if inject == "AFTER_MENU_PUBLISHED":
            raise SimulatedCrash(inject)
        read_pinned(self.active, active_before_sha256)
        self._publish(self.active, new_active)
        read_pinned(self.active, active_after_sha256)
        if inject == "AFTER_ACTIVE_WRITE_BEFORE_JOURNAL":
            raise SimulatedCrash(inject)
        self._journal(plan, "ACTIVE_PUBLISHED")
        if inject == "AFTER_ACTIVE_PUBLISHED":
            raise SimulatedCrash(inject)
        read_pinned(self.menu, menu_after_sha256)
        read_pinned(self.active, active_after_sha256)
        self._journal(plan, "COMMITTED")
        return "PASS_SANDBOX_ONLY"

    def reconcile(self, *, inject: str = "") -> str:
        """Never infer COMMITTED from two candidate files; rollback uncommitted state."""
        self._check_layout()
        plan, phase = self._load()
        menu_state = self._read_current_status(self.menu, plan["menu_before_sha256"], plan["menu_after_sha256"])
        active_state = self._read_current_status(self.active, plan["active_before_sha256"], plan["active_after_sha256"])
        if phase == "COMMITTED":
            if menu_state != "new" or active_state != "new":
                raise Blocked("COMMITTED_RECEIPT_DRIFT")
            return "PASS_ALREADY_COMMITTED_NO_WRITE"
        if phase == "ROLLED_BACK":
            if menu_state != "old" or active_state != "old":
                raise Blocked("ROLLED_BACK_RECEIPT_DRIFT")
            return "PASS_ALREADY_ROLLED_BACK_NO_WRITE"
        # Validate both before modifying either to prevent partial rollback on discovered drift.
        if active_state == "new":
            if plan["active_before_sha256"] is None:
                self._remove_target(self.active)
            else:
                self._publish(self.active, read_pinned(self.backup_active, plan["active_before_sha256"]))
            if self._read_current_status(self.active, plan["active_before_sha256"], plan["active_after_sha256"]) != "old":
                raise Blocked("ACTIVE_RECOVERY_READBACK")
        if inject == "AFTER_ACTIVE_RECOVERY":
            raise SimulatedCrash(inject)
        if menu_state == "new":
            self._publish(self.menu, read_pinned(self.backup_menu, plan["menu_before_sha256"]))
            if self._read_current_status(self.menu, plan["menu_before_sha256"], plan["menu_after_sha256"]) != "old":
                raise Blocked("MENU_RECOVERY_READBACK")
        self._journal(plan, "ROLLED_BACK")
        return "PASS_RECOVERED_SANDBOX_ONLY"
