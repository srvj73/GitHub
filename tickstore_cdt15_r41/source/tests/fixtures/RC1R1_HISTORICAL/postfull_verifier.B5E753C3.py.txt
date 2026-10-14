from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,pathlib,zipfile

LEDGER_SHA="27FF5A0FE47F3DDC5FD63F6371CCF0EDA8124E0E5D504A8F0756A4DF0DB9C3CA"
CORE_SHA="D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0"
REFERENCE_SHA="74EE141B014DE7A9F9C401C2B3C5AF6BF72E5D7D80F49E67F9D9032338480165"
R8_CERTIFIED_DATES=frozenset(("20211022","20260731"))
R8_CERTIFIED_RUNNER_IDS={
    "runner_sha256":"14233AD2B40AD889CAB5CA9EE25A829D893009D61DD3EC914D9544EEC1B81F01",
    "reference_sha256":"74EE141B014DE7A9F9C401C2B3C5AF6BF72E5D7D80F49E67F9D9032338480165",
    "spec_sha256":"1609248D358CF65529475D6753181E4C9BBB19369E8852DD8DED1EEFE44FFCAD",
    "preflight_sha256":"CDC49F5E6AC1A1A43954D36F900CC8BE82EC8FCD7EF4A903515CC92A462EAE0F",
}
MANIFEST="TICKSTORE_GLOBAL_MANIFEST.json"
MANIFEST_SCHEMA="TICKSTORE_GLOBAL_MANIFEST_V003"
COMMIT_SCHEMA="TICKSTORE_DAY_COMMIT_V003"
TOTAL_DAYS=1550
TOTAL_ROWS=7049522162
FORMAT_ID="PTS2G001"
CODEC_ID="ZSTD9"
ROW_GROUP_TICKS=262144

class Blocked(RuntimeError):pass
def req(x,m):
    if not x:raise Blocked(m)
def sha_bytes(b):return hashlib.sha256(b).hexdigest().upper()
def sha_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
    return h.hexdigest().upper()
def strict_json(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise Blocked("JSON_DUPLICATE_KEY")
            d[k]=v
        return d
    def bad(x):raise Blocked("JSON_NONFINITE")
    return json.loads(raw.decode("utf-8"),object_pairs_hook=pairs,parse_constant=bad)
def load_ledger(path):
    raw=pathlib.Path(path).read_bytes();req(sha_bytes(raw)==LEDGER_SHA,"LEDGER_SHA")
    with zipfile.ZipFile(io.BytesIO(raw),"r") as z:
        req(z.testzip() is None,"LEDGER_CRC")
        days=list(csv.DictReader(io.StringIO(z.read("P4A_ALL_DAYS.csv").decode("utf-8-sig"))))
        months=list(csv.DictReader(io.StringIO(z.read("P4A_MONTHS.csv").decode("utf-8-sig"))))
    req(len(days)==TOTAL_DAYS and len({d["date_key"] for d in days})==TOTAL_DAYS,"LEDGER_DAY_SET")
    req(sum(int(d["rows"]) for d in days)==TOTAL_ROWS,"LEDGER_ROWS")
    req(len(months)==75 and len({m["month_id"] for m in months})==75,"LEDGER_MONTHS")
    return {d["date_key"]:d for d in days},{m["month_id"]:m for m in months}
def manifest_record_from_commit(commit,container_sha,container_bytes,commit_sha):
    o=commit["oracle"]
    return {"date_key":o["date_key"],"month_id":o["month_id"],"source_identity":o["source_identity"],
            "ledger_zip_sha256":o["ledger_zip_sha256"],"day_contract_sha256":o["day_contract_sha256"],
            "code_revision":o["code_revision"],"format_id":FORMAT_ID,"codec_id":CODEC_ID,
            "row_group_ticks":ROW_GROUP_TICKS,"semantic_sha256":o["semantic_sha256"],
            "offset_sha256":o["offset_sha256"],"container_sha256":container_sha,
            "container_bytes":container_bytes,"commit_sha256":commit_sha}
def verify(root,ledger):
    root=pathlib.Path(root);days,months=load_ledger(ledger)
    mp=root/MANIFEST;req(mp.is_file(),"MANIFEST_MISSING");mraw=mp.read_bytes();manifest=strict_json(mraw)
    req(manifest.get("schema")==MANIFEST_SCHEMA,"MANIFEST_SCHEMA")
    records=manifest.get("records");req(isinstance(records,dict) and set(records)==set(days),"MANIFEST_DATE_SET")
    expected={MANIFEST};expected_dirs={"WIN@N"}
    for key,c in days.items():
        month=c["month_id"];expected_dirs.add("WIN@N/"+month)
        expected.add(f"WIN@N/{month}/{key}.pts2g");expected.add(f"WIN@N/{month}/{key}.commit.json")
    actual=set();actual_dirs=set()
    for base,dirs,files in os.walk(root,followlinks=False):
        bp=pathlib.Path(base)
        for d in dirs:
            q=bp/d;req(not q.is_symlink(),"SYMLINK_DIR");actual_dirs.add(q.relative_to(root).as_posix())
        for f in files:
            q=bp/f;req(not q.is_symlink(),"SYMLINK_FILE");actual.add(q.relative_to(root).as_posix())
    req(actual==expected,"EXACT_FILE_NAMESPACE")
    req(actual_dirs==expected_dirs,"EXACT_DIRECTORY_NAMESPACE")
    rows=0;checked=0
    for key,c in sorted(days.items()):
        month=c["month_id"];cp=root/"WIN@N"/month/(key+".pts2g");kp=root/"WIN@N"/month/(key+".commit.json")
        ch=sha_file(cp);cb=cp.stat().st_size;kraw=kp.read_bytes();kh=sha_bytes(kraw);commit=strict_json(kraw)
        req(commit.get("schema")==COMMIT_SCHEMA,"COMMIT_SCHEMA:"+key)
        o=commit.get("oracle");req(isinstance(o,dict),"ORACLE_OBJECT:"+key)
        req(o.get("date_key")==key and o.get("month_id")==month,"ORACLE_DATE_MONTH:"+key)
        req(int(o.get("rows",-1))==int(c["rows"]),"ORACLE_ROWS:"+key)
        req(o.get("semantic_sha256")==c["semantic_sha256"].upper(),"ORACLE_SEMANTIC:"+key)
        req(o.get("offset_sha256")==c["offset_values_sha256"].upper(),"ORACLE_OFFSET:"+key)
        req(o.get("ledger_zip_sha256")==LEDGER_SHA,"ORACLE_LEDGER:"+key)
        req(o.get("format_id")==FORMAT_ID and o.get("codec_id")==CODEC_ID and int(o.get("row_group_ticks",-1))==ROW_GROUP_TICKS,"ORACLE_FORMAT:"+key)
        ids=o.get("runner_ids",{});runner=ids.get("runner_sha256") if isinstance(ids,dict) else None
        if runner==CORE_SHA:req(ids.get("reference_sha256")==REFERENCE_SHA,"ORACLE_RUNNER_IDS:"+key)
        elif runner==R8_CERTIFIED_RUNNER_IDS["runner_sha256"]:
            req(key in R8_CERTIFIED_DATES and ids==R8_CERTIFIED_RUNNER_IDS,"ORACLE_R8_CERTIFIED_PROVENANCE:"+key)
        else:raise Blocked("ORACLE_RUNNER_IDS:"+key)
        src=o.get("source_identity",{});mon=months[month]
        req(src.get("sha256")==mon["source_sha256"].upper() and int(src.get("size",-1))==int(mon["source_size"]),"ORACLE_SOURCE:"+key)
        req(commit.get("container_sha256")==ch and int(commit.get("container_bytes",-1))==cb,"COMMIT_CONTAINER:"+key)
        req(commit.get("semantic_sha256")==o["semantic_sha256"] and commit.get("offset_sha256")==o["offset_sha256"],"COMMIT_SEMANTICS:"+key)
        req(type(commit.get("published_unix_ns")) is int and commit["published_unix_ns"]>0,"COMMIT_TIMESTAMP:"+key)
        req(records[key]==manifest_record_from_commit(commit,ch,cb,kh),"MANIFEST_RECORD:"+key)
        rows+=int(c["rows"]);checked+=1
    req(checked==TOTAL_DAYS and rows==TOTAL_ROWS,"FINAL_COUNTS")
    return {"schema":"POSTFULL_INDEPENDENT_VERIFIER_V001","status":"PASS","days":checked,"rows":rows,
            "manifest_sha256":sha_bytes(mraw),"namespace_files":len(actual),"namespace_dirs":len(actual_dirs),
            "ledger_sha256":LEDGER_SHA,"engine_imported":False}
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--ledger",required=True);ap.add_argument("--root",required=True);ap.add_argument("--output",required=True);a=ap.parse_args()
    try:r=verify(a.root,a.ledger);pathlib.Path(a.output).write_text(json.dumps(r,indent=2,sort_keys=True),encoding="utf-8");print("POSTFULL_INDEPENDENT_VERIFIER=PASS");return 0
    except Exception as e:
        r={"schema":"POSTFULL_INDEPENDENT_VERIFIER_V001","status":"BLOCKED","reason":str(e)}
        pathlib.Path(a.output).write_text(json.dumps(r,indent=2,sort_keys=True),encoding="utf-8");print("POSTFULL_INDEPENDENT_VERIFIER=BLOCKED "+str(e));return 2
if __name__=="__main__":raise SystemExit(main())
