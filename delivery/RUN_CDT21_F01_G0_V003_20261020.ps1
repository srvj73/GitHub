#requires -Version 5.1
# TICKSTORE CDT21 - G0 nativo do delta F-01/F-04 sobre o candidato V003 (somente laboratorio proprio).
# Execute a partir de PS C:\Users\silvi> em PowerShell 5.1 ELEVADO:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_CDT21_F01_G0_V003_20261020.ps1"
# Log sempre em pasta absoluta fixa, nova a cada execucao, independente da pasta atual:
#   C:\Users\silvi\OneDrive\Downloads\CDT21_F01_RUNS\G0_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt
# Escopo: nenhuma raiz produtiva, nenhum B06/B07/D4/D5/canario/FULL, nenhuma rede, nenhum credito.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$Thread = 'Compress' + [char]0x00E3 + 'o De Ticks 21'
$Downloads = 'C:\Users\silvi\OneDrive\Downloads'
$PackageName = 'CDT21_FINAL_PACKAGE_V003_20261020.zip'
$ExpectedPackageSha = '69DA2D5964BABA95D8B90D5BC17E12683B5F5E91D1C7D7ABD01938A7AE014A50'
$Python = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$ExpectedPythonSha = '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
$Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
$LogDir = Join-Path $Downloads ('CDT21_F01_RUNS\G0_' + $Stamp)
New-Item -ItemType Directory -Path $LogDir -ErrorAction Stop | Out-Null
$Log = Join-Path $LogDir 'RUN_LOG.txt'
$Utf8 = New-Object Text.UTF8Encoding($false)

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
    Log 'ESCOPO=G0_DELTA_F01_F04_V003; LABORATORIO_PROPRIO; PRODUCAO=NAO; B06=NOT_STARTED; B07=NOT_STARTED; D4_D5=NOT_STARTED; CANARIO=NAO; FULL=NAO'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'WINDOWS_POWERSHELL_5_1_REQUIRED' }
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'ELEVATION_REQUIRED (abra o PowerShell como Administrador e execute novamente)'
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw ('PYTHON_MISSING=' + $Python) }
    if ((Sha $Python) -cne $ExpectedPythonSha) { throw 'PYTHON_SHA_MISMATCH' }
    $Package = Join-Path $Downloads $PackageName
    if (-not (Test-Path -LiteralPath $Package -PathType Leaf)) { throw ('PACKAGE_NOT_FOUND=' + $Package) }
    $packageSha = Sha $Package
    if ($packageSha -cne $ExpectedPackageSha) { throw ('PACKAGE_SHA_MISMATCH=' + $packageSha) }
    Log ('PACKAGE=' + $Package + ' SHA256_OK=' + $packageSha)

    $hex = [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $RunRoot = Join-Path $env:LOCALAPPDATA ('CDT21_F01_G0\R08_Q1_' + (Get-Date).ToString('yyyyMMddHHmmss') + '_' + $hex)
    if (Test-Path -LiteralPath $RunRoot) { throw 'RUN_ROOT_EXISTS' }
    New-Item -ItemType Directory -Path (Join-Path $RunRoot 'TEMP') -ErrorAction Stop | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($Package, (Join-Path $RunRoot 'PACKAGED'))
    Log ('RUN_ROOT=' + $RunRoot)
    $Driver = Join-Path $RunRoot 'PACKAGED\implementation_v001\qual\CDT21_F01_G0_QUALIFICATION.py'
    Log 'ETA=UNKNOWN (11 unidades; referencia V002: poucos minutos). Heartbeats a cada 5 s abaixo.'

    $oldTemp = $env:TEMP; $oldTmp = $env:TMP
    $env:TEMP = Join-Path $RunRoot 'TEMP'; $env:TMP = $env:TEMP
    $oldPref = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Python -I -B $Driver --run-root $RunRoot --package $Package 2>&1 | ForEach-Object { Log ([string]$_) }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPref
        $env:TEMP = $oldTemp; $env:TMP = $oldTmp
    }
    foreach ($name in @('G0_RESULT.json', 'CDT21_F01_G0_RETURN.zip')) {
        $src = Join-Path $RunRoot $name
        if (Test-Path -LiteralPath $src -PathType Leaf) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $LogDir $name)
            Log ('COLLECTED=' + (Join-Path $LogDir $name) + ' SHA256=' + (Sha (Join-Path $LogDir $name)))
        } else { Log ('NOT_PRODUCED=' + $name); $code = 2 }
    }
} catch {
    Log ('G0_BLOCKED=' + $_.Exception.Message)
    $code = 2
} finally {
    Log ('EXIT_CODE=' + $code)
    Log ('ENVIE_O_RETORNO=' + $LogDir + ' (RUN_LOG.txt, G0_RESULT.json, CDT21_F01_G0_RETURN.zip)')
    Log ('Devolva este resultado ao ChatGPT, no projeto Base de Dados CSV / Tickstore, conversa ' + $Thread + '. Anexe as evidencias existentes e cole esta resposta.')
    Log ('RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=' + $Thread)
}
exit $code
