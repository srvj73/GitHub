#requires -Version 5.1
<#
CDT20 PRE-G06 - lancador integrado unico (Windows PowerShell 5.1 x64).

Uso (a partir de PS C:\Users\silvi>, sem cd):
  powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_CDT20_PRE_G06_INTEGRATED_20261020.ps1"
Retomada de uma raiz interrompida (mesmo pacote):
  ... -File "<este arquivo>" -ResumeRoot "C:\Users\silvi\AppData\Local\CDT20_R08\R08_Q1_..."
SAFE_STOP cooperativo durante a campanha: criar o arquivo SAFE_STOP.request na raiz RUN_ROOT impressa.

Etapas: preflight sem efeitos -> coleta read-only do log G0 de 20/10 -> staging hash-verificado em
LOCALAPPDATA -> G0 nativo (todas as suites DELTA no contexto da campanha) -> campanha PRE-G06
(11 consumidores, G3/G6, SAFE_STOP, MULTIWORK, provas G5) -> completude 5/5 e quatro achados ->
pacote unico de retorno. Nada de producao, B06, B07, D4/D5 produtivos, canario ou FULL.
Codigos: 0 PASS; 2 bloqueado antes de efeitos; 3 bloqueado apos efeitos run-owned; 130 SAFE_STOP.
#>
[CmdletBinding()]
param([string]$ResumeRoot = '')
$ErrorActionPreference = 'Stop'

# ---- Constantes fixas (regra do titular: log em pasta absoluta definida pelo script) ----
$Context        = 'ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 20'
$TransportName  = 'CDT20_PRE_G06_INTEGRATED_TRANSPORT_20261020.zip'
$TransportSha   = '61C0EFFA358D9CB04E90114CA5A7B544493B4DC5DB2B8E90DDDC6FB72B333C13'
$DownloadsRoot  = 'C:\Users\silvi\OneDrive\Downloads'
$RunsParent     = 'C:\Users\silvi\OneDrive\Downloads\CDT20_PRE_G06_RUNS'
$LocalAppData   = [Environment]::GetFolderPath('LocalApplicationData')
$PythonExe      = Join-Path $LocalAppData 'Python\pythoncore-3.14-64\python.exe'
$LabDrive       = 'D:\'
$PriorG0Glob    = 'CDT20_PRE_G06_PROJECTION_G0_*'
$RequireDesktop = $true

$ScriptExit = 2
$PartialEffect = $false
$Status = 'BLOCKED_BEFORE_EFFECTS'
$Reason = ''
$RunDir = $null
$RunLog = $null
$Stage = $null
$RunRoot = $null
$Collected = New-Object System.Collections.ArrayList
$Mutex = $null

function Write-Run([string]$Line) {
    Write-Host $Line
    if ($script:RunLog) { [IO.File]::AppendAllText($script:RunLog, $Line + "`r`n", (New-Object System.Text.UTF8Encoding($false))) }
}

function Get-Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant() }

function Test-NoReparse([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    while ($null -ne $item) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw ('REPARSE_POINT_IN_CHAIN: ' + $item.FullName) }
        if ($item -is [IO.DirectoryInfo]) { $item = $item.Parent } else { $item = $item.Directory }
    }
}

function Invoke-Native([string]$Exe, [string[]]$Arguments, [string]$Label) {
    # stderr lines arrive as ErrorRecord objects in PS 5.1; they are logged, never turned into a stop.
    Write-Run ('NATIVE_BEGIN=' + $Label)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                if ($_.TargetObject -is [string]) { Write-Run ([string]$_.TargetObject) } else { Write-Run ($_.Exception.Message) }
            } else { Write-Run ([string]$_) }
        }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    if ($null -eq $code) { throw ('NATIVE_EXIT_NULL: ' + $Label) }
    Write-Run ('NATIVE_END=' + $Label + ' EXIT_CODE=' + $code)
    return [int]$code
}

function Copy-Verified([string]$Source, [string]$Destination) {
    if ([IO.File]::Exists($Destination)) { throw ('COLLECT_DESTINATION_EXISTS: ' + $Destination) }
    [IO.File]::Copy($Source, $Destination, $false)
    $a = Get-Sha $Source; $b = Get-Sha $Destination
    if ($a -cne $b) { throw ('COLLECT_COPY_HASH: ' + $Destination) }
    [void]$script:Collected.Add([ordered]@{ path = [IO.Path]::GetFileName($Destination); source = $Source; sha256 = $b; bytes = (Get-Item -LiteralPath $Destination).Length })
    Write-Run ('COLLECTED=' + $Destination + ' SHA256=' + $b)
}

try {
    # ---------------- Pasta de log fixa e nova a cada execucao ----------------
    if (-not [IO.Directory]::Exists($DownloadsRoot)) { throw ('DOWNLOADS_ROOT_ABSENT: ' + $DownloadsRoot) }
    if (-not [IO.Directory]::Exists($RunsParent)) { [void][IO.Directory]::CreateDirectory($RunsParent) }
    $stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff')
    $RunDir = Join-Path $RunsParent ('INTEGRATED_' + $stamp + '_' + $PID)
    if ([IO.Directory]::Exists($RunDir)) { throw ('RUN_DIR_COLLISION: ' + $RunDir) }
    [void][IO.Directory]::CreateDirectory($RunDir)
    $RunLog = Join-Path $RunDir 'RUN_LOG.txt'
    Write-Run ('RESULT_CONTEXT=' + $Context)
    Write-Run ('RUN_LOG=' + $RunLog)
    Write-Run ('LAUNCHER=' + $PSCommandPath + ' SHA256=' + (Get-Sha $PSCommandPath))
    Write-Run 'ESCOPO=ENGENHARIA_ISOLADA_PRE_G06; PRODUCAO=NAO; B06=NOT_STARTED; B07=NOT_STARTED; D4_D5_PROD=NOT_STARTED; CANARIO=NAO; FULL=NOT_STARTED'

    # ---------------- Preflight sem efeitos de engenharia ----------------
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'REQUIRED_WINDOWS_POWERSHELL_5_1' }
    if ($RequireDesktop -and $PSVersionTable.PSEdition -ne 'Desktop') { throw 'REQUIRED_POWERSHELL_DESKTOP_EDITION' }
    if (-not [Environment]::Is64BitProcess) { throw 'REQUIRED_64_BIT_POWERSHELL' }
    $mutexCreated = $false
    $candidateMutex = [System.Threading.Mutex]::new($true, 'Local\CDT20_PRE_G06_INTEGRATED_LAUNCHER', [ref]$mutexCreated)
    if (-not $mutexCreated) { $candidateMutex.Dispose(); throw 'LAUNCHER_ALREADY_RUNNING' }
    $Mutex = $candidateMutex
    $transport = Join-Path $PSScriptRoot $TransportName
    if (-not [IO.File]::Exists($transport)) { throw ('TRANSPORT_ABSENT_NEXT_TO_LAUNCHER: ' + $transport) }
    $actual = Get-Sha $transport
    if ($actual -cne $TransportSha) { throw ('TRANSPORT_SHA256_MISMATCH: ' + $actual) }
    Write-Run ('TRANSPORT_SHA256_OK=' + $actual)
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($transport)
    try {
        $seen = @{}
        foreach ($entry in @($zip.Entries)) {
            $n = $entry.FullName
            if ([string]::IsNullOrEmpty($n) -or $n.StartsWith('/') -or $n.Contains('\') -or $n.Contains(':') -or $entry.Name.Length -eq 0) { throw ('UNSAFE_ZIP_MEMBER: ' + $n) }
            foreach ($part in $n.Split('/')) { if ($part -eq '' -or $part -eq '.' -or $part -eq '..') { throw ('UNSAFE_ZIP_COMPONENT: ' + $n) } }
            $low = $n.ToLowerInvariant()
            if ($seen.ContainsKey($low)) { throw ('ZIP_DUPLICATE_MEMBER: ' + $n) }
            $seen[$low] = $true
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw ('ZIP_SYMLINK_MEMBER: ' + $n) }
        }
        if (-not $seen.ContainsKey('transport_manifest.json')) { throw 'TRANSPORT_MANIFEST_ABSENT' }
    } finally { $zip.Dispose() }
    if (-not [IO.File]::Exists($PythonExe)) { throw ('PYTHON_314_X64_MISSING: ' + $PythonExe) }
    $version = & $PythonExe -I -B -c 'import sys,struct;print(sys.version_info[0],sys.version_info[1],struct.calcsize(chr(80))*8)'
    if ($LASTEXITCODE -ne 0 -or [string]$version -notmatch '^3 (1[4-9]|[2-9][0-9]) 64$') { throw ('PYTHON_INCOMPATIBLE: ' + $version) }
    Write-Run ('PYTHON=' + $PythonExe + ' VERSION=' + $version)
    if (-not [IO.Directory]::Exists($LabDrive)) { throw ('LAB_VOLUME_ABSENT: ' + $LabDrive) }
    if ($ResumeRoot) {
        if (-not [IO.Directory]::Exists($ResumeRoot)) { throw ('RESUME_ROOT_ABSENT: ' + $ResumeRoot) }
        Write-Run ('RESUME_ROOT=' + $ResumeRoot)
    }

    # ---------------- Coleta read-only do G0 de 20/10 (causa primaria) ----------------
    $priorDir = Join-Path $RunDir 'PRIOR_G0_20261020_READONLY'
    $priorStages = @(Get-ChildItem -LiteralPath $LocalAppData -Directory -Filter $PriorG0Glob -ErrorAction SilentlyContinue)
    Write-Run ('PRIOR_G0_STAGES_FOUND=' + $priorStages.Count)
    foreach ($ps in $priorStages) {
        $files = @(Get-ChildItem -LiteralPath $ps.FullName -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'G0_*' -and $_.Length -lt 16MB })
        foreach ($f in $files) {
            $dst = Join-Path $priorDir ($ps.Name + '__' + $f.Name)
            if (-not [IO.Directory]::Exists($priorDir)) { [void][IO.Directory]::CreateDirectory($priorDir) }
            Copy-Verified $f.FullName $dst
            if ($f.Name -like '*.log') {
                $text = [IO.File]::ReadAllText($dst)
                $idx = $text.IndexOf('======')
                if ($idx -ge 0) {
                    $excerpt = $text.Substring($idx, [Math]::Min(6000, $text.Length - $idx))
                    Write-Run ('PRIOR_G0_FAILURE_EXCERPT_BEGIN ' + $f.Name)
                    foreach ($l in ($excerpt -split "`r?`n")) { Write-Run $l }
                    Write-Run 'PRIOR_G0_FAILURE_EXCERPT_END'
                }
            }
        }
    }

    # ---------------- Staging hash-verificado (primeiro efeito run-owned) ----------------
    Test-NoReparse $LocalAppData
    $Stage = Join-Path $LocalAppData ('CDT20_PREG06_' + [guid]::NewGuid().ToString('N').Substring(0, 12))
    if ([IO.Directory]::Exists($Stage)) { throw 'STAGE_COLLISION' }
    [void][IO.Directory]::CreateDirectory($Stage)
    $PartialEffect = $true
    $Status = 'BLOCKED_AFTER_RUN_OWNED_EFFECTS'
    Write-Run ('STAGE=' + $Stage)
    [IO.Compression.ZipFile]::ExtractToDirectory($transport, $Stage)
    $manifest = [IO.File]::ReadAllText((Join-Path $Stage 'TRANSPORT_MANIFEST.json')) | ConvertFrom-Json
    $declared = @{}
    foreach ($r in @($manifest.files)) {
        $rel = [string]$r.path
        if ($declared.ContainsKey($rel.ToLowerInvariant())) { throw ('DUPLICATE_MANIFEST_MEMBER: ' + $rel) }
        $declared[$rel.ToLowerInvariant()] = $true
        $exact = Join-Path $Stage $rel
        if (-not [IO.File]::Exists($exact)) { throw ('PACKAGE_MEMBER_MISSING: ' + $rel) }
        if ([int64](Get-Item -LiteralPath $exact).Length -ne [int64]$r.bytes) { throw ('PACKAGE_MEMBER_BYTES: ' + $rel) }
        if ((Get-Sha $exact) -cne [string]$r.sha256) { throw ('PACKAGE_MEMBER_HASH: ' + $rel) }
    }
    $onDisk = @([IO.Directory]::EnumerateFiles($Stage, '*', [IO.SearchOption]::AllDirectories))
    if ($onDisk.Count -ne @($manifest.files).Count + 1) { throw ('TRANSPORT_EXACT_MEMBER_COUNT: ' + $onDisk.Count) }
    Test-NoReparse $Stage
    Write-Run ('TRANSPORT_MEMBERS_VERIFIED=' + @($manifest.files).Count)

    # ---------------- G0 nativo antes de qualquer campanha ----------------
    $g0 = Invoke-Native $PythonExe @('-I', '-B', (Join-Path $Stage 'G0_CDT20_PRE_G06.py')) 'G0'
    foreach ($name in @('G0_RESULT.json', 'G0_RETURN.zip')) {
        $p = Join-Path $Stage $name
        if ([IO.File]::Exists($p)) { Copy-Verified $p (Join-Path $RunDir $name) }
    }
    if ($g0 -ne 0) { throw ('NATIVE_G0_NONPASS: ' + $g0) }
    Write-Run 'NATIVE_G0=PASS; PRE_G06_CAMPAIGN_STARTING=YES; PRODUCTION=NO; B06=NOT_STARTED'

    # ---------------- Campanha PRE-G06 integrada ----------------
    $campaignArgs = @('-I', '-B', (Join-Path $Stage 'RUN_CDT20_R08Q1.py'))
    if ($ResumeRoot) { $campaignArgs += @('--resume-root', $ResumeRoot) }
    $campaign = Invoke-Native $PythonExe $campaignArgs 'PRE_G06_CAMPAIGN'
    $text = [IO.File]::ReadAllText($RunLog)
    $m = [regex]::Matches($text, '(?m)^RUN_ROOT=(.+?)\r?$')
    if ($m.Count -gt 0) { $RunRoot = $m[$m.Count - 1].Groups[1].Value }
    if ($RunRoot -and [IO.Directory]::Exists($RunRoot)) {
        foreach ($name in @('CDT20_PRE_G06_RETURN.zip', 'CDT20_PRE_G06_RETURN.sha256', 'ENGINEERING_RESULT.json', 'LIVE_STATUS.json')) {
            $p = Join-Path $RunRoot $name
            if ([IO.File]::Exists($p)) { Copy-Verified $p (Join-Path $RunDir $name) }
        }
        $finalStatus = Join-Path $RunRoot 'FINAL_G5\FINAL_ENGINEERING_STATUS.json'
        if ([IO.File]::Exists($finalStatus)) { Copy-Verified $finalStatus (Join-Path $RunDir 'FINAL_ENGINEERING_STATUS.json') }
    } else { Write-Run 'RUN_ROOT_NOT_REPORTED' }
    if ($campaign -eq 0) {
        # Exit 0 is not a PASS by itself: the sealed return and its final receipt must exist and agree.
        $statusCopy = Join-Path $RunDir 'FINAL_ENGINEERING_STATUS.json'
        $returnCopy = Join-Path $RunDir 'CDT20_PRE_G06_RETURN.zip'
        $returnSha = Join-Path $RunDir 'CDT20_PRE_G06_RETURN.sha256'
        if (-not ([IO.File]::Exists($statusCopy) -and [IO.File]::Exists($returnCopy) -and [IO.File]::Exists($returnSha))) { throw 'CAMPAIGN_EXIT_0_WITHOUT_FINAL_RECEIPT_OR_RETURN' }
        $declaredSha = ([IO.File]::ReadAllText($returnSha).Trim() -split '\s+')[0]
        if ($declaredSha -cne (Get-Sha $returnCopy)) { throw 'RETURN_SHA256_FILE_MISMATCH' }
        $final = [IO.File]::ReadAllText($statusCopy) | ConvertFrom-Json
        if ([string]$final.engineering_five_part_completeness -cne 'PASS' -or [string]$final.four_pre_b06_findings -cne 'PASS_NATIVE_REGRESSION' -or [string]$final.b06 -cne 'NOT_STARTED' -or $final.full_started -ne $false) {
            throw 'FINAL_RECEIPT_NOT_FIVE_PART_PASS'
        }
        Write-Run ('FINAL_RECEIPT=FIVE_PART_PASS FOUR_FINDINGS=PASS_NATIVE_REGRESSION RETURN_SHA256=' + $declaredSha)
        $ScriptExit = 0; $Status = 'PASS_NATIVE_INTEGRATED_PRE_G06_ENGINEERING_FIVE_PART'
    } elseif ($campaign -eq 130) {
        $ScriptExit = 130; $Status = 'SAFE_STOP'
    } else {
        throw ('PRE_G06_CAMPAIGN_NONPASS: ' + $campaign)
    }
} catch {
    $Reason = $_.Exception.Message
    Write-Run ('PRE_G06_INTEGRATED_BLOCKED=' + $Reason)
    if ($PartialEffect) { $ScriptExit = 3 } else { $ScriptExit = 2 }
} finally {
    if ($RunDir -and [IO.Directory]::Exists($RunDir)) {
        try {
            $summary = [ordered]@{
                schema = 'CDT20_PRE_G06_INTEGRATED_LAUNCHER_RESULT_V001'; status = $Status; exit_code = $ScriptExit
                reason = $Reason; partial_effect_scope = $(if ($PartialEffect) { 'RUN_OWNED_LAB_ONLY' } else { 'NONE' })
                stage = $Stage; run_root = $RunRoot; transport_sha256 = $TransportSha; collected = @($Collected)
                production_modified = $false; b06 = 'NOT_STARTED'; full = 'NOT_STARTED'
                physical_powerloss = 'NOT_TESTED_PHYSICAL_POWERLOSS'; result_return_to = $Context
            }
            $json = $summary | ConvertTo-Json -Depth 6
            [IO.File]::WriteAllText((Join-Path $RunDir 'LAUNCHER_RESULT.json'), $json, (New-Object System.Text.UTF8Encoding($false)))
            Write-Run ('ENGINEERING_STATUS=' + $Status)
            Write-Run ('EXIT_CODE=' + $ScriptExit)
            [IO.File]::AppendAllText($RunLog, ('RESULT_RETURN_TO=' + $Context + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
            $bundle = Join-Path $RunDir ('ENVIAR_AO_CHATGPT_CDT20_PRE_G06_' + [IO.Path]::GetFileName($RunDir) + '.zip')
            Add-Type -AssemblyName System.IO.Compression
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $fs = [IO.File]::Open($bundle, [IO.FileMode]::CreateNew)
            try {
                $archive = New-Object System.IO.Compression.ZipArchive($fs, [IO.Compression.ZipArchiveMode]::Create)
                try {
                    foreach ($f in @(Get-ChildItem -LiteralPath $RunDir -File -Recurse | Where-Object { $_.FullName -ne $bundle })) {
                        $rel = $f.FullName.Substring($RunDir.Length + 1).Replace('\', '/')
                        $level = [IO.Compression.CompressionLevel]::Optimal
                        if ($f.Extension -eq '.zip') { $level = [IO.Compression.CompressionLevel]::NoCompression }
                        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $f.FullName, $rel, $level)
                    }
                } finally { $archive.Dispose() }
            } finally { $fs.Dispose() }
            Write-Host ('ENVIE_O_RETORNO=' + $bundle)
            Write-Host ('ENVIE_O_RETORNO_SHA256=' + (Get-Sha $bundle))
        } catch { Write-Host ('RETURN_BUNDLE_SECONDARY_ERROR=' + $_.Exception.Message) }
    } else {
        Write-Host ('ENGINEERING_STATUS=' + $Status)
        Write-Host ('EXIT_CODE=' + $ScriptExit)
    }
    if ($null -ne $Mutex) { try { $Mutex.ReleaseMutex() } catch { }; $Mutex.Dispose() }
    Write-Host 'Devolva este resultado ao ChatGPT, no projeto Base de Dados CSV / Tickstore, conversa Compressão De Ticks 20. Anexe as evidências existentes e cole esta resposta.'
    Write-Host ('RESULT_RETURN_TO=' + $Context)
}
exit $ScriptExit
