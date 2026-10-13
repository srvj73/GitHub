# TICKSTORE CDT15 R41 - Windows sandbox qualification bootstrap (Windows PowerShell 5.1).
# Run (no cd needed):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_TICKSTORE_CDT15_R41_QUAL.ps1"
# Effects: creates only run-owned folders
#   C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\R41_QUAL_<timestamp>_<PID>\   (log, receipt, RETURN ZIP)
#   %LOCALAPPDATA%\TICKSTORE_QUAL_R41\R41_QUAL_<timestamp>_<PID>\                 (extracted code, C: sandboxes)
#   D:\TICKSTORE_QUALIFICATION_SANDBOX\R41_QUAL_<timestamp>_<PID>\                (D: sandboxes)
# It never writes D:\Base CSV, %LOCALAPPDATA%\TICKSTORE, MENU.py, the BAT, ACTIVE_DEPLOYMENT or STATE.
[CmdletBinding()]
param()
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$ZipPattern = 'TICKSTORE_CDT15_R41_QUAL_*.zip'
$ExpectedZipName = 'TICKSTORE_CDT15_R41_QUAL_R1_20261013.zip'
$ExpectedZipSha = '3654D59D5A2E7E9CA596C7B5915848CC9C418EB791AF2E16E8E17185E5FB00B5'
$ExpectedZipBytes = 1598904
$ExpectedQualManifestSha = '52A869F36C5B97F0101901BFAA40EB15F68969B479379C950224545A3D5BB73D'
$Downloads = 'C:\Users\silvi\OneDrive\Downloads'
$LogRoot = 'C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS'
$Python = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$PythonSha = '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
$DParent = 'D:\TICKSTORE_QUALIFICATION_SANDBOX'
$CloudFilesTag = [uint32]2415943706  # IO_REPARSE_TAG_CLOUD_6 0x9000601A (OneDrive Files On-Demand)
$utf8 = New-Object Text.UTF8Encoding($false)
$script:RunDir = ''

function Log([string]$Line) {
    Write-Host $Line
    if ($script:RunDir -ne '') { [IO.File]::AppendAllText((Join-Path $script:RunDir 'RUN_LOG.txt'), $Line + "`r`n", $utf8) }
}
function Require([bool]$Condition, [string]$Reason) { if (-not $Condition) { throw $Reason } }
function Sha([string]$Path) {
    $s = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $h = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($h.ComputeHash($s)).Replace('-', '') } finally { $h.Dispose(); $s.Dispose() }
}
function NoReparseBelow([string]$Path, [string[]]$Allowed) {
    $p = [IO.Path]::GetFullPath($Path)
    while ($p) {
        if ([IO.Directory]::Exists($p) -or [IO.File]::Exists($p)) {
            if ((([IO.File]::GetAttributes($p)) -band [IO.FileAttributes]::ReparsePoint) -ne 0 -and -not ($Allowed -contains $p)) {
                throw ('REPARSE_IN_PATH:' + $p)
            }
        }
        $parent = [IO.Directory]::GetParent($p); if ($null -eq $parent) { break }; $p = $parent.FullName
    }
}
function SafeMember([string]$Name) {
    Require ($Name -ne '' -and $Name -notmatch '[:\\]' -and -not $Name.StartsWith('/')) ('ZIP_MEMBER_PATH:' + $Name)
    foreach ($part in $Name.Split('/')) {
        Require ($part -ne '' -and $part -ne '.' -and $part -ne '..' -and $part -notmatch '[ .]$|[\x00-\x1f]' -and
                 $part -notmatch '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') ('ZIP_MEMBER_SEGMENT:' + $Name)
    }
}


$exitCode = 2
try {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class R41Reparse {
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
    $runName = 'R41_QUAL_' + (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
    [IO.Directory]::CreateDirectory($LogRoot) | Out-Null
    NoReparseBelow $LogRoot @('C:\Users\silvi\OneDrive', 'C:\Users\silvi\OneDrive\Downloads')
    $script:RunDir = Join-Path $LogRoot $runName
    Require (-not [IO.Directory]::Exists($script:RunDir)) 'RUN_DIR_COLLISION'
    [IO.Directory]::CreateDirectory($script:RunDir) | Out-Null
    Log ('RESULT_CONTEXT=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compress' + [char]0x00E3 + 'o De Ticks 15')
    Log ('RUN_DIR=' + $script:RunDir)
    Log ('RUN_LOG=' + (Join-Path $script:RunDir 'RUN_LOG.txt'))
    Require ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'POWERSHELL_51_REQUIRED'
    Require ([Environment]::Is64BitProcess) 'POWERSHELL_64BIT_REQUIRED'
    $app = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
    Require ($app -cmatch '^[A-Za-z]:\\[^%]+$' -and -not $app.EndsWith('\')) 'LOCALAPPDATA_INVALID_OR_UNEXPANDED'
    Require ([IO.Path]::GetFullPath($app) -ceq $app) 'LOCALAPPDATA_NOT_CANONICAL'
    Log ('POWERSHELL=' + $PSVersionTable.PSVersion.ToString() + ' LOCALAPPDATA=' + $app)

    # 1. Locate eligible ZIPs in this script's folder and in Downloads (no cwd use).
    $dirs = @($PSScriptRoot, $Downloads) | ForEach-Object { [IO.Path]::GetFullPath($_) } | Select-Object -Unique
    $inputDir = Join-Path $script:RunDir 'INPUT'; [IO.Directory]::CreateDirectory($inputDir) | Out-Null
    $matched = @(); $seen = @(); $n = 0
    foreach ($dir in $dirs) {
        if (-not [IO.Directory]::Exists($dir)) { continue }
        foreach ($f in @(Get-ChildItem -LiteralPath $dir -File -Filter $ZipPattern)) {
            $n++
            $tag = [R41Reparse]::Tag($f.FullName)
            if ($tag -ne 0 -and $tag -ne $CloudFilesTag) { Log ('ZIP_REJECTED_REPARSE_TAG=' + ('0x{0:X8}' -f $tag) + ' ' + $f.FullName); continue }
            # Private copy: hash the bytes actually copied, then re-hash the copy on disk.
            $copy = Join-Path $inputDir ([string]$n + '_' + $f.Name)
            $src = [IO.File]::Open($f.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
            try {
                $dst = [IO.File]::Open($copy, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try { $src.CopyTo($dst); $dst.Flush($true) } finally { $dst.Dispose() }
            } finally { $src.Dispose() }
            $digest = Sha $copy
            $len = (New-Object IO.FileInfo($copy)).Length
            $seen += ($f.FullName + ' SHA256=' + $digest + ' BYTES=' + $len + ' REPARSE_TAG=' + ('0x{0:X8}' -f $tag))
            if ($digest -ceq $ExpectedZipSha -and $len -eq $ExpectedZipBytes) { $matched += $copy }
        }
    }
    foreach ($s in $seen) { Log ('ZIP_CANDIDATE=' + $s) }
    Require ($matched.Count -ge 1) ('QUAL_ZIP_NOT_FOUND_OR_HASH_MISMATCH: expected ' + $ExpectedZipName + ' SHA256=' + $ExpectedZipSha)
    $zipCopy = $matched[0]
    Log ('ZIP_SELECTED_PRIVATE_COPY=' + $zipCopy + ' IDENTICAL_COPIES=' + $matched.Count)

    # 2. Extract into a fresh run-owned, non-synced folder; every member re-verified.
    $work = Join-Path (Join-Path $app 'TICKSTORE_QUAL_R41') $runName
    NoReparseBelow $app @()
    Require (-not [IO.Directory]::Exists($work)) 'WORK_DIR_COLLISION'
    [IO.Directory]::CreateDirectory($work) | Out-Null
    $bundle = Join-Path $work 'X'; [IO.Directory]::CreateDirectory($bundle) | Out-Null
    Add-Type -AssemblyName System.IO.Compression
    $zs = [IO.File]::Open($zipCopy, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $archive = New-Object IO.Compression.ZipArchive($zs, [IO.Compression.ZipArchiveMode]::Read, $false)
        try {
            $names = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
            foreach ($e in $archive.Entries) {
                SafeMember $e.FullName
                Require ($names.Add($e.FullName)) 'ZIP_DUPLICATE_MEMBER'
                $target = Join-Path $bundle ($e.FullName.Replace('/', '\'))
                Require ($target.StartsWith($bundle + '\', [StringComparison]::OrdinalIgnoreCase)) 'ZIP_PATH_ESCAPE'
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
                $in = $e.Open(); $out = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try { $in.CopyTo($out); $out.Flush($true) } finally { $in.Dispose(); $out.Dispose() }
            }
        } finally { $archive.Dispose() }
    } finally { $zs.Dispose() }
    Require ((Sha (Join-Path $bundle 'QUAL_MANIFEST.json')) -ceq $ExpectedQualManifestSha) 'QUAL_MANIFEST_SHA256'
    Log ('EXTRACTED_TO=' + $bundle)

    # 3. Pinned interpreter identity.
    Require ([IO.File]::Exists($Python)) 'PYTHON_314_MISSING'
    Require ((Sha $Python) -ceq $PythonSha) 'PYTHON_IDENTITY'
    Require ([Diagnostics.FileVersionInfo]::GetVersionInfo($Python).ProductVersion -match '^3\.14\.7(?:\D|$)') 'PYTHON_VERSION_3147'
    Log 'PYTHON=PASS 3.14.7 SHA256_PINNED'

    # 4. Driver (its own output is mirrored into RUN_LOG.txt by Python).
    $driver = Join-Path $bundle 'qual\QUAL_DRIVER.py'
    & $Python -I -X utf8 -B $driver --run-dir $script:RunDir --work-root $work --bundle-dir $bundle --d-parent $DParent --ps-version ($PSVersionTable.PSVersion.ToString())
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 2 }
    Log ('QUAL_BOOTSTRAP_DRIVER_EXIT=' + $exitCode)
} catch {
    Log ('QUAL_BOOTSTRAP_BLOCKED=' + $_.Exception.Message)
    Log 'PRODUCTION_MODIFIED=NO (bootstrap writes only run-owned folders); FULL_STARTED=NO'
    $exitCode = 2
}
Log ('RUN_LOG=' + (Join-Path $script:RunDir 'RUN_LOG.txt'))
Log 'Devolva ao engenheiro: o arquivo RETURN_ZIP indicado acima (ou RUN_LOG.txt se nao houver RETURN_ZIP).'
exit $exitCode
