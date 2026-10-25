# PEGASUS FULL 2026 — Runner de qualificacao de IDENTIDADE DE ARQUIVO no Windows (V008R18R2).
# Windows PowerShell 5.1 Desktop. ASCII, sem BOM. SEGURO PRE-EFEITO: nao executa economia, nao instala,
# nao toca as tres arvores protegidas, nao le politica. Hash-bound ao ZIP selado.
# Uso a partir de PS C:\Users\silvi> (sem cd):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\RUN_WINDOWS_IDENTITY_QUALIFICATION_R18R2_PS51.ps1
# Log SEMPRE em pasta absoluta fixa, nova por execucao, independente da pasta atual:
#   C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\WINIDENT_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt
# Exit: 0 = todos os casos obrigatorios conforme esperado; 3 = violacao de contrato; 2 = bloqueio de setup.
[CmdletBinding()]
param(
    [string]$ZipPath = 'C:\Users\silvi\Downloads\PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R18R2_20261024.zip',
    [string]$Python  = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedZipSha = '09E4759308DBD68762F331820D23B9BEC6FC504BFA0BC2685DDEB588E4A62A2D'
$TreeName       = 'PEGASUS_FULL_2026_ENGINEERING_FINAL_V008'
$RunsBase       = 'C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS'
$Stamp          = (Get-Date).ToString('yyyyMMdd_HHmmss_fff')
$RunRoot        = Join-Path $RunsBase ('WINIDENT_' + $Stamp + '_' + $PID)
$LogPath        = Join-Path $RunRoot 'RUN_LOG.txt'
$Footer         = 'RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementacao Runner Paralelo 15'

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
function Write-Log([string]$m) {
    $line = ((Get-Date).ToString('s') + ' ' + $m)
    Add-Content -LiteralPath $LogPath -Value $line
    Write-Host $line
}
function Get-Sha([string]$p) { return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToUpperInvariant() }

$Code = 2
try {
    Write-Log ('PEGASUS_WINDOWS_IDENTITY_R18R2 run_root=' + $RunRoot)
    if (-not (Test-Path -LiteralPath $ZipPath)) { throw ('ZIP_NOT_FOUND ' + $ZipPath) }
    $zsha = Get-Sha $ZipPath
    Write-Log ('ZIP_SHA256=' + $zsha)
    if ($zsha -ne $ExpectedZipSha) { throw ('ZIP_SHA_MISMATCH expected=' + $ExpectedZipSha + ' got=' + $zsha) }
    Write-Log 'ZIP_SHA256=PASS'
    if (-not (Test-Path -LiteralPath $Python)) { throw ('PYTHON_NOT_FOUND ' + $Python) }

    $Tree = Join-Path $RunRoot $TreeName
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $RunRoot)
    if (-not (Test-Path -LiteralPath $Tree)) { throw ('TREE_NOT_EXTRACTED ' + $Tree) }
    Write-Log ('EXTRACTED ' + $Tree)

    $Qual = Join-Path $Tree 'supervisor\tests\windows_identity_qualifier_v008r18r2.py'
    if (-not (Test-Path -LiteralPath $Qual)) { throw ('QUALIFIER_NOT_FOUND ' + $Qual) }
    $OutDir = Join-Path $RunRoot 'RECEIPT'

    # Pre-efeito: so o qualificador de identidade (fixtures sinteticas). Nenhuma economia/instalacao.
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Write-Log ('QUALIFIER_START ' + $Qual)
    & $Python -I -B $Qual --out $OutDir 2>&1 | ForEach-Object { Write-Log ('PY ' + $_) }
    $Code = $LASTEXITCODE
    $Receipt = Join-Path $OutDir 'WINDOWS_IDENTITY_QUALIFICATION_R18R2_RESULT.json'
    if (Test-Path -LiteralPath $Receipt) {
        Write-Log ('RECEIPT ' + $Receipt + ' sha256=' + (Get-Sha $Receipt))
    } else {
        Write-Log 'RECEIPT_MISSING'; if ($Code -eq 0) { $Code = 3 }
    }
    Write-Log ('RESULT exit=' + $Code)
} catch {
    Write-Log ('FAIL ' + $_.Exception.Message)
    $Code = 2
}
Write-Log $Footer
exit $Code
