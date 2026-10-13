[CmdletBinding()]
param(
    [ValidateSet('Check','Monitor','D4','D4Close','D5','CANARY','FULL_PREP','FULL_ADMIT','FULL_READMIT','FULL','Stop')][string]$Stage='Check',
    [Parameter(Mandatory=$true)][string]$ChainFile,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9A-F]{64}$')][string]$ChainSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9A-F]{64}$')][string]$B06Sha256,
    [switch]$Resume,
    [switch]$CloseOnly,
    [string]$Workers='AUTO',
    [switch]$MonitorOnce,
    [ValidateRange(2,3600)][int]$MonitorInterval=10,
    [switch]$ElevatedChild,
    [string]$RunDir='',
    [string]$ExpectedLauncherSha='',
    [string]$ExpectedEntrySha=''
)
Set-StrictMode -Version 2
$ErrorActionPreference='Stop'
$python='C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$entry=Join-Path $PSScriptRoot 'FULL_RUNNER.py'
# Fixed absolute log root (owner rule): never derived from the current directory.
$LogRoot='C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS'
$utf8=New-Object Text.UTF8Encoding($false)
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
function NoReparse([string]$Path) {
    $p=[IO.Path]::GetFullPath($Path)
    while ($p) {
        if ([IO.File]::Exists($p) -or [IO.Directory]::Exists($p)) {
            if (([IO.File]::GetAttributes($p) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                # OneDrive turns synced folders into Cloud Files directories (tag 0x9000x01A,
                # observed natively on TICKSTORE_RUNS in R41R1). Accept only that tag, only for
                # directories under the OneDrive root; junctions/symlinks stay rejected.
                $under=($p -ieq 'C:\Users\silvi\OneDrive' -or $p.StartsWith('C:\Users\silvi\OneDrive\',[StringComparison]::OrdinalIgnoreCase))
                $tag=[TickstoreReparseTag]::Tag($p)
                if (-not ($under -and [IO.Directory]::Exists($p) -and (($tag -band [uint32]4294905855) -eq [uint32]2415919130))) {
                    throw ('LOG_REPARSE:'+$p+' TAG='+('0x{0:X8}' -f $tag))
                }
            }
        }
        $parent=[IO.Directory]::GetParent($p)
        if ($null -eq $parent) { break }; $p=$parent.FullName
    }
}
if (-not ('TickstoreReparseTag' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class TickstoreReparseTag {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct WIN32_FIND_DATA {
        public uint dwFileAttributes; public long ftCreationTime; public long ftLastAccessTime; public long ftLastWriteTime;
        public uint nFileSizeHigh; public uint nFileSizeLow; public uint dwReserved0; public uint dwReserved1;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string cFileName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 14)] public string cAlternateFileName;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr FindFirstFileW(string name, out WIN32_FIND_DATA data);
    [DllImport("kernel32.dll")] static extern bool FindClose(IntPtr h);
    public static uint Tag(string path) {
        WIN32_FIND_DATA d; IntPtr h = FindFirstFileW(path, out d);
        if (h == new IntPtr(-1)) { throw new System.ComponentModel.Win32Exception(); }
        FindClose(h);
        return (d.dwFileAttributes & 0x400) != 0 ? d.dwReserved0 : 0;
    }
}
'@
}
function NewRunDir([string]$Mode) {
    [IO.Directory]::CreateDirectory($LogRoot) | Out-Null
    NoReparse $LogRoot
    $name=$Mode+'_'+(Get-Date).ToString('yyyyMMdd_HHmmss_fff')+'_'+$PID
    $dir=Join-Path $LogRoot $name
    if ([IO.Directory]::Exists($dir) -or [IO.File]::Exists($dir)) { throw 'RUN_DIR_COLLISION' }
    [IO.Directory]::CreateDirectory($dir) | Out-Null
    return $dir
}
function Log([string]$Line) {
    Write-Output $Line
    if ($script:RunDir -ne '') { [IO.File]::AppendAllText((Join-Path $script:RunDir 'RUN_LOG.txt'),$Line+"`r`n",$utf8) }
}
try {
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'POWERSHELL_51_REQUIRED' }
    if ($ElevatedChild) {
        if ((Hash $PSCommandPath) -cne $ExpectedLauncherSha -or (Hash $entry) -cne $ExpectedEntrySha) { throw 'UAC_CODE_DRIFT' }
        # The non-elevated parent created this folder; accept only a direct child of the fixed root.
        $full=[IO.Path]::GetFullPath($RunDir)
        if ([IO.Path]::GetDirectoryName($full) -cne $LogRoot -or -not [IO.Directory]::Exists($full) -or
            [IO.Path]::GetFileName($full) -cnotmatch ('^'+$Stage+'_[0-9]{8}_[0-9]{6}_[0-9]{3}_[0-9]+$')) { throw 'RUN_DIR_NOT_RUN_OWNED' }
        NoReparse $full
        $script:RunDir=$full
    } else {
        $script:RunDir=NewRunDir $Stage
    }
    Log ('RESULT_CONTEXT=TICKSTORE FULL RUNNER R41 | STAGE='+$Stage)
    Log ('RUN_DIR='+$script:RunDir)
    Log ('RUN_LOG='+(Join-Path $script:RunDir 'RUN_LOG.txt'))
    if ((Hash $python) -cne '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9') { throw 'PYTHON_IDENTITY' }
    $admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    # Stop opens the elevated runner's Global named event (high integrity), so it is elevated too.
    if ($Stage -notin @('Check','Monitor','D4Close') -and -not $admin) {
        if ($ElevatedChild) { throw 'UAC_NOT_ELEVATED' }
        $argsLine='-NoProfile -ExecutionPolicy Bypass -File '+(Quoted $PSCommandPath)+' -Stage '+$Stage+
          ' -ChainFile '+(Quoted $ChainFile)+' -ChainSha256 '+$ChainSha256+' -B06Sha256 '+$B06Sha256+
          ' -Workers '+(Quoted $Workers)+' -RunDir '+(Quoted $script:RunDir)+
          ' -ElevatedChild -ExpectedLauncherSha '+(Hash $PSCommandPath)+' -ExpectedEntrySha '+(Hash $entry)
        if ($Resume) { $argsLine+=' -Resume' }
        if ($CloseOnly) { $argsLine+=' -CloseOnly' }
        $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        Log 'UAC_ELEVATION=REQUESTED WINDOW=VISIBLE (progress bar, ETA and Ctrl+C SAFE_STOP live in that window)'
        # Visible window: the operator sees PROGRESS/ETA and can press Ctrl+C for SAFE_STOP.
        $child=Start-Process -FilePath $ps -ArgumentList $argsLine -Verb RunAs -WindowStyle Normal -Wait -PassThru
        $child.Refresh()
        if ($null -eq $child.ExitCode) { throw 'UAC_EXIT_UNKNOWN' }
        Log ('ELEVATED_CHILD_EXIT_CODE='+[int]$child.ExitCode)
        Log ('RUN_LOG='+(Join-Path $script:RunDir 'RUN_LOG.txt'))
        exit [int]$child.ExitCode
    }
    $argv=@('-I','-X','utf8','-B',$entry,'--stage',$Stage,'--chain-file',$ChainFile,
             '--chain-sha256',$ChainSha256,'--b06-sha256',$B06Sha256,'--workers',$Workers,
             '--log-file',(Join-Path $script:RunDir 'RUN_LOG.txt'),'--monitor-interval',[string]$MonitorInterval)
    if ($Resume) { $argv+='--resume' }
    if ($CloseOnly) { $argv+='--close-only' }
    if ($MonitorOnce) { $argv+='--monitor-once' }
    & $python @argv
    $code=$LASTEXITCODE
    if ($null -eq $code) { throw 'RUNNER_EXIT_UNKNOWN' }
    Log ('TICKSTORE_FULL_LAUNCHER_EXIT_CODE='+[int]$code)
    if ($ElevatedChild) {
        Write-Output 'Pressione Enter para fechar esta janela elevada (o log permanece em RUN_LOG.txt).'
        [void][Console]::ReadLine()
    }
    exit [int]$code
} catch {
    try { Log ('TICKSTORE_FULL_LAUNCHER_BLOCKED='+$_.Exception.Message) } catch { Write-Output ('TICKSTORE_FULL_LAUNCHER_BLOCKED='+$_.Exception.Message) }
    if ($ElevatedChild) { [void][Console]::ReadLine() }
    exit 2
}
