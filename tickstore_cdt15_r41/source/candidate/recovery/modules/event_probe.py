import ctypes,sys
from ctypes import wintypes as w
k=ctypes.WinDLL("kernel32",use_last_error=True)
k.OpenEventW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR]
k.OpenEventW.restype=w.HANDLE
k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
k.WaitForSingleObject.restype=w.DWORD
k.CloseHandle.argtypes=[w.HANDLE]
name=sys.argv[1]
h=k.OpenEventW(0x00100000,False,name)
print("OPEN="+str(bool(h)),flush=True)
if not h: raise SystemExit(2)
try:
    r=k.WaitForSingleObject(h,10000)
    print("WAIT="+str(r),flush=True)
    raise SystemExit(0 if r==0 else 2)
finally:
    k.CloseHandle(h)
