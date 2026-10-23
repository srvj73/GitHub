# PEGASUS FULL 2026 V008R2 - bootstrap Windows PowerShell 5.1 Desktop. ASCII, sem BOM.
# Uso a partir de PS C:\Users\silvi> (sem cd):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R12_PS51.ps1 -Mode Verify
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R12_PS51.ps1 -Mode QualifyNative
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R12_PS51.ps1 -Mode Install
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R12_PS51.ps1 -Mode Rollback
# Log SEMPRE em pasta absoluta fixa, nova por execucao, independente da pasta atual:
#   C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt
# Classificacao de exit (unica para bootstrap e supervisor):
#   0 = PASS | 2 = BLOCKED fail-closed sem efeito (inclui UAC negado) | 3 = FAIL apos inicio de efeito
#   130 = SAFE_STOP confirmado (somente supervisor). Exit nulo/ausente NUNCA vira 0: e FAIL.
# Nao executa QS4, FULL economico, Phase B/C nem reselection. Nao altera ExecutionPolicy permanente,
# ACL produtiva, D: ou servicos. Falha preserva evidencias; nao ha retry automatico.
[CmdletBinding()]
param(
    [ValidateSet('Verify','QualifyNative','Install','Rollback')][string]$Mode = 'Verify',
    [string]$RunRoot = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ZipName          = 'PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R12_20261023.zip'
$ExpectedZipSha   = 'EA17EDE35C577CE1D69CB91D529F166B39FBD6B779D6F347487B65E3BF587082'
$ExpectedManifest = 'D49A54D8D9778A65CC597442FFCEB8041D3195C22566800EBB3E3536ACAD8035'
$TreeName         = 'PEGASUS_FULL_2026_ENGINEERING_FINAL_V008'
$Downloads        = 'C:\Users\silvi\Downloads'
$RunsBase         = 'C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS'
$Python           = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$ExpectedPySha    = '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
$Footer           = 'RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementacao Runner Paralelo 14'

$IsTopLevel = [string]::IsNullOrEmpty($RunRoot)
$ResultCode = 2
$Facts = [ordered]@{ schema = 'PEGASUS_FULL_2026_V008R2_WINDOWS_CAMPAIGN_RESULT'; mode = $Mode; top_level = $IsTopLevel;
    g4 = 'FROZEN'; qs4 = 'NO'; full_economic = 'NO'; phase_c = 'FORBIDDEN'; reselection_2026 = 'FORBIDDEN';
    run_released = 'NO'; full_released = 'NO'; steps = [ordered]@{} }

# ---------------------------------------------------------------- pasta de log fixa
if ($IsTopLevel) {
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
function Write-Utf8NoBom([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
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
function Get-PegasusExitCode($Child) {
    # Exit so e aceito de processo comprovadamente encerrado e com codigo presente.
    # Ausencia de codigo NUNCA e convertida em 0 (defeito R1: [int]$null == 0).
    if ($null -eq $Child) { throw 'NATIVE_PROCESS_OBJECT_NULL' }
    if (-not $Child.HasExited) { throw 'NATIVE_EXIT_READ_BEFORE_EXIT' }
    $Raw = $Child.ExitCode
    if ($null -eq $Raw) { throw 'NATIVE_EXIT_NULL' }
    return [int]$Raw
}
function Resolve-PegasusRelayExit($ProcessExit, $FileExit) {
    # Pai apos UAC: o exit do processo elevado deve coincidir com o exit que o proprio
    # elevado gravou em CAMPAIGN_RESULT.json. Nulo, ausente ou divergente => FAIL (3).
    if ($null -eq $ProcessExit -or $null -eq $FileExit) { return 3 }
    if ([int]$ProcessExit -ne [int]$FileExit) { return 3 }
    return [int]$ProcessExit
}
function Invoke-Native([string]$Exe, [string[]]$NativeArgs, [string]$Label, [int[]]$Expected, [int]$TimeoutS = 3600) {
    $OutPath = Join-Path $RunRoot ($Label + '.stdout.txt'); $ErrPath = Join-Path $RunRoot ($Label + '.stderr.txt')
    $Info = New-Object System.Diagnostics.ProcessStartInfo
    $Info.FileName = $Exe
    $Info.Arguments = [string]::Join(' ', [string[]]@($NativeArgs | ForEach-Object { ConvertTo-PegasusNativeArgument $_ }))
    $Info.WorkingDirectory = $RunRoot
    $Info.UseShellExecute = $false
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Info.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $Info.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false)
    # Higiene de ambiente identica ao V003 (Invoke-PegasusNative) + stdio UTF-8 deterministico.
    $Info.EnvironmentVariables['PYTHONNOUSERSITE'] = '1'
    $Info.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $Info.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $Info.EnvironmentVariables['OPENBLAS_NUM_THREADS'] = '1'
    $Info.EnvironmentVariables['OMP_NUM_THREADS'] = '1'
    $Info.EnvironmentVariables.Remove('PYTHONPATH')
    $Info.EnvironmentVariables.Remove('PYTHONHOME')
    Write-Log ('NATIVE_START label=' + $Label + ' expected=' + ($Expected -join ','))
    $Child = New-Object System.Diagnostics.Process
    $Child.StartInfo = $Info
    if (-not $Child.Start()) { throw ('NATIVE_START_FAILED label=' + $Label) }
    $null = $Child.Handle   # retem o handle ja no inicio: ExitCode legivel mesmo em saida rapida
    $ChildId = $Child.Id
    $Created = 'UNKNOWN'
    try { $Created = $Child.StartTime.ToUniversalTime().ToString('o') } catch { $Created = 'UNKNOWN' }
    $OutTask = $Child.StandardOutput.ReadToEndAsync()
    $ErrTask = $Child.StandardError.ReadToEndAsync()
    $Clock = [Diagnostics.Stopwatch]::StartNew()
    while (-not $Child.WaitForExit(10000)) {
        Write-Log ('BOOTSTRAP_HEARTBEAT label=' + $Label + ' pid=' + $ChildId + ' elapsed_s=' + [int]$Clock.Elapsed.TotalSeconds)
        if ($Clock.Elapsed.TotalSeconds -gt $TimeoutS) {
            $Rec = [ordered]@{ schema = 'PEGASUS_FULL_2026_V008R2_TIMEOUT_RECONCILE'; label = $Label; pid = $ChildId;
                creation_time_utc = $Created; timeout_s = $TimeoutS; kill_performed = $false;
                result = 'FAIL_RECONCILE_LIVE_CHILD' }
            Write-Utf8NoBom (Join-Path $RunRoot ('TIMEOUT_RECONCILE_' + $Label + '.json')) ($Rec | ConvertTo-Json -Depth 4)
            $Facts.steps[$Label] = [ordered]@{ expected = $Expected; observed = $null; classification = 'TIMEOUT_NO_KILL';
                pid = $ChildId; creation_time_utc = $Created; seconds = [math]::Round($Clock.Elapsed.TotalSeconds, 3) }
            throw ('NATIVE_TIMEOUT_NO_KILL_RECONCILE label=' + $Label + ' pid=' + $ChildId)
        }
    }
    $Code = Get-PegasusExitCode $Child
    $Drained = $OutTask.Wait(120000) -and $ErrTask.Wait(120000)
    $OutText = ''; $ErrText = ''
    if ($OutTask.IsCompleted) { $OutText = $OutTask.Result }
    if ($ErrTask.IsCompleted) { $ErrText = $ErrTask.Result }
    Write-Utf8NoBom $OutPath $OutText
    Write-Utf8NoBom $ErrPath $ErrText
    $Seconds = [math]::Round($Clock.Elapsed.TotalSeconds, 3)
    $Class = 'MATCH'
    if (-not $Drained) { $Class = 'STREAM_DRAIN_TIMEOUT' }
    elseif (-not ($Expected -contains $Code)) { $Class = 'MISMATCH' }
    $Facts.steps[$Label] = [ordered]@{ expected = $Expected; observed = $Code; classification = $Class; pid = $ChildId;
        creation_time_utc = $Created; seconds = $Seconds; stdout_bytes = $OutText.Length; stderr_bytes = $ErrText.Length }
    Write-Log ('NATIVE_EXIT label=' + $Label + ' code=' + $Code + ' expected=' + ($Expected -join ',') + ' class=' + $Class + ' seconds=' + $Seconds)
    foreach ($Line in @(($OutText + "`n" + $ErrText) -split "`r?`n")) {
        if ($Line.Length -gt 0 -and $Line.Length -le 4000) { Write-Log ('  | ' + $Line) }
    }
    $Child.Dispose()
    return $Code
}
function Invoke-NativeExpect([string]$Exe, [string[]]$NativeArgs, [string]$Label, [int[]]$Expected, [string]$FailTag, [int]$TimeoutS = 3600) {
    $Code = Invoke-Native $Exe $NativeArgs $Label $Expected $TimeoutS
    if ($Facts.steps[$Label].classification -ne 'MATCH') { throw ($FailTag + ' observed=' + $Code + ' expected=' + ($Expected -join ',') + ' class=' + $Facts.steps[$Label].classification) }
    return $Code
}
function Invoke-ExitCanary {
    # S00: prova, no runtime alvo, a fronteira de exit/stdio ANTES de qualquer efeito.
    foreach ($C in @(0, 2, 3, 7, 19, 37, 130)) {
        [void](Invoke-NativeExpect $Python @('-I', '-c', ('import sys; sys.exit(' + $C + ')')) ('S00_CANARY_EXIT_' + $C) @($C) 'EXIT_CANARY_FAILED' 60)
    }
    $Big = "import sys; sys.stdout.write('o'*2097152); sys.stderr.write('e'*2097152); sys.stdout.flush(); sys.stderr.flush(); sys.exit(5)"
    [void](Invoke-NativeExpect $Python @('-I', '-c', $Big) 'S00_CANARY_STREAMS_2MB' @(5) 'EXIT_CANARY_FAILED' 120)
    $St = $Facts.steps['S00_CANARY_STREAMS_2MB']
    if ($St.stdout_bytes -ne 2097152 -or $St.stderr_bytes -ne 2097152) { throw ('EXIT_CANARY_STREAM_TRUNCATED out=' + $St.stdout_bytes + ' err=' + $St.stderr_bytes) }
    Write-Log 'S00_EXIT_AND_STREAM_CANARY=PASS'
}

$ExtractStarted = $false
$Relaunched = $false
try {
    Write-Log ('PEGASUS_V008R2_BOOTSTRAP mode=' + $Mode + ' top_level=' + $IsTopLevel + ' run_root=' + $RunRoot + ' bootstrap_sha256=' + (Get-Sha $PSCommandPath))
    if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'WINDOWS_POWERSHELL_5_1_DESKTOP_REQUIRED' }
    $Facts.ps_version = $PSVersionTable.PSVersion.ToString(); $Facts.os_build = [Environment]::OSVersion.Version.ToString()
    $Facts.elevated = (Test-Elevated); $Facts.logical_cpus = [Environment]::ProcessorCount
    $Facts.bootstrap_sha256 = (Get-Sha $PSCommandPath)

    if ($Mode -ne 'Verify' -and -not $Facts.elevated) {
        if (-not $IsTopLevel) { throw 'ELEVATED_INSTANCE_NOT_ELEVATED' }
        Write-Log ('ELEVATION_REQUIRED mode=' + $Mode + ': relaunching with UAC into the SAME run root')
        $Psi = New-Object System.Diagnostics.ProcessStartInfo
        $Psi.FileName = Join-Path $PSHOME 'powershell.exe'
        $Psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Mode ' + $Mode + ' -RunRoot "' + $RunRoot + '"'
        $Psi.UseShellExecute = $true
        $Psi.Verb = 'runas'
        $E = $null
        try { $E = [System.Diagnostics.Process]::Start($Psi) } catch { throw ('UAC_RELAUNCH_DECLINED_OR_FAILED ' + $_.Exception.Message) }
        if ($null -eq $E) { throw 'UAC_RELAUNCH_NOT_STARTED' }
        $null = $E.Handle
        $E.WaitForExit()
        $ProcExit = $null
        try { $ProcExit = Get-PegasusExitCode $E } catch { $ProcExit = $null; Write-Log ('ELEVATED_PROCESS_EXIT_UNREADABLE=' + $_.Exception.Message) }
        $FileExit = $null
        $ChildJson = Join-Path $RunRoot 'CAMPAIGN_RESULT.json'
        if (Test-Path -LiteralPath $ChildJson) { $FileExit = (Get-Content -LiteralPath $ChildJson -Raw | ConvertFrom-Json).exit_code }
        $ResultCode = Resolve-PegasusRelayExit $ProcExit $FileExit
        $Facts.relay = [ordered]@{ elevated_process_exit = $ProcExit; elevated_file_exit = $FileExit; final_exit = $ResultCode;
            consistent = ($null -ne $ProcExit -and $null -ne $FileExit -and [int]$ProcExit -eq [int]$FileExit) }
        Write-Log ('ELEVATED_RELAY process_exit=' + $ProcExit + ' file_exit=' + $FileExit + ' final_exit=' + $ResultCode)
        $Relaunched = $true
    }
    if (-not $Relaunched) {

    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'PINNED_PYTHON_NOT_FOUND' }
    $PySha = Get-Sha $Python; $Facts.python_sha256 = $PySha
    if ($PySha -ne $ExpectedPySha) { throw ('PINNED_PYTHON_SHA_CHANGED ' + $PySha) }
    $Ver = @(& $Python --version)
    if ($LASTEXITCODE -ne 0 -or $Ver.Count -ne 1 -or $Ver[0] -ne 'Python 3.14.7') { throw 'PYTHON_3_14_7_REQUIRED' }
    Invoke-ExitCanary

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
    [void](Invoke-NativeExpect $Python @('-I','-B',$Sup,'verify') 'S01_SUPERVISOR_VERIFY' @(0) 'SUPERVISOR_VERIFY_FAILED' 300)
    [void](Invoke-NativeExpect $Python @('-I','-B',(Join-Path $Tree 'CODE\pegasus_entry.py'),'verify') 'S02_ENTRY_VERIFY' @(0) 'ENTRY_VERIFY_FAILED' 300)
    $Probe = Join-Path $RunRoot 'ARGV_PROBE.json'
    [void](Invoke-NativeExpect $Python @('-I','-B',(Join-Path $Tree 'tests\argv_probe.py'),$Probe,'space value','literal"quote','tail\') 'S03_ARGV_EXIT_PROBE' @(37) 'ARGV_EXIT_PROPAGATION_PROBE_FAILED' 60)
    foreach ($C in @('run-b','run-c','run-full')) {
        [void](Invoke-NativeExpect $Python @('-I','-B',$Sup,$C) ('S04_FAILCLOSED_' + $C) @(2) ('ECONOMIC_MODE_NOT_BLOCKED ' + $C) 300)
    }
    Write-Log 'G0_AND_FAILCLOSED_CHAIN=PASS'

    if ($Mode -eq 'QualifyNative') {
        $Venv = Join-Path $RunRoot 'venv314'
        [void](Invoke-NativeExpect $Python @('-I','-m','venv',$Venv) 'S05_VENV' @(0) 'VENV_CREATE_FAILED' 600)
        $VPy = Join-Path $Venv 'Scripts\python.exe'
        $Lock = Join-Path $Tree 'dependencies\requirements_windows.lock'
        $Wheels = Join-Path $Tree 'dependencies'
        [void](Invoke-NativeExpect $VPy @('-I','-m','pip','install','--no-index','--require-hashes','--find-links',$Wheels,'-r',$Lock) 'S06_OFFLINE_NUMPY' @(0) 'OFFLINE_WHEEL_INSTALL_FAILED' 900)
        $Evidence = Join-Path $RunRoot 'QUALIFY'
        # O filho supervisionado recebe console proprio oculto; o Ctrl+C real do SAFE_STOP e entregue
        # so a esse console pelo helper V003 CODE\r1r11_signal.py (este PowerShell nao e atingido).
        $Q = Invoke-Native $VPy @('-B',$Sup,'qualify','--evidence',$Evidence) 'S07_SUPERVISED_NATIVE_QUALIFICATION' @(0) 7200
        $Facts.qualification_exit = $Q
        $Rec = Join-Path $Evidence 'V008_QUALIFICATION_RECEIPT.json'
        if (Test-Path -LiteralPath $Rec) { $Facts.qualification_receipt_sha256 = (Get-Sha $Rec) }
        if ($Facts.steps['S07_SUPERVISED_NATIVE_QUALIFICATION'].classification -ne 'MATCH') { throw ('NATIVE_QUALIFICATION_EXIT=' + $Q) }
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
            [void](Invoke-NativeExpect $Icacls @($Staging,'/inheritance:r','/grant:r','*S-1-5-32-544:(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-545:(OI)(CI)RX') 'S08_INSTALL_DACL' @(0) 'INSTALL_DACL_FAILED' 300)
            Move-Item -LiteralPath $Staging -Destination $InstallRoot
            $InstSup = Join-Path $InstallRoot 'supervisor\pegasus_supervisor_v008.py'
            [void](Invoke-NativeExpect $Python @('-I','-B',$InstSup,'verify') 'S09_INSTALLED_TREE_VERIFY' @(0) 'INSTALLED_TREE_VERIFY_FAILED' 300)
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
    Write-Log ('PEGASUS_V008R2_BLOCKED=' + $_.Exception.Message)
    $Facts.primary_failure = $_.Exception.Message
    if ($ExtractStarted) { $ResultCode = 3 } else { $ResultCode = 2 }
} finally {
    $Classes = @{ 0 = 'PASS'; 2 = 'BLOCKED_FAIL_CLOSED_NO_EFFECT'; 3 = 'FAIL_TECHNICAL_AFTER_EFFECT_START' }
    $Facts.exit_code = $ResultCode; $Facts.run_root = $RunRoot
    if ($Classes.ContainsKey($ResultCode)) { $Facts.exit_class = $Classes[$ResultCode] } else { $Facts.exit_class = 'UNCLASSIFIED_FAIL' }
    try {
        if ($Relaunched) { $JsonName = 'RELAY_RESULT_TOPLEVEL.json' } else { $JsonName = 'CAMPAIGN_RESULT.json' }
        $Json = Join-Path $RunRoot $JsonName
        if (-not (Test-Path -LiteralPath $Json)) { Write-Utf8NoBom $Json ($Facts | ConvertTo-Json -Depth 8) }
        Write-Log ('FINAL exit_code=' + $ResultCode + ' class=' + $Facts.exit_class + ' top_level=' + $IsTopLevel)
        if ($IsTopLevel) {
            Write-Log 'Devolva este resultado ao ChatGPT, no projeto Pegasus Original, conversa Implementacao Runner Paralelo 14. Anexe as evidencias existentes e cole esta resposta.'
            Write-Log $Footer
            # Selado SOMENTE agora: o ZIP contem o log completo das duas instancias.
            $ResultZip = Join-Path $RunsBase ((Split-Path $RunRoot -Leaf) + '_RESULT.zip')
            if (-not (Test-Path -LiteralPath $ResultZip)) {
                $Items = @(Get-ChildItem -LiteralPath $RunRoot -Force | Where-Object { $_.Name -ne 'PACKAGE' -and $_.Name -ne 'venv314' })
                if ($Items.Count -gt 0) { Compress-Archive -LiteralPath ($Items | ForEach-Object { $_.FullName }) -DestinationPath $ResultZip }
            }
            if (Test-Path -LiteralPath $ResultZip) {
                $ZipHash = Get-Sha $ResultZip
                Write-Utf8NoBom ($ResultZip + '.sha256.txt') ($ZipHash + '  ' + (Split-Path $ResultZip -Leaf) + "`r`n")
                Write-Host ('RESULT_ZIP=' + $ResultZip)
                Write-Host ('RESULT_ZIP_SHA256=' + $ZipHash)
            }
        }
    } catch { Write-Host ('RESULT_PACKAGING_FAILED=' + $_.Exception.Message); if ($ResultCode -eq 0) { $ResultCode = 3 } }
}
exit $ResultCode
