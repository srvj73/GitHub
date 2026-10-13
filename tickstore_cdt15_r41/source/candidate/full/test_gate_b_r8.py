from pathlib import Path
import hashlib,json,tempfile,types
from unittest.mock import patch
import tickstore_serial_runner as r
BASE=Path(__file__).resolve().parent
LEDGER=BASE/'OUT_P4A_R3_FULL_HISTORY_COMPAT.zip'


def blocked(fn,contains):
    try: fn()
    except r.Blocked as e:
        assert contains in str(e),(contains,str(e)); return str(e)
    raise AssertionError('EXPECTED_BLOCK:'+contains)


def volume(): return {'root':'D:\\','serial':'A1B2C3D4','filesystem':'NTFS'}
def zproof(): return {'module':'compression.zstd','origin':'C:\\Python314\\Lib\\compression\\zstd\\__init__.py','stdlib_root':'C:\\Python314\\Lib'}

def complete_report(root:Path,date='20260731'):
    ids=r.file_ids(BASE)
    return {
      'schema':r.WINDOWS_PREFLIGHT_SCHEMA,'status':'PASS','windows_runtime':True,
      'python_3_14_or_newer':True,'native_compression_zstd':True,'core_filesystem_tests':'PASS',
      'pilot_date':date,'runner_sha256':ids['runner_sha256'],'reference_sha256':ids['reference_sha256'],
      'spec_sha256':ids['spec_sha256'],'preflight_sha256':ids['preflight_sha256'],'ledger_sha256':r.sha256_file(LEDGER),
      'source_root':r._norm_binding_path(root/'src'),'dest_root':r._norm_binding_path(root/'dst'),
      'scratch_root':r._norm_binding_path(root/'scratch'),
      'source_volume':volume(),'dest_volume':volume(),'scratch_volume':volume(),
      'zstd_module':'compression.zstd','zstd_origin':zproof()['origin'],'zstd_stdlib_root':zproof()['stdlib_root'],
      'results':{
       'native_zstd_roundtrip':'PASS','hardlink_alias':'PASS','ads':'PASS','junction_reparse':'PASS',
       'symlink':'NOT_PERMITTED_WINERROR_1314','alias_8dot3':'NOT_AVAILABLE_ON_VOLUME',
       'createfile_share_denial':'PASS','live_ancestor_rename_denial':'PASS',
       'transient_external_denial':'PASS','single_writer':'PASS'
      }
    }

def main():
    assert r.PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE is True
    assert r.FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE is False
    assert set(r.FROZEN_PILOT_DATES)=={'20260731','20211022'}
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); (root/'src').mkdir(); (root/'scratch').mkdir()
        fake=complete_report(root); fake.pop('results')
        p=root/'fake.json';p.write_text(json.dumps(fake))
        with patch.object(r,'native_zstd_origin_evidence',return_value=zproof()), patch.object(r,'windows_volume_identity',return_value=volume()):
            blocked(lambda:r.validate_windows_preflight_report(p,LEDGER,root/'src',root/'dst',root/'scratch','20260731'),'WINDOWS_PREFLIGHT_RESULTS_MISSING')
        good=complete_report(root);p.write_text(json.dumps(good))
        with patch.object(r,'native_zstd_origin_evidence',return_value=zproof()), patch.object(r,'windows_volume_identity',return_value=volume()):
            r.validate_windows_preflight_report(p,LEDGER,root/'src',root/'dst',root/'scratch','20260731')
            blocked(lambda:r.validate_windows_preflight_report(p,LEDGER,root/'src',root/'dst',root/'scratch','20211022'),'PILOT_DATE_MISMATCH')
        ids=r.file_ids(BASE)
        gate={'schema':r.OWNER_GATE_SCHEMA,'authorized':True,'pilot_date':'20260731',
              'preflight_report_sha256':r.sha256_file(p),'runner_sha256':ids['runner_sha256'],
              'reference_sha256':ids['reference_sha256'],'spec_sha256':ids['spec_sha256'],'preflight_sha256':ids['preflight_sha256'],'ledger_sha256':r.sha256_file(LEDGER)}
        gp=root/'gate.json';gp.write_text(json.dumps(gate))
        r.require_pilot_owner_gate(gp,p,LEDGER,'20260731')
        gate['pilot_date']='20211022';gp.write_text(json.dumps(gate))
        blocked(lambda:r.require_pilot_owner_gate(gp,p,LEDGER,'20260731'),'PILOT_OWNER_GATE_DATE_MISMATCH')
    # A shadow module outside stdlib cannot satisfy the native provenance proof.
    fakez=types.SimpleNamespace(__name__='compression.zstd',__spec__=types.SimpleNamespace(name='compression.zstd',origin='/tmp/shadow/compression/zstd/__init__.py'))
    blocked(lambda:r.native_zstd_origin_evidence(fakez),'WINDOWS_PILOT_ZSTD_NOT_FROM_STDLIB')
    # An arbitrary ledger date is rejected before any Windows runtime access.
    with patch('sys.argv',['runner','--ledger-zip',str(LEDGER),'--pilot-date','20260923']):
        blocked(r.main,'PILOT_DATE_NOT_FROZEN_GATE_B_CASE')
    # FULL remains hard blocked.
    with tempfile.TemporaryDirectory() as td:
        g=Path(td)/'full.txt';g.write_text('TICKSTORE_FULL_HISTORY_AUTHORIZED=YES\n')
        with patch('sys.argv',['runner','--ledger-zip',str(LEDGER),'--full-history','--full-gate-file',str(g)]):
            blocked(r.main,'FULL_HISTORY_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE')
        runner_text=(BASE/'tickstore_serial_runner.py').read_text(encoding='utf-8')
    assert 'FILE_LIST_DIRECTORY=0x1' in runner_text
    assert 'desired=FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES|SYNCHRONIZE' in runner_text
    print('WINDOWS_ANCESTOR_PIN_ACCESS_R8=PASS')
    print('GATE_B_R8_TESTS=PASS')
    print('FORGED_PREFLIGHT_MINIMAL=BLOCKED')
    print('OWNER_GATE_REPORT_DATE_BINDING=PASS')
    print('SHADOW_ZSTD_ORIGIN=BLOCKED')
    print('FROZEN_PILOT_DATES=PASS')
    print('FULL_HISTORY_HARD_BLOCK=PASS')
if __name__=='__main__':main()
