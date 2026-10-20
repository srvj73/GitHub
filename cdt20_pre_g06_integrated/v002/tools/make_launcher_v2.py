import hashlib,json
from pathlib import Path
S=Path(__file__).resolve().parents[1]
t=S/'build2/out/CDT20_PRE_G06_INTEGRATED_TRANSPORT_V002_20261020.zip';h=hashlib.sha256(t.read_bytes()).hexdigest().upper()
src=(S/'succ/launcher/RUN_CDT20_PRE_G06_INTEGRATED_20261020.ps1').read_text(encoding='utf-8-sig')
for a,b in (("$TransportName  = 'CDT20_PRE_G06_INTEGRATED_TRANSPORT_20261020.zip'","$TransportName  = 'CDT20_PRE_G06_INTEGRATED_TRANSPORT_V002_20261020.zip'"),
            ('C:\\Users\\silvi\\OneDrive\\Downloads\\RUN_CDT20_PRE_G06_INTEGRATED_20261020.ps1','C:\\Users\\silvi\\OneDrive\\Downloads\\RUN_CDT20_PRE_G06_INTEGRATED_V002_20261020.ps1'),
            ('__TRANSPORT_SHA256__',h)):
    assert src.count(a)==1,a;src=src.replace(a,b)
out=S/'build2/out/RUN_CDT20_PRE_G06_INTEGRATED_V002_20261020.ps1'
out.write_text(src,encoding='utf-8-sig',newline='\r\n')
test=(S/'tools/launcher_sandbox_test.py').read_text()
for a,b in (("S/'build/out/RUN_CDT20_PRE_G06_INTEGRATED_20261020.ps1'","S/'build2/out/RUN_CDT20_PRE_G06_INTEGRATED_V002_20261020.ps1'"),
            ("S/'build/out/CDT20_PRE_G06_INTEGRATED_TRANSPORT_20261020.zip'","S/'build2/out/CDT20_PRE_G06_INTEGRATED_TRANSPORT_V002_20261020.zip'"),
            ("BASE=S/'launcher_test'","BASE=S/'launcher_test2'")):
    assert test.count(a)==1,a;test=test.replace(a,b)
(S/'tools/launcher_sandbox_test_v2.py').write_text(test)
print('LAUNCHER_V2',hashlib.sha256(out.read_bytes()).hexdigest().upper(),'TRANSPORT',h)
