import sys,importlib.util,json
from pathlib import Path
here=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('g0',here/'G0_CDT20_PRE_G06.py');g0=importlib.util.module_from_spec(spec);spec.loader.exec_module(g0)
try:g0.main()
except g0.G0Blocked as e:print('MAIN_REFUSES_NON_WINDOWS='+str(e))
r=g0.qualify(here,native=False);g0.seal(here,r)
print('SANDBOX_G0_RESULT='+r['result'],'SUITES',len(r['suites']),'BLOCKED',r['blocked_suites'])
print('LEGACY_DIAG',r['legacy_context_diagnostic']['status'])
