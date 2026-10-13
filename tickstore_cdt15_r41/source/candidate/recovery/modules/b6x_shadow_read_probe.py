from __future__ import annotations
import argparse,ctypes,hashlib,importlib.util,json,pathlib,sys,traceback

def req(ok,msg):
    if not ok:raise RuntimeError(msg)
def shab(data):return hashlib.sha256(data).hexdigest().upper()
def stable(obj):return (json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)+"\n").encode()
def load_engine(path):
    spec=importlib.util.spec_from_file_location("tickstore_b6x_engine",path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def volume_guid():
    k=ctypes.WinDLL("kernel32",use_last_error=True);b=ctypes.create_unicode_buffer(1024);ok=k.GetVolumeNameForVolumeMountPointW("D:\\",b,len(b))
    if not ok:raise RuntimeError("B6X_VOLUME_GUID:WINERROR="+str(ctypes.get_last_error()))
    return b.value

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--package",required=True);ap.add_argument("--workspace",required=True);ap.add_argument("--b4",required=True);ap.add_argument("--result",required=True);a=ap.parse_args()
    pkg=pathlib.Path(a.package).resolve();workspace=pathlib.Path(a.workspace).resolve();b4p=pathlib.Path(a.b4).resolve();resultp=pathlib.Path(a.result).resolve();cfg=json.loads((pkg/"config/STAGE_A_SEALED_VALUES_V001.json").read_text())
    eng=load_engine((pkg/"engine/tickstore_publisher_recovery_v004_release.py").resolve());sys.path.insert(0,str(workspace));from compression import zstd
    ledger_raw=pathlib.Path(cfg["ledger_path"]).read_bytes();req(shab(ledger_raw)==cfg["ledger_sha256"],"B6X_LEDGER_SHA");days,months=eng.ledger_from_bytes(ledger_raw)
    b4=json.loads(b4p.read_text());dest_meta={x["path"]:x for x in b4["dest"]};req(len(dest_meta)==303,"B6X_B4_DEST_303")
    st=eng.Win32Store();
    with st.open(pathlib.Path("D:\\"),directory=True) as f:volume_identity=f.info()["volume"]
    profile={"context":25,"snapshot_execution_authorized":True,"provider_id":cfg["microsoft_vss_provider_id"],"volume_guid":volume_guid(),"volume_identity":volume_identity,"drive":"D:","create_deadline_seconds":600}
    v=eng.NativeVSS(st,profile);generation=None;result=None;primary=None
    try:
        print("B6X_STEP=CREATE",flush=True);generation=v.create("B6X_SHADOW_READ");v.assert_present(generation);shadow_dest=v.shadow_root(generation,cfg["production_dest_root"]);shadow_scratch=v.shadow_root(generation,cfg["production_scratch_root"])
        print("B6X_STEP=OPEN_ROOTS",flush=True)
        for root in (shadow_dest,shadow_scratch):
            with st.open(root,directory=True):pass
        print("B6X_STEP=MANIFEST",flush=True);mr=dest_meta["TICKSTORE_GLOBAL_MANIFEST.json"]
        with st.open(pathlib.Path(shadow_dest)/"TICKSTORE_GLOBAL_MANIFEST.json") as f:raw=f.read();mh,mn=f.hash()
        req((mh,mn)==(mr["sha256"],mr["bytes"]),"B6X_MANIFEST_B4_MISMATCH")
        print("B6X_STEP=C0_THREE_DAYS",flush=True);containers=[x for x in b4["dest"] if x["path"].endswith(".pts2g")];req(len(containers)==151,"B6X_C0_CONTAINER_151");ordered=sorted(containers,key=lambda x:(int(x["bytes"]),x["path"]));selected=[ordered[0],ordered[len(ordered)//2],ordered[-1]];req(len({x["path"] for x in selected})==3,"B6X_C0_SELECTION_UNIQUE");c0=[]
        for item in selected:
            key=pathlib.PurePosixPath(item["path"]).name.removesuffix(".pts2g");contract=days[key];_base,cp,kp=eng.day_paths(pathlib.Path(shadow_dest),contract)
            with st.open(kp) as f:oracle=eng.parse(f.read())["oracle"]
            eng.oracle_contract(oracle,contract,months[contract["month_id"]]);pair=eng.validate_pair(st,pathlib.Path(shadow_dest),contract,oracle,zstd);ec=dest_meta[cp.relative_to(shadow_dest).as_posix()];ek=dest_meta[kp.relative_to(shadow_dest).as_posix()];req(pair["container"]=={"sha256":ec["sha256"],"bytes":ec["bytes"]},"B6X_C0_CONTAINER_MISMATCH:"+key);req(pair["commit"]=={"sha256":ek["sha256"],"bytes":ek["bytes"]},"B6X_C0_COMMIT_MISMATCH:"+key);c0.append({"date_key":key,"container":pair["container"],"commit":pair["commit"]})
        print("B6X_STEP=S0_LARGEST_DAY_20210304",flush=True);key="20210304";jm=[x for x in b4["scratch"] if x["path"].endswith("/"+key+".journal.json") or x["path"]==key+".journal.json"];pm=[x for x in b4["scratch"] if x["path"].endswith("/"+key+".pts2g.partial") or x["path"]==key+".pts2g.partial"];req(len(jm)==1 and len(pm)==1,"B6X_S0_20210304_CARDINALITY");jm,pm=jm[0],pm[0];req(int(pm["bytes"])==15017474,"B6X_S0_20210304_EXPECTED_BYTES");jp=pathlib.Path(shadow_scratch).joinpath(*pathlib.PurePosixPath(jm["path"]).parts);pp=pathlib.Path(shadow_scratch).joinpath(*pathlib.PurePosixPath(pm["path"]).parts)
        with st.open(jp) as jf:jraw=jf.read();jh,jn=jf.hash()
        with st.open(pp) as pf:ph,pn=pf.hash()
        journal=eng.parse(jraw);oracle=eng.oracle_contract(journal["oracle"],days[key],months[days[key]["month_id"]]);entry={"namespace":pathlib.PurePosixPath(jm["path"]).parts[0],"contract":oracle,"journal":{"path":jm["path"],"sha256":jh,"bytes":jn},"partial":{"path":pm["path"],"sha256":ph,"bytes":pn}};prep=eng.prep(st,pathlib.Path(shadow_scratch),entry,days[key],months[days[key]["month_id"]],zstd);req(prep["container_sha256"]==ph and prep["container_bytes"]==pn,"B6X_S0_PREP_MISMATCH")
        print("B6X_STEP=SCAN_S0_FULL",flush=True);obs=eng.scan_s0(st,pathlib.Path(shadow_scratch));req(len(obs)==2798,"B6X_S0_OBJECTS_2798");grouped={}
        for x in obs:grouped.setdefault(x["date_key"],set()).add(x["kind"])
        req(len(grouped)==1399 and all(vv=={"journal","partial"} for vv in grouped.values()),"B6X_S0_1399")
        print("B6X_STEP=DEST_INVENTORY_303",flush=True);inv=st.inventory(pathlib.Path(shadow_dest));req(len(inv)==303,"B6X_DEST_INVENTORY_303");inv_map={x["path"]:x for x in inv};expected={k:{"path":k,"sha256":v["sha256"],"bytes":v["bytes"]} for k,v in dest_meta.items()};req(inv_map==expected,"B6X_DEST_INVENTORY_B4_MISMATCH")
        result={"schema":"B6X_SHADOW_READ_PATH_V001","status":"PASS","release_sha256":cfg["delta_release_source_sha256"],"core_sha256":eng.CORE_SHA,"reference_sha256":eng.REFERENCE_SHA,"generation":{"snapshot_id":generation["snapshot_id"],"snapshot_set_id":generation["snapshot_set_id"],"device_object":generation["device_object"],"provider_id":generation["provider_id"],"creation_timestamp":generation["creation_timestamp"]},"manifest":{"sha256":mh,"bytes":mn},"c0_days":c0,"s0_largest_day":{"date_key":key,"partial_sha256":ph,"partial_bytes":pn,"prep_container_sha256":prep["container_sha256"]},"s0_scan":{"days":len(grouped),"objects":len(obs)},"dest_inventory":{"files":len(inv),"sha256":shab(stable(inv))}};resultp.parent.mkdir(parents=True,exist_ok=True);resultp.write_bytes(stable(result));print("B6X_SHADOW_READ_PATH=PASS",flush=True)
    except BaseException as exc:primary=exc
    finally:
        if generation is not None:
            try:print("B6X_STEP=CLEANUP_OWN_GENERATION",flush=True);v.delete_generation(generation,"B6X");print("B6X_OWN_GENERATION_CLEANUP=PASS",flush=True)
            except BaseException as cleanup:
                if primary is not None:
                    try:primary.add_note("B6X_CLEANUP_ERROR:"+str(cleanup))
                    except Exception:pass
                else:primary=cleanup
        v.close()
    if primary is not None:raise primary
    req(result is not None,"B6X_RESULT_MISSING");return 0
if __name__=="__main__":
    try:raise SystemExit(main())
    except BaseException as exc:print("B6X_SHADOW_READ_PATH=FAIL:"+str(exc),flush=True);traceback.print_exc();raise
