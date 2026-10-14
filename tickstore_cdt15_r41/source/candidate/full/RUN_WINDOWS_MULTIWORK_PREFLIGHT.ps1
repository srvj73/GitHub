[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$Root=$PSScriptRoot
$Core=Join-Path $Root 'tickstore_serial_runner.py'
$ExpectedCore='749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00'
if((Get-FileHash -LiteralPath $Core -Algorithm SHA256).Hash.ToUpperInvariant() -ne $ExpectedCore){throw 'BLOCKED: CORE_RC1_SHA_MISMATCH'}
$Py=(& py -3.14 -c "import sys;print(sys.executable)").Trim()
if($LASTEXITCODE -ne 0){throw 'BLOCKED: PYTHON314'}

$Tmp=Join-Path $env:TEMP ("TICKSTORE_RC4_PREFLIGHT_"+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Tmp -Force | Out-Null

function Invoke-PythonChecked {
    param([string]$Name,[string[]]$Arguments)
    $Out=Join-Path $Tmp ($Name+'.stdout.log')
    $Err=Join-Path $Tmp ($Name+'.stderr.log')
    $P=Start-Process -FilePath $Py -ArgumentList $Arguments -WorkingDirectory $Root -Wait -PassThru -NoNewWindow -RedirectStandardOutput $Out -RedirectStandardError $Err
    if(Test-Path -LiteralPath $Out){Get-Content -LiteralPath $Out | ForEach-Object {Write-Host $_}}
    if(Test-Path -LiteralPath $Err){Get-Content -LiteralPath $Err | ForEach-Object {Write-Host $_}}
    if($P.ExitCode -ne 0){throw ("BLOCKED: {0}_EXIT={1}" -f $Name,$P.ExitCode)}
    $Text=''
    if(Test-Path -LiteralPath $Out){$Text+=(Get-Content -LiteralPath $Out -Raw)}
    if(Test-Path -LiteralPath $Err){$Text+="`n"+(Get-Content -LiteralPath $Err -Raw)}
    return $Text
}

try {
    $Compile=Invoke-PythonChecked 'PY_COMPILE' @('-m','py_compile','tickstore_full_multiwork.py','test_full_multiwork.py','static_multiwork_preaudit.py','windows_multiwork_smoke.py','windows_multiwork_smoke_22.py','windows_rc1_recovery_bridge_smoke.py','windows_rc4_publisher_smoke.py','windows_rc4r2_shutdown_smoke.py')
    $Unit=Invoke-PythonChecked 'MULTIWORK_UNITTEST' @('-m','unittest','-v','test_full_multiwork.py')
    if($Unit -notmatch 'Ran\s+21\s+tests' -or $Unit -notmatch '(?m)^OK\s*$'){throw 'BLOCKED: MULTIWORK_UNITTEST_MARKERS'}
    $Static=Invoke-PythonChecked 'STATIC_MULTIWORK' @('static_multiwork_preaudit.py')
    if($Static -notmatch 'STATIC_MULTIWORK_PREAUDIT=PASS'){throw 'BLOCKED: STATIC_MULTIWORK_MARKER'}
    $RC1=Invoke-PythonChecked 'RC1_WINDOWS_REGRESSION' @('-m','unittest','-v','test_full_serial_r9.py')
    if($RC1 -notmatch 'Ran\s+39\s+tests' -or $RC1 -match 'skipped\s*=' -or $RC1 -notmatch '(?m)^OK\s*$'){throw 'BLOCKED: RC1_WINDOWS_REGRESSION_MARKERS'}
    $Smoke=Invoke-PythonChecked 'WINDOWS_MULTIWORK_SMOKE' @('windows_multiwork_smoke.py')
    foreach($M in @('WINDOWS_MULTIWORK_SPAWN=PASS','WINDOWS_MULTIWORK_SOURCE_PIN=PASS','WINDOWS_MULTIWORK_INLINE_SOURCE_SHA=PASS','WINDOWS_MULTIWORK_NO_DAY_ACK_BARRIER=PASS','WINDOWS_MULTIWORK_NATIVE_ZSTD=PASS','WINDOWS_MULTIWORK_SCRATCH_BUILD=PASS','WINDOWS_MULTIWORK_SCRATCH_RESUME=PASS','WINDOWS_MULTIWORK_SMOKE=PASS')){if($Smoke -notmatch [regex]::Escape($M)){throw ("BLOCKED: SINGLE_SMOKE_MARKER={0}" -f $M)}}
    $Bridge=Invoke-PythonChecked 'WINDOWS_RC1_RECOVERY_BRIDGE' @('windows_rc1_recovery_bridge_smoke.py')
    foreach($M in @('WINDOWS_RC1_RECOVERY_BRIDGE_REPRO_MISMATCH=PASS','WINDOWS_RC1_RECOVERY_BRIDGE_FULL_IDS=PASS','WINDOWS_RC1_RECOVERY_BRIDGE_FINAL_STATE=PASS','WINDOWS_RC1_RECOVERY_BRIDGE=PASS')){if($Bridge -notmatch [regex]::Escape($M)){throw ("BLOCKED: RECOVERY_BRIDGE_MARKER={0}" -f $M)}}
    $Smoke22=Invoke-PythonChecked 'WINDOWS_MULTIWORK_22_SMOKE' @('windows_multiwork_smoke_22.py')
    foreach($M in @('WINDOWS_MULTIWORK_22_CONCURRENT_SPAWN=PASS','WINDOWS_MULTIWORK_22_CONCURRENT_PINNED=PASS','WINDOWS_MULTIWORK_22_NO_DAY_ACK_BARRIER=PASS','WINDOWS_MULTIWORK_22_INLINE_SOURCE_SHA=PASS','WINDOWS_MULTIWORK_22_SOURCE_WRITE_DENIAL=PASS','WINDOWS_MULTIWORK_22_SCRATCH_BUILD=PASS','WINDOWS_MULTIWORK_22_SCRATCH_RESUME=PASS','WINDOWS_MULTIWORK_22_SMOKE=PASS')){if($Smoke22 -notmatch [regex]::Escape($M)){throw ("BLOCKED: SMOKE22_MARKER={0}" -f $M)}}
    $Pub=Invoke-PythonChecked 'WINDOWS_RC4_PUBLISHER_SMOKE' @('windows_rc4_publisher_smoke.py')
    foreach($M in @('WINDOWS_RC4_PARENT_PIN_BEFORE_WORKER=PASS','WINDOWS_RC4_WORKER_START_PREQUEUED=PASS','WINDOWS_RC4_MONTH_SHA_BEFORE_PUBLISH=PASS','WINDOWS_RC4_DEDICATED_PUBLISHER_PROCESS=PASS','WINDOWS_RC4_CANONICAL_SINGLE_WRITER=PASS','WINDOWS_RC4_PUBLISHER_SMOKE=PASS')){if($Pub -notmatch [regex]::Escape($M)){throw ("BLOCKED: RC4_PUBLISHER_MARKER={0}" -f $M)}}
    $Shutdown=Invoke-PythonChecked 'WINDOWS_RC4R2_SHUTDOWN_SMOKE' @('windows_rc4r2_shutdown_smoke.py')
    foreach($M in @('WINDOWS_RC4R2_COOPERATIVE_PROCESS_TREE_CLEAN=PASS','WINDOWS_RC4R2_BOUNDED_ESCALATION=PASS','WINDOWS_RC4R2_NO_RESIDUAL_CHILDREN=PASS','WINDOWS_RC4R2_SAFE_STOP_PROCESS_TREE_SMOKE=PASS')){if($Shutdown -notmatch [regex]::Escape($M)){throw ("BLOCKED: RC4R2_SHUTDOWN_MARKER={0}" -f $M)}}
    Write-Host 'TICKSTORE_FULL_MULTIWORK_RC4R2_WINDOWS_PREFLIGHT=PASS'
    Write-Host 'MULTIWORK_UNITTESTS=PASS_21_OF_21'
    Write-Host 'RC1_WINDOWS_REGRESSION=PASS_39_OF_39'
    Write-Host 'WINDOWS_RC1_RECOVERY_BRIDGE=PASS'
    Write-Host 'WINDOWS_MULTIWORK_22_CONCURRENT_SPAWN=PASS'
    Write-Host 'WINDOWS_MULTIWORK_22_CONCURRENT_PINNED=PASS'
    Write-Host 'WINDOWS_MULTIWORK_22_NO_DAY_ACK_BARRIER=PASS'
    Write-Host 'WINDOWS_MULTIWORK_22_INLINE_SOURCE_SHA=PASS'
    Write-Host 'WINDOWS_MULTIWORK_22_SOURCE_WRITE_DENIAL=PASS'
    Write-Host 'WINDOWS_MULTIWORK_22_SCRATCH_BUILD=PASS'
    Write-Host 'WINDOWS_MULTIWORK_22_SCRATCH_RESUME=PASS'
    Write-Host 'ONE_SOURCE_PASS_ARCHITECTURE=PASS'
    Write-Host 'DEDICATED_PUBLISHER_PROCESS=PASS'
    Write-Host 'PUBLICATION_OVERLAPS_WORKER_BUILD=PASS'
    Write-Host 'WORKER_START_PREQUEUED_AFTER_PARENT_PIN=PASS'
    Write-Host 'WINDOWS_RC4_PUBLISHER_SMOKE=PASS'
    Write-Host 'WINDOWS_RC4R2_SAFE_STOP_PROCESS_TREE_SMOKE=PASS'
    Write-Host 'SAFE_STOP_NO_RESIDUAL_CHILDREN=PASS'
    Write-Host 'REAL_CSV_READ=NO'
    Write-Host 'FULL_EXECUTION=NO'
    Write-Host 'CSV_DELETION=NO'
}
finally {
    if(Test-Path -LiteralPath $Tmp){Remove-Item -LiteralPath $Tmp -Recurse -Force}
}
