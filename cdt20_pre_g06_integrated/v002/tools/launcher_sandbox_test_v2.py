"""Functional sandbox test of the PS launcher under pwsh 7 on Linux. NOT Windows PS 5.1 evidence.

The tested copy differs from the delivered launcher ONLY by the substitutions in SUBST
(fixed paths, version gate, Python), recorded in the report. Stubs are labelled.
"""
import hashlib,json,os,shutil,subprocess,sys,time,unittest,zipfile
from pathlib import Path
S=Path(sys.argv.pop(1)).resolve();PWSH=str(S/'pwsh/ps/pwsh')
DELIVERED=S/'build2/out/RUN_CDT20_PRE_G06_INTEGRATED_V002_20261020.ps1'
TRANSPORT=S/'build2/out/CDT20_PRE_G06_INTEGRATED_TRANSPORT_V002_20261020.zip'
BASE=S/'launcher_test2'
def sha(b):return hashlib.sha256(b).hexdigest().upper()
STUB_CAMPAIGN='''import sys,os,zipfile,pathlib
root=pathlib.Path(os.environ['STUB_ROOT']);root.mkdir(parents=True,exist_ok=True)
print('RUN_ROOT='+str(root),flush=True)
print('STUB_STDERR_LINE_MUST_NOT_STOP_LAUNCHER',file=sys.stderr,flush=True)
code=int(os.environ.get('STUB_EXIT','0'))
with zipfile.ZipFile(root/'CDT20_PRE_G06_RETURN.zip','w') as z:z.writestr('ENGINEERING_RESULT.json','{"status":"STUB"}')
(root/'ENGINEERING_RESULT.json').write_text('{"status":"STUB"}')
import hashlib,json
if os.environ.get('STUB_RECEIPT','1')=='1':
    (root/'FINAL_G5').mkdir(exist_ok=True)
    (root/'FINAL_G5/FINAL_ENGINEERING_STATUS.json').write_text(json.dumps({'engineering_five_part_completeness':os.environ.get('STUB_FIVE','PASS'),
        'four_pre_b06_findings':'PASS_NATIVE_REGRESSION','b06':'NOT_STARTED','full_started':False,'STUB':True}))
    (root/'CDT20_PRE_G06_RETURN.sha256').write_text(hashlib.sha256((root/'CDT20_PRE_G06_RETURN.zip').read_bytes()).hexdigest().upper()+'  CDT20_PRE_G06_RETURN.zip\\n')
print('EXIT_CODE='+str(code),flush=True);raise SystemExit(code)
'''
class Launcher(unittest.TestCase):
    def setUp(self):
        self.n=getattr(Launcher,'_n',0)+1;Launcher._n=self.n
        self.box=BASE/('case%02d'%self.n)
        if self.box.exists():shutil.rmtree(self.box)
        self.down=self.box/'Downloads';self.local=self.box/'Local';self.down.mkdir(parents=True);self.local.mkdir()
        self.transport=self.down/TRANSPORT.name;shutil.copy2(TRANSPORT,self.transport)
        self.sha=sha(TRANSPORT.read_bytes())

    def launcher(self,g0=None,campaign=None,sha_override=None):
        s=DELIVERED.read_text(encoding='utf-8-sig')
        subst=[("'C:\\Users\\silvi\\OneDrive\\Downloads\\CDT20_PRE_G06_RUNS'","'"+str(self.down/'CDT20_PRE_G06_RUNS')+"'"),
               ("'C:\\Users\\silvi\\OneDrive\\Downloads'","'"+str(self.down)+"'"),
               ("[Environment]::GetFolderPath('LocalApplicationData')","'"+str(self.local)+"'"),
               ("Join-Path $LocalAppData 'Python\\pythoncore-3.14-64\\python.exe'","'"+sys.executable+"'"),
               ("$LabDrive       = 'D:\\'","$LabDrive       = '/'"),
               ("$PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1","$false"),
               ("$RequireDesktop = $true","$RequireDesktop = $false"),
               ("'^3 (1[4-9]|[2-9][0-9]) 64$'","'^3 (1[3-9]|[2-9][0-9]) 64$'")]
        if g0:subst.append(("(Join-Path $Stage 'G0_CDT20_PRE_G06.py')","'"+str(g0)+"'"))
        if campaign:subst.append(("(Join-Path $Stage 'RUN_CDT20_R08Q1.py')","'"+str(campaign)+"'"))
        if sha_override:subst.append((self.sha,sha_override))
        for a,b in subst:
            self.assertEqual(s.count(a),1,a);s=s.replace(a,b)
        p=self.down/DELIVERED.name;p.write_text(s,encoding='utf-8-sig');self.subst=subst;return p

    def run_ps(self,script,env=None,cwd=None,args=()):
        e=dict(os.environ,**(env or {}))
        p=subprocess.run([PWSH,'-NoProfile','-File',str(script),*args],capture_output=True,timeout=1800,cwd=str(cwd or self.box),env=e)
        out=(p.stdout+p.stderr).decode('utf8','replace')
        (self.box/'console.txt').write_text(out)
        return p.returncode,out

    def rundir(self):
        dirs=list((self.down/'CDT20_PRE_G06_RUNS').glob('INTEGRATED_*'));self.assertEqual(len(dirs),1);return dirs[0]

    def assert_tail(self,out):
        lines=[l for l in out.strip().splitlines() if l.strip()]
        self.assertTrue(lines[-2].startswith('Devolva este resultado ao ChatGPT'))
        self.assertEqual(lines[-1],'RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 20')

    def test_a_real_g0_refuses_non_windows_and_blocks_after_staging(self):
        rc,out=self.run_ps(self.launcher())
        self.assertEqual(rc,3,out);self.assertIn('NATIVE_G0_NONPASS: 2',out);self.assertIn('CDT20_PRE_G06_G0_WIN_PYTHON_314_X64',out)
        self.assertIn('TRANSPORT_MEMBERS_VERIFIED=20',out)
        d=self.rundir();res=json.loads((d/'LAUNCHER_RESULT.json').read_text())
        self.assertEqual((res['status'],res['exit_code'],res['partial_effect_scope']),('BLOCKED_AFTER_RUN_OWNED_EFFECTS',3,'RUN_OWNED_LAB_ONLY'))
        self.assertTrue(list(d.glob('ENVIAR_AO_CHATGPT_CDT20_PRE_G06_*.zip')));self.assert_tail(out)
        self.assertRegex(d.name,r'^INTEGRATED_\d{8}_\d{6}_\d{3}_\d+$');self.assertTrue((d/'RUN_LOG.txt').exists())

    def test_b_success_plumbing_with_real_g0_sandbox_and_stub_campaign(self):
        g0=self.box/'g0_wrapper.py';g0.write_text("import sys,subprocess,pathlib\nstage=pathlib.Path(sys.argv[0]).resolve().parent\n")
        # Real G0 qualify() on the extracted stage (native=False), via the sealed sandbox driver.
        g0.write_text('import sys,glob,subprocess\nstage=sorted(glob.glob(%r))[-1]\nraise SystemExit(subprocess.call([sys.executable,"-I","-B",%r,stage]))\n'
                      %(str(self.local/'CDT20_PREG06_*'),str(S/'tools/g0_sandbox.py')))
        camp=self.box/'stub_campaign.py';camp.write_text(STUB_CAMPAIGN)
        rc,out=self.run_ps(self.launcher(g0=g0,campaign=camp),env={'STUB_ROOT':str(self.local/'CDT20_R08/R08_STUB')},cwd='/')
        self.assertEqual(rc,0,out[-3000:]);self.assertIn('SANDBOX_G0_RESULT=PASS',out)
        self.assertIn('STUB_STDERR_LINE_MUST_NOT_STOP_LAUNCHER',out);self.assertIn('FINAL_RECEIPT=FIVE_PART_PASS',out)
        d=self.rundir();res=json.loads((d/'LAUNCHER_RESULT.json').read_text())
        self.assertEqual(res['status'],'PASS_NATIVE_INTEGRATED_PRE_G06_ENGINEERING_FIVE_PART')
        got={c['path'] for c in res['collected']};self.assertTrue({'G0_RESULT.json','G0_RETURN.zip','CDT20_PRE_G06_RETURN.zip'}<=got)
        with zipfile.ZipFile(next(d.glob('ENVIAR_AO_CHATGPT_*.zip'))) as z:
            self.assertTrue({'RUN_LOG.txt','LAUNCHER_RESULT.json','G0_RETURN.zip','CDT20_PRE_G06_RETURN.zip'}<=set(z.namelist()))
        self.assert_tail(out)

    def test_c_safe_stop_and_blocked_campaign_codes(self):
        camp=self.box/'stub_campaign.py';camp.write_text(STUB_CAMPAIGN);g0=self.box/'g0_ok.py';g0.write_text('raise SystemExit(0)\n')
        rc,out=self.run_ps(self.launcher(g0=g0,campaign=camp),env={'STUB_ROOT':str(self.local/'R'),'STUB_EXIT':'130'})
        self.assertEqual(rc,130,out);self.assertIn('ENGINEERING_STATUS=SAFE_STOP',out)
        shutil.rmtree(self.down/'CDT20_PRE_G06_RUNS')
        rc,out=self.run_ps(self.launcher(g0=g0,campaign=camp),env={'STUB_ROOT':str(self.local/'R2'),'STUB_EXIT':'3'})
        self.assertEqual(rc,3,out);self.assertIn('PRE_G06_CAMPAIGN_NONPASS: 3',out)

    def test_k_exit_zero_without_receipt_is_not_pass(self):
        camp=self.box/'stub_campaign.py';camp.write_text(STUB_CAMPAIGN);g0=self.box/'g0_ok.py';g0.write_text('raise SystemExit(0)\n')
        rc,out=self.run_ps(self.launcher(g0=g0,campaign=camp),env={'STUB_ROOT':str(self.local/'R'),'STUB_RECEIPT':'0'})
        self.assertEqual(rc,3,out);self.assertIn('CAMPAIGN_EXIT_0_WITHOUT_FINAL_RECEIPT_OR_RETURN',out)
        self.assertNotIn('ENGINEERING_STATUS=PASS',out)
        shutil.rmtree(self.down/'CDT20_PRE_G06_RUNS')
        rc,out=self.run_ps(self.launcher(g0=g0,campaign=camp),env={'STUB_ROOT':str(self.local/'R2'),'STUB_FIVE':'NOT_PROVEN'})
        self.assertEqual(rc,3,out);self.assertIn('FINAL_RECEIPT_NOT_FIVE_PART_PASS',out)

    def test_d_tampered_transport_blocks_before_effects(self):
        raw=bytearray(self.transport.read_bytes());raw[100]^=1;self.transport.write_bytes(bytes(raw))
        rc,out=self.run_ps(self.launcher())
        self.assertEqual(rc,2,out);self.assertIn('TRANSPORT_SHA256_MISMATCH',out)
        self.assertFalse(list(self.local.glob('CDT20_PREG06_*')));self.assert_tail(out)

    def test_e_missing_transport_blocks(self):
        self.transport.unlink();rc,out=self.run_ps(self.launcher())
        self.assertEqual(rc,2,out);self.assertIn('TRANSPORT_ABSENT_NEXT_TO_LAUNCHER',out)

    def rebuild(self,mutate):
        with zipfile.ZipFile(TRANSPORT) as z:members={n:z.read(n) for n in z.namelist()}
        mutate(members);self.transport.unlink()
        with zipfile.ZipFile(self.transport,'w') as z:
            for n,b in members.items():z.writestr(n,b)
        return sha(self.transport.read_bytes())

    def test_f_member_hash_mismatch_blocks_after_staging(self):
        new=self.rebuild(lambda m:m.__setitem__('RUN_CDT20_R08Q1.py',m['RUN_CDT20_R08Q1.py']+b'\n# tampered\n'))
        rc,out=self.run_ps(self.launcher(sha_override=new))
        self.assertEqual(rc,3,out);self.assertIn('PACKAGE_MEMBER_BYTES: RUN_CDT20_R08Q1.py',out)

    def test_g_unsafe_member_blocks(self):
        new=self.rebuild(lambda m:m.__setitem__('../evil.txt',b'x'))
        rc,out=self.run_ps(self.launcher(sha_override=new))
        self.assertEqual(rc,2,out);self.assertIn('UNSAFE_ZIP_COMPONENT',out)

    def test_h_extra_member_blocks(self):
        new=self.rebuild(lambda m:m.__setitem__('EXTRA_UNDECLARED.txt',b'x'))
        rc,out=self.run_ps(self.launcher(sha_override=new))
        self.assertEqual(rc,3,out);self.assertIn('TRANSPORT_EXACT_MEMBER_COUNT',out)

    def test_i_prior_g0_log_collected_read_only(self):
        prior=self.local/'CDT20_PRE_G06_PROJECTION_G0_9ef688d3dea34e5fb89997f9024ace09';prior.mkdir()
        log=prior/'G0_test_cdt19_final_transport_closure.py.log'
        body=b'test_x ... ERROR\n\n'+b'='*70+b'\nERROR: test_x (__main__.C.test_x)\nTraceback...\nPRIOR_PRIMARY_CAUSE_SENTINEL\n'
        log.write_bytes(body);before=(log.stat().st_mtime_ns,sha(body))
        rc,out=self.run_ps(self.launcher())
        self.assertIn('PRIOR_G0_STAGES_FOUND=1',out);self.assertIn('PRIOR_PRIMARY_CAUSE_SENTINEL',out)
        self.assertEqual((log.stat().st_mtime_ns,sha(log.read_bytes())),before)
        d=self.rundir();self.assertEqual(sha(next((d/'PRIOR_G0_20261020_READONLY').glob('*.log')).read_bytes()),before[1])

    def test_j_reentrancy_blocked(self):
        holder=self.box/'hold.ps1'
        holder.write_text("$c=$false;$m=[System.Threading.Mutex]::new($true,'Local\\CDT20_PRE_G06_INTEGRATED_LAUNCHER',[ref]$c);'HELD='+$c;[Console]::Out.Flush();Start-Sleep 25;$m.ReleaseMutex()\n")
        h=subprocess.Popen([PWSH,'-NoProfile','-File',str(holder)],stdout=subprocess.PIPE)
        self.assertEqual(h.stdout.readline().strip(),b'HELD=True')
        try:
            rc,out=self.run_ps(self.launcher())
            self.assertEqual(rc,2,out);self.assertIn('LAUNCHER_ALREADY_RUNNING',out)
        finally:h.wait(60)

if __name__=='__main__':unittest.main(verbosity=2)
