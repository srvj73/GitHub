#requires -Version 5.1
# TICKSTORE CDT21 - qualificacao nativa Windows do sucessor V004 (correcao F-01R1: legado ja inicializado antes da cerca).
# Somente laboratorio proprio: nenhuma raiz produtiva, nenhum G5/B06/B07/D4/D5/canario/FULL, nenhuma rede, nenhum credito.
# Executa: as 11 unidades do G0 do V003 + a suite nova F-01R1 (12 unidades, um Job por unidade), os controles negativos por
# mutacao (8 mutacoes, nativos) e o cenario de reproducao da origem sobre os fontes do V004 (e, se presente, do V003 como contraste).
# Execute a partir de PS C:\Users\silvi> em PowerShell 5.1 (autoeleva por UAC quando necessario):
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_F01R1_G0_V004_20261021.ps1"
# Pre-requisito: C:\Users\silvi\Downloads\CDT21_FINAL_PACKAGE_V004_20261021.zip
# Opcional (contraste): C:\Users\silvi\Downloads\CDT21_FINAL_PACKAGE_V003_20261020.zip
# Log sempre em pasta absoluta fixa, nova a cada execucao, independente da pasta atual:
#   C:\Users\silvi\Downloads\CDT21_F01R1_RUNS\G0_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt (pai) e RUN_LOG_ELEVATED.txt (filho)
# Efeitos: somente C:\Users\silvi\AppData\Local\CDT21_F01R1_G0\<raiz nova> e a pasta de log acima.
[CmdletBinding()]
param([switch]$ElevatedChild, [string]$SharedLogDir = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$Thread = 'Compress' + [char]0x00E3 + 'o De Ticks 21'
$Downloads = 'C:\Users\silvi\Downloads'
$RunsDir = 'C:\Users\silvi\Downloads\CDT21_F01R1_RUNS'
$PackageName = 'CDT21_FINAL_PACKAGE_V004_20261021.zip'
$ExpectedPackageSha = 'AD33486954F1248AF28A78677377E83AB979AB86EDD5F71F5B7D108CBA8F99DD'
$ContrastName = 'CDT21_FINAL_PACKAGE_V003_20261020.zip'
$ContrastSha = '69DA2D5964BABA95D8B90D5BC17E12683B5F5E91D1C7D7ABD01938A7AE014A50'
$Python = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$ExpectedPythonSha = '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
$Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
$Utf8 = New-Object Text.UTF8Encoding($false)
if (-not (Test-Path -LiteralPath $RunsDir -PathType Container)) { New-Item -ItemType Directory -Path $RunsDir -ErrorAction Stop | Out-Null }
if ($ElevatedChild) {
    $full = [IO.Path]::GetFullPath($SharedLogDir)
    if (-not $SharedLogDir -or -not $full.StartsWith($RunsDir + '\G0_', [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $full -PathType Container)) {
        throw ('SHARED_LOG_DIR_INVALID=' + $SharedLogDir)
    }
    $LogDir = $full
    $Log = Join-Path $LogDir 'RUN_LOG_ELEVATED.txt'
} else {
    $LogDir = Join-Path $RunsDir ('G0_' + $Stamp)
    New-Item -ItemType Directory -Path $LogDir -ErrorAction Stop | Out-Null
    $Log = Join-Path $LogDir 'RUN_LOG.txt'
}

function Log([string]$Line) {
    Write-Host $Line
    [IO.File]::AppendAllText($Log, $Line + "`r`n", $Utf8)
}
function Sha([string]$Path) {
    $s = [IO.File]::OpenRead($Path); $h = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($h.ComputeHash($s)).Replace('-', '') } finally { $h.Dispose(); $s.Dispose() }
}

$code = 2
try {
    Log ('RESULT_CONTEXT=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=' + $Thread)
    Log ('RUN_LOG=' + $Log)
    Log ('LAUNCHER=' + $PSCommandPath + ' SHA256=' + (Sha $PSCommandPath))
    Log 'ESCOPO=G0_DELTA_F01R1_V004; LABORATORIO_PROPRIO; PRODUCAO=NAO; G5_38=NAO_EXECUTADO; B06=NOT_STARTED; B07=NOT_STARTED; D4_D5=NOT_STARTED; CANARIO=NAO; FULL=NAO'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'WINDOWS_POWERSHELL_5_1_REQUIRED' }
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        if ($ElevatedChild) { throw 'ELEVATION_REENTRY_GUARD: rights missing after RunAs' }
        $si = New-Object System.Diagnostics.ProcessStartInfo
        $si.FileName = Join-Path $PSHOME 'powershell.exe'
        $si.WorkingDirectory = 'C:\Users\silvi'
        $si.UseShellExecute = $true
        $si.Verb = 'runas'
        $si.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -ElevatedChild -SharedLogDir "' + $LogDir + '"'
        Log ('UAC_REQUEST=YES LOG_COMPARTILHADO=' + $LogDir)
        $child = [System.Diagnostics.Process]::Start($si)
        if ($null -eq $child) { throw 'UAC_NO_CHILD_PROCESS' }
        try {
            Log ('ELEVATED_CHILD_PID=' + $child.Id + ' (log do filho: ' + (Join-Path $LogDir 'RUN_LOG_ELEVATED.txt') + ')')
            $deadline = [DateTime]::UtcNow.AddHours(3); $n = 0
            while (-not $child.WaitForExit(5000)) {
                $n++; if ($n % 6 -eq 0) { Log ('ELEVATED_CHILD_ACTIVE=YES PID=' + $child.Id) }
                if ([DateTime]::UtcNow -ge $deadline) { throw 'ELEVATED_CHILD_WAIT_TIMEOUT: sem encerramento automatico; inspecione o filho e os logs' }
            }
            $child.WaitForExit(); $child.Refresh()
            $code = [int]$child.ExitCode
            Log ('ELEVATED_CHILD_EXIT_CODE=' + $code)
        } finally { $child.Dispose() }
    } else {
        if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA_MISSING' }
        if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw ('PYTHON_MISSING=' + $Python) }
        if ((Sha $Python) -cne $ExpectedPythonSha) { throw 'PYTHON_SHA_MISMATCH' }
        $Package = Join-Path $Downloads $PackageName
        if (-not (Test-Path -LiteralPath $Package -PathType Leaf)) { throw ('PACKAGE_NOT_FOUND=' + $Package) }
        $packageSha = Sha $Package
        if ($packageSha -cne $ExpectedPackageSha) { throw ('PACKAGE_SHA_MISMATCH=' + $packageSha) }
        Log ('PACKAGE=' + $Package + ' SHA256_OK=' + $packageSha)
        $contrastArgs = @()
        $Contrast = Join-Path $Downloads $ContrastName
        if (Test-Path -LiteralPath $Contrast -PathType Leaf) {
            $cSha = Sha $Contrast
            if ($cSha -ceq $ContrastSha) { $contrastArgs = @('--contrast-package', $Contrast); Log ('CONTRASTE_V003=' + $Contrast + ' SHA256_OK') }
            else { Log ('CONTRASTE_V003=IGNORADO_SHA_DIVERGENTE ' + $cSha) }
        } else { Log 'CONTRASTE_V003=NAO_EXECUTADO (pacote V003 ausente em Downloads; opcional)' }

        $hex = [Guid]::NewGuid().ToString('N').Substring(0, 12)
        $RunRoot = Join-Path $env:LOCALAPPDATA ('CDT21_F01R1_G0\R08_Q1_' + (Get-Date).ToString('yyyyMMddHHmmss') + '_' + $hex)
        if (Test-Path -LiteralPath $RunRoot) { throw 'RUN_ROOT_EXISTS' }
        New-Item -ItemType Directory -Path (Join-Path $RunRoot 'TEMP') -ErrorAction Stop | Out-Null
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($Package, (Join-Path $RunRoot 'PACKAGED'))
        Log ('RUN_ROOT=' + $RunRoot)
        $Driver = Join-Path $RunRoot 'PACKAGED\implementation_v001\qual\CDT21_F01R1_G0_QUALIFICATION.py'
        Log 'ETA=cerca de 10 a 20 min (12 unidades + 8 mutacoes nativas + cenario da origem). Heartbeats a cada 5 s abaixo.'

        $oldTemp = $env:TEMP; $oldTmp = $env:TMP
        $env:TEMP = Join-Path $RunRoot 'TEMP'; $env:TMP = $env:TEMP
        $oldPref = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $driverArgs = @('-I', '-B', $Driver, '--run-root', $RunRoot, '--package', $Package) + $contrastArgs
            & $Python @driverArgs 2>&1 | ForEach-Object { Log ([string]$_) }
            $code = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $oldPref
            $env:TEMP = $oldTemp; $env:TMP = $oldTmp
        }
        foreach ($name in @('G0_RESULT.json', 'CDT21_F01R1_G0_RETURN.zip')) {
            $src = Join-Path $RunRoot $name
            if (Test-Path -LiteralPath $src -PathType Leaf) {
                Copy-Item -LiteralPath $src -Destination (Join-Path $LogDir $name)
                Log ('COLLECTED=' + (Join-Path $LogDir $name) + ' SHA256=' + (Sha (Join-Path $LogDir $name)))
            } else { Log ('NOT_PRODUCED=' + $name); $code = 2 }
        }
        if ($code -eq 0) { Log 'G0_V004=PASS_CDT21_F01R1_V004_G0_NATIVE; B06=NOT_STARTED' } else { Log 'G0_V004=NAO_PASSOU (ver G0_RESULT.json); B06=NOT_STARTED' }
    }
} catch {
    Log ('G0_V004_BLOCKED=' + $_.Exception.Message)
    $code = 2
} finally {
    Log ('EXIT_CODE=' + $code)
    if ($ElevatedChild) {
        Log 'FILHO_ELEVADO_CONCLUIDO (o processo pai empacota o retorno unico)'
    } else {
        $Send = Join-Path $LogDir ('ENVIAR_AO_OPUS_CDT21_F01R1_G0_V004_' + $Stamp + '.zip')
        try {
            Add-Type -AssemblyName System.IO.Compression
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $zip = [IO.Compression.ZipFile]::Open($Send, [IO.Compression.ZipArchiveMode]::Create)
            try {
                foreach ($name in @('RUN_LOG.txt', 'RUN_LOG_ELEVATED.txt', 'G0_RESULT.json', 'CDT21_F01R1_G0_RETURN.zip')) {
                    $p = Join-Path $LogDir $name
                    if (Test-Path -LiteralPath $p -PathType Leaf) {
                        $level = [IO.Compression.CompressionLevel]::Optimal
                        if ($name.EndsWith('.zip')) { $level = [IO.Compression.CompressionLevel]::NoCompression }
                        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $p, $name, $level)
                    }
                }
            } finally { $zip.Dispose() }
            Log ('ENVIE_O_RETORNO=' + $Send)
            Log ('ENVIE_O_RETORNO_SHA256=' + (Sha $Send))
        } catch {
            Log ('ENVIAR_ZIP_FALHOU=' + $_.Exception.Message + ' (envie o conteudo de ' + $LogDir + ')')
        }
        Log ('Devolva este resultado ao Opus/ChatGPT, projeto Base de Dados CSV / Tickstore, conversa ' + $Thread + '. Anexe as evidencias e cole esta resposta.')
        Log ('RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=' + $Thread)
    }
}
exit $code
