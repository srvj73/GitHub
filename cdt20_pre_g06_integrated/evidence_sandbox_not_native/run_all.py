import subprocess,sys,re,json
from pathlib import Path
root=Path(sys.argv[1]).resolve()/'implementation_v001'
files=sorted((root/'tests').glob('test_*.py'))+sorted((root/'candidate/full').glob('test_*.py'))+[root/'candidate/adapter/adapter_tests.py']
out={}
for f in files:
    try:p=subprocess.run([sys.executable,'-E','-B',str(f)],capture_output=True,timeout=600,cwd=str(f.parent))
    except subprocess.TimeoutExpired:out[f.name]='TIMEOUT';continue
    d=p.stdout+p.stderr;ran=re.findall(rb'Ran (\d+) test',d);tail=d.strip().splitlines()[-1].decode(errors='replace') if d.strip() else ''
    out[f.name]=f'rc={p.returncode} ran={ran[-1].decode() if ran else "?"} {tail[:80]}'
print(json.dumps(out,indent=0))
