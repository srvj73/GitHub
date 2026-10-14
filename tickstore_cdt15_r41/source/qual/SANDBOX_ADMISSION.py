"""R44-DROOT-01: physical admission of qualification sandbox roots (no reparse, no redirection).

A sandbox root is admitted only when every existing component from the volume root down
to the root itself is a plain directory (no reparse point of any tag: junction, symlink,
mount point, cloud placeholder), the object resolves to itself (GetFinalPathNameByHandleW
on Windows, realpath on POSIX), and it lies on NTFS (Windows).  The identity (volume
serial + file index) is recorded at admission and re-checked later, so a root swapped
during the run is detected.  Read-only: admission never creates, renames or deletes.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class AdmissionBlocked(RuntimeError):
    pass


def _require(ok, reason):
    if not ok:
        raise AdmissionBlocked(reason)


def _win():
    import ctypes
    from ctypes import wintypes as w
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
    k.CreateFileW.restype = w.HANDLE
    k.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
    k.GetFinalPathNameByHandleW.restype = w.DWORD
    k.CloseHandle.argtypes = [w.HANDLE]
    k.GetVolumeInformationByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, ctypes.POINTER(w.DWORD),
                                                ctypes.POINTER(w.DWORD), ctypes.POINTER(w.DWORD), w.LPWSTR, w.DWORD]
    k.GetVolumeInformationByHandleW.restype = w.BOOL

    class INFO(ctypes.Structure):
        _fields_ = [('attrs', w.DWORD), ('c1', w.DWORD), ('c2', w.DWORD), ('a1', w.DWORD), ('a2', w.DWORD),
                    ('w1', w.DWORD), ('w2', w.DWORD), ('serial', w.DWORD), ('size_hi', w.DWORD), ('size_lo', w.DWORD),
                    ('links', w.DWORD), ('idx_hi', w.DWORD), ('idx_lo', w.DWORD)]
    k.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(INFO)]
    k.GetFileInformationByHandle.restype = w.BOOL
    return ctypes, w, k, INFO


def _native_identity(path):
    """(final_path, filesystem, volume_serial, file_index) of a directory handle (follows links)."""
    ctypes, w, k, INFO = _win()
    h = k.CreateFileW(str(path), 0x80, 7, None, 3, 0x02000000, None)  # FILE_READ_ATTRIBUTES, BACKUP_SEMANTICS
    _require(h is not None and h != ctypes.c_void_p(-1).value, 'ADMISSION_OPEN:%s:%d' % (path, ctypes.get_last_error()))
    try:
        buf = ctypes.create_unicode_buffer(32768)
        n = k.GetFinalPathNameByHandleW(h, buf, 32768, 0)
        _require(0 < n < 32768, 'ADMISSION_FINAL_PATH:%d' % ctypes.get_last_error())
        final = buf.value
        if final.startswith('\\\\?\\UNC\\'):
            final = '\\\\' + final[8:]
        elif final.startswith('\\\\?\\'):
            final = final[4:]
        fs = ctypes.create_unicode_buffer(261)
        _require(k.GetVolumeInformationByHandleW(h, None, 0, None, None, None, fs, 261), 'ADMISSION_VOLUME_INFO')
        info = INFO()
        _require(k.GetFileInformationByHandle(h, ctypes.byref(info)), 'ADMISSION_FILE_INFO')
        return final, fs.value, '%08X' % info.serial, '%08X%08X' % (info.idx_hi, info.idx_lo)
    finally:
        k.CloseHandle(h)


def components(path):
    p = Path(os.path.abspath(path))
    return list(reversed([p, *p.parents]))


def admit_root(path, *, must_exist=True, require_ntfs=None):
    """Admit `path` as a sandbox root; return its identity record.  Raises AdmissionBlocked."""
    raw = str(path)
    _require(os.path.isabs(raw) and '..' not in Path(raw).parts, 'ADMISSION_PATH_NOT_ABSOLUTE_NORMAL:' + raw)
    p = Path(os.path.abspath(raw))
    native = os.name == 'nt'
    require_ntfs = native if require_ntfs is None else require_ntfs
    checked = []
    for c in components(p):
        if not os.path.lexists(c):
            _require(not must_exist or c != p, 'ADMISSION_ROOT_MISSING:' + str(c))
            continue
        st = os.lstat(c)
        reparse = bool(getattr(st, 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT)
        _require(not stat.S_ISLNK(st.st_mode) and not reparse, 'ADMISSION_REPARSE_COMPONENT:' + str(c))
        _require(stat.S_ISDIR(st.st_mode), 'ADMISSION_NOT_DIRECTORY:' + str(c))
        checked.append(str(c))
    record = {'path': str(p), 'components_checked': checked}
    if os.path.lexists(p):
        if native:
            final, fs, serial, index = _native_identity(p)
            _require(os.path.normcase(final) == os.path.normcase(str(p)), 'ADMISSION_REDIRECTED:%s->%s' % (p, final))
            if require_ntfs:
                _require(fs == 'NTFS', 'ADMISSION_NOT_NTFS:' + fs)
            record.update(final_path=final, filesystem=fs, volume_serial=serial, file_index=index)
        else:
            real = os.path.realpath(p)
            _require(real == str(p), 'ADMISSION_REDIRECTED:%s->%s' % (p, real))
            st = os.stat(p)
            record.update(final_path=real, filesystem='POSIX', volume_serial='%X' % st.st_dev, file_index='%X' % st.st_ino)
    return record


def revalidate(record):
    """Same admission and same physical identity as at admission time."""
    now = admit_root(record['path'])
    for key in ('final_path', 'volume_serial', 'file_index'):
        _require(now.get(key) == record.get(key), 'ADMISSION_IDENTITY_CHANGED:' + key)
    return now


def audit_tree(root, limit=200000):
    """Read-only census of every reparse point and non-directory special object below root."""
    out = {'root': str(root), 'entries': 0, 'reparse_points': [], 'truncated': False}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            out['entries'] += 1
            q = os.path.join(dirpath, name)
            try:
                st = os.lstat(q)
            except OSError as exc:
                out['reparse_points'].append({'path': q, 'error': type(exc).__name__})
                continue
            if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                item = {'path': q, 'is_dir_entry': name in dirnames}
                try:
                    item['target'] = os.readlink(q)
                except OSError as exc:
                    item['target'] = 'UNREADABLE:' + type(exc).__name__
                out['reparse_points'].append(item)
            if out['entries'] >= limit:
                out['truncated'] = True
                return out
        # never descend into reparse directories
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))
                       and not (getattr(os.lstat(os.path.join(dirpath, d)), 'st_file_attributes', 0)
                                & FILE_ATTRIBUTE_REPARSE_POINT)]
    return out


# ----------------------------------------------------------------------------- R44D2: handle-bound identity

_OPEN_DIR_SELF = 0x02000000 | 0x00200000   # BACKUP_SEMANTICS | OPEN_REPARSE_POINT (never follow)
_SHARE_NO_DELETE = 0x1 | 0x2                # READ | WRITE; no FILE_SHARE_DELETE: no rename/delete/replace


class HeldDirectory:
    """Handle on the directory object itself, held without FILE_SHARE_DELETE.

    While held, the directory cannot be renamed, deleted or replaced by a junction (Windows).
    Identity (not a reparse point, final path, volume serial, file index) is read from the
    handle, so a later path lookup must reach the very same object.  POSIX keeps an
    O_NOFOLLOW directory fd (identity only; POSIX cannot deny rename).
    """

    def __init__(self, path):
        self.path = str(Path(os.path.abspath(str(path))))
        self.native = os.name == 'nt'
        if self.native:
            ctypes, w, k, INFO = _win()
            self._k, self._ctypes, self._w, self._INFO = k, ctypes, w, INFO
            k.GetFileInformationByHandleEx.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
            k.GetFileInformationByHandleEx.restype = w.BOOL
            h = k.CreateFileW(self.path, 0x80 | 0x00100000, _SHARE_NO_DELETE, None, 3, _OPEN_DIR_SELF, None)
            _require(h is not None and h != ctypes.c_void_p(-1).value,
                     'HOLD_OPEN:%s:%d' % (self.path, ctypes.get_last_error()))
            self.handle = h
        else:
            self.fd = os.open(self.path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        try:
            self.identity = self.read_identity()
            _require(self.identity['reparse'] is False, 'HOLD_REPARSE:' + self.path)
            _require(os.path.normcase(self.identity['final_path']) == os.path.normcase(self.path),
                     'HOLD_REDIRECTED:%s->%s' % (self.path, self.identity['final_path']))
        except BaseException:
            self.close()
            raise

    def read_identity(self):
        if not self.native:
            st = os.fstat(self.fd)
            return {'reparse': False, 'final_path': self.path, 'filesystem': 'POSIX',
                    'volume_serial': '%X' % st.st_dev, 'file_index': '%X' % st.st_ino}
        ctypes, w, k = self._ctypes, self._w, self._k

        class TAG(ctypes.Structure):
            _fields_ = [('attrs', w.DWORD), ('tag', w.DWORD)]
        tag = TAG()
        _require(k.GetFileInformationByHandleEx(self.handle, 9, ctypes.byref(tag), ctypes.sizeof(tag)), 'HOLD_TAG_INFO')
        buf = ctypes.create_unicode_buffer(32768)
        n = k.GetFinalPathNameByHandleW(self.handle, buf, 32768, 0)
        _require(0 < n < 32768, 'HOLD_FINAL_PATH')
        final = buf.value[4:] if buf.value.startswith('\\\\?\\') else buf.value
        fs = ctypes.create_unicode_buffer(261)
        _require(k.GetVolumeInformationByHandleW(self.handle, None, 0, None, None, None, fs, 261), 'HOLD_VOLUME_INFO')
        info = self._INFO()
        _require(k.GetFileInformationByHandle(self.handle, ctypes.byref(info)), 'HOLD_FILE_INFO')
        return {'reparse': bool(tag.attrs & FILE_ATTRIBUTE_REPARSE_POINT) or tag.tag != 0, 'final_path': final,
                'filesystem': fs.value, 'volume_serial': '%08X' % info.serial,
                'file_index': '%08X%08X' % (info.idx_hi, info.idx_lo)}

    def verify(self):
        """Handle still names the same non-reparse object, and the path still resolves to it."""
        now = self.read_identity()
        _require(now == self.identity, 'HOLD_IDENTITY_CHANGED:' + self.path)
        again = admit_root(self.path, require_ntfs=False)
        _require((again.get('volume_serial'), again.get('file_index')) == (now['volume_serial'], now['file_index']),
                 'HOLD_PATH_NO_LONGER_REACHES_HELD_OBJECT:' + self.path)
        return now

    def close(self):
        if getattr(self, 'native', False) and getattr(self, 'handle', None):
            self._k.CloseHandle(self.handle); self.handle = None
        elif getattr(self, 'fd', None) is not None:
            os.close(self.fd); self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class HeldChain:
    """Admit `path` (must exist, no reparse component, resolves to itself, NTFS on Windows) and
    hold every component from the volume root down to it.  Nothing is created."""

    def __init__(self, path, *, require_ntfs=None):
        self.record = admit_root(path, must_exist=True, require_ntfs=require_ntfs)
        self.held = []
        try:
            for c in components(self.record['path']):
                self.held.append(HeldDirectory(c))
            self.leaf = self.held[-1]
            _require((self.leaf.identity['volume_serial'], self.leaf.identity['file_index'])
                     == (self.record.get('volume_serial'), self.record.get('file_index')), 'HOLD_ADMISSION_RACE')
        except BaseException:
            self.close()
            raise

    def verify(self):
        for h in self.held:
            h.verify()
        return self.leaf.identity

    def close(self):
        for h in reversed(self.held):
            h.close()
        self.held = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def create_run_dir_exclusive(chain, name):
    """New directory `name` directly under the held, admitted leaf; never reuses or follows."""
    import re
    _require(re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', name) is not None and name not in ('.', '..'), 'RUN_DIR_NAME:' + name)
    chain.verify()
    target = os.path.join(chain.record['path'], name)
    _require(not os.path.lexists(target), 'RUN_DIR_PREEXISTS:' + target)
    os.mkdir(target)  # exclusive: FileExistsError if anything (incl. a junction) appeared meanwhile
    chain.verify()
    held = HeldDirectory(target)
    parent = chain.leaf.identity
    _require(held.identity['volume_serial'] == parent['volume_serial'], 'RUN_DIR_OTHER_VOLUME')
    _require(os.path.normcase(held.identity['final_path']) == os.path.normcase(
        os.path.join(parent['final_path'], name)), 'RUN_DIR_NOT_UNDER_HELD_PARENT')
    return held
