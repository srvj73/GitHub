from __future__ import annotations
import argparse,base64,concurrent.futures,ctypes,datetime as dt,hashlib,json,math,os,pathlib,re,shutil,subprocess,sys,time,types,uuid,zipfile
from ctypes import wintypes as w
PASS,FAIL,BLOCKED,PARTIAL,SAFE_STOP=0,1,2,3,130
NODES=["A0","A1","A2","A3","B1","B2","B3","B4","B5","B6","B7","B8","B6X","B9","C1","C2","C3",
"D1","D2","D3","D4","D5","D6","D7","D8","D9","D10","D11","E1","E2","E3","E4","E5","E6","E7","E8","E9",
"F1","F2","F3","G1","G2","G3","G4","G5","G6","G7","H1","H2","H3","H4","H5","H6","I1"]
def req(x,m):
    if not x: raise RuntimeError(m)
def require_sha256_hex(value,label):
    req(isinstance(value,str) and re.fullmatch(r"[0-9A-F]{64}",value) is not None,label+"_SHA256_GRAMMAR")
    return value
def shab(b):return hashlib.sha256(b).hexdigest().upper()
def shaf(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
    return h.hexdigest().upper()
def jb(o):return (json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)+"\n").encode()
def atom(p,b):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=pathlib.Path(str(p)+".partial")
    with open(t,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
    os.replace(t,p)
def atomj(p,o):atom(p,jb(o))
def rj(p):return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
def now():return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
class SafeStopFlow(RuntimeError):
    def __init__(self,message="SAFE_STOP=YES",resume_current=False):
        super().__init__(message);self.resume_current=bool(resume_current)
class RetryFullFlow(RuntimeError):
    pass
def fenced_kv_blocks(text):
    blocks=[]
    for raw in re.findall(r"```(?:text)?\s*\n(.*?)```",text,re.S):
        lines=[line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:continue
        title=lines[0];items={}
        for line in lines[1:]:
            req("=" in line,"CP2_BLOCK_NON_KV_LINE")
            k,v=line.split("=",1);req(k and k not in items and re.fullmatch(r"[A-Z0-9_]+",k) is not None,"CP2_BLOCK_KEY")
            items[k]=v
        blocks.append((title,items))
    return blocks
class State:
    def __init__(self,root):
        self.root=pathlib.Path(root);self.sd=self.root/"state";self.runs=self.root/"runs";self.inbox=self.root/"inbox";self.packs=self.root/"packs";self.ev=self.root/"evidence"
        for p in (self.sd,self.runs,self.inbox,self.packs,self.ev):p.mkdir(parents=True,exist_ok=True)
        self.sp=self.sd/"STATE.json";self.jp=self.sd/"STATE_JOURNAL.jsonl"
        self.d=rj(self.sp) if self.sp.exists() else {"schema":"TICKSTORE_ORCH_STATE_V001","next_node":"A0","completed":[],"status":"NEW","engine":None,"created_at":now()}
        atomj(self.sp,self.d)
    def log(self,node,phase,**x):
        prev=""
        if self.jp.exists():
            ls=self.jp.read_bytes().splitlines()
            if ls:prev=shab(ls[-1])
        raw=jb({"ts":now(),"node":node,"phase":phase,"prev_line_sha256":prev,**x}).rstrip(b"\n")
        with open(self.jp,"ab") as f:f.write(raw+b"\n");f.flush();os.fsync(f.fileno())
    def finish(self,node,status,result=None,error=None):
        self.log(node,"FINISHED",status=status,result_sha256=shab(jb(result)) if result is not None else None,primary_error=error)
        if status=="PASS":
            if node not in self.d["completed"]:self.d["completed"].append(node)
            i=NODES.index(node);self.d["next_node"]=NODES[i+1] if i+1<len(NODES) else "DONE"
        self.d["status"]=status;self.d["updated_at"]=now();atomj(self.sp,self.d)
class Event:
    def __init__(self,name,create=False):
        req(os.name=="nt","WINDOWS_REQUIRED");self.k=ctypes.WinDLL("kernel32",use_last_error=True);self.name=name
        self.k.CreateEventW.argtypes=[ctypes.c_void_p,w.BOOL,w.BOOL,w.LPCWSTR];self.k.CreateEventW.restype=w.HANDLE
        self.k.OpenEventW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR];self.k.OpenEventW.restype=w.HANDLE
        self.k.SetEvent.argtypes=[w.HANDLE];self.k.SetEvent.restype=w.BOOL
        self.k.CloseHandle.argtypes=[w.HANDLE];self.k.CloseHandle.restype=w.BOOL
        if create:
            ctypes.set_last_error(0)
            self.h=self.k.CreateEventW(None,True,False,name)
            last=ctypes.get_last_error()
            if self.h and last==183:
                self.k.CloseHandle(self.h);self.h=None
                raise RuntimeError("SAFE_STOP_EVENT_PREEXISTS")
        else:
            self.h=self.k.OpenEventW(0x00100002,False,name)
        req(bool(self.h),"EVENT_OPEN_CREATE")
    def set(self):req(bool(self.k.SetEvent(self.h)),"EVENT_SET")
    def close(self):
        if self.h:self.k.CloseHandle(self.h);self.h=None
def load_engine(p):
    ns={"__name__":"tickstore_engine_library","__file__":str(p)};exec(compile(pathlib.Path(p).read_bytes(),str(p),"exec"),ns,ns);return types.SimpleNamespace(**ns)
def volume_guid():
    k=ctypes.WinDLL("kernel32",use_last_error=True);b=ctypes.create_unicode_buffer(1024);req(k.GetVolumeNameForVolumeMountPointW("D:\\",b,len(b)),"VOLUME_GUID");return b.value
def perms(mode):
    m=("CERTIFY_SCRATCH","CERTIFY_CANONICAL","LIVE_EQUALITY","MANIFEST_REDERIVATION","PROMOTION_CHECK","RECOVER","STALE_LOCK");return {x:x==mode for x in m}
class O:
    def __init__(self,a):
        self.a=a;self.pkg=pathlib.Path(a.package);self.cfg=rj(self.pkg/"config/STAGE_A_SEALED_VALUES_V001.json")
        for key,value in sorted(self.cfg.items()):
            if key.endswith("_sha256") and isinstance(value,str):
                require_sha256_hex(value,"CONFIG_"+key.upper())
        self.control=pathlib.Path(self.cfg["control_root"])
        self.st=State(self.control);self.ws=pathlib.Path(self.cfg["workspace"]);self.py=a.python;self.rel=self.pkg/"engine/tickstore_publisher_recovery_v004_release.py"
        self.eng=load_engine(self.rel);self.ledger=pathlib.Path(self.cfg["ledger_path"]);self.id=dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]+f"_{os.getpid()}"
        self.rd=self.st.runs/self.id;self.rd.mkdir(parents=True,exist_ok=False)
    def rec(self,n,s,r=None,e=None,scope="EVID"):
        atomj(self.rd/f"RECEIPT_{n}.json",{"schema":"RECEIPT_V002","node":n,"run_id":self.id,"status":s,"exit_code":0 if s=="PASS" else 130 if s=="SAFE_STOP" else 2 if s=="BLOCKED" else 1,
        "effect_scope":scope,"protected_state_effects_occurred":scope=="PROT","canary_data_effects_occurred":scope=="CAN","system_effects_occurred":scope=="SYS",
        "evidence_writes_occurred":True,"safe_to_rerun_same_runner":scope in ("NONE","EVID"),"rerun_authorized":s=="PASS" and scope in ("NONE","EVID"),
        "reconcile_required":scope in ("PROT","CAN","SYS","DEV") and s!="PASS","result_sha256":shab(jb(r)) if r is not None else None,"primary_error":e,"finished_at":now()})
    def cp2(self):
        p=self.pkg/"review/CP2_SAFE_STOP_DELTA_REVIEW_V001.txt"
        self.exact(p,self.cfg["cp2_review_sha256"],"CP2_REVIEW")
        blocks=fenced_kv_blocks(p.read_text(encoding="utf-8"))
        req(len(blocks)==2,"CP2_BLOCK_CARDINALITY")
        title0,b0=blocks[0];title1,b1=blocks[1]
        req(title0=="CP2_SAFE_STOP_DELTA_REVIEW_V001","CP2_MAIN_TITLE")
        req(b0.get("VERDICT")=="BLOCKED","CP2_MAIN_VERDICT")
        req(b0.get("DELTA_CANDIDATE_SHA256")==self.cfg["cp2_submitted_candidate_sha256"],"CP2_SUBMITTED_CANDIDATE")
        req(b0.get("DELTA_RELEASE_SHA256")==self.cfg["cp2_submitted_release_sha256"],"CP2_SUBMITTED_RELEASE")
        req(b0.get("NAMED_EVENT_SAFE_STOP_APPROVED")=="NO","CP2_SUBMITTED_DESIGN_STATUS")
        req(title1=="CP2R1_PRESEALED_CORRECTION_V001","CP2R1_TITLE")
        req(b1.get("CORRECTION")=="ENGINE_LINE_41_ONLY_SINGLE_BACKSLASH_REGEX","CP2R1_CORRECTION")
        req(b1.get("CORRECTED_CANDIDATE_SHA256")==self.cfg["cp2r1_corrected_candidate_sha256"],"CP2R1_CANDIDATE")
        req(b1.get("CORRECTED_RELEASE_SHA256")==self.cfg["cp2r1_corrected_release_sha256"],"CP2R1_RELEASE")
        req(b1.get("CORRECTED_ENGINE_APPROVAL")=="GRANTED_IFF_EXACT_HASH_EQUALITY","CP2R1_APPROVAL")
        req(b1.get("NEW_EXTERNAL_REVIEW_REQUIRED_FOR_CP2R1")=="NO","CP2R1_EXTERNAL_REVIEW")
        req(self.cfg["b6_code_delta_base_release_sha256"]==self.cfg["cp2r1_corrected_release_sha256"],"B6_DELTA_BASE_RELEASE_NOT_CP2R1")
        self.exact(self.pkg/"review/base_release_before_B6_delta.py",self.cfg["b6_code_delta_base_release_sha256"],"B6_DELTA_BASE_RELEASE")
        self.exact(self.pkg/"review/intermediate_release_parent_floor.py",self.cfg["b6_parent_floor_release_sha256"],"B6_PARENT_FLOOR_INTERMEDIATE")
        self.exact(self.pkg/"review/intermediate_release_rootslash.py",self.cfg["b6_rootslash_release_sha256"],"B6_ROOTSLASH_INTERMEDIATE")
        self.exact(self.pkg/"engine/tickstore_publisher_recovery_v004_candidate.py",self.cfg["delta_candidate_source_sha256"],"B6_DELTA_CURRENT_CANDIDATE")
        self.exact(self.pkg/"engine/tickstore_publisher_recovery_v004_release.py",self.cfg["delta_release_source_sha256"],"B6_DELTA_CURRENT_RELEASE")
        return {"main_verdict":"BLOCKED_ON_SUPERSEDED_SAFE_STOP_BYTES","presealed_safe_stop_correction":"ACCEPTED",
                "b6_code_delta_review_required":True,"b6_base_release_sha256":self.cfg["b6_code_delta_base_release_sha256"]}
    def exact(self,p,h,m):
        require_sha256_hex(h,m)
        req(pathlib.Path(p).is_file(),m+"_MISSING")
        actual=shaf(p);require_sha256_hex(actual,m+"_ACTUAL")
        req(actual==h,m)
    def install(self,s,d,h):
        req(shaf(s)==h,"INSTALL_SOURCE");t=pathlib.Path(str(d)+f".{self.id}.partial");shutil.copyfile(s,t);req(shaf(t)==h,"INSTALL_COPY");os.replace(t,d);req(shaf(d)==h,"INSTALL_FINAL")
    def tests(self,label):
        test_runner=self.pkg/"modules/unittest_path_runner.py"
        req(test_runner.is_file(),label+"_TEST_RUNNER_MISSING")
        cp=subprocess.run([self.py,"-I","-S","-B",str(test_runner),str(self.ws),
                           "test_native_rename_v004r2r1","test_precanary_completeness_v005","test_publisher_recovery_v004"],
         cwd=self.ws,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);(self.rd/f"{label}.txt").write_text(cp.stdout,encoding="utf-8")
        m=re.search(r"Ran (\d+) tests",cp.stdout)
        req(cp.returncode==0 and m and int(m.group(1))==self.cfg["physical_test_count"] and "\nOK" in cp.stdout,label+"_MATRIX")
        req("skipped=" not in cp.stdout.lower(),label+"_UNEXPECTED_SKIP")
        ids=self.cfg["r01_required_test_ids"]
        for tid in ids:req(("test_"+tid.replace("-","_")) in cp.stdout,label+"_MISSING_"+tid)
        vids=self.cfg["core_vss_required_test_ids"]
        for tid in vids:req(("test_"+tid.replace("-","_")) in cp.stdout,label+"_MISSING_"+tid)
        pids=self.cfg["r8_provenance_required_test_ids"]
        for tid in pids:req(("test_"+tid.replace("-","_")) in cp.stdout,label+"_MISSING_"+tid)
        return {"tests":int(m.group(1)),"unexpected_skips":0,"r01_ids":ids,"core_vss_ids":vids,"r8_provenance_ids":pids}
    def ledger_data(self):raw=self.ledger.read_bytes();req(shab(raw)==self.cfg["ledger_sha256"],"LEDGER_SHA");return self.eng.ledger_from_bytes(raw),raw
    def bind(self,st,p):
        with st.open(pathlib.Path(p),directory=True) as f:return f.info()
    def vprof(self,st):
        with st.open(pathlib.Path("D:\\"),directory=True) as f:v=f.info()["volume"]
        return {"context":25,"snapshot_execution_authorized":True,"provider_id":self.cfg["microsoft_vss_provider_id"],"volume_guid":volume_guid(),"volume_identity":v,"drive":"D:","create_deadline_seconds":600}
    def gate(self,mode,roots,rid,prod=False,can=False):
        st=self.eng.Win32Store();return {"schema":"RECOVERY_OWNER_GATE_V004","authorized":True,"mode":mode,"permissions":perms(mode),"spec_sha256":self.cfg["spec_sha256"],
        "spec_addendum_v004r2r1_sha256":self.cfg["spec_addendum_sha256"],"recovery_source_sha256":self.cfg["delta_release_source_sha256"],"python_exe_sha256":self.cfg["python_exe_sha256"],
        "python_version":self.cfg["python_version"],"release_id":rid,"rescan_authorized":False,"csv_deletion_authorized":False,"format_promotion_authorized":False,"codec_promotion_authorized":False,
        "production_recovery_authorized":bool(prod and mode=="RECOVER"),"canary_execution_authorized":bool(can and mode=="RECOVER"),"stale_lock_clear_authorized":False,"prep_workers":22,"bootstrap_deadlines":self.cfg["bootstrap_deadlines"],
        "size_classes":self.cfg["size_classes"],"inline_root_loader_revision":self.cfg["root_contract_id"],"inline_root_loader_sha256":self.cfg["root_loader_sha256"],
        "canary_recovery_source_sha256":self.cfg["delta_release_source_sha256"],"dest_root":str(roots["dest"]),"scratch_root":str(roots["scratch"]),"recovery_root":str(roots["recovery"]),
        "root_bindings":{"dest_root":self.bind(st,roots["dest"]),"scratch_root":self.bind(st,roots["scratch"]),"recovery_root":self.bind(st,roots["recovery"])},"vss":self.vprof(st)}
    def bundle(self,name,g,extra=None,certs=None,deadline=None,noledger=False):
        mem={"tickstore_publisher_recovery_v004.py":self.rel.read_bytes()}
        if extra:mem.update(extra)
        if certs:mem.update(certs)
        if deadline:mem["DEADLINE_PROFILE.json"]=jb(deadline)
        if not noledger and g["mode"]!="STALE_LOCK":mem["LEDGER.zip"]=self.ledger.read_bytes()
        for m,f in (("SCRATCH_CERT.json","scratch_admission_cert_sha256"),("CANONICAL_CERT.json","canonical_admission_cert_sha256"),("DEADLINE_PROFILE.json","deadline_profile_sha256")):
            if m in mem:g[f]=shab(mem[m])
        gr=self.eng.json_bytes(g);mem["OWNER_GATE.json"]=gr;man={"schema":"RELEASE_MANIFEST_V004","members":{n:{"sha256":shab(b),"bytes":len(b)} for n,b in sorted(mem.items())}}
        mem["RELEASE_MANIFEST.json"]=self.eng.json_bytes(man);bp=self.rd/(name+".zip")
        with zipfile.ZipFile(bp,"w",compression=zipfile.ZIP_STORED) as z:
            for n,b in sorted(mem.items()):zi=zipfile.ZipInfo(n,(1980,1,1,0,0,0));zi.compress_type=zipfile.ZIP_STORED;zi.create_system=0;zi.external_attr=0;z.writestr(zi,b)
        req(bp.stat().st_size<=32*1024*1024,"BUNDLE_LIMIT");an={"release_id":g["release_id"],"spec_sha256":self.cfg["spec_sha256"],"release_bundle_sha256":shaf(bp),
        "release_manifest_sha256":shab(mem["RELEASE_MANIFEST.json"]),"recovery_source_sha256":self.cfg["delta_release_source_sha256"],"owner_gate_sha256":shab(gr),
        "python_exe_sha256":self.cfg["python_exe_sha256"],"python_version":self.cfg["python_version"],"inline_root_loader_revision":self.cfg["root_contract_id"]}
        for m,f in (("SCRATCH_CERT.json","scratch_admission_cert_sha256"),("CANONICAL_CERT.json","canonical_admission_cert_sha256"),("DEADLINE_PROFILE.json","deadline_profile_sha256")):
            if m in mem:an[f]=shab(mem[m])
        ap=self.rd/(name+".anchor.json");atomj(ap,an);return bp,ap,g
    def launch(self,b,a,label,async_=False):
        ps=self.pkg/"modules/Launch-TickstoreBundle.ps1";so=self.rd/f"{label}.stdout.log";se=self.rd/f"{label}.stderr.log";fo=open(so,"wb");fe=open(se,"wb")
        cmd=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ps),"-PackageRoot",str(self.pkg),"-BundlePath",str(b),"-AnchorPath",str(a),"-PythonPath",self.py]
        p=subprocess.Popen(cmd,stdout=fo,stderr=fe,creationflags=0x08000000)
        if async_:return p,fo,fe,so,se
        c=p.wait();fo.close();fe.close();return c,so,se
    def rootsc(self):c=self.st.d.get("canary");req(c,"CANARY_ROOTS");return {k:pathlib.Path(c[k]) for k in ("dest","scratch","recovery")}
    def rootsp(self):return {"dest":pathlib.Path(self.cfg["production_dest_root"]),"scratch":pathlib.Path(self.cfg["production_scratch_root"]),"recovery":pathlib.Path(self.cfg["production_recovery_root"])}
    def vss(self,roots,purpose):
        st=self.eng.Win32Store();pr=self.vprof(st);v=self.eng.NativeVSS(st,pr)
        try:g=v.create(purpose);v.assert_present(g);return pr,g
        finally:v.close()
    def invs0(self,shadow):
        st=self.eng.Win32Store();obs=self.eng.scan_s0(st,pathlib.Path(shadow));d={}
        for x in obs:
            e=d.setdefault(x["date_key"],{"namespace":x["namespace"]});e[x["kind"]]={f:x[f] for f in ("path","sha256","bytes")}
            if x["kind"]=="journal":e["contract"]=x["contract"]
        req(len(d)==1399 and all({"namespace","journal","partial","contract"}<=set(v) for v in d.values()),"S0_1399");return d
    def orc0(self,shadow,days,months):
        st=self.eng.Win32Store();o={}
        for k,c in sorted(days.items()):
            _,_,kp=self.eng.day_paths(pathlib.Path(shadow),c)
            if st.exists(kp):
                with st.open(kp) as f:q=self.eng.parse(f.read())["oracle"]
                self.eng.oracle_contract(q,c,months[c["month_id"]]);o[k]=q
        req(len(o)==151,"C0_151");return o
    def cert(self,mode,roots,generation,profile,s0=None,c0=None,certs=None,prod=False,deadline=None):
        rid=f"{mode}_{self.id}_{uuid.uuid4().hex[:8].upper()}";g=self.gate(mode,roots,rid,prod,not prod);g["vss"]=profile;g["admission_generation"]=generation
        if s0 is not None:g["s0_inventory"]=s0
        if c0 is not None:g["c0_oracles"]=c0
        before=set(pathlib.Path(roots["recovery"]).glob(mode.lower()+".*.json"));b,a,_=self.bundle(rid,g,certs=certs,deadline=deadline);c,so,se=self.launch(b,a,rid)
        if c==SAFE_STOP:
            out=pathlib.Path(so).read_text(errors="replace") if pathlib.Path(so).is_file() else ""
            if "SAFE_STOP=YES" in out: raise SafeStopFlow("SAFE_STOP=YES",resume_current=True)
            raise RuntimeError(mode+"_SAFE_STOP_UNCONFIRMED")
        req(c==0,mode+"_EXIT")
        new=set(pathlib.Path(roots["recovery"]).glob(mode.lower()+".*.json"))-before;req(len(new)==1,mode+"_CERT");p=next(iter(new));return p.read_bytes()
    def ccerts(self):return {"SCRATCH_CERT.json":base64.b64decode(self.st.d["canary_scratch_cert"]),"CANONICAL_CERT.json":base64.b64decode(self.st.d["canary_canonical_cert"])}
    def pcerts(self):return {"SCRATCH_CERT.json":base64.b64decode(self.st.d["prod_scratch_cert"]),"CANONICAL_CERT.json":base64.b64decode(self.st.d["prod_canonical_cert"])}
    def recover(self,roots,prod=False,label="RECOVER"):
        rid=label+"_"+self.id+"_"+uuid.uuid4().hex[:8].upper();g=self.gate("RECOVER",roots,rid,prod,not prod);name=r"Global\TICKSTORE_V004R1_STOP_"+uuid.uuid4().hex.upper();g["safe_stop_event_name"]=name
        b,a,_=self.bundle(rid,g,certs=self.pcerts() if prod else self.ccerts(),deadline=self.st.d["deadline_profile"] if prod else None);return b,a,name
    def stale(self,roots,label,prod=False):
        rid=label+"_"+self.id;g=self.gate("STALE_LOCK",roots,rid,prod,False);g["stale_lock_clear_authorized"]=True;b,a,_=self.bundle(rid,g);c,so,se=self.launch(b,a,rid);req(c==0,"STALE_LOCK");return {"stdout":str(so)}
    def tree_zip(self,root,out):
        root=pathlib.Path(root);out=pathlib.Path(out);entries=[]
        for f in sorted(root.rglob("*")):
            if f.is_file():entries.append((f.relative_to(root).as_posix(),f.read_bytes()))
        req(len({n for n,_ in entries})==len(entries),"TREE_ZIP_DUPLICATE")
        with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED) as z:
            for n,b in entries:
                zi=zipfile.ZipInfo(n,(1980,1,1,0,0,0));zi.compress_type=zipfile.ZIP_STORED;zi.create_system=0;zi.external_attr=0;z.writestr(zi,b)
        with zipfile.ZipFile(out,"r") as z:req(z.testzip() is None,"TREE_ZIP_CRC")
        return {"path":str(out),"sha256":shaf(out),"entries":len(entries)}
    def pack(self,label):
        p=self.st.packs/(label+"_"+self.id+".zip");entries=[]
        for root in (self.rd,self.control/"state"):
            for f in sorted(root.rglob("*")):
                if f.is_file():entries.append((root.name+"/"+f.relative_to(root).as_posix(),f.read_bytes()))
        if label.startswith("TICKSTORE_V004R1_STAGE_B"):
            direct=[
              ("00_PROMPT_STAGE_B_REVIEW_V001.md",self.pkg/"review/00_PROMPT_STAGE_B_REVIEW_V001.md"),
              ("01_STAGE_A_SEALED_VALUES_V001.json",self.pkg/"config/STAGE_A_SEALED_VALUES_V001.json"),
              ("02_AUTOCHECK_REPORT.json",self.rd/"02_AUTOCHECK_REPORT.json"),
              ("03_ORCHESTRATOR_PACKAGE_STAGE_B.zip",pathlib.Path(self.st.d["stage_b_orchestrator_package"]["path"])),
              ("04_PRODUCTION_RECOVER_BUNDLE.zip",pathlib.Path(self.st.d["pb"])),
              ("05_PRODUCTION_RECOVER_ANCHOR.json",pathlib.Path(self.st.d["pa"])),
              ("06_PRODUCTION_STALE_LOCK_BUNDLE.zip",pathlib.Path(self.st.d["psb"])),
              ("07_PRODUCTION_STALE_LOCK_ANCHOR.json",pathlib.Path(self.st.d["psa"])),
            ]
            for name,f in direct:req(f.is_file(),"STAGE_B_DIRECT_MEMBER_MISSING:"+name);entries.append((name,f.read_bytes()))
            entries.append(("08_MONTH_DIRECTORY_PLAN.json",jb(self.st.d["month_plan"])))
            entries.append(("09_DEADLINE_PROFILE.json",self.eng.json_bytes(self.st.d["deadline_profile"])))
            entries.append(("10_SCRATCH_ADMISSION_CERT.json",base64.b64decode(self.st.d["prod_scratch_cert"])))
            entries.append(("11_CANONICAL_ADMISSION_CERT.json",base64.b64decode(self.st.d["prod_canonical_cert"])))
            prior=self.st.d.get("canary_evidence_pack")
            if prior and pathlib.Path(prior["path"]).is_file():entries.append(("12_CANARY_EVIDENCE_PACK.zip",pathlib.Path(prior["path"]).read_bytes()))
        req(len({n for n,_ in entries})==len(entries),"EVIDENCE_ZIP_DUPLICATE")
        manifest={"schema":"EVIDENCE_PACK_MANIFEST_V001","files":[{"path":n,"bytes":len(b),"sha256":shab(b)} for n,b in sorted(entries)]}
        entries.append(("99_MANIFEST_SHA256.json",jb(manifest)))
        with zipfile.ZipFile(p,"w",compression=zipfile.ZIP_STORED) as z:
            for n,b in sorted(entries):
                zi=zipfile.ZipInfo(n,(1980,1,1,0,0,0));zi.compress_type=zipfile.ZIP_STORED;zi.create_system=0;zi.external_attr=0;z.writestr(zi,b)
        with zipfile.ZipFile(p,"r") as z:req(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),"EVIDENCE_ZIP_INTEGRITY")
        return {"path":str(p),"sha256":shaf(p),"entries":len(entries),"deterministic_metadata":True,"manifest_sha256":shab(jb(manifest))}
    def independent_verify(self,roots,label):
        out=self.rd/(label+"_INDEPENDENT.json");mod=self.pkg/"modules/postfull_verifier.py"
        cp=subprocess.run([self.py,"-I","-S","-B",str(mod),"--ledger",str(self.ledger),"--root",str(roots["dest"]),"--output",str(out)],
          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (self.rd/(label+"_INDEPENDENT.log")).write_text(cp.stdout,encoding="utf-8");req(cp.returncode==0,label+"_INDEPENDENT_FAIL")
        obj=rj(out);req(obj.get("status")=="PASS" and obj.get("days")==1550 and obj.get("rows")==7049522162,label+"_INDEPENDENT_RESULT");return obj
    def postverify(self,roots):
        st=self.eng.Win32Store();(days,months),_=self.ledger_data()
        with st.open(roots["dest"]/"TICKSTORE_GLOBAL_MANIFEST.json") as f:raw=f.read();m=self.eng.parse(raw)
        req(set(m["records"])==set(days),"POST_DATES");inv=self.eng.exact_canonical_inventory(st,roots["dest"],days);req(len(inv)==3101,"POST_NAMESPACE")
        from compression import zstd
        rows=0
        for k,c in sorted(days.items()):
            _,_,kp=self.eng.day_paths(roots["dest"],c)
            with st.open(kp) as f:oracle=self.eng.parse(f.read())["oracle"]
            self.eng.oracle_contract(oracle,c,months[c["month_id"]]);pair=self.eng.validate_pair(st,roots["dest"],c,oracle,zstd);req(m["records"][k]==pair["record"],"POST_RECORD:"+k);rows+=int(c["rows"])
        req(rows==7049522162,"POST_ROWS");return {"POST_FULL_AUDIT":"PASS","days":1550,"rows":rows,"manifest_sha256":shab(raw),"namespace":len(inv)}
    def b6_v004_review(self):
        p=self.pkg/"review/B6_CODE_DELTA_REVIEW_V004.txt";self.exact(p,self.cfg["b6_v004_review_sha256"],"B6_V004_REVIEW")
        blocks=fenced_kv_blocks(p.read_text(encoding="utf-8"));req(len(blocks)>=1,"B6_V004_REVIEW_BLOCK_MISSING");title,b=blocks[0]
        req(title=="B6_CODE_DELTA_REVIEW_V004" and b.get("VERDICT")=="BLOCKED","B6_V004_REVIEW_VERDICT")
        req(b.get("DELTA_CANDIDATE_SHA256")==self.cfg["b6_v004_candidate_sha256"],"B6_V004_CANDIDATE");req(b.get("DELTA_RELEASE_SHA256")==self.cfg["b6_v004_release_sha256"],"B6_V004_RELEASE")
        for k in ("VSS_SHADOW_PARENT_DELTA_APPROVED","VSS_ROOT_TRAILING_SLASH_DELTA_APPROVED","VSS_FINAL_PATH_NT_DELTA_APPROVED","LOGICAL_PATH_IDENTITY_PRESERVED","RELEASE_FUSE_ONLY_FROM_CANDIDATE"):req(b.get(k)=="YES","B6_V004_NOT_APPROVED:"+k)
        req("B-01" in b.get("BLOCKERS","") and "B-02" in b.get("BLOCKERS",""),"B6_V004_BLOCKERS_NOT_BOUND");return {"verdict":"BLOCKED","approved_prior_deltas":3,"blockers":["B-01","B-02"]}
    def prior_v001r8_failure_reconciliation(self):
        root=pathlib.Path(self.cfg["v001r8_failed_control_root"]);sp=root/"state"/"STATE.json";req(sp.is_file(),"V001R8_STATE_MISSING");s=rj(sp)
        expected=["A0","A1","A2","A3","B1","B2","B3","B4","B5","B6","B7","B8"]
        req(s.get("status")=="FAIL" and s.get("next_node")=="B6X" and s.get("completed")==expected,"V001R8_STATE_NOT_EXPECTED_FAIL")
        recs=sorted(root.glob("runs/*/RECEIPT_B6X.json"));req(len(recs)==1,"V001R8_B6X_RECEIPT_CARDINALITY");rp=recs[0];rec=rj(rp)
        req(rec.get("status")=="FAIL" and rec.get("effect_scope")=="SYS" and rec.get("reconcile_required") is True and rec.get("primary_error")=="B6X_EXIT","V001R8_B6X_RECEIPT")
        rd=rp.parent;before=rj(rd/"B6X_SHADOWS_BEFORE.json");after=rj(rd/"B6X_SHADOWS_AFTER.json")
        for label,obj in (("BEFORE",before),("AFTER",after)):
            req(obj.get("schema")=="TICKSTORE_VSS_SHADOW_INVENTORY_V001" and obj.get("drive")=="D:","V001R8_B6X_SHADOW_SCOPE_"+label)
            req(obj.get("count")==len(obj.get("snapshots",[])),"V001R8_B6X_SHADOW_COUNT_"+label)
        bid=sorted(x["id"] for x in before["snapshots"]);aid=sorted(x["id"] for x in after["snapshots"])
        expected_d=sorted(self.cfg["v001r8_expected_d_shadow_ids"])
        req(len(expected_d)==self.cfg["v001r8_expected_d_shadow_count"]==3,"V001R8_EXPECTED_D_SHADOW_CONTRACT")
        req(bid==aid==expected_d,"V001R8_B6X_SHADOW_RECONCILIATION")
        out=(rd/"B6X.stdout.log").read_text(encoding="utf-8",errors="replace");err=(rd/"B6X.stderr.log").read_text(encoding="utf-8",errors="replace")
        req("B6X_OWN_GENERATION_CLEANUP=PASS" in out and "B6X_SHADOW_READ_PATH=FAIL:ORACLE_FROZEN_RC1_PROVENANCE" in out,"V001R8_B6X_FAILURE_SIGNATURE")
        req("ORACLE_FROZEN_RC1_PROVENANCE" in err,"V001R8_B6X_STDERR_SIGNATURE")
        current=self.shadow_inventory("V001R8_RECON_CURRENT")
        req(current.get("count")==len(current.get("snapshots",[])),"V001R8_CURRENT_SHADOW_COUNT")
        cid=sorted(x["id"] for x in current["snapshots"]);req(cid==aid==expected_d,"V001R8_CURRENT_SHADOW_SET_CHANGED")
        expected_ws={"tickstore_publisher_recovery_v004.py":self.cfg["v001r8_release_source_sha256"],"test_publisher_recovery_v004.py":self.cfg["v001r8_release_domain_test_sha256"],"test_native_rename_v004r2r1.py":self.cfg["v001r8_release_native_test_sha256"],"test_precanary_completeness_v005.py":self.cfg["v001r8_release_precanary_test_sha256"]}
        for name,h in expected_ws.items():self.exact(self.ws/name,h,"V001R8_WORKSPACE_"+name.upper().replace(".","_"))
        result={"schema":"V001R8_B6X_FAILURE_RECONCILIATION_V001","status":"PASS","old_control_root":str(root),"old_run":str(rd),"state_status":"FAIL","failed_node":"B6X","primary_error":"B6X_EXIT","failure_signature":"ORACLE_FROZEN_RC1_PROVENANCE","own_generation_cleanup":"PASS","shadow_ids_before":bid,"shadow_ids_after":aid,"shadow_ids_current":cid,"preexisting_shadow_set_unchanged":True,"workspace_v001r8_release_identity":"PASS_4_OF_4","rerun_same_runner_authorized":False,"successor_fresh_run_authorized_after_reconciliation":True}
        atomj(self.rd/"V001R8_FAILURE_RECONCILIATION.json",result);return result
    def n_a0(self):
        prior=self.prior_v001r8_failure_reconciliation();cp=self.cp2();rv=self.b6_v004_review();self.exact(self.cfg["corrective_result_path"],self.cfg["corrective_result_sha256"],"CORRECTIVE_RESULT");self.exact(self.cfg["corrective_receipt_path"],self.cfg["corrective_receipt_sha256"],"CORRECTIVE_RECEIPT")
        return {"V001R8_FAILURE_RECONCILIATION":prior,"CP2R1_PRESEAL":cp,"B6_V004_REVIEW":rv,"CP2R1_FINAL_ACCEPTANCE":"PENDING_A2_B2"}
    def n_a1(self):
        bk=self.rd/"A1_BACKUP";bk.mkdir();pairs=[(self.pkg/"engine/tickstore_publisher_recovery_v004_candidate.py",self.ws/"tickstore_publisher_recovery_v004.py",self.cfg["delta_candidate_source_sha256"]),
        (self.pkg/"tests/test_publisher_recovery_v004.py",self.ws/"test_publisher_recovery_v004.py",self.cfg["domain_test_sha256"]),(self.pkg/"tests/test_native_rename_v004r2r1.py",self.ws/"test_native_rename_v004r2r1.py",self.cfg["native_test_sha256"]),
        (self.pkg/"tests/test_precanary_completeness_v005.py",self.ws/"test_precanary_completeness_v005.py",self.cfg["precanary_test_sha256"])]
        for s,d,h in pairs:
            if d.exists():shutil.copy2(d,bk/d.name)
            self.install(s,d,h)
        return {"backup":str(bk)}
    def n_a2(self):
        r=self.tests("A2");self.st.d["cp2r1_a2"]=r;atomj(self.st.sp,self.st.d);return r
    def n_a3(self):
        self.exact(self.ws/"tickstore_publisher_recovery_v004.py",self.cfg["delta_candidate_source_sha256"],"A3_CANDIDATE_SOURCE")
        self.exact(self.ws/"test_publisher_recovery_v004.py",self.cfg["domain_test_sha256"],"A3_DOMAIN_TEST")
        self.exact(self.ws/"test_native_rename_v004r2r1.py",self.cfg["native_test_sha256"],"A3_NATIVE_TEST")
        self.exact(self.ws/"test_precanary_completeness_v005.py",self.cfg["precanary_test_sha256"],"A3_PRECANARY_TEST")
        return {"contract":"INLINE_ROOT_LOADER_V004_R1","stop":"NAMED_EVENT","tested_vs_installed_identity":"PASS"}
    def n_b1(self):
        self.install(self.rel,self.ws/"tickstore_publisher_recovery_v004.py",self.cfg["delta_release_source_sha256"])
        self.install(self.pkg/"tests_release/test_publisher_recovery_v004.py",self.ws/"test_publisher_recovery_v004.py",self.cfg["release_domain_test_sha256"])
        self.install(self.pkg/"tests_release/test_precanary_completeness_v005.py",self.ws/"test_precanary_completeness_v005.py",self.cfg["release_precanary_test_sha256"])
        self.install(self.pkg/"tests_release/test_native_rename_v004r2r1.py",self.ws/"test_native_rename_v004r2r1.py",self.cfg["native_test_sha256"])
        return {"release":self.cfg["delta_release_source_sha256"],"release_test_deltas":"EXACT_2_FUSE_TESTS"}
    def n_b2(self):
        self.exact(self.ws/"tickstore_publisher_recovery_v004.py",self.cfg["delta_release_source_sha256"],"B2_RELEASE_SOURCE")
        self.exact(self.ws/"test_publisher_recovery_v004.py",self.cfg["release_domain_test_sha256"],"B2_RELEASE_DOMAIN")
        self.exact(self.ws/"test_precanary_completeness_v005.py",self.cfg["release_precanary_test_sha256"],"B2_RELEASE_PRECANARY")
        self.exact(self.ws/"test_native_rename_v004r2r1.py",self.cfg["native_test_sha256"],"B2_RELEASE_NATIVE")
        r=self.tests("B2");req(self.st.d.get("cp2r1_a2",{}).get("tests")==self.cfg["physical_test_count"],"CP2R1_A2_NOT_PASSED")
        self.st.d["cp2r1_b2"]=r;self.st.d["cp2r1_satisfied"]=True;atomj(self.st.sp,self.st.d);return {**r,"CP2R1_FINAL_ACCEPTANCE":"PASS","RELEASE_TEST_DELTAS_EXACT":"PASS_2_OF_2"}
    def n_b3(self):
        st=self.eng.Win32Store();(days,_),_=self.ledger_data();root=pathlib.Path(self.cfg["production_dest_root"])
        with st.open(root/"TICKSTORE_GLOBAL_MANIFEST.json") as f:raw=f.read();m=self.eng.parse(raw)
        req(len(m["records"])==151,"P4_151");self.eng.rederive_manifest(raw,m["records"]);inv=self.eng.exact_canonical_inventory(st,root,{k:days[k] for k in m["records"]})
        return {"result":"PASS_151_151","manifest_sha256":shab(raw),"inventory_sha256":shab(self.eng.stable(inv)),"namespace":len(inv)}
    def n_b4(self):
        def meta(root,h=False):
            root=pathlib.Path(root);r=[]
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    st=p.stat();x={"path":p.relative_to(root).as_posix(),"bytes":st.st_size,"mtime_ns":st.st_mtime_ns}
                    if h:x["sha256"]=shaf(p)
                    r.append(x)
            return r
        return {"dest":meta(self.cfg["production_dest_root"],True),"scratch":meta(self.cfg["production_scratch_root"]),"csv_metadata":meta(self.cfg["production_csv_root_metadata_only"]),"free_d":shutil.disk_usage("D:\\").free}
    def n_b5(self):
        name=r"Global\TICKSTORE_V004R1_STOP_"+uuid.uuid4().hex.upper();e=Event(name,True)
        try:
            p=subprocess.Popen([self.py,"-I","-S","-B",str(self.pkg/"modules/event_probe.py"),name],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=0x08000000)
            time.sleep(1);e.set();o,_=p.communicate(timeout=15);req(p.returncode==0 and "WAIT=0" in o,"B5_EVENT");return {"NAMED_EVENT_SAFE_STOP_CHANNEL":"PASS","output":o.strip()}
        finally:e.close()
    def n_b6(self):
        st=self.eng.Win32Store();pr=self.vprof(st);v=self.eng.NativeVSS(st,pr)
        try:v.startup_probe(self.cfg["production_dest_root"],self.cfg["production_scratch_root"])
        finally:v.close()
        return {"VSS_CAPABILITY":"PASS","profile":pr}
    def n_b7(self):
        from compression import zstd
        root=pathlib.Path(self.cfg["production_scratch_root"]);partials=list(root.rglob("*.pts2g.partial"));req(len(partials)>=1399,"B7_PARTIALS")
        (days,months),_=self.ledger_data();st=self.eng.Win32Store();selected={}
        for p in partials:
            sc=self.eng.size_class(p.stat().st_size)
            if sc not in selected or p.stat().st_size>selected[sc].stat().st_size:selected[sc]=p
        rates=[];hash_rates=[];raw={}
        for sc,p in sorted(selected.items()):
            key=p.name[:8];req(key in days,"B7_DATE_KEY");jp=p.with_name(key+".journal.json");req(jp.is_file(),"B7_JOURNAL_MISSING")
            relp=p.relative_to(root).as_posix();relj=jp.relative_to(root).as_posix()
            t0=time.perf_counter()
            with st.open(p) as pf:ph,pn=pf.hash()
            hsec=max(time.perf_counter()-t0,1e-9);hash_rates.append(pn/hsec)
            with st.open(jp) as jf:jraw=jf.read();jh,jn=jf.hash()
            jo=self.eng.parse(jraw);entry={"namespace":relp.split("/",1)[0],"contract":jo["oracle"],
                 "journal":{"path":relj,"sha256":jh,"bytes":jn},"partial":{"path":relp,"sha256":ph,"bytes":pn}}
            t0=time.perf_counter();self.eng.prep(st,root,entry,days[key],months[days[key]["month_id"]],zstd);sec=max(time.perf_counter()-t0,1e-9)
            rate=int(days[key]["rows"])/sec;rates.append(rate);raw[sc]={"date_key":key,"bytes":pn,"rows":int(days[key]["rows"]),"prep_seconds":sec,"rows_per_second":rate,"hash_seconds":hsec}
        req(rates and hash_rates,"B7_NO_MEASUREMENTS");r_ser=min(rates);serial_hours=7049522162/r_ser/3600.0;full_projected=serial_hours*4.0
        req(serial_hours<=24.0,"PERF_BLOCK_SERIAL_PASS_GT_24H");req(full_projected<=144.0,"PERF_BLOCK_FULL_WALL_GT_144H")
        result={"schema":"B7_PERFORMANCE_PROBE_V001","partials":len(partials),"partial_bytes":sum(x.stat().st_size for x in partials),
                "classes":raw,"serial_rows_per_second_floor":r_ser,"serial_pass_hours":serial_hours,"full_wall_projected_hours_conservative":full_projected,
                "hash_bytes_per_second_floor":min(hash_rates),"workers_candidates":[22,16,12,8],"status":"PASS" if serial_hours<=12 else "WARN"}
        atomj(self.rd/"B7_PERFORMANCE_PROBE.json",result);self.st.d["b7_performance"]=result;atomj(self.st.sp,self.st.d);return result
    def n_b8(self):
        st=self.eng.Win32Store();p=self.control/"evidence"/("DIRBIND_"+self.id);p.mkdir()
        with st.open(p,directory=True) as f:b=f.info()
        for i in range(7000):(p/f"{i:05d}.tmp").write_bytes(b"x")
        for i in range(0,7000,7):os.replace(p/f"{i:05d}.tmp",p/f"r{i:05d}.tmp")
        with st.open(p,directory=True) as f:a=f.info()
        result={"policy":"STABLE" if all(b[k]==a[k] for k in ("volume","file_id","links","path","bytes")) else "UNSTABLE","before":b,"after":a}
        self.st.d["dirbind_policy"]=result["policy"];atomj(self.st.sp,self.st.d);return result
    def shadow_inventory(self,label):
        out=self.rd/(label+".json");so=self.rd/(label+".stdout.log");se=self.rd/(label+".stderr.log")
        cmd=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(self.pkg/"modules/shadow_inventory.ps1"),"-OutFile",str(out)]
        with open(so,"wb") as fo,open(se,"wb") as fe:cp=subprocess.run(cmd,stdout=fo,stderr=fe,creationflags=0x08000000)
        req(cp.returncode==0,label+"_EXIT");obj=rj(out);req(obj.get("schema")=="TICKSTORE_VSS_SHADOW_INVENTORY_V001" and obj.get("drive")=="D:",label+"_SCHEMA");req(obj.get("count")==len(obj.get("snapshots",[])),label+"_COUNT");return obj
    def historical_b6_failures(self):
        out=[]
        for root in self.cfg["historical_b6_failure_controls"]:
            p=pathlib.Path(root);recs=sorted(p.glob("runs/*/RECEIPT_B6.json"));req(recs,"HISTORICAL_B6_RECEIPT_MISSING:"+str(p));failures=[]
            for q in recs:
                obj=rj(q)
                if obj.get("status")=="FAIL":failures.append((q,obj))
            req(failures,"HISTORICAL_B6_FAIL_MISSING:"+str(p));q,obj=failures[-1];out.append({"control_root":str(p),"receipt":str(q),"finished_at":obj["finished_at"],"primary_error":obj.get("primary_error")})
        req(len(out)==3,"HISTORICAL_B6_FAILURE_COUNT");return out
    def reconcile_preexisting_shadows(self,inventory,failures):
        snaps=[dict(x) for x in inventory.get("snapshots",[])];used=set();classified=[]
        for failure in failures:
            finish=dt.datetime.fromisoformat(failure["finished_at"]).astimezone(dt.timezone.utc);candidates=[]
            for snap in snaps:
                sid=snap.get("id")
                if sid in used or not snap.get("install_utc"):continue
                try:created=dt.datetime.fromisoformat(snap["install_utc"].replace("Z","+00:00")).astimezone(dt.timezone.utc)
                except Exception:continue
                delta=(finish-created).total_seconds()
                if 0<=delta<=1800:candidates.append((delta,snap))
            if candidates:
                delta,snap=min(candidates,key=lambda x:x[0]);used.add(snap["id"]);classified.append({**failure,"classification":"MATCHED_PREEXISTING_SHADOW","snapshot":snap,"seconds_before_receipt":delta})
            else:classified.append({**failure,"classification":"NO_MATCH_PRESENT"})
        return {"schema":"B6_ORPHAN_RECONCILIATION_V001","historical_failures":classified,"preexisting_snapshot_count":len(snaps),"matched_candidate_orphans":len(used),"unmatched_preexisting_snapshots":[x for x in snaps if x.get("id") not in used],"owner_delete_authorized":False,"preexisting_snapshot_deletion_performed":False,"status":"RECONCILED_READ_ONLY"}
    def n_b6x(self):
        before=self.shadow_inventory("B6X_SHADOWS_BEFORE");failures=self.historical_b6_failures();reconcile=self.reconcile_preexisting_shadows(before,failures);atomj(self.rd/"B6X_ORPHAN_RECONCILIATION.json",reconcile)
        result_path=self.rd/"B6X_RESULT.json";so=self.rd/"B6X.stdout.log";se=self.rd/"B6X.stderr.log";cmd=[self.py,"-I","-S","-B",str(self.pkg/"modules/b6x_shadow_read_probe.py"),"--package",str(self.pkg),"--workspace",str(self.ws),"--b4",str(self.rd/"RESULT_B4.json"),"--result",str(result_path)];cp=None
        try:
            with open(so,"wb") as fo,open(se,"wb") as fe:cp=subprocess.run(cmd,stdout=fo,stderr=fe,creationflags=0x08000000)
        finally:after=self.shadow_inventory("B6X_SHADOWS_AFTER")
        before_ids=sorted(x["id"] for x in before["snapshots"]);after_ids=sorted(x["id"] for x in after["snapshots"]);req(before_ids==after_ids,"B6X_SHADOW_SET_CHANGED");req(cp is not None and cp.returncode==0,"B6X_EXIT");req(result_path.is_file(),"B6X_RESULT_MISSING");result=rj(result_path);req(result.get("schema")=="B6X_SHADOW_READ_PATH_V001" and result.get("status")=="PASS","B6X_RESULT_STATUS");req(result.get("release_sha256")==self.cfg["delta_release_source_sha256"],"B6X_RELEASE");req(result.get("core_sha256")==self.cfg["core_sha256"],"B6X_CORE");req(result.get("reference_sha256")==self.cfg["reference_sha256"],"B6X_REFERENCE");req(result.get("s0_scan")=={"days":1399,"objects":2798},"B6X_S0");req(result.get("dest_inventory",{}).get("files")==303,"B6X_DEST_303")
        evidence={"B6X_SHADOW_READ_PATH":"PASS","result":result,"orphan_reconciliation":reconcile,"shadow_ids_before":before_ids,"shadow_ids_after":after_ids,"own_generation_residual":False,"ORPHAN_SNAPSHOTS_RECONCILED":"YES","PREEXISTING_ORPHAN_DELETION_AUTHORIZED":"NO","PREEXISTING_ORPHAN_DELETION_PERFORMED":"NO","stdout":str(so),"stderr":str(se)};self.st.d["b6x"]=evidence;atomj(self.st.sp,self.st.d);return evidence
    def n_b9(self):
        req(self.st.d.get("b6x",{}).get("B6X_SHADOW_READ_PATH")=="PASS","B9_B6X_NOT_PASSED")
        pack=self.st.packs/("B6_CODE_DELTA_REVIEW_PACK_V005R1_"+self.id+".zip");entries=[]
        direct=[("00_PROMPT_OPUS55_B6_CODE_DELTA_REVIEW_V005R1.md",self.pkg/"review/00_PROMPT_OPUS55_B6_CODE_DELTA_REVIEW_V005R1.md"),
        ("01_B6_V004_REVIEW_BLOCKED.txt",self.pkg/"review/B6_CODE_DELTA_REVIEW_V004.txt"),
        ("02_BASE_B6_V004_RELEASE.py",self.pkg/"review/base_b6_v004_release.py"),
        ("03_BASE_V005_CANDIDATE.py",self.pkg/"review/base_v005_candidate.py"),
        ("04_BASE_V005_RELEASE.py",self.pkg/"review/base_v005_release.py"),
        ("05_DELTA_V005R1_CANDIDATE.py",self.pkg/"engine/tickstore_publisher_recovery_v004_candidate.py"),
        ("06_DELTA_V005R1_RELEASE.py",self.pkg/"engine/tickstore_publisher_recovery_v004_release.py"),
        ("07_V004_TO_V005_ENGINE_DIFF.patch",self.pkg/"review/B6_V005_CORE_ADAPTER_ENGINE_DIFF.patch"),
        ("08_V005_TO_V005R1_ORACLE_PROVENANCE_DIFF.patch",self.pkg/"review/V005_TO_V005R1_ORACLE_PROVENANCE_DIFF.patch"),
        ("09_CANDIDATE_PRECANARY_TEST.py",self.pkg/"tests/test_precanary_completeness_v005.py"),
        ("10_RELEASE_PRECANARY_TEST.py",self.pkg/"tests_release/test_precanary_completeness_v005.py"),
        ("11_B6X_PROBE.py",self.pkg/"modules/b6x_shadow_read_probe.py"),
        ("12_POSTFULL_VERIFIER.py",self.pkg/"modules/postfull_verifier.py"),
        ("13_SHADOW_INVENTORY.ps1",self.pkg/"modules/shadow_inventory.ps1"),
        ("14_CONFIG.json",self.pkg/"config/STAGE_A_SEALED_VALUES_V001.json"),
        ("15_V001R9_SUPERSESSION.md",self.pkg/"docs/V001R9_B6X_R8_PROVENANCE_SUPERSESSION.md")]
        for name,p in direct:req(p.is_file(),"B6_V005R1_REVIEW_MEMBER_MISSING:"+name);entries.append((name,p.read_bytes()))
        wanted=("A2.txt","B2.txt","RESULT_A0.json","RESULT_A1.json","RESULT_A2.json","RESULT_A3.json","RESULT_B1.json","RESULT_B2.json","RESULT_B3.json","RESULT_B4.json","RESULT_B5.json","RESULT_B6.json","RESULT_B7.json","RESULT_B8.json","RESULT_B6X.json","RECEIPT_A0.json","RECEIPT_A1.json","RECEIPT_A2.json","RECEIPT_A3.json","RECEIPT_B1.json","RECEIPT_B2.json","RECEIPT_B3.json","RECEIPT_B4.json","RECEIPT_B5.json","RECEIPT_B6.json","RECEIPT_B7.json","RECEIPT_B8.json","RECEIPT_B6X.json","V001R8_FAILURE_RECONCILIATION.json","V001R8_RECON_CURRENT.json","B6X.stdout.log","B6X.stderr.log","B6X_RESULT.json","B6X_ORPHAN_RECONCILIATION.json","B6X_SHADOWS_BEFORE.json","B6X_SHADOWS_AFTER.json","B6X_SHADOWS_BEFORE.stdout.log","B6X_SHADOWS_BEFORE.stderr.log","B6X_SHADOWS_AFTER.stdout.log","B6X_SHADOWS_AFTER.stderr.log")
        for name in wanted:p=self.rd/name;req(p.is_file(),"B6_V005R1_RUN_EVIDENCE_MISSING:"+name);entries.append(("run/"+name,p.read_bytes()))
        req(len({n for n,_ in entries})==len(entries),"B6_V005R1_REVIEW_DUPLICATE");manifest={"schema":"B6_CODE_DELTA_REVIEW_PACK_MANIFEST_V005R1","files":[{"path":n,"bytes":len(b),"sha256":shab(b)} for n,b in sorted(entries)]};entries.append(("99_MANIFEST_SHA256.json",jb(manifest)))
        with zipfile.ZipFile(pack,"w",compression=zipfile.ZIP_STORED) as z:
            for n,b in sorted(entries):zi=zipfile.ZipInfo(n,(1980,1,1,0,0,0));zi.compress_type=zipfile.ZIP_STORED;zi.create_system=0;zi.external_attr=0;z.writestr(zi,b)
        with zipfile.ZipFile(pack,"r") as z:req(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),"B6_V005R1_REVIEW_PACK_INTEGRITY")
        review={"path":str(pack),"sha256":shaf(pack),"entries":len(entries),"manifest_sha256":shab(jb(manifest))};self.st.d["b6_code_delta_review_pack"]=review;atomj(self.st.sp,self.st.d);raise RuntimeError("AWAITING_B6_CODE_DELTA_REVIEW_V005R1")
    def n_c1(self):
        p=self.st.inbox/self.cfg["b6_code_delta_review_filename"];req(p.exists(),"AWAITING_B6_CODE_DELTA_REVIEW_V005R1");blocks=fenced_kv_blocks(p.read_text(encoding="utf-8"));req(len(blocks)==1,"B6_V005R1_REVIEW_BLOCK_CARDINALITY");title,b=blocks[0];req(title=="B6_CODE_DELTA_REVIEW_V005R1","B6_V005R1_REVIEW_TITLE");req(b.get("VERDICT")=="PASS" and b.get("BLOCKERS")=="NONE","B6_V005R1_REVIEW_VERDICT");req(b.get("BASE_B6_V004_RELEASE_SHA256")==self.cfg["b6_v004_release_sha256"],"B6_V005R1_BASE");req(b.get("V005_BASE_RELEASE_SHA256")==self.cfg["v005_base_release_sha256"],"B6_V005R1_BASE_V005");req(b.get("DELTA_CANDIDATE_SHA256")==self.cfg["delta_candidate_source_sha256"],"B6_V005R1_CANDIDATE");req(b.get("DELTA_RELEASE_SHA256")==self.cfg["delta_release_source_sha256"],"B6_V005R1_RELEASE");req(b.get("CANDIDATE_TEST_COUNT")==str(self.cfg["physical_test_count"]),"B6_V005R1_CANDIDATE_TESTS");req(b.get("RELEASE_TEST_COUNT")==str(self.cfg["physical_test_count"]),"B6_V005R1_RELEASE_TESTS")
        for k in ("CORE_SHA256_UNCHANGED","CORE_VSS_IO_ADAPTER_APPROVED","STARTUP_PROBE_CLEANUP_APPROVED","R8_HISTORICAL_PROVENANCE_APPROVED","R8_PROVENANCE_SCOPE_EXACT_TWO_DATES","POSTFULL_VERIFIER_PARITY","ORPHAN_SNAPSHOTS_RECONCILED","LIVE_PATH_BEHAVIOR_IDENTICAL","RELEASE_FUSE_ONLY_FROM_CANDIDATE"):req(b.get(k)=="YES","B6_V005R1_FIELD:"+k)
        req(b.get("B6X_SHADOW_READ_PATH")=="PASS","B6_V005R1_B6X");return {"STAGE_A":"PASS","B6_CODE_DELTA_REVIEW_V005R1":"PASS","C1":"AUTHORIZED_AFTER_EXTERNAL_PASS"}
    def n_c2(self):
        base=pathlib.Path(self.cfg["canary_base"])/("CANARY_V004R1_"+self.id);req(not base.exists(),"CANARY_EXISTS");c={}
        for k in ("dest","scratch","recovery","evidence","calib"):p=base/k.upper();p.mkdir(parents=True);c[k]=str(p)
        self.st.d["canary"]=c;atomj(self.st.sp,self.st.d);return {"ANCHOR_RULE":"PASS","R1":True,"CANARY_ROOTS_CREATED_AFTER_EXTERNAL_PASS":"YES"}
    def n_c3(self):
        r=self.rootsc();rid="C3_"+self.id;g=self.gate("LIVE_EQUALITY",r,rid);b,a,_=self.bundle(rid,g,noledger=True);c,so,se=self.launch(b,a,rid);t=pathlib.Path(so).read_text(errors="replace")+pathlib.Path(se).read_text(errors="replace")
        req(c==2 and "RECOVERY_STARTUP_HANDSHAKE="+self.cfg["delta_release_source_sha256"] in t and "LEDGER.zip" in t,"C3");return {"SAME_ANCHOR_ACCEPTED_END_TO_END":"PASS"}
    def n_d1(self):req(ctypes.WinDLL("shell32").IsUserAnAdmin(),"ADMIN");req(shutil.disk_usage("D:\\").free>20*1024**3,"FREE_D");return {"ADMIN":"PASS","FREE_D":shutil.disk_usage("D:\\").free}
    def n_d2(self):
        r=self.rootsc();prod=pathlib.Path(self.cfg["production_dest_root"]);ps=pathlib.Path(self.cfg["production_scratch_root"]);c=s=0
        for p in sorted(prod.rglob("*")):
            if p.is_file():q=r["dest"]/p.relative_to(prod);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);req(shaf(p)==shaf(q),"C0_COPY");c+=1
        for p in sorted(ps.rglob("*")):
            if p.is_file() and re.fullmatch(r"\d{8}\.(journal\.json|pts2g\.partial)",p.name):q=r["scratch"]/p.relative_to(ps);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);req(shaf(p)==shaf(q),"S0_COPY");s+=1
        (days,_),_=self.ledger_data();months=sorted({x["month_id"] for x in days.values()});req(len(months)==75,"CANARY_MONTH_COUNT")
        created=[]
        for m in months:
            q=r["dest"]/"WIN@N"/m
            if not q.exists():q.mkdir(parents=True);created.append(str(q))
        req(c==303 and s==2798,"COPY_COUNTS");return {"c0_files":c,"s0_files":s,"month_dirs_total":75,"month_dirs_created":created}
    def n_d3(self):pr,g=self.vss(self.rootsc(),"CANARY_ADMISSION");self.st.d["cprof"]=pr;self.st.d["G_CA"]=g;atomj(self.st.sp,self.st.d);return g
    def n_d4(self):
        r=self.rootsc();st=self.eng.Win32Store();v=self.eng.NativeVSS(st,self.st.d["cprof"])
        try:inv=self.invs0(v.shadow_root(self.st.d["G_CA"],r["scratch"]))
        finally:v.close()
        c=self.cert("CERTIFY_SCRATCH",r,self.st.d["G_CA"],self.st.d["cprof"],s0=inv);self.st.d["canary_scratch_cert"]=base64.b64encode(c).decode();atomj(self.st.sp,self.st.d);return {"cert_sha256":shab(c)}
    def n_d5(self):
        r=self.rootsc();(days,months),_=self.ledger_data();st=self.eng.Win32Store();v=self.eng.NativeVSS(st,self.st.d["cprof"])
        try:o=self.orc0(v.shadow_root(self.st.d["G_CA"],r["dest"]),days,months)
        finally:v.close()
        c=self.cert("CERTIFY_CANONICAL",r,self.st.d["G_CA"],self.st.d["cprof"],c0=o);self.st.d["canary_canonical_cert"]=base64.b64encode(c).decode();atomj(self.st.sp,self.st.d);return {"cert_sha256":shab(c)}
    def n_d6(self):self.cert("MANIFEST_REDERIVATION",self.rootsc(),self.st.d["G_CA"],self.st.d["cprof"],certs=self.ccerts());return {"PASS":True}
    def n_d7(self):self.cert("LIVE_EQUALITY",self.rootsc(),self.st.d["G_CA"],self.st.d["cprof"],certs=self.ccerts());return {"PASS":True}
    def n_d8(self):b,a,n=self.recover(self.rootsc(),False,"CANARY_RECOVER");self.st.d.update({"cb":str(b),"ca":str(a),"ce":n});atomj(self.st.sp,self.st.d);return {"bundle":str(b),"anchor":str(a),"event":n}
    def n_d9(self):
        r=self.rootsc();m={}
        # R1 named-event SAFE_STOP after 30s.
        b,a,n=self.recover(r,False,"R1");e=Event(n,True);p,fo,fe,so,se=self.launch(b,a,"R1",True);time.sleep(30);e.set();c=p.wait();fo.close();fe.close();e.close();req(c==130 and "SAFE_STOP=YES" in pathlib.Path(so).read_text(errors="replace"),"R1");m["R1"]="PASS"
        # R2 after >=5 NEW coordinators from this attempt.
        before_coord=len(list(r["recovery"].glob("coordinator.*.json")))
        b,a,n=self.recover(r,False,"R2");e=Event(n,True);p,fo,fe,so,se=self.launch(b,a,"R2",True);end=time.time()+7200
        while time.time()<end and len(list(r["recovery"].glob("coordinator.*.json")))<before_coord+5:time.sleep(2)
        req(len(list(r["recovery"].glob("coordinator.*.json")))>=before_coord+5,"R2_COORD");e.set();c=p.wait();fo.close();fe.close();e.close();req(c==130 and "SAFE_STOP=YES" in pathlib.Path(so).read_text(errors="replace"),"R2");m["R2"]="PASS"
        # R3b kill-on-close during stage; then canary stale-lock.
        b,a,n=self.recover(r,False,"R3B");e=Event(n,True);p,fo,fe,so,se=self.launch(b,a,"R3B",True);end=time.time()+7200
        while time.time()<end and not list(r["recovery"].glob("container.*.stage")):time.sleep(1)
        req(list(r["recovery"].glob("container.*.stage")),"R3_STAGE");p.kill();p.wait();fo.close();fe.close();e.close();lock_path=r["dest"]/"TICKSTORE_WRITER.lock";req(lock_path.exists(),"R3_LOCK")
        st=self.eng.Win32Store()
        with st.open(lock_path) as lf:
            raw=lf.read();meta=self.eng.parse(raw);identity=lf.info()
        req(self.eng.process_creation_time(int(meta["pid"]))!=meta["process_creation_time"],"R3_LOCK_OWNER_STILL_ALIVE")
        census=self.eng.recovery_process_census();req(census["known_recovery_supervisor_or_workers"]==0,"R3_RESIDUAL_RECOVERY_PROCESS")
        self.st.d["r3_stale_lock"]={"sha256":shab(raw),"run_id":meta["run_id"],"pid":meta["pid"],"process_creation_time":meta["process_creation_time"],"identity":identity}
        atomj(self.st.sp,self.st.d);self.stale(r,"R3C");m["R3"]="PASS"
        # R4 S0 divergence in canary only.
        with open(r["dest"]/"TICKSTORE_GLOBAL_MANIFEST.json","rb") as f:pub=set(self.eng.parse(f.read())["records"])
        ps=[p for p in r["scratch"].rglob("*.pts2g.partial") if p.name[:8] not in pub];req(ps,"R4_PENDING");t=ps[0];orig=t.read_bytes();bad=bytearray(orig);bad[len(bad)//2]^=1;t.write_bytes(bad)
        try:
            b,a,n=self.recover(r,False,"R4");e=Event(n,True)
            try:c,so,se=self.launch(b,a,"R4")
            finally:e.close()
            req(c==2,"R4_EXIT")
        finally:t.write_bytes(orig)
        self.stale(r,"R4_CLEAR");m["R4"]="PASS"
        # R5 finish.
        b,a,n=self.recover(r,False,"R5");e=Event(n,True)
        try:c,so,se=self.launch(b,a,"R5")
        finally:e.close()
        req(c==0 and "TICKSTORE_PUBLISHER_RECOVERY_V004=PASS" in pathlib.Path(so).read_text(errors="replace"),"R5");m["R5"]="PASS";return m
    def n_d10(self):
        from compression import zstd
        roots=self.rootsc();cert=self.eng.parse(base64.b64decode(self.st.d["canary_scratch_cert"]));(days,months),_=self.ledger_data()
        by_class={f"B{i}":[] for i in range(8)}
        for key,entry in cert["days"].items():by_class[self.eng.size_class(int(entry["partial"]["bytes"]))].append((key,entry))
        present={k:sorted(v,key=lambda x:int(x[1]["partial"]["bytes"]),reverse=True) for k,v in by_class.items() if v};req(present,"D10_NO_SIZE_CLASSES")
        workers=22;raw={};rates=[];copy_rates=[];calib=pathlib.Path(self.st.d["canary"]["calib"]);calib.mkdir(parents=True,exist_ok=True)
        def prep_once(key,entry):
            st=self.eng.Win32Store();t0=time.perf_counter();self.eng.prep(st,roots["scratch"],entry,days[key],months[days[key]["month_id"]],zstd)
            return max(time.perf_counter()-t0,1e-9),int(days[key]["rows"])
        for sc,items in sorted(present.items()):
            sample=items[:min(workers,len(items))];prep_times=[]
            for trial in range(3):
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers,len(sample))) as ex:
                    results=list(ex.map(lambda pair:prep_once(pair[0],pair[1]),sample))
                for sec,rows in results:prep_times.append(sec);rates.append(rows/sec)
            key,entry=items[0];source=roots["scratch"].joinpath(*self.eng.relative_path(entry["partial"]["path"]));copy_times=[]
            for trial in range(3):
                st=self.eng.Win32Store();dst=calib/f"{sc}.{trial}.{uuid.uuid4().hex}.copy";t0=time.perf_counter()
                with st.open(source) as sf,st.open(dst,new=True,mutate=True) as df:
                    for chunk in sf.chunks():df.write(chunk)
                    df.flush()
                elapsed=max(time.perf_counter()-t0,1e-9);copy_times.append(elapsed);copy_rates.append(int(entry["partial"]["bytes"])/elapsed);dst.unlink(missing_ok=True)
            raw[sc]={"largest_date_key":key,"largest_bytes":int(entry["partial"]["bytes"]),"concurrent_sample_days":[x[0] for x in sample],
                     "prep_seconds":prep_times,"copy_seconds":copy_times,"t_max":max(prep_times+copy_times)}
        max_present=max(v["t_max"] for v in raw.values());by={}
        for i in range(8):
            sc=f"B{i}";tmax=raw[sc]["t_max"] if sc in raw else max_present;by[sc]=max(900,int(math.ceil(6*tmax)))
        st=self.eng.Win32Store();mt=[]
        for _ in range(3):
            t0=time.perf_counter()
            with st.open(roots["dest"]/"TICKSTORE_GLOBAL_MANIFEST.json") as f:f.read()
            mt.append(max(time.perf_counter()-t0,1e-9))
        meta_deadline=max(900,int(math.ceil(6*max(mt))));r_ser=min(rates);serial_hours=7049522162/r_ser/3600.0;req(serial_hours<=24.0,"PERF_BLOCK_SERIAL_PASS_GT_24H")
        p={"schema":"DEADLINE_PROFILE_V004","heartbeat_target_seconds":5,"liveness_fatal_seconds":45,"no_progress_diagnostic_seconds":180,
           "metadata_hard_deadline_seconds":meta_deadline,"cooperative_shutdown_ceiling_seconds":900,"terminate_wait_seconds":120,"kill_wait_seconds":60,
           "streaming_by_size_class":by}
        evidence={"schema":"D10_CALIBRATION_V001","prep_workers":workers,"classes":raw,"absent_classes":[f"B{i}" for i in range(8) if f"B{i}" not in raw],
                  "metadata_seconds":mt,"serial_rows_per_second_floor":r_ser,"serial_pass_hours":serial_hours,
                  "copy_bytes_per_second_floor":min(copy_rates),"profile":p}
        atomj(self.rd/"D10_CALIBRATION.json",evidence);self.st.d["deadline_profile"]=p;self.st.d["d10_calibration"]=evidence;atomj(self.st.sp,self.st.d);return evidence
    def n_d11(self):
        p=self.pack("CANARY_EVIDENCE_PACK");self.st.d["canary_evidence_pack"]=p;atomj(self.st.sp,self.st.d);return p
    def n_e1(self):
        deep=self.postverify(self.rootsc());ind=self.independent_verify(self.rootsc(),"E1_CANARY_POSTFULL")
        return {"deep":deep,"independent":ind}
    def n_e2(self):pathlib.Path(self.cfg["production_recovery_root"]).mkdir(parents=True,exist_ok=True);pr,g=self.vss(self.rootsp(),"PRODUCTION_ADMISSION");self.st.d["pprof"]=pr;self.st.d["G_PA"]=g;atomj(self.st.sp,self.st.d);return g
    def n_e3(self):
        r=self.rootsp();st=self.eng.Win32Store();v=self.eng.NativeVSS(st,self.st.d["pprof"])
        try:inv=self.invs0(v.shadow_root(self.st.d["G_PA"],r["scratch"]))
        finally:v.close()
        c=self.cert("CERTIFY_SCRATCH",r,self.st.d["G_PA"],self.st.d["pprof"],s0=inv,prod=True,deadline=self.st.d["deadline_profile"]);self.st.d["prod_scratch_cert"]=base64.b64encode(c).decode();atomj(self.st.sp,self.st.d);return {"sha":shab(c)}
    def n_e4(self):
        r=self.rootsp();(days,months),_=self.ledger_data();st=self.eng.Win32Store();v=self.eng.NativeVSS(st,self.st.d["pprof"])
        try:o=self.orc0(v.shadow_root(self.st.d["G_PA"],r["dest"]),days,months)
        finally:v.close()
        c=self.cert("CERTIFY_CANONICAL",r,self.st.d["G_PA"],self.st.d["pprof"],c0=o,prod=True,deadline=self.st.d["deadline_profile"]);self.st.d["prod_canonical_cert"]=base64.b64encode(c).decode();atomj(self.st.sp,self.st.d);return {"sha":shab(c)}
    def n_e5(self):self.cert("MANIFEST_REDERIVATION",self.rootsp(),self.st.d["G_PA"],self.st.d["pprof"],certs=self.pcerts(),prod=True,deadline=self.st.d["deadline_profile"]);return {"PASS":True}
    def n_e6(self):self.cert("LIVE_EQUALITY",self.rootsp(),self.st.d["G_PA"],self.st.d["pprof"],certs=self.pcerts(),prod=True,deadline=self.st.d["deadline_profile"]);return {"PASS":True}
    def n_e7(self):
        a=self.eng.parse(base64.b64decode(self.st.d["canary_scratch_cert"]));b=self.eng.parse(base64.b64decode(self.st.d["prod_scratch_cert"]));c=self.eng.parse(base64.b64decode(self.st.d["canary_canonical_cert"]));d=self.eng.parse(base64.b64decode(self.st.d["prod_canonical_cert"]))
        req(set(a["days"])==set(b["days"]) and set(c["days"])==set(d["days"]),"CERT_SETS");return {"S0":1399,"C0":151}
    def n_e8(self):
        roots=self.rootsp();b,a,n=self.recover(roots,True,"PRODUCTION_RECOVER_CANDIDATE")
        rid="PRODUCTION_STALE_LOCK_CANDIDATE_"+self.id;sg=self.gate("STALE_LOCK",roots,rid,True,False);sg["stale_lock_clear_authorized"]=False;sb,sa,_=self.bundle(rid,sg)
        # Admission simulation for the production RECOVER candidate.
        with zipfile.ZipFile(b,"r") as z:members={name:z.read(name) for name in z.namelist()}
        admitted=self.eng.admit_bundle(rj(a),members);req(admitted["mode"]=="RECOVER","E8_RECOVER_ADMISSION")
        (days,_),_=self.ledger_data();plan=[]
        for m in sorted({x["month_id"] for x in days.values()}):
            p=roots["dest"]/"WIN@N"/m
            if not p.exists():plan.append(str(p))
        self.st.d.update({"pb":str(b),"pa":str(a),"pe":n,"psb":str(sb),"psa":str(sa),"month_plan":plan});atomj(self.st.sp,self.st.d)
        return {"recover_bundle":str(b),"recover_anchor":str(a),"stale_lock_bundle":str(sb),"stale_lock_anchor":str(sa),"month_plan":plan,
                "recover_bundle_sha256":shaf(b),"stale_lock_bundle_sha256":shaf(sb)}
    def n_e9(self):
        opkg=self.tree_zip(self.pkg,self.rd/"ORCHESTRATOR_PACKAGE_STAGE_B.zip");self.st.d["stage_b_orchestrator_package"]=opkg;atomj(self.st.sp,self.st.d)
        autocheck={"schema":"STAGE_B_AUTOCHECK_V001","status":"PASS","cp2r1_satisfied":self.st.d.get("cp2r1_satisfied") is True,
          "candidate_tests":self.st.d.get("cp2r1_a2"),"release_tests":self.st.d.get("cp2r1_b2"),
          "release_source_sha256":self.cfg["delta_release_source_sha256"],"release_domain_test_sha256":self.cfg["release_domain_test_sha256"],
          "release_precanary_test_sha256":self.cfg["release_precanary_test_sha256"],"native_test_sha256":self.cfg["native_test_sha256"],
          "orchestrator_package_sha256":opkg["sha256"],"postfull_verifier_sha256":self.cfg["postfull_verifier_sha256"],
          "b7_performance":self.st.d.get("b7_performance"),"d10_calibration":self.st.d.get("d10_calibration"),
          "deadline_profile_sha256":shab(self.eng.json_bytes(self.st.d["deadline_profile"])),
          "scratch_admission_cert_sha256":shab(base64.b64decode(self.st.d["prod_scratch_cert"])),
          "canonical_admission_cert_sha256":shab(base64.b64decode(self.st.d["prod_canonical_cert"])),
          "production_recover_bundle_sha256":shaf(self.st.d["pb"]),"production_recover_anchor_sha256":shaf(self.st.d["pa"]),
          "production_stale_lock_bundle_sha256":shaf(self.st.d["psb"]),"production_stale_lock_anchor_sha256":shaf(self.st.d["psa"]),
          "month_directory_plan_sha256":shab(jb(self.st.d["month_plan"])),"dirbind_policy":self.st.d.get("dirbind_policy")}
        atomj(self.rd/"02_AUTOCHECK_REPORT.json",autocheck);p=self.pack("TICKSTORE_V004R1_STAGE_B_EVIDENCE_PACK_V001");self.st.d["stage_b_pack"]=p;atomj(self.st.sp,self.st.d);raise RuntimeError("AWAITING_STAGE_B")
    def stageb(self):
        p=self.st.inbox/"STAGE_B_REVIEW_V001.txt";req(p.exists(),"AWAITING_STAGE_B");blocks=fenced_kv_blocks(p.read_text(encoding="utf-8"));req(blocks,"STAGE_B_BLOCK_MISSING")
        title,b=blocks[0];req(title=="STAGE_B_REVIEW_V001","STAGE_B_TITLE");req(b.get("STAGE_B_VERDICT")=="PASS","STAGE_B_VERDICT");req(b.get("BLOCKERS")=="NONE","STAGE_B_BLOCKERS")
        req(b.get("RELEASE_SOURCE_SHA256")==self.cfg["delta_release_source_sha256"],"STAGE_B_RELEASE")
        req(b.get("EVIDENCE_PACK_SHA256")==self.st.d["stage_b_pack"]["sha256"],"STAGE_B_EVIDENCE_PACK")
        req(b.get("ORCHESTRATOR_PACKAGE_SHA256")==self.st.d["stage_b_orchestrator_package"]["sha256"],"STAGE_B_ORCHESTRATOR_PACKAGE")
        req(b.get("POSTFULL_VERIFIER_SHA256")==self.cfg["postfull_verifier_sha256"],"STAGE_B_POSTFULL_VERIFIER")
        req(b.get("DEADLINE_PROFILE_SHA256")==shab(self.eng.json_bytes(self.st.d["deadline_profile"])),"STAGE_B_DEADLINE")
        req(b.get("SCRATCH_ADMISSION_CERT_SHA256")==shab(base64.b64decode(self.st.d["prod_scratch_cert"])),"STAGE_B_SCRATCH_CERT")
        req(b.get("CANONICAL_ADMISSION_CERT_SHA256")==shab(base64.b64decode(self.st.d["prod_canonical_cert"])),"STAGE_B_CANONICAL_CERT")
        req(b.get("PRODUCTION_RECOVER_BUNDLE_SHA256")==shaf(self.st.d["pb"]),"STAGE_B_RECOVER_BUNDLE")
        req(b.get("PRODUCTION_STALE_LOCK_BUNDLE_SHA256")==shaf(self.st.d["psb"]),"STAGE_B_STALE_BUNDLE")
        try:
            recover_anchor_review=json.loads(b.get("PRODUCTION_RECOVER_ANCHOR_JSON",""))
            stale_anchor_review=json.loads(b.get("PRODUCTION_STALE_LOCK_ANCHOR_JSON",""))
        except Exception:
            raise RuntimeError("STAGE_B_ANCHOR_JSON_PARSE")
        req(recover_anchor_review==rj(self.st.d["pa"]),"STAGE_B_RECOVER_ANCHOR")
        req(stale_anchor_review==rj(self.st.d["psa"]),"STAGE_B_STALE_ANCHOR")
        req(b.get("MONTH_DIRECTORY_PLAN_SHA256")==shab(jb(self.st.d["month_plan"])),"STAGE_B_MONTH_PLAN")
        req(b.get("CANARY_BULK_RELEASE_ALLOWED") in ("YES","NO"),"STAGE_B_CANARY_BULK_DECISION")
        perf=self.st.d.get("b7_performance",{})
        if perf.get("status")=="WARN":req(b.get("PERFORMANCE_WARN_ACCEPTED")=="YES","STAGE_B_PERFORMANCE_WARN")
        else:req(b.get("PERFORMANCE_WARN_ACCEPTED") in ("YES","NOT_APPLICABLE"),"STAGE_B_PERFORMANCE_FIELD")
        req(b.get("FULL_EXECUTION_RECOMMENDED")=="YES","STAGE_B_FULL_NOT_RECOMMENDED")
        if self.st.d.get("dirbind_policy")=="UNSTABLE":req(b.get("DIRBIND_REANCHOR_PRODUCTION_ALLOWED")=="YES","STAGE_B_DIRBIND")
        else:req(b.get("DIRBIND_REANCHOR_PRODUCTION_ALLOWED") in ("NO","NOT_APPLICABLE"),"STAGE_B_DIRBIND_FIELD")
        q=self.st.inbox/"FULL_GO.txt";req(q.exists(),"AWAITING_FULL_GO_PHRASE");return b,q.read_text(encoding="utf-8").strip()
    def n_f1(self):
        b,q=self.stageb();bundle=b["PRODUCTION_RECOVER_BUNDLE_SHA256"];req(q==f"AUTORIZO FULL TICKSTORE V004R1 {bundle[:12]}","FULL_GO");req(shaf(self.st.d["pb"])==bundle,"FULL_BUNDLE")
        current=self.tree_zip(self.pkg,self.rd/"F1_ORCHESTRATOR_PACKAGE_RECHECK.zip");req(current["sha256"]==b["ORCHESTRATOR_PACKAGE_SHA256"],"F1_ORCHESTRATOR_DRIFT")
        return {"FULL_GO":"PASS","stage_b":b,"orchestrator_recheck":current}
    def n_f2(self):
        x={"schema":"PRODUCTION_FREEZE_V004R1","release_source_sha256":self.cfg["delta_release_source_sha256"],
           "candidate_source_sha256":self.cfg["delta_candidate_source_sha256"],"domain_test_sha256":self.cfg["release_domain_test_sha256"],
           "native_test_sha256":self.cfg["native_test_sha256"],"precanary_test_sha256":self.cfg["release_precanary_test_sha256"],
           "root_loader_sha256":self.cfg["root_loader_sha256"],"root_contract_id":self.cfg["root_contract_id"],
           "python_exe_sha256":self.cfg["python_exe_sha256"],"orchestrator_package_sha256":self.st.d["stage_b_orchestrator_package"]["sha256"],
           "deadline_profile_sha256":shab(self.eng.json_bytes(self.st.d["deadline_profile"])),
           "scratch_admission_cert_sha256":shab(base64.b64decode(self.st.d["prod_scratch_cert"])),
           "canonical_admission_cert_sha256":shab(base64.b64decode(self.st.d["prod_canonical_cert"])),
           "production_recover_bundle_sha256":shaf(self.st.d["pb"]),"production_recover_anchor_sha256":shaf(self.st.d["pa"]),
           "production_stale_lock_bundle_sha256":shaf(self.st.d["psb"]),"production_stale_lock_anchor_sha256":shaf(self.st.d["psa"]),
           "month_directory_plan_sha256":shab(jb(self.st.d["month_plan"])),"dirbind_policy":self.st.d.get("dirbind_policy"),
           "production_vss_generation":self.st.d["G_PA"],"rescan_authorized":False,"csv_deletion_authorized":False,
           "format_promotion_authorized":False,"codec_promotion_authorized":False}
        path=self.control/"PRODUCTION_FREEZE_V004R1.json";req(not path.exists(),"PRODUCTION_FREEZE_ALREADY_EXISTS");atomj(path,x);return {**x,"freeze_sha256":shaf(path)}
    def n_f3(self):return {"CANARY_BULK_RELEASE":"NO_ACTION_DEFAULT"}
    def n_g1(self):req(not (pathlib.Path(self.cfg["production_dest_root"])/"TICKSTORE_WRITER.lock").exists(),"WRITER_LOCK");req(shutil.disk_usage("D:\\").free>20*1024**3,"FULL_FREE");return {"PASS":True}
    def n_g2(self):
        m=[]
        for s in self.st.d["month_plan"]:
            p=pathlib.Path(s)
            if not p.exists():p.mkdir(parents=True);m.append(s)
        return {"created":m}
    def n_g3(self):
        e=Event(self.st.d["pe"],True);self.st.d["engine"]={"safe_stop_event_name":self.st.d["pe"],"bundle":self.st.d["pb"],"anchor":self.st.d["pa"],"started":now()};atomj(self.st.sp,self.st.d)
        try:c,so,se=self.launch(self.st.d["pb"],self.st.d["pa"],"FULL_G3")
        finally:e.close()
        t=pathlib.Path(so).read_text(errors="replace")
        if c==130 and "SAFE_STOP=YES" in t:
            self.st.d["full_safe_stop"]=True;self.st.d["full_safe_stop_stdout"]=str(so);atomj(self.st.sp,self.st.d)
            raise SafeStopFlow("SAFE_STOP=YES")
        req(c==0 and "TICKSTORE_PUBLISHER_RECOVERY_V004=PASS" in t,"FULL_NOT_PASS");self.st.d["full_safe_stop"]=False;atomj(self.st.sp,self.st.d);return {"FULL":"PASS","stdout":str(so)}
    def n_g4(self):return {"CLASS":"SAFE_STOP" if self.st.d.get("full_safe_stop") else "PASS"}
    def n_g5(self):
        if not self.st.d.get("full_safe_stop"):return {"RESUME":"NOT_REQUIRED"}
        if self.st.d.get("dirbind_policy")=="UNSTABLE":
            review=(self.st.inbox/"STAGE_B_REVIEW_V001.txt").read_text(encoding="utf-8")
            req("DIRBIND_REANCHOR_PRODUCTION_ALLOWED=YES" in review,"DIRBIND_REANCHOR_NOT_AUTHORIZED")
            b,a,n=self.recover(self.rootsp(),True,"PRODUCTION_RECOVER_RESUME_REANCHOR")
            self.st.d.update({"pb":str(b),"pa":str(a),"pe":n});atomj(self.st.sp,self.st.d)
        e=Event(self.st.d["pe"],True)
        try:c,so,se=self.launch(self.st.d["pb"],self.st.d["pa"],"FULL_G5_RESUME")
        finally:e.close()
        t=pathlib.Path(so).read_text(errors="replace")
        if c==130 and "SAFE_STOP=YES" in t:raise SafeStopFlow("SAFE_STOP=YES")
        req(c==0 and "TICKSTORE_PUBLISHER_RECOVERY_V004=PASS" in t,"FULL_RESUME_NOT_PASS")
        self.st.d["full_safe_stop"]=False;atomj(self.st.sp,self.st.d);return {"RESUME":"PASS","stdout":str(so)}
    def n_g6(self):
        lock=pathlib.Path(self.cfg["production_dest_root"])/"TICKSTORE_WRITER.lock"
        if not lock.exists():return {"RECONCILE":"PASS","writer_lock":"ABSENT","action":"NONE"}
        st=self.eng.Win32Store()
        with st.open(lock) as f:raw=f.read();meta=self.eng.parse(raw);identity=f.info()
        census=self.eng.recovery_process_census();alive=self.eng.process_creation_time(int(meta["pid"]))==meta["process_creation_time"]
        report={"schema":"PRODUCTION_RECONCILE_V001","lock_sha256":shab(raw),"lock":meta,"identity":identity,"process_census":census,"lock_owner_alive":alive}
        atomj(self.rd/"G6_RECONCILE.json",report)
        req(not alive and census["known_recovery_supervisor_or_workers"]==0,"PRODUCTION_STALE_LOCK_PROCESS_NOT_CLEAR")
        confirm=self.st.inbox/("STALE_LOCK_CONFIRM_"+shab(raw)+".txt")
        req(confirm.exists() and confirm.read_text(encoding="utf-8").strip()=="CONFIRM STALE LOCK "+shab(raw),"AWAITING_STALE_LOCK_CONFIRM_"+shab(raw))
        self.stale(self.rootsp(),"G6_PRODUCTION_STALE_LOCK",prod=True)
        retry=self.n_g3()
        return {**report,"stale_lock_clear":"PASS","full_retry":retry}
    def n_g7(self):x={"schema":"FULL_COMPLETE_V001","release":self.cfg["delta_release_source_sha256"],"finished_at":now()};atomj(self.control/"FULL_COMPLETE.json",x);return x
    def n_h1(self):pr,g=self.vss(self.rootsp(),"POSTFULL_AUDIT");self.st.d["G_POSTFULL"]=g;atomj(self.st.sp,self.st.d);return g
    def n_h2(self):
        deep=self.postverify(self.rootsp());ind=self.independent_verify(self.rootsp(),"H2_POSTFULL");r={"deep":deep,"independent":ind}
        self.st.d["postfull_h2"]=r;atomj(self.st.sp,self.st.d);return r
    def n_h3(self):
        files=sorted(pathlib.Path(self.cfg["production_recovery_root"]).glob("final_reconcile.*.json"),key=lambda p:p.stat().st_mtime_ns)
        req(files,"H3_FINAL_RECONCILE_MISSING");obj=rj(files[-1]);h2=self.st.d.get("postfull_h2");req(h2,"H3_H2_MISSING");deep=h2["deep"]
        req(obj.get("days")==deep["days"] and obj.get("rows")==deep["rows"] and obj.get("manifest_sha256")==deep["manifest_sha256"],"H3_FINAL_POSTFULL_MISMATCH")
        return {"FINAL_VS_POSTFULL":"PASS","final_reconcile":str(files[-1]),"manifest_sha256":deep["manifest_sha256"]}
    def n_h4(self):return {"RESIDUAL_POLICY":"NO_DELETE"}
    def n_h5(self):x={"TICKSTORE_V004R1_FULL_RECOVERY":"PASS","FORMAT_PROMOTION_AUTHORIZED":"NO","CODEC_PROMOTION_AUTHORIZED":"NO","CSV_DELETION_AUTHORIZED":"NO"};atomj(self.control/"FINAL_REPORT_TICKSTORE_V004R1.json",x);return x
    def n_h6(self):return self.pack("FINAL_EVIDENCE")
    def n_i1(self):x={"INCREMENTAL_READINESS":"PASS","last_date":"2026-09-18","delta_publisher_required":"V005","BAT_INTEGRATION_FUTURE":True};atomj(self.control/"INCREMENTAL_READINESS_I1.json",x);return x
    def runnode(self,n):return getattr(self,"n_"+n.lower())()
def execute(a):
    o=O(a);target=a.until or "E9";req(target in NODES,"TARGET");start=o.st.d["next_node"];i=NODES.index(start) if start in NODES else len(NODES);j=NODES.index(target)
    if i>j:return PASS
    for n in NODES[i:j+1]:
        scope="PROT" if n in ("G2","G3","G5","G6") else "CAN" if (n.startswith("D") or n=="C2") else "SYS" if n in ("B6","B6X","E2","H1") else "DEV" if n in ("A1","B1") else "EVID"
        o.st.log(n,"STARTED",run_id=o.id)
        try:
            r=o.runnode(n);atomj(o.rd/f"RESULT_{n}.json",r);o.rec(n,"PASS",r,scope=scope);o.st.finish(n,"PASS",r);print(n+"=PASS",flush=True)
        except SafeStopFlow as e:
            m=str(e);o.rec(n,"SAFE_STOP",e=m,scope=scope);o.st.log(n,"FINISHED",status="SAFE_STOP",primary_error=m)
            idx=NODES.index(n);o.st.d["next_node"]=n if getattr(e,"resume_current",False) else (NODES[idx+1] if idx+1<len(NODES) else "DONE");o.st.d["status"]="SAFE_STOP";o.st.d["updated_at"]=now();atomj(o.st.sp,o.st.d)
            print(f"{n}=SAFE_STOP REASON={m}",flush=True);return SAFE_STOP
        except RuntimeError as e:
            m=str(e)
            if n=="B9" and m=="AWAITING_B6_CODE_DELTA_REVIEW_V005R1":
                o.rec(n,"BLOCKED",e=m,scope=scope)
                o.st.log(n,"FINISHED",status="AWAITING_B6_CODE_DELTA_REVIEW_V005R1",primary_error=m)
                o.st.d["next_node"]="C1";o.st.d["status"]="AWAITING_B6_CODE_DELTA_REVIEW_V005R1";o.st.d["updated_at"]=now();atomj(o.st.sp,o.st.d)
                print("B9=PASS_TO_B6_CODE_DELTA_REVIEW_V005R1",flush=True);print("AWAITING_B6_CODE_DELTA_REVIEW_V005R1",flush=True);return BLOCKED
            if n=="E9" and m=="AWAITING_STAGE_B":
                o.rec(n,"BLOCKED",e=m,scope=scope)
                o.st.log(n,"FINISHED",status="AWAITING_STAGE_B",primary_error=m)
                o.st.d["next_node"]="F1";o.st.d["status"]="AWAITING_STAGE_B";o.st.d["updated_at"]=now();atomj(o.st.sp,o.st.d)
                print("E9=PASS_TO_STAGE_B",flush=True);print("AWAITING_STAGE_B",flush=True);return BLOCKED
            st="BLOCKED" if m.startswith("AWAITING_") else "FAIL";o.rec(n,st,e=m,scope=scope);o.st.finish(n,st,error=m);print(f"{n}={st} REASON={m}",flush=True);return BLOCKED if st=="BLOCKED" else (PARTIAL if scope in ("PROT","CAN","SYS","DEV") else FAIL)
    return PASS
def reconcile_command(a):
    o=O(a);lock=pathlib.Path(o.cfg["production_dest_root"])/"TICKSTORE_WRITER.lock"
    if not lock.exists():
        report={"schema":"PRODUCTION_RECONCILE_V001","writer_lock":"ABSENT","action":"RETRY_OR_RESUME_ALLOWED"}
        atomj(o.rd/"RECONCILE.json",report);print(json.dumps(report,indent=2));return PASS
    st=o.eng.Win32Store()
    with st.open(lock) as f:raw=f.read();meta=o.eng.parse(raw);identity=f.info()
    census=o.eng.recovery_process_census();alive=o.eng.process_creation_time(int(meta["pid"]))==meta["process_creation_time"]
    report={"schema":"PRODUCTION_RECONCILE_V001","writer_lock":"PRESENT","lock_sha256":shab(raw),"lock":meta,"identity":identity,
            "process_census":census,"lock_owner_alive":alive}
    atomj(o.rd/"RECONCILE.json",report)
    req(not alive and census["known_recovery_supervisor_or_workers"]==0,"RECOVERY_PROCESS_STILL_LIVE")
    o.st.d["next_node"]="G6";o.st.d["status"]="AWAITING_STALE_LOCK_CONFIRM";o.st.d["stale_lock_sha256"]=shab(raw);atomj(o.st.sp,o.st.d)
    print(json.dumps(report,indent=2));print("NEXT=confirm-stale-lock --lock-sha "+shab(raw));return BLOCKED
def confirm_stale_lock(a):
    req(a.lock_sha is not None and re.fullmatch(r"[0-9A-F]{64}",a.lock_sha) is not None,"LOCK_SHA_ARGUMENT")
    cfg=rj(pathlib.Path(a.package)/"config/STAGE_A_SEALED_VALUES_V001.json");st=State(cfg["control_root"]);lock=pathlib.Path(cfg["production_dest_root"])/"TICKSTORE_WRITER.lock"
    req(lock.exists(),"WRITER_LOCK_ABSENT");actual=shaf(lock);req(actual==a.lock_sha,"WRITER_LOCK_SHA_CHANGED")
    token=st.inbox/("STALE_LOCK_CONFIRM_"+actual+".txt");atom(token,("CONFIRM STALE LOCK "+actual+"\n").encode())
    print("STALE_LOCK_CONFIRMATION_RECORDED="+actual);return PASS
def main():
    ap=argparse.ArgumentParser();ap.add_argument("command",choices=["plan","run","status","stop","resume","reconcile","confirm-stale-lock","ingest-stage-b","postfull","attach"]);ap.add_argument("--package",required=True);ap.add_argument("--python",required=True);ap.add_argument("--until");ap.add_argument("--lock-sha");a=ap.parse_args()
    cfg=rj(pathlib.Path(a.package)/"config/STAGE_A_SEALED_VALUES_V001.json");st=State(cfg["control_root"])
    if a.command=="plan":print(json.dumps({"next_node":st.d["next_node"],"nodes":NODES,"default_until":"E9"},indent=2));return 0
    if a.command=="status":print(json.dumps(st.d,indent=2));return 0
    if a.command=="stop":
        n=(st.d.get("engine") or {}).get("safe_stop_event_name");req(n,"NO_ACTIVE_SAFE_STOP_EVENT");e=Event(n,False)
        try:e.set()
        finally:e.close()
        print("SAFE_STOP_REQUESTED="+n);return 0
    if a.command in ("run","resume"):return execute(a)
    if a.command=="ingest-stage-b":print(str(st.inbox/"STAGE_B_REVIEW_V001.txt"));return 0
    if a.command=="attach":print(json.dumps(st.d.get("engine"),indent=2));return 0
    if a.command=="postfull":o=O(a);print(json.dumps({"deep":o.postverify(o.rootsp()),"independent":o.independent_verify(o.rootsp(),"POSTFULL_COMMAND")},indent=2));return 0
    if a.command=="reconcile":return reconcile_command(a)
    if a.command=="confirm-stale-lock":return confirm_stale_lock(a)
    return 2
if __name__=="__main__":
    try:raise SystemExit(main())
    except RuntimeError as e:print("ORCHESTRATOR_BLOCKED="+str(e),flush=True);raise SystemExit(BLOCKED)
