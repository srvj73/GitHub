from __future__ import annotations
import ctypes
import importlib.util
import json
import pathlib
import sys
import traceback

def require(ok,msg):
    if not ok:
        raise RuntimeError(msg)

def volume_guid():
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    b=ctypes.create_unicode_buffer(1024)
    ok=k.GetVolumeNameForVolumeMountPointW("D:\\",b,len(b))
    if not ok:
        raise RuntimeError("VOLUME_GUID:WINERROR="+str(ctypes.get_last_error()))
    value=b.value
    require(value.startswith("\\\\?\\Volume{") and value.endswith("}\\"),"VOLUME_GUID_FORMAT")
    return value

def main():
    if len(sys.argv)!=3:
        raise SystemExit("ARGS")
    pkg=pathlib.Path(sys.argv[1]).resolve()
    release_arg=pathlib.Path(sys.argv[2]).resolve()
    cfg=json.loads((pkg/"config/STAGE_A_SEALED_VALUES_V001.json").read_text(encoding="utf-8"))
    ep=(pkg/"engine/tickstore_publisher_recovery_v004_release.py").resolve()
    require(release_arg==ep,"RELEASE_ARG_MISMATCH")

    spec=importlib.util.spec_from_file_location("tickstore_b6_microprobe_engine",ep)
    eng=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eng)

    st=eng.Win32Store()
    with st.open(pathlib.Path("D:\\"),directory=True) as f:
        volume=f.info()["volume"]

    profile={
        "context":25,
        "snapshot_execution_authorized":True,
        "provider_id":cfg["microsoft_vss_provider_id"],
        "volume_guid":volume_guid(),
        "volume_identity":volume,
        "drive":"D:",
        "create_deadline_seconds":600,
    }

    v=eng.NativeVSS(st,profile)
    try:
        v.startup_probe(cfg["production_dest_root"],cfg["production_scratch_root"])
    finally:
        v.close()

    print("B6_VSS_MICROPROBE=PASS",flush=True)
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        print("B6_VSS_MICROPROBE=FAIL:"+str(exc),flush=True)
        traceback.print_exc()
        raise
