from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
runner=(HERE/'tickstore_serial_runner.py').read_text(encoding='utf-8')
ps=(HERE/'RUN_WINDOWS_GATE_B.ps1').read_text(encoding='utf-8-sig')
pre=(HERE/'WINDOWS_GATE_B_PREFLIGHT_V005.py').read_text(encoding='utf-8')
launch=(HERE/'RUN_FROM_DOWNLOADS_PLAN_ONLY.ps1.txt').read_text(encoding='utf-8-sig')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()
checks={
 'RUNNER_SCHEMA_R8':'RUNNER_SCHEMA="TICKSTORE_SERIAL_RUNNER_V001R8_GATE_B_WINDOWS"' in runner,
 'REF_FROZEN':sha(HERE/'pts2g_reference.py')=='74EE141B014DE7A9F9C401C2B3C5AF6BF72E5D7D80F49E67F9D9032338480165',
 'LEDGER_FROZEN':sha(HERE/'OUT_P4A_R3_FULL_HISTORY_COMPAT.zip')=='27FF5A0FE47F3DDC5FD63F6371CCF0EDA8124E0E5D504A8F0756A4DF0DB9C3CA',
 'PILOT_TRUE':'PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True' in runner,
 'FULL_FALSE':'FULL_HISTORY_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False' in runner,
 'FROZEN_DATES':'FROZEN_PILOT_DATES=("20260731","20211022")' in runner,
 'STDLIB_ZSTD_PROOF':'WINDOWS_PILOT_ZSTD_NOT_FROM_STDLIB' in runner and 'sysconfig.get_path("stdlib")' in runner,
 'PREFLIGHT_V5':'WINDOWS_PREFLIGHT_SCHEMA="TICKSTORE_WINDOWS_GATE_B_PREFLIGHT_V005"' in runner,
 'PREFLIGHT_SCRIPT_HASH_BOUND':'"preflight_sha256":ids["preflight_sha256"]' in runner,
 'REPORT_RESULTS_REQUIRED':'WINDOWS_PREFLIGHT_RESULTS_MISSING' in runner and 'REQUIRED_PREFLIGHT_PASS_RESULTS' in runner,
 'REPORT_DATE_BOUND':'WINDOWS_PREFLIGHT_PILOT_DATE_MISMATCH' in runner,
 'REPORT_VOLUME_BOUND':'WINDOWS_PREFLIGHT_SOURCE_DEST_SCRATCH_VOLUME_MISMATCH' in runner,
 'OWNER_GATE_JSON_BOUND':'PILOT_OWNER_GATE_BINDING_MISMATCH:' in runner and 'preflight_report_sha256' in runner,
 'FRESH_PREFLIGHT_RUNTIME':'run_fresh_windows_preflight(' in runner and 'FRESH_WINDOWS_PREFLIGHT_FAILED' in runner,
 'NO_AUTOCPU': all(x not in runner+ps for x in ('ThreadPoolExecutor','ProcessPoolExecutor','multiprocessing','Start-Job')),
 'NO_CSV_DELETE':'CSV_DELETION=NO' in runner and 'Remove-Item' not in ps,
 'PS_PY314':'-3.14' in ps,
 'PS_NO_FULL_MODE':"'FULL'" not in ps and '--full-history' not in ps,
 'PS_FROZEN_MODES':"ValidateSet('PLAN','PREFLIGHT_LOW','PILOT_LOW','PREFLIGHT_HIGH','PILOT_HIGH')" in ps and '$DateKey=' in ps,
 'NO_YES_GATE_INCLUDED':'"authorized": false' in (HERE/'PILOT_OWNER_GATE_TEMPLATE_DO_NOT_USE.json').read_text(),
 'PREFLIGHT_CORE_TESTS':all(x in pre for x in ('hardlink_alias','junction_reparse','alias_8dot3','createfile_share_denial','live_ancestor_rename_denial','transient_external_denial','single_writer')),
 'PREFLIGHT_PATH_VOLUME_BINDING':all(x in pre for x in ('source_volume','dest_volume','scratch_volume','source_root','dest_root')),
 'WINDOWS_ANCESTOR_PIN_LIST_ACCESS':'FILE_LIST_DIRECTORY=0x1' in runner and 'desired=FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES|SYNCHRONIZE' in runner,
 'LAUNCHER_R8_NAME':'TICKSTORE_GATE_B_WINDOWS_V001R8_20260924.zip' in launch,
}
for k,v in checks.items(): print(f'{k}={"PASS" if v else "FAIL"}')
if not all(checks.values()): raise SystemExit(2)
print('STATIC_R8=PASS')
