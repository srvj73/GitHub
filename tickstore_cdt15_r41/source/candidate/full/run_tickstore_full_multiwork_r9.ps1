[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$DestRoot,
    [Parameter(Mandatory=$true)][string]$ScratchRoot,
    [Parameter(Mandatory=$true)][string]$LedgerZip,
    [Parameter(Mandatory=$true)][string]$ChainFile,
    [Parameter(Mandatory=$true)][string]$ChainSha256,
    [Parameter(Mandatory=$true)][string]$B06Sha256,
    [string]$Workers = 'AUTO',
    [int]$MaxWorkers = 22,
    [int]$RamTargetPercent = 60,
    [string]$PythonPath = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Thread='Compress'+[char]0x00E3+'o De Ticks 15'
Write-Host ('RESULT_CONTEXT=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD='+$Thread)
$code = 2
try {
$stream=[IO.File]::OpenRead($PythonPath);$hash=[Security.Cryptography.SHA256]::Create()
try {$pythonSha=[BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','')}
finally {$hash.Dispose();$stream.Dispose()}
if ($pythonSha -cne '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9') { throw 'PYTHON_HASH_MISMATCH' }
if ([Diagnostics.FileVersionInfo]::GetVersionInfo($PythonPath).ProductVersion -notmatch '^3\.14\.7(?:\D|$)') { throw 'PYTHON_VERSION_MISMATCH' }
& $PythonPath -I -X utf8 -B (Join-Path $PSScriptRoot 'tickstore_full_multiwork.py') `
    --source-root $SourceRoot --dest-root $DestRoot --scratch-root $ScratchRoot `
    --ledger-zip $LedgerZip `
    --chain-file $ChainFile --chain-sha256 $ChainSha256 --b06-sha256 $B06Sha256 `
    --workers $Workers --max-workers $MaxWorkers --ram-target-percent $RamTargetPercent
$code = $LASTEXITCODE
if ($code -eq 0) { Write-Host 'TICKSTORE_MULTIWORK_LAUNCHER_RETURN=PASS' }
else { Write-Host ('TICKSTORE_MULTIWORK_LAUNCHER_RETURN=NONZERO EXIT_CODE=' + $code) }
} catch {
    Write-Host ('TICKSTORE_MULTIWORK_LAUNCHER_RETURN=BLOCKED REASON=' + $_.Exception.Message)
} finally {
    Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD='+$Thread)
}
exit [int]$code
