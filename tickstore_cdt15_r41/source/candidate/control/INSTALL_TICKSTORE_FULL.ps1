[CmdletBinding()]
param(
    [string]$WitnessPath='',
    [string]$Downloads='C:\Users\silvi\OneDrive\Downloads',
    [string]$InstallRoot=(Join-Path $env:LOCALAPPDATA 'TICKSTORE\Candidates'),
    [switch]$ActivateMenu
)
Set-StrictMode -Version 2
$ErrorActionPreference='Stop'
$held=New-Object System.Collections.Generic.List[System.IDisposable]
function Require([bool]$Condition,[string]$Reason) { if (-not $Condition) { throw $Reason } }
function NoReparse([string]$Path) {
    $p=[IO.Path]::GetFullPath($Path)
    while ($p) {
        if ([IO.File]::Exists($p) -or [IO.Directory]::Exists($p)) {
            Require (([IO.File]::GetAttributes($p) -band [IO.FileAttributes]::ReparsePoint) -eq 0) ('INSTALL_REPARSE:'+ $p)
        }
        $parent=[IO.Directory]::GetParent($p)
        if ($null -eq $parent) { break }; $p=$parent.FullName
    }
}
function OpenRead([string]$Path) {
    NoReparse $Path
    $s=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $held.Add($s); return $s
}
function StreamSha([IO.Stream]$Stream) {
    $h=[Security.Cryptography.SHA256]::Create()
    try { $Stream.Position=0; $r=[BitConverter]::ToString($h.ComputeHash($Stream)).Replace('-',''); $Stream.Position=0; return $r }
    finally { $h.Dispose() }
}
function RawSha([byte[]]$Raw) {
    $hash=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($Raw)).Replace('-','') }
    finally { $hash.Dispose() }
}
function ParseStream([IO.Stream]$Stream) {
    $r=New-Object IO.StreamReader($Stream,[Text.Encoding]::UTF8,$true,4096,$true)
    try { $Stream.Position=0; return ($r.ReadToEnd() | ConvertFrom-Json) } finally { $r.Dispose(); $Stream.Position=0 }
}
function SafeMember([string]$Name) {
    Require ($Name -ne '' -and $Name -notmatch '[:\\]' -and -not $Name.StartsWith('/')) 'INSTALL_MEMBER_PATH'
    foreach ($part in $Name.Split('/')) {
        Require ($part -ne '' -and $part -ne '.' -and $part -ne '..' -and $part -notmatch '[ .]$|[\x00-\x1f]' -and
                 $part -notmatch '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') 'INSTALL_MEMBER_SEGMENT'
    }
}
function WriteNew([string]$Path,[byte[]]$Raw) {
    NoReparse ([IO.Path]::GetDirectoryName($Path))
    $f=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $f.Write($Raw,0,$Raw.Length); $f.Flush($true) } finally { $f.Dispose() }
}
try {
    Require ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'POWERSHELL_51_REQUIRED'
    # G4 source-only gate: two-phase MENU writer not yet integrated or target-qualified.
    # Fail BEFORE reading external witnesses, creating Candidates or modifying ACTIVE.
    Require (-not $ActivateMenu) 'G4_MENU_ACTIVATION_REQUIRES_INTEGRATED_COMMIT_WRITER'
    if ($WitnessPath -eq '') {
        $found=@(Get-ChildItem -LiteralPath $Downloads -Filter 'WITNESS_TICKSTORE_FULL_FINAL_*.json' -File)
        Require ($found.Count -eq 1) 'FINAL_WITNESS_CARDINALITY'; $WitnessPath=$found[0].FullName
    }
    $witnessStream=OpenRead $WitnessPath; $w=ParseStream $witnessStream
    Require ($w.schema -ceq 'TICKSTORE_FINAL_PACKAGE_WITNESS_V001') 'FINAL_WITNESS_SCHEMA'
    Require ($w.package_sha256 -cmatch '^[0-9A-F]{64}$' -and $w.manifest_sha256 -cmatch '^[0-9A-F]{64}$') 'FINAL_WITNESS_HASH'
    SafeMember $w.package_name; Require ($w.package_name -notmatch '/' -and $w.package_name.EndsWith('.zip')) 'PACKAGE_NAME'
    $package=Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($WitnessPath))) $w.package_name
    $zipStream=OpenRead $package
    Require ((StreamSha $zipStream) -ceq $w.package_sha256) 'PACKAGE_SHA256'
    Add-Type -AssemblyName System.IO.Compression
    $archive=New-Object IO.Compression.ZipArchive($zipStream,[IO.Compression.ZipArchiveMode]::Read,$true)
    $held.Add($archive)
    $names=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $archive.Entries) {
        SafeMember $entry.FullName
        Require ($names.Add($entry.FullName)) 'PACKAGE_DUPLICATE_MEMBER'
        Require (($entry.ExternalAttributes -band 0x400) -eq 0) 'PACKAGE_REPARSE_MEMBER'
        Require ((($entry.ExternalAttributes -shr 16) -band 0xF000) -ne 0xA000) 'PACKAGE_SYMLINK_MEMBER'
    }
    $manifestEntry=$archive.GetEntry('PACKAGE_MANIFEST.json'); Require ($null -ne $manifestEntry) 'PACKAGE_MANIFEST_MISSING'
    $entryInput=$manifestEntry.Open(); $mem=New-Object IO.MemoryStream
    try { $entryInput.CopyTo($mem) } finally { $entryInput.Dispose() }
    try {
        Require ((StreamSha $mem) -ceq $w.manifest_sha256) 'PACKAGE_MANIFEST_SHA256'
        $manifest=ParseStream $mem
        $manifestRaw=$mem.ToArray()
    } finally { $mem.Dispose() }
    Require ($manifest.schema -ceq 'TICKSTORE_FINAL_PACKAGE_MANIFEST_V001') 'PACKAGE_MANIFEST_SCHEMA'
    Require (@($manifest.files).Count -eq $archive.Entries.Count-1) 'PACKAGE_MANIFEST_CARDINALITY'
    $listed=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $manifest.files) {
        SafeMember $file.path
        Require ($file.path -cne 'PACKAGE_MANIFEST.json' -and $listed.Add($file.path) -and $names.Contains($file.path)) 'PACKAGE_MANIFEST_SET'
        Require ($file.sha256 -cmatch '^[0-9A-F]{64}$' -and $file.bytes -ge 0) 'PACKAGE_MANIFEST_RECORD'
    }
    $python='C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
    $pythonStream=OpenRead $python
    Require ((StreamSha $pythonStream) -ceq '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9') 'INSTALL_PYTHON_IDENTITY'
    & $python -I -S -B -c 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); bad=z.testzip(); z.close(); sys.exit(2 if bad else 0)' $package
    Require ($LASTEXITCODE -eq 0) 'PACKAGE_CRC'
    # Required member must be present in the FINAL manifest before ANY install write.
    $menuRelative='implementation_v001/candidate/menu/MENU.py'
    $menuMatches=@($manifest.files | Where-Object { $_.path -ceq $menuRelative })
    Require ($menuMatches.Count -eq 1) 'INSTALL_INTENT_MENU_MANIFEST_CARDINALITY'
    NoReparse $InstallRoot
    [IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($InstallRoot)) | Out-Null
    $target=Join-Path ([IO.Path]::GetFullPath($InstallRoot)) $w.package_sha256
    Require (-not ([IO.File]::Exists($target) -or [IO.Directory]::Exists($target))) 'INSTALLATION_ALREADY_EXISTS_VERIFY_EXISTING'
    [IO.Directory]::CreateDirectory($target) | Out-Null
    WriteNew (Join-Path $target 'PACKAGE_MANIFEST.json') $manifestRaw
    foreach ($file in $manifest.files) {
        $path=Join-Path $target $file.path
        Require ($path.StartsWith($target+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) 'INSTALL_PATH_ESCAPE'
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path)) | Out-Null; NoReparse ([IO.Path]::GetDirectoryName($path))
        $entryInput=$archive.GetEntry($file.path).Open()
        $output=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $entryInput.CopyTo($output); $output.Flush($true) } finally { $entryInput.Dispose(); $output.Dispose() }
        $check=OpenRead $path
        Require ($check.Length -eq $file.bytes -and (StreamSha $check) -ceq $file.sha256) ('INSTALL_READBACK:'+ $file.path)
    }
    $launcher=Join-Path $target 'implementation_v001\candidate\control\RUN_TICKSTORE_FULL.ps1'
    Require ([IO.File]::Exists($launcher)) 'INSTALLED_LAUNCHER_MISSING'
    $launcherSha=StreamSha (OpenRead $launcher)
    $deployment=[ordered]@{schema='TICKSTORE_DEPLOYMENT_V001';installation_root=$target;package_sha256=$w.package_sha256;
       package_manifest_sha256=$w.manifest_sha256;witness_sha256=(StreamSha $witnessStream);launcher_sha256=$launcherSha;
       status='INSTALLED_NOT_PRODUCTION_ADMISSION';production_started=$false}
    $raw=[Text.Encoding]::UTF8.GetBytes(($deployment | ConvertTo-Json -Depth 10)+[Environment]::NewLine)
    WriteNew (Join-Path $target 'DEPLOYMENT.json') $raw
    # G4 SOURCE_ONLY bridge: emit a hash-bound inert intent INSIDE the installed
    # inactive instance. This is NOT an activation credential or transaction writer.
    $installedMenu=Join-Path $target ($menuRelative.Replace('/',[IO.Path]::DirectorySeparatorChar))
    Require ([IO.File]::Exists($installedMenu)) 'INSTALL_INTENT_MENU_MISSING'
    $installedMenuSha=StreamSha (OpenRead $installedMenu)
    Require ($installedMenuSha -ceq $menuMatches[0].sha256) 'INSTALL_INTENT_MENU_MISMATCH'
    $intent=[ordered]@{
       schema='TICKSTORE_MENU_INSTALL_INTENT_V001'
       installation_root=$target
       package_sha256=$w.package_sha256
       package_manifest_sha256=$w.manifest_sha256
       witness_sha256=(StreamSha $witnessStream)
       candidate_menu_relative_path=$menuRelative
       candidate_menu_sha256=$installedMenuSha
       active_deployment_sha256=(RawSha $raw)
       launcher_sha256=$launcherSha
       transaction_state='NOT_STARTED'
       effectful_authorized=$false
       production_started=$false
    }
    $intentRaw=[Text.Encoding]::UTF8.GetBytes(($intent | ConvertTo-Json -Depth 10)+[Environment]::NewLine)
    $intentPath=Join-Path $target 'MENU_INSTALL_INTENT.json'
    WriteNew $intentPath $intentRaw
    Require ((StreamSha (OpenRead $intentPath)) -ceq (RawSha $intentRaw)) 'INSTALL_INTENT_READBACK'
    Write-Output 'MENU_INSTALL_INTENT=PASS_SOURCE_ONLY_NOT_AUTHORIZED'
    # Legacy one-file MENU activation is permanently disabled in this source-only
    # candidate. The independent COMMITTED writer must be integrated, qualified,
    # and explicitly admitted before any official ACTIVE/MENU publication.
    Write-Output 'MENU_ACTIVATION=NOT_SUPPORTED_TRANSACTIONAL_WRITER_PENDING'
    Write-Output ('INSTALLATION_ROOT='+$target)
    Write-Output ('LAUNCHER='+$launcher)
    Write-Output 'INSTALLATION=PASS_READBACK; FULL_STARTED=NO'
    exit 0
} catch {
    Write-Output ('INSTALLATION_BLOCKED='+$_.Exception.Message)
    Write-Output 'PARTIAL_INSTALLATION_PRESERVED=YES; FULL_STARTED=NO'
    exit 2
} finally {
    for ($n=$held.Count-1; $n -ge 0; $n--) { $held[$n].Dispose() }
}
