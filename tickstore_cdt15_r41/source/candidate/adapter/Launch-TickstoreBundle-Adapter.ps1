#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [Parameter(Mandatory=$true)][string]$BundlePath,
    [Parameter(Mandatory=$true)][string]$AnchorPath,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$AdapterEntryPath
)
$ErrorActionPreference='Stop'
$Thread='Compress'+[char]0x00E3+'o De Ticks 14'
Write-Host ('RESULT_CONTEXT=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD='+$Thread)
$code=2
try {
$Loader=[IO.Path]::Combine((Split-Path -Parent $PSCommandPath),'INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1')
$ExpectedLoader='10104BE1731E1FA27C51E9730C9F9334D1782C3673EFABDC225A6B7166B59855'
$ExpectedAdapterEntry='9DEE7D6CFD075E042CA09B51B6FB05944488CE416690F4371764F732E6EDD9ED'
function Get-PinnedSourceSha([string]$Path) {
    $stream=[IO.File]::OpenRead($Path);$hash=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','') }
    finally { $hash.Dispose();$stream.Dispose() }
}
if((Get-PinnedSourceSha $AdapterEntryPath)-cne$ExpectedAdapterEntry){throw 'ADAPTER_INLINE_ENTRY_HASH_MISMATCH'}
# B06R2: hash the same buffer that is executed (no hash->re-read window).
$raw=[IO.File]::ReadAllBytes($Loader)
$loaderHash=[Security.Cryptography.SHA256]::Create()
try { $loaderSha=[BitConverter]::ToString($loaderHash.ComputeHash($raw)).Replace('-','') } finally { $loaderHash.Dispose() }
if($loaderSha-cne$ExpectedLoader){throw 'ADAPTER_ROOT_LOADER_HASH_MISMATCH'}
$offset=0
if($raw.Length-ge3-and$raw[0]-eq0xEF-and$raw[1]-eq0xBB-and$raw[2]-eq0xBF){$offset=3}
$text=[Text.Encoding]::UTF8.GetString($raw,$offset,$raw.Length-$offset)
$sb=[ScriptBlock]::Create($text)
. $sb
$anchor=[IO.File]::ReadAllText($AnchorPath)
$code=Invoke-TickstoreInlineRootV004R1Adapter -BundlePath $BundlePath -PythonPath $PythonPath -ExternalAnchorJson $anchor -AdapterEntryPath $AdapterEntryPath -ExpectedAdapterEntrySha $ExpectedAdapterEntry
} catch {
    Write-Host ('TICKSTORE_ADAPTER_LAUNCH=BLOCKED REASON='+$_.Exception.Message)
} finally {
    Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD='+$Thread)
}
exit [int]$code
