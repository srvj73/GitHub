[CmdletBinding()]
param(
    [ValidateSet('Check','D4','D4Close','D5','CANARY','FULL_PREP','FULL_ADMIT','FULL_READMIT','FULL','Stop')][string]$Stage='Check',
    [Parameter(Mandatory=$true)][string]$ChainFile,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9A-F]{64}$')][string]$ChainSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9A-F]{64}$')][string]$B06Sha256,
    [switch]$Resume,
    [switch]$CloseOnly,
    [string]$Workers='AUTO',
    [switch]$ElevatedChild,
    [string]$ExpectedLauncherSha='',
    [string]$ExpectedEntrySha=''
)
Set-StrictMode -Version 2
$ErrorActionPreference='Stop'
$python='C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$entry=Join-Path $PSScriptRoot 'FULL_RUNNER.py'
function Hash([string]$Path) {
    # PS 5.1 may inherit a PSModulePath that cannot autoload Get-FileHash.
    $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}
function Quoted([string]$Value) {
    if ($Value.IndexOf([char]34) -ge 0 -or $Value.IndexOf([char]0) -ge 0) { throw 'UNSAFE_ARGUMENT' }
    # Native Windows command-line quoting: double the backslashes before closing quote.
    return '"'+[regex]::Replace($Value,'(\\+)$','$1$1')+'"'
}
try {
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'POWERSHELL_51_REQUIRED' }
    if ((Hash $python) -cne '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9') { throw 'PYTHON_IDENTITY' }
    if ($ElevatedChild -and ((Hash $PSCommandPath) -cne $ExpectedLauncherSha -or (Hash $entry) -cne $ExpectedEntrySha)) { throw 'UAC_CODE_DRIFT' }
    $admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($Stage -notin @('Check','D4Close','Stop') -and -not $admin) {
        if ($ElevatedChild) { throw 'UAC_NOT_ELEVATED' }
        $argsLine='-NoProfile -ExecutionPolicy Bypass -File '+(Quoted $PSCommandPath)+' -Stage '+$Stage+
          ' -ChainFile '+(Quoted $ChainFile)+' -ChainSha256 '+$ChainSha256+' -B06Sha256 '+$B06Sha256+
          ' -Workers '+(Quoted $Workers)+' -ElevatedChild -ExpectedLauncherSha '+(Hash $PSCommandPath)+' -ExpectedEntrySha '+(Hash $entry)
        if ($Resume) { $argsLine+=' -Resume' }
        if ($CloseOnly) { $argsLine+=' -CloseOnly' }
        $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $child=Start-Process -FilePath $ps -ArgumentList $argsLine -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        $child.Refresh()
        if ($null -eq $child.ExitCode) { throw 'UAC_EXIT_UNKNOWN' }
        exit [int]$child.ExitCode
    }
    $argv=@('-I','-X','utf8','-B',$entry,'--stage',$Stage,'--chain-file',$ChainFile,
             '--chain-sha256',$ChainSha256,'--b06-sha256',$B06Sha256,'--workers',$Workers)
    if ($Resume) { $argv+='--resume' }
    if ($CloseOnly) { $argv+='--close-only' }
    & $python @argv
    if ($null -eq $LASTEXITCODE) { throw 'RUNNER_EXIT_UNKNOWN' }
    exit [int]$LASTEXITCODE
} catch {
    Write-Output ('TICKSTORE_FULL_LAUNCHER_BLOCKED='+$_.Exception.Message)
    exit 2
}
