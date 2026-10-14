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
