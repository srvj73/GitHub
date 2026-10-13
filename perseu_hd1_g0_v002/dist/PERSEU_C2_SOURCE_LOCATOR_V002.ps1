#requires -Version 5.1
<#
PERSEU_C2_SOURCE_LOCATOR_V002.ps1 -- SOURCE_ONLY read-only locator; Windows target G0 pending.
V002 = V001 (Windows G0 PASS 12/10) + HD2 cold-archive modes HD2Index / HD2Deep (HD2 bound by serial).
Project: Perseu MT5 (Astra) | Thread: PERSEU_C2_DISK_SPACE_RECONCILIATION | Front: C2 sources

Read-only. Looks ONLY at exact paths and at first-level names of the two Downloads roots
derived from the recovered originals (delta V001). Never recurses D:\Base CSV, F:, HD1/HD2.
D:\PerseuRuns run folders: existence and first-level entry count only (no hash, no recursion).
Cloud placeholders (Offline/RecallOnOpen/RecallOnDataAccess) are never hashed (no implicit download).
Evidence goes ONLY to the fixed absolute run root, independent of the current directory:
  C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002_RUNS\<MODE>_<RUN_ID>\

Launch from PS C:\Users\silvi> (no cd), Windows PowerShell 5.1 Desktop:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002.ps1" -Mode SelfTest
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002.ps1" -Mode HD2Index
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002.ps1" -Mode HD2Deep
HD2 modes read only <HD2>:\ARQUIVO_FRIO\CHATGPT_DLS_20261007_093221 on the disk with serial WD-WCAYUS916314;
HD2Deep hashes files <= 64 MiB (budget 4 GiB) and copies identified files to the run dir (SHA verified).
Exit codes: 0=PASS (SelfTest assertions / Locate inventory completed)  2=BLOCKED_NO_PROTECTED_EFFECTS
C2_SOURCE_GATE is reported separately and is NOT implied by exit 0.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('SelfTest', 'Locate', 'HD2Index', 'HD2Deep')]
    [string]$Mode
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$ProjectName = 'Perseu MT5 (Astra)'
$ThreadName = 'PERSEU_C2_DISK_SPACE_RECONCILIATION'
$Revision = 'PERSEU_C2_SOURCE_LOCATOR_V002'
$PolicyMasterSha256 = '5B135DA0CA7C3BFE992F364720605522FB939977772C6D5A6FD3811A8288B302'
$ResultContext = 'RESULT_CONTEXT=ChatGPT | PROJECT=' + $ProjectName + ' | THREAD=' + $ThreadName
$ResultFooter = 'RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ProjectName + ' | THREAD=' + $ThreadName
$OneDriveDownloads = 'C:\Users\silvi\OneDrive\Downloads'
$LegacyDownloads = 'C:\Users\silvi\Downloads'
$EvidenceRoot = 'C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002_RUNS'
$InstallRootName = 'PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921_CONFIRMATORY'
$PerseuRuns = 'D:\PerseuRuns'
$HashCapBytes = [int64]67108864
$HashBudgetBytes = [int64]2147483648
$InventoryMaxFiles = 5000
$InventoryMaxDirs = 2000
$PlaceholderMask = [int64](0x1000 -bor 0x40000 -bor 0x400000)
$Hd2Serial = 'WD-WCAYUS916314'
$Hd2Model = 'WDC WD5000AAKX-003CA0'
$Hd1Serial = '6VMCLT3M'
$Hd2ArchiveRel = 'ARQUIVO_FRIO\CHATGPT_DLS_20261007_093221'
$DeepEntryLimit = 60000
$DeepHashBudget = [int64]4294967296
$RecoverCapBytes = [int64]536870912
$IndexScanCapBytes = [int64]67108864
$TargetNamePatterns = @('PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9*', '*R4R9*', '*PREREG*V004*', '*H1_H3*V004*', '*TELEMETRY_V004*', 'D1_HOMOLOGATION_CERT_*', 'perseu_parallel_auto*.py', 'perseu_r4r9_*.py', 'test_r4r9_gate.py', 'PERSEU_H1_H3_*')
$TargetNameTokens = @('PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921', 'PERSEU_H1_H3_CONFIRMATORY_PREREG_V004', 'PREREG_V004', 'TELEMETRY_V004', 'perseu_r4r9_accel', 'D1_HOMOLOGATION_CERT', 'RESUME_HOTFIX')
$RequiredC2Labels = @('R4R9_ORIGINAL_ZIP', 'R4R9_RUNNER_perseu_parallel_auto', 'R4R9_ACCEL_perseu_r4r9_accel', 'R4R9_test_parallel_auto_PRISTINE', 'R4R9_test_r4r9_gate', 'R4R9_C2_WRAPPER', 'D1_PHYSICAL_IDENTITY_INFORMED_BY_ORIGIN')

$Invariant = [System.Globalization.CultureInfo]::InvariantCulture
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# SHA-256 -> label. Sources: EVIDENCE_ORIGINAL terminal audit (22/09), constants in RECOVERED_ORIGINALS,
# delta manifest, parent handoff, and DERIVED_STATIC values (hotfix R3, telemetry V4 REENVIO shim).
$KnownSha = @{
    '70D6E13125EDCA3FC0AC5049ADBE0FD605AA5111598030EBFDE8A35030C0F69F' = 'R4R9_ORIGINAL_ZIP'
    '799B4914E7BA2C856CF3BBFA9004504E6CA4C35DBDAE342E145DC14C2D281A3F' = 'R4R8_PREDECESSOR_ZIP_NOT_R4R9'
    '8BF75A546F83EBAD4EEC040023B09F4166EEEF6D4A26797B2F5DCB9AF7363CA2' = 'TELEMETRY_V004_REENVIO_ZIP_NOT_ORIGINAL'
    '46E4E52FC84DF1FDC043573D7F54361A173A6937A21C7011D69A3B1EF2E37D07' = 'TELEMETRY_V004_REENVIO_PREP_PY_NOT_ORIGINAL'
    '1F03965868E63A5D950910FE01B529668403C8E528D148440185C811EC2DD19D' = 'TELEMETRY_V004_REENVIO_SHA_SIDECAR'
    '76833706F5E87F386071F35328D362FA0C5ABB124AC52CA1AA0840A603D7C408' = 'PREREG_H1H3_V003_ZIP_NOT_V004'
    '8DD95E2E9B833B04723AA86A7952897D06E407BA0C0292367B37FEEE82818AEA' = 'CONFIRMATORY_CODE_V001R2_ZIP'
    'B859614801DB3A8C72CB5BD902A264E4F14C31E0B822AC1D3E89AE71EF52B4D7' = 'CONFIRMATORY_CODE_AUDIT_PASS_ZIP'
    '3F6BD3F5067CD1E54E9D4CF7B3E289333C03E20737A05591EFF5439E1D6FE625' = 'PREREG_V003_AUDIT_AND_CONTAMINATION_ZIP'
    '93092E9A8FB656CF5696087CE863C1F7B5F1601B52621993081A98A49B2F628D' = 'D1_PHYSICAL_IDENTITY_INFORMED_BY_ORIGIN'
    'CBA5B92735CE5CB8DA5FE353BC7BB17A5339C2AC3B02F20778C81A4A391C127C' = 'D1_CERT_R4R8_SEP2026_PREDECESSOR'
    '28DF85A4BF87B859230C931042C493CD6B4E57FE8698135C3D771C56E466E68C' = 'R4R9_RUNNER_perseu_parallel_auto'
    '042FA9CB7DB2DE26BD64F82B41B2A1977B05C65509E2038239BDC972E766F2E5' = 'R4R9_ACCEL_perseu_r4r9_accel'
    '5D3DB8FD5EB532D23DB7F9FF9FCA7A4041447EBE6E66AC674D29CBDB7C74AB7E' = 'R4R9_test_parallel_auto_PRISTINE'
    'B8E1417ED0806AA03B3C3C89FACD3A0CDDC856971E76B1152DCD9312F553E8B8' = 'R4R9_test_r4r9_gate'
    'A331F308182766C299B067BE2035EB071E01019C28A6C20DD6DF09B1AB92607F' = 'CORE_perseu_exploratorio_R4R7_R4R8_R4R9'
    '7CC5A79C81B481847AEBA52D4441293305079F766D52CE2D04DCAEACE9C34A80' = 'CORE_TESTS_test_perseu_exploratorio'
    '8EE1A1B17771ECEB536A233E8319CB574F61F86472F07C2C5229ADC93E0641FB' = 'R4R8_RUNNER_BASELINE'
    '78830B5AF55FE3D88D382B294FFEDBB33ADAD597D8BF091B11D5B70F3EF33328' = 'R4R9_C1_WRAPPER'
    '53C8A1FBAA0C836DCB616789BD0C1D7264CCA6E97C8780E364FA05204E088ADD' = 'R4R9_C2_WRAPPER'
    '23AAE25717C36CCE99E37697215DE2B0C5AB6ADC85B582BEE14078DAE1BFD62B' = 'HOTFIX_R1_MODULE'
    '6D6A75477BD28CFE1E40E155A23BA739F2D62E6DE08BE01B7A57D6FCDCFF1034' = 'HOTFIX_R1_WRAPPER'
    '07562BD138422CE5E7033C7042D23CC1AB9963B28ABAFD869727CBD8BAB28CDF' = 'HOTFIX_R2_MODULE'
    'DE7506A9C1B056B9155F9D2E6EB0FD83B583D8878877B7773FCDAD954672BE57' = 'HOTFIX_R2_WRAPPER'
    '6F77DFA4AB70BE0A3804B406CEF8DF2D8567A02470BE1993E51AA5F5CB5BBB13' = 'HOTFIX_R3_MODULE_DERIVED_STATIC'
    'A0AA416919F8FA755B055FAB8060AF001B4C86502E1EA6E993343E99E0B63787' = 'TELEMETRY_V1_SHIM_KNOWN_FAILED'
    '4F3339AE2C2FA71E336273D1C317DBA8F80B6206E971042169A53E85A10F65F0' = 'TELEMETRY_V1_WRAPPER_KNOWN_FAILED'
    'ACF50B1FFA1B42C43E4552E8632419E680AD1AC815C3A3DFF5ECBA1DA49467C4' = 'TELEMETRY_V2_SHIM_KNOWN_FAILED'
    '33FC2095B24AF2F70C1982EF28878125726A85762DFA8009377FA2F7BFD01AB1' = 'TELEMETRY_V2_WRAPPER_KNOWN_FAILED'
    'C92AC5A38184CCDDC5E45892654FC41A8E1A31B2B63544B173E72E728F2923D0' = 'TELEMETRY_V3_SHIM_KNOWN_FAILED'
    '1BA52D0AECE7107AE64859FC796242FB9363F8DDECAC1E5DB8015C23F76977D4' = 'TELEMETRY_V3_WRAPPER_KNOWN_FAILED'
    '8BF0BFBB6D142B0088E4FED5E0F7A74F1786AD2D427AE8338C45F7F29B624710' = 'TELEMETRY_V4_SHIM_REENVIO_DERIVED_CRLF'
    '882C90AF4561B8DA8E68DCBD4D60D2EF9E2F4AD030B6553F980A7A6B2A4CB7FD' = 'TELEMETRY_V4_SHIM_REENVIO_LF'
    'A86A3C635AA1878061FF93F3A5251304E74C7208EA138B18034EDFF81EC7C48F' = 'HD500_TOP4_V003_PREDELIVERY_QUALIFICATION_ZIP'
    '416A385CCAEBCCC95A7806A4EF37F7092A58CF2375162B6FDF09735F716AD90C' = 'TOP4_ARCHIVE_SOURCE_MANIFEST_CSV'
    'D3717C4A09255C9C1003325454BDB4912DD53CA3C5B95AEEAD637F9EB1F7711B' = 'RECOVERED_AUDIT_HOTFIX_IDENTITY_MIGRATION_PREFLIGHT_V001'
    'A7FF4FCC4E2B6AC9FCC99F73B78F8BBAD516BC62B831888F4E7F4C4BBC753133' = 'RECOVERED_AUDIT_TELEMETRY_GAPS_V001'
    'DCD331A213280349CBD41FF11A3A36D3C8FC101F0467C92C5E47084A37822A09' = 'RECOVERED_AUDIT_TELEMETRY_SEMANTICS_V002'
    'F05CFE3DBFED304DAF59839C638DA2378B56E9CB4CB39A5D8BA4BD90742B4DC8' = 'RECOVERED_FIXTURE_FIX_PREP_V002'
    'C664F36314E5C6901C9E5010BFB9618AD385399099E5FB663BF1F37837D0F880' = 'RECOVERED_PREP_CONFIRMATORY_C1_C2_V001'
    '7DBA5E7DCBD07483A8943D18E8B785389FD01CE258EA0E9C362BF794CC16ADB7' = 'RECOVERED_PREP_HOTFIX_R1_V001'
    'B92867AA31707AE8BBA4FBC88431A5BDE5F98AEE7333400948403A2BE74145F1' = 'RECOVERED_PREP_HOTFIX_R2_V002'
    'CFAFC741C4B859FBB4D30BD0926EA9CB2B1AAE368D40963CFA8E0B84DFB5C94A' = 'RECOVERED_PREP_HOTFIX_R3_V003'
    'E5CAFB8E89865E8796B13438AB582609E5E3C0D6B7D59D7B173A110EB4497598' = 'RECOVERED_RUN_CONFIRMATORY_C1_C2_V001'
}

$script:Phase = 'INIT'
$script:KnownActive = $KnownSha
$script:HashBudgetLimit = $HashBudgetBytes
$script:RunDir = $null
$script:LogPath = $null
$script:HashBudgetUsed = [int64]0
$script:EvidenceFiles = New-Object System.Collections.Generic.List[string]

function Get-CslTimestamp {
    return (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz', $Invariant)
}

function Write-CslLog {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Line)
    Write-Host $Line
    if ($null -ne $script:LogPath) {
        [System.IO.File]::AppendAllText($script:LogPath, ((Get-CslTimestamp) + ' ' + $Line + "`r`n"), $Utf8NoBom)
    }
}

function Stop-CslBlocked {
    param([Parameter(Mandatory = $true)][string]$Reason)
    throw (New-Object System.InvalidOperationException('BLOCKED:' + $Reason))
}

function Write-CslNewText {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text
    )
    if ([System.IO.File]::Exists($LiteralPath)) { Stop-CslBlocked -Reason ('EVIDENCE_FILE_PREEXISTS:' + $LiteralPath) }
    $bytes = $Utf8NoBom.GetBytes($Text)
    $fs = New-Object System.IO.FileStream($LiteralPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $fs.Write($bytes, 0, $bytes.Length)
        $fs.Flush($true)
    } finally {
        $fs.Dispose()
    }
    $script:EvidenceFiles.Add($LiteralPath)
}

function Get-CslLabel {
    # [object], not [string]: a [string] parameter silently turns $null into '' (PS coercion).
    param([AllowNull()][object]$Sha)
    if ($null -eq $Sha -or ([string]$Sha).Length -eq 0) { return $null }
    if ($script:KnownActive.ContainsKey([string]$Sha)) { return [string]$script:KnownActive[[string]$Sha] }
    return 'UNKNOWN_IDENTITY'
}

function Measure-CslItem {
    # Metadata + guarded SHA-256 of one filesystem item. Never follows links, never hydrates placeholders.
    param([Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item)
    $attr = [int64]$Item.Attributes
    $isDir = (($attr -band 0x10) -ne 0)
    $linkType = $null
    $ltProp = $Item.PSObject.Properties['LinkType']
    if ($null -ne $ltProp -and $null -ne $ltProp.Value) { $linkType = [string]$ltProp.Value }
    $rec = [ordered]@{
        path = $Item.FullName; name = $Item.Name; directory = $isDir; attributes = $attr
        reparse = (($attr -band 0x400) -ne 0); link_type = $linkType
        bytes = $null; last_write_utc = $Item.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ', $Invariant)
        sha256 = $null; label = $null; hash_status = 'NOT_APPLICABLE'
    }
    if ($isDir) { return [pscustomobject]$rec }
    $len = [int64]$Item.Length
    $rec.bytes = $len
    if (($attr -band $PlaceholderMask) -ne 0) { $rec.hash_status = 'NOT_HASHED_CLOUD_PLACEHOLDER_OR_OFFLINE'; return [pscustomobject]$rec }
    if ($null -ne $linkType -and $linkType -ne '') { $rec.hash_status = 'NOT_HASHED_LINK'; return [pscustomobject]$rec }
    if ($len -gt $HashCapBytes) { $rec.hash_status = 'NOT_HASHED_SIZE_CAP'; return [pscustomobject]$rec }
    if (($script:HashBudgetUsed + $len) -gt $script:HashBudgetLimit) { $rec.hash_status = 'NOT_HASHED_TOTAL_BUDGET'; return [pscustomobject]$rec }
    try {
        $rec.sha256 = (Get-FileHash -LiteralPath $Item.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
        $script:HashBudgetUsed = $script:HashBudgetUsed + $len
        $rec.label = Get-CslLabel -Sha $rec.sha256
        $rec.hash_status = 'HASHED'
    } catch {
        $rec.hash_status = 'HASH_ERROR:' + $_.Exception.GetType().Name
    }
    return [pscustomobject]$rec
}

function Test-CslExact {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [AllowNull()][object]$ExpectedSha,
        [Parameter(Mandatory = $true)][string]$Class
    )
    $expected = $null
    if ($null -ne $ExpectedSha -and ([string]$ExpectedSha).Length -gt 0) { $expected = [string]$ExpectedSha }
    $res = [ordered]@{ id = $Id; class = $Class; path = $LiteralPath; expected_sha256 = $expected; expected_label = (Get-CslLabel -Sha $expected); status = 'NOT_FOUND'; item = $null }
    if (Test-Path -LiteralPath $LiteralPath) {
        $item = Get-Item -LiteralPath $LiteralPath -Force
        $m = Measure-CslItem -Item $item
        $res.item = $m
        if ($m.directory) { $res.status = 'FOUND_DIRECTORY' }
        elseif ($m.hash_status -ne 'HASHED') { $res.status = 'FOUND_' + $m.hash_status }
        elseif ($null -eq $expected) { $res.status = 'FOUND_UNPINNED' }
        elseif ($m.sha256 -eq $expected) { $res.status = 'FOUND_MATCH' }
        else { $res.status = 'FOUND_MISMATCH' }
    }
    Write-CslLog ('EXACT ID=' + $Id + ' STATUS=' + $res.status + ' PATH=' + $LiteralPath)
    return [pscustomobject]$res
}

function Find-CslPattern {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string[]]$Roots,
        [Parameter(Mandatory = $true)][string[]]$Patterns,
        [Parameter(Mandatory = $true)][string]$Class
    )
    $hits = New-Object System.Collections.Generic.List[object]
    $rootStatus = New-Object System.Collections.Generic.List[object]
    foreach ($root in $Roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) {
            $rootStatus.Add([pscustomobject][ordered]@{ root = $root; exists = $false })
            continue
        }
        $rootStatus.Add([pscustomobject][ordered]@{ root = $root; exists = $true })
        $entries = @(Get-ChildItem -LiteralPath $root -Force)
        foreach ($e in $entries) {
            $matched = $false
            foreach ($pat in $Patterns) {
                if ($e.Name -like $pat) { $matched = $true }
            }
            if ($matched) { $hits.Add((Measure-CslItem -Item $e)) }
        }
    }
    Write-CslLog ('PATTERN ID=' + $Id + ' CANDIDATES=' + $hits.Count)
    return [pscustomobject][ordered]@{ id = $Id; class = $Class; patterns = $Patterns; roots = $rootStatus.ToArray(); candidates = $hits.ToArray(); candidate_count = $hits.Count }
}

function Get-CslTreeInventory {
    param([Parameter(Mandatory = $true)][string]$Root)
    $files = New-Object System.Collections.Generic.List[object]
    $notFollowed = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        return [pscustomobject][ordered]@{ root = $Root; exists = $false; files = @(); file_count = 0; dirs = 0; not_followed = @(); truncated = $false }
    }
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Root)
    $dirs = 0
    $truncated = $false
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        $dirs = $dirs + 1
        if ($dirs -gt $InventoryMaxDirs) { $truncated = $true; break }
        foreach ($e in @(Get-ChildItem -LiteralPath $current -Force)) {
            $m = Measure-CslItem -Item $e
            if ($m.directory) {
                if ($m.reparse -or ($null -ne $m.link_type -and $m.link_type -ne '')) { $notFollowed.Add($m.path + ' [LINK=' + $m.link_type + ' REPARSE=' + $m.reparse + ']'); continue }
                $stack.Push($e.FullName)
                continue
            }
            if ($files.Count -ge $InventoryMaxFiles) { $truncated = $true; break }
            $files.Add($m)
        }
        if ($truncated) { break }
    }
    Write-CslLog ('TREE ROOT=' + $Root + ' FILES=' + $files.Count + ' DIRS=' + $dirs + ' NOT_FOLLOWED=' + $notFollowed.Count + ' TRUNCATED=' + $truncated)
    return [pscustomobject][ordered]@{ root = $Root; exists = $true; files = $files.ToArray(); file_count = $files.Count; dirs = $dirs; not_followed = $notFollowed.ToArray(); truncated = $truncated }
}

function Get-CslRunFolder {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $r = [ordered]@{ path = $LiteralPath; exists = $false; first_level_entries = $null; reparse = $null }
    if (Test-Path -LiteralPath $LiteralPath -PathType Container) {
        $it = Get-Item -LiteralPath $LiteralPath -Force
        $r.exists = $true
        $r.reparse = (([int64]$it.Attributes -band 0x400) -ne 0)
        $r.first_level_entries = @(Get-ChildItem -LiteralPath $LiteralPath -Force).Count
    }
    Write-CslLog ('RUN_FOLDER PATH=' + $LiteralPath + ' EXISTS=' + $r.exists + ' ENTRIES=' + $r.first_level_entries)
    return [pscustomobject]$r
}

function Invoke-CslLocate {
    param(
        [Parameter(Mandatory = $true)][string]$PrimaryRoot,
        [Parameter(Mandatory = $true)][string]$SecondaryRoot,
        [Parameter(Mandatory = $true)][string]$RunsRoot
    )
    $install = [System.IO.Path]::Combine($PrimaryRoot, $InstallRootName)
    $exact = New-Object System.Collections.Generic.List[object]
    $zipName = 'PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921.zip'
    $exact.Add((Test-CslExact -Id 'R4R9_ZIP_PRIMARY' -LiteralPath ([System.IO.Path]::Combine($PrimaryRoot, $zipName)) -ExpectedSha '70D6E13125EDCA3FC0AC5049ADBE0FD605AA5111598030EBFDE8A35030C0F69F' -Class 'REQUIRED'))
    $exact.Add((Test-CslExact -Id 'R4R9_ZIP_SECONDARY' -LiteralPath ([System.IO.Path]::Combine($SecondaryRoot, $zipName)) -ExpectedSha '70D6E13125EDCA3FC0AC5049ADBE0FD605AA5111598030EBFDE8A35030C0F69F' -Class 'REQUIRED_ALTERNATE'))
    $installFiles = @(
        @('INSTALL_RUNNER', 'perseu_parallel_auto.py', '28DF85A4BF87B859230C931042C493CD6B4E57FE8698135C3D771C56E466E68C', 'REQUIRED'),
        @('INSTALL_ACCEL', 'perseu_r4r9_accel.py', '042FA9CB7DB2DE26BD64F82B41B2A1977B05C65509E2038239BDC972E766F2E5', 'REQUIRED'),
        @('INSTALL_CORE', 'perseu_exploratorio.py', 'A331F308182766C299B067BE2035EB071E01019C28A6C20DD6DF09B1AB92607F', 'REQUIRED'),
        @('INSTALL_TEST_PARALLEL', 'test_parallel_auto.py', '5D3DB8FD5EB532D23DB7F9FF9FCA7A4041447EBE6E66AC674D29CBDB7C74AB7E', 'REQUIRED'),
        @('INSTALL_TEST_R4R9_GATE', 'test_r4r9_gate.py', 'B8E1417ED0806AA03B3C3C89FACD3A0CDDC856971E76B1152DCD9312F553E8B8', 'REQUIRED'),
        @('INSTALL_TEST_CORE', 'test_perseu_exploratorio.py', '7CC5A79C81B481847AEBA52D4441293305079F766D52CE2D04DCAEACE9C34A80', 'REQUIRED'),
        @('INSTALL_BASELINE_R4R8_RUNNER', 'BASELINE_R4R8\perseu_parallel_auto.py', '8EE1A1B17771ECEB536A233E8319CB574F61F86472F07C2C5229ADC93E0641FB', 'SUPPORT'),
        @('INSTALL_MANIFEST', 'MANIFEST_SHA256.json', $null, 'REQUIRED_IDENTITY_UNPINNED'),
        @('INSTALL_SEP_WRAPPER', 'RUN_WINDOWS_R4R9_SEP2026.ps1', $null, 'REQUIRED_IDENTITY_UNPINNED'),
        @('INSTALL_LOCAL_TESTS_WRAPPER', 'RUN_WINDOWS_R4R9_LOCAL_TESTS.ps1', $null, 'SUPPORT'),
        @('INSTALL_C1_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C1_202502.ps1', '78830B5AF55FE3D88D382B294FFEDBB33ADAD597D8BF091B11D5B70F3EF33328', 'SUPPORT'),
        @('INSTALL_C2_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1', '53C8A1FBAA0C836DCB616789BD0C1D7264CCA6E97C8780E364FA05204E088ADD', 'REQUIRED'),
        @('HOTFIX_R1_MODULE', 'perseu_parallel_auto_resume_hotfix_r1.py', '23AAE25717C36CCE99E37697215DE2B0C5AB6ADC85B582BEE14078DAE1BFD62B', 'PROVENANCE'),
        @('HOTFIX_R1_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C1_202502_HOTFIX_R1.ps1', '6D6A75477BD28CFE1E40E155A23BA739F2D62E6DE08BE01B7A57D6FCDCFF1034', 'PROVENANCE'),
        @('HOTFIX_R2_MODULE', 'perseu_parallel_auto_resume_hotfix_r2.py', '07562BD138422CE5E7033C7042D23CC1AB9963B28ABAFD869727CBD8BAB28CDF', 'PROVENANCE'),
        @('HOTFIX_R2_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C1_202502_HOTFIX_R2.ps1', 'DE7506A9C1B056B9155F9D2E6EB0FD83B583D8878877B7773FCDAD954672BE57', 'PROVENANCE'),
        @('HOTFIX_R3_MODULE', 'perseu_parallel_auto_resume_hotfix_r3.py', '6F77DFA4AB70BE0A3804B406CEF8DF2D8567A02470BE1993E51AA5F5CB5BBB13', 'REQUIRED_DERIVED_IDENTITY'),
        @('HOTFIX_R3_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C1_202502_HOTFIX_R3.ps1', $null, 'REQUIRED_IDENTITY_UNPINNED'),
        @('TELEMETRY_V1_SHIM', 'perseu_r4r9_telemetry_v1.py', 'A0AA416919F8FA755B055FAB8060AF001B4C86502E1EA6E993343E99E0B63787', 'PROVENANCE'),
        @('TELEMETRY_V1_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V1.ps1', '4F3339AE2C2FA71E336273D1C317DBA8F80B6206E971042169A53E85A10F65F0', 'PROVENANCE'),
        @('TELEMETRY_V2_SHIM', 'perseu_r4r9_telemetry_v2.py', 'ACF50B1FFA1B42C43E4552E8632419E680AD1AC815C3A3DFF5ECBA1DA49467C4', 'PROVENANCE'),
        @('TELEMETRY_V2_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V2.ps1', '33FC2095B24AF2F70C1982EF28878125726A85762DFA8009377FA2F7BFD01AB1', 'PROVENANCE'),
        @('TELEMETRY_V3_SHIM', 'perseu_r4r9_telemetry_v3.py', 'C92AC5A38184CCDDC5E45892654FC41A8E1A31B2B63544B173E72E728F2923D0', 'PROVENANCE'),
        @('TELEMETRY_V3_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V3.ps1', '1BA52D0AECE7107AE64859FC796242FB9363F8DDECAC1E5DB8015C23F76977D4', 'PROVENANCE'),
        @('TELEMETRY_V4_SHIM', 'perseu_r4r9_telemetry_v4.py', $null, 'REQUIRED_VARIANT_BY_LABEL'),
        @('TELEMETRY_V4_WRAPPER', 'RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V4.ps1', $null, 'REQUIRED_IDENTITY_UNPINNED')
    )
    foreach ($row in $installFiles) {
        $exact.Add((Test-CslExact -Id $row[0] -LiteralPath ([System.IO.Path]::Combine($install, $row[1])) -ExpectedSha $row[2] -Class $row[3]))
    }
    $reports = @(
        'PERSEU_R4R9_CONFIRMATORY_CAPABILITY_AUDIT_V002.json', 'PERSEU_R4R9_CONFIRMATORY_PREP_C1_C2_V001.json',
        'PERSEU_R4R9_FIXTURE_FIX_AND_CONFIRMATORY_PREP_V002.json', 'PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R1_PREP_V001.json',
        'PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R2_PREP_V002.json', 'PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R3_PREP_V003.json',
        'PERSEU_R4R9_HOTFIX_IDENTITY_MIGRATION_PREFLIGHT_V001.json', 'PREP_PERSEU_R4R9_C2_TELEMETRY_V004.json',
        'AUDIT_PERSEU_R4R9_TELEMETRY_GAPS_V001.json', 'AUDIT_PERSEU_R4R9_TELEMETRY_GAPS_V001_CONTEXT.txt',
        'AUDIT_PERSEU_R4R9_TELEMETRY_SEMANTICS_V002.json', 'AUDIT_PERSEU_R4R9_TELEMETRY_SEMANTICS_V002_CONTEXT.txt',
        'D1_HOMOLOGATION_CERT_V001_20260919.json'
    )
    foreach ($name in $reports) {
        $exact.Add((Test-CslExact -Id ('REPORT_' + $name) -LiteralPath ([System.IO.Path]::Combine($PrimaryRoot, $name)) -ExpectedSha $null -Class 'EVIDENCE'))
    }
    $roots = @($PrimaryRoot, $SecondaryRoot)
    $patterns = New-Object System.Collections.Generic.List[object]
    $patterns.Add((Find-CslPattern -Id 'R4R9_FAMILY' -Roots $roots -Patterns @('PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9*') -Class 'REQUIRED_DISCOVERY'))
    $patterns.Add((Find-CslPattern -Id 'PREREG_V004' -Roots $roots -Patterns @('*PREREG*V004*', '*H1_H3*V004*', '*PREREG_V004*') -Class 'REQUIRED_IDENTITY_UNPINNED'))
    $patterns.Add((Find-CslPattern -Id 'PREREG_ALL_VERSIONS' -Roots $roots -Patterns @('PERSEU_H1_H3_CONFIRMATORY_PREREG*') -Class 'DISAMBIGUATION'))
    $patterns.Add((Find-CslPattern -Id 'TELEMETRY_V004_ALL' -Roots $roots -Patterns @('*TELEMETRY_V004*') -Class 'REQUIRED_VARIANT_BY_LABEL'))
    $patterns.Add((Find-CslPattern -Id 'HOTFIX_ARTIFACTS' -Roots $roots -Patterns @('*R4R9*HOTFIX*') -Class 'REQUIRED_DISCOVERY'))
    $patterns.Add((Find-CslPattern -Id 'D1_CERTS' -Roots $roots -Patterns @('D1_HOMOLOGATION_CERT_*') -Class 'REQUIRED_IDENTITY_BY_LABEL'))
    $patterns.Add((Find-CslPattern -Id 'R4R9_RUN_LOGS_AND_RECEIPTS' -Roots $roots -Patterns @('PERSEU_R4R9_*.log', 'PERSEU_R4R9_CONFIRMATORY_C1_C2_RECEIPT_*.json') -Class 'EVIDENCE'))
    $runFolders = New-Object System.Collections.Generic.List[object]
    foreach ($leaf in @('PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C1_202502', 'PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C2_202608', 'PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_SEP2026')) {
        $runFolders.Add((Get-CslRunFolder -LiteralPath ([System.IO.Path]::Combine($RunsRoot, $leaf))))
    }
    $tree = Get-CslTreeInventory -Root $install
    return [pscustomobject][ordered]@{ install_root = $install; exact = $exact.ToArray(); patterns = $patterns.ToArray(); run_folders = $runFolders.ToArray(); install_tree = $tree }
}

function Get-CslGate {
    param([Parameter(Mandatory = $true)][object]$Located)
    $blockers = New-Object System.Collections.Generic.List[string]
    $byId = @{}
    foreach ($e in $Located.exact) { $byId[$e.id] = $e }
    if ($byId['R4R9_ZIP_PRIMARY'].status -ne 'FOUND_MATCH' -and $byId['R4R9_ZIP_SECONDARY'].status -ne 'FOUND_MATCH') { $blockers.Add('R4R9_ORIGINAL_ZIP_NOT_FOUND_WITH_MATCHING_SHA') }
    foreach ($id in @('INSTALL_RUNNER', 'INSTALL_ACCEL', 'INSTALL_CORE', 'INSTALL_TEST_PARALLEL', 'INSTALL_TEST_R4R9_GATE', 'INSTALL_TEST_CORE', 'INSTALL_C2_WRAPPER')) {
        if ($byId[$id].status -ne 'FOUND_MATCH') { $blockers.Add($id + '_' + $byId[$id].status) }
    }
    if ($byId['HOTFIX_R3_MODULE'].status -ne 'FOUND_MATCH') { $blockers.Add('HOTFIX_R3_MODULE_' + $byId['HOTFIX_R3_MODULE'].status) }
    $blockers.Add('HOTFIX_TARGET_APPLICATION_RECEIPT_NOT_PROVEN_BY_LOCATOR')
    $v4 = $byId['TELEMETRY_V4_SHIM']
    if ($v4.status -eq 'FOUND_UNPINNED' -and $null -ne $v4.item -and $v4.item.label -like 'TELEMETRY_V4_SHIM_REENVIO*') { $blockers.Add('TELEMETRY_V4_INSTALLED_IS_REENVIO_ORIGINAL_STILL_UNIDENTIFIED') }
    elseif ($v4.status -eq 'FOUND_UNPINNED') { $blockers.Add('TELEMETRY_V4_INSTALLED_UNKNOWN_VARIANT_ORIGIN_MUST_PIN') }
    else { $blockers.Add('TELEMETRY_V4_SHIM_' + $v4.status) }
    $prereg = @($Located.patterns | Where-Object { $_.id -eq 'PREREG_V004' })[0]
    if ($prereg.candidate_count -eq 0) { $blockers.Add('PREREG_V004_NOT_FOUND') } else { $blockers.Add('PREREG_V004_CANDIDATES_FOUND_ORIGIN_MUST_PIN_IDENTITY') }
    $d1 = @($Located.patterns | Where-Object { $_.id -eq 'D1_CERTS' })[0]
    $d1Hits = @($d1.candidates | Where-Object { $_.label -eq 'D1_PHYSICAL_IDENTITY_INFORMED_BY_ORIGIN' }).Count
    if ($d1Hits -ne 1) { $blockers.Add('D1_IDENTITY_93092E9A_CARDINALITY_' + $d1Hits) }
    $status = 'BLOCKED'
    if ($blockers.Count -eq 0) { $status = 'PASS' }
    return [pscustomobject][ordered]@{ C2_SOURCE_GATE = $status; blockers = $blockers.ToArray() }
}

function Select-CslHd2Binding {
    # Pure binding: serial+model+Online+exactly one drive letter; inputs are Get-Disk/Get-Partition rows.
    param([AllowEmptyCollection()][object[]]$Disks, [AllowEmptyCollection()][object[]]$Partitions)
    $fail = { param($r) return [pscustomobject][ordered]@{ ok = $false; reason = $r; letter = $null; disk_number = $null; size_bytes = $null; hd1_present = $null } }
    $hd2 = @($Disks | Where-Object { ([string]$_.SerialNumber).Trim().ToUpperInvariant() -eq $Hd2Serial })
    if ($hd2.Count -ne 1) { return (& $fail ('HD2_SERIAL_CARDINALITY_' + $hd2.Count)) }
    $disk = $hd2[0]
    if (([string]$disk.FriendlyName).Trim() -ne $Hd2Model) { return (& $fail 'HD2_MODEL_MISMATCH') }
    if ([string]$disk.OperationalStatus -ne 'Online') { return (& $fail 'HD2_NOT_ONLINE_NO_MUTATION_ATTEMPTED') }
    $number = [int64]$disk.Number
    $letters = @($Partitions | Where-Object { [int64]$_.DiskNumber -eq $number } | ForEach-Object { ([string]$_.DriveLetter).Trim().ToUpperInvariant() } | Where-Object { $_ -match '^[A-Z]$' })
    if ($letters.Count -ne 1) { return (& $fail ('HD2_DRIVE_LETTER_CARDINALITY_' + $letters.Count)) }
    $owners = @($Partitions | Where-Object { ([string]$_.DriveLetter).Trim().ToUpperInvariant() -eq $letters[0] }).Count
    if ($owners -ne 1) { return (& $fail 'HD2_DRIVE_LETTER_MULTIPLE_OWNERS') }
    $hd1 = @($Disks | Where-Object { ([string]$_.SerialNumber).Trim().ToUpperInvariant() -eq $Hd1Serial }).Count
    return [pscustomobject][ordered]@{ ok = $true; reason = 'BOUND'; letter = $letters[0]; disk_number = $number; size_bytes = [int64]$disk.Size; hd1_present = $hd1 }
}

function Get-CslHd2Binding {
    $disks = @(Get-Disk | Select-Object -Property Number, FriendlyName, SerialNumber, Size, OperationalStatus)
    $parts = @(Get-Partition | Select-Object -Property DiskNumber, PartitionNumber, DriveLetter)
    $b = Select-CslHd2Binding -Disks $disks -Partitions $parts
    Write-CslLog ('HD2_BINDING OK=' + $b.ok + ' REASON=' + $b.reason + ' LETTER=' + $b.letter + ' DISK=' + $b.disk_number + ' HD1_PRESENT=' + $b.hd1_present)
    if (-not $b.ok) { Stop-CslBlocked -Reason $b.reason }
    return $b
}

function Find-CslIndexHits {
    # Schema-agnostic: searches index-like text files for known SHA-256 values and target names.
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Items, [Parameter(Mandatory = $true)][string[]]$Tokens)
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($m in $Items) {
        if ($m.directory) { continue }
        $ext = [System.IO.Path]::GetExtension($m.name).ToLowerInvariant()
        if (@('.csv', '.json', '.txt', '.tsv', '.log', '.md') -notcontains $ext) { continue }
        $rec = [ordered]@{ path = $m.path; bytes = $m.bytes; sha256 = $m.sha256; scanned = $false; skip_reason = $null; hits = @() }
        if ((([int64]$m.attributes) -band $PlaceholderMask) -ne 0) { $rec.skip_reason = 'CLOUD_PLACEHOLDER_OR_OFFLINE'; $out.Add([pscustomobject]$rec); continue }
        if ($m.reparse -or [int64]$m.bytes -gt $IndexScanCapBytes) { $rec.skip_reason = 'REPARSE_OR_SIZE_CAP'; $out.Add([pscustomobject]$rec); continue }
        try {
            $text = [System.IO.File]::ReadAllText($m.path)
        } catch {
            $rec.skip_reason = 'READ_ERROR:' + $_.Exception.GetType().Name
            $out.Add([pscustomobject]$rec)
            continue
        }
        $rec.scanned = $true
        $hits = New-Object System.Collections.Generic.List[object]
        foreach ($tok in $Tokens) {
            $pos = $text.IndexOf($tok, [System.StringComparison]::OrdinalIgnoreCase)
            if ($pos -lt 0) { continue }
            $count = 0
            $excerpts = New-Object System.Collections.Generic.List[string]
            while ($pos -ge 0 -and $count -lt 1000) {
                $count = $count + 1
                if ($excerpts.Count -lt 3) {
                    $ls = $text.LastIndexOf([char]10, [System.Math]::Max($pos, 0)) + 1
                    $le = $text.IndexOf([char]10, $pos)
                    if ($le -lt 0) { $le = $text.Length }
                    $line = $text.Substring($ls, [System.Math]::Min($le - $ls, 400)).Trim()
                    $excerpts.Add($line)
                }
                $pos = $text.IndexOf($tok, $pos + $tok.Length, [System.StringComparison]::OrdinalIgnoreCase)
            }
            $hits.Add([pscustomobject][ordered]@{ token = $tok; label = (Get-CslLabel -Sha $tok); occurrences = $count; excerpts = $excerpts.ToArray() })
        }
        $rec.hits = $hits.ToArray()
        $out.Add([pscustomobject]$rec)
    }
    return $out.ToArray()
}

function Invoke-CslHd2Scan {
    param(
        [Parameter(Mandatory = $true)][string]$ArchiveRoot,
        [Parameter(Mandatory = $true)][bool]$Deep,
        [Parameter(Mandatory = $true)][hashtable]$KnownMap,
        [Parameter(Mandatory = $true)][int]$EntryLimit,
        [Parameter(Mandatory = $true)][int64]$HashBudget,
        [AllowNull()][object]$RecoverDir
    )
    $savedKnown = $script:KnownActive
    $savedLimit = $script:HashBudgetLimit
    $savedUsed = $script:HashBudgetUsed
    $script:KnownActive = $KnownMap
    $script:HashBudgetLimit = $HashBudget
    $script:HashBudgetUsed = [int64]0
    try {
        $res = [ordered]@{ archive_root = $ArchiveRoot; exists = $false; deep = $Deep; first_level = @(); index_files = @(); data_first_level_names = @(); deep_scan = $null }
        if (-not (Test-Path -LiteralPath $ArchiveRoot -PathType Container)) {
            Write-CslLog ('HD2_ARCHIVE_ROOT_MISSING=' + $ArchiveRoot)
            return [pscustomobject]$res
        }
        $res.exists = $true
        $first = @(Get-ChildItem -LiteralPath $ArchiveRoot -Force | ForEach-Object { Measure-CslItem -Item $_ })
        $res.first_level = $first
        $tokens = New-Object System.Collections.Generic.List[string]
        foreach ($k in $KnownMap.Keys) { $tokens.Add([string]$k) }
        foreach ($n in $TargetNameTokens) { $tokens.Add($n) }
        $res.index_files = @(Find-CslIndexHits -Items $first -Tokens $tokens.ToArray())
        $data = [System.IO.Path]::Combine($ArchiveRoot, 'DATA')
        if (Test-Path -LiteralPath $data -PathType Container) {
            $res.data_first_level_names = @(Get-ChildItem -LiteralPath $data -Force | ForEach-Object { $_.Name })
        }
        Write-CslLog ('HD2_INDEX FIRST_LEVEL=' + $first.Count + ' INDEX_FILES=' + @($res.index_files).Count + ' DATA_FIRST_LEVEL=' + @($res.data_first_level_names).Count)
        if (-not $Deep) { return [pscustomobject]$res }
        $known = New-Object System.Collections.Generic.List[object]
        $named = New-Object System.Collections.Generic.List[object]
        $notFollowed = New-Object System.Collections.Generic.List[string]
        $budgetSkipped = 0
        $files = 0
        $dirs = 0
        $truncated = $false
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $nextBeat = 30
        $stack = New-Object System.Collections.Generic.Stack[string]
        if (Test-Path -LiteralPath $data -PathType Container) { $stack.Push($data) }
        while ($stack.Count -gt 0 -and -not $truncated) {
            $current = $stack.Pop()
            $dirs = $dirs + 1
            foreach ($e in @(Get-ChildItem -LiteralPath $current -Force)) {
                if (($files + $dirs) -ge $EntryLimit) { $truncated = $true; break }
                $m = Measure-CslItem -Item $e
                if ($m.directory) {
                    if ($m.reparse -or ($null -ne $m.link_type -and $m.link_type -ne '')) { $notFollowed.Add($m.path); continue }
                    $stack.Push($e.FullName)
                    continue
                }
                $files = $files + 1
                if ($m.hash_status -eq 'NOT_HASHED_TOTAL_BUDGET') { $budgetSkipped = $budgetSkipped + 1 }
                $isKnown = ($null -ne $m.label -and $m.label -ne 'UNKNOWN_IDENTITY')
                $isNamed = $false
                foreach ($pat in $TargetNamePatterns) { if ($m.name -like $pat) { $isNamed = $true } }
                if ($isKnown) { $known.Add($m) }
                elseif ($isNamed) { $named.Add($m) }
                $elapsed = [int][System.Math]::Floor($sw.Elapsed.TotalSeconds)
                if ($elapsed -ge $nextBeat) {
                    Write-CslLog ('HEARTBEAT PHASE=HD2_DEEP FILES=' + $files + ' DIRS=' + $dirs + ' HASHED_BYTES=' + $script:HashBudgetUsed + ' KNOWN_HITS=' + $known.Count + ' NAME_HITS=' + $named.Count + ' ELAPSED_S=' + $elapsed + ' TOTAL=UNKNOWN_HISTORICAL_28065 ETA=UNKNOWN SAFE_STOP=YES_READ_ONLY')
                    $nextBeat = $nextBeat + 30
                }
            }
        }
        $recovered = New-Object System.Collections.Generic.List[object]
        if ($null -ne $RecoverDir) {
            [void][System.IO.Directory]::CreateDirectory([string]$RecoverDir)
            $copied = [int64]0
            $seenSha = @{}
            $seq = 0
            foreach ($m in @($known.ToArray()) + @($named.ToArray())) {
                if ($m.hash_status -ne 'HASHED') { $recovered.Add([pscustomobject][ordered]@{ source = $m.path; status = 'NOT_COPIED_NOT_HASHED' }); continue }
                if ($seenSha.ContainsKey($m.sha256)) { $recovered.Add([pscustomobject][ordered]@{ source = $m.path; status = 'DUPLICATE_SHA_NOT_COPIED'; sha256 = $m.sha256 }); continue }
                if (($copied + [int64]$m.bytes) -gt $RecoverCapBytes) { $recovered.Add([pscustomobject][ordered]@{ source = $m.path; status = 'NOT_COPIED_RECOVER_CAP' }); continue }
                $seq = $seq + 1
                $dst = [System.IO.Path]::Combine([string]$RecoverDir, ($seq.ToString('0000', $Invariant) + '_' + $m.name))
                try {
                    [System.IO.File]::Copy($m.path, $dst, $false)
                    $script:EvidenceFiles.Add($dst)
                    $dstSha = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToUpperInvariant()
                    $srcSha = (Get-FileHash -LiteralPath $m.path -Algorithm SHA256).Hash.ToUpperInvariant()
                    $st = 'COPY_SHA_MISMATCH'
                    if ($dstSha -eq $m.sha256 -and $srcSha -eq $m.sha256) { $st = 'RECOVERED_SHA_VERIFIED' }
                    $seenSha[$m.sha256] = $true
                    $copied = $copied + [int64]$m.bytes
                    $recovered.Add([pscustomobject][ordered]@{ source = $m.path; destination = $dst; sha256 = $m.sha256; label = $m.label; bytes = $m.bytes; status = $st })
                } catch {
                    $recovered.Add([pscustomobject][ordered]@{ source = $m.path; destination = $dst; status = 'COPY_ERROR:' + $_.Exception.GetType().Name })
                }
            }
        }
        $res.deep_scan = [pscustomobject][ordered]@{
            files_scanned = $files; dirs_scanned = $dirs; truncated = $truncated; entry_limit = $EntryLimit
            hashed_bytes = $script:HashBudgetUsed; hash_budget = $HashBudget; files_not_hashed_budget = $budgetSkipped
            not_followed = $notFollowed.ToArray(); known_hits = $known.ToArray(); name_candidates = $named.ToArray(); recovered = $recovered.ToArray()
            elapsed_seconds = [int][System.Math]::Floor($sw.Elapsed.TotalSeconds)
        }
        Write-CslLog ('HD2_DEEP FILES=' + $files + ' DIRS=' + $dirs + ' TRUNCATED=' + $truncated + ' HASHED_BYTES=' + $script:HashBudgetUsed + ' KNOWN_HITS=' + $known.Count + ' NAME_HITS=' + $named.Count + ' RECOVERED=' + $recovered.Count)
        return [pscustomobject]$res
    } finally {
        $script:KnownActive = $savedKnown
        $script:HashBudgetLimit = $savedLimit
        $script:HashBudgetUsed = $savedUsed + $script:HashBudgetUsed
    }
}

function Get-CslHd2Gate {
    param([Parameter(Mandatory = $true)][object]$Scan)
    $blockers = New-Object System.Collections.Generic.List[string]
    $found = @{}
    if (-not $Scan.exists) { $blockers.Add('HD2_ARCHIVE_ROOT_MISSING') }
    if ($null -ne $Scan.deep_scan) {
        foreach ($k in $Scan.deep_scan.known_hits) { $found[[string]$k.label] = $true }
        if ($Scan.deep_scan.truncated) { $blockers.Add('HD2_SCAN_TRUNCATED') }
        if ($Scan.deep_scan.files_not_hashed_budget -gt 0) { $blockers.Add('HD2_FILES_NOT_HASHED_BUDGET_' + $Scan.deep_scan.files_not_hashed_budget) }
    } else {
        $blockers.Add('HD2_CONTENT_SCAN_NOT_RUN_INDEX_ONLY')
    }
    foreach ($lab in $RequiredC2Labels) { if (-not $found.ContainsKey($lab)) { $blockers.Add('NOT_FOUND_BY_CONTENT_' + $lab) } }
    $blockers.Add('PREREG_V004_AND_TELEMETRY_V004_ORIGINAL_REQUIRE_ORIGIN_PINNING_OF_NAME_CANDIDATES')
    $status = 'BLOCKED'
    if ($blockers.Count -eq 0) { $status = 'PASS' }
    return [pscustomobject][ordered]@{ C2_SOURCE_GATE = $status; blockers = $blockers.ToArray(); found_labels = @($found.Keys | Sort-Object) }
}

function Invoke-CslSelfTest {
    # Synthetic fixture inside the run directory only (run-owned, preserved as evidence).
    $fx = [System.IO.Path]::Combine($script:RunDir, 'SELFTEST_FIXTURE')
    $primary = [System.IO.Path]::Combine($fx, 'OneDriveDownloads')
    $secondary = [System.IO.Path]::Combine($fx, 'LegacyDownloads')
    $runs = [System.IO.Path]::Combine($fx, 'PerseuRuns')
    $install = [System.IO.Path]::Combine($primary, $InstallRootName)
    foreach ($d in @($fx, $primary, $secondary, $runs, $install, [System.IO.Path]::Combine($install, 'BASELINE_R4R8'), [System.IO.Path]::Combine($runs, 'PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C1_202502'))) {
        [void][System.IO.Directory]::CreateDirectory($d)
    }
    $checks = New-Object System.Collections.Generic.List[object]
    function Add-CslCheck([string]$Name, [bool]$Pass, [string]$Detail) {
        $checks.Add([pscustomobject][ordered]@{ name = $Name; pass = $Pass; detail = $Detail })
        Write-CslLog ('SELFTEST_CHECK ' + $Name + '=' + $(if ($Pass) { 'PASS' } else { 'FAIL' }) + ' ' + $Detail)
    }
    $zipPath = [System.IO.Path]::Combine($primary, 'PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921.zip')
    [System.IO.File]::WriteAllText($zipPath, 'not-the-real-zip', $Utf8NoBom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($install, 'perseu_exploratorio.py'), 'synthetic', $Utf8NoBom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($install, 'MANIFEST_SHA256.json'), '{}', $Utf8NoBom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($primary, 'PERSEU_H1_H3_CONFIRMATORY_PREREG_V004_SYNTHETIC.zip'), 'x', $Utf8NoBom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($secondary, 'PREP_PERSEU_R4R9_C2_TELEMETRY_V004.py'), 'y', $Utf8NoBom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($primary, 'unrelated.txt'), 'z', $Utf8NoBom)
    $placeholder = [System.IO.Path]::Combine($primary, 'D1_HOMOLOGATION_CERT_SYNTHETIC_OFFLINE.json')
    [System.IO.File]::WriteAllText($placeholder, '{}', $Utf8NoBom)
    $offlineSupported = $false
    try {
        [System.IO.File]::SetAttributes($placeholder, ([System.IO.File]::GetAttributes($placeholder) -bor [System.IO.FileAttributes]::Offline))
        $offlineSupported = (([int64][System.IO.File]::GetAttributes($placeholder) -band 0x1000) -ne 0)
    } catch {
        $offlineSupported = $false
    }
    $linkKind = 'NOT_CREATABLE'
    $linkPath = [System.IO.Path]::Combine($install, 'LINK_DIR')
    foreach ($kind in @('Junction', 'SymbolicLink')) {
        if ($linkKind -ne 'NOT_CREATABLE') { break }
        try {
            [void](New-Item -ItemType $kind -Path $linkPath -Value ([System.IO.Path]::Combine($install, 'BASELINE_R4R8')) -ErrorAction Stop)
            # A returned object is not proof: require the physical link (exists + ReparsePoint attribute).
            if ((Test-Path -LiteralPath $linkPath) -and (([int64](Get-Item -LiteralPath $linkPath -Force).Attributes -band 0x400) -ne 0)) { $linkKind = $kind }
        } catch {
            $linkKind = 'NOT_CREATABLE'
        }
    }
    $loc = Invoke-CslLocate -PrimaryRoot $primary -SecondaryRoot $secondary -RunsRoot $runs
    $byId = @{}
    foreach ($e in $loc.exact) { $byId[$e.id] = $e }
    Add-CslCheck 'ZIP_WRONG_BYTES_IS_MISMATCH' ($byId['R4R9_ZIP_PRIMARY'].status -eq 'FOUND_MISMATCH') $byId['R4R9_ZIP_PRIMARY'].status
    Add-CslCheck 'ZIP_SECONDARY_ABSENT_IS_NOT_FOUND' ($byId['R4R9_ZIP_SECONDARY'].status -eq 'NOT_FOUND') $byId['R4R9_ZIP_SECONDARY'].status
    Add-CslCheck 'CORE_WRONG_BYTES_IS_MISMATCH' ($byId['INSTALL_CORE'].status -eq 'FOUND_MISMATCH') $byId['INSTALL_CORE'].status
    Add-CslCheck 'RUNNER_ABSENT_IS_NOT_FOUND' ($byId['INSTALL_RUNNER'].status -eq 'NOT_FOUND') $byId['INSTALL_RUNNER'].status
    Add-CslCheck 'MANIFEST_IS_UNPINNED' ($byId['INSTALL_MANIFEST'].status -eq 'FOUND_UNPINNED') $byId['INSTALL_MANIFEST'].status
    $pv4 = @($loc.patterns | Where-Object { $_.id -eq 'PREREG_V004' })[0]
    Add-CslCheck 'PREREG_V004_PATTERN_ONE_CANDIDATE' ($pv4.candidate_count -eq 1) ([string]$pv4.candidate_count)
    $tel = @($loc.patterns | Where-Object { $_.id -eq 'TELEMETRY_V004_ALL' })[0]
    Add-CslCheck 'TELEMETRY_PATTERN_SECONDARY_ROOT' ($tel.candidate_count -eq 1 -and $tel.candidates[0].path.StartsWith($secondary, [System.StringComparison]::Ordinal)) ([string]$tel.candidate_count)
    $fam = @($loc.patterns | Where-Object { $_.id -eq 'R4R9_FAMILY' })[0]
    Add-CslCheck 'R4R9_FAMILY_ZIP_AND_DIR' ($fam.candidate_count -eq 2) ([string]$fam.candidate_count)
    $d1 = @($loc.patterns | Where-Object { $_.id -eq 'D1_CERTS' })[0]
    if ($offlineSupported) {
        Add-CslCheck 'OFFLINE_PLACEHOLDER_NOT_HASHED' ($d1.candidate_count -eq 1 -and $d1.candidates[0].hash_status -eq 'NOT_HASHED_CLOUD_PLACEHOLDER_OR_OFFLINE' -and $null -eq $d1.candidates[0].sha256) ([string]$d1.candidate_count)
    } else {
        Add-CslCheck 'OFFLINE_PLACEHOLDER_NOT_HASHED' $true 'SKIPPED_ATTRIBUTE_NOT_SUPPORTED_ON_PLATFORM'
    }
    $c1 = @($loc.run_folders | Where-Object { $_.path.EndsWith('CONFIRM_C1_202502') })[0]
    Add-CslCheck 'RUN_FOLDER_EXISTS_EMPTY' ($c1.exists -and $c1.first_level_entries -eq 0) ([string]$c1.first_level_entries)
    $c2 = @($loc.run_folders | Where-Object { $_.path.EndsWith('CONFIRM_C2_202608') })[0]
    Add-CslCheck 'RUN_FOLDER_ABSENT' (-not $c2.exists) ([string]$c2.exists)
    if ($linkKind -ne 'NOT_CREATABLE') {
        Add-CslCheck 'TREE_LINK_NOT_FOLLOWED' ($loc.install_tree.not_followed.Count -eq 1) ([string]$loc.install_tree.not_followed.Count + ' ' + $linkKind)
    } else {
        Add-CslCheck 'TREE_LINK_NOT_FOLLOWED' $true 'SKIPPED_LINK_NOT_CREATABLE'
    }
    Add-CslCheck 'TREE_FILE_COUNT' ($loc.install_tree.file_count -eq 2) ([string]$loc.install_tree.file_count)
    $gate = Get-CslGate -Located $loc
    Add-CslCheck 'GATE_FAIL_CLOSED_ON_SYNTHETIC' ($gate.C2_SOURCE_GATE -eq 'BLOCKED' -and $gate.blockers.Count -ge 5) ([string]$gate.blockers.Count)
    $a = [int64]3000000000
    $b = [int64][int32]::MaxValue + [int64]1
    Add-CslCheck 'INT64_ACCUMULATOR' ((($a + $b) -is [int64]) -and (($a + $b) -eq [int64]5147483648)) ([string]($a + $b))
    # ---- HD2 binding (pure function, synthetic rows) ----
    $okDisk = [pscustomobject]@{ Number = 2; FriendlyName = 'WDC WD5000AAKX-003CA0'; SerialNumber = '   WD-WCAYUS916314'; Size = [uint64]500107862016; OperationalStatus = 'Online' }
    $sysDisk = [pscustomobject]@{ Number = 3; FriendlyName = 'Lexar'; SerialNumber = 'X'; Size = [uint64]1; OperationalStatus = 'Online' }
    $pF = [pscustomobject]@{ DiskNumber = 2; PartitionNumber = 1; DriveLetter = [char]'F' }
    $pNone = [pscustomobject]@{ DiskNumber = 2; PartitionNumber = 2; DriveLetter = [char]0 }
    $pG = [pscustomobject]@{ DiskNumber = 2; PartitionNumber = 3; DriveLetter = [char]'G' }
    $bOk = Select-CslHd2Binding -Disks @($sysDisk, $okDisk) -Partitions @($pF, $pNone)
    Add-CslCheck 'HD2_BIND_OK' ($bOk.ok -and $bOk.letter -eq 'F' -and $bOk.disk_number -eq 2) $bOk.reason
    $bindCases = @(
        @(@($sysDisk), @($pF), 'HD2_SERIAL_CARDINALITY_0'),
        @(@($okDisk, ([pscustomobject]@{ Number = 5; FriendlyName = 'WDC WD5000AAKX-003CA0'; SerialNumber = 'WD-WCAYUS916314'; Size = [uint64]1; OperationalStatus = 'Online' })), @($pF), 'HD2_SERIAL_CARDINALITY_2'),
        @(@(([pscustomobject]@{ Number = 2; FriendlyName = 'ST3500418AS'; SerialNumber = 'WD-WCAYUS916314'; Size = [uint64]1; OperationalStatus = 'Online' })), @($pF), 'HD2_MODEL_MISMATCH'),
        @(@(([pscustomobject]@{ Number = 2; FriendlyName = 'WDC WD5000AAKX-003CA0'; SerialNumber = 'WD-WCAYUS916314'; Size = [uint64]1; OperationalStatus = 'Offline' })), @($pF), 'HD2_NOT_ONLINE_NO_MUTATION_ATTEMPTED'),
        @(@($okDisk), @($pNone), 'HD2_DRIVE_LETTER_CARDINALITY_0'),
        @(@($okDisk), @($pF, $pG), 'HD2_DRIVE_LETTER_CARDINALITY_2')
    )
    foreach ($bc in $bindCases) {
        $r = Select-CslHd2Binding -Disks $bc[0] -Partitions $bc[1]
        Add-CslCheck ('HD2_BIND_NEG_' + $bc[2]) ((-not $r.ok) -and $r.reason -eq $bc[2]) $r.reason
    }
    # ---- HD2 index + content scan (synthetic archive inside the run directory) ----
    $arch = [System.IO.Path]::Combine($fx, 'HD2', 'ARQUIVO_FRIO', 'CHATGPT_DLS_20261007_093221')
    $dl = [System.IO.Path]::Combine($arch, 'DATA', 'OneDrive_Downloads', 'nested')
    [void][System.IO.Directory]::CreateDirectory($dl)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($arch, 'ARCHIVE_MANIFEST.csv'), "path,sha256`nPACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921.zip,70D6E13125EDCA3FC0AC5049ADBE0FD605AA5111598030EBFDE8A35030C0F69F`n", $Utf8NoBom)
    $renamed = [System.IO.Path]::Combine($dl, 'renamed_copy.bin')
    [System.IO.File]::WriteAllText($renamed, 'synthetic-r4r9-runner-bytes', $Utf8NoBom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($dl, 'PREP_PERSEU_R4R9_C2_TELEMETRY_V004.py'), 'candidate', $Utf8NoBom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($dl, 'unrelated.txt'), 'u', $Utf8NoBom)
    $synthSha = (Get-FileHash -LiteralPath $renamed -Algorithm SHA256).Hash.ToUpperInvariant()
    $map = @{}
    foreach ($k in $KnownSha.Keys) { $map[$k] = $KnownSha[$k] }
    $map[$synthSha] = 'SYNTHETIC_TARGET_RENAMED'
    $hdLink = [System.IO.Path]::Combine($arch, 'DATA', 'LINKED')
    $hdLinkMade = $false
    foreach ($kind in @('Junction', 'SymbolicLink')) {
        if ($hdLinkMade) { break }
        try {
            [void](New-Item -ItemType $kind -Path $hdLink -Value $dl -ErrorAction Stop)
            if ((Test-Path -LiteralPath $hdLink) -and (([int64](Get-Item -LiteralPath $hdLink -Force).Attributes -band 0x400) -ne 0)) { $hdLinkMade = $true }
        } catch {
            $hdLinkMade = $false
        }
    }
    $rec = [System.IO.Path]::Combine($fx, 'HD2_RECOVERED')
    $scan = Invoke-CslHd2Scan -ArchiveRoot $arch -Deep $true -KnownMap $map -EntryLimit 1000 -HashBudget ([int64]1048576) -RecoverDir $rec
    $ds = $scan.deep_scan
    $idx = @(@($scan.index_files) | Where-Object { $_.path.EndsWith('ARCHIVE_MANIFEST.csv') })
    $zipHit = @()
    if ($idx.Count -eq 1) { $zipHit = @(@($idx[0].hits) | Where-Object { $_.label -eq 'R4R9_ORIGINAL_ZIP' }) }
    Add-CslCheck 'HD2_INDEX_HIT_ZIP_SHA' ($zipHit.Count -eq 1 -and $zipHit[0].occurrences -eq 1) ([string]$zipHit.Count)
    $kh = @(@($ds.known_hits) | Where-Object { $_.label -eq 'SYNTHETIC_TARGET_RENAMED' })
    Add-CslCheck 'HD2_CONTENT_HIT_RENAMED_FILE' ($kh.Count -eq 1) ([string]$kh.Count)
    Add-CslCheck 'HD2_NAME_CANDIDATE' (@($ds.name_candidates).Count -eq 1 -and $ds.name_candidates[0].name -eq 'PREP_PERSEU_R4R9_C2_TELEMETRY_V004.py') ([string]@($ds.name_candidates).Count)
    $okRec = @(@($ds.recovered) | Where-Object { $_.status -eq 'RECOVERED_SHA_VERIFIED' })
    Add-CslCheck 'HD2_RECOVERY_SHA_VERIFIED' ($okRec.Count -eq 2 -and @([System.IO.Directory]::GetFiles($rec)).Count -eq 2) ([string]$okRec.Count)
    Add-CslCheck 'HD2_SOURCE_UNCHANGED' ((Get-FileHash -LiteralPath $renamed -Algorithm SHA256).Hash.ToUpperInvariant() -eq $synthSha) 'SOURCE_SHA_STABLE'
    if ($hdLinkMade) { Add-CslCheck 'HD2_LINK_NOT_FOLLOWED' (@($ds.not_followed).Count -eq 1 -and $ds.files_scanned -eq 3) ([string]@($ds.not_followed).Count + '/' + $ds.files_scanned) }
    else { Add-CslCheck 'HD2_LINK_NOT_FOLLOWED' ($ds.files_scanned -eq 3) 'SKIPPED_LINK_NOT_CREATABLE' }
    $g2 = Get-CslHd2Gate -Scan $scan
    Add-CslCheck 'HD2_GATE_FAIL_CLOSED' ($g2.C2_SOURCE_GATE -eq 'BLOCKED' -and $g2.blockers.Count -ge 7) ([string]$g2.blockers.Count)
    $scanB = Invoke-CslHd2Scan -ArchiveRoot $arch -Deep $true -KnownMap $map -EntryLimit 1000 -HashBudget ([int64]0) -RecoverDir $null
    Add-CslCheck 'HD2_BUDGET_EXHAUSTION_REPORTED' ($scanB.deep_scan.files_not_hashed_budget -eq 3 -and @($scanB.deep_scan.known_hits).Count -eq 0 -and (@((Get-CslHd2Gate -Scan $scanB).blockers) -contains 'HD2_FILES_NOT_HASHED_BUDGET_3')) ([string]$scanB.deep_scan.files_not_hashed_budget)
    $scanT = Invoke-CslHd2Scan -ArchiveRoot $arch -Deep $true -KnownMap $map -EntryLimit 2 -HashBudget ([int64]1048576) -RecoverDir $null
    Add-CslCheck 'HD2_TRUNCATION_REPORTED' ($scanT.deep_scan.truncated -and (@((Get-CslHd2Gate -Scan $scanT).blockers) -contains 'HD2_SCAN_TRUNCATED')) ([string]$scanT.deep_scan.truncated)
    $scanM = Invoke-CslHd2Scan -ArchiveRoot ([System.IO.Path]::Combine($fx, 'HD2_ABSENT')) -Deep $false -KnownMap $map -EntryLimit 10 -HashBudget ([int64]1) -RecoverDir $null
    Add-CslCheck 'HD2_ARCHIVE_ABSENT_BLOCKED' ((-not $scanM.exists) -and (@((Get-CslHd2Gate -Scan $scanM).blockers) -contains 'HD2_ARCHIVE_ROOT_MISSING')) ([string]$scanM.exists)
    $allPass = $true
    foreach ($c in $checks) { if (-not $c.pass) { $allPass = $false } }
    return [pscustomobject][ordered]@{ pass = $allPass; checks = $checks.ToArray(); offline_attribute_supported = $offlineSupported; link_kind = $linkKind; fixture = $fx; fixture_lifecycle = 'PRESERVE_RUN_OWNED_EVIDENCE_NOT_AUTO_DELETED'; located = $loc; gate = $gate }
}

# ------------------------------------------------------------------ main
$exitCode = 2
$finalResult = 'BLOCKED'
$finalReason = $null
$startedAt = Get-CslTimestamp
$runId = $null
$wrapperPath = $null
$wrapperSha = $null
$edition = 'UNKNOWN'
$psVer = $null
$body = $null
$gateOut = $null
$resultPath = $null
$resultSha = $null
$script:TryCompleted = $false
$script:Caught = $false
$script:Interrupted = $false

try {
    Write-Host $ResultContext
    $script:Phase = 'ENVIRONMENT_GATES'
    if ($env:OS -ne 'Windows_NT') { Stop-CslBlocked -Reason 'WINDOWS_TARGET_REQUIRED' }
    $edition = 'Desktop'
    $editionProp = $PSVersionTable.PSObject.Properties['PSEdition']
    if ($null -ne $editionProp) { $edition = [string]$editionProp.Value }
    $psVer = $PSVersionTable.PSVersion
    if ($edition -ne 'Desktop' -or $psVer.Major -ne 5 -or $psVer.Minor -ne 1) {
        Stop-CslBlocked -Reason ('WINDOWS_POWERSHELL_51_DESKTOP_REQUIRED:' + $edition + ':' + $psVer.ToString())
    }
    if ([string]::IsNullOrEmpty($PSCommandPath)) { Stop-CslBlocked -Reason 'LAUNCH_WITH_DASH_FILE_REQUIRED' }
    $wrapperPath = $PSCommandPath
    $wrapperSha = (Get-FileHash -LiteralPath $wrapperPath -Algorithm SHA256).Hash.ToUpperInvariant()
    if (-not [System.IO.Directory]::Exists($OneDriveDownloads)) { Stop-CslBlocked -Reason ('CANONICAL_DOWNLOADS_MISSING:' + $OneDriveDownloads) }

    $script:Phase = 'RUN_DIR'
    $runId = (Get-Date).ToString('yyyyMMdd_HHmmss_fff', $Invariant) + '_' + $PID
    if (-not [System.IO.Directory]::Exists($EvidenceRoot)) { [void][System.IO.Directory]::CreateDirectory($EvidenceRoot) }
    $runDirCandidate = [System.IO.Path]::Combine($EvidenceRoot, ($Mode.ToUpperInvariant() + '_' + $runId))
    if ([System.IO.Directory]::Exists($runDirCandidate) -or [System.IO.File]::Exists($runDirCandidate)) { Stop-CslBlocked -Reason 'RUN_DIR_PREEXISTS' }
    [void][System.IO.Directory]::CreateDirectory($runDirCandidate)
    $script:RunDir = $runDirCandidate
    $script:LogPath = [System.IO.Path]::Combine($script:RunDir, 'RUN_LOG.txt')
    Write-CslLog ('REVISION=' + $Revision + ' MODE=' + $Mode + ' RUN_ID=' + $runId)
    Write-CslLog ('WRAPPER=' + $wrapperPath + ' WRAPPER_SHA256=' + $wrapperSha)
    Write-CslLog ('RUN_DIR=' + $script:RunDir)
    Write-CslLog 'PROTECTED_EFFECTS=NONE READ_ONLY=YES C2_FULL_STARTED=NO SOURCE_DELETE=NO'

    if ($Mode -eq 'SelfTest') {
        $script:Phase = 'SELFTEST'
        $body = Invoke-CslSelfTest
        $gateOut = $body.gate
        if ($body.pass) { $finalResult = 'PASS_SELFTEST_ONLY'; $finalReason = 'ALL_SYNTHETIC_CHECKS_PASS'; $exitCode = 0 }
        else { $finalReason = 'SELFTEST_CHECK_FAILED' }
    } elseif ($Mode -eq 'Locate') {
        $script:Phase = 'LOCATE'
        $body = Invoke-CslLocate -PrimaryRoot $OneDriveDownloads -SecondaryRoot $LegacyDownloads -RunsRoot $PerseuRuns
        $gateOut = Get-CslGate -Located $body
        $finalResult = 'PASS_INVENTORY_ONLY'
        $finalReason = 'INVENTORY_COMPLETED_SEE_C2_SOURCE_GATE'
        $exitCode = 0
    } else {
        $script:Phase = 'HD2_BINDING'
        $hd2 = Get-CslHd2Binding
        $archive = [System.IO.Path]::Combine(($hd2.letter + ':\'), $Hd2ArchiveRel)
        $mediaId = [System.IO.Path]::Combine(($hd2.letter + ':\'), 'ARQUIVO_FRIO\00_AF2_MEDIA_IDENTITY.json')
        $mediaItem = $null
        if (Test-Path -LiteralPath $mediaId -PathType Leaf) { $mediaItem = Measure-CslItem -Item (Get-Item -LiteralPath $mediaId -Force) }
        $script:Phase = $Mode.ToUpperInvariant()
        $deep = ($Mode -eq 'HD2Deep')
        $recover = $null
        if ($deep) { $recover = [System.IO.Path]::Combine($script:RunDir, 'RECOVERED') }
        $scan = Invoke-CslHd2Scan -ArchiveRoot $archive -Deep $deep -KnownMap $KnownSha -EntryLimit $DeepEntryLimit -HashBudget $DeepHashBudget -RecoverDir $recover
        $body = [pscustomobject][ordered]@{ hd2_binding = $hd2; media_identity_file = $mediaItem; scan = $scan }
        $gateOut = Get-CslHd2Gate -Scan $scan
        $finalResult = 'PASS_INVENTORY_ONLY'
        $finalReason = 'HD2_SCAN_COMPLETED_SEE_C2_SOURCE_GATE'
        $exitCode = 0
    }
    $script:TryCompleted = $true
} catch {
    $script:Caught = $true
    $msg = [string]$_.Exception.Message
    $finalResult = 'BLOCKED'
    if ($msg.StartsWith('BLOCKED:', [System.StringComparison]::Ordinal)) { $finalReason = $msg.Substring(8) }
    else { $finalReason = 'UNEXPECTED_' + $_.Exception.GetType().FullName + ':' + $msg }
    $exitCode = 2
    try { Write-CslLog ('ERROR PHASE=' + $script:Phase + ' REASON=' + $finalReason) } catch { Write-Host ('ERROR PHASE=' + $script:Phase + ' REASON=' + $finalReason) }
} finally {
    if (-not $script:TryCompleted -and -not $script:Caught) {
        # Pipeline stopped (Ctrl+C): read-only scan, SAFE_STOP; never report the initial values.
        $script:Interrupted = $true
        $finalResult = 'SAFE_STOP'
        $finalReason = 'WRAPPER_INTERRUPTED_CTRL_C_READ_ONLY'
        $exitCode = 130
    }
    if ($null -ne $script:RunDir) {
        try {
            $script:Phase = 'RESULT_WRITE'
            $doc = [ordered]@{
                schema = 'PERSEU_C2_SOURCE_LOCATOR_V002_RESULT'
                PROJECT = $ProjectName; THREAD = $ThreadName; REVISION = $Revision
                POLICY_MASTER_SHA256_AT_BUILD = $PolicyMasterSha256
                MODE = $Mode; RUN_ID = $runId; started_at = $startedAt; finished_at = (Get-CslTimestamp)
                RESULT = $finalResult; REASON = $finalReason; EXIT_CODE = $exitCode; LAST_PHASE = $script:Phase
                powershell = ($edition + ' ' + [string]$psVer); os = [System.Environment]::OSVersion.VersionString
                wrapper_path = $wrapperPath; wrapper_sha256 = $wrapperSha
                hash_budget_used_bytes = $script:HashBudgetUsed
                C2_SOURCE_GATE = $(if ($null -ne $gateOut) { $gateOut.C2_SOURCE_GATE } else { 'NOT_EVALUATED' })
                c2_blockers = $(if ($null -ne $gateOut) { $gateOut.blockers } else { $null })
                body = $body
                INTERRUPTED = $script:Interrupted
                PROTECTED_EFFECTS = 'NONE'; READ_ONLY = 'YES'; SOURCE_DELETE = 'NO'; C2_FULL_STARTED = 'NO'
                EVIDENCE_WRITES_ROOT = $script:RunDir; RESULT_RETURN_TO = $ResultFooter
            }
            $resultPath = [System.IO.Path]::Combine($script:RunDir, 'LOCATOR_RESULT_' + $Mode.ToUpperInvariant() + '.json')
            Write-CslNewText -LiteralPath $resultPath -Text (ConvertTo-Json -InputObject $doc -Depth 10)
            $resultSha = (Get-FileHash -LiteralPath $resultPath -Algorithm SHA256).Hash.ToUpperInvariant()
        } catch {
            $exitCode = 2
            $finalReason = 'RESULT_WRITE_FAILED:' + [string]$_.Exception.Message + ' PRIMARY=' + $finalReason
            $finalResult = 'BLOCKED'
            try { Write-CslLog ('RESULT_WRITE_FAILED ' + [string]$_.Exception.Message) } catch { Write-Host 'RESULT_WRITE_FAILED' }
        }
    }
    try {
        Write-CslLog '=== SUMMARY ==='
        Write-CslLog ('RESULT=' + $finalResult)
        Write-CslLog ('REASON=' + $finalReason)
        Write-CslLog ('EXIT_CODE=' + $exitCode)
        Write-CslLog ('MODE=' + $Mode)
        if ($null -ne $gateOut) {
            Write-CslLog ('C2_SOURCE_GATE=' + $gateOut.C2_SOURCE_GATE)
            foreach ($bl in $gateOut.blockers) { Write-CslLog ('C2_BLOCKER=' + $bl) }
        }
        Write-CslLog ('RUN_DIR=' + $script:RunDir)
        Write-CslLog ('RESULT_JSON=' + $resultPath)
        Write-CslLog ('RESULT_JSON_SHA256=' + $resultSha)
        Write-CslLog ('WRAPPER_SHA256=' + $wrapperSha)
        Write-CslLog 'PROTECTED_EFFECTS=NONE'
        Write-CslLog $ResultFooter
    } catch {
        Write-Host $ResultFooter
    }
    if ($script:Interrupted -and ([System.Environment]::CommandLine -match '(?i)\s-File\s')) {
        [System.Environment]::Exit($exitCode)
    }
}
exit $exitCode
