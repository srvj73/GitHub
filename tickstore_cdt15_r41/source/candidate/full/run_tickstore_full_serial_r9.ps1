[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$DestRoot,
    [Parameter(Mandatory=$true)][string]$ScratchRoot,
    [Parameter(Mandatory=$true)][string]$LedgerZip,
    [Parameter(Mandatory=$true)][string]$FullGateFile,
    [Parameter(Mandatory=$true)][string]$FullGateSha256
)
$ErrorActionPreference = 'Stop'
# R9 RELEASE_RC1: capability still requires the external gate file and its independently
# supplied trusted SHA256. This launcher embeds neither and performs no automatic execution.
& py -3.14 (Join-Path $PSScriptRoot 'tickstore_serial_runner.py') `
    --mode FULL_SERIAL --source-root $SourceRoot --dest-root $DestRoot `
    --scratch-root $ScratchRoot --ledger-zip $LedgerZip `
    --full-gate-file $FullGateFile --full-gate-sha256 $FullGateSha256
exit $LASTEXITCODE
