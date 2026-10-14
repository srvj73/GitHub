"""CDT15 R41: effectful two-artifact MENU/ACTIVE writer (cross-volume, journaled).

One exclusive OS lock (share-none handle on ``<TICKSTORE>/MENU_WRITER.lock``)
is held from live re-admission through COMMITTED or ROLLED_BACK.  MENU and its
pending/backup artifacts live on the MENU volume (D:); ACTIVE, the journal and
the evidence live on the LOCALAPPDATA volume (C:).  This is a cross-volume
protocol with a hash-bound recovery table, NEVER a global atomic transaction.

Two layouts exist and share every protocol line:

* QUALIFICATION: disposable sentinel-marked sandbox roots only.  Crash/swap
  injection is permitted only here.
* OFFICIAL: fixed historical targets.  Requires Windows, a technical release
  chain through B07 (independent B06 digest supplied separately), and a fresh
  live read-only target admission.  No injection, no arbitrary target paths.

COMMITTED is never inferred from target hashes alone; drift always blocks.
Nothing is deleted: displaced, abandoned and backup bytes are preserved.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import ntpath
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'full'))
import tickstore_serial_runner as core  # noqa: E402  (frozen RC1 secure primitives)
from MENU_INSTALL_INTENT_VERIFY import (  # noqa: E402
    verify_inert_intent, MENU_REL, Blocked as IntentBlocked)
from MENU_OFFICIAL_WRITER_CONTRACT_SOURCE_ONLY import (  # noqa: E402
    recovery_decision, Blocked as ContractBlocked, TX_SCHEMA, PHASES)

WRITER_SCHEMA = 'TICKSTORE_MENU_OFFICIAL_WRITER_RESULT_V001'
EVIDENCE_SCHEMA = 'TICKSTORE_MENU_TRANSACTION_EVIDENCE_V001'
PHASE_RECORD_SCHEMA = 'TICKSTORE_MENU_TRANSACTION_PHASE_RECORD_V001'
SANDBOX_PREFIX = 'CDT15_R41_WRITER_QUAL_'
SANDBOX_SENTINEL = b'CDT15_R41_OFFICIAL_WRITER_QUALIFICATION_SANDBOX_ONLY_V001\n'
LOCK_NAME = 'MENU_WRITER.lock'
TX_NAME = 'MENU_TRANSACTION'
STAGING_PREFIX = '.MENU_TRANSACTION.staging.'
ARCHIVE_NAME = 'MENU_TRANSACTION_ARCHIVE'
MENU_ARCHIVE_NAME = '.TICKSTORE_MENU_ARCHIVE'
ACTIVE_NAME = 'ACTIVE_DEPLOYMENT.json'
HEX64 = re.compile(r'[0-9A-F]{64}\Z')
INJECTION_POINTS = (
    'AFTER_STAGING_WRITTEN', 'AFTER_PREPARED', 'AFTER_MENU_PENDING', 'BEFORE_MENU_REPLACE',
    'AFTER_MENU_REPLACE_BEFORE_JOURNAL', 'AFTER_MENU_PUBLISHED', 'AFTER_ACTIVE_PENDING',
    'AFTER_ACTIVE_MOVE_BEFORE_JOURNAL', 'AFTER_ACTIVE_PUBLISHED', 'AFTER_COMMITTED',
    'RECOVERY_AFTER_ACTIVE_DISPLACED', 'RECOVERY_AFTER_MENU_RESTORED',
)


class Blocked(RuntimeError):
    pass


class SimulatedCrash(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def canonical(obj) -> bytes:
    # Byte-compatible with the MENU consumer and the sandbox model.
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def _strict_json(raw: bytes):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'JSON_DUPLICATE_KEY')
            out[k] = v
        return out
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    except (UnicodeDecodeError, ValueError) as exc:
        raise Blocked('JSON_INVALID') from exc


def _good_hash(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


# --------------------------------------------------------------------------- native ops

class _Win32:
    """Minimal kernel32 surface; handle identity reuses the frozen RC1 validator."""
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_ALWAYS = 4
    FILE_ATTRIBUTE_NORMAL = 0x80
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    REPLACEFILE_IGNORE_MERGE_ERRORS = 0x2
    MOVEFILE_REPLACE_EXISTING = 0x1
    MOVEFILE_WRITE_THROUGH = 0x8

    def __init__(self):
        from ctypes import wintypes as w
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        k.CreateFileW.restype = w.HANDLE
        k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL
        k.ReplaceFileW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        k.ReplaceFileW.restype = w.BOOL
        k.MoveFileExW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.DWORD]; k.MoveFileExW.restype = w.BOOL
        k.CreateDirectoryW.argtypes = [w.LPCWSTR, ctypes.c_void_p]; k.CreateDirectoryW.restype = w.BOOL
        k.GetFileAttributesW.argtypes = [w.LPCWSTR]; k.GetFileAttributesW.restype = w.DWORD
        k.FlushFileBuffers.argtypes = [w.HANDLE]; k.FlushFileBuffers.restype = w.BOOL
        self.k = k
        self.invalid = w.HANDLE(-1).value

    def error(self, label, path=''):
        return Blocked(label + ':' + str(path) + ':winerror=' + str(ctypes.get_last_error()))


_WIN = None


def _win():
    global _WIN
    if _WIN is None:
        _WIN = _Win32()
    return _WIN


def exists(path: Path) -> bool:
    if os.name == 'nt':
        w = _win()
        attrs = w.k.GetFileAttributesW(str(path))
        if attrs != 0xFFFFFFFF:
            return True
        err = ctypes.get_last_error()
        if err in (2, 3):
            return False
        raise Blocked('EXISTENCE_UNKNOWN:' + str(path) + ':winerror=' + str(err))
    return core.strict_lstat(Path(path), allow_missing=True) is not None


def read_pinned(path: Path) -> bytes:
    """Read through one validated handle (no reparse, one link, final path match)."""
    return core.secure_read_all(Path(path))


def digest_or_none(path: Path):
    return sha(read_pinned(path)) if exists(path) else None


def write_new_durable(path: Path, raw: bytes) -> None:
    """CREATE_NEW + flush (FlushFileBuffers via fsync) + independent readback."""
    fd = core.secure_create_new_fd(Path(path))
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(read_pinned(path) == raw, 'WRITE_READBACK:' + str(path))


def flush_existing(path: Path) -> None:
    fd = core.secure_open_existing_fd(Path(path), writable=True)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def mkdir_new(path: Path) -> None:
    path = Path(path)
    if os.name == 'nt':
        pins = core._windows_pin_ancestor_chain(path.parent)
        try:
            if not _win().k.CreateDirectoryW(str(path), None):
                raise _win().error('MKDIR_NEW_FAIL', path)
        finally:
            core._windows_unpin(pins)
        return
    try:
        os.mkdir(path, 0o700)
    except FileExistsError as exc:
        raise Blocked('MKDIR_NEW_EXISTS:' + str(path)) from exc
    _fsync_dir(path.parent)


def _fsync_dir(path: Path) -> None:
    if os.name == 'nt':
        return
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def move_no_replace(src: Path, dst: Path) -> None:
    """Same-volume rename that fails if dst exists (files or directories)."""
    src, dst = Path(src), Path(dst)
    if os.name == 'nt':
        pins = core._windows_pin_ancestor_chain(src.parent) + core._windows_pin_ancestor_chain(dst.parent)
        try:
            require(not exists(dst), 'MOVE_TARGET_EXISTS:' + str(dst))
            if not _win().k.MoveFileExW(str(src), str(dst), _Win32.MOVEFILE_WRITE_THROUGH):
                raise _win().error('MOVE_NO_REPLACE_FAIL', str(src) + '->' + str(dst))
        finally:
            core._windows_unpin(pins)
        return
    st = core.strict_lstat(src, allow_missing=False)
    if stat.S_ISDIR(st.st_mode):
        require(not exists(dst), 'MOVE_TARGET_EXISTS:' + str(dst))
        os.rename(src, dst)  # sandbox-only POSIX emulation; Windows path is authoritative
    else:
        try:
            os.link(src, dst, follow_symlinks=False)
        except FileExistsError as exc:
            raise Blocked('MOVE_TARGET_EXISTS:' + str(dst)) from exc
        os.unlink(src)
    _fsync_dir(src.parent); _fsync_dir(dst.parent)


def move_replace_file(src: Path, dst: Path) -> None:
    """Journal-record replacement: MoveFileExW(REPLACE_EXISTING|WRITE_THROUGH)."""
    src, dst = Path(src), Path(dst)
    if os.name == 'nt':
        pins = core._windows_pin_ancestor_chain(dst.parent)
        try:
            core.strict_regular_file(src)
            if exists(dst):
                core.strict_regular_file(dst)
            if not _win().k.MoveFileExW(str(src), str(dst),
                                        _Win32.MOVEFILE_REPLACE_EXISTING | _Win32.MOVEFILE_WRITE_THROUGH):
                raise _win().error('MOVE_REPLACE_FAIL', str(src) + '->' + str(dst))
        finally:
            core._windows_unpin(pins)
        return
    core.secure_replace(src, dst)
    _fsync_dir(dst.parent)


def replace_with_backup(target: Path, replacement: Path, backup: Path) -> None:
    """ReplaceFileW with an explicit backup; all three on one volume.

    The caller proves afterwards that ``backup`` holds exactly the admitted
    before-bytes, which closes the close->replace TOCTOU window.
    """
    target, replacement, backup = Path(target), Path(replacement), Path(backup)
    require(not exists(backup), 'BACKUP_NAME_COLLISION:' + str(backup))
    if os.name == 'nt':
        pins = core._windows_pin_ancestor_chain(target.parent)
        try:
            core.strict_regular_file(target); core.strict_regular_file(replacement)
            if not _win().k.ReplaceFileW(str(target), str(replacement), str(backup),
                                         _Win32.REPLACEFILE_IGNORE_MERGE_ERRORS, None, None):
                raise _win().error('REPLACEFILE_FAIL', target)
        finally:
            core._windows_unpin(pins)
    else:
        # Portable emulation: backup keeps the old inode, target is atomically swapped.
        core.strict_regular_file(target); core.strict_regular_file(replacement)
        os.link(target, backup, follow_symlinks=False)
        os.replace(replacement, target)
        _fsync_dir(target.parent)
    flush_existing(target)
    flush_existing(backup)


class ExclusiveLock:
    """Single writer lock: share-none handle, released by the OS on process death."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.handle = None
        self.fd = None

    def __enter__(self):
        if os.name == 'nt':
            w = _win()
            pins = core._windows_pin_ancestor_chain(self.path.parent)
            try:
                h = w.k.CreateFileW(str(self.path), _Win32.GENERIC_READ | _Win32.GENERIC_WRITE, 0, None,
                                    _Win32.OPEN_ALWAYS,
                                    _Win32.FILE_ATTRIBUTE_NORMAL | _Win32.FILE_FLAG_OPEN_REPARSE_POINT, None)
                if h == w.invalid:
                    err = ctypes.get_last_error()
                    if err == 32:
                        raise Blocked('WRITER_LOCK_BUSY')
                    raise Blocked('WRITER_LOCK_OPEN:winerror=' + str(err))
                try:
                    core._windows_validate_handle(w.k, h, self.path, expect_directory=False,
                                                  require_single_link=True)
                except BaseException:
                    w.k.CloseHandle(h)
                    raise
                self.handle = h
            finally:
                core._windows_unpin(pins)
            return self
        import fcntl
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            st = os.fstat(fd)
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'WRITER_LOCK_IDENTITY')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Blocked('WRITER_LOCK_BUSY') from exc
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            _win().k.CloseHandle(self.handle)
            self.handle = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        return False


# --------------------------------------------------------------------------- layout

@dataclass(frozen=True)
class Layout:
    kind: str                 # 'OFFICIAL' or 'QUALIFICATION'
    menu: Path
    bat: Path
    tickstore_root: Path      # %LOCALAPPDATA%\TICKSTORE (C:)
    menu_before_sha256: str
    bat_sha256: str
    cross_volume_required: bool

    @property
    def active(self):
        return self.tickstore_root / ACTIVE_NAME

    @property
    def tx(self):
        return self.tickstore_root / TX_NAME

    @property
    def lock(self):
        return self.tickstore_root / LOCK_NAME

    @property
    def archive(self):
        return self.tickstore_root / ARCHIVE_NAME

    def token_paths(self, package_sha256):
        require(_good_hash(package_sha256), 'PACKAGE_DIGEST')
        token = package_sha256[:16]
        parent = self.menu.parent
        return {
            'menu_pending': parent / ('.TICKSTORE_MENU_' + token + '.pending'),
            'menu_backup': parent / ('.TICKSTORE_MENU_' + token + '.backup'),
            'menu_restore': parent / ('.TICKSTORE_MENU_' + token + '.restore'),
            'menu_displaced': parent / ('.TICKSTORE_MENU_' + token + '.displaced'),
            'active_pending': self.tickstore_root / ('.TICKSTORE_ACTIVE_' + token + '.pending'),
            'staging': self.tickstore_root / (STAGING_PREFIX + token),
        }

    def validate(self):
        require(self.kind in ('OFFICIAL', 'QUALIFICATION'), 'LAYOUT_KIND')
        for p in (self.menu, self.bat, self.tickstore_root):
            require(Path(p).is_absolute() and ':' not in Path(p).name, 'LAYOUT_NOT_ABSOLUTE')
        require(_good_hash(self.menu_before_sha256) and _good_hash(self.bat_sha256), 'LAYOUT_PINS')
        if self.cross_volume_required:
            d1 = ntpath.splitdrive(str(self.menu))[0].casefold()
            d2 = ntpath.splitdrive(str(self.tickstore_root))[0].casefold()
            require(d1 and d2 and d1 != d2, 'CROSS_VOLUME_LAYOUT_NOT_PROVEN')
        return self


def official_layout():
    """Fixed historical targets; LOCALAPPDATA is validated after real expansion."""
    from MENU_OFFICIAL_ADMISSION_READONLY import MENU, BAT, MENU_SHA, BAT_SHA
    app = os.environ.get('LOCALAPPDATA', '')
    require(re.fullmatch(r'[A-Za-z]:\\[^%]+', app) is not None, 'LOCALAPPDATA_INVALID')
    require(ntpath.normpath(app).casefold() == app.casefold() and not app.endswith('\\'),
            'LOCALAPPDATA_NOT_CANONICAL')
    return Layout('OFFICIAL', Path(MENU), Path(BAT), Path(ntpath.join(app, 'TICKSTORE')),
                  MENU_SHA, BAT_SHA, True).validate()


def touches_real_target(root: str, local_appdata: str) -> bool:
    """Component-wise overlap with real targets ('...\\TICKSTORE_QUAL' is not '...\\TICKSTORE')."""
    reals = [r'D:\Base CSV']
    if re.fullmatch(r'[A-Za-z]:\\[^%]+', local_appdata or ''):
        reals.append(ntpath.join(local_appdata, 'TICKSTORE'))
    parts = [x.casefold() for x in PureWindowsPath(root).parts]
    for real in reals:
        real_parts = [x.casefold() for x in PureWindowsPath(real).parts]
        n = min(len(parts), len(real_parts))
        if parts[:n] == real_parts[:n]:
            return True
    return False


def qualification_layout(d_root: Path, c_root: Path, menu_before_sha256: str, bat_sha256: str):
    """Disposable sentinel-marked sandbox; refuses anything resembling a real target."""
    d_root, c_root = Path(d_root).absolute(), Path(c_root).absolute()
    for root in (d_root, c_root):
        require(root.name.startswith(SANDBOX_PREFIX), 'QUALIFICATION_SANDBOX_NAME')
        require(read_pinned(root / 'SANDBOX_ONLY.txt') == SANDBOX_SENTINEL, 'QUALIFICATION_SENTINEL')
    require(d_root != c_root, 'QUALIFICATION_ROOTS_DISTINCT')
    for root in (d_root, c_root):
        require(not touches_real_target(str(root), os.environ.get('LOCALAPPDATA', '')),
                'QUALIFICATION_TOUCHES_REAL_TARGET')
    return Layout('QUALIFICATION', d_root / 'Base CSV' / 'Scripts' / 'Biblioteca' / 'MENU.py',
                  d_root / 'Base CSV' / 'Manutenção Base de Dados.bat', c_root / 'TICKSTORE',
                  menu_before_sha256, bat_sha256, os.name == 'nt').validate()


# --------------------------------------------------------------------------- records

class Injector:
    """Crash/swap hooks exist only for qualification layouts."""

    def __init__(self, layout, point=None, mode='EXIT', swap_bytes=None):
        require(point is None or point in INJECTION_POINTS, 'INJECTION_POINT_UNKNOWN')
        require(point is None or layout.kind == 'QUALIFICATION', 'INJECTION_FORBIDDEN_OFFICIAL')
        require(mode in ('EXIT', 'RAISE', 'SWAP'), 'INJECTION_MODE')
        self.layout, self.point, self.mode, self.swap_bytes = layout, point, mode, swap_bytes

    def __call__(self, point):
        if point != self.point:
            return
        if self.mode == 'SWAP':
            # Hostile concurrent replacement of MENU inside the close->replace window.
            tmp = self.layout.menu.with_name(self.layout.menu.name + '.hostile')
            tmp.write_bytes(self.swap_bytes or b'HOSTILE\n')
            os.replace(tmp, self.layout.menu)
            return
        if self.mode == 'RAISE':
            raise SimulatedCrash(point)
        sys.stdout.flush(); sys.stderr.flush()
        os._exit(77)  # abrupt death: no finally, no handle cleanup by Python


def _journal(tx_dir: Path, plan_sha: str, phase: str, seq: int, extra=None):
    require(phase in PHASES, 'PHASE_UNKNOWN')
    record = dict(schema=PHASE_RECORD_SCHEMA, plan_sha256=plan_sha, phase=phase, sequence=seq,
                  pid=os.getpid(), created_unix_ns=time.time_ns(), **(extra or {}))
    write_new_durable(tx_dir / ('PHASE_%02d_%s.json' % (seq, phase)), canonical(record))
    journal = canonical({'schema': TX_SCHEMA, 'plan_sha256': plan_sha, 'phase': phase})
    pending = tx_dir / ('JOURNAL.%02d_%s.pending' % (seq, phase))
    write_new_durable(pending, journal)
    move_replace_file(pending, tx_dir / 'JOURNAL.json')
    require(read_pinned(tx_dir / 'JOURNAL.json') == journal, 'JOURNAL_READBACK:' + phase)


def load_transaction(tx_dir: Path):
    """Exact consumer-compatible PLAN/JOURNAL binding plus writer evidence."""
    plan_raw = read_pinned(tx_dir / 'PLAN.json')
    journal_raw = read_pinned(tx_dir / 'JOURNAL.json')
    evidence_raw = read_pinned(tx_dir / 'EVIDENCE.json')
    plan, journal, evidence = _strict_json(plan_raw), _strict_json(journal_raw), _strict_json(evidence_raw)
    require(isinstance(plan, dict) and canonical(plan) == plan_raw and plan.get('schema') == TX_SCHEMA
            and set(plan) == {'schema', 'menu_before_sha256', 'menu_after_sha256',
                              'active_before_sha256', 'active_after_sha256'}, 'TX_PLAN_SCHEMA')
    require(isinstance(journal, dict) and canonical(journal) == journal_raw
            and set(journal) == {'schema', 'plan_sha256', 'phase'} and journal['schema'] == TX_SCHEMA
            and journal['plan_sha256'] == sha(plan_raw) and journal['phase'] in PHASES, 'TX_JOURNAL_BINDING')
    require(isinstance(evidence, dict) and canonical(evidence) == evidence_raw
            and evidence.get('schema') == EVIDENCE_SCHEMA and evidence.get('plan_sha256') == sha(plan_raw),
            'TX_EVIDENCE_BINDING')
    # A crash may leave exactly one trailing phase record whose JOURNAL move did
    # not happen; the JOURNAL remains authoritative and recovery appends after it.
    phases = sorted(p.name for p in tx_dir.iterdir() if p.name.startswith('PHASE_'))
    current = [i for i, n in enumerate(phases) if n.endswith('_' + journal['phase'] + '.json')]
    require(current and len(phases) - 1 - current[-1] <= 1, 'TX_PHASE_HISTORY_GAP')
    for i, name in enumerate(phases):
        require(name.startswith('PHASE_%02d_' % (i + 1)), 'TX_PHASE_SEQUENCE')
    return plan, journal['phase'], evidence, sha(plan_raw)


# --------------------------------------------------------------------------- protocol

def _admit_targets(layout: Layout):
    """Live re-admission under the held writer lock (handles validated by RC1 core)."""
    require(sha(read_pinned(layout.bat)) == layout.bat_sha256, 'BAT_DRIFT')
    menu_raw = read_pinned(layout.menu)
    require(sha(menu_raw) == layout.menu_before_sha256, 'MENU_BEFORE_DRIFT')
    require(not exists(layout.tx), 'EXISTING_TRANSACTION_REQUIRES_RECOVERY')
    require(not exists(layout.active), 'ACTIVE_PREEXISTING_WITHOUT_TRANSACTION')
    staging = [p.name for p in layout.tickstore_root.iterdir() if p.name.startswith(STAGING_PREFIX)]
    require(not staging, 'ORPHAN_STAGING_REQUIRES_RECOVERY')
    return menu_raw


def publish(layout: Layout, *, installed_root: Path, trusted_package_sha256: str,
            trusted_witness_sha256: str, inject=None, writer_identity=None):
    layout.validate()
    hook = inject or Injector(layout)
    require(hook.layout is layout, 'INJECTOR_LAYOUT')
    try:
        verified = verify_inert_intent(Path(installed_root), trusted_package_sha256=trusted_package_sha256,
                                       trusted_witness_sha256=trusted_witness_sha256)
    except IntentBlocked as exc:
        raise Blocked('INSTALLED_INTENT:' + str(exc)) from exc
    paths = layout.token_paths(verified['package_sha256'])
    with ExclusiveLock(layout.lock) as lock:
        pins = core._windows_pin_ancestor_chain(layout.menu.parent) if os.name == 'nt' else []
        try:
            before_raw = _admit_targets(layout)
            for key in ('menu_pending', 'menu_backup', 'menu_restore', 'menu_displaced',
                        'active_pending', 'staging'):
                require(not exists(paths[key]), 'ARTIFACT_NAME_COLLISION:' + key)
            # Candidate bytes are re-read from the installed instance under the lock.
            menu_after = read_pinned(Path(installed_root) / MENU_REL)
            active_after = read_pinned(Path(installed_root) / 'DEPLOYMENT.json')
            require(sha(menu_after) == verified['candidate_menu_sha256'], 'CANDIDATE_MENU_DRIFT')
            require(sha(active_after) == verified['active_deployment_sha256'], 'CANDIDATE_ACTIVE_DRIFT')
            require(menu_after != before_raw, 'NOOP_MENU_NOT_A_TRANSACTION')
            plan = {'schema': TX_SCHEMA, 'menu_before_sha256': sha(before_raw),
                    'menu_after_sha256': sha(menu_after), 'active_before_sha256': None,
                    'active_after_sha256': sha(active_after)}
            plan_raw = canonical(plan); plan_sha = sha(plan_raw)
            evidence = dict(schema=EVIDENCE_SCHEMA, plan_sha256=plan_sha, layout_kind=layout.kind,
                            menu_path=str(layout.menu), bat_path=str(layout.bat), bat_sha256=layout.bat_sha256,
                            active_path=str(layout.active), menu_backup_path=str(paths['menu_backup']),
                            menu_pending_path=str(paths['menu_pending']),
                            active_pending_path=str(paths['active_pending']),
                            package_sha256=verified['package_sha256'], intent_sha256=verified['intent_sha256'],
                            installed_root=str(Path(installed_root)), witness_sha256=trusted_witness_sha256,
                            writer_sha256=sha(Path(__file__).read_bytes()),
                            writer_identity=writer_identity or {}, pid=os.getpid(),
                            created_unix_ns=time.time_ns(), production_started=False)
            # 1. PREPARED becomes visible only through one directory rename.
            mkdir_new(paths['staging'])
            write_new_durable(paths['staging'] / 'PLAN.json', plan_raw)
            write_new_durable(paths['staging'] / 'EVIDENCE.json', canonical(evidence))
            _journal(paths['staging'], plan_sha, 'PREPARED', 1)
            hook('AFTER_STAGING_WRITTEN')
            move_no_replace(paths['staging'], layout.tx)
            hook('AFTER_PREPARED')
            # 2. MENU on its own volume: pending, JIT re-check, ReplaceFileW + backup proof.
            write_new_durable(paths['menu_pending'], menu_after)
            hook('AFTER_MENU_PENDING')
            require(read_pinned(layout.menu) == before_raw, 'MENU_DRIFT_BEFORE_REPLACE')
            hook('BEFORE_MENU_REPLACE')
            replace_with_backup(layout.menu, paths['menu_pending'], paths['menu_backup'])
            require(read_pinned(paths['menu_backup']) == before_raw, 'MENU_CONCURRENT_SWAP_DETECTED')
            require(read_pinned(layout.menu) == menu_after, 'MENU_AFTER_READBACK')
            hook('AFTER_MENU_REPLACE_BEFORE_JOURNAL')
            _journal(layout.tx, plan_sha, 'MENU_PUBLISHED', 2)
            hook('AFTER_MENU_PUBLISHED')
            # 3. ACTIVE on the LOCALAPPDATA volume: absent target, no-replace move.
            write_new_durable(paths['active_pending'], active_after)
            hook('AFTER_ACTIVE_PENDING')
            move_no_replace(paths['active_pending'], layout.active)
            require(read_pinned(layout.active) == active_after, 'ACTIVE_AFTER_READBACK')
            hook('AFTER_ACTIVE_MOVE_BEFORE_JOURNAL')
            _journal(layout.tx, plan_sha, 'ACTIVE_PUBLISHED', 3)
            hook('AFTER_ACTIVE_PUBLISHED')
            # 4. Final readback of every bound object before COMMITTED.
            require(read_pinned(layout.menu) == menu_after and read_pinned(layout.active) == active_after,
                    'PRECOMMIT_TARGET_READBACK')
            require(sha(read_pinned(layout.bat)) == layout.bat_sha256, 'PRECOMMIT_BAT_DRIFT')
            require(read_pinned(paths['menu_backup']) == before_raw, 'PRECOMMIT_BACKUP_DRIFT')
            loaded = load_transaction(layout.tx)
            require(loaded[0] == plan and loaded[1] == 'ACTIVE_PUBLISHED', 'PRECOMMIT_TX_READBACK')
            _journal(layout.tx, plan_sha, 'COMMITTED', 4)
            hook('AFTER_COMMITTED')
            final = load_transaction(layout.tx)
            require(final[1] == 'COMMITTED' and recovery_decision(
                'COMMITTED', menu_digest=sha(read_pinned(layout.menu)),
                active_digest=sha(read_pinned(layout.active)), plan=plan)
                == 'RECONCILE_COMMITTED_WITH_FULL_EVIDENCE_ONLY', 'COMMITTED_READBACK')
        finally:
            core._windows_unpin(pins) if pins else None
    return dict(schema=WRITER_SCHEMA, status='COMMITTED', layout_kind=layout.kind, plan=plan,
                plan_sha256=plan_sha, package_sha256=verified['package_sha256'],
                menu_backup=str(paths['menu_backup']), production_started=False,
                full_started=False)


def _displace(src: Path, dst: Path, expected_sha: str):
    require(sha(read_pinned(src)) == expected_sha, 'DISPLACE_SOURCE_DRIFT:' + str(src))
    move_no_replace(src, dst)
    require(sha(read_pinned(dst)) == expected_sha, 'DISPLACE_READBACK:' + str(dst))


def recover(layout: Layout, *, inject=None):
    """Hash-bound recovery under the same writer lock; never auto-runs a successor."""
    layout.validate()
    hook = inject or Injector(layout)
    with ExclusiveLock(layout.lock):
        pins = core._windows_pin_ancestor_chain(layout.menu.parent) if os.name == 'nt' else []
        try:
            staging = sorted(p for p in layout.tickstore_root.iterdir() if p.name.startswith(STAGING_PREFIX))
            if staging:
                # Nothing outside staging was written before the PREPARED rename.
                require(not exists(layout.tx), 'STAGING_AND_TRANSACTION_COEXIST')
                require(sha(read_pinned(layout.menu)) == layout.menu_before_sha256
                        and not exists(layout.active), 'STAGING_WITH_TARGET_DRIFT')
                mkdir_archive(layout.archive)
                for item in staging:
                    move_no_replace(item, layout.archive / ('ABORTED_STAGING_' + item.name.lstrip('.')
                                                            + '_' + str(time.time_ns())))
                return dict(schema=WRITER_SCHEMA, status='STAGING_ABORTED_ARCHIVED', layout_kind=layout.kind)
            if not exists(layout.tx):
                return dict(schema=WRITER_SCHEMA, status='NO_TRANSACTION', layout_kind=layout.kind)
            plan, phase, evidence, plan_sha = load_transaction(layout.tx)
            paths = layout.token_paths(evidence['package_sha256'])
            actions = []
            if not exists(layout.menu) and phase not in ('COMMITTED', 'ROLLED_BACK'):
                # ReplaceFileW ERROR_UNABLE_TO_MOVE_REPLACEMENT_2: MENU exists only under
                # the backup name.  Restore a verified copy without consuming the backup.
                require(sha(read_pinned(paths['menu_backup'])) == plan['menu_before_sha256'],
                        'RECOVERY_MENU_MISSING_WITHOUT_VALID_BACKUP')
                require(not exists(paths['menu_restore']), 'RECOVERY_MENU_ARTIFACT_COLLISION')
                write_new_durable(paths['menu_restore'], read_pinned(paths['menu_backup']))
                move_no_replace(paths['menu_restore'], layout.menu)
                actions.append('MENU_REINSTATED_AFTER_PARTIAL_REPLACE')
            menu_digest = sha(read_pinned(layout.menu))
            active_digest = digest_or_none(layout.active)
            try:
                decision = recovery_decision(phase, menu_digest=menu_digest, active_digest=active_digest, plan=plan)
            except ContractBlocked as exc:
                raise Blocked('RECOVERY_' + str(exc)) from exc
            if phase == 'COMMITTED':
                return dict(schema=WRITER_SCHEMA, status='COMMITTED_VERIFIED_NO_WRITE', plan_sha256=plan_sha,
                            decision=decision, layout_kind=layout.kind)
            if phase == 'ROLLED_BACK':
                return dict(schema=WRITER_SCHEMA, status='ROLLED_BACK_VERIFIED_NO_WRITE', plan_sha256=plan_sha,
                            decision=decision, layout_kind=layout.kind)
            require(str(paths['menu_backup']) == evidence['menu_backup_path']
                    and str(layout.menu) == evidence['menu_path']
                    and str(layout.active) == evidence['active_path'], 'RECOVERY_LAYOUT_EVIDENCE')
            # Validate everything needed BEFORE the first recovery write.
            if menu_digest == plan['menu_after_sha256']:
                require(sha(read_pinned(paths['menu_backup'])) == plan['menu_before_sha256'],
                        'RECOVERY_MENU_BACKUP_INVALID')
                require(not exists(paths['menu_restore']) and not exists(paths['menu_displaced']),
                        'RECOVERY_MENU_ARTIFACT_COLLISION')
            seq = len([p for p in layout.tx.iterdir() if p.name.startswith('PHASE_')]) + 1
            if active_digest is not None:
                _displace(layout.active, layout.tx / 'ROLLBACK_DISPLACED_ACTIVE.json', plan['active_after_sha256'])
                actions.append('ACTIVE_DISPLACED_INTO_TRANSACTION')
            if exists(paths['active_pending']):
                move_no_replace(paths['active_pending'], layout.tx / 'ROLLBACK_ABANDONED_ACTIVE_PENDING.json')
                actions.append('ACTIVE_PENDING_PRESERVED')
            hook('RECOVERY_AFTER_ACTIVE_DISPLACED')
            if menu_digest == plan['menu_after_sha256']:
                write_new_durable(paths['menu_restore'], read_pinned(paths['menu_backup']))
                replace_with_backup(layout.menu, paths['menu_restore'], paths['menu_displaced'])
                require(sha(read_pinned(paths['menu_displaced'])) == plan['menu_after_sha256'],
                        'RECOVERY_MENU_CONCURRENT_SWAP')
                actions.append('MENU_RESTORED_FROM_BACKUP')
            hook('RECOVERY_AFTER_MENU_RESTORED')
            if exists(paths['menu_pending']):
                move_no_replace(paths['menu_pending'], paths['menu_pending'].with_name(
                    paths['menu_pending'].name + '.abandoned'))
                actions.append('MENU_PENDING_PRESERVED')
            require(sha(read_pinned(layout.menu)) == plan['menu_before_sha256'] and not exists(layout.active),
                    'RECOVERY_READBACK')
            _journal(layout.tx, plan_sha, 'ROLLED_BACK', seq, {'recovered_from': phase, 'actions': actions})
            return dict(schema=WRITER_SCHEMA, status='ROLLED_BACK', recovered_from=phase, actions=actions,
                        plan_sha256=plan_sha, layout_kind=layout.kind, production_started=False)
        finally:
            core._windows_unpin(pins) if pins else None


def mkdir_archive(path: Path):
    if not exists(path):
        mkdir_new(path)
    core.strict_directory(path, create=False)


def archive_rolled_back(layout: Layout):
    """Move a verified ROLLED_BACK transaction and its D: artifacts aside (no deletion)."""
    layout.validate()
    with ExclusiveLock(layout.lock):
        plan, phase, evidence, plan_sha = load_transaction(layout.tx)
        require(phase == 'ROLLED_BACK', 'ARCHIVE_ONLY_ROLLED_BACK')
        require(sha(read_pinned(layout.menu)) == plan['menu_before_sha256'] and not exists(layout.active),
                'ARCHIVE_TARGET_DRIFT')
        label = plan_sha[:16] + '_' + str(time.time_ns())
        menu_archive = layout.menu.parent / MENU_ARCHIVE_NAME
        mkdir_archive(menu_archive)
        mkdir_new(menu_archive / label)
        token = '.TICKSTORE_MENU_' + evidence['package_sha256'][:16] + '.'
        for item in sorted(layout.menu.parent.iterdir()):
            if item.name.startswith(token):
                move_no_replace(item, menu_archive / label / item.name.lstrip('.'))
        mkdir_archive(layout.archive)
        move_no_replace(layout.tx, layout.archive / label)
    return dict(schema=WRITER_SCHEMA, status='ROLLED_BACK_ARCHIVED', archive_label=label, layout_kind=layout.kind)


# --------------------------------------------------------------------------- official entry

def official_admission(installed_root: Path, chain_file, chain_sha256, b06_sha256, *, live_readonly=True):
    """Technical gate for real targets: Windows + chain through B07 (+ live admission to publish).

    Recovery skips the read-only admission because that probe, by design, blocks
    whenever a transaction exists; recovery is itself hash-bound to the journal.
    """
    require(os.name == 'nt', 'OFFICIAL_WRITER_WINDOWS_REQUIRED')
    from FULL_RELEASE_CHAIN import ReleaseChain
    from MENU_OFFICIAL_ADMISSION_READONLY import run_readonly, Blocked as AdmissionBlocked
    code_root = HERE.parent
    require(Path(installed_root).absolute() == code_root.parent.parent,
            'OFFICIAL_WRITER_MUST_RUN_FROM_INSTALLED_CANDIDATE')
    admission = ReleaseChain(chain_file, chain_sha256, b06_sha256, code_root, until='B07')
    if not live_readonly:
        return admission, None
    try:
        live = run_readonly()
    except AdmissionBlocked as exc:
        admission.close()
        raise Blocked('LIVE_TARGET_ADMISSION:' + str(exc)) from exc
    return admission, live


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--mode', required=True, choices=('qualification-publish', 'qualification-recover',
                                                     'qualification-archive', 'official-publish',
                                                     'official-recover'))
    ap.add_argument('--installed-root')
    ap.add_argument('--package-sha256')
    ap.add_argument('--witness-sha256')
    ap.add_argument('--d-root'); ap.add_argument('--c-root')
    ap.add_argument('--menu-before-sha256'); ap.add_argument('--bat-sha256')
    ap.add_argument('--inject', choices=INJECTION_POINTS)
    ap.add_argument('--inject-mode', default='EXIT', choices=('EXIT', 'RAISE', 'SWAP'))
    ap.add_argument('--chain-file'); ap.add_argument('--chain-sha256'); ap.add_argument('--b06-sha256')
    a = ap.parse_args(argv)
    try:
        if a.mode.startswith('qualification-'):
            require(not a.chain_file, 'QUALIFICATION_TAKES_NO_CHAIN')
            layout = qualification_layout(Path(a.d_root), Path(a.c_root), a.menu_before_sha256, a.bat_sha256)
            hook = Injector(layout, a.inject, a.inject_mode)
            if a.mode == 'qualification-publish':
                result = publish(layout, installed_root=Path(a.installed_root),
                                 trusted_package_sha256=a.package_sha256,
                                 trusted_witness_sha256=a.witness_sha256, inject=hook)
            elif a.mode == 'qualification-recover':
                result = recover(layout, inject=hook)
            else:
                result = archive_rolled_back(layout)
        else:
            require(a.inject is None, 'INJECTION_FORBIDDEN_OFFICIAL')
            admission, live = official_admission(Path(a.installed_root), a.chain_file, a.chain_sha256,
                                                 a.b06_sha256, live_readonly=a.mode == 'official-publish')
            try:
                layout = official_layout()
                if a.mode == 'official-publish':
                    result = publish(layout, installed_root=Path(a.installed_root),
                                     trusted_package_sha256=a.package_sha256,
                                     trusted_witness_sha256=a.witness_sha256,
                                     writer_identity={'live_admission': live['verdict'],
                                                      'release_chain_sha256': a.chain_sha256})
                else:
                    result = recover(layout)
                admission.revalidate()
            finally:
                admission.close()
        print(canonical(result).decode('utf-8'), end='')
        print('MENU_WRITER_STATUS=' + result['status'], flush=True)
        return 0
    except (Blocked, ContractBlocked, IntentBlocked, core.Blocked, OSError, KeyError, TypeError, ValueError) as exc:
        print('MENU_WRITER_BLOCKED=' + type(exc).__name__ + ':' + str(exc), flush=True)
        return 2


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from RUN_LOG_FIXED import run_with_fixed_log
    raise SystemExit(run_with_fixed_log('MENU_OFFICIAL_WRITER', main))
