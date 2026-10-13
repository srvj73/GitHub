param(
    [ValidateSet('PLAN','PREFLIGHT_LOW','PILOT_LOW','PREFLIGHT_HIGH','PILOT_HIGH')]
    [string]$Mode='PLAN',
    [string]$SourceRoot='D:\Base CSV\WIN@N',
    [string]$DestRoot='D:\TICKSTORE',
    [string]$ScratchRoot='D:\TICKSTORE_GATE_B_SCRATCH',
    [string]$ReportPath='',
    [string]$GateFile=''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$Here=$PSScriptRoot
$Runner=Join-Path $Here 'tickstore_serial_runner.py'
$Preflight=Join-Path $Here 'WINDOWS_GATE_B_PREFLIGHT_V005.py'
$Ledger=Join-Path $Here 'OUT_P4A_R3_FULL_HISTORY_COMPAT.zip'
foreach($P in @($Runner,$Preflight,$Ledger)){if(-not (Test-Path -LiteralPath $P -PathType Leaf)){throw "REQUIRED_FILE_MISSING=$P"}}
$Py=Get-Command 'py.exe' -ErrorAction Stop
& $Py.Source -3.14 -c "import sys,sysconfig,pathlib; assert sys.version_info >= (3,14); from compression import zstd; p=pathlib.Path(zstd.__spec__.origin).resolve(); s=pathlib.Path(sysconfig.get_path('stdlib')).resolve(); assert p.relative_to(s).parts[:2]==('compression','zstd'); x=b'tickstore'*1000; assert zstd.decompress(zstd.compress(x,level=9))==x; print('PY314_NATIVE_STDLIB_ZSTD=PASS')"
if($LASTEXITCODE -ne 0){throw "PY314_STDLIB_ZSTD_PREFLIGHT_FAIL=$LASTEXITCODE"}
& $Py.Source -3.14 -m py_compile $Runner (Join-Path $Here 'pts2g_reference.py') $Preflight
if($LASTEXITCODE -ne 0){throw "PY_COMPILE_FAIL=$LASTEXITCODE"}
$DateKey=$null
if($Mode -in @('PREFLIGHT_LOW','PILOT_LOW')){$DateKey='20260731'}
if($Mode -in @('PREFLIGHT_HIGH','PILOT_HIGH')){$DateKey='20211022'}
if([string]::IsNullOrWhiteSpace($ReportPath) -and $DateKey){$ReportPath=Join-Path $Here ("WINDOWS_GATE_B_PREFLIGHT_REPORT_${DateKey}.json")}
switch($Mode){
    'PLAN' {
        & $Py.Source -3.14 $Runner --plan --ledger-zip $Ledger
    }
    'PREFLIGHT_LOW' {
        if(Test-Path -LiteralPath $ReportPath){throw "REPORT_ALREADY_EXISTS=$ReportPath"}
        & $Py.Source -3.14 $Preflight --ledger-zip $Ledger --scratch-root $ScratchRoot --report $ReportPath --pilot-date $DateKey --source-root $SourceRoot --dest-root $DestRoot
    }
    'PREFLIGHT_HIGH' {
        if(Test-Path -LiteralPath $ReportPath){throw "REPORT_ALREADY_EXISTS=$ReportPath"}
        & $Py.Source -3.14 $Preflight --ledger-zip $Ledger --scratch-root $ScratchRoot --report $ReportPath --pilot-date $DateKey --source-root $SourceRoot --dest-root $DestRoot
    }
    'PILOT_LOW' {
        if([string]::IsNullOrWhiteSpace($GateFile)){throw 'PILOT_GATE_FILE_REQUIRED'}
        & $Py.Source -3.14 $Runner --pilot-date $DateKey --pilot-gate-file $GateFile --windows-preflight-report $ReportPath --scratch-root $ScratchRoot `
            --ledger-zip $Ledger --source-root $SourceRoot --dest-root $DestRoot
    }
    'PILOT_HIGH' {
        if([string]::IsNullOrWhiteSpace($GateFile)){throw 'PILOT_GATE_FILE_REQUIRED'}
        & $Py.Source -3.14 $Runner --pilot-date $DateKey --pilot-gate-file $GateFile --windows-preflight-report $ReportPath --scratch-root $ScratchRoot `
            --ledger-zip $Ledger --source-root $SourceRoot --dest-root $DestRoot
    }
}
if($LASTEXITCODE -ne 0){throw "TICKSTORE_EXIT_CODE=$LASTEXITCODE"}
