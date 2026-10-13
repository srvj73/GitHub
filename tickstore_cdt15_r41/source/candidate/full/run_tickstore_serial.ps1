param(
    [ValidateSet('PLAN','PREFLIGHT','PILOT_LOW','PILOT_HIGH')]
    [string]$Mode='PLAN',
    [string]$SourceRoot='D:\Base CSV\WIN@N',
    [string]$DestRoot='D:\TICKSTORE',
    [string]$ScratchRoot='D:\TICKSTORE_GATE_B_SCRATCH',
    [string]$ReportPath='',
    [string]$GateFile='',
    [string]$DateKey=''
)
$ErrorActionPreference='Stop'
$Delegate=Join-Path $PSScriptRoot 'RUN_WINDOWS_GATE_B.ps1'
if(-not (Test-Path -LiteralPath $Delegate -PathType Leaf)){throw "GATE_B_LAUNCHER_MISSING=$Delegate"}
& $Delegate -Mode $Mode -SourceRoot $SourceRoot -DestRoot $DestRoot -ScratchRoot $ScratchRoot -ReportPath $ReportPath -GateFile $GateFile -DateKey $DateKey
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
