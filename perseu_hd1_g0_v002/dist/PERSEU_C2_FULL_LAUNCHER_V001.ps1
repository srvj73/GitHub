#requires -Version 5.1
<#
PERSEU_C2_FULL_LAUNCHER_V001.ps1 -- SOURCE_ONLY launcher; Windows target G0 pending.
Project: Perseu MT5 (Astra) | Thread: PERSEU_C2_DISK_SPACE_RECONCILIATION | Front: C2 AUG2026 exploratory FULL

Does NOT reimplement R4R9. It verifies an origin-pinned source lock and then runs the ORIGINAL canonical
R4R9 entry wrapper (powershell.exe -File) unchanged. Non-negotiable invariants are compiled in:
runner/accel/core SHA, D1 certificate 93092E9A..., OUT path, range 2026-08-01..2026-08-31, prereg V003 forbidden.

Modes:
  SelfTest   synthetic install + fixture wrappers (real child powershell.exe -File), no protected effects
  Install    copy EXACTLY the lock's pinned file set from a recovered -SourceDir into a NEW install root (verified)
  Preflight  DRY_RUN on the real install: lock, identities, wrapper static contract, D1, prereg, OUT fresh, D: free, processes
  Run        Preflight, then launch the canonical entry wrapper (effectful: the R4R9 runner writes OUT on D:)
Launch from PS C:\Users\silvi> (no cd):
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001.ps1" -Mode SelfTest
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001.ps1" -Mode Preflight -SourceLockPath "<abs path>" -SourceLockSha256 <64 hex from origin>
Evidence: C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001_RUNS\<MODE>_<RUN_ID>\ (fixed, absolute, new per run)
Exit codes: 0=PASS  2=BLOCKED_NO_EFFECTS  3=FAIL_OR_BLOCKED_AFTER_PARTIAL_EFFECT  130=SAFE_STOP; Run propagates runner rc in receipt.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('SelfTest', 'Install', 'Preflight', 'Run')]
    [string]$Mode,
    [string]$SourceLockPath = '',
    [string]$SourceLockSha256 = '',
    [string]$SourceDir = ''
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$ProjectName = 'Perseu MT5 (Astra)'
$ThreadName = 'PERSEU_C2_DISK_SPACE_RECONCILIATION'
$Revision = 'PERSEU_C2_FULL_LAUNCHER_V001'
$PolicyMasterSha256 = '5B135DA0CA7C3BFE992F364720605522FB939977772C6D5A6FD3811A8288B302'
$ResultContext = 'RESULT_CONTEXT=ChatGPT | PROJECT=' + $ProjectName + ' | THREAD=' + $ThreadName
$ResultFooter = 'RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ProjectName + ' | THREAD=' + $ThreadName
$DownloadsRoot = 'C:\Users\silvi\OneDrive\Downloads'
$EvidenceRoot = 'C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001_RUNS'
$PowerShellExe = [System.IO.Path]::Combine([string]$env:WINDIR, 'System32\WindowsPowerShell\v1.0\powershell.exe')
$LockSchema = 'PERSEU_C2_SOURCE_LOCK_V001'
$RunWatchdogSeconds = 345600
$HeartbeatSeconds = 60
$MinFreeGbFloor = 100.0
$PlaceholderMask = [int64](0x1000 -bor 0x40000 -bor 0x400000)

$ProductionInvariants = @{
    runner = '28DF85A4BF87B859230C931042C493CD6B4E57FE8698135C3D771C56E466E68C'
    accel = '042FA9CB7DB2DE26BD64F82B41B2A1977B05C65509E2038239BDC972E766F2E5'
    core = 'A331F308182766C299B067BE2035EB071E01019C28A6C20DD6DF09B1AB92607F'
    d1 = '93092E9A8FB656CF5696087CE863C1F7B5F1601B52621993081A98A49B2F628D'
    c2_wrapper = '53C8A1FBAA0C836DCB616789BD0C1D7264CCA6E97C8780E364FA05204E088ADD'
    forbidden_prereg = '76833706F5E87F386071F35328D362FA0C5ABB124AC52CA1AA0840A603D7C408'
    out = 'D:\PerseuRuns\PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C2_202608'
    start = '2026-08-01'
    end = '2026-08-31'
}
$EntryPlain = 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1'
$EntryTelemetry = 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V4.ps1'

$Invariant = [System.Globalization.CultureInfo]::InvariantCulture
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$script:Phase = 'INIT'
$script:RunDir = $null
$script:LogPath = $null
$script:EvidenceFiles = New-Object System.Collections.Generic.List[string]
$script:ActiveChild = $null

function Get-PflTimestamp {
    return (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz', $Invariant)
}

function Write-PflLog {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Line)
    Write-Host $Line
    if ($null -ne $script:LogPath) {
        [System.IO.File]::AppendAllText($script:LogPath, ((Get-PflTimestamp) + ' ' + $Line + "`r`n"), $Utf8NoBom)
    }
}

function Stop-PflBlocked {
    param([Parameter(Mandatory = $true)][string]$Reason)
    throw (New-Object System.InvalidOperationException('BLOCKED:' + $Reason))
}

function Get-PflSha {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Write-PflNewText {
    param([Parameter(Mandatory = $true)][string]$LiteralPath, [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    if ([System.IO.File]::Exists($LiteralPath)) { Stop-PflBlocked -Reason ('EVIDENCE_FILE_PREEXISTS:' + $LiteralPath) }
    $bytes = $Utf8NoBom.GetBytes($Text)
    $fs = New-Object System.IO.FileStream($LiteralPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try { $fs.Write($bytes, 0, $bytes.Length); $fs.Flush($true) } finally { $fs.Dispose() }
    $script:EvidenceFiles.Add($LiteralPath)
}

function Get-PflProp {
    param([AllowNull()][object]$Obj, [Parameter(Mandatory = $true)][string]$Name)
    if ($null -eq $Obj) { return $null }
    $p = $Obj.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}

function Test-PflLocalFile {
    # Exists, regular, not a cloud placeholder (no implicit hydration), returns SHA or a blocker reason.
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) { return [pscustomobject]@{ ok = $false; reason = 'MISSING'; sha256 = $null } }
    $it = Get-Item -LiteralPath $LiteralPath -Force
    if ((([int64]$it.Attributes) -band $PlaceholderMask) -ne 0) { return [pscustomobject]@{ ok = $false; reason = 'CLOUD_PLACEHOLDER_NOT_LOCAL'; sha256 = $null } }
    return [pscustomobject]@{ ok = $true; reason = 'LOCAL'; sha256 = (Get-PflSha -LiteralPath $LiteralPath) }
}

function Test-PflWrapperContract {
    # Static contract of the canonical entry wrapper (text only; it is never modified).
    param([Parameter(Mandatory = $true)][string]$LiteralPath, [Parameter(Mandatory = $true)][hashtable]$Inv, [Parameter(Mandatory = $true)][string]$D1Path)
    $text = [System.IO.File]::ReadAllText($LiteralPath)
    $b = New-Object System.Collections.Generic.List[string]
    $opt = [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    if (-not [regex]::IsMatch($text, ('--start\s+[''"]?' + [regex]::Escape($Inv.start)), $opt)) { $b.Add('WRAPPER_START_NOT_' + $Inv.start) }
    if (-not [regex]::IsMatch($text, ('--end\s+[''"]?' + [regex]::Escape($Inv.end)), $opt)) { $b.Add('WRAPPER_END_NOT_' + $Inv.end) }
    $leaf = [System.IO.Path]::GetFileName($Inv.out.TrimEnd('\'))
    if ($text.IndexOf($leaf, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { $b.Add('WRAPPER_OUT_LEAF_ABSENT') }
    $d1m = [regex]::Matches($text, '\$D1Cert\s*=\s*''([^'']+)''', $opt)
    if ($d1m.Count -ne 1) { $b.Add('WRAPPER_D1CERT_ASSIGNMENT_CARDINALITY_' + $d1m.Count) }
    elseif (-not [string]::Equals($d1m[0].Groups[1].Value, $D1Path, [System.StringComparison]::OrdinalIgnoreCase)) { $b.Add('WRAPPER_D1CERT_PATH_NOT_LOCKED_D1') }
    return $b.ToArray()
}

function Test-PflLock {
    param(
        [Parameter(Mandatory = $true)][string]$LockPath,
        [Parameter(Mandatory = $true)][string]$LockSha,
        [Parameter(Mandatory = $true)][hashtable]$Inv,
        [Parameter(Mandatory = $true)][bool]$CheckFreeSpace
    )
    $b = New-Object System.Collections.Generic.List[string]
    $ids = [ordered]@{}
    if ($LockSha -notmatch '^[0-9A-Fa-f]{64}$') { $b.Add('LOCK_SHA_PARAMETER_INVALID'); return [pscustomobject]@{ ok = $false; blockers = $b.ToArray(); identities = $ids; entry = $null; install = $null; out = $null } }
    $lf = Test-PflLocalFile -LiteralPath $LockPath
    if (-not $lf.ok) { $b.Add('LOCK_' + $lf.reason); return [pscustomobject]@{ ok = $false; blockers = $b.ToArray(); identities = $ids; entry = $null; install = $null; out = $null } }
    $ids['lock'] = $lf.sha256
    if ($lf.sha256 -ne $LockSha.ToUpperInvariant()) { $b.Add('LOCK_SHA_MISMATCH'); return [pscustomobject]@{ ok = $false; blockers = $b.ToArray(); identities = $ids; entry = $null; install = $null; out = $null } }
    try { $lock = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($LockPath)) } catch { $b.Add('LOCK_JSON_MALFORMED'); return [pscustomobject]@{ ok = $false; blockers = $b.ToArray(); identities = $ids; entry = $null; install = $null; out = $null } }
    if ((Get-PflProp $lock 'schema') -ne $LockSchema) { $b.Add('LOCK_SCHEMA_INVALID') }
    $install = [string](Get-PflProp $lock 'install_root')
    $files = Get-PflProp $lock 'files'
    $entry = [string](Get-PflProp $lock 'entry_wrapper')
    $out = [string](Get-PflProp $lock 'out')
    $range = @(Get-PflProp $lock 'range')
    $d1 = Get-PflProp $lock 'd1_cert'
    $pre = Get-PflProp $lock 'prereg'
    $minFree = Get-PflProp $lock 'min_free_gb_out_drive'
    if ([string]::IsNullOrEmpty($install) -or -not [System.IO.Directory]::Exists($install)) { $b.Add('INSTALL_ROOT_MISSING') }
    if ($null -eq $files) { $b.Add('LOCK_FILES_MISSING') }
    if (-not [string]::Equals($out, $Inv.out, [System.StringComparison]::OrdinalIgnoreCase)) { $b.Add('LOCK_OUT_NOT_INVARIANT') }
    if ($range.Count -ne 2 -or [string]$range[0] -ne $Inv.start -or [string]$range[1] -ne $Inv.end) { $b.Add('LOCK_RANGE_NOT_INVARIANT') }
    $required = @{ 'perseu_parallel_auto.py' = $Inv.runner; 'perseu_r4r9_accel.py' = $Inv.accel; 'perseu_exploratorio.py' = $Inv.core }
    if ($entry -eq $EntryPlain) { $required[$EntryPlain] = $Inv.c2_wrapper }
    elseif ($entry -eq $EntryTelemetry) {
        if ($null -eq (Get-PflProp $files 'perseu_r4r9_telemetry_v4.py')) { $b.Add('LOCK_TELEMETRY_SHIM_NOT_PINNED') }
        if ($null -eq (Get-PflProp $files $EntryTelemetry)) { $b.Add('LOCK_TELEMETRY_WRAPPER_NOT_PINNED') }
    } else { $b.Add('LOCK_ENTRY_WRAPPER_NOT_ALLOWED') }
    if ($null -ne $files -and $b.Count -eq 0) {
        foreach ($k in $required.Keys) {
            if ([string](Get-PflProp $files $k) -ne $required[$k]) { $b.Add('LOCK_PIN_NOT_INVARIANT:' + $k) }
        }
        foreach ($p in $files.PSObject.Properties) {
            $rel = [string]$p.Name
            if ($rel.Contains('..') -or [System.IO.Path]::IsPathRooted($rel)) { $b.Add('LOCK_FILE_PATH_INVALID:' + $rel); continue }
            $want = ([string]$p.Value).ToUpperInvariant()
            $lfx = Test-PflLocalFile -LiteralPath ([System.IO.Path]::Combine($install, $rel))
            $ids[$rel] = $lfx.sha256
            if (-not $lfx.ok) { $b.Add('INSTALL_' + $lfx.reason + ':' + $rel) }
            elseif ($lfx.sha256 -ne $want) { $b.Add('INSTALL_SHA_MISMATCH:' + $rel) }
        }
    }
    $d1Path = [string](Get-PflProp $d1 'path')
    if ([string](Get-PflProp $d1 'sha256') -ne $Inv.d1) { $b.Add('LOCK_D1_NOT_INVARIANT') }
    $d1f = Test-PflLocalFile -LiteralPath $d1Path
    $ids['d1_cert'] = $d1f.sha256
    if (-not $d1f.ok) { $b.Add('D1_' + $d1f.reason) } elseif ($d1f.sha256 -ne $Inv.d1) { $b.Add('D1_SHA_MISMATCH') }
    $preSha = ([string](Get-PflProp $pre 'sha256')).ToUpperInvariant()
    if ([string](Get-PflProp $pre 'version') -ne 'V004') { $b.Add('LOCK_PREREG_VERSION_NOT_V004') }
    if ($preSha -eq $Inv.forbidden_prereg) { $b.Add('LOCK_PREREG_IS_V003_FORBIDDEN') }
    if ($preSha -notmatch '^[0-9A-F]{64}$') { $b.Add('LOCK_PREREG_SHA_INVALID') }
    $pf = Test-PflLocalFile -LiteralPath ([string](Get-PflProp $pre 'path'))
    $ids['prereg'] = $pf.sha256
    if (-not $pf.ok) { $b.Add('PREREG_' + $pf.reason) } elseif ($pf.sha256 -ne $preSha) { $b.Add('PREREG_SHA_MISMATCH') }
    $entryPath = $null
    if ($b.Count -eq 0) {
        $entryPath = [System.IO.Path]::Combine($install, $entry)
        foreach ($x in @(Test-PflWrapperContract -LiteralPath $entryPath -Inv $Inv -D1Path $d1Path)) { $b.Add($x) }
    }
    if ([System.IO.Directory]::Exists($Inv.out)) {
        $n = @([System.IO.Directory]::GetFileSystemEntries($Inv.out)).Count
        if ($n -gt 0) { $b.Add('OUT_NOT_FRESH_ENTRIES_' + $n + '_RESUME_REQUIRES_SEPARATE_DECISION') }
    }
    $freeGb = $null
    if ($CheckFreeSpace) {
        $floor = $MinFreeGbFloor
        if ($null -ne $minFree -and [double]$minFree -gt $floor) { $floor = [double]$minFree }
        try {
            $di = New-Object System.IO.DriveInfo([System.IO.Path]::GetPathRoot($Inv.out))
            $freeGb = [math]::Round(([double][int64]$di.AvailableFreeSpace) / 1073741824.0, 3)
            if ($freeGb -lt $floor) { $b.Add('OUT_DRIVE_FREE_GB_' + $freeGb + '_BELOW_' + $floor) }
        } catch {
            $b.Add('OUT_DRIVE_FREE_SPACE_UNAVAILABLE:' + $_.Exception.GetType().Name)
        }
    }
    return [pscustomobject][ordered]@{ ok = ($b.Count -eq 0); blockers = $b.ToArray(); identities = $ids; entry = $entryPath; install = $install; out = $Inv.out; free_gb = $freeGb }
}

function Get-PflActivePerseu {
    # Supplementary process evidence (10.AB): CommandLine may be invisible across privilege boundaries.
    $rows = @()
    try {
        $rows = @(Get-CimInstance Win32_Process | Where-Object { $null -ne $_.CommandLine -and $_.CommandLine -match '(?i)perseu_(parallel_auto|exploratorio|r4r9)|RUN_WINDOWS_R4R9' } |
            ForEach-Object { [pscustomobject][ordered]@{ pid = $_.ProcessId; name = $_.Name; cmd = ([string]$_.CommandLine).Substring(0, [System.Math]::Min(300, ([string]$_.CommandLine).Length)) } })
    } catch {
        return [pscustomobject]@{ ok = $false; reason = 'PROCESS_QUERY_FAILED:' + $_.Exception.GetType().Name; rows = @() }
    }
    return [pscustomobject]@{ ok = ($rows.Count -eq 0); reason = ('ACTIVE_PERSEU_' + $rows.Count); rows = $rows }
}

function Invoke-PflEntry {
    # Single serialization point; the entry wrapper path is the only argv besides fixed flags.
    param([Parameter(Mandatory = $true)][string]$EntryPath, [Parameter(Mandatory = $true)][string]$WorkDir, [Parameter(Mandatory = $true)][int]$WatchdogSeconds, [Parameter(Mandatory = $true)][string]$OutDir)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $PowerShellExe
    $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $EntryPath + '"'
    if ($EntryPath.Contains('"')) { Stop-PflBlocked -Reason 'ENTRY_PATH_QUOTE_FORBIDDEN' }
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.WorkingDirectory = $WorkDir
    Write-PflLog ('CHILD_START EXE=' + $PowerShellExe + ' ARGS=' + $psi.Arguments)
    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($null -eq $proc) { Stop-PflBlocked -Reason 'CHILD_START_NULL' }
    $script:ActiveChild = $proc
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $next = $HeartbeatSeconds
    $expired = $false
    while (-not $proc.WaitForExit(1000)) {
        $el = [int][System.Math]::Floor($sw.Elapsed.TotalSeconds)
        if ($el -ge $WatchdogSeconds) { $expired = $true; break }
        if ($el -ge $next) {
            $entries = $null
            if ([System.IO.Directory]::Exists($OutDir)) { $entries = @([System.IO.Directory]::GetFileSystemEntries($OutDir)).Count }
            Write-PflLog ('HEARTBEAT PHASE=C2_FULL CHILD_PID=' + $proc.Id + ' ELAPSED_S=' + $el + ' OUT_TOP_LEVEL_ENTRIES=' + $entries + ' WATCHDOG_S=' + $WatchdogSeconds + ' PROGRESS=SEE_RUNNER_CONSOLE')
            $next = $next + $HeartbeatSeconds
        }
    }
    if ($expired) {
        Write-PflLog ('WATCHDOG_EXPIRED NO_KILL CHILD_PID=' + $proc.Id)
        return [pscustomobject]@{ watchdog = $true; exit_code = $null; child_pid = $proc.Id; elapsed_s = [int]$sw.Elapsed.TotalSeconds }
    }
    $proc.WaitForExit()
    $script:ActiveChild = $null
    $code = [int]$proc.ExitCode
    Write-PflLog ('CHILD_END CHILD_PID=' + $proc.Id + ' EXIT_CODE=' + $code)
    return [pscustomobject]@{ watchdog = $false; exit_code = $code; child_pid = $proc.Id; elapsed_s = [int]$sw.Elapsed.TotalSeconds }
}

function Invoke-PflInstall {
    # Copies EXACTLY the lock's pinned file set from a recovered source directory into a NEW install root.
    # All source identities are verified before the first copy (no partial install on a known mismatch).
    param([Parameter(Mandatory = $true)][string]$LockPath, [Parameter(Mandatory = $true)][string]$LockSha, [Parameter(Mandatory = $true)][string]$SourceDir, [Parameter(Mandatory = $true)][hashtable]$Inv)
    $b = New-Object System.Collections.Generic.List[string]
    $copied = New-Object System.Collections.Generic.List[object]
    $res = { param($st) return [pscustomobject][ordered]@{ status = $st; blockers = $b.ToArray(); copied = $copied.ToArray(); partial_effect = ($copied.Count -gt 0) } }
    if ($LockSha -notmatch '^[0-9A-Fa-f]{64}$') { $b.Add('LOCK_SHA_PARAMETER_INVALID'); return (& $res 'BLOCKED') }
    $lf = Test-PflLocalFile -LiteralPath $LockPath
    if (-not $lf.ok -or $lf.sha256 -ne $LockSha.ToUpperInvariant()) { $b.Add('LOCK_SHA_MISMATCH_OR_' + $lf.reason); return (& $res 'BLOCKED') }
    $lock = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($LockPath))
    if ((Get-PflProp $lock 'schema') -ne $LockSchema) { $b.Add('LOCK_SCHEMA_INVALID'); return (& $res 'BLOCKED') }
    $install = [string](Get-PflProp $lock 'install_root')
    $files = Get-PflProp $lock 'files'
    if ([string]::IsNullOrEmpty($install) -or $null -eq $files) { $b.Add('LOCK_INSTALL_OR_FILES_MISSING'); return (& $res 'BLOCKED') }
    if ([System.IO.Directory]::Exists($install) -or [System.IO.File]::Exists($install)) { $b.Add('INSTALL_ROOT_PREEXISTS_NO_OVERWRITE'); return (& $res 'BLOCKED') }
    if (-not [System.IO.Directory]::Exists($SourceDir)) { $b.Add('SOURCE_DIR_MISSING'); return (& $res 'BLOCKED') }
    foreach ($pin in @(@{ k = 'perseu_parallel_auto.py'; v = $Inv.runner }, @{ k = 'perseu_r4r9_accel.py'; v = $Inv.accel }, @{ k = 'perseu_exploratorio.py'; v = $Inv.core })) {
        if ([string](Get-PflProp $files $pin.k) -ne $pin.v) { $b.Add('LOCK_PIN_NOT_INVARIANT:' + $pin.k) }
    }
    $plan = New-Object System.Collections.Generic.List[object]
    foreach ($p in $files.PSObject.Properties) {
        $rel = [string]$p.Name
        if ($rel.Contains('..') -or [System.IO.Path]::IsPathRooted($rel)) { $b.Add('LOCK_FILE_PATH_INVALID:' + $rel); continue }
        $src = [System.IO.Path]::Combine($SourceDir, $rel)
        $t = Test-PflLocalFile -LiteralPath $src
        if (-not $t.ok) { $b.Add('SOURCE_' + $t.reason + ':' + $rel); continue }
        if ($t.sha256 -ne ([string]$p.Value).ToUpperInvariant()) { $b.Add('SOURCE_SHA_MISMATCH:' + $rel); continue }
        $plan.Add([pscustomobject]@{ rel = $rel; src = $src; dst = [System.IO.Path]::Combine($install, $rel); sha = $t.sha256 })
    }
    $d1 = Get-PflProp $lock 'd1_cert'
    $d1Path = [string](Get-PflProp $d1 'path')
    $d1Rel = [string](Get-PflProp $d1 'restore_from_rel')
    $d1Plan = $null
    if (-not [System.IO.File]::Exists($d1Path) -and -not [string]::IsNullOrEmpty($d1Rel)) {
        $t = Test-PflLocalFile -LiteralPath ([System.IO.Path]::Combine($SourceDir, $d1Rel))
        if (-not $t.ok -or $t.sha256 -ne $Inv.d1) { $b.Add('D1_RESTORE_SOURCE_NOT_D1_INVARIANT') } else { $d1Plan = [System.IO.Path]::Combine($SourceDir, $d1Rel) }
    }
    if ($b.Count -gt 0) { return (& $res 'BLOCKED') }
    foreach ($x in $plan) {
        $dir = [System.IO.Path]::GetDirectoryName($x.dst)
        if (-not [System.IO.Directory]::Exists($dir)) { [void][System.IO.Directory]::CreateDirectory($dir) }
        [System.IO.File]::Copy($x.src, $x.dst, $false)
        $got = Get-PflSha -LiteralPath $x.dst
        $copied.Add([pscustomobject][ordered]@{ rel = $x.rel; sha256 = $got; verified = ($got -eq $x.sha) })
        if ($got -ne $x.sha) { $b.Add('COPY_VERIFY_FAILED:' + $x.rel); return (& $res 'FAIL_PARTIAL') }
    }
    if ($null -ne $d1Plan) {
        [System.IO.File]::Copy($d1Plan, $d1Path, $false)
        $got = Get-PflSha -LiteralPath $d1Path
        $copied.Add([pscustomobject][ordered]@{ rel = $d1Path; sha256 = $got; verified = ($got -eq $Inv.d1) })
        if ($got -ne $Inv.d1) { $b.Add('D1_COPY_VERIFY_FAILED'); return (& $res 'FAIL_PARTIAL') }
    }
    Write-PflLog ('INSTALL COPIED=' + $copied.Count + ' ROOT=' + $install)
    return (& $res 'PASS')
}

function New-PflFixture {
    # Synthetic install + D1 + prereg + lock + entry wrapper whose exit code / OUT write are controlled.
    param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Behaviour)
    $inst = [System.IO.Path]::Combine($Root, 'INSTALL')
    [void][System.IO.Directory]::CreateDirectory($inst)
    $out = [System.IO.Path]::Combine($Root, 'OUT_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C2_202608')
    foreach ($n in @('perseu_parallel_auto.py', 'perseu_r4r9_accel.py', 'perseu_exploratorio.py')) {
        [System.IO.File]::WriteAllText([System.IO.Path]::Combine($inst, $n), ('synthetic ' + $n), $Utf8NoBom)
    }
    $d1 = [System.IO.Path]::Combine($Root, 'D1_HOMOLOGATION_CERT_SYNTH.json')
    [System.IO.File]::WriteAllText($d1, '{"d1":"synthetic"}', $Utf8NoBom)
    $pre = [System.IO.Path]::Combine($Root, 'PREREG_V004_SYNTH.zip')
    [System.IO.File]::WriteAllText($pre, 'synthetic prereg v004', $Utf8NoBom)
    $body = "`$D1Cert = '" + $d1 + "'`r`n`$Out = '" + $out + "'`r`n# --start 2026-08-01 --end 2026-08-31`r`n"
    if ($Behaviour -eq 'pass') { $body += "[void][System.IO.Directory]::CreateDirectory(`$Out)`r`n[System.IO.File]::WriteAllText([System.IO.Path]::Combine(`$Out, 'RUN_STATUS.json'), '{""state"":""PASS""}')`r`nexit 0`r`n" }
    elseif ($Behaviour -eq 'fail') { $body += "exit 7`r`n" }
    elseif ($Behaviour -eq 'sleep') { $body += "Start-Sleep -Seconds 6`r`nexit 0`r`n" }
    elseif ($Behaviour -eq 'mutate') { $body += "[System.IO.File]::AppendAllText([System.IO.Path]::Combine((Split-Path -Parent `$MyInvocation.MyCommand.Path), 'perseu_parallel_auto.py'), 'tamper')`r`nexit 0`r`n" }
    $entry = [System.IO.Path]::Combine($inst, $EntryPlain)
    [System.IO.File]::WriteAllText($entry, $body, $Utf8NoBom)
    $inv = @{}
    foreach ($k in $ProductionInvariants.Keys) { $inv[$k] = $ProductionInvariants[$k] }
    $inv.runner = Get-PflSha -LiteralPath ([System.IO.Path]::Combine($inst, 'perseu_parallel_auto.py'))
    $inv.accel = Get-PflSha -LiteralPath ([System.IO.Path]::Combine($inst, 'perseu_r4r9_accel.py'))
    $inv.core = Get-PflSha -LiteralPath ([System.IO.Path]::Combine($inst, 'perseu_exploratorio.py'))
    $inv.d1 = Get-PflSha -LiteralPath $d1
    $inv.c2_wrapper = Get-PflSha -LiteralPath $entry
    $inv.out = $out
    $lockObj = [ordered]@{
        schema = $LockSchema; install_root = $inst; entry_wrapper = $EntryPlain; out = $out; range = @('2026-08-01', '2026-08-31')
        files = [ordered]@{ 'perseu_parallel_auto.py' = $inv.runner; 'perseu_r4r9_accel.py' = $inv.accel; 'perseu_exploratorio.py' = $inv.core; 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1' = $inv.c2_wrapper }
        d1_cert = [ordered]@{ path = $d1; sha256 = $inv.d1 }
        prereg = [ordered]@{ version = 'V004'; path = $pre; sha256 = (Get-PflSha -LiteralPath $pre) }
        min_free_gb_out_drive = 0
    }
    $lockPath = [System.IO.Path]::Combine($Root, 'C2_SOURCE_LOCK_V001.json')
    [System.IO.File]::WriteAllText($lockPath, (ConvertTo-Json -InputObject $lockObj -Depth 5), $Utf8NoBom)
    return [pscustomobject]@{ root = $Root; install = $inst; entry = $entry; out = $out; lock = $lockPath; lock_sha = (Get-PflSha -LiteralPath $lockPath); inv = $inv; d1 = $d1; pre = $pre }
}

function Invoke-PflSelfTest {
    $checks = New-Object System.Collections.Generic.List[object]
    $base = [System.IO.Path]::Combine($script:RunDir, 'SELFTEST_FIXTURE')
    [void][System.IO.Directory]::CreateDirectory($base)
    $add = { param($n, $p, $d) $checks.Add([pscustomobject][ordered]@{ name = $n; pass = [bool]$p; detail = [string]$d }); Write-PflLog ('SELFTEST_CHECK ' + $n + '=' + $(if ($p) { 'PASS' } else { 'FAIL' }) + ' ' + $d) }
    $mk = { param($tag, $beh) New-PflFixture -Root ([System.IO.Path]::Combine($base, $tag)) -Behaviour $beh }
    $f = & $mk 'ok' 'pass'
    $r = Test-PflLock -LockPath $f.lock -LockSha $f.lock_sha -Inv $f.inv -CheckFreeSpace $false
    & $add 'LOCK_VALID_FIXTURE_PASS' $r.ok (($r.blockers) -join ';')
    $r = Test-PflLock -LockPath $f.lock -LockSha ('0' * 64) -Inv $f.inv -CheckFreeSpace $false
    & $add 'LOCK_SHA_PARAMETER_MISMATCH' ((-not $r.ok) -and (@($r.blockers) -contains 'LOCK_SHA_MISMATCH')) (($r.blockers) -join ';')
    $r = Test-PflLock -LockPath $f.lock -LockSha $f.lock_sha -Inv $ProductionInvariants -CheckFreeSpace $false
    & $add 'FIXTURE_REJECTED_BY_PRODUCTION_INVARIANTS' ((-not $r.ok) -and @(@($r.blockers) | Where-Object { $_ -like 'LOCK_*NOT_INVARIANT*' }).Count -ge 1) (($r.blockers) -join ';')
    $f2 = & $mk 'tamper' 'pass'
    [System.IO.File]::AppendAllText([System.IO.Path]::Combine($f2.install, 'perseu_r4r9_accel.py'), 'x')
    $r = Test-PflLock -LockPath $f2.lock -LockSha $f2.lock_sha -Inv $f2.inv -CheckFreeSpace $false
    & $add 'INSTALL_SHA_MISMATCH_DETECTED' (@($r.blockers) -contains 'INSTALL_SHA_MISMATCH:perseu_r4r9_accel.py') (($r.blockers) -join ';')
    $f3 = & $mk 'd1wrong' 'pass'
    [System.IO.File]::AppendAllText($f3.d1, ' ')
    $r = Test-PflLock -LockPath $f3.lock -LockSha $f3.lock_sha -Inv $f3.inv -CheckFreeSpace $false
    & $add 'D1_SHA_MISMATCH_DETECTED' (@($r.blockers) -contains 'D1_SHA_MISMATCH') (($r.blockers) -join ';')
    $f4 = & $mk 'v003' 'pass'
    $inv4 = @{}; foreach ($k in $f4.inv.Keys) { $inv4[$k] = $f4.inv[$k] }
    $inv4.forbidden_prereg = Get-PflSha -LiteralPath $f4.pre
    $r = Test-PflLock -LockPath $f4.lock -LockSha $f4.lock_sha -Inv $inv4 -CheckFreeSpace $false
    & $add 'PREREG_V003_FORBIDDEN' (@($r.blockers) -contains 'LOCK_PREREG_IS_V003_FORBIDDEN') (($r.blockers) -join ';')
    $f5 = & $mk 'outdirty' 'pass'
    [void][System.IO.Directory]::CreateDirectory($f5.out)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($f5.out, 'old.txt'), 'x')
    $r = Test-PflLock -LockPath $f5.lock -LockSha $f5.lock_sha -Inv $f5.inv -CheckFreeSpace $false
    & $add 'OUT_NOT_FRESH_BLOCKED' (@(@($r.blockers) | Where-Object { $_ -like 'OUT_NOT_FRESH_ENTRIES_1*' }).Count -eq 1) (($r.blockers) -join ';')
    $f6 = & $mk 'wrapperrange' 'pass'
    $txt = [System.IO.File]::ReadAllText($f6.entry).Replace('2026-08-31', '2026-08-30')
    [System.IO.File]::WriteAllText($f6.entry, $txt, $Utf8NoBom)
    $f6.inv.c2_wrapper = Get-PflSha -LiteralPath $f6.entry
    $lock6 = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($f6.lock))
    $lock6.files.'RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1' = $f6.inv.c2_wrapper
    $lock6Path = [System.IO.Path]::Combine($f6.root, 'C2_SOURCE_LOCK_V001_RANGE_EDITED.json')
    [System.IO.File]::WriteAllText($lock6Path, (ConvertTo-Json -InputObject $lock6 -Depth 5), $Utf8NoBom)
    $r = Test-PflLock -LockPath $lock6Path -LockSha (Get-PflSha -LiteralPath $lock6Path) -Inv $f6.inv -CheckFreeSpace $false
    & $add 'WRAPPER_RANGE_CONTRACT' (@($r.blockers) -contains 'WRAPPER_END_NOT_2026-08-31') (($r.blockers) -join ';')
    $r = Test-PflLock -LockPath $f.lock -LockSha $f.lock_sha -Inv $f.inv -CheckFreeSpace $true
    & $add 'FREE_SPACE_MEASURED' ($null -ne $r.free_gb) ([string]$r.free_gb)
    # real child launches through powershell.exe -File
    $run = Invoke-PflEntry -EntryPath $f.entry -WorkDir $f.install -WatchdogSeconds 120 -OutDir $f.out
    & $add 'CHILD_PASS_EXIT_0_OUT_WRITTEN' (($run.exit_code -eq 0) -and [System.IO.File]::Exists([System.IO.Path]::Combine($f.out, 'RUN_STATUS.json'))) ([string]$run.exit_code)
    $ff = & $mk 'childfail' 'fail'
    $run = Invoke-PflEntry -EntryPath $ff.entry -WorkDir $ff.install -WatchdogSeconds 120 -OutDir $ff.out
    & $add 'CHILD_EXIT_CODE_PROPAGATED_7' ($run.exit_code -eq 7) ([string]$run.exit_code)
    $fs = & $mk 'childsleep' 'sleep'
    $run = Invoke-PflEntry -EntryPath $fs.entry -WorkDir $fs.install -WatchdogSeconds 2 -OutDir $fs.out
    $natural = $null
    if ($run.watchdog -and $null -ne $script:ActiveChild) { [void]$script:ActiveChild.WaitForExit(60000); $natural = [int]$script:ActiveChild.ExitCode; $script:ActiveChild = $null }
    & $add 'WATCHDOG_NO_KILL_NATURAL_EXIT' ($run.watchdog -and $natural -eq 0) ([string]$natural)
    $fm = & $mk 'childmutate' 'mutate'
    $before = Get-PflSha -LiteralPath ([System.IO.Path]::Combine($fm.install, 'perseu_parallel_auto.py'))
    $run = Invoke-PflEntry -EntryPath $fm.entry -WorkDir $fm.install -WatchdogSeconds 120 -OutDir $fm.out
    $post = Test-PflLock -LockPath $fm.lock -LockSha $fm.lock_sha -Inv $fm.inv -CheckFreeSpace $false
    $fi = & $mk 'install' 'pass'
    $newRoot = [System.IO.Path]::Combine($fi.root, 'INSTALL_RESTORED')
    $lockI = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($fi.lock))
    $lockI.install_root = $newRoot
    $lockIPath = [System.IO.Path]::Combine($fi.root, 'C2_SOURCE_LOCK_V001_INSTALL.json')
    [System.IO.File]::WriteAllText($lockIPath, (ConvertTo-Json -InputObject $lockI -Depth 5), $Utf8NoBom)
    $lockISha = Get-PflSha -LiteralPath $lockIPath
    $ins = Invoke-PflInstall -LockPath $lockIPath -LockSha $lockISha -SourceDir $fi.install -Inv $fi.inv
    $after = Test-PflLock -LockPath $lockIPath -LockSha $lockISha -Inv $fi.inv -CheckFreeSpace $false
    & $add 'INSTALL_EXACT_SET_VERIFIED_THEN_PREFLIGHT_OK' (($ins.status -eq 'PASS') -and @($ins.copied).Count -eq 4 -and $after.ok) ($ins.status + ' ' + (($after.blockers) -join ';'))
    $ins2 = Invoke-PflInstall -LockPath $lockIPath -LockSha $lockISha -SourceDir $fi.install -Inv $fi.inv
    & $add 'INSTALL_NO_OVERWRITE' (($ins2.status -eq 'BLOCKED') -and (@($ins2.blockers) -contains 'INSTALL_ROOT_PREEXISTS_NO_OVERWRITE') -and -not $ins2.partial_effect) $ins2.status
    $fj = & $mk 'install_bad' 'pass'
    $badRoot = [System.IO.Path]::Combine($fj.root, 'INSTALL_RESTORED')
    $lockJ = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($fj.lock))
    $lockJ.install_root = $badRoot
    $lockJPath = [System.IO.Path]::Combine($fj.root, 'C2_SOURCE_LOCK_V001_INSTALL.json')
    [System.IO.File]::WriteAllText($lockJPath, (ConvertTo-Json -InputObject $lockJ -Depth 5), $Utf8NoBom)
    [System.IO.File]::AppendAllText([System.IO.Path]::Combine($fj.install, 'perseu_exploratorio.py'), 'drift')
    $ins3 = Invoke-PflInstall -LockPath $lockJPath -LockSha (Get-PflSha -LiteralPath $lockJPath) -SourceDir $fj.install -Inv $fj.inv
    & $add 'INSTALL_SOURCE_MISMATCH_NOTHING_COPIED' (($ins3.status -eq 'BLOCKED') -and (@($ins3.blockers) -contains 'SOURCE_SHA_MISMATCH:perseu_exploratorio.py') -and -not [System.IO.Directory]::Exists($badRoot)) (($ins3.blockers) -join ';')
    & $add 'POST_RUN_MUTATION_DETECTED' ((@($post.blockers) -contains 'INSTALL_SHA_MISMATCH:perseu_parallel_auto.py') -and $before -eq $fm.inv.runner) (($post.blockers) -join ';')
    $allPass = $true
    foreach ($c in $checks) { if (-not $c.pass) { $allPass = $false } }
    return [pscustomobject][ordered]@{ pass = $allPass; checks = $checks.ToArray(); fixture_lifecycle = 'PRESERVE_RUN_OWNED_EVIDENCE_NOT_AUTO_DELETED' }
}

# ------------------------------------------------------------------ main
$exitCode = 2
$finalResult = 'BLOCKED'
$finalReason = $null
$startedAt = Get-PflTimestamp
$runId = $null
$wrapperPath = $null
$wrapperSha = $null
$edition = 'UNKNOWN'
$psVer = $null
$body = [ordered]@{}
$fullStarted = 'NO'
$fullCompleted = 'NO'
$partialEffect = 'NO'
$receiptPath = $null
$receiptSha = $null
$script:TryCompleted = $false
$script:Caught = $false
$script:Interrupted = $false

try {
    Write-Host $ResultContext
    $script:Phase = 'ENVIRONMENT_GATES'
    if ($env:OS -ne 'Windows_NT') { Stop-PflBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }
    $edition = 'Desktop'
    $editionProp = $PSVersionTable.PSObject.Properties['PSEdition']
    if ($null -ne $editionProp) { $edition = [string]$editionProp.Value }
    $psVer = $PSVersionTable.PSVersion
    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) { Stop-PflBlocked -Reason ('WINDOWS_POWERSHELL_51_DESKTOP_REQUIRED:' + $edition + ':' + $psVer.ToString()) }
    if ([string]::IsNullOrEmpty($PSCommandPath)) { Stop-PflBlocked -Reason 'LAUNCH_WITH_DASH_FILE_REQUIRED' }
    $wrapperPath = $PSCommandPath
    $wrapperSha = Get-PflSha -LiteralPath $wrapperPath
    if (-not [System.IO.Directory]::Exists($DownloadsRoot)) { Stop-PflBlocked -Reason ('CANONICAL_DOWNLOADS_MISSING:' + $DownloadsRoot) }
    if (-not [System.IO.File]::Exists($PowerShellExe)) { Stop-PflBlocked -Reason ('WINDOWS_POWERSHELL_EXE_MISSING:' + $PowerShellExe) }
    $script:Phase = 'RUN_DIR'
    $runId = (Get-Date).ToString('yyyyMMdd_HHmmss_fff', $Invariant) + '_' + $PID
    if (-not [System.IO.Directory]::Exists($EvidenceRoot)) { [void][System.IO.Directory]::CreateDirectory($EvidenceRoot) }
    $rd = [System.IO.Path]::Combine($EvidenceRoot, ($Mode.ToUpperInvariant() + '_' + $runId))
    if ([System.IO.Directory]::Exists($rd) -or [System.IO.File]::Exists($rd)) { Stop-PflBlocked -Reason 'RUN_DIR_PREEXISTS' }
    [void][System.IO.Directory]::CreateDirectory($rd)
    $script:RunDir = $rd
    $script:LogPath = [System.IO.Path]::Combine($rd, 'RUN_LOG.txt')
    Write-PflLog ('REVISION=' + $Revision + ' MODE=' + $Mode + ' RUN_ID=' + $runId)
    Write-PflLog ('WRAPPER=' + $wrapperPath + ' WRAPPER_SHA256=' + $wrapperSha)
    Write-PflLog ('RUN_DIR=' + $rd)
    if ($Mode -eq 'SelfTest') {
        $script:Phase = 'SELFTEST'
        Write-PflLog 'PROTECTED_EFFECTS=NONE C2_FULL_STARTED=NO'
        $st = Invoke-PflSelfTest
        $body['selftest'] = $st
        if ($st.pass) { $finalResult = 'PASS_SELFTEST_ONLY'; $finalReason = 'ALL_SYNTHETIC_CHECKS_PASS'; $exitCode = 0 } else { $finalReason = 'SELFTEST_CHECK_FAILED' }
    } elseif ($Mode -eq 'Install') {
        $script:Phase = 'INSTALL'
        if ([string]::IsNullOrEmpty($SourceLockPath) -or [string]::IsNullOrEmpty($SourceLockSha256) -or [string]::IsNullOrEmpty($SourceDir)) { Stop-PflBlocked -Reason 'SOURCE_LOCK_PATH_SHA_AND_SOURCE_DIR_REQUIRED' }
        $ins = Invoke-PflInstall -LockPath $SourceLockPath -LockSha $SourceLockSha256 -SourceDir $SourceDir -Inv $ProductionInvariants
        $body['install'] = $ins
        foreach ($bl in @($ins.blockers)) { Write-PflLog ('INSTALL_BLOCKER=' + $bl) }
        if ($ins.status -eq 'PASS') { $finalResult = 'PASS_INSTALL_VERIFIED'; $finalReason = 'NEXT_PREFLIGHT'; $exitCode = 0; $partialEffect = 'YES_INSTALL_ROOT_CREATED_VERIFIED' }
        elseif ($ins.partial_effect) { $finalResult = 'FAIL'; $finalReason = 'INSTALL_PARTIAL_COPY_PRESERVED_RECONCILE'; $exitCode = 3; $partialEffect = 'YES_PARTIAL_INSTALL' }
        else { $finalReason = 'INSTALL_BLOCKED_NO_EFFECTS' }
    } else {
        $script:Phase = 'PREFLIGHT'
        if ([string]::IsNullOrEmpty($SourceLockPath) -or [string]::IsNullOrEmpty($SourceLockSha256)) { Stop-PflBlocked -Reason 'SOURCE_LOCK_PATH_AND_SHA_REQUIRED' }
        $lock = Test-PflLock -LockPath $SourceLockPath -LockSha $SourceLockSha256 -Inv $ProductionInvariants -CheckFreeSpace $true
        $proc = Get-PflActivePerseu
        $body['preflight'] = [ordered]@{ lock = $lock; processes = $proc; ram_total_bytes = [int64](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory; logical_cpus = [System.Environment]::ProcessorCount; py_launcher = [bool](Get-Command py -ErrorAction SilentlyContinue) }
        foreach ($bl in @($lock.blockers)) { Write-PflLog ('PREFLIGHT_BLOCKER=' + $bl) }
        Write-PflLog ('PREFLIGHT LOCK_OK=' + $lock.ok + ' PROCESSES_OK=' + $proc.ok + ' FREE_GB=' + $lock.free_gb)
        $ready = $lock.ok -and $proc.ok -and $body['preflight'].py_launcher
        if (-not $ready) {
            $finalReason = 'PREFLIGHT_BLOCKED_NO_EFFECTS'
        } elseif ($Mode -eq 'Preflight') {
            $finalResult = 'PASS_PREFLIGHT_DRY_RUN'; $finalReason = 'READY_FOR_RUN_NO_EFFECTS'; $exitCode = 0
        } else {
            $script:Phase = 'RUN'
            $fullStarted = 'YES'
            $partialEffect = 'YES_RUNNER_MAY_WRITE_OUT'
            Write-PflLog ('C2_FULL_STARTED=YES ENTRY=' + $lock.entry + ' OUT=' + $lock.out)
            $run = Invoke-PflEntry -EntryPath $lock.entry -WorkDir $lock.install -WatchdogSeconds $RunWatchdogSeconds -OutDir $lock.out
            $post = Test-PflLock -LockPath $SourceLockPath -LockSha $SourceLockSha256 -Inv $ProductionInvariants -CheckFreeSpace $false
            $unchanged = @($post.blockers | Where-Object { $_ -like 'INSTALL_*' -or $_ -like 'D1_*' -or $_ -like 'PREREG_*' -or $_ -like 'LOCK_*' }).Count -eq 0
            $status = $null
            $statusPath = [System.IO.Path]::Combine($lock.out, 'RUN_STATUS.json')
            if ([System.IO.File]::Exists($statusPath)) {
                try { $status = Get-PflProp (ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($statusPath))) 'state' } catch { $status = 'UNREADABLE' }
            }
            $body['run'] = [ordered]@{ child = $run; identities_unchanged_after_run = $unchanged; post_blockers = $post.blockers; run_status_state = $status; run_status_sha256 = $(if ([System.IO.File]::Exists($statusPath)) { Get-PflSha -LiteralPath $statusPath } else { $null }) }
            if ($run.watchdog) { $finalReason = 'WATCHDOG_EXPIRED_NO_KILL_RECONCILE_RUNNER'; $exitCode = 3 }
            elseif ($run.exit_code -eq 0 -and $unchanged -and [string]$status -eq 'PASS') { $finalResult = 'PASS_C2_FULL_RUN_EXIT_0'; $finalReason = 'RUNNER_EXIT_0_RUN_STATUS_PASS_SCIENTIFIC_VALIDATION_PENDING'; $exitCode = 0; $fullCompleted = 'YES_PENDING_SCIENTIFIC_VALIDATION' }
            else { $finalResult = 'FAIL'; $finalReason = ('RUNNER_EXIT_' + $run.exit_code + '_STATUS_' + $status + '_UNCHANGED_' + $unchanged); $exitCode = 3 }
        }
    }
    $script:TryCompleted = $true
} catch {
    $script:Caught = $true
    $msg = [string]$_.Exception.Message
    if ($msg.StartsWith('BLOCKED:', [System.StringComparison]::Ordinal)) { $finalReason = $msg.Substring(8) } else { $finalReason = 'UNEXPECTED_' + $_.Exception.GetType().FullName + ':' + $msg }
    $finalResult = 'BLOCKED'
    $exitCode = 2
    if ($fullStarted -eq 'YES') { $exitCode = 3 }
    try { Write-PflLog ('ERROR PHASE=' + $script:Phase + ' REASON=' + $finalReason) } catch { Write-Host ('ERROR ' + $finalReason) }
} finally {
    if (-not $script:TryCompleted -and -not $script:Caught) {
        $script:Interrupted = $true
        $finalResult = 'SAFE_STOP'
        $finalReason = 'LAUNCHER_INTERRUPTED_CTRL_C_RUNNER_RECONCILED_NOT_KILLED'
        $exitCode = 130
        if ($null -ne $script:ActiveChild) {
            try { [void]$script:ActiveChild.WaitForExit(300000); $body['child_after_interrupt'] = [ordered]@{ pid = $script:ActiveChild.Id; exited = $script:ActiveChild.HasExited; killed = $false } } catch { $body['child_after_interrupt'] = [ordered]@{ error = $_.Exception.GetType().FullName; killed = $false } }
        }
    }
    if ($null -ne $script:RunDir) {
        try {
            $doc = [ordered]@{
                schema = 'PERSEU_C2_FULL_LAUNCHER_V001_RECEIPT'; PROJECT = $ProjectName; THREAD = $ThreadName; REVISION = $Revision
                POLICY_MASTER_SHA256_AT_BUILD = $PolicyMasterSha256; MODE = $Mode; RUN_ID = $runId; started_at = $startedAt; finished_at = (Get-PflTimestamp)
                RESULT = $finalResult; REASON = $finalReason; EXIT_CODE = $exitCode; LAST_PHASE = $script:Phase; INTERRUPTED = $script:Interrupted
                powershell = ($edition + ' ' + [string]$psVer); wrapper_path = $wrapperPath; wrapper_sha256 = $wrapperSha
                source_lock_path = $SourceLockPath; source_lock_sha256_param = $SourceLockSha256
                C2_FULL_STARTED = $fullStarted; C2_FULL_COMPLETED = $fullCompleted; PARTIAL_EFFECT = $partialEffect
                body = $body; SOURCE_DELETE = 'NO'; RESULT_RETURN_TO = $ResultFooter
            }
            $receiptPath = [System.IO.Path]::Combine($script:RunDir, 'RECEIPT_' + $Mode.ToUpperInvariant() + '.json')
            Write-PflNewText -LiteralPath $receiptPath -Text (ConvertTo-Json -InputObject $doc -Depth 10)
            $receiptSha = Get-PflSha -LiteralPath $receiptPath
        } catch {
            $finalReason = 'RECEIPT_WRITE_FAILED:' + [string]$_.Exception.Message + ' PRIMARY=' + $finalReason
            if ($exitCode -eq 0) { $exitCode = 2 }
            $finalResult = 'BLOCKED'
            try { Write-PflLog ('RECEIPT_WRITE_FAILED ' + [string]$_.Exception.Message) } catch { Write-Host 'RECEIPT_WRITE_FAILED' }
        }
    }
    try {
        Write-PflLog '=== SUMMARY ==='
        Write-PflLog ('RESULT=' + $finalResult)
        Write-PflLog ('REASON=' + $finalReason)
        Write-PflLog ('EXIT_CODE=' + $exitCode)
        Write-PflLog ('MODE=' + $Mode)
        Write-PflLog ('C2_FULL_STARTED=' + $fullStarted + ' C2_FULL_COMPLETED=' + $fullCompleted + ' PARTIAL_EFFECT=' + $partialEffect)
        Write-PflLog ('RUN_DIR=' + $script:RunDir)
        Write-PflLog ('RECEIPT=' + $receiptPath)
        Write-PflLog ('RECEIPT_SHA256=' + $receiptSha)
        Write-PflLog ('WRAPPER_SHA256=' + $wrapperSha)
        Write-PflLog $ResultFooter
    } catch {
        Write-Host $ResultFooter
    }
    if ($script:Interrupted -and ([System.Environment]::CommandLine -match '(?i)\s-File\s')) {
        [System.Environment]::Exit($exitCode)
    }
}
exit $exitCode
