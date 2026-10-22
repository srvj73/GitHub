# PEGASUS FULL 2026 V008 - bootstrap Windows PowerShell 5.1 Desktop. ASCII, sem BOM.
# Uso a partir de PS C:\Users\silvi> (sem cd):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode Verify
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode QualifyNative
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode Install
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode Rollback
# Log SEMPRE em pasta absoluta fixa, nova por execucao, independente da pasta atual:
#   C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt
# Nao executa QS4, FULL economico, Phase B/C nem reselection. Nao altera ExecutionPolicy permanente,
# ACL produtiva, D: ou servicos. Falha preserva evidencias; nao ha retry automatico.
[CmdletBinding()]
param(
    [ValidateSet('Verify','QualifyNative','Install','Rollback')][string]$Mode = 'Verify',
    [string]$RunRoot = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ZipName          = '@@ZIP_NAME@@'
$ExpectedZipSha   = '@@ZIP_SHA256@@'
$ExpectedManifest = '@@MANIFEST_SHA256@@'
$TreeName         = '@@TREE_NAME@@'
$Downloads        = 'C:\Users\silvi\Downloads'
$RunsBase         = 'C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS'
$Python           = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$ExpectedPySha    = '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
$Footer           = 'RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementacao Runner Paralelo 14'

$ResultCode = 2
$Facts = [ordered]@{ schema = 'PEGASUS_FULL_2026_V008_WINDOWS_CAMPAIGN_RESULT_V001'; mode = $Mode;
    g4 = 'FROZEN'; qs4 = 'NO'; full_economic = 'NO'; phase_c = 'FORBIDDEN'; reselection_2026 = 'FORBIDDEN';
    run_released = 'NO'; full_released = 'NO'; steps = [ordered]@{} }

# ---------------------------------------------------------------- pasta de log fixa
if ([string]::IsNullOrEmpty($RunRoot)) {
    $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff')
    $RunRoot = Join-Path $RunsBase ($Mode.ToUpperInvariant() + '_' + $Stamp + '_' + $PID)
    if (Test-Path -LiteralPath $RunRoot) { throw 'RUN_ROOT_COLLISION' }
    [void][System.IO.Directory]::CreateDirectory($RunRoot)
} else {
    if (-not $RunRoot.StartsWith($RunsBase + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'RUN_ROOT_OUTSIDE_FIXED_BASE' }
    if (-not (Test-Path -LiteralPath $RunRoot -PathType Container)) { throw 'ELEVATED_RUN_ROOT_ABSENT' }
}
$Log = Join-Path $RunRoot 'RUN_LOG.txt'
function Write-Log([string]$Text) {
    $Line = (Get-Date).ToString('o') + ' ' + $Text
    Write-Host $Line
    [System.IO.File]::AppendAllText($Log, $Line + "`r`n", [System.Text.Encoding]::ASCII)
}
function Get-Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant() }
function Test-Elevated {
    $Id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($Id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function ConvertTo-PegasusNativeArgument([string]$Value) {
    # Copia exata da camada unica de serializacao argv do bootstrap V003.
    $Builder = New-Object System.Text.StringBuilder
    [void]$Builder.Append('"')
    $SlashCount = 0
    foreach ($Character in $Value.ToCharArray()) {
        if ($Character -eq [char]92) { $SlashCount++; continue }
        if ($Character -eq [char]34) {
            [void]$Builder.Append(([string][char]92) * ($SlashCount * 2 + 1))
            [void]$Builder.Append($Character)
        } else {
            [void]$Builder.Append(([string][char]92) * $SlashCount)
            [void]$Builder.Append($Character)
        }
        $SlashCount = 0
    }
    [void]$Builder.Append(([string][char]92) * ($SlashCount * 2))
    [void]$Builder.Append('"')
    return $Builder.ToString()
}
function Invoke-Native([string]$Exe, [string[]]$NativeArgs, [string]$Label, [int]$TimeoutS = 3600) {
    $Out = Join-Path $RunRoot ($Label + '.stdout.txt'); $Err = Join-Path $RunRoot ($Label + '.stderr.txt')
    $Serialized = [string]::Join(' ', [string[]]@($NativeArgs | ForEach-Object { ConvertTo-PegasusNativeArgument $_ }))
    Write-Log ('NATIVE_START label=' + $Label)
    $P = Start-Process -FilePath $Exe -ArgumentList $Serialized -RedirectStandardOutput $Out -RedirectStandardError $Err -PassThru -NoNewWindow
    $Clock = [Diagnostics.Stopwatch]::StartNew()
    while (-not $P.WaitForExit(10000)) {
        Write-Log ('BOOTSTRAP_HEARTBEAT label=' + $Label + ' pid=' + $P.Id + ' elapsed_s=' + [int]$Clock.Elapsed.TotalSeconds)
        if ($Clock.Elapsed.TotalSeconds -gt $TimeoutS) { throw ('NATIVE_TIMEOUT_NO_KILL_RECONCILE label=' + $Label + ' pid=' + $P.Id) }
    }
    $P.WaitForExit(); $Code = [int]$P.ExitCode
    Write-Log ('NATIVE_EXIT label=' + $Label + ' code=' + $Code)
    foreach ($F in @($Out, $Err)) { if (Test-Path -LiteralPath $F) { Get-Content -LiteralPath $F | ForEach-Object { Write-Log ('  | ' + $_) } } }
    $Facts.steps[$Label] = $Code
    return $Code
}

$ExtractStarted = $false
$Relaunched = $false
try {
    Write-Log ('PEGASUS_V008_BOOTSTRAP mode=' + $Mode + ' run_root=' + $RunRoot + ' bootstrap_sha256=' + (Get-Sha $PSCommandPath))
    if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'WINDOWS_POWERSHELL_5_1_DESKTOP_REQUIRED' }
    $Facts.ps_version = $PSVersionTable.PSVersion.ToString(); $Facts.os_build = [Environment]::OSVersion.Version.ToString()
    $Facts.elevated = (Test-Elevated); $Facts.logical_cpus = [Environment]::ProcessorCount

    if ($Mode -ne 'Verify' -and -not $Facts.elevated) {
        Write-Log ('ELEVATION_REQUIRED mode=' + $Mode + ': relaunching with UAC into the SAME run root')
        $Args2 = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Mode ' + $Mode + ' -RunRoot "' + $RunRoot + '"'
        $E = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $Args2 -Verb RunAs -Wait -PassThru
        Write-Log ('ELEVATED_INSTANCE_EXIT=' + $E.ExitCode)
        $ResultCode = [int]$E.ExitCode
        $Relaunched = $true
    }
    if (-not $Relaunched) {

    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'PINNED_PYTHON_NOT_FOUND' }
    $PySha = Get-Sha $Python; $Facts.python_sha256 = $PySha
    if ($PySha -ne $ExpectedPySha) { throw ('PINNED_PYTHON_SHA_CHANGED ' + $PySha) }
    $Ver = @(& $Python --version)
    if ($LASTEXITCODE -ne 0 -or $Ver.Count -ne 1 -or $Ver[0] -ne 'Python 3.14.7') { throw 'PYTHON_3_14_7_REQUIRED' }

    $Zip = Join-Path $Downloads $ZipName
    if (-not (Test-Path -LiteralPath $Zip -PathType Leaf)) { throw ('PACKAGE_ZIP_NOT_FOUND ' + $Zip) }
    $ZipSha = Get-Sha $Zip; $Facts.zip_sha256 = $ZipSha
    if ($ZipSha -ne $ExpectedZipSha) { throw ('PACKAGE_ZIP_SHA_MISMATCH ' + $ZipSha) }
    Write-Log ('PACKAGE_ZIP_SHA256=PASS ' + $ZipSha)

    # Autoextracao segura em root novo dentro da pasta da execucao.
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Extract = Join-Path $RunRoot 'PACKAGE'
    $ExtractStarted = $true
    [void][System.IO.Directory]::CreateDirectory($Extract)
    $Archive = [System.IO.Compression.ZipFile]::OpenRead($Zip)
    try {
        $Seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach ($Entry in $Archive.Entries) {
            $Name = $Entry.FullName
            if ([string]::IsNullOrEmpty($Name) -or $Name.Contains('\') -or $Name.Contains(':') -or $Name.StartsWith('/') -or $Name.EndsWith('/') -or @($Name.Split('/') | Where-Object { $_ -eq '..' -or $_ -eq '.' -or $_ -eq '' }).Count -gt 0 -or -not $Seen.Add($Name)) { throw ('ZIP_UNSAFE_OR_DUPLICATE_MEMBER ' + $Name) }
            if (-not $Name.StartsWith($TreeName + '/')) { throw ('ZIP_MEMBER_OUTSIDE_TREE ' + $Name) }
            if ((($Entry.ExternalAttributes -shr 16) -band 61440) -eq 40960) { throw 'ZIP_SYMLINK_FORBIDDEN' }
        }
        foreach ($Entry in $Archive.Entries) {
            $Target = Join-Path $Extract ($Entry.FullName.Replace('/', '\'))
            [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($Target))
            $Src = $Entry.Open()
            $Dst = New-Object System.IO.FileStream($Target, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
            try { $Src.CopyTo($Dst); $Dst.Flush($true) } finally { $Dst.Dispose(); $Src.Dispose() }
        }
    } finally { $Archive.Dispose() }
    $Tree = Join-Path $Extract $TreeName
    $ManSha = Get-Sha (Join-Path $Tree 'MANIFEST_SHA256.json'); $Facts.manifest_sha256 = $ManSha
    if ($ManSha -ne $ExpectedManifest) { throw ('MANIFEST_SHA_MISMATCH ' + $ManSha) }
    Write-Log ('EXTRACTED_TREE=' + $Tree)

    $Sup = Join-Path $Tree 'supervisor\pegasus_supervisor_v008.py'
    if ((Invoke-Native $Python @('-I','-B',$Sup,'verify') 'S01_SUPERVISOR_VERIFY' 300) -ne 0) { throw 'SUPERVISOR_VERIFY_FAILED' }
    if ((Invoke-Native $Python @('-I','-B',(Join-Path $Tree 'CODE\pegasus_entry.py'),'verify') 'S02_ENTRY_VERIFY' 300) -ne 0) { throw 'ENTRY_VERIFY_FAILED' }
    $Probe = Join-Path $RunRoot 'ARGV_PROBE.json'
    if ((Invoke-Native $Python @('-I','-B',(Join-Path $Tree 'tests\argv_probe.py'),$Probe,'space value','literal"quote','tail\') 'S03_ARGV_EXIT_PROBE' 60) -ne 37) { throw 'ARGV_EXIT_PROPAGATION_PROBE_FAILED' }
    foreach ($C in @('run-b','run-c','run-full')) {
        if ((Invoke-Native $Python @('-I','-B',$Sup,$C) ('S04_FAILCLOSED_' + $C) 300) -ne 2) { throw ('ECONOMIC_MODE_NOT_BLOCKED ' + $C) }
    }
    Write-Log 'G0_AND_FAILCLOSED_CHAIN=PASS'

    if ($Mode -eq 'QualifyNative') {
        $Venv = Join-Path $RunRoot 'venv314'
        if ((Invoke-Native $Python @('-I','-m','venv',$Venv) 'S05_VENV' 600) -ne 0) { throw 'VENV_CREATE_FAILED' }
        $VPy = Join-Path $Venv 'Scripts\python.exe'
        $Lock = Join-Path $Tree 'dependencies\requirements_windows.lock'
        $Wheels = Join-Path $Tree 'dependencies'
        if ((Invoke-Native $VPy @('-I','-m','pip','install','--no-index','--require-hashes','--find-links',$Wheels,'-r',$Lock) 'S06_OFFLINE_NUMPY' 900) -ne 0) { throw 'OFFLINE_WHEEL_INSTALL_FAILED' }
        $Evidence = Join-Path $RunRoot 'QUALIFY'
        # O filho supervisionado recebe console proprio oculto; o Ctrl+C real do SAFE_STOP e entregue
        # so a esse console pelo helper V003 CODE\r1r11_signal.py (este PowerShell nao e atingido).
        $Q = Invoke-Native $VPy @('-B',$Sup,'qualify','--evidence',$Evidence) 'S07_SUPERVISED_NATIVE_QUALIFICATION' 7200
        $Facts.qualification_exit = $Q
        $Rec = Join-Path $Evidence 'V008_QUALIFICATION_RECEIPT.json'
        if (Test-Path -LiteralPath $Rec) { $Facts.qualification_receipt_sha256 = (Get-Sha $Rec) }
        if ($Q -ne 0) { throw ('NATIVE_QUALIFICATION_EXIT=' + $Q) }
    }
    if ($Mode -eq 'Install' -or $Mode -eq 'Rollback') {
        $InstallRoot = 'C:\ProgramData\PEGASUS_FULL_2026_V008_' + $ExpectedManifest.Substring(0, 16)
        $Facts.install_root = $InstallRoot
        if ($Mode -eq 'Install') {
            if (Test-Path -LiteralPath $InstallRoot) { throw ('INSTALL_ROOT_EXISTS_NO_OVERWRITE ' + $InstallRoot) }
            $Staging = $InstallRoot + '.staging_' + $PID
            if (Test-Path -LiteralPath $Staging) { throw 'INSTALL_STAGING_COLLISION' }
            Copy-Item -LiteralPath $Tree -Destination $Staging -Recurse
            $Icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
            & $Icacls $Staging '/inheritance:r' '/grant:r' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | ForEach-Object { Write-Log ('  | ' + $_) }
            if ($LASTEXITCODE -ne 0) { throw 'INSTALL_DACL_FAILED' }
            Move-Item -LiteralPath $Staging -Destination $InstallRoot
            $InstSup = Join-Path $InstallRoot 'supervisor\pegasus_supervisor_v008.py'
            if ((Invoke-Native $Python @('-I','-B',$InstSup,'verify') 'S08_INSTALLED_TREE_VERIFY' 300) -ne 0) { throw 'INSTALLED_TREE_VERIFY_FAILED' }
            if ((Get-Sha (Join-Path $InstallRoot 'MANIFEST_SHA256.json')) -ne $ExpectedManifest) { throw 'INSTALLED_MANIFEST_MISMATCH' }
            $Acl = Get-Acl -LiteralPath $InstallRoot
            $Facts.install_dacl_protected = $Acl.AreAccessRulesProtected
            if (-not $Acl.AreAccessRulesProtected) { throw 'INSTALL_DACL_NOT_PROTECTED' }
            Write-Log ('INSTALLED_ROOT=' + $InstallRoot + ' (V007 root untouched)')
        } else {
            if (-not (Test-Path -LiteralPath $InstallRoot)) { throw ('ROLLBACK_TARGET_ABSENT ' + $InstallRoot) }
            $Retired = $InstallRoot + '_RETIRED_' + (Get-Date).ToString('yyyyMMdd_HHmmss_fff')
            Move-Item -LiteralPath $InstallRoot -Destination $Retired
            $Facts.retired_root = $Retired
            Write-Log ('ROLLBACK_NON_DESTRUCTIVE_RENAMED_TO=' + $Retired + ' (nothing deleted; V007 root untouched)')
        }
    }
    $ResultCode = 0
    Write-Log ('RESULT=PASS mode=' + $Mode)
    }
} catch {
    Write-Log ('PEGASUS_V008_BLOCKED=' + $_.Exception.Message)
    $Facts.primary_failure = $_.Exception.Message
    if ($ExtractStarted) { $ResultCode = 3 } else { $ResultCode = 2 }
} finally {
    $Facts.exit_code = $ResultCode; $Facts.run_root = $RunRoot
    try {
        $Json = Join-Path $RunRoot 'CAMPAIGN_RESULT.json'
        if (-not (Test-Path -LiteralPath $Json)) {
            ($Facts | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $Json -Encoding ASCII
        }
        $ResultZip = Join-Path $RunsBase ((Split-Path $RunRoot -Leaf) + '_RESULT.zip')
        if (-not (Test-Path -LiteralPath $ResultZip)) {
            $Items = @(Get-ChildItem -LiteralPath $RunRoot -Force | Where-Object { $_.Name -ne 'PACKAGE' -and $_.Name -ne 'venv314' })
            if ($Items.Count -gt 0) { Compress-Archive -LiteralPath ($Items | ForEach-Object { $_.FullName }) -DestinationPath $ResultZip }
        }
        if (Test-Path -LiteralPath $ResultZip) {
            Write-Log ('RESULT_ZIP=' + $ResultZip)
            Write-Log ('RESULT_ZIP_SHA256=' + (Get-Sha $ResultZip))
        }
    } catch { Write-Log ('RESULT_PACKAGING_FAILED=' + $_.Exception.Message) }
    Write-Log 'Devolva este resultado ao ChatGPT, no projeto Pegasus Original, conversa Implementacao Runner Paralelo 14. Anexe as evidencias existentes e cole esta resposta.'
    Write-Log $Footer
}
exit $ResultCode
