"""CDT15 G4: Windows-only, READ-ONLY target admission observation.

No official publication, install, cleanup, locks or activation. A PASS here is
not authorization to write: the effectful writer must rebind open handles and
pass all policy/gate checks after this receipt. No arbitrary target path input.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import ntpath
import re
import sys
from pathlib import Path

SCHEMA = 'CDT15_G4_OFFICIAL_TARGET_READONLY_V001'
MENU = r'D:\Base CSV\Scripts\Biblioteca\MENU.py'
BAT = r'D:\Base CSV\Manutenção Base de Dados.bat'
MENU_SHA = '7080DCB0A2A14147CAD8C07A00607C17DE73C1DB61D8A110332871A2829C947F'
BAT_SHA = '9C2CAB199832E8E549B2ED54EAE8218D18718A0633BCA7BAC285263CE79EEA08'
CANDIDATE_MENU_SHA = 'D7402CAF7774620B75B201BB845945087C29E88DDE074B0CEBA392E869FCB58C'  # checked against package by builder
SOURCE_POLICY_SHA = '695DCD6495E549B13B13A73E063EA147CF97354C53940A70647EDFD0A0BC7DF5'
ACTIVE_NAME = 'ACTIVE_DEPLOYMENT.json'
TX_NAME = 'MENU_TRANSACTION'
FILE_REPARSE = 0x400
GENERIC_READ = 0x80000000
FILE_READ_ATTRIBUTES = 0x80
FILE_SHARE_READ = 1
OPEN_EXISTING = 3
FLAG_BACKUP = 0x02000000
FLAG_OPEN_REPARSE = 0x00200000

class Blocked(Exception):
    pass

def digest(blob):
    return hashlib.sha256(blob).hexdigest().upper()

def good_hash(x):
    return isinstance(x,str) and re.fullmatch(r'[0-9A-F]{64}',x) is not None

def validate_observation(obs, *, local_appdata):
    """Pure, independently unit-testable admission boundary; cannot authorize effects."""
    if set(obs) != {'menu','bat','active','transaction','active_root'}:
        raise Blocked('OBSERVATION_FIELDS')
    if not isinstance(local_appdata,str) or not re.fullmatch(r'[A-Za-z]:\\[^%]*',local_appdata):
        raise Blocked('LOCALAPPDATA_NOT_ABSOLUTE')
    root = ntpath.normpath(local_appdata + r'\TICKSTORE')
    # The target never comes from user CLI or a portable fixture.
    expected={'menu':(MENU,MENU_SHA),'bat':(BAT,BAT_SHA),
              'active':(ntpath.join(root,ACTIVE_NAME),None),
              'transaction':(ntpath.join(root,TX_NAME),None),
              'active_root':(root,None)}
    for name,(path,expected_sha) in expected.items():
        value=obs[name]
        if not isinstance(value,dict) or value.get('path','').casefold()!=path.casefold():
            raise Blocked('PATH_IDENTITY_'+name.upper())
        if value.get('status') not in ('PRESENT','ABSENT'):
            raise Blocked('OBS_STATUS_'+name.upper())
        if value.get('status')=='ABSENT':
            if name in ('menu','bat'):
                raise Blocked('HISTORICAL_TARGET_MISSING_'+name.upper())
            continue
        if value.get('reparse') is not False or value.get('final_path_match') is not True:
            raise Blocked('TARGET_REDIRECTION_'+name.upper())
        if name in ('menu','bat','active'):
            if value.get('nlink')!=1 or not good_hash(value.get('sha256')):
                raise Blocked('TARGET_FILE_IDENTITY_'+name.upper())
            if expected_sha and value['sha256']!=expected_sha:
                raise Blocked('BASELINE_DRIFT_'+name.upper())
        if name in ('active','transaction'):
            # An existing ACTIVE or transaction requires its own independent
            # disposition. Do not overwrite, reconcile or remove by assumption.
            raise Blocked('EXISTING_BOUNDARY_REQUIRES_RECONCILIATION_'+name.upper())
    return {'schema':SCHEMA,'status':'PASS_READONLY_IDENTITY_ONLY',
            'menu_before_sha256':MENU_SHA, 'bat_sha256':BAT_SHA,
            'candidate_menu_sha256':CANDIDATE_MENU_SHA,
            'policy_master_sha256_source':SOURCE_POLICY_SHA,
            'active_target_status':obs['active']['status'],
            'effects_authorized':False,'production_modified':False,
            'full_started':False}

# Native handle metadata for the Windows probe. No write access requested.
if os.name == 'nt':
    from ctypes import Structure, byref
    class FILETIME(Structure):
        _fields_=[('low',wintypes.DWORD),('high',wintypes.DWORD)]
    class FILEINFO(Structure):
        _fields_=[('attributes',wintypes.DWORD),('creation',FILETIME),
                  ('access',FILETIME),('write',FILETIME),('volume',wintypes.DWORD),
                  ('size_high',wintypes.DWORD),('size_low',wintypes.DWORD),
                  ('links',wintypes.DWORD),('index_high',wintypes.DWORD),('index_low',wintypes.DWORD)]
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
          ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes=[wintypes.HANDLE,ctypes.POINTER(FILEINFO)]
    kernel.GetFileInformationByHandle.restype=wintypes.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
    kernel.GetFinalPathNameByHandleW.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    kernel.GetFileAttributesW.argtypes=[wintypes.LPCWSTR]
    kernel.GetFileAttributesW.restype=wintypes.DWORD

def _exists_native(path):
    attrs=kernel.GetFileAttributesW(path)
    if attrs!=0xFFFFFFFF:return True
    err=ctypes.get_last_error()
    if err in (2,3):return False
    raise Blocked('WIN32_EXISTENCE_UNKNOWN_'+str(err))

def _native_open(path, directory=False):
    flags=FLAG_OPEN_REPARSE | (FLAG_BACKUP if directory else 0)
    h=kernel.CreateFileW(path,GENERIC_READ if not directory else FILE_READ_ATTRIBUTES,
                         FILE_SHARE_READ,None,OPEN_EXISTING,flags,None)
    if h==wintypes.HANDLE(-1).value:
        raise Blocked('OPEN_HANDLE_'+str(ctypes.get_last_error()))
    return h

def _meta(h,path):
    info=FILEINFO()
    if not kernel.GetFileInformationByHandle(h,ctypes.byref(info)):
        raise Blocked('WIN32_FILEINFO_'+str(ctypes.get_last_error()))
    b=ctypes.create_unicode_buffer(32768)
    size=kernel.GetFinalPathNameByHandleW(h,b,len(b),0)
    if size==0 or size>=len(b):
        raise Blocked('WIN32_FINALPATH_'+str(ctypes.get_last_error()))
    final=b.value
    if final.startswith('\\\\?\\'):
        final=final[4:]
    # No alternate path roots, magic names, or UNC accepted.
    same=(os.path.normcase(os.path.normpath(final))==os.path.normcase(os.path.normpath(path)))
    return {'attributes':int(info.attributes),'nlink':int(info.links),
            'final_path_match':same,'volume':int(info.volume),
            'file_index':(int(info.index_high)<<32)|int(info.index_low)}

def _ancestors(path):
    p=Path(path)
    items=[]
    while True:
        p=p.parent
        if str(p)=='.':break
        items.append(str(p))
        if p.parent==p:break
    return list(reversed(items))

def _probe(path, *, kind):
    for folder in _ancestors(path):
        if not _exists_native(folder):
            if folder.lower().endswith('\\tickstore'):
                return {'path':path,'status':'ABSENT'}
            raise Blocked('ANCESTOR_MISSING_'+folder)
        h=_native_open(folder,directory=True)
        try:
            m=_meta(h,folder)
            if m['attributes']&FILE_REPARSE or not m['final_path_match']:
                raise Blocked('ANCESTOR_REPARSE_OR_REDIRECT_'+folder)
        finally: kernel.CloseHandle(h)
    if not _exists_native(path):
        return {'path':path,'status':'ABSENT'}
    if kind=='dir':
        h=_native_open(path,directory=True)
        try:
            m=_meta(h,path)
            return {'path':path,'status':'PRESENT','reparse':bool(m['attributes']&FILE_REPARSE),
                    'final_path_match':m['final_path_match'],'nlink':m['nlink']}
        finally:kernel.CloseHandle(h)
    h=_native_open(path)
    try:
        m=_meta(h,path)
        if m['attributes'] & FILE_REPARSE or not m['final_path_match'] or m['nlink']!=1:
            raise Blocked('FILE_IDENTITY_'+path)
        # The same handle supplies the digest; FILE_SHARE_READ blocks concurrent
        # WRITE/DELETE handles during this probe, but not after it is closed.
        import msvcrt
        fd=msvcrt.open_osfhandle(h,os.O_RDONLY|os.O_BINARY)
        h=None
        try:
            import hashlib
            sh=hashlib.sha256()
            with os.fdopen(fd,'rb',closefd=True) as stream:
                while True:
                    chunk=stream.read(1024*1024)
                    if not chunk:break
                    sh.update(chunk)
            return {'path':path,'status':'PRESENT','reparse':False,
                    'final_path_match':True,'nlink':1,'sha256':sh.hexdigest().upper()}
        except Exception:
            # fd owns handle; its context manager normally closes it.
            raise
    finally:
        if h is not None:kernel.CloseHandle(h)

def run_readonly():
    if os.name!='nt':raise Blocked('WINDOWS_ONLY')
    app=os.environ.get('LOCALAPPDATA','')
    if not re.fullmatch(r'[A-Za-z]:\\[^%]+',app):raise Blocked('LOCALAPPDATA_INVALID')
    root=ntpath.normpath(app+r'\TICKSTORE')
    if os.path.normcase(root)==os.path.normcase(os.path.abspath(os.sep)):
        raise Blocked('ROOT_INVALID')
    observations={
       'menu':_probe(MENU,kind='file'),
       'bat':_probe(BAT,kind='file'),
       'active_root':_probe(root,kind='dir'),
       'active':_probe(ntpath.join(root,ACTIVE_NAME),kind='file'),
       'transaction':_probe(ntpath.join(root,TX_NAME),kind='dir'),
    }
    # A second read of the historical targets detects between-file drift.
    second_menu=_probe(MENU,kind='file')
    second_bat=_probe(BAT,kind='file')
    if second_menu!=observations['menu'] or second_bat!=observations['bat']:
        raise Blocked('HISTORICAL_TARGET_CHANGED_DURING_PROBE')
    verdict=validate_observation(observations,local_appdata=app)
    return {'verdict':verdict,'observation':observations}

if __name__=='__main__':
    # No arbitrary destination, CLI target path, install or effectful mode.
    try:
        if sys.argv[1:]!=['--readonly']:
            raise Blocked('READONLY_ONLY')
        result=run_readonly()
        print(json.dumps(result,sort_keys=True,ensure_ascii=True))
        print('G4_OFFICIAL_TARGET_PREFLIGHT=PASS_READONLY_ONLY')
    except (Blocked,OSError,ValueError) as exc:
        print('G4_OFFICIAL_TARGET_PREFLIGHT=BLOCKED:'+str(exc))
        sys.exit(2)
