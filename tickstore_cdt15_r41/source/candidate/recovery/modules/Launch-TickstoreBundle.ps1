#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$PackageRoot,[Parameter(Mandatory=$true)][string]$BundlePath,
      [Parameter(Mandatory=$true)][string]$AnchorPath,[Parameter(Mandatory=$true)][string]$PythonPath)
$ErrorActionPreference='Stop'
$Loader=[IO.Path]::Combine($PackageRoot,'loader','INLINE_ROOT_LOADER_V004_R1R1.ps1')
$Expected='74FE55D8FC43A5C1CEDE22887C60624DC454D3E52E26E1C3AA108072451F1597'
if((Get-FileHash -LiteralPath $Loader -Algorithm SHA256).Hash.ToUpperInvariant()-cne$Expected){throw 'ROOT_LOADER_HASH_MISMATCH'}
$raw=[IO.File]::ReadAllBytes($Loader)
$offset=0
if($raw.Length-ge3-and$raw[0]-eq0xEF-and$raw[1]-eq0xBB-and$raw[2]-eq0xBF){$offset=3}
$text=[Text.Encoding]::UTF8.GetString($raw,$offset,$raw.Length-$offset)
$sb=[ScriptBlock]::Create($text)
. $sb
$anchor=[IO.File]::ReadAllText($AnchorPath)
$code=Invoke-TickstoreInlineRootV004R1 -BundlePath $BundlePath -PythonPath $PythonPath -ExternalAnchorJson $anchor
exit [int]$code
