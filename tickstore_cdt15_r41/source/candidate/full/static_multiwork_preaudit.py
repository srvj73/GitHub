import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WRAPPER=ROOT/'tickstore_full_multiwork.py'
CORE=ROOT/'tickstore_serial_runner.py'
LAUNCHER=ROOT/'run_tickstore_full_multiwork_r9.ps1'
TEMPLATE=ROOT/'FULL_MULTIWORK_OWNER_GATE_TEMPLATE_DO_NOT_USE.json'
PREFLIGHT=ROOT/'RUN_WINDOWS_MULTIWORK_PREFLIGHT.ps1'

checks={}
checks['CORE_RC1_FROZEN']=hashlib.sha256(CORE.read_bytes()).hexdigest().upper()=='D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0'
text=WRAPPER.read_text(encoding='utf-8')
tree=ast.parse(text)
# R41: children start through the native Job (KILL_ON_JOB_CLOSE) wrapper.
pc=(ROOT/'FULL_PROCESS_CONTROL.py').read_text(encoding='utf-8')
checks['SPAWN_MULTIPROCESS']= 'mp.get_context("spawn")' in text and 'job.start(ctx' in text and 'ctx.Process(' in pc and '0x2000' in pc
checks['AUTO_WORKERS_PRESENT']='WORKERS_EFFECTIVE=' in text and 'choose_workers(' in text
checks['MAX_WORKERS_22']='DEFAULT_MAX_WORKERS = 22' in text and 'cpu_budget = max(1, cpu - 2)' in text
checks['EXPLICIT_WORKERS_RAM_GATED']='WORKER_COUNT_EXCEEDS_RAM_BUDGET' in text
checks['GROUP_SAFE_STOP']='SAFE_STOP=GROUP_OR_SCAN_CHUNK_BOUNDARY' in text and 'stop_event.is_set()' in text
checks['SCRATCH_RESUME']='VALIDATED_PENDING_PUBLISH' in text and 'completed_groups' in text
checks['CANONICAL_SINGLE_WRITER']='core.acquire_lock(dest_root)' in text and 'PUBLICATION=DEDICATED_SINGLE_WRITER_PROCESS_AFTER_MONTH_SHA_VERIFIED' in text
checks['PARENT_MONTH_PIN_CONTINUOUS']='class ParentMonthPin' in text and 'source_pin=True' in text and 'sealed_pins[month_id]=parent_pin' in text
checks['FINAL_RECONCILIATION']='core.reconcile_full_readonly(' in text and 'FULL_SOURCE_CONTINUOUS_PIN_SEAL=PASS' in text
# R41: administrative owner gates are revoked; the technical release chain is mandatory.
checks['LEGACY_GATES_REVOKED']='LEGACY_ADMINISTRATIVE_OWNER_GATE_REVOKED' in text and 'core.validate_full_owner_gate(' not in text
checks['TECHNICAL_CHAIN_REQUIRED']='TECHNICAL_RELEASE_CHAIN_REQUIRED' in text and 'ReleaseChain(chain_file, chain_sha256, b06_sha256' in text
checks['ADMITTED_ENTRY_ONLY']='def _execute_admitted_multiwork(' in text and 'admission.validate_full(core_bindings' in text
checks['AUTOCPU_PROCESS_AVAILABLE']='def available_logical_cpus()' in text and 'process_cpu_count' in text and 'cpu = available_logical_cpus()' in text
checks['WATCHDOG_MAIN_LOOP']='class MainLoopWatchdog' in text and 'SAFE_STOP_REASON=WATCHDOG_MAIN_LOOP_STALL' in text
checks['HEARTBEAT_LOOP_TICK']='loop_tick_unix_ns=time.time_ns()' in text
checks['NO_THREADPOOL']='ThreadPoolExecutor' not in text and 'ProcessPoolExecutor' not in text
checks['NO_SOURCE_DELETE_OPTION']='--delete' not in text.lower()
checks['NO_CSV_DELETE_AUTH']='CSV_DELETION_AUTHORIZED=YES' not in text
checks['PROGRESS_BAR']='PROGRESS ' in text and 'SOURCE_MIB_S=' in text and 'ETA_SCAN=' in text and 'BUILDING=' in text
checks['PREVIOUS_SERIAL_RESUME']='PRE_MULTIWORK_RECOVERY' in text and 'def _recover_full_serial_day' in text and 'core.run_one_day(' not in text
checks['MANIFEST_NOT_DAY_STATE']='def _day_state_present' in text and '"manifest"' not in text[text.index('def _day_state_present'):text.index('def _canonical_transient_dates')]

checks['ONE_SOURCE_PASS']='SOURCE_PASS=ONE_PHYSICAL_PASS_PER_MONTH' in text and 'class StreamingMonthSource' in text
checks['NO_WORKER_PREHASH']='core.FullSerialMonth(' not in text and '.hash_all(' not in text
checks['NO_DAY_ACK_BARRIER']='DAY_READY' not in text and 'WORKER_BAD_ACK' not in text and 'WORKER_DAY_ACK_BARRIER=NO' in text
checks['MONTH_SHA_BEFORE_PUBLISH']='MONTH_VERIFIED' in text and 'SOURCE_SHA256_MISMATCH_SINGLE_PASS' in text
checks['LEGACY_SCRATCH_COMPAT']='FULL_MULTIWORK_RC2R3' in text and 'SCRATCH_REVISION_CONFLICT' in text

checks['DEDICATED_PUBLISHER_PROCESS']='def _publisher_main(' in text and 'TICKSTORE-RC4R2-PUBLISHER' in text
checks['PUBLICATION_OVERLAP']='PUBLICATION_OVERLAPS_WORKER_BUILD=YES' in text and 'MONTH_VERIFIED_QUEUED' in text
checks['BOUNDED_PROCESS_TREE_SHUTDOWN']='SAFE_STOP_JOIN_TIMEOUT_SECONDS = 60.0' in text and 'SAFE_STOP_PROCESS_TREE=PASS' in text and 'SHUTDOWN_PROCESS_TREE_STILL_ALIVE' in text
checks['PREQUEUED_START']='WORKER_START_BARRIER=PREQUEUED_AFTER_PARENT_PIN' in text and 'START_PREQUEUED=YES' in text
checks['RC3_SCRATCH_COMPAT']='FULL_MULTIWORK_RC4R2' in text and 'FULL_MULTIWORK_RC4' in text and 'FULL_MULTIWORK_RC3' in text and 'FULL_MULTIWORK_RC2R3' in text
checks['RC4R2_CURRENT_SCRATCH_NAMESPACE']='current_root=scratch_root / "FULL_MULTIWORK_RC4R2"' in text and '"namespace":"RC4R2"' in text
lt=LAUNCHER.read_text(encoding='utf-8')
for p in ('SourceRoot','DestRoot','ScratchRoot','LedgerZip','ChainFile','ChainSha256','B06Sha256'):
    checks['LAUNCHER_'+p.upper()]=('[Parameter(Mandatory=$true)][string]$'+p) in lt
obj=json.loads(TEMPLATE.read_text(encoding='utf-8'))
checks['TEMPLATE_CLOSED']=obj.get('authorized') is False
checks['TEMPLATE_SCHEMA']=obj.get('schema')=='TICKSTORE_FULL_MULTIWORK_OWNER_GATE_V001'
checks['TEMPLATE_WRAPPER_SCHEMA']=obj.get('wrapper_schema')=='TICKSTORE_R9_FULL_MULTIWORK_RC4R2_V001'
checks['LAUNCHER_NO_HOST_EXIT']='exit $LASTEXITCODE' not in lt and 'TICKSTORE_MULTIWORK_LAUNCHER_RETURN=PASS' in lt
pt=PREFLIGHT.read_text(encoding='utf-8')
checks['PREFLIGHT_NATIVE_STDERR_SAFE']='Start-Process' in pt and 'RedirectStandardError' in pt and 'WINDOWS_MULTIWORK_22_SMOKE' in pt

failed=[k for k,v in checks.items() if not v]
for k in sorted(checks):
    print(f'{k}={"PASS" if checks[k] else "FAIL"}')
if failed:
    raise SystemExit('STATIC_MULTIWORK_PREAUDIT_FAIL:'+','.join(failed))
print('STATIC_MULTIWORK_PREAUDIT=PASS')
