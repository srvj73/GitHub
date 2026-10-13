#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import csv
import errno
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid
import zipfile

import pts2g_reference as ref

RUNNER_SCHEMA="TICKSTORE_SERIAL_RUNNER_V001R9_FULL_SERIAL_RELEASE_RC1"
FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True
FULL_OWNER_GATE_SCHEMA="TICKSTORE_FULL_OWNER_GATE_V001"
FULL_PLAN_CONTRACT_SHA256="D07217CDB7BB50DC6EECCC1DF7746F412BD71B1E5968CFB133B5A6E06AA3A4D5"
GATE_B_CERTIFICATE_SHA256="7D142D73D740986FA62219DE6CA0C9BD0AF347A9186D58AC1C8DFB35EFB5DFF7"
FROZEN_REFERENCE_SHA256="74EE141B014DE7A9F9C401C2B3C5AF6BF72E5D7D80F49E67F9D9032338480165"
JOURNAL_SCHEMA="TICKSTORE_DAY_JOURNAL_V003"
COMMIT_SCHEMA="TICKSTORE_DAY_COMMIT_V003"
MANIFEST_SCHEMA="TICKSTORE_GLOBAL_MANIFEST_V003"
FORMAT_ID="PTS2G001"
CODEC_ID="ZSTD9"
ROW_GROUP_TICKS=262_144
EXPECTED_P4A_LEDGER_SHA256="27FF5A0FE47F3DDC5FD63F6371CCF0EDA8124E0E5D504A8F0756A4DF0DB9C3CA"

# R3 independent audit authorizes only a separate, explicitly-gated Windows pilot revision.
# This package may execute ONE explicitly selected pilot day after its machine preflight and
# owner gate are both present. Full-history remains intentionally unavailable.
PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True
FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False
WINDOWS_PREFLIGHT_SCHEMA="TICKSTORE_WINDOWS_GATE_B_PREFLIGHT_V005"
OWNER_GATE_SCHEMA="TICKSTORE_PILOT_OWNER_GATE_V002"
FROZEN_PILOT_DATES=("20260731","20211022")
REQUIRED_PREFLIGHT_PASS_RESULTS=(
    "native_zstd_roundtrip","hardlink_alias","ads","junction_reparse",
    "createfile_share_denial","live_ancestor_rename_denial",
    "transient_external_denial","single_writer",
)

class Blocked(RuntimeError):
    pass

def sha256_bytes(b:bytes)->str:
    return hashlib.sha256(b).hexdigest().upper()


def sha256_file(path:Path, chunk=8*1024*1024)->str:
    fd=secure_open_existing_fd(path,writable=False)
    try:
        h=hashlib.sha256()
        with os.fdopen(fd,"rb",buffering=chunk) as f:
            fd=-1
            while True:
                b=f.read(chunk)
                if not b:break
                h.update(b)
        return h.hexdigest().upper()
    finally:
        if fd!=-1:os.close(fd)

def stable_json(obj)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")


def atomic_write_bytes(path:Path,data:bytes):
    assert_no_link_chain(path.parent,allow_missing_tail=False)
    tmp=path.with_suffix(path.suffix+".partial")
    if strict_lstat(tmp,allow_missing=True) is not None:
        raise Blocked("ATOMIC_PARTIAL_ALREADY_EXISTS:"+str(tmp))
    fd=secure_create_new_fd(tmp)
    try:
        with os.fdopen(fd,"wb") as f:
            fd=-1
            f.write(data);f.flush();os.fsync(f.fileno())
    finally:
        if fd!=-1:os.close(fd)
    secure_replace(tmp,path)

def atomic_write_json(path:Path,obj):
    atomic_write_bytes(path,stable_json(obj)+b"\n")


def write_transaction_json(path:Path,obj):
    """Publish transaction sidecar through an unambiguous non-authoritative .stage."""
    stage=Path(str(path)+".stage")
    if strict_lstat(path,allow_missing=True) is not None:
        raise Blocked("TRANSACTION_FILE_ALREADY_EXISTS:"+str(path))
    if strict_lstat(stage,allow_missing=True) is not None:
        raise Blocked("TRANSACTION_STAGE_CONFLICT:"+str(stage))
    fd=secure_create_new_fd(stage)
    try:
        with os.fdopen(fd,"wb") as f:
            fd=-1;f.write(stable_json(obj)+b"\n");f.flush();os.fsync(f.fileno())
    finally:
        if fd!=-1:os.close(fd)
    secure_replace(stage,path)

def strict_lstat(path:Path,allow_missing:bool=False):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        if allow_missing:return None
        raise Blocked("PATH_MISSING:"+str(path))
    except OSError as e:
        raise Blocked(f"PATH_QUERY_FAIL:{path}:{type(e).__name__}:{getattr(e,'errno',None)}") from e

def is_reparse(st)->bool:
    attrs=int(getattr(st,"st_file_attributes",0) or 0)
    bit=int(getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0) or 0)
    return bool(bit and attrs & bit)

def _reject_link_or_reparse(path:Path,st):
    if stat.S_ISLNK(st.st_mode) or is_reparse(st):
        raise Blocked("LINK_OR_REPARSE_NOT_ALLOWED:"+str(path))

def _reject_multiple_links(path:Path,st):
    """Reject regular files with aliases before any runner mutation/publication."""
    if stat.S_ISREG(st.st_mode):
        links=int(getattr(st,"st_nlink",1) or 0)
        if links!=1:
            raise Blocked(f"MULTIPLE_HARDLINKS_NOT_ALLOWED:{path}:nlink={links}")

def assert_no_link_chain(path:Path,allow_missing_tail:bool=False):
    """Validate every existing path component without following links/reparse points."""
    p=Path(os.path.abspath(str(path)))
    parts=p.parts
    if not parts:
        raise Blocked("EMPTY_PATH")
    cur=Path(parts[0])
    # Anchor/root is trusted only if it is a directory. All remaining components are checked.
    try:
        rst=os.lstat(cur)
    except OSError as e:
        raise Blocked(f"PATH_CHAIN_ROOT_QUERY_FAIL:{cur}:{type(e).__name__}") from e
    _reject_link_or_reparse(cur,rst)
    for part in parts[1:]:
        cur=cur/part
        try:
            st=os.lstat(cur)
        except FileNotFoundError:
            if allow_missing_tail:
                return
            raise Blocked("PATH_CHAIN_MISSING:"+str(cur))
        except OSError as e:
            raise Blocked(f"PATH_CHAIN_QUERY_FAIL:{cur}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
        _reject_link_or_reparse(cur,st)

def strict_regular_file(path:Path):
    assert_no_link_chain(path.parent,allow_missing_tail=False)
    st=strict_lstat(path)
    _reject_link_or_reparse(path,st)
    if not stat.S_ISREG(st.st_mode):
        raise Blocked("NOT_REGULAR_FILE:"+str(path))
    _reject_multiple_links(path,st)
    return st

def strict_directory(path:Path,create=False):
    p=Path(os.path.abspath(str(path)))
    if create:
        parts=p.parts
        if not parts:
            raise Blocked("EMPTY_DIRECTORY_PATH")
        if os.name!="nt":
            flags=os.O_RDONLY|int(getattr(os,"O_DIRECTORY",0) or 0)|int(getattr(os,"O_NOFOLLOW",0) or 0)|int(getattr(os,"O_CLOEXEC",0) or 0)
            fd=-1
            try:
                fd=os.open(parts[0],flags)
                st=os.fstat(fd)
                if not stat.S_ISDIR(st.st_mode):
                    raise Blocked("PATH_ROOT_NOT_DIRECTORY:"+str(parts[0]))
                for part in parts[1:]:
                    try:
                        nfd=os.open(part,flags,dir_fd=fd)
                    except FileNotFoundError:
                        try:
                            os.mkdir(part,dir_fd=fd)
                        except FileExistsError:
                            pass
                        except OSError as e:
                            raise Blocked(f"DIRECTORY_CREATE_FAIL:{p}:{part}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
                        try:
                            nfd=os.open(part,flags,dir_fd=fd)
                        except OSError as e:
                            raise Blocked(f"DIRECTORY_OPEN_AFTER_CREATE_FAIL:{p}:{part}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
                    except OSError as e:
                        raise Blocked(f"DIRECTORY_CHAIN_OPEN_FAIL:{p}:{part}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
                    nst=os.fstat(nfd)
                    if not stat.S_ISDIR(nst.st_mode):
                        os.close(nfd);raise Blocked("NOT_DIRECTORY_COMPONENT:"+str(part))
                    os.close(fd);fd=nfd
                return os.fstat(fd)
            finally:
                if fd!=-1:os.close(fd)
        # Windows: create only while every already-existing ancestor is pinned against
        # rename/delete. Each newly created component is then handle-validated before use.
        cur=Path(parts[0])
        st=strict_lstat(cur)
        _reject_link_or_reparse(cur,st)
        if not stat.S_ISDIR(st.st_mode):
            raise Blocked("PATH_ROOT_NOT_DIRECTORY:"+str(cur))
        for part in parts[1:]:
            cur=cur/part
            st=strict_lstat(cur,allow_missing=True)
            if st is None:
                pins=_windows_pin_ancestor_chain(cur.parent)
                try:
                    try:os.mkdir(cur)
                    except FileExistsError:pass
                    except OSError as e:raise Blocked(f"DIRECTORY_CREATE_FAIL:{cur}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
                finally:
                    _windows_unpin(pins)
                st=strict_lstat(cur)
            _reject_link_or_reparse(cur,st)
            if not stat.S_ISDIR(st.st_mode):raise Blocked("NOT_DIRECTORY:"+str(cur))
            k32,h=_windows_open_directory_handle(cur)
            k32.CloseHandle(h)
        return strict_lstat(p)
    assert_no_link_chain(p,allow_missing_tail=False)
    st=strict_lstat(p)
    _reject_link_or_reparse(p,st)
    if not stat.S_ISDIR(st.st_mode):
        raise Blocked("NOT_DIRECTORY:"+str(p))
    return st

def _posix_parent_fd(path:Path):
    """Open the parent by walking one no-follow directory handle at a time.

    The returned parent fd pins the resolved directory object. Later file operations use
    only the basename plus dir_fd, so swapping an ancestor after this walk cannot redirect
    the operation to another tree.
    """
    p=Path(os.path.abspath(str(path)))
    parent=p.parent
    parts=parent.parts
    if not parts:
        raise Blocked("EMPTY_PARENT_PATH:"+str(path))
    flags=os.O_RDONLY|int(getattr(os,"O_DIRECTORY",0) or 0)|int(getattr(os,"O_NOFOLLOW",0) or 0)|int(getattr(os,"O_CLOEXEC",0) or 0)
    fd=-1
    try:
        fd=os.open(parts[0],flags)
        st=os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise Blocked("PARENT_CHAIN_NOT_DIRECTORY:"+str(parts[0]))
        for part in parts[1:]:
            try:
                nfd=os.open(part,flags,dir_fd=fd)
            except OSError as e:
                raise Blocked(f"PARENT_CHAIN_OPEN_FAIL:{parent}:{part}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
            try:
                nst=os.fstat(nfd)
                if not stat.S_ISDIR(nst.st_mode):
                    raise Blocked("PARENT_CHAIN_NOT_DIRECTORY:"+str(part))
            except Exception:
                os.close(nfd)
                raise
            os.close(fd);fd=nfd
        return p,fd
    except Exception:
        if fd!=-1:
            try: os.close(fd)
            except OSError: pass
        raise

def _windows_strip_extended_prefix(value:str)->str:
    if value.startswith('\\\\?\\UNC\\'):
        return '\\\\'+value[8:]
    if value.startswith('\\\\?\\'):
        return value[4:]
    return value

def _windows_normalized_path(path)->str:
    return os.path.normcase(os.path.normpath(os.path.abspath(_windows_strip_extended_prefix(str(path)))))

def _windows_reject_ads_path(path:Path):
    # Drive-colon is allowed; any later colon is an alternate data stream.
    full=os.path.abspath(str(path))
    _drive,tail=os.path.splitdrive(full)
    if ':' in tail:
        raise Blocked("WIN_ADS_NOT_ALLOWED:"+str(path))

def _windows_handle_info(k32,h,path:Path):
    class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_=[
            ("dwFileAttributes",ctypes.wintypes.DWORD),
            ("ftCreationTime",ctypes.wintypes.FILETIME),
            ("ftLastAccessTime",ctypes.wintypes.FILETIME),
            ("ftLastWriteTime",ctypes.wintypes.FILETIME),
            ("dwVolumeSerialNumber",ctypes.wintypes.DWORD),
            ("nFileSizeHigh",ctypes.wintypes.DWORD),
            ("nFileSizeLow",ctypes.wintypes.DWORD),
            ("nNumberOfLinks",ctypes.wintypes.DWORD),
            ("nFileIndexHigh",ctypes.wintypes.DWORD),
            ("nFileIndexLow",ctypes.wintypes.DWORD),
        ]
    info=BY_HANDLE_FILE_INFORMATION()
    if not k32.GetFileInformationByHandle(h,ctypes.byref(info)):
        err=ctypes.get_last_error()
        raise Blocked(f"WIN_HANDLE_INFO_FAIL:{path}:winerror={err}")
    return info

def _windows_final_handle_path(k32,h,path:Path)->str:
    fn=k32.GetFinalPathNameByHandleW
    fn.argtypes=[ctypes.wintypes.HANDLE,ctypes.wintypes.LPWSTR,ctypes.wintypes.DWORD,ctypes.wintypes.DWORD]
    fn.restype=ctypes.wintypes.DWORD
    size=512
    while True:
        buf=ctypes.create_unicode_buffer(size)
        n=fn(h,buf,size,0)
        if n==0:
            err=ctypes.get_last_error()
            raise Blocked(f"WIN_FINAL_PATH_FAIL:{path}:winerror={err}")
        if n<size:
            return buf.value
        size=int(n)+1
        if size>32768:
            raise Blocked("WIN_FINAL_PATH_TOO_LONG:"+str(path))

def _windows_validate_handle(k32,h,path:Path,expect_directory:bool=False,require_single_link:bool=True):
    _windows_reject_ads_path(path)
    info=_windows_handle_info(k32,h,path)
    FILE_ATTRIBUTE_REPARSE_POINT=0x400;FILE_ATTRIBUTE_DIRECTORY=0x10
    if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
        raise Blocked("WIN_REPARSE_HANDLE_NOT_ALLOWED:"+str(path))
    is_dir=bool(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
    if is_dir!=bool(expect_directory):
        raise Blocked("WIN_HANDLE_TYPE_MISMATCH:"+str(path))
    if not is_dir and require_single_link and int(info.nNumberOfLinks)!=1:
        raise Blocked(f"MULTIPLE_HARDLINKS_NOT_ALLOWED:{path}:nlink={int(info.nNumberOfLinks)}")
    actual=_windows_normalized_path(_windows_final_handle_path(k32,h,path))
    expected=_windows_normalized_path(path)
    if actual!=expected:
        raise Blocked(f"WIN_HANDLE_PATH_MISMATCH:{path}:{actual}")
    return info

def _windows_open_directory_handle(path:Path):
    _windows_reject_ads_path(path)
    k32=ctypes.WinDLL("kernel32",use_last_error=True)
    CreateFileW=k32.CreateFileW
    CreateFileW.argtypes=[ctypes.wintypes.LPCWSTR,ctypes.wintypes.DWORD,ctypes.wintypes.DWORD,ctypes.c_void_p,ctypes.wintypes.DWORD,ctypes.wintypes.DWORD,ctypes.wintypes.HANDLE]
    CreateFileW.restype=ctypes.wintypes.HANDLE
    FILE_LIST_DIRECTORY=0x1;FILE_READ_ATTRIBUTES=0x80;SYNCHRONIZE=0x00100000
    FILE_SHARE_READ=0x1;FILE_SHARE_WRITE=0x2
    OPEN_EXISTING=3;FILE_FLAG_OPEN_REPARSE_POINT=0x00200000;FILE_FLAG_BACKUP_SEMANTICS=0x02000000
    # Windows real Gate B evidence (2026-09-24): FILE_READ_ATTRIBUTES|SYNCHRONIZE alone
    # allowed ancestor rename. Adding the least-privilege FILE_LIST_DIRECTORY access made
    # rename fail with WinError 32 until this HANDLE closed. Do not remove without new evidence.
    desired=FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES|SYNCHRONIZE
    h=CreateFileW(str(path),desired,FILE_SHARE_READ|FILE_SHARE_WRITE,None,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,None)
    INVALID=ctypes.wintypes.HANDLE(-1).value
    if h==INVALID:
        err=ctypes.get_last_error();raise Blocked(f"WIN_DIRECTORY_PIN_FAIL:{path}:winerror={err}")
    try:
        _windows_validate_handle(k32,h,path,expect_directory=True,require_single_link=False)
    except Exception:
        k32.CloseHandle(h);raise
    return k32,h

def _windows_pin_ancestor_chain(path:Path):
    """Pin every existing directory component with delete sharing denied.

    While these handles are alive Windows cannot rename/delete those directory objects,
    closing the check->replace ancestor swap that existed in R2.
    """
    p=Path(os.path.abspath(str(path)))
    chain=list(reversed(p.parents))+[p]
    handles=[]
    try:
        for cur in chain:
            k32,h=_windows_open_directory_handle(cur)
            handles.append((k32,h))
        return handles
    except Exception:
        for k32,h in reversed(handles):
            try:k32.CloseHandle(h)
            except Exception:pass
        raise

def _windows_unpin(handles):
    for k32,h in reversed(handles):
        try:k32.CloseHandle(h)
        except Exception:pass

def _windows_createfile_error(path:Path,create_new:bool,err:int):
    # CREATE_NEW reports an existing target as ERROR_FILE_EXISTS (80) or
    # ERROR_ALREADY_EXISTS (183). Normalize only those cases to the same
    # semantic contract as POSIX O_EXCL; all other failures stay fail-closed.
    if create_new and int(err) in (80,183):
        return Blocked("SECURE_CREATE_EXISTS:"+str(path))
    return Blocked(f"WIN_CREATEFILE_FAIL:{path}:winerror={int(err)}")

def _windows_open_fd(path:Path,writable:bool,create_new:bool,share_read:bool,share_write:bool=False,share_delete:bool=False):
    import msvcrt
    _windows_reject_ads_path(path)
    k32=ctypes.WinDLL("kernel32",use_last_error=True)
    CreateFileW=k32.CreateFileW
    CreateFileW.argtypes=[
        ctypes.wintypes.LPCWSTR,ctypes.wintypes.DWORD,ctypes.wintypes.DWORD,
        ctypes.c_void_p,ctypes.wintypes.DWORD,ctypes.wintypes.DWORD,ctypes.wintypes.HANDLE
    ]
    CreateFileW.restype=ctypes.wintypes.HANDLE
    GENERIC_READ=0x80000000;GENERIC_WRITE=0x40000000
    FILE_SHARE_READ=0x1;FILE_SHARE_WRITE=0x2;FILE_SHARE_DELETE=0x4
    CREATE_NEW=1;OPEN_EXISTING=3
    FILE_ATTRIBUTE_NORMAL=0x80
    FILE_FLAG_OPEN_REPARSE_POINT=0x00200000
    FILE_FLAG_SEQUENTIAL_SCAN=0x08000000
    desired=GENERIC_READ|(GENERIC_WRITE if writable else 0)
    share=(FILE_SHARE_READ if share_read else 0)|(FILE_SHARE_WRITE if share_write else 0)|(FILE_SHARE_DELETE if share_delete else 0)
    disp=CREATE_NEW if create_new else OPEN_EXISTING
    h=CreateFileW(str(path),desired,share,None,disp,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_SEQUENTIAL_SCAN,None)
    INVALID=ctypes.wintypes.HANDLE(-1).value
    if h==INVALID:
        err=ctypes.get_last_error()
        raise _windows_createfile_error(path,create_new,err)
    try:
        _windows_validate_handle(k32,h,path,expect_directory=False,require_single_link=True)
    except Exception:
        k32.CloseHandle(h);raise
    oflags=(os.O_RDWR if writable else os.O_RDONLY)|int(getattr(os,"O_BINARY",0) or 0)
    try:
        fd=msvcrt.open_osfhandle(int(h),oflags)
    except Exception:
        k32.CloseHandle(h)
        raise
    return fd

def secure_open_existing_fd(path:Path,writable:bool=False,source_pin:bool=False):
    if os.name=="nt":
        # The opened HANDLE itself proves final path + no reparse + one link. The source
        # pin also denies write/delete sharing for the lifetime of the handle.
        return _windows_open_fd(
            path,writable=writable,create_new=False,
            share_read=True,share_write=False if source_pin or writable else True,
            share_delete=False if source_pin or writable else True,
        )
    p,pfd=_posix_parent_fd(path)
    flags=(os.O_RDWR if writable else os.O_RDONLY)|int(getattr(os,"O_BINARY",0) or 0)|int(getattr(os,"O_NOFOLLOW",0) or 0)|int(getattr(os,"O_CLOEXEC",0) or 0)
    fd=-1
    try:
        try:
            fd=os.open(p.name,flags,dir_fd=pfd)
        except OSError as e:
            raise Blocked(f"SECURE_OPEN_FAIL:{path}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Blocked("SECURE_OPEN_NOT_REGULAR:"+str(path))
        _reject_multiple_links(path,st)
        pst=os.stat(p.name,dir_fd=pfd,follow_symlinks=False)
        _reject_link_or_reparse(path,pst);_reject_multiple_links(path,pst)
        pino=int(getattr(pst,"st_ino",0) or 0);fino=int(getattr(st,"st_ino",0) or 0)
        if pino and fino and (int(getattr(pst,"st_dev",0) or 0),pino)!=(int(getattr(st,"st_dev",0) or 0),fino):
            raise Blocked("SECURE_OPEN_IDENTITY_MISMATCH:"+str(path))
        out=fd;fd=-1;return out
    finally:
        if fd!=-1:os.close(fd)
        os.close(pfd)

def secure_create_new_fd(path:Path):
    if os.name=="nt":
        pins=_windows_pin_ancestor_chain(Path(path).parent)
        try:
            return _windows_open_fd(path,writable=True,create_new=True,share_read=False)
        finally:
            _windows_unpin(pins)
    p,pfd=_posix_parent_fd(path)
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|int(getattr(os,"O_BINARY",0) or 0)|int(getattr(os,"O_NOFOLLOW",0) or 0)|int(getattr(os,"O_CLOEXEC",0) or 0)
    try:
        try:
            return os.open(p.name,flags,0o600,dir_fd=pfd)
        except FileExistsError as e:
            raise Blocked("SECURE_CREATE_EXISTS:"+str(path)) from e
        except OSError as e:
            raise Blocked(f"SECURE_CREATE_FAIL:{path}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
    finally:
        os.close(pfd)

def secure_read_all(path:Path)->bytes:
    fd=secure_open_existing_fd(path,writable=False)
    try:
        with os.fdopen(fd,"rb") as f:
            fd=-1
            return f.read()
    finally:
        if fd!=-1:os.close(fd)

def secure_open_existing(path:Path,mode:str):
    writable=("+" in mode or "w" in mode or "a" in mode)
    fd=secure_open_existing_fd(path,writable=writable)
    try:
        f=os.fdopen(fd,mode)
        fd=-1
        return f
    finally:
        if fd!=-1:os.close(fd)

def safe_unlink_regular(path:Path):
    if os.name=="nt":
        pins=_windows_pin_ancestor_chain(Path(path).parent)
        try:
            strict_regular_file(path)
            try:os.unlink(path)
            except OSError as e:raise Blocked(f"UNLINK_FAIL:{path}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
        finally:
            _windows_unpin(pins)
        return
    p,pfd=_posix_parent_fd(path)
    try:
        st=os.stat(p.name,dir_fd=pfd,follow_symlinks=False)
        _reject_link_or_reparse(path,st)
        if not stat.S_ISREG(st.st_mode):raise Blocked("NOT_REGULAR_FILE:"+str(path))
        _reject_multiple_links(path,st)
        try:os.unlink(p.name,dir_fd=pfd)
        except OSError as e:raise Blocked(f"UNLINK_FAIL:{path}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
    finally:
        os.close(pfd)

def secure_replace(src:Path,dst:Path):
    src=Path(src);dst=Path(dst)
    if os.name=="nt":
        srcpins=_windows_pin_ancestor_chain(src.parent);dstpins=[]
        try:
            dstpins=_windows_pin_ancestor_chain(dst.parent)
            sst=strict_regular_file(src)
            dstst=strict_lstat(dst,allow_missing=True)
            if dstst is not None:
                _reject_link_or_reparse(dst,dstst)
                if not stat.S_ISREG(dstst.st_mode):raise Blocked("REPLACE_DEST_NOT_REGULAR:"+str(dst))
                _reject_multiple_links(dst,dstst)
            sid=(int(getattr(sst,"st_dev",0) or 0),int(getattr(sst,"st_ino",0) or 0))
            try:os.replace(src,dst)
            except OSError as e:raise Blocked(f"SECURE_REPLACE_FAIL:{src}->{dst}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
            fst=strict_regular_file(dst)
            fid=(int(getattr(fst,"st_dev",0) or 0),int(getattr(fst,"st_ino",0) or 0))
            if all(sid) and all(fid) and sid!=fid:
                raise Blocked("REPLACE_POST_IDENTITY_MISMATCH:"+str(dst))
        finally:
            _windows_unpin(dstpins);_windows_unpin(srcpins)
        return
    sp,sfd=_posix_parent_fd(src);dp,dfd=_posix_parent_fd(dst)
    try:
        try:sst=os.stat(sp.name,dir_fd=sfd,follow_symlinks=False)
        except OSError as e:raise Blocked(f"REPLACE_SOURCE_QUERY_FAIL:{src}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
        _reject_link_or_reparse(src,sst)
        if not stat.S_ISREG(sst.st_mode):raise Blocked("NOT_REGULAR_FILE:"+str(src))
        _reject_multiple_links(src,sst)
        try:dstst=os.stat(dp.name,dir_fd=dfd,follow_symlinks=False)
        except FileNotFoundError:dstst=None
        except OSError as e:raise Blocked(f"REPLACE_DEST_QUERY_FAIL:{dst}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
        if dstst is not None:
            _reject_link_or_reparse(dst,dstst)
            if not stat.S_ISREG(dstst.st_mode):raise Blocked("REPLACE_DEST_NOT_REGULAR:"+str(dst))
            _reject_multiple_links(dst,dstst)
        sid=(int(getattr(sst,"st_dev",0) or 0),int(getattr(sst,"st_ino",0) or 0))
        try:os.replace(sp.name,dp.name,src_dir_fd=sfd,dst_dir_fd=dfd)
        except OSError as e:raise Blocked(f"SECURE_REPLACE_FAIL:{src}->{dst}:{type(e).__name__}:{getattr(e,'errno',None)}") from e
        fst=os.stat(dp.name,dir_fd=dfd,follow_symlinks=False)
        _reject_link_or_reparse(dst,fst);_reject_multiple_links(dst,fst)
        fid=(int(getattr(fst,"st_dev",0) or 0),int(getattr(fst,"st_ino",0) or 0))
        if all(sid) and all(fid) and sid!=fid:
            raise Blocked("REPLACE_POST_IDENTITY_MISMATCH:"+str(dst))
    finally:
        os.close(dfd);os.close(sfd)

class PinnedSource:
    """One open source object from hash through conversion/publication."""
    def __init__(self,path:Path,expected_size:int,expected_sha:str):
        self.path=Path(path)
        self.expected_size=int(expected_size)
        self.expected_sha=expected_sha.upper()
        self.fd=None;self.file=None;self.identity=None
    def __enter__(self):
        strict_regular_file(self.path)
        self.fd=secure_open_existing_fd(self.path,writable=False,source_pin=True)
        self.file=os.fdopen(self.fd,"rb",buffering=8*1024*1024)
        self.fd=None
        st=os.fstat(self.file.fileno())
        if st.st_size!=self.expected_size:
            raise Blocked(f"SOURCE_SIZE_MISMATCH:{st.st_size}:{self.expected_size}")
        digest=self.hash_all()
        if digest!=self.expected_sha:
            raise Blocked("SOURCE_SHA256_MISMATCH:"+str(self.path))
        st2=os.fstat(self.file.fileno())
        if (st.st_size,st.st_mtime_ns,int(getattr(st,"st_dev",0) or 0),int(getattr(st,"st_ino",0) or 0)) != (
            st2.st_size,st2.st_mtime_ns,int(getattr(st2,"st_dev",0) or 0),int(getattr(st2,"st_ino",0) or 0)
        ):
            raise Blocked("SOURCE_HANDLE_CHANGED_DURING_HASH")
        self.identity={
            "normalized_path":os.path.normcase(os.path.normpath(os.path.abspath(str(self.path)))),
            "size":st2.st_size,"mtime_ns":st2.st_mtime_ns,
            "st_dev":int(getattr(st2,"st_dev",0) or 0),
            "st_ino":int(getattr(st2,"st_ino",0) or 0),
            "sha256":digest,
        }
        self.verify_path_binding()
        return self
    def __exit__(self,*exc):
        if self.file is not None:
            self.file.close();self.file=None
    def hash_all(self):
        pos=self.file.tell()
        self.file.seek(0)
        h=hashlib.sha256()
        while True:
            b=self.file.read(8*1024*1024)
            if not b:break
            h.update(b)
        self.file.seek(pos)
        return h.hexdigest().upper()
    def verify_path_binding(self):
        pst=strict_regular_file(self.path)
        if os.path.normcase(os.path.normpath(os.path.abspath(str(self.path))))!=self.identity["normalized_path"]:
            raise Blocked("SOURCE_PATH_IDENTITY_CHANGED")
        vals=(pst.st_size,pst.st_mtime_ns,int(getattr(pst,"st_dev",0) or 0),int(getattr(pst,"st_ino",0) or 0))
        exp=(self.identity["size"],self.identity["mtime_ns"],self.identity["st_dev"],self.identity["st_ino"])
        # dev/ino may be zero on some filesystems; compare when both sides expose them.
        if vals[:2]!=exp[:2]:
            raise Blocked("SOURCE_STAT_IDENTITY_CHANGED")
        if exp[3] and vals[3] and vals[2:]!=exp[2:]:
            raise Blocked("SOURCE_FILE_ID_CHANGED")
        fst=os.fstat(self.file.fileno())
        fvals=(fst.st_size,fst.st_mtime_ns,int(getattr(fst,"st_dev",0) or 0),int(getattr(fst,"st_ino",0) or 0))
        if fvals[:2]!=exp[:2] or (exp[3] and fvals[3] and fvals[2:]!=exp[2:]):
            raise Blocked("SOURCE_OPEN_HANDLE_IDENTITY_CHANGED")
        return True
    def verify_full(self):
        self.verify_path_binding()
        if self.hash_all()!=self.identity["sha256"]:
            raise Blocked("SOURCE_OPEN_HANDLE_SHA_CHANGED")
        self.verify_path_binding()
        return True
    def seek(self,*a): return self.file.seek(*a)
    def tell(self): return self.file.tell()
    def readline(self): return self.file.readline()


def normalized_path(path:Path)->str:
    strict_regular_file(path)
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def source_identity(path:Path,expected_size:int,expected_sha:str):
    # Compatibility helper for tests; production keeps PinnedSource open.
    with PinnedSource(path,expected_size,expected_sha) as ps:
        return dict(ps.identity)


def source_identity_quick_check(path:Path,identity):
    st=strict_regular_file(path)
    if normalized_path(path)!=identity["normalized_path"]:
        raise Blocked("SOURCE_PATH_IDENTITY_CHANGED")
    if st.st_size!=int(identity["size"]) or st.st_mtime_ns!=int(identity["mtime_ns"]):
        raise Blocked("SOURCE_STAT_IDENTITY_CHANGED")
    idev=int(getattr(st,"st_dev",0) or 0); iino=int(getattr(st,"st_ino",0) or 0)
    if int(identity.get("st_ino",0) or 0) and iino and (idev,iino)!=(int(identity.get("st_dev",0) or 0),int(identity.get("st_ino",0) or 0)):
        raise Blocked("SOURCE_FILE_ID_CHANGED")
    # A path-only helper is never sufficient for publication authority.
    return True


def read_json_strict(path:Path):
    try:
        raw=secure_read_all(path)
        return json.loads(raw.decode("utf-8"))
    except Blocked:
        raise
    except Exception as e:
        raise Blocked("JSON_READ_OR_PARSE_FAIL:"+str(path)) from e

def file_ids(base_dir:Path):
    runner_path=Path(__file__).resolve()
    ref_path=(base_dir/"pts2g_reference.py").resolve()
    spec_path=(base_dir/"SPEC_FULL_RUNNER_V001.md").resolve()
    preflight_path=(base_dir/"WINDOWS_GATE_B_PREFLIGHT_V005.py").resolve()
    return {
        "runner_sha256":sha256_file(runner_path),
        "reference_sha256":sha256_file(ref_path),
        "spec_sha256":sha256_file(spec_path),
        "preflight_sha256":sha256_file(preflight_path),
    }


def load_ledgers(ledger_zip:Path):
    strict_regular_file(ledger_zip)
    raw=secure_read_all(ledger_zip)
    zsha=sha256_bytes(raw)
    if zsha != EXPECTED_P4A_LEDGER_SHA256:
        raise Blocked("LEDGER_ZIP_SHA256_NOT_CANONICAL:"+zsha)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if z.testzip() is not None:
                raise Blocked("LEDGER_ZIP_CRC_FAIL")
            days=list(csv.DictReader(io.StringIO(z.read("P4A_ALL_DAYS.csv").decode("utf-8-sig"))))
            months=list(csv.DictReader(io.StringIO(z.read("P4A_MONTHS.csv").decode("utf-8-sig"))))
    except Blocked:
        raise
    except Exception as e:
        raise Blocked("LEDGER_ZIP_INVALID") from e
    if not days or not months: raise Blocked("LEDGER_EMPTY")
    month_map={m["month_id"]:m for m in months}
    if len(month_map)!=len(months): raise Blocked("DUPLICATE_MONTH_ID")
    seen=set()
    for d in days:
        key=d["date_key"]
        if key in seen: raise Blocked("DUPLICATE_DATE_KEY:"+key)
        seen.add(key)
        if d["month_id"] not in month_map: raise Blocked("DAY_MONTH_NOT_FOUND:"+key)
        for k in ("time_msc_decrease_rows","price_negative_rows","negative_unsupported_rows",
                  "price_not_multiple_5_rows","offset_seconds_change_rows",
                  "f6_f7_numeric_diff_rows","f6_f7_lexical_diff_rows",
                  "f6_noncanonical_lexical_rows","f7_noncanonical_lexical_rows"):
            if int(d[k])!=0:
                raise Blocked("DAY_NOT_CODEC_COMPATIBLE:"+key+":"+k)
    # zsha and parsed rows come from the exact same immutable byte image.
    return days,month_map,zsha

def day_contract_hash(c)->str:
    keep={k:str(v) for k,v in sorted(c.items())}
    return sha256_bytes(stable_json(keep))

def code_revision(ids)->str:
    return sha256_bytes(stable_json(ids))

def make_oracle(c,month,src_id,ledger_sha,ids):
    return {
        "schema":"TICKSTORE_DAY_ORACLE_V002",
        "date_key":c["date_key"],
        "month_id":c["month_id"],
        "rows":int(c["rows"]),
        "first_offset":int(c["first_offset"]),
        "last_offset":int(c["last_offset"]),
        "block_end_offset":int(c["block_end_offset"]),
        "source_day_bytes":int(c["source_day_bytes"]),
        "semantic_sha256":c["semantic_sha256"].upper(),
        "offset_sha256":c["offset_values_sha256"].upper(),
        "offset_seconds":int(c["offset_seconds_first"]),
        "source_identity":src_id,
        "ledger_zip_sha256":ledger_sha,
        "day_contract_sha256":day_contract_hash(c),
        "runner_ids":ids,
        "code_revision":code_revision(ids),
        "format_id":FORMAT_ID,
        "codec_id":CODEC_ID,
        "row_group_ticks":ROW_GROUP_TICKS,
        "month_expected_sha256":month["source_sha256"].upper(),
        "month_expected_size":int(month["source_size"]),
    }

def serialize_group(g):
    return {
        "group_no":g["group_no"],
        "row_start":g["row_start"],
        "row_count":g["row_count"],
        "source_first":g["source_first"],
        "source_end":g["source_end"],
        "offset_seconds":g["offset_seconds"],
        "alias":bool(g["alias"]),
        "group_semantic_sha":g["group_semantic_sha"].hex(),
        "group_offset_sha":g["group_offset_sha"].hex(),
        "sections":[{
            "name":s["name"],"payload_offset":s["payload_offset"],
            "raw_len":s["raw_len"],"stored_len":s["stored_len"],
            "raw_sha":s["raw_sha"].hex()
        } for s in g["sections"]]
    }

def deserialize_group(g):
    return {
        "group_no":int(g["group_no"]),"row_start":int(g["row_start"]),
        "row_count":int(g["row_count"]),"source_first":int(g["source_first"]),
        "source_end":int(g["source_end"]),"offset_seconds":int(g["offset_seconds"]),
        "alias":bool(g["alias"]),
        "group_semantic_sha":bytes.fromhex(g["group_semantic_sha"]),
        "group_offset_sha":bytes.fromhex(g["group_offset_sha"]),
        "sections":[{
            "name":s["name"],"payload_offset":int(s["payload_offset"]),
            "raw_len":int(s["raw_len"]),"stored_len":int(s["stored_len"]),
            "raw_sha":bytes.fromhex(s["raw_sha"])
        } for s in g["sections"]]
    }

def make_header(c,group_count):
    header=bytearray()
    header+=b"WIN@N"
    header+=struct.pack("<I",ref.FORMAT_VERSION)
    header+=struct.pack("<i",int(c["date_key"]))
    header+=struct.pack("<q",int(c["rows"]))
    header+=struct.pack("<q",int(c["offset_seconds_first"]))
    header+=struct.pack("<I",ref.GROUP_TICKS)
    header+=struct.pack("<I",group_count)
    header+=struct.pack("<BBBB",ref.CODEC_ID_ZSTD,ref.CODEC_LEVEL,ref.SECTION_COUNT,0)
    header+=bytes.fromhex(c["semantic_sha256"])
    header+=bytes.fromhex(c["offset_values_sha256"])
    header+=struct.pack("<qqq",int(c["first_offset"]),int(c["block_end_offset"]),int(c["source_day_bytes"]))
    return bytes(header)

def partial_layout(c):
    group_count=math.ceil(int(c["rows"])/ref.GROUP_TICKS)
    header=make_header(c,group_count)
    index_len=group_count*ref.INDEX_ENTRY_SIZE
    index_offset=8+4+len(header)+32+8
    index_hash_offset=index_offset+index_len
    payload_base=index_hash_offset+32
    return group_count,header,index_len,index_offset,index_hash_offset,payload_base

def prefix_bytes(c):
    group_count,header,index_len,_,_,_=partial_layout(c)
    b=bytearray()
    b+=ref.MAGIC
    b+=struct.pack("<I",len(header));b+=header;b+=ref.sha256_bytes(header)
    b+=struct.pack("<Q",index_len);b+=b"\0"*index_len;b+=b"\0"*32
    return bytes(b)

def atomic_journal(path,obj):
    atomic_write_json(path,obj)


def init_partial(partial:Path,journal:Path,c,oracle):
    if strict_lstat(partial,allow_missing=True) is not None or strict_lstat(journal,allow_missing=True) is not None:
        raise Blocked("INIT_PARTIAL_CONFLICT")
    pb=prefix_bytes(c)
    fd=secure_create_new_fd(partial)
    try:
        with os.fdopen(fd,"wb") as f:
            fd=-1;f.write(pb);f.flush();os.fsync(f.fileno())
    finally:
        if fd!=-1:os.close(fd)
    j={
        "schema":JOURNAL_SCHEMA,"state":"BUILDING","oracle":oracle,
        "completed_groups":[],"durable_end":len(pb),
        "created_unix_ns":time.time_ns(),
    }
    atomic_journal(journal,j)
    return j

def same_oracle(a,b):
    return a==b


def validate_partial_prefix(partial:Path,c):
    """Validate immutable prefix fields while allowing an interrupted/rebuilt index region."""
    group_count,header,index_len,index_offset,index_hash_offset,payload_base=partial_layout(c)
    expected=prefix_bytes(c)
    st=strict_regular_file(partial)
    if st.st_size<payload_base:
        raise Blocked("PARTIAL_SHORTER_THAN_RESERVED_PREFIX")
    with secure_open_existing(partial,"rb") as f:
        got=f.read(index_offset)
    if got!=expected[:index_offset]:
        raise Blocked("PARTIAL_IMMUTABLE_PREFIX_MISMATCH")
    return payload_base

def parsed_from_journal(c,j):
    groups=[deserialize_group(x) for x in j["completed_groups"]]
    return {
        "date_key":int(c["date_key"]),
        "total_rows":int(c["rows"]),
        "offset_seconds":int(c["offset_seconds_first"]),
        "group_count":len(groups),
        "groups":groups,
    }


JOURNAL_STATES=(
    "BUILDING",
    "VALIDATED_PENDING_PUBLISH",
    "COMMIT_STAGED",
    "CONTAINER_PUBLISHED",
    "COMMIT_PUBLISHED",
    "MANIFEST_PUBLISHED",
)

def validate_journal_structure(j,c,oracle,allowed_states=None,require_full_groups=False):
    if not isinstance(j,dict):
        raise Blocked("JOURNAL_NOT_OBJECT")
    if j.get("schema")!=JOURNAL_SCHEMA:
        raise Blocked("JOURNAL_SCHEMA")
    if j.get("oracle")!=oracle:
        raise Blocked("JOURNAL_ORACLE_MISMATCH")
    state=j.get("state")
    if state not in JOURNAL_STATES:
        raise Blocked("UNKNOWN_JOURNAL_STATE:"+str(state))
    if allowed_states is not None and state not in set(allowed_states):
        raise Blocked("JOURNAL_STATE_NOT_ALLOWED:"+str(state))
    groups=j.get("completed_groups")
    if not isinstance(groups,list):
        raise Blocked("JOURNAL_GROUPS_NOT_LIST")
    expected_groups=math.ceil(int(c["rows"])/ref.GROUP_TICKS)
    if len(groups)>expected_groups:
        raise Blocked("JOURNAL_TOO_MANY_GROUPS")
    if require_full_groups and len(groups)!=expected_groups:
        raise Blocked("JOURNAL_GROUP_COUNT_INCOMPLETE")
    try:
        durable=int(j["durable_end"])
    except Exception as e:
        raise Blocked("JOURNAL_DURABLE_END_INVALID") from e
    if durable<0:
        raise Blocked("JOURNAL_DURABLE_END_INVALID")
    rank=JOURNAL_STATES.index(state)
    if rank>=JOURNAL_STATES.index("VALIDATED_PENDING_PUBLISH"):
        if not isinstance(j.get("container_sha256"),str) or len(j["container_sha256"])!=64:
            raise Blocked("JOURNAL_CONTAINER_SHA_MISSING")
        if int(j.get("container_bytes",-1))<=0:
            raise Blocked("JOURNAL_CONTAINER_BYTES_INVALID")
    if rank>=JOURNAL_STATES.index("COMMIT_STAGED"):
        if not isinstance(j.get("commit_sha256"),str) or len(j["commit_sha256"])!=64:
            raise Blocked("JOURNAL_COMMIT_SHA_MISSING")
        if int(j.get("commit_bytes",-1))<=0:
            raise Blocked("JOURNAL_COMMIT_BYTES_INVALID")
    if rank>=JOURNAL_STATES.index("MANIFEST_PUBLISHED"):
        if not isinstance(j.get("manifest_record_sha256"),str) or len(j["manifest_record_sha256"])!=64:
            raise Blocked("JOURNAL_MANIFEST_RECORD_SHA_MISSING")
    return state,groups,durable

def journal_record_hash(record)->str:
    return sha256_bytes(stable_json(record))


def validate_completed_groups(partial,c,j,zstd,oracle=None,allowed_states=("BUILDING",),require_full_groups=False):
    if oracle is None:
        oracle=j.get("oracle")
    state,serialized,durable=validate_journal_structure(
        j,c,oracle,allowed_states=allowed_states,require_full_groups=require_full_groups
    )
    base=validate_partial_prefix(partial,c)
    st=strict_regular_file(partial)
    if durable<base or st.st_size<durable:
        raise Blocked("PARTIAL_SHORTER_THAN_JOURNAL")
    groups=[deserialize_group(x) for x in serialized]
    expected_end=base
    expected_row=0
    expected_src=int(c["first_offset"])
    day_end=int(c["block_end_offset"])
    for gi,g in enumerate(groups):
        if g["group_no"]!=gi or g["row_start"]!=expected_row or g["source_first"]!=expected_src:
            raise Blocked("JOURNAL_GROUP_CONTINUITY_FAIL")
        if g["row_count"]<=0 or g["row_count"]>ref.GROUP_TICKS:
            raise Blocked("JOURNAL_BAD_GROUP_ROW_COUNT")
        if gi<len(groups)-1 and g["row_count"]!=ref.GROUP_TICKS:
            raise Blocked("JOURNAL_NONFINAL_SHORT_GROUP")
        if g["source_end"]<=g["source_first"] or g["source_end"]>day_end:
            raise Blocked("JOURNAL_SOURCE_RANGE_INVALID")
        if g["offset_seconds"]!=int(c["offset_seconds_first"]):
            raise Blocked("JOURNAL_OFFSET_SECONDS_MISMATCH")
        names=[s["name"] for s in g["sections"]]
        if tuple(names)!=tuple(ref.SECTION_NAMES):
            raise Blocked("JOURNAL_SECTION_ORDER_MISMATCH")
        for s in g["sections"]:
            if s["payload_offset"]!=expected_end:
                raise Blocked("JOURNAL_PAYLOAD_CONTINUITY_FAIL")
            if s["raw_len"]<0 or s["stored_len"]<0:
                raise Blocked("JOURNAL_SECTION_LENGTH_INVALID")
            expected_end+=s["stored_len"]
        expected_row+=g["row_count"]
        expected_src=g["source_end"]
    if expected_end!=durable:
        raise Blocked("JOURNAL_DURABLE_END_MISMATCH")
    if require_full_groups:
        if expected_row!=int(c["rows"]) or expected_src!=day_end:
            raise Blocked("JOURNAL_FULL_COVERAGE_MISMATCH")
    parsed=parsed_from_journal(c,j)
    for gi in range(len(groups)):
        ref.decode_group(partial,parsed,gi,zstd)
    return expected_row,expected_src,durable


def truncate_to_durable(partial:Path,durable:int):
    with secure_open_existing(partial,"r+b") as f:
        f.truncate(durable);f.flush();os.fsync(f.fileno())

def build_index_from_groups(groups):
    index=bytearray()
    for g in groups:
        index+=struct.pack(
            ref.GROUP_BASE_FMT,g["group_no"],g["row_start"],g["row_count"],
            g["source_first"],g["source_end"],g["offset_seconds"],
            1 if g["alias"] else 0,g["group_semantic_sha"],g["group_offset_sha"]
        )
        for s in g["sections"]:
            index+=struct.pack(
                ref.SECTION_FMT,s["name"].encode("ascii").ljust(8,b"\0"),
                s["payload_offset"],s["raw_len"],s["stored_len"],s["raw_sha"]
            )
    return bytes(index)

class FaultInjector:
    def __init__(self,name:str|None):
        self.name=name or ""
    def hit(self,point:str):
        if self.name==point:
            raise OSError(errno.ENOSPC if "ENOSPC" in point else errno.EIO,
                          "TICKSTORE_FAULT_INJECTION:"+point)


def write_group_payload(partial:Path,g,fault:FaultInjector):
    with secure_open_existing(partial,"r+b") as f:
        f.seek(0,os.SEEK_END)
        for i,s in enumerate(g["sections"]):
            if f.tell()!=s["payload_offset"]: raise Blocked("PAYLOAD_WRITE_OFFSET_MISMATCH")
            if s["stored_len"]:
                f.write(s["stored"])
            fault.hit(f"GROUP_{g['group_no']}_SECTION_{i}_ENOSPC")
        f.flush();os.fsync(f.fileno())


def build_or_resume_day(src_guard:PinnedSource,c,oracle,partial:Path,journal:Path,zstd,fault:FaultInjector):
    p_exists=strict_lstat(partial,allow_missing=True) is not None
    j_exists=strict_lstat(journal,allow_missing=True) is not None
    if p_exists!=j_exists: raise Blocked("PARTIAL_JOURNAL_PAIR_MISMATCH")
    if not p_exists:
        j=init_partial(partial,journal,c,oracle)
        row_start=0;source_cursor=int(c["first_offset"]);durable=int(j["durable_end"])
    else:
        j=read_json_strict(journal)
        row_start,source_cursor,durable=validate_completed_groups(
            partial,c,j,zstd,oracle=oracle,allowed_states=("BUILDING",),require_full_groups=False
        )
        if strict_regular_file(partial).st_size!=durable:
            truncate_to_durable(partial,durable)

    midnight=ref.midnight_epoch_from_datekey(int(c["date_key"]))
    expected_rows=int(c["rows"]);day_end=int(c["block_end_offset"])
    group_count=math.ceil(expected_rows/ref.GROUP_TICKS)
    t0=time.perf_counter()

    src_guard.verify_path_binding()
    sf=src_guard
    sf.seek(source_cursor)
    while row_start<expected_rows:
        gi=len(j["completed_groups"])
        if gi>=group_count: raise Blocked("TOO_MANY_GROUPS")
        gb=ref.GroupBuilder(int(c["date_key"]),gi,row_start)
        target=min(ref.GROUP_TICKS,expected_rows-row_start)
        for _ in range(target):
            line_start=sf.tell()
            raw=sf.readline()
            line_end=sf.tell()
            if not raw: raise Blocked("SOURCE_EOF_DURING_GROUP")
            if line_end>day_end: raise Blocked("SOURCE_LINE_CROSSES_DAY")
            logical=raw[:-1] if raw.endswith(b"\n") else raw
            if logical.endswith(b"\r"): logical=logical[:-1]
            row=ref.parse_row(logical,int(c["date_key"]),midnight)
            gb.add(row,line_start,line_end)
        g=gb.finalize(zstd)
        for s in g["sections"]:
            s["payload_offset"]=durable
            durable+=s["stored_len"]
        fault.hit(f"BEFORE_GROUP_{gi}_PAYLOAD")
        write_group_payload(partial,g,fault)
        fault.hit(f"AFTER_GROUP_{gi}_PAYLOAD_BEFORE_JOURNAL")
        j["completed_groups"].append(serialize_group(g))
        j["durable_end"]=durable
        atomic_journal(journal,j)
        fault.hit(f"AFTER_GROUP_{gi}_JOURNAL")
        row_start+=g["row_count"]
        source_cursor=g["source_end"]
        elapsed=max(time.perf_counter()-t0,1e-9)
        rate=row_start/elapsed
        remain=expected_rows-row_start
        eta=remain/rate if rate>0 else 0
        print(f"TICKSTORE_BUILD DATE={c['date_key']} GROUP={gi+1}/{group_count} "
              f"ROWS={row_start}/{expected_rows} ETA={ref.fmt_eta(eta)}",flush=True)

    if source_cursor!=day_end: raise Blocked("SOURCE_DAY_END_NOT_EXACT")
    if row_start!=expected_rows: raise Blocked("SOURCE_ROW_COUNT_NOT_EXACT")
    src_guard.verify_path_binding()
    return j

def finalize_partial_container(partial:Path,journal:Path,c,oracle,zstd):
    j=read_json_strict(journal)
    # Every finalization path, including index-crash recovery, must first prove all
    # durable journaled payload groups and their exact boundary.
    _,_,durable=validate_completed_groups(
        partial,c,j,zstd,oracle=oracle,allowed_states=("BUILDING",),require_full_groups=True
    )
    st=strict_regular_file(partial)
    if st.st_size>durable:
        truncate_to_durable(partial,durable)
    groups=[deserialize_group(x) for x in j["completed_groups"]]
    group_count,header,index_len,index_offset,index_hash_offset,_=partial_layout(c)
    if len(groups)!=group_count: raise Blocked("GROUP_COUNT_INCOMPLETE")
    index=build_index_from_groups(groups)
    if len(index)!=index_len: raise Blocked("INDEX_LENGTH_MISMATCH")
    with secure_open_existing(partial,"r+b") as f:
        f.seek(index_offset);f.write(index)
        f.seek(index_hash_offset);f.write(ref.sha256_bytes(index))
        f.flush();os.fsync(f.fileno())
    parsed=ref.parse_container(partial,c)
    ref.decode_full(partial,c,zstd)
    parsed_groups=[serialize_group(g) for g in parsed["groups"]]
    if parsed_groups!=j["completed_groups"]:
        raise Blocked("FINAL_INDEX_JOURNAL_GROUP_MISMATCH")
    cont_sha=sha256_file(partial)
    j["state"]="VALIDATED_PENDING_PUBLISH"
    j["container_sha256"]=cont_sha
    j["container_bytes"]=strict_regular_file(partial).st_size
    atomic_journal(journal,j)
    return j

def manifest_path(dest_root:Path)->Path:
    return dest_root/"TICKSTORE_GLOBAL_MANIFEST.json"

def load_manifest(dest_root:Path):
    p=manifest_path(dest_root)
    if strict_lstat(p,allow_missing=True) is None:
        return {"schema":MANIFEST_SCHEMA,"records":{}}
    m=read_json_strict(p)
    if m.get("schema")!=MANIFEST_SCHEMA or not isinstance(m.get("records"),dict):
        raise Blocked("GLOBAL_MANIFEST_INVALID")
    return m

def manifest_record(oracle,container_sha,container_bytes,commit_sha):
    return {
        "date_key":oracle["date_key"],"month_id":oracle["month_id"],
        "source_identity":oracle["source_identity"],
        "ledger_zip_sha256":oracle["ledger_zip_sha256"],
        "day_contract_sha256":oracle["day_contract_sha256"],
        "code_revision":oracle["code_revision"],
        "format_id":FORMAT_ID,"codec_id":CODEC_ID,"row_group_ticks":ROW_GROUP_TICKS,
        "semantic_sha256":oracle["semantic_sha256"],"offset_sha256":oracle["offset_sha256"],
        "container_sha256":container_sha,"container_bytes":container_bytes,
        "commit_sha256":commit_sha,
    }

def update_manifest(dest_root:Path,record):
    m=load_manifest(dest_root)
    key=record["date_key"]
    old=m["records"].get(key)
    if old is not None and old!=record:
        raise Blocked("GLOBAL_MANIFEST_RECORD_CONFLICT:"+key)
    m["records"][key]=record
    m["updated_unix_ns"]=time.time_ns()
    atomic_write_json(manifest_path(dest_root),m)

def expected_commit(oracle,container_sha,container_bytes):
    return {
        "schema":COMMIT_SCHEMA,
        "oracle":oracle,
        "container_sha256":container_sha,
        "container_bytes":container_bytes,
        "semantic_sha256":oracle["semantic_sha256"],
        "offset_sha256":oracle["offset_sha256"],
        "published_unix_ns":None,
    }

def validate_commit_without_manifest(commit_path:Path,oracle,container:Path,zstd,c):
    commit=read_json_strict(commit_path)
    if commit.get("schema")!=COMMIT_SCHEMA: raise Blocked("COMMIT_SCHEMA")
    if commit.get("oracle")!=oracle: raise Blocked("COMMIT_ORACLE_MISMATCH")
    actual=sha256_file(container)
    if commit.get("container_sha256")!=actual: raise Blocked("COMMIT_CONTAINER_SHA_MISMATCH")
    if int(commit.get("container_bytes",-1))!=strict_regular_file(container).st_size:
        raise Blocked("COMMIT_CONTAINER_SIZE_MISMATCH")
    if commit.get("semantic_sha256")!=oracle["semantic_sha256"]: raise Blocked("COMMIT_SEMANTIC_MISMATCH")
    if commit.get("offset_sha256")!=oracle["offset_sha256"]: raise Blocked("COMMIT_OFFSET_MISMATCH")
    ref.parse_container(container,c);ref.decode_full(container,c,zstd)
    return commit,actual,sha256_file(commit_path)

def commit_matches(commit_path:Path,oracle,container:Path,manifest_rec,zstd,c):
    commit,actual,commit_sha=validate_commit_without_manifest(commit_path,oracle,container,zstd,c)
    if manifest_rec is None: raise Blocked("GLOBAL_MANIFEST_RECORD_MISSING")
    candidate=manifest_record(
        oracle,actual,strict_regular_file(container).st_size,commit_sha
    )
    if manifest_rec!=candidate:
        # identify first field for auditability
        keys=sorted(set(candidate)|set(manifest_rec))
        for k in keys:
            if candidate.get(k)!=manifest_rec.get(k):
                raise Blocked("GLOBAL_MANIFEST_MISMATCH:"+k)
        raise Blocked("GLOBAL_MANIFEST_MISMATCH")
    return "REUSE"

def cleanup_atomic_shadow(path:Path):
    tmp=path.with_suffix(path.suffix+".partial")
    st=strict_lstat(tmp,allow_missing=True)
    if st is None:return
    # A final authoritative file wins over its abandoned atomic shadow.
    if strict_lstat(path,allow_missing=True) is None:
        raise Blocked("ATOMIC_SHADOW_WITHOUT_FINAL:"+str(tmp))
    strict_regular_file(path); strict_regular_file(tmp)
    try: safe_unlink_regular(tmp)
    except Blocked as e: raise Blocked("ATOMIC_SHADOW_CLEANUP_FAIL:"+str(tmp)) from e


def validate_journal_final_transaction(
    j,c,oracle,container:Path,commit_path:Path|None,zstd,
    allowed_states,manifest_rec=None
):
    state,groups,durable=validate_journal_structure(
        j,c,oracle,allowed_states=allowed_states,require_full_groups=True
    )
    strict_regular_file(container)
    parsed=ref.parse_container(container,c)
    ref.decode_full(container,c,zstd)
    if [serialize_group(g) for g in parsed["groups"]]!=groups:
        raise Blocked("JOURNAL_FINAL_GROUPS_MISMATCH")
    csha=sha256_file(container);cbytes=strict_regular_file(container).st_size
    if csha!=j.get("container_sha256") or cbytes!=int(j.get("container_bytes",-1)):
        raise Blocked("JOURNAL_FINAL_CONTAINER_BINDING_MISMATCH")
    if durable!=cbytes:
        raise Blocked("JOURNAL_FINAL_DURABLE_END_MISMATCH")
    if JOURNAL_STATES.index(state)>=JOURNAL_STATES.index("COMMIT_STAGED"):
        if commit_path is None:
            raise Blocked("JOURNAL_EXPECTS_COMMIT_OBJECT")
        strict_regular_file(commit_path)
        actual_sha=sha256_file(commit_path);actual_bytes=strict_regular_file(commit_path).st_size
        if actual_sha!=j.get("commit_sha256") or actual_bytes!=int(j.get("commit_bytes",-1)):
            raise Blocked("JOURNAL_COMMIT_BINDING_MISMATCH")
        validate_commit_without_manifest(commit_path,oracle,container,zstd,c)
    if manifest_rec is not None:
        expected=manifest_record(oracle,csha,cbytes,sha256_file(commit_path))
        if manifest_rec!=expected:
            raise Blocked("JOURNAL_MANIFEST_RECORD_MISMATCH")
        if state=="MANIFEST_PUBLISHED":
            if j.get("manifest_record_sha256")!=journal_record_hash(manifest_rec):
                raise Blocked("JOURNAL_MANIFEST_RECORD_HASH_MISMATCH")
    return state

def advance_journal(journal:Path,j,new_state:str,**fields):
    if new_state not in JOURNAL_STATES:
        raise Blocked("BAD_JOURNAL_TRANSITION_TARGET")
    old=j.get("state")
    if old not in JOURNAL_STATES:
        raise Blocked("BAD_JOURNAL_TRANSITION_SOURCE")
    if JOURNAL_STATES.index(new_state)<JOURNAL_STATES.index(old):
        raise Blocked("JOURNAL_STATE_REGRESSION")
    j=dict(j);j.update(fields);j["state"]=new_state
    atomic_journal(journal,j)
    return j

def repair_manifest_from_proven_transaction(dest_root:Path,oracle,container:Path,commit_path:Path,journal:Path,zstd,c):
    j=read_json_strict(journal)
    validate_journal_final_transaction(
        j,c,oracle,container,commit_path,zstd,
        allowed_states=("COMMIT_STAGED","CONTAINER_PUBLISHED","COMMIT_PUBLISHED","MANIFEST_PUBLISHED"),
        manifest_rec=None
    )
    commit,actual,commit_sha=validate_commit_without_manifest(commit_path,oracle,container,zstd,c)
    rec=manifest_record(oracle,actual,strict_regular_file(container).st_size,commit_sha)
    update_manifest(dest_root,rec)
    j=advance_journal(journal,j,"MANIFEST_PUBLISHED",manifest_record_sha256=journal_record_hash(rec))
    return commit_matches(commit_path,oracle,container,load_manifest(dest_root)["records"].get(c["date_key"]),zstd,c),j

def acquire_lock(dest_root:Path):
    lock=dest_root/"TICKSTORE_WRITER.lock"
    try:
        fd=secure_create_new_fd(lock)
    except Blocked as e:
        if "SECURE_CREATE_EXISTS:" in str(e):
            raise Blocked("WRITER_LOCK_EXISTS:"+str(lock)) from e
        raise Blocked("WRITER_LOCK_CREATE_FAIL:"+str(lock)) from e
    payload=stable_json({"pid":os.getpid(),"created_unix_ns":time.time_ns()})+b"\n"
    with os.fdopen(fd,"wb") as f:
        f.write(payload);f.flush();os.fsync(f.fileno())
    return lock

def release_lock(lock:Path):
    if strict_lstat(lock,allow_missing=True) is None:
        raise Blocked("WRITER_LOCK_DISAPPEARED")
    try:
        safe_unlink_regular(lock)
    except Blocked as e:
        raise Blocked("WRITER_LOCK_REMOVE_FAIL") from e

def free_space_gate(dest_root:Path,source_day_bytes:int):
    usage=shutil.disk_usage(dest_root)
    reserve=max(source_day_bytes*2,2*1024**3)+512*1024**2
    if usage.free<reserve:
        raise Blocked(f"INSUFFICIENT_FREE_SPACE:{usage.free}:{reserve}")
    return {"free_bytes":usage.free,"required_reserve_bytes":reserve}

def paths_for_day(dest_root:Path,c):
    md=dest_root/"WIN@N"/c["month_id"]
    strict_directory(dest_root,create=True)
    strict_directory(dest_root/"WIN@N",create=True)
    strict_directory(md,create=True)
    stem=c["date_key"]
    return {
        "dir":md,
        "container":md/(stem+".pts2g"),
        "partial":md/(stem+".pts2g.partial"),
        "journal":md/(stem+".journal.json"),
        "journal_atomic":md/(stem+".journal.json.partial"),
        "commit":md/(stem+".commit.json"),
        "commit_partial":md/(stem+".commit.json.partial"),
        "commit_stage":md/(stem+".commit.json.partial.stage"),
    }


def transaction_state(pp,dest_root:Path):
    mp=manifest_path(dest_root);ma=mp.with_suffix(mp.suffix+".partial")
    paths={k:v for k,v in pp.items() if k!="dir"}
    paths["manifest"]=mp;paths["manifest_atomic"]=ma
    state={}
    for k,p in paths.items():
        st=strict_lstat(p,allow_missing=True)
        state[k]=st is not None
        if st is not None:
            _reject_link_or_reparse(p,st)
            if not stat.S_ISREG(st.st_mode):
                raise Blocked("TRANSACTION_PATH_NOT_REGULAR:"+k)
    return state

def discard_uncommitted(path:Path,label:str):
    strict_regular_file(path)
    safe_unlink_regular(path)

def validate_validated_partial(partial:Path,journal:Path,c,oracle,zstd,allowed_states):
    j=read_json_strict(journal)
    validate_completed_groups(
        partial,c,j,zstd,oracle=oracle,allowed_states=allowed_states,require_full_groups=True
    )
    parsed=ref.parse_container(partial,c);ref.decode_full(partial,c,zstd)
    if [serialize_group(g) for g in parsed["groups"]]!=j["completed_groups"]:
        raise Blocked("VALIDATED_PARTIAL_GROUPS_MISMATCH")
    actual=sha256_file(partial);size=strict_regular_file(partial).st_size
    if actual!=j.get("container_sha256") or size!=int(j.get("container_bytes",-1)):
        raise Blocked("VALIDATED_PARTIAL_BINDING_MISMATCH")
    return j

def validate_commit_object_against_journal(commit_path:Path,j,oracle,container:Path,zstd,c):
    strict_regular_file(commit_path)
    if sha256_file(commit_path)!=j.get("commit_sha256"):
        raise Blocked("JOURNAL_COMMIT_SHA_MISMATCH")
    if strict_regular_file(commit_path).st_size!=int(j.get("commit_bytes",-1)):
        raise Blocked("JOURNAL_COMMIT_SIZE_MISMATCH")
    validate_commit_without_manifest(commit_path,oracle,container,zstd,c)
    return True

def stage_commit_for_validated_partial(pp,j,c,oracle,zstd,source_guard:PinnedSource):
    # The source must still be exactly the same open object/bytes immediately before
    # transaction authority expands beyond the validated partial.
    source_guard.verify_full()
    if strict_lstat(pp["commit_partial"],allow_missing=True) is not None:
        raise Blocked("COMMIT_PARTIAL_PREEXISTS_WITHOUT_JOURNAL_BINDING")
    commit=expected_commit(oracle,j["container_sha256"],j["container_bytes"])
    commit["published_unix_ns"]=time.time_ns()
    write_transaction_json(pp["commit_partial"],commit)
    csha=sha256_file(pp["commit_partial"]);cbytes=strict_regular_file(pp["commit_partial"]).st_size
    j=advance_journal(pp["journal"],j,"COMMIT_STAGED",commit_sha256=csha,commit_bytes=cbytes)
    return j

def publish_from_staged(pp,j,c,oracle,dest_root,zstd,source_guard:PinnedSource,fault):
    # Partial container + durable commit.partial + COMMIT_STAGED journal.
    validate_validated_partial(
        pp["partial"],pp["journal"],c,oracle,zstd,allowed_states=("COMMIT_STAGED",)
    )
    validate_commit_object_against_journal(pp["commit_partial"],j,oracle,pp["partial"],zstd,c)
    source_guard.verify_full()
    secure_replace(pp["partial"],pp["container"])
    j=advance_journal(pp["journal"],j,"CONTAINER_PUBLISHED")
    fault.hit("AFTER_CONTAINER_RENAME")
    source_guard.verify_full()
    secure_replace(pp["commit_partial"],pp["commit"])
    j=advance_journal(pp["journal"],j,"COMMIT_PUBLISHED")
    fault.hit("AFTER_COMMIT_RENAME_BEFORE_MANIFEST")
    source_guard.verify_full()
    # Validate the final pair against the same journal before creating external authority.
    validate_journal_final_transaction(
        j,c,oracle,pp["container"],pp["commit"],zstd,
        allowed_states=("COMMIT_PUBLISHED",),manifest_rec=None
    )
    commit,actual,commit_sha=validate_commit_without_manifest(pp["commit"],oracle,pp["container"],zstd,c)
    rec=manifest_record(oracle,actual,strict_regular_file(pp["container"]).st_size,commit_sha)
    update_manifest(dest_root,rec)
    j=advance_journal(
        pp["journal"],j,"MANIFEST_PUBLISHED",manifest_record_sha256=journal_record_hash(rec)
    )
    fault.hit("AFTER_MANIFEST_BEFORE_JOURNAL_CLEANUP")
    source_guard.verify_full()
    rec2=load_manifest(dest_root)["records"].get(c["date_key"])
    validate_journal_final_transaction(
        j,c,oracle,pp["container"],pp["commit"],zstd,
        allowed_states=("MANIFEST_PUBLISHED",),manifest_rec=rec2
    )
    commit_matches(pp["commit"],oracle,pp["container"],rec2,zstd,c)
    safe_unlink_regular(pp["journal"])
    return "BUILT_OR_RESUMED"

def recover_container_commit_partial(pp,j,c,oracle,dest_root,zstd,source_guard:PinnedSource,fault):
    # Crash after container rename but before commit rename. Journal must already bind
    # both container and commit bytes from COMMIT_STAGED.
    validate_journal_final_transaction(
        j,c,oracle,pp["container"],pp["commit_partial"],zstd,
        allowed_states=("COMMIT_STAGED","CONTAINER_PUBLISHED"),manifest_rec=None
    )
    source_guard.verify_full()
    secure_replace(pp["commit_partial"],pp["commit"])
    j=advance_journal(pp["journal"],j,"COMMIT_PUBLISHED")
    fault.hit("AFTER_COMMIT_RENAME_BEFORE_MANIFEST")
    source_guard.verify_full()
    commit,actual,commit_sha=validate_commit_without_manifest(pp["commit"],oracle,pp["container"],zstd,c)
    rec=manifest_record(oracle,actual,strict_regular_file(pp["container"]).st_size,commit_sha)
    update_manifest(dest_root,rec)
    j=advance_journal(pp["journal"],j,"MANIFEST_PUBLISHED",manifest_record_sha256=journal_record_hash(rec))
    fault.hit("AFTER_MANIFEST_BEFORE_JOURNAL_CLEANUP")
    source_guard.verify_full()
    rec2=load_manifest(dest_root)["records"].get(c["date_key"])
    validate_journal_final_transaction(
        j,c,oracle,pp["container"],pp["commit"],zstd,
        allowed_states=("MANIFEST_PUBLISHED",),manifest_rec=rec2
    )
    commit_matches(pp["commit"],oracle,pp["container"],rec2,zstd,c)
    safe_unlink_regular(pp["journal"])
    return "RESUMED_PUBLICATION"

def reconcile_final_pair(pp,c,oracle,dest_root,zstd,source_guard:PinnedSource,state):
    if state["partial"] or state["commit_partial"] or state["commit_stage"]:
        raise Blocked("CONFLICTING_FINAL_AND_PARTIAL_STATE")
    m=load_manifest(dest_root);rec=m["records"].get(c["date_key"])
    if state["journal_atomic"] and not state["journal"]:
        raise Blocked("JOURNAL_ATOMIC_WITHOUT_AUTHORITATIVE_JOURNAL")
    if state["manifest_atomic"] and not state["journal"]:
        raise Blocked("MANIFEST_ATOMIC_WITHOUT_TRANSACTION_JOURNAL")
    if state["journal"]:
        j=read_json_strict(pp["journal"])
        allowed=("COMMIT_STAGED","CONTAINER_PUBLISHED","COMMIT_PUBLISHED","MANIFEST_PUBLISHED")
        validate_journal_final_transaction(
            j,c,oracle,pp["container"],pp["commit"],zstd,
            allowed_states=allowed,manifest_rec=rec
        )
        # Shadows are discarded only AFTER the authoritative final state is classified
        # and journal/final pair have been proven consistent.
        if state["journal_atomic"]:
            discard_uncommitted(pp["journal_atomic"],"journal_atomic")
        if state["manifest_atomic"]:
            discard_uncommitted(manifest_path(dest_root).with_suffix(manifest_path(dest_root).suffix+".partial"),"manifest_atomic")
    if rec is None:
        if not state["journal"]:
            raise Blocked("GLOBAL_MANIFEST_RECORD_MISSING_WITHOUT_TRANSACTION_JOURNAL")
        result,j2=repair_manifest_from_proven_transaction(
            dest_root,oracle,pp["container"],pp["commit"],pp["journal"],zstd,c
        )
        source_guard.verify_full()
        rec=load_manifest(dest_root)["records"].get(c["date_key"])
        validate_journal_final_transaction(
            j2,c,oracle,pp["container"],pp["commit"],zstd,
            allowed_states=("MANIFEST_PUBLISHED",),manifest_rec=rec
        )
        safe_unlink_regular(pp["journal"])
        return "RESUMED_MANIFEST"
    source_guard.verify_full()
    result=commit_matches(pp["commit"],oracle,pp["container"],rec,zstd,c)
    if state["journal"]:
        safe_unlink_regular(pp["journal"])
    return "REUSED"


def reconcile_or_build(source_guard:PinnedSource,c,oracle,dest_root:Path,zstd,fault):
    pp=paths_for_day(dest_root,c)
    state=transaction_state(pp,dest_root)

    # No cleanup is allowed before the whole state is classified.
    if state["container"] and state["commit"]:
        return reconcile_final_pair(pp,c,oracle,dest_root,zstd,source_guard,state)

    # Final container + durable commit.partial is recoverable ONLY with full journal proof.
    if state["container"] and not state["commit"] and state["commit_partial"]:
        if state["partial"] or not state["journal"]:
            raise Blocked("CONTAINER_COMMIT_PARTIAL_STATE_UNPROVEN")
        if state["commit_stage"]:
            raise Blocked("COMMIT_STAGE_CONFLICT")
        j=read_json_strict(pp["journal"])
        if state["journal_atomic"]:
            # Main journal remains authority; validate before discarding its uncommitted shadow.
            validate_journal_structure(j,c,oracle,allowed_states=("COMMIT_STAGED","CONTAINER_PUBLISHED"),require_full_groups=True)
            discard_uncommitted(pp["journal_atomic"],"journal_atomic")
        if state["manifest_atomic"]:
            # No manifest should be authoritative yet; discard only after journal proof below.
            validate_journal_final_transaction(
                j,c,oracle,pp["container"],pp["commit_partial"],zstd,
                allowed_states=("COMMIT_STAGED","CONTAINER_PUBLISHED"),manifest_rec=None
            )
            discard_uncommitted(manifest_path(dest_root).with_suffix(manifest_path(dest_root).suffix+".partial"),"manifest_atomic")
        return recover_container_commit_partial(
            pp,j,c,oracle,dest_root,zstd,source_guard,fault
        )

    if state["container"] and not state["commit"]:
        raise Blocked("ORPHAN_CONTAINER_REBUILD_REQUIRED")
    if state["commit"] and not state["container"]:
        raise Blocked("COMMIT_WITHOUT_CONTAINER_REBUILD_REQUIRED")
    if state["commit_partial"] and not state["container"] and not state["partial"]:
        raise Blocked("COMMIT_PARTIAL_WITHOUT_CONTAINER_STATE")

    # Classified zero-authority states: safe to discard only because no final pair exists
    # and no durable partial+journal pair exists. This occurs AFTER complete state snapshot.
    if state["partial"] and not state["journal"]:
        if state["commit_partial"] or state["commit_stage"]:
            raise Blocked("PARTIAL_WITH_COMMIT_SIDE_CAR_NO_JOURNAL")
        if state["journal_atomic"]:
            discard_uncommitted(pp["journal_atomic"],"journal_atomic")
            state["journal_atomic"]=False
        discard_uncommitted(pp["partial"],"partial_without_journal")
        state["partial"]=False
    elif state["journal"] and not state["partial"]:
        if state["commit_partial"] or state["commit_stage"]:
            raise Blocked("JOURNAL_WITH_COMMIT_SIDE_CAR_NO_PARTIAL")
        # A journal without payload has zero reusable progress. Validate it is a regular
        # JSON object before discarding so metadata errors cannot masquerade as absence.
        read_json_strict(pp["journal"])
        if state["journal_atomic"]:
            discard_uncommitted(pp["journal_atomic"],"journal_atomic")
            state["journal_atomic"]=False
        safe_unlink_regular(pp["journal"]);state["journal"]=False
    elif state["journal_atomic"] and not state["journal"] and not state["partial"]:
        discard_uncommitted(pp["journal_atomic"],"journal_atomic_only")
        state["journal_atomic"]=False

    if state["manifest_atomic"] and not state["journal"]:
        # Without a live day transaction, a global-manifest shadow is ambiguous. Never
        # discard it merely to make the current state look clean.
        raise Blocked("MANIFEST_ATOMIC_WITHOUT_TRANSACTION_JOURNAL")

    # Fresh day.
    if not state["partial"] and not state["journal"]:
        if state["commit_stage"]:
            raise Blocked("COMMIT_STAGE_WITHOUT_TRANSACTION")
        free_space_gate(dest_root,int(c["source_day_bytes"]))
        build_or_resume_day(source_guard,c,oracle,pp["partial"],pp["journal"],zstd,fault)
        fault.hit("BEFORE_INDEX_FINALIZE")
        j=finalize_partial_container(pp["partial"],pp["journal"],c,oracle,zstd)
        fault.hit("AFTER_VALIDATE_BEFORE_COMMIT_PARTIAL")
        source_guard.verify_full()
        j=stage_commit_for_validated_partial(pp,j,c,oracle,zstd,source_guard)
        fault.hit("AFTER_COMMIT_PARTIAL")
        result=publish_from_staged(pp,j,c,oracle,dest_root,zstd,source_guard,fault)
        return "BUILT"

    # Partial + authoritative journal transaction.
    j=read_json_strict(pp["journal"])
    state_name,_,_=validate_journal_structure(j,c,oracle,allowed_states=JOURNAL_STATES,require_full_groups=False)

    # An atomic journal shadow is uncommitted and may be discarded only now, after the
    # main journal and all other paths were classified.
    if state["journal_atomic"]:
        discard_uncommitted(pp["journal_atomic"],"journal_atomic")
    if state["manifest_atomic"]:
        # During an unfinished day there is no valid reason to make a shadow authoritative.
        discard_uncommitted(manifest_path(dest_root).with_suffix(manifest_path(dest_root).suffix+".partial"),"manifest_atomic")

    if state_name=="BUILDING":
        if state["commit_partial"] or state["commit_stage"]:
            raise Blocked("BUILDING_WITH_COMMIT_SIDE_CAR_CONFLICT")
        expected_groups=math.ceil(int(c["rows"])/ref.GROUP_TICKS)
        # Always validate the journal/payload boundary, including the all-groups branch.
        _,_,durable=validate_completed_groups(
            pp["partial"],c,j,zstd,oracle=oracle,allowed_states=("BUILDING",),
            require_full_groups=(len(j.get("completed_groups",[]))==expected_groups)
        )
        if strict_regular_file(pp["partial"]).st_size>durable:
            truncate_to_durable(pp["partial"],durable)
        if len(j.get("completed_groups",[]))<expected_groups:
            free_space_gate(dest_root,int(c["source_day_bytes"]))
            build_or_resume_day(source_guard,c,oracle,pp["partial"],pp["journal"],zstd,fault)
        fault.hit("BEFORE_INDEX_FINALIZE")
        j=finalize_partial_container(pp["partial"],pp["journal"],c,oracle,zstd)
        fault.hit("AFTER_VALIDATE_BEFORE_COMMIT_PARTIAL")
        source_guard.verify_full()
        j=stage_commit_for_validated_partial(pp,j,c,oracle,zstd,source_guard)
        fault.hit("AFTER_COMMIT_PARTIAL")
        publish_from_staged(pp,j,c,oracle,dest_root,zstd,source_guard,fault)
        return "RESUMED"

    if state_name=="VALIDATED_PENDING_PUBLISH":
        if state["commit_stage"]:
            # Stage is explicitly non-authoritative. Validate the real journal/partial first.
            validate_validated_partial(
                pp["partial"],pp["journal"],c,oracle,zstd,allowed_states=("VALIDATED_PENDING_PUBLISH",)
            )
            discard_uncommitted(pp["commit_stage"],"commit_stage")
        if state["commit_partial"]:
            # It was not recorded by the authoritative journal; discard only after full
            # partial validation and restage deterministically.
            validate_validated_partial(
                pp["partial"],pp["journal"],c,oracle,zstd,allowed_states=("VALIDATED_PENDING_PUBLISH",)
            )
            discard_uncommitted(pp["commit_partial"],"commit_partial_unbound")
        j=validate_validated_partial(
            pp["partial"],pp["journal"],c,oracle,zstd,allowed_states=("VALIDATED_PENDING_PUBLISH",)
        )
        source_guard.verify_full()
        j=stage_commit_for_validated_partial(pp,j,c,oracle,zstd,source_guard)
        fault.hit("AFTER_COMMIT_PARTIAL")
        publish_from_staged(pp,j,c,oracle,dest_root,zstd,source_guard,fault)
        return "RESUMED"

    if state_name=="COMMIT_STAGED":
        if state["commit_stage"]:
            raise Blocked("COMMIT_STAGED_WITH_STAGE_CONFLICT")
        if not state["commit_partial"]:
            raise Blocked("COMMIT_STAGED_WITHOUT_COMMIT_PARTIAL")
        validate_validated_partial(
            pp["partial"],pp["journal"],c,oracle,zstd,allowed_states=("COMMIT_STAGED",)
        )
        validate_commit_object_against_journal(pp["commit_partial"],j,oracle,pp["partial"],zstd,c)
        publish_from_staged(pp,j,c,oracle,dest_root,zstd,source_guard,fault)
        return "RESUMED"

    # Later journal states require a final container and are impossible with partial here.
    raise Blocked("JOURNAL_STATE_PATH_CONFIGURATION_MISMATCH:"+state_name)

def select_contract(days,date_key):
    matches=[d for d in days if d["date_key"]==date_key]
    if len(matches)!=1: raise Blocked("DATE_NOT_UNIQUE_OR_NOT_FOUND:"+date_key)
    return matches[0]

def source_for(source_root:Path,c):
    p=source_root/f"WIN@N_ticks_{c['month_id']}.csv"
    strict_regular_file(p)
    return p


def run_one_day(source_root:Path,dest_root:Path,ledger_zip:Path,date_key:str,inject:str|None):
    zstd=ref.require_zstd()
    days,months,ledger_sha=load_ledgers(ledger_zip)
    c=select_contract(days,date_key)
    month=months[c["month_id"]]
    src=source_for(source_root,c)
    ids=file_ids(Path(__file__).resolve().parent)

    strict_directory(dest_root,create=True)
    result=None
    lock=None
    with PinnedSource(src,int(month["source_size"]),month["source_sha256"]) as source_guard:
        oracle=make_oracle(c,month,dict(source_guard.identity),ledger_sha,ids)
        lock=acquire_lock(dest_root)
        try:
            result=_run_day_already_locked(source_guard,c,oracle,dest_root,zstd,FaultInjector(inject))
        finally:
            release_lock(lock)
            lock=None

    # Terminal success is emitted only after source verification and lock cleanup.
    print("TICKSTORE_DAY_RESULT="+str(result))
    print("DATE_KEY="+date_key)
    print("SOURCE_MUTATION=NO")
    print("CSV_DELETION=NO")
    print("TICKSTORE_RUNNER_STATUS=PASS")
    return 0

def _run_day_already_locked(source_guard,c,oracle,dest_root,zstd,fault):
    """Caller owns the writer lock; R8 transaction/verification order is unchanged."""
    source_guard.verify_full()
    result=reconcile_or_build(source_guard,c,oracle,dest_root,zstd,fault)
    source_guard.verify_full()
    return result


def plan(ledger_zip:Path):
    days,months,zsha=load_ledgers(ledger_zip)
    total_rows=sum(int(x["rows"]) for x in days)
    total_bytes=sum(int(x["source_day_bytes"]) for x in days)
    print("TICKSTORE_PLAN=PASS")
    print(f"MONTHS={len(months)}")
    print(f"DAYS={len(days)}")
    print(f"ROWS={total_rows}")
    print(f"SOURCE_BYTES={total_bytes}")
    print(f"LEDGER_ZIP_SHA256={zsha}")
    print("FULL_HISTORY_EXECUTION_AUTHORIZED=NO")
    return 0

def require_gate(path:Path,expected:str):
    raw=secure_read_all(path)
    try:
        txt=raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError as e:
        raise Blocked("AUTHORIZATION_GATE_ENCODING") from e
    if txt!=expected: raise Blocked("AUTHORIZATION_GATE_CONTENT_MISMATCH")


def native_zstd_origin_evidence(zstd=None):
    if zstd is None:
        zstd=ref.require_zstd()
    if getattr(zstd,"__name__",None)!="compression.zstd":
        raise Blocked("WINDOWS_PILOT_ZSTD_MODULE_NAME_MISMATCH")
    spec=getattr(zstd,"__spec__",None)
    if spec is None or getattr(spec,"name",None)!="compression.zstd":
        raise Blocked("WINDOWS_PILOT_ZSTD_SPEC_MISMATCH")
    origin=getattr(spec,"origin",None) or getattr(zstd,"__file__",None)
    if not origin or str(origin) in ("built-in","frozen"):
        raise Blocked("WINDOWS_PILOT_ZSTD_ORIGIN_UNPROVEN")
    try:
        origin_path=Path(origin).resolve(strict=True)
        stdlib=Path(sysconfig.get_path("stdlib")).resolve(strict=True)
        rel=origin_path.relative_to(stdlib)
    except Exception as e:
        raise Blocked("WINDOWS_PILOT_ZSTD_NOT_FROM_STDLIB:"+str(origin)) from e
    parts=tuple(x.lower() for x in rel.parts)
    if len(parts)<3 or parts[0]!="compression" or parts[1]!="zstd" or parts[-1]!="__init__.py":
        raise Blocked("WINDOWS_PILOT_ZSTD_STDLIB_LAYOUT_MISMATCH:"+str(rel))
    return {"module":"compression.zstd","origin":str(origin_path),"stdlib_root":str(stdlib)}


def windows_volume_identity(path:Path):
    if os.name!="nt": raise Blocked("WINDOWS_VOLUME_IDENTITY_REQUIRES_WINDOWS")
    absolute=os.path.abspath(str(path))
    drive=os.path.splitdrive(absolute)[0]
    if not drive:
        raise Blocked("WINDOWS_PILOT_REQUIRES_DRIVE_LETTER_PATH:"+absolute)
    root=drive+"\\"
    k32=ctypes.WinDLL("kernel32",use_last_error=True)
    fn=k32.GetVolumeInformationW
    fn.argtypes=[ctypes.wintypes.LPCWSTR,ctypes.wintypes.LPWSTR,ctypes.wintypes.DWORD,
                 ctypes.POINTER(ctypes.wintypes.DWORD),ctypes.POINTER(ctypes.wintypes.DWORD),
                 ctypes.POINTER(ctypes.wintypes.DWORD),ctypes.wintypes.LPWSTR,ctypes.wintypes.DWORD]
    fn.restype=ctypes.wintypes.BOOL
    name=ctypes.create_unicode_buffer(261);fs=ctypes.create_unicode_buffer(261)
    serial=ctypes.wintypes.DWORD();maxcomp=ctypes.wintypes.DWORD();flags=ctypes.wintypes.DWORD()
    if not fn(root,name,len(name),ctypes.byref(serial),ctypes.byref(maxcomp),ctypes.byref(flags),fs,len(fs)):
        err=ctypes.get_last_error();raise Blocked(f"WINDOWS_VOLUME_INFO_FAIL:{root}:winerror={err}")
    return {"root":root.upper(),"serial":f"{int(serial.value):08X}","filesystem":fs.value.upper()}


def require_windows_pilot_runtime():
    if os.name!="nt":
        raise Blocked("WINDOWS_PILOT_REQUIRES_WINDOWS")
    if sys.version_info < (3,14):
        raise Blocked(f"WINDOWS_PILOT_REQUIRES_PYTHON_3_14:{sys.version.split()[0]}")
    zstd=ref.require_zstd()
    native_zstd_origin_evidence(zstd)
    return zstd


def _norm_binding_path(path:Path)->str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def validate_windows_preflight_report(path:Path,ledger_zip:Path,source_root:Path,dest_root:Path,scratch_root:Path,pilot_date:str):
    report=read_json_strict(path)
    if report.get("schema")!=WINDOWS_PREFLIGHT_SCHEMA:
        raise Blocked("WINDOWS_PREFLIGHT_SCHEMA_MISMATCH")
    if report.get("status")!="PASS":
        raise Blocked("WINDOWS_PREFLIGHT_NOT_PASS")
    if str(report.get("pilot_date",""))!=str(pilot_date):
        raise Blocked("WINDOWS_PREFLIGHT_PILOT_DATE_MISMATCH")
    ids=file_ids(Path(__file__).resolve().parent)
    required={
        "runner_sha256":ids["runner_sha256"],
        "reference_sha256":ids["reference_sha256"],
        "spec_sha256":ids["spec_sha256"],
        "preflight_sha256":ids["preflight_sha256"],
        "ledger_sha256":sha256_file(ledger_zip),
    }
    for k,v in required.items():
        if str(report.get(k,"")).upper()!=str(v).upper():
            raise Blocked("WINDOWS_PREFLIGHT_IDENTITY_MISMATCH:"+k)
    if report.get("windows_runtime") is not True:
        raise Blocked("WINDOWS_PREFLIGHT_WINDOWS_RUNTIME_NOT_PROVED")
    if report.get("python_3_14_or_newer") is not True:
        raise Blocked("WINDOWS_PREFLIGHT_PYTHON_NOT_PROVED")
    if report.get("native_compression_zstd") is not True:
        raise Blocked("WINDOWS_PREFLIGHT_ZSTD_NOT_PROVED")
    if report.get("core_filesystem_tests")!="PASS":
        raise Blocked("WINDOWS_PREFLIGHT_FILESYSTEM_NOT_PASS")
    zproof=native_zstd_origin_evidence()
    if report.get("zstd_module")!=zproof["module"] or _norm_binding_path(Path(report.get("zstd_origin","")))!=_norm_binding_path(Path(zproof["origin"])):
        raise Blocked("WINDOWS_PREFLIGHT_ZSTD_ORIGIN_MISMATCH")
    roots={"source_root":Path(source_root),"dest_root":Path(dest_root),"scratch_root":Path(scratch_root)}
    volumes={}
    for key,pth in roots.items():
        if str(report.get(key,""))!=_norm_binding_path(pth):
            raise Blocked("WINDOWS_PREFLIGHT_PATH_BINDING_MISMATCH:"+key)
        volumes[key]=windows_volume_identity(pth)
        repvol=report.get(key.replace("_root","_volume"))
        if repvol!=volumes[key]:
            raise Blocked("WINDOWS_PREFLIGHT_VOLUME_BINDING_MISMATCH:"+key)
    serials={v["serial"] for v in volumes.values()}
    roots={v["root"] for v in volumes.values()}
    if len(serials)!=1 or len(roots)!=1:
        raise Blocked("WINDOWS_PREFLIGHT_SOURCE_DEST_SCRATCH_VOLUME_MISMATCH")
    results=report.get("results")
    if not isinstance(results,dict): raise Blocked("WINDOWS_PREFLIGHT_RESULTS_MISSING")
    for key in REQUIRED_PREFLIGHT_PASS_RESULTS:
        if results.get(key)!="PASS": raise Blocked("WINDOWS_PREFLIGHT_REQUIRED_RESULT_NOT_PASS:"+key)
    symlink=str(results.get("symlink",""))
    if symlink!="PASS" and not symlink.startswith("NOT_PERMITTED_WINERROR_"):
        raise Blocked("WINDOWS_PREFLIGHT_SYMLINK_RESULT_INVALID")
    a83=str(results.get("alias_8dot3",""))
    if a83 not in ("PASS","NOT_AVAILABLE_ON_VOLUME"):
        raise Blocked("WINDOWS_PREFLIGHT_8DOT3_RESULT_INVALID")
    return report


def require_pilot_owner_gate(path:Path,preflight_path:Path,ledger_zip:Path,pilot_date:str):
    gate=read_json_strict(path)
    if gate.get("schema")!=OWNER_GATE_SCHEMA or gate.get("authorized") is not True:
        raise Blocked("PILOT_OWNER_GATE_NOT_AUTHORIZED")
    if str(gate.get("pilot_date",""))!=str(pilot_date):
        raise Blocked("PILOT_OWNER_GATE_DATE_MISMATCH")
    ids=file_ids(Path(__file__).resolve().parent)
    required={
        "preflight_report_sha256":sha256_file(preflight_path),
        "runner_sha256":ids["runner_sha256"],
        "reference_sha256":ids["reference_sha256"],
        "spec_sha256":ids["spec_sha256"],
        "preflight_sha256":ids["preflight_sha256"],
        "ledger_sha256":sha256_file(ledger_zip),
    }
    for k,v in required.items():
        if str(gate.get(k,"")).upper()!=str(v).upper():
            raise Blocked("PILOT_OWNER_GATE_BINDING_MISMATCH:"+k)
    return gate


def run_fresh_windows_preflight(ledger_zip:Path,source_root:Path,dest_root:Path,scratch_root:Path,pilot_date:str):
    base=Path(__file__).resolve().parent
    preflight=base/"WINDOWS_GATE_B_PREFLIGHT_V005.py"
    strict_regular_file(preflight)
    strict_directory(scratch_root,create=True)
    fresh=Path(scratch_root)/("FRESH_GATE_B_PREFLIGHT_"+uuid.uuid4().hex+".json")
    argv=[sys.executable,str(preflight),"--ledger-zip",str(ledger_zip),"--scratch-root",str(scratch_root),
          "--report",str(fresh),"--pilot-date",str(pilot_date),"--source-root",str(source_root),"--dest-root",str(dest_root)]
    cp=subprocess.run(argv,capture_output=True,text=True)
    if cp.returncode!=0:
        raise Blocked("FRESH_WINDOWS_PREFLIGHT_FAILED:"+str(cp.returncode)+":"+(cp.stdout+cp.stderr)[-1000:])
    try:
        validate_windows_preflight_report(fresh,ledger_zip,source_root,dest_root,scratch_root,pilot_date)
    finally:
        if strict_lstat(fresh,allow_missing=True) is not None:
            safe_unlink_regular(fresh)
    return True

def _full_json(raw):
    """Reject duplicate keys at every level, including manifest date keys."""
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj: raise Blocked("FULL_JSON_DUPLICATE_KEY:"+key)
            obj[key]=value
        return obj
    try:
        obj=json.loads(raw.decode("utf-8"),object_pairs_hook=unique,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if not isinstance(obj,dict): raise ValueError("object required")
        return obj
    except Blocked: raise
    except (ValueError,UnicodeError,TypeError) as e:
        raise Blocked("FULL_JSON_MALFORMED") from e


def _sealed_full_json(path,expected_sha):
    raw=secure_read_all(path)
    if sha256_bytes(raw)!=expected_sha: raise Blocked("FULL_SEAL_MISMATCH:"+str(path))
    return _full_json(raw)


def validate_full_plan(days,months,ledger_sha,contract):
    """Pure plan validation; no source or destination is opened here.

    Sequence serialization is UTF-8, LF-separated keys with exactly one final LF.
    Full-plan hashing uses stable_json before adding full_plan_sha256 itself.
    """
    try:
        if contract["schema"]!="TICKSTORE_FULL_PLAN_CONTRACT_V001": raise ValueError("schema")
        if ledger_sha!=contract["ledger_sha256"] or ledger_sha!=EXPECTED_P4A_LEDGER_SHA256:
            raise ValueError("ledger")
        if not days or not months: raise ValueError("empty")
        if len(days)!=contract["days"] or len(months)!=contract["months"]: raise ValueError("cardinality")
        ordered=sorted(days,key=lambda c:c["date_key"])
        dates=[c["date_key"] for c in ordered];month_keys=sorted(months)
        if days!=ordered or list(months)!=month_keys: raise ValueError("ledger ordering")
        if len(set(dates))!=len(dates): raise ValueError("duplicate date")
        if contract["dates_sorted_ascending"] is not True or contract["months_sorted_ascending"] is not True:
            raise ValueError("ordering contract")
        if contract["range_partition_exact"] is not True: raise ValueError("partition contract")
        if dates[0]!=contract["first_date"] or dates[-1]!=contract["last_date"]: raise ValueError("endpoints")
        if sha256_bytes(("\n".join(dates)+"\n").encode("utf-8"))!=contract["date_sequence_sha256"]:
            raise ValueError("date sequence")
        if sha256_bytes(("\n".join(month_keys)+"\n").encode("utf-8"))!=contract["month_sequence_sha256"]:
            raise ValueError("month sequence")
        grouped={key:[] for key in month_keys}
        for c in ordered:
            key=c["date_key"]
            if len(key)!=8 or not key.isascii() or not key.isdigit(): raise ValueError("date")
            ref.midnight_epoch_from_datekey(int(key))
            if c["month_id"]!=key[:4]+"_"+key[4:6]: raise ValueError("month/date")
            grouped[c["month_id"]].append(c)
            for field in ("time_msc_decrease_rows","price_negative_rows","negative_unsupported_rows",
                          "price_not_multiple_5_rows","offset_seconds_change_rows","f6_f7_numeric_diff_rows",
                          "f6_f7_lexical_diff_rows","f6_noncanonical_lexical_rows","f7_noncanonical_lexical_rows"):
                if int(c[field])!=0: raise ValueError("codec:"+field)
            for field in ("semantic_sha256","offset_values_sha256"):
                value=c[field]
                if len(value)!=64 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
                    raise ValueError("digest:"+field)
        for key,items in grouped.items():
            m=months[key]
            if m["month_id"]!=key or not items: raise ValueError("month identity/empty")
            if m["core_codec_compatible"]!="YES" or m["p1e_lexical_compatible"]!="YES":
                raise ValueError("month codec")
            if m["seal_integrity"]!="PASS" or m["summary_ledger_crosscheck"]!="PASS":
                raise ValueError("month seal")
            cursor=0
            for c in items:
                start=int(c["first_offset"]);last=int(c["last_offset"]);end=int(c["block_end_offset"])
                if start!=cursor or not start<=last<end or int(c["rows"])<=0:
                    raise ValueError("range partition:"+c["date_key"])
                if int(c["source_day_bytes"])!=end-start: raise ValueError("range bytes")
                cursor=end
            if cursor!=int(m["source_size"]): raise ValueError("month partition end")
            if sum(int(c["rows"]) for c in items)!=int(m["rows"]) or len(items)!=int(m["days"]):
                raise ValueError("month totals")
        rows=sum(int(c["rows"]) for c in ordered)
        day_bytes=sum(int(c["source_day_bytes"]) for c in ordered)
        month_bytes=sum(int(m["source_size"]) for m in months.values())
        if rows!=contract["rows"]: raise ValueError("rows")
        if day_bytes!=contract["source_bytes"] or month_bytes!=contract["unique_month_source_bytes"]:
            raise ValueError("source bytes")
        if day_bytes!=month_bytes: raise ValueError("source byte partition")
        if sum(int(months[c["month_id"]]["source_size"]) for c in ordered)!=contract["naive_one_month_hash_per_day_bytes"]:
            raise ValueError("month membership total")
        fields=("schema","ledger_sha256","months","days","rows","source_bytes","first_date","last_date",
                "dates_sorted_ascending","months_sorted_ascending","date_sequence_sha256","month_sequence_sha256",
                "range_partition_exact","unique_month_source_bytes","naive_one_month_hash_per_day_bytes")
        if set(contract)!=set(fields)|{"full_plan_sha256"}: raise ValueError("contract fields")
        if sha256_bytes(stable_json({key:contract[key] for key in fields}))!=contract["full_plan_sha256"]:
            raise ValueError("full plan hash")
        return ordered
    except (KeyError,ValueError,TypeError,OverflowError) as e:
        raise Blocked("FULL_PLAN_INVALID:"+str(e)) from e


def full_release_materials(base):
    contract=_sealed_full_json(base/"TICKSTORE_FULL_PLAN_CONTRACT_V001.json",FULL_PLAN_CONTRACT_SHA256)
    cert=_sealed_full_json(base/"TICKSTORE_GATE_B_R8_FINAL_CERTIFICATE_20260924.json",GATE_B_CERTIFICATE_SHA256)
    ids=file_ids(base)
    if ids["reference_sha256"]!=FROZEN_REFERENCE_SHA256: raise Blocked("FULL_REFERENCE_NOT_FROZEN")
    if ids["spec_sha256"]!=cert["r8_ids"]["spec_sha256"]: raise Blocked("FULL_R8_SPEC_NOT_FROZEN")
    if ids["preflight_sha256"]!=cert["r8_ids"]["preflight_sha256"]: raise Blocked("FULL_PREFLIGHT_NOT_FROZEN")
    ids["spec_sha256"]=sha256_file(base/"SPEC_FULL_SERIAL_R9.md")
    ids["full_plan_contract_sha256"]=FULL_PLAN_CONTRACT_SHA256
    ids["gate_b_certificate_sha256"]=GATE_B_CERTIFICATE_SHA256
    if (cert["schema"]!="TICKSTORE_GATE_B_R8_FINAL_CERTIFICATE_V001" or cert["status"]!="PASS"
            or cert["ledger_sha256"]!=EXPECTED_P4A_LEDGER_SHA256
            or cert["format_id"]!=FORMAT_ID or cert["codec_id"]!=CODEC_ID
            or cert["row_group_ticks"]!=ROW_GROUP_TICKS
            or code_revision(cert["r8_ids"])!=cert["r8_code_revision"]):
        raise Blocked("FULL_GATE_B_CERTIFICATE_INVALID")
    return contract,cert,ids


def full_gate_bindings(source_root,dest_root,scratch_root,ids,contract):
    roots=[Path(os.path.abspath(str(p))) for p in (source_root,dest_root,scratch_root)]
    for p in roots:
        strict_directory(p,create=False)
        _windows_reject_ads_path(p)
    normalized=[_norm_binding_path(p) for p in roots]
    for i,a in enumerate(normalized):
        for b in normalized[i+1:]:
            if os.path.splitdrive(a)[0]!=os.path.splitdrive(b)[0]: continue
            if os.path.commonpath([a,b]) in (a,b): raise Blocked("FULL_ROOTS_OVERLAP")
    bindings={"schema":FULL_OWNER_GATE_SCHEMA,"authorized":True,"runner_schema":RUNNER_SCHEMA,
              "runner_sha256":ids["runner_sha256"],"reference_sha256":ids["reference_sha256"],
              "full_spec_sha256":ids["spec_sha256"],"full_plan_sha256":contract["full_plan_sha256"],
              "full_plan_contract_sha256":FULL_PLAN_CONTRACT_SHA256,
              "ledger_sha256":EXPECTED_P4A_LEDGER_SHA256,"gate_b_certificate_sha256":GATE_B_CERTIFICATE_SHA256}
    for label,path,norm in zip(("source","dest","scratch"),roots,normalized):
        bindings[label+"_root"]=norm
        bindings[label+"_volume"]=windows_volume_identity(path)
    return bindings


def validate_full_owner_gate(path,expected,expected_gate_sha256):
    """External digest must be supplied independently of the gate file.

    RC1 capability is necessary but this exact external owner authorization remains mandatory.
    """
    path,expected_gate_sha256=validate_full_gate_arguments(path,expected_gate_sha256)
    gate=_sealed_full_json(path,expected_gate_sha256)
    if gate.get("authorized") is not True: raise Blocked("FULL_OWNER_GATE_NOT_AUTHORIZED")
    if set(gate)!=set(expected): raise Blocked("FULL_OWNER_GATE_FIELDS_MISMATCH")
    for key,value in expected.items():
        if type(gate[key]) is not type(value) or gate[key]!=value:
            raise Blocked("FULL_OWNER_GATE_BINDING_MISMATCH:"+key)
    return gate


def validate_full_gate_arguments(gate_path,gate_sha256):
    """Pure syntax gate for independently supplied owner-gate arguments.

    This performs no path, ledger, volume or source access and provides no fallback.
    Full byte/field validation remains the responsibility of validate_full_owner_gate.
    """
    if not isinstance(gate_path,(str,os.PathLike)) or not str(gate_path).strip():
        raise Blocked("FULL_OWNER_GATE_REQUIRED")
    if (not isinstance(gate_sha256,str) or len(gate_sha256)!=64
            or any(c not in "0123456789ABCDEFabcdef" for c in gate_sha256)):
        raise Blocked("FULL_OWNER_GATE_TRUSTED_SHA256_REQUIRED")
    return Path(gate_path),gate_sha256.upper()


def _require_full_serial_windows():
    if os.name!="nt": raise Blocked("FULL_SERIAL_REQUIRES_WINDOWS")


class FullSerialSourceView:
    """Only valid inside a continuously open write/delete-denying month pin."""
    def __init__(self,pinned): self.pinned=pinned
    @property
    def identity(self): return self.pinned.identity
    def verify_path_binding(self):
        if self.pinned.file is None or self.pinned.file.closed: raise Blocked("FULL_MONTH_PIN_CLOSED")
        return self.pinned.verify_path_binding()
    def verify_full(self): return self.verify_path_binding()
    def seek(self,*args): return self.pinned.seek(*args)
    def tell(self): return self.pinned.tell()
    def readline(self): return self.pinned.readline()


class FullSerialMonth:
    def __init__(self,path,month):
        self.pin=PinnedSource(path,int(month["source_size"]),month["source_sha256"])
    def __enter__(self):
        _require_full_serial_windows()
        try:
            self.pin.__enter__()
            return FullSerialSourceView(self.pin)
        except BaseException:
            if self.pin.file is not None:
                self.pin.__exit__(*sys.exc_info())
                self.pin.fd=None
            elif self.pin.fd is not None:
                os.close(self.pin.fd)
                self.pin.fd=None
            raise
    def __exit__(self,kind,value,tb):
        try:
            if kind is None: self.pin.verify_full()
        finally:
            self.pin.__exit__(kind,value,tb)


class FullSourceFinalSeal:
    """Retain lightweight source-pin fds through reconciliation and final verification.

    The caller performs the success-path close before PASS and retries residual handles
    in finally, including when open_all fails halfway through. No buffered file objects
    are retained: hashing uses one transient 1 MiB read.
    """
    def __init__(self,source_root,months,source_identities):
        self.source_root=source_root
        self.months=months
        self.source_identities=source_identities
        self.handles={}
        self.ready=False

    def _verify_identity(self,month_id):
        path,fd,expected=self.handles[month_id]
        month=self.months[month_id]
        if _norm_binding_path(path)!=expected["normalized_path"]:
            raise Blocked("FULL_SOURCE_FINAL_SEAL_PATH_MISMATCH:"+month_id)
        if (expected["size"]!=int(month["source_size"])
                or expected["sha256"]!=month["source_sha256"].upper()):
            raise Blocked("FULL_SOURCE_FINAL_SEAL_CAPTURED_IDENTITY_MISMATCH:"+month_id)
        for st in (strict_regular_file(path),os.fstat(fd)):
            _reject_link_or_reparse(path,st)
            _reject_multiple_links(path,st)
            if not stat.S_ISREG(st.st_mode): raise Blocked("FULL_SOURCE_FINAL_SEAL_NOT_REGULAR:"+month_id)
            if st.st_size!=expected["size"]:
                raise Blocked("FULL_SOURCE_FINAL_SEAL_SIZE_MISMATCH:"+month_id)
            if st.st_mtime_ns!=expected["mtime_ns"]:
                raise Blocked("FULL_SOURCE_FINAL_SEAL_MTIME_MISMATCH:"+month_id)
            expected_file_id=(int(expected["st_dev"]),int(expected["st_ino"]))
            actual_file_id=(int(getattr(st,"st_dev",0) or 0),int(getattr(st,"st_ino",0) or 0))
            if expected_file_id[1] and actual_file_id!=expected_file_id:
                raise Blocked("FULL_SOURCE_FINAL_SEAL_FILE_ID_MISMATCH:"+month_id)

    def hash_fd(self,fd):
        os.lseek(fd,0,os.SEEK_SET)
        digest=hashlib.sha256()
        while True:
            chunk=os.read(fd,1024*1024)
            if not chunk: break
            digest.update(chunk)
        return digest.hexdigest().upper()

    def open_all(self):
        _require_full_serial_windows()
        if self.handles or self.ready: raise Blocked("FULL_SOURCE_FINAL_SEAL_ALREADY_OPEN")
        if not self.months or set(self.source_identities)!=set(self.months):
            raise Blocked("FULL_SOURCE_FINAL_SEAL_MONTH_SET_MISMATCH")
        for month_id in sorted(self.months):
            path=self.source_root/f"WIN@N_ticks_{month_id}.csv"
            # Defer SIGINT only until the acquired descriptor is registered for cleanup.
            with FullSerialLockBoundary():
                fd=secure_open_existing_fd(path,writable=False,source_pin=True)
                self.handles[month_id]=(path,fd,dict(self.source_identities[month_id]))
            self._verify_identity(month_id)
            if self.hash_fd(fd)!=self.months[month_id]["source_sha256"].upper():
                raise Blocked("FULL_SOURCE_FINAL_SEAL_SHA256_MISMATCH:"+month_id)
            self._verify_identity(month_id)
        self.ready=True
        self.verify_bindings()

    def verify_bindings(self):
        if not self.ready or list(self.handles)!=sorted(self.months):
            raise Blocked("FULL_SOURCE_FINAL_SEAL_INCOMPLETE")
        for month_id in self.handles:self._verify_identity(month_id)

    def close(self):
        self.ready=False
        first_error=None
        failed={}
        # Finish all closes even if another Ctrl+C arrives at the cleanup boundary.
        with FullSerialLockBoundary():
            while self.handles:
                month_id,item=self.handles.popitem()
                _,fd,_=item
                try:os.close(fd)
                except OSError as e:
                    # Preserve failed descriptors for the residual finally cleanup.
                    failed[month_id]=item
                    if first_error is None:first_error=e
            self.handles.update(failed)
        if first_error is not None:
            raise Blocked("FULL_SOURCE_FINAL_SEAL_CLOSE_FAILED") from first_error


def _full_day_paths(dest_root,c):
    """Read-only counterpart of paths_for_day: never creates directories."""
    md=dest_root/"WIN@N"/c["month_id"];stem=c["date_key"]
    return {"dir":md,"container":md/(stem+".pts2g"),"commit":md/(stem+".commit.json"),
            "partial":md/(stem+".pts2g.partial"),"journal":md/(stem+".journal.json"),
            "journal_atomic":md/(stem+".journal.json.partial"),
            "commit_partial":md/(stem+".commit.json.partial"),
            "commit_stage":md/(stem+".commit.json.partial.stage")}


def _full_manifest(dest_root,expected_keys,complete=False):
    path=manifest_path(dest_root)
    if strict_lstat(path,allow_missing=True) is None:
        if complete: raise Blocked("FULL_MANIFEST_MISSING")
        return {"schema":MANIFEST_SCHEMA,"records":{}}
    m=_full_json(secure_read_all(path))
    if m.get("schema")!=MANIFEST_SCHEMA or not isinstance(m.get("records"),dict):
        raise Blocked("FULL_MANIFEST_INVALID")
    keys=set(m["records"])
    if keys-set(expected_keys): raise Blocked("FULL_MANIFEST_EXTRA")
    if complete and keys!=set(expected_keys): raise Blocked("FULL_MANIFEST_MISSING_DATES")
    for key,rec in m["records"].items():
        if not isinstance(rec,dict) or rec.get("date_key")!=key: raise Blocked("FULL_MANIFEST_DATE_MISMATCH")
    return m


def _full_no_transients(pp,dest_root):
    for key,path in pp.items():
        if key in ("dir","container","commit"): continue
        if strict_lstat(path,allow_missing=True) is not None:
            strict_regular_file(path)
            raise Blocked("FULL_LIVE_TRANSACTION:"+str(path))
    mp=manifest_path(dest_root)
    if strict_lstat(mp.with_suffix(mp.suffix+".partial"),allow_missing=True) is not None:
        raise Blocked("FULL_LIVE_MANIFEST_TRANSACTION")


def validate_certified_r8_day(pp,c,month,src_identity,ledger_sha,cert,dest_root,zstd,record):
    key=c["date_key"]
    if key not in FROZEN_PILOT_DATES: raise Blocked("FULL_R8_DATE_NOT_CERTIFIED:"+key)
    case=cert["low"] if key=="20260731" else cert["high"]
    if case["date_key"]!=key: raise Blocked("FULL_R8_CERTIFICATE_DATE")
    _full_no_transients(pp,dest_root)
    if sha256_file(pp["commit"])!=case["commit_sha256"]: raise Blocked("FULL_R8_COMMIT_CERTIFICATE_MISMATCH")
    if sha256_file(pp["container"])!=case["container_sha256"]: raise Blocked("FULL_R8_CONTAINER_CERTIFICATE_MISMATCH")
    if strict_regular_file(pp["container"]).st_size!=case["container_bytes"]: raise Blocked("FULL_R8_CONTAINER_BYTES")
    oracle=make_oracle(c,month,src_identity,ledger_sha,cert["r8_ids"])
    for field in ("rows","source_day_bytes","semantic_sha256","offset_sha256"):
        if oracle[field]!=case[field]: raise Blocked("FULL_R8_CERTIFICATE_CONTRACT:"+field)
    if oracle["code_revision"]!=cert["r8_code_revision"]: raise Blocked("FULL_R8_REVISION")
    commit=_full_json(secure_read_all(pp["commit"]))
    if commit.get("schema")!=COMMIT_SCHEMA or commit.get("oracle")!=oracle:
        raise Blocked("FULL_R8_ORACLE_MISMATCH")
    commit_matches(pp["commit"],oracle,pp["container"],record,zstd,c)
    return "REUSED"


def _is_r8_pair(pp,cert):
    if strict_lstat(pp["commit"],allow_missing=True) is None: return False
    obj=_full_json(secure_read_all(pp["commit"]))
    oracle=obj.get("oracle")
    if not isinstance(oracle,dict): raise Blocked("FULL_COMMIT_ORACLE_INVALID")
    ids=oracle.get("runner_ids")
    return isinstance(ids,dict) and ids.get("runner_sha256")==cert["r8_ids"]["runner_sha256"]


def _full_artifact_inventory(dest_root,expected):
    """Walk destination only, reject links before descent, never follow aliases.

    Windows directory handles remain pinned while each directory is enumerated.
    Unknown date artifacts and all surviving transaction sidecars block.
    """
    found=set()
    suffixes=(".pts2g",".commit.json")
    transients=(".pts2g.partial",".journal.json",".journal.json.partial",
                ".commit.json.partial",".commit.json.partial.stage")
    def walk(directory):
        strict_directory(directory,create=False)
        pins=_windows_pin_ancestor_chain(directory) if os.name=="nt" else []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path=directory/entry.name;st=strict_lstat(path)
                    _reject_link_or_reparse(path,st)
                    if stat.S_ISDIR(st.st_mode): walk(path)
                    elif stat.S_ISREG(st.st_mode):
                        strict_regular_file(path)
                        name=entry.name.lower()
                        if name.endswith(transients): raise Blocked("FULL_EXTRA_OR_LIVE_TRANSACTION:"+str(path))
                        if name.endswith(suffixes):
                            norm=_norm_binding_path(path)
                            if norm not in expected or norm in found: raise Blocked("FULL_EXTRA_OR_DUPLICATE_ARTIFACT:"+str(path))
                            found.add(norm)
                    else: raise Blocked("FULL_NONREGULAR_ARTIFACT:"+str(path))
        finally:
            _windows_unpin(pins)
    walk(dest_root)
    if found!=expected: raise Blocked("FULL_ARTIFACTS_MISSING")


def reconcile_full_readonly(dest_root,days,months,ledger_sha,ids,cert,source_identities,zstd):
    """No repair, cleanup, directory creation or source hashing is allowed here."""
    keys={c["date_key"] for c in days}
    if len(keys)!=len(days): raise Blocked("FULL_RECONCILE_DUPLICATE_PLAN")
    manifest=_full_manifest(dest_root,keys,complete=True)
    expected=set()
    for c in days:
        pp=_full_day_paths(dest_root,c)
        _full_no_transients(pp,dest_root)
        for name in ("container","commit"):
            strict_regular_file(pp[name]);expected.add(_norm_binding_path(pp[name]))
        src_id=source_identities[c["month_id"]]
        if _is_r8_pair(pp,cert):
            validate_certified_r8_day(pp,c,months[c["month_id"]],src_id,ledger_sha,cert,
                                     dest_root,zstd,manifest["records"][c["date_key"]])
        else:
            oracle=make_oracle(c,months[c["month_id"]],src_id,ledger_sha,ids)
            commit_matches(pp["commit"],oracle,pp["container"],manifest["records"][c["date_key"]],zstd,c)
    _full_artifact_inventory(dest_root,expected)
    # A second immutable read catches manifest changes during reconciliation.
    if _full_manifest(dest_root,keys,complete=True)!=manifest: raise Blocked("FULL_MANIFEST_CHANGED")
    _full_artifact_inventory(dest_root,expected)
    mp=manifest_path(dest_root)
    if strict_lstat(mp.with_suffix(mp.suffix+".partial"),allow_missing=True) is not None:
        raise Blocked("FULL_LATE_MANIFEST_TRANSACTION")
    # Third read follows the second complete inventory and the final shadow check.
    if _full_manifest(dest_root,keys,complete=True)!=manifest: raise Blocked("FULL_MANIFEST_CHANGED")


def _full_progress(done,total,key,counts,started):
    elapsed=max(time.perf_counter()-started,0.0)
    eta=ref.fmt_eta(elapsed*(total-done)/done) if done else "UNKNOWN"
    print(f"DAY={done}/{total} DATE_KEY={key} PERCENT={100*done/total:.6f} ETA={eta} "
          f"BUILT_COUNT={counts['BUILT']} REUSED_COUNT={counts['REUSED']} "
          f"RESUMED_COUNT={counts['RESUMED']} FAILED_COUNT={counts['FAILED']}",flush=True)


class FullSerialLockBoundary:
    """Defer SIGINT only across acquire/ownership assignment or release.

    Conversion stays interruptible. A signal cannot strand an acquired lock before
    the caller assigns ownership, or interrupt successful lock removal halfway.
    """
    def __enter__(self):
        self.pending=False
        self.previous=signal.getsignal(signal.SIGINT)
        def deferred(signum,frame): self.pending=True
        signal.signal(signal.SIGINT,deferred)
        return self
    def __exit__(self,kind,value,tb):
        signal.signal(signal.SIGINT,self.previous)
        if kind is None and self.pending: raise KeyboardInterrupt()


def _execute_full_serial(source_root,dest_root,days,months,ledger_sha,ids,cert,zstd,fault=None):
    """Internal engine for validated inputs. No CLI bypass; synthetic tests call this layer.

    No success is emitted until final source sealing, read-only global reconciliation,
    successful writer-lock release, final binding verification and successful seal close.
    Per-day journals remain the sole resume authority.
    """
    if not days: raise Blocked("FULL_EMPTY_PLAN")
    fault=fault or FaultInjector(None)
    counts={"BUILT":0,"REUSED":0,"RESUMED":0,"FAILED":0}
    done=0;key=days[0]["date_key"];started=time.perf_counter();identities={}
    keys={c["date_key"] for c in days}
    lock=None
    seal=FullSourceFinalSeal(source_root,months,identities)
    primary_error=None
    try:
        strict_directory(dest_root,create=False)
        try:
            with FullSerialLockBoundary():
                lock=acquire_lock(dest_root)
            _full_manifest(dest_root,keys)
            _full_progress(done,len(days),key,counts,started)
            for month_id in sorted(months):
                items=[c for c in days if c["month_id"]==month_id]
                if not items: raise Blocked("FULL_EMPTY_MONTH:"+month_id)
                with FullSerialMonth(source_for(source_root,items[0]),months[month_id]) as view:
                    identities[month_id]=dict(view.identity)
                    for c in items:
                        key=c["date_key"]
                        fault.hit("BEFORE_DAY:"+key)
                        manifest=_full_manifest(dest_root,keys)
                        pp=_full_day_paths(dest_root,c)
                        if _is_r8_pair(pp,cert):
                            view.verify_full()
                            status=validate_certified_r8_day(pp,c,months[month_id],dict(view.identity),
                                ledger_sha,cert,dest_root,zstd,manifest["records"].get(key))
                            view.verify_full()
                        else:
                            oracle=make_oracle(c,months[month_id],dict(view.identity),ledger_sha,ids)
                            status=_run_day_already_locked(view,c,oracle,dest_root,zstd,fault)
                        if status not in ("BUILT","REUSED","RESUMED","RESUMED_PUBLICATION","RESUMED_MANIFEST"):
                            raise Blocked("FULL_UNKNOWN_DAY_STATUS:"+str(status))
                        counts["RESUMED" if status.startswith("RESUMED") else status]+=1
                        done+=1
                        _full_progress(done,len(days),key,counts,started)
                        fault.hit("AFTER_DAY:"+key)
            if done!=len(days): raise Blocked("FULL_DAY_COUNT_MISMATCH")
            print("FULL_SOURCE_FINAL_SEAL=START",flush=True)
            seal.open_all()
            reconcile_full_readonly(dest_root,days,months,ledger_sha,ids,cert,identities,zstd)
        finally:
            if lock is not None:
                with FullSerialLockBoundary():
                    release_lock(lock)
                    lock=None
        seal.verify_bindings()
        seal.close()
    except BaseException:
        primary_error=sys.exc_info()
    finally:
        if seal.handles:
            try:
                seal.close()
            except BaseException:
                # Cleanup is best-effort after an established failure and must not
                # replace the original close/open/reconciliation/interruption cause.
                if primary_error is None:primary_error=sys.exc_info()

    if primary_error is not None:
        _,error,traceback=primary_error
        if isinstance(error,KeyboardInterrupt):
            print("SAFE_STOP=YES",flush=True)
            print("REUSABLE_PROGRESS=ONLY_JOURNALED_GROUPS_AND_PROVEN_PUBLICATIONS",flush=True)
            return 130
        if isinstance(error,Exception):
            counts["FAILED"]+=1
            _full_progress(done,len(days),key,counts,started)
        raise error.with_traceback(traceback)

    print("TICKSTORE_FULL_SERIAL_STATUS=PASS",flush=True)
    return 0


def run_full_serial(source_root,dest_root,scratch_root,ledger_zip,gate_path,gate_sha256):
    # Package capability is necessary but never substitutes for the external owner gate.
    if not FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE:
        raise Blocked("FULL_SERIAL_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE")
    gate_path,gate_sha256=validate_full_gate_arguments(gate_path,gate_sha256)
    _require_full_serial_windows()
    zstd=require_windows_pilot_runtime()
    base=Path(__file__).resolve().parent
    contract,cert,ids=full_release_materials(base)
    days,months,ledger_sha=load_ledgers(ledger_zip)
    days=validate_full_plan(days,months,ledger_sha,contract)
    bindings=full_gate_bindings(source_root,dest_root,scratch_root,ids,contract)
    validate_full_owner_gate(gate_path,bindings,gate_sha256)
    return _execute_full_serial(source_root,dest_root,days,months,ledger_sha,ids,cert,zstd)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--plan",action="store_true")
    ap.add_argument("--ledger-zip")
    ap.add_argument("--source-root")
    ap.add_argument("--dest-root")
    ap.add_argument("--pilot-date")
    ap.add_argument("--pilot-gate-file")
    ap.add_argument("--windows-preflight-report")
    ap.add_argument("--scratch-root")
    ap.add_argument("--full-history",action="store_true")
    ap.add_argument("--mode",choices=("FULL_SERIAL",))
    ap.add_argument("--full-gate-file")
    ap.add_argument("--full-gate-sha256")
    ap.add_argument("--inject")
    args=ap.parse_args()

    if args.mode=="FULL_SERIAL":
        if args.plan or args.pilot_date or args.full_history or args.inject:
            raise Blocked("FULL_SERIAL_CONFLICTING_MODE")
        if not FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE:
            raise Blocked("FULL_SERIAL_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE")
        # Gate syntax is checked before any source/destination/ledger access.
        gate_path,gate_sha256=validate_full_gate_arguments(args.full_gate_file,args.full_gate_sha256)
        if not all((args.source_root,args.dest_root,args.scratch_root,args.ledger_zip)):
            raise Blocked("FULL_SERIAL_PATHS_REQUIRED")
        return run_full_serial(Path(args.source_root),Path(args.dest_root),Path(args.scratch_root),
                               Path(args.ledger_zip),gate_path,gate_sha256)

    if not args.ledger_zip: raise Blocked("LEDGER_ZIP_REQUIRED")
    ledger=Path(args.ledger_zip)

    if args.plan:
        return plan(ledger)

    if args.pilot_date:
        if not PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE:
            raise Blocked("PILOT_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE")
        if args.pilot_date not in FROZEN_PILOT_DATES:
            raise Blocked("PILOT_DATE_NOT_FROZEN_GATE_B_CASE:"+str(args.pilot_date))
        require_windows_pilot_runtime()
        if not args.source_root or not args.dest_root: raise Blocked("SOURCE_DEST_REQUIRED")
        if not args.scratch_root: raise Blocked("WINDOWS_GATE_B_SCRATCH_ROOT_REQUIRED")
        if not args.windows_preflight_report: raise Blocked("WINDOWS_PREFLIGHT_REPORT_REQUIRED")
        srcroot=Path(args.source_root);destroot=Path(args.dest_root);scratch=Path(args.scratch_root);pre=Path(args.windows_preflight_report)
        validate_windows_preflight_report(pre,ledger,srcroot,destroot,scratch,args.pilot_date)
        if not args.pilot_gate_file: raise Blocked("PILOT_GATE_FILE_REQUIRED")
        require_pilot_owner_gate(Path(args.pilot_gate_file),pre,ledger,args.pilot_date)
        run_fresh_windows_preflight(ledger,srcroot,destroot,scratch,args.pilot_date)
        return run_one_day(srcroot,destroot,ledger,args.pilot_date,args.inject)

    if args.full_history:
        if not FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE:
            raise Blocked("FULL_HISTORY_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE")
        if not args.full_gate_file: raise Blocked("FULL_GATE_FILE_REQUIRED")
        require_gate(Path(args.full_gate_file),"TICKSTORE_FULL_HISTORY_AUTHORIZED=YES")
        raise Blocked("FULL_HISTORY_DISPATCH_INTENTIONALLY_NOT_RELEASED_IN_GATE_A_PACKAGE")

    raise Blocked("NO_MODE_SELECTED")

if __name__=="__main__":
    try:
        rc=main()
        raise SystemExit(rc or 0)
    except KeyboardInterrupt:
        print("SAFE_STOP=YES")
        print("REUSABLE_PROGRESS=ONLY_JOURNALED_GROUPS")
        raise SystemExit(130)
    except Blocked as e:
        print("TICKSTORE_RUNNER_STATUS=BLOCKED")
        print("REASON="+str(e))
        raise SystemExit(2)
    except OSError as e:
        print("TICKSTORE_RUNNER_STATUS=BLOCKED_OSERROR")
        print(f"REASON={type(e).__name__}:errno={getattr(e,'errno',None)}:{e}")
        raise SystemExit(3)
