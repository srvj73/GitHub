# TICKSTORE CDT15 R47 - Windows QUAL bootstrap (Windows PowerShell 5.1).
# Run (no cd needed):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_TICKSTORE_CDT15_R47_QUAL.ps1"
# Mode B07 (only after an independent B06 PASS) also takes, each digest supplied separately:
#   -ChainFile <EXECUTION_CHAIN until B06> -ChainSha256 <hex> -B06Sha256 <B06 stage receipt hex>
#   -B06Verdict <B06 verdict text> -B06VerdictSha256 <hex> -PolicyRoot <capture 1+1>
#   -PolicyReconciliation <origin record> -PolicyReconciliationSha256 <hex>
# Mode QUAL campaign control: SAFE_STOP = create the file STOP inside the RUN folder printed below
# (the campaign stops between units and closes a partial RETURN ZIP); resume with
#   -ResumeFrom "C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\<RUN>\QUAL_RETURN_<RUN>.zip"
# (same bytes only; units already PASS are reused from that closed ZIP, the campaign RUN_ID is kept).
# Requires Administrator (symlink tests). When started without elevation it opens a new
# elevated window of itself (UAC prompt) and the non-elevated run ends with exit code 3.
# Effects: creates only run-owned folders
#   C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\R47_QUAL_<timestamp>_<PID>\   (log, receipt, RETURN ZIP)
#   %LOCALAPPDATA%\TICKSTORE_QUAL_R47\R47_QUAL_<timestamp>_<PID>\                 (extracted code, C: sandboxes)
#   D:\TICKSTORE_QUALIFICATION_SANDBOX\R47_QUAL_<timestamp>_<PID>\                (D: sandboxes; QUAL mode only)
# It never writes D:\Base CSV, %LOCALAPPDATA%\TICKSTORE, MENU.py, the BAT, ACTIVE_DEPLOYMENT or STATE.
[CmdletBinding()]
param(
    [string]$ChainFile = '',
    [ValidatePattern('^$|^[0-9A-F]{64}$')][string]$ChainSha256 = '',
    [ValidatePattern('^$|^[0-9A-F]{64}$')][string]$B06Sha256 = '',
    [string]$B06Verdict = '',
    [ValidatePattern('^$|^[0-9A-F]{64}$')][string]$B06VerdictSha256 = '',
    [string]$PolicyRoot = '',
    [string]$PolicyReconciliation = '',
    [ValidatePattern('^$|^[0-9A-F]{64}$')][string]$PolicyReconciliationSha256 = '',
    [string]$ResumeFrom = ''
)
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$Mode = 'QUAL'
$ZipPattern = 'TICKSTORE_CDT15_R47_QUAL_*.zip'
$ExpectedZipName = 'TICKSTORE_CDT15_R47_QUAL_20261014.zip'
$ExpectedZipSha = 'FF94A48CA4DA3BD47747A4509D54A410531AD903C230126A73D8F90B9E47E9DC'
$ExpectedZipBytes = 3782456
$ExpectedQualManifestSha = '33CEEFF83156C14C7DEF7B905905C5F8C16C0393445E500E828E3CF364323479'
$Downloads = 'C:\Users\silvi\OneDrive\Downloads'
$LogRoot = 'C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS'
$Python = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$PythonSha = '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
$DParent = 'D:\TICKSTORE_QUALIFICATION_SANDBOX'
$CloudFilesMask = [uint32]4294905855; $CloudFilesTag = [uint32]2415919130  # IO_REPARSE_TAG_CLOUD_* 0x9000x01A (OneDrive)
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
function IsOneDriveCloudDir([string]$p) {
    # OneDrive marks synced folders as reparse points (Cloud Files). Such a folder is
    # accepted only under the OneDrive root, only as a directory, and only when the
    # object resolves to itself: a junction/symlink resolves elsewhere and is rejected.
    if (-not [IO.Directory]::Exists($p)) { return $false }
    if (-not ($p -ieq 'C:\Users\silvi\OneDrive' -or $p.StartsWith('C:\Users\silvi\OneDrive\', [StringComparison]::OrdinalIgnoreCase))) { return $false }
    return ([R41Reparse]::FinalPath($p) -ieq $p)
}
function NoReparseBelow([string]$Path, [string[]]$Allowed) {
    $p = [IO.Path]::GetFullPath($Path)
    while ($p) {
        if ([IO.Directory]::Exists($p) -or [IO.File]::Exists($p)) {
            if ((([IO.File]::GetAttributes($p)) -band [IO.FileAttributes]::ReparsePoint) -ne 0 -and -not ($Allowed -contains $p) -and -not (IsOneDriveCloudDir $p)) {
                throw ('REPARSE_IN_PATH:' + $p + ' TAG=' + ('0x{0:X8}' -f [R41Reparse]::Tag($p)) + ' FINAL=' + [R41Reparse]::FinalPath($p))
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
using System.Text;
public static class R41Reparse {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateFileW(string name, uint access, uint share, IntPtr sa, uint disp, uint flags, IntPtr tpl);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern uint GetFinalPathNameByHandleW(IntPtr h, StringBuilder buf, uint len, uint flags);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetFileInformationByHandleEx(IntPtr h, int cls, out FILE_ATTRIBUTE_TAG_INFO info, uint size);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [StructLayout(LayoutKind.Sequential)] public struct FILE_ATTRIBUTE_TAG_INFO { public uint FileAttributes; public uint ReparseTag; }
    static IntPtr Open(string p, bool noFollow) {
        uint flags = 0x02000000 | (noFollow ? 0x00200000u : 0u);
        IntPtr h = CreateFileW(p, 0x80, 7, IntPtr.Zero, 3, flags, IntPtr.Zero);
        if (h == new IntPtr(-1)) { throw new System.ComponentModel.Win32Exception(); }
        return h;
    }
    // Where the path really resolves after following any reparse point.
    public static string FinalPath(string p) {
        IntPtr h = Open(p, false);
        try {
            StringBuilder b = new StringBuilder(32768);
            uint n = GetFinalPathNameByHandleW(h, b, 32768, 0);
            if (n == 0 || n >= 32768) { throw new System.ComponentModel.Win32Exception(); }
            string s = b.ToString();
            if (s.StartsWith(@"\\?\UNC\")) { return @"\\" + s.Substring(8); }
            if (s.StartsWith(@"\\?\")) { return s.Substring(4); }
            return s;
        } finally { CloseHandle(h); }
    }
    // Diagnostic only: the object's own reparse tag (handle opened without following).
    public static uint Tag(string p) {
        IntPtr h = Open(p, true);
        try {
            FILE_ATTRIBUTE_TAG_INFO i;
            if (!GetFileInformationByHandleEx(h, 9, out i, 8)) { return 0xFFFFFFFF; }
            return (i.FileAttributes & 0x400) != 0 ? i.ReparseTag : 0;
        } finally { CloseHandle(h); }
    }
}
'@
    $runName = 'R47_' + $Mode + '_' + (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
    [IO.Directory]::CreateDirectory($LogRoot) | Out-Null
    NoReparseBelow $LogRoot @()
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
    $bootstrapSha = Sha $PSCommandPath
    Log ('BOOTSTRAP_SHA256=' + $bootstrapSha + ' PARSED_AND_RUNNING_UNDER_PS=' + $PSVersionTable.PSVersion.ToString())
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Log ('ELEVATED=' + $(if ($isAdmin) { 'YES' } else { 'NO' }) + ' MODE=' + $Mode)
    $b07Args = @()
    if ($ResumeFrom -ne '') {
        Require ($Mode -ceq 'QUAL') 'RESUME_ONLY_QUAL_CAMPAIGN'
        $rf = [IO.Path]::GetFullPath($ResumeFrom)
        Require ($rf.StartsWith($LogRoot + '\', [StringComparison]::OrdinalIgnoreCase)) 'RESUME_FROM_OUTSIDE_TICKSTORE_RUNS'
        Require ([IO.Path]::GetFileName($rf) -cmatch '^QUAL_RETURN_[A-Za-z0-9_]+\.zip$' -and [IO.File]::Exists($rf)) 'RESUME_FROM_NOT_A_QUAL_RETURN'
        Require ($rf.IndexOf([char]34) -lt 0) 'RESUME_FROM_QUOTE'
        $b07Args = @('--resume-return', $rf)
        Log ('RESUME_FROM=' + $rf + ' SHA256=' + (Sha $rf))
    }
    if ($Mode -ceq 'B07') {
        foreach ($pair in @(@('ChainFile',$ChainFile),@('ChainSha256',$ChainSha256),@('B06Sha256',$B06Sha256),
                            @('B06Verdict',$B06Verdict),@('B06VerdictSha256',$B06VerdictSha256),@('PolicyRoot',$PolicyRoot),
                            @('PolicyReconciliation',$PolicyReconciliation),@('PolicyReconciliationSha256',$PolicyReconciliationSha256))) {
            Require ($pair[1] -ne '') ('B07_PARAMETER_REQUIRED:' + $pair[0])
            Require ($pair[1].IndexOf([char]34) -lt 0) ('B07_PARAMETER_QUOTE:' + $pair[0])
        }
        $b07Args = @('--b07-chain-file',$ChainFile,'--b07-chain-sha256',$ChainSha256,'--b06-sha256',$B06Sha256,
                     '--b06-verdict',$B06Verdict,'--b06-verdict-sha256',$B06VerdictSha256,'--policy-root',$PolicyRoot,
                     '--policy-reconciliation',$PolicyReconciliation,'--policy-reconciliation-sha256',$PolicyReconciliationSha256)
        Log ('B07_INPUTS=CHAIN:' + $ChainFile + ' CHAIN_SHA256=' + $ChainSha256 + ' B06_SHA256=' + $B06Sha256 + ' B06_VERDICT_SHA256=' + $B06VerdictSha256 + ' POLICY_RECONCILIATION_SHA256=' + $PolicyReconciliationSha256)
    }
    if (-not $isAdmin) {
        Require ([IO.File]::Exists($PSCommandPath)) 'SCRIPT_PATH_UNKNOWN_FOR_ELEVATION'
        Log 'ELEVATION_REQUIRED: abrindo uma nova janela do PowerShell como Administrador (confirme o UAC).'
        $argList = '-NoProfile -ExecutionPolicy Bypass -NoExit -File "' + $PSCommandPath + '"'
        if ($ResumeFrom -ne '') { $argList += ' -ResumeFrom "' + $ResumeFrom + '"' }
        if ($Mode -ceq 'B07') {
            foreach ($pair in @(@('ChainFile',$ChainFile),@('ChainSha256',$ChainSha256),@('B06Sha256',$B06Sha256),
                                @('B06Verdict',$B06Verdict),@('B06VerdictSha256',$B06VerdictSha256),@('PolicyRoot',$PolicyRoot),
                                @('PolicyReconciliation',$PolicyReconciliation),@('PolicyReconciliationSha256',$PolicyReconciliationSha256))) {
                # Native quoting: double trailing backslashes before the closing quote.
                $argList += ' -' + $pair[0] + ' "' + [regex]::Replace($pair[1], '(\\+)$', '$1$1') + '"'
            }
        }
        Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -Verb RunAs -ArgumentList $argList | Out-Null
        throw 'ELEVATED_WINDOW_STARTED'
    }

    # 1. Locate eligible ZIPs in this script's folder and in Downloads (no cwd use).
    $dirs = @($PSScriptRoot, $Downloads) | ForEach-Object { [IO.Path]::GetFullPath($_) } | Select-Object -Unique
    $inputDir = Join-Path $script:RunDir 'INPUT'; [IO.Directory]::CreateDirectory($inputDir) | Out-Null
    $matched = @(); $seen = @(); $n = 0
    foreach ($dir in $dirs) {
        if (-not [IO.Directory]::Exists($dir)) { continue }
        foreach ($f in @(Get-ChildItem -LiteralPath $dir -File -Filter $ZipPattern)) {
            $n++
            $tag = [R41Reparse]::Tag($f.FullName)
            if ($tag -ne 0 -and (($tag -band $CloudFilesMask) -ne $CloudFilesTag)) { Log ('ZIP_REJECTED_REPARSE_TAG=' + ('0x{0:X8}' -f $tag) + ' ' + $f.FullName); continue }
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
    $work = Join-Path (Join-Path $app 'TICKSTORE_QUAL_R47') $runName
    NoReparseBelow $app @()
    # R44D-ORIGIN-01: the D: sandbox root is NEVER created here.  It must already exist and is
    # admitted physically (no reparse component, resolves to itself) before anything touches D:;
    # the Python driver then holds it by handle and creates its run directory exclusively.
    if ($Mode -ceq 'QUAL') {
        Require ([IO.Directory]::Exists($DParent)) ('D_SANDBOX_ROOT_ABSENT_NOT_CREATED:' + $DParent)
        NoReparseBelow $DParent @()
        Require ([R41Reparse]::FinalPath($DParent) -ieq $DParent) ('D_SANDBOX_ROOT_REDIRECTED:' + [R41Reparse]::FinalPath($DParent))
        Log ('D_SANDBOX_ROOT_ADMITTED_PREWRITE=' + $DParent)
    } else { Log 'D_SANDBOX=NOT_USED_IN_B07_MODE' }
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
    & $Python -I -X utf8 -B $driver --run-dir $script:RunDir --work-root $work --bundle-dir $bundle --d-parent $DParent --ps-version ($PSVersionTable.PSVersion.ToString()) --bootstrap-sha256 $bootstrapSha --mode $Mode @b07Args
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 2 }
    Log ('QUAL_BOOTSTRAP_DRIVER_EXIT=' + $exitCode)
} catch {
  if ($_.Exception.Message -ceq 'ELEVATED_WINDOW_STARTED') {
    Log 'DELEGATED_TO_ELEVATED_WINDOW=YES: acompanhe a nova janela (Administrador). Ela grava outra pasta RUN em TICKSTORE_RUNS.'
    Log 'PRODUCTION_MODIFIED=NO; FULL_STARTED=NO'
    $exitCode = 3
  } else {
    Log ('QUAL_BOOTSTRAP_BLOCKED=' + $_.Exception.Message)
    Log 'PRODUCTION_MODIFIED=NO (bootstrap writes only run-owned folders); FULL_STARTED=NO'
    $exitCode = 2
  }
}
if ($script:RunDir -ne '') { Log ('RUN_LOG=' + (Join-Path $script:RunDir 'RUN_LOG.txt')) }
if ($exitCode -ne 3) { Log 'Devolva ao engenheiro: o arquivo RETURN_ZIP indicado acima (ou RUN_LOG.txt se nao houver RETURN_ZIP).' }
exit $exitCode
