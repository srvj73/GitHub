
param (
    [switch]$FirstAdmission,
    [switch]$ResumeAdmittedRun,
    [string]$FinalCodeManifestPath = '',
    [string]$FinalCodeManifestSha = '',
    [string]$CompletenessReceiptPath = '',
    [string]$B07ReceiptPath = '',
    [string]$FirstAdmissionReviewPackPath = '',
    [string]$PredecessorEvidenceDir = '',
    [string]$RunAuthoritySha = '',
    [switch]$PrepareFirstAdmission,
    [switch]$ObserveNative,
    [string]$PolicyRoot = '',
    [string]$OriginCapturePath = '',
    [string]$OriginReconciliationSha256 = '',
    [string]$PreparationBindingSha = '',
    [string]$EvidenceDir = '',
    [string]$PreparationInstanceId = '',
    [string]$PreparationPython = 'C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe',
    [string]$PreparationResumeRoot = 'D:\Base CSV\Scripts\TICKSTORE_R9_DEV\TICKSTORE_D4_RESUMABLE_V002R22',
    [switch]$ExecuteD4,
    [switch]$RequestSafeStop,
    [switch]$ElevatedChild,
    [switch]$ResumeAfterSafeStop,
    [switch]$RuntimeProbe,
    [switch]$RuntimeProbeChild,
    [string]$RuntimeProbeReviewPackPath = '',
    [int]$ProbeExitCode = 7,
    [string]$ReviewVerdictPath = '',
    [string]$GcaRecoveryReceiptPath = '',
    [string]$PolicyAdmissionReceiptPath = '',
    [string]$OriginalCwd = '',
    [string]$ChildResultPath = '',
    [string]$AdapterDir = '',
    [string]$AdapterBindingSha = '',
    [string]$AdmittedOwnerGatePath = '',
    [string]$AdmittedOwnerGateSha = ''
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'Continue'

# Operational admission requires explicit mode and final technical gates.
if (($FirstAdmission -and $ResumeAdmittedRun) -or (($FirstAdmission -or $ResumeAdmittedRun) -and (-not $ExecuteD4 -or $PrepareFirstAdmission -or $RequestSafeStop))) {
    Write-Host 'BLOCKED|FIRST_ADMISSION_MODE_CONFLICT';exit 2
}
if ($ElevatedChild -or $RuntimeProbe -or $RuntimeProbeChild -or ($ExecuteD4 -and -not ($FirstAdmission -or $ResumeAdmittedRun)) -or ($ResumeAfterSafeStop -and -not $ResumeAdmittedRun)) {
    Write-Host 'BLOCKED|FINAL_B06_B07_AND_INSTANCE_EXECUTION_INTEGRATION_PENDING';exit 2
}
# R45 G6: D4 effects run only in an already elevated process (RUN_TICKSTORE_FULL.ps1 elevates before
# dispatching). Checked before any admission boundary, so a non-elevated call never has an effect.
if ($ExecuteD4 -and -not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'BLOCKED|ELEVATION_REQUIRED_USE_RUN_TICKSTORE_FULL_PS1';exit 2
}
if ($RequestSafeStop -and ($RunAuthoritySha -cnotmatch '^[0-9A-F]{64}$')) {
    Write-Host 'BLOCKED|SAFE_STOP_EXISTING_AUTHORITY_SHA_REQUIRED';exit 2
}
if ($PrepareFirstAdmission) {
    try {
        if ($PreparationBindingSha -cnotmatch '^[0-9A-F]{64}$') { throw 'PREPARATION_BINDING_SHA_REQUIRED' }
        $bindingPath = Join-Path $PSScriptRoot 'FIRST_ADMISSION_BINDING.json'
        $bindingBytes = [IO.File]::ReadAllBytes($bindingPath)
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $actual = [BitConverter]::ToString($hash.ComputeHash($bindingBytes)).Replace('-','') } finally { $hash.Dispose() }
        if ($actual -cne $PreparationBindingSha) { throw 'PREPARATION_BINDING_SHA' }
        $binding = [Text.Encoding]::UTF8.GetString($bindingBytes) | ConvertFrom-Json
        $prepScript = Join-Path $PSScriptRoot 'D4_FIRST_ADMISSION_PREP.py'
        $scriptBytes = [IO.File]::ReadAllBytes($prepScript)
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $actual = [BitConverter]::ToString($hash.ComputeHash($scriptBytes)).Replace('-','') } finally { $hash.Dispose() }
        if ($actual -cne $binding.preparation_sha256) { throw 'PREPARATION_SCRIPT_SHA' }
        if ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash -cne $binding.wrapper_sha256) { throw 'PREPARATION_WRAPPER_SHA' }
        if ((Get-FileHash -LiteralPath $PreparationPython -Algorithm SHA256).Hash -cne '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9') { throw 'PREPARATION_PYTHON_SHA' }
        if ([string]::IsNullOrWhiteSpace($PolicyRoot) -or [string]::IsNullOrWhiteSpace($OriginCapturePath)) { throw 'TECHNICAL_POLICYROOT_AND_ORIGIN_REQUIRED' }
        if ($OriginReconciliationSha256 -cnotmatch '^[0-9A-F]{64}$') { throw 'ORIGIN_POLICY_RECONCILIATION_SHA_REQUIRED' }
        if ([string]::IsNullOrWhiteSpace($EvidenceDir)) { throw 'NEW_EVIDENCE_DIRECTORY_REQUIRED' }
        $target = [IO.Path]::GetFullPath($EvidenceDir)
        $userBase = [IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd('\') + '\'
        if (-not $target.StartsWith($userBase,[StringComparison]::OrdinalIgnoreCase) -or $target.StartsWith('D:',[StringComparison]::OrdinalIgnoreCase)) { throw 'EVIDENCE_MUST_BE_UNDER_USERPROFILE_NOT_D' }
        if (Test-Path -LiteralPath $target) { throw 'EVIDENCE_DIRECTORY_PREEXISTS' }
        $parent = [IO.Directory]::GetParent($target)
        if (-not $parent.Exists) { throw 'EVIDENCE_PARENT_MISSING' }
        while ($null -ne $parent) {
            if (($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'EVIDENCE_PARENT_REPARSE' }
            $parent = $parent.Parent
        }
        if ([string]::IsNullOrWhiteSpace($PreparationInstanceId)) { $PreparationInstanceId = [Guid]::NewGuid().ToString('D') }
        $runtime = Split-Path -Parent $PSScriptRoot
        $bootstrap = 'import base64,sys;sys.argv=sys.argv[1:];__file__=sys.argv[0];exec(compile(base64.b64decode(sys.stdin.buffer.read().strip(),validate=True),__file__,"exec"))'
        $argsPrep = @('-I','-S','-B','-c',$bootstrap,$prepScript,'--policy-root',$PolicyRoot,'--policy-reconciliation',$OriginCapturePath,'--policy-reconciliation-sha256',$OriginReconciliationSha256,
            '--package',(Join-Path $runtime 'recovery'),'--adapter-dir',(Join-Path $runtime 'adapter'),
            '--resume-root',$PreparationResumeRoot,'--instance-id',$PreparationInstanceId,'--binding-sha',$PreparationBindingSha)
        if ($ObserveNative) { $argsPrep += '--observe-native' }
        # Directory reserved with CreateDirectory then exclusive receipt; it is
        # never reused as a successful observation or operational authority.
        New-Item -ItemType Directory -Path $target -ErrorAction Stop | Out-Null
        $output = [Convert]::ToBase64String($scriptBytes) | & $PreparationPython @argsPrep
        $code = $LASTEXITCODE
        $text = ($output -join "`n") + "`n"
        $report = $text | ConvertFrom-Json
        if ($null -eq $code -or $null -eq $report.execution_allowed -or $report.execution_allowed -ne $false) { throw 'PREPARATION_RESULT_INVALID' }
        $path = Join-Path $target 'PREPARATION.json'
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($text)
        $f = New-Object IO.FileStream($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $f.Write($bytes,0,$bytes.Length); $f.Flush($true) } finally { $f.Dispose() }
        Write-Host ('PREPARATION_STATUS=' + $report.status)
        Write-Host ('EVIDENCE=' + $path)
        Write-Host 'RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressao De Ticks 14'
        exit ([int]$code)
    } catch {
        Write-Host ('SAFE_STOP|PREPARATION_BLOCKED|' + $_.Exception.Message)
        exit 2
    }
}
if (($ObserveNative -or -not [string]::IsNullOrWhiteSpace($PolicyRoot)) -and -not ($FirstAdmission -or $ResumeAdmittedRun)) {
    Write-Host 'BLOCKED|USE_PREPARE_FIRST_ADMISSION'; exit 2
}

# Historical receipt provenance required byte-for-byte by the frozen release engine (ABI,
# not routing); the current policy identity is bound by POLICY_CAPTURE_BINDING (R44-B2C).
$Project = 'PEGASUS_TICKSTORE'
$Thread = 'Compress' + [char]0x00E3 + 'o De Ticks 7'
$ResultProject='Base de Dados CSV / Tickstore'
$ResultThread='Compress'+[char]0x00E3+'o De Ticks 15'
$Python='C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$ResumeRoot = 'D:\Base CSV\Scripts\TICKSTORE_R9_DEV\TICKSTORE_D4_RESUMABLE_V002R22'
$CheckpointRoot = Join-Path $ResumeRoot 'checkpoint'
$StatusPath = Join-Path $ResumeRoot 'D4_STATUS.json'
$StopFile = Join-Path $ResumeRoot 'STOP.request'
$AuthorityRoot = Join-Path $ResumeRoot 'authority'
$RunAuthorityPath = Join-Path $AuthorityRoot 'RUN_AUTHORITY.json'
$SuccessorRoot = Join-Path $ResumeRoot 'SUCCESSOR_PACKAGE'
$ArtifactsRoot = Join-Path $ResumeRoot 'artifacts'
$SuccessorZip = Join-Path $ArtifactsRoot 'TICKSTORE_V004R1_D4_RESUMABLE_V002R22_PACKAGE.zip'
$ReviewPack = Join-Path $ArtifactsRoot 'TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R22.zip'
$ControlRoot = 'D:\Base CSV\Scripts\TICKSTORE_R9_DEV\WORK_R9_PUBLISHER_RECOVERY_V004R1R1\ORCHESTRATOR_V001R9R1_B6_R8_PROVENANCE_VSS_SCOPE_FIX'
$StatePath = Join-Path $ControlRoot 'state\STATE.json'
$RunsRoot = Join-Path $ControlRoot 'runs'
# R44-B2C: no historical administrative gate is named here; the technical descriptor path and
# digest are always taken from the admitted RUN_AUTHORITY before use.
$OwnerGatePath = ''
$ExpectedBaseReleaseSha = '82FA3A22E6AA7BC306E0544F2FE7EE250B96BBE305A6D1593911E3641CE888C7'
$ExpectedReleaseSha = 'BFC44DA9A375ED565D8DA2DA7E34EC376C25DEAFE15ED2F3C063CE635CEBCD4C'
$ExpectedCandidateSha = 'E998032478EA1FAB8BD69FF000D9622749B679058F457A927D5854963208E310'
$ExpectedOrchestratorSha = '9EB509A2A82C0BE6D4C7AEF315AAF6B41348CECE64AB502061116DFC74419DDA'
$ExpectedConfigSha = 'B67527C0E78E896BF4F4128BF02CC3968CA1AE00F2A8449DB7DBD1E583785515'
$ExpectedCodeManifestSha = '60FE88C92BDBD95884DF3258C739855AF870F4A4D58B40301BF8E5E1786C579D'
$ExpectedPackageManifestSha = '5199C7B03A442F0D33C1250E3E2A68A5A213377E012A902336502453CAAA18D6'
$ExpectedPackageZipSha = '4BC28843012A059F65237E07780B79D158190A661B16FFD520861A3F092C3062'
$ExpectedOwnerGateSha = ''
$ExpectedMasterScriptSha = '18900BCC198347A5912AA4CEC23F4D9E7A2513FC41EBE393BFD8151F9EEF259A'
$ArtifactBaseMasterSha = 'C7697B1798A02DF2CF128B2A28247182C8D36A9924C52A0844BCDDE66B956AE1'
$ArtifactBaseHeadSha = '7B4C0654F45D7E3A2170A33E9453D8D0593D00E127ECB60CF497DFEB5CC72601'
$ArtifactBaseRevisionId = '20261001T160551-0300-C7697B1798A02DF2'
$ExpectedTotalChunks = 1399
$HeartbeatSeconds = 30
$ProgressBaselineCommitted = 0
$ExpectedScratchGrowthBytes = [int64]0
$ExpectedOutputGrowthBytes = [int64]$ExpectedTotalChunks * [int64]2097152 + [int64]67108864
$FreeSpaceHeadroomBytes = [int64]4294967296

Add-Type -AssemblyName System.Security

function Require([bool]$Condition,[string]$Reason){if (-not $Condition){throw ('BLOCKED|' + $Reason)}}
function Get-Prop([AllowNull()]$Object,[string]$Name){
    if ($null -eq $Object){return $null}
    if ($Object -is [System.Collections.IDictionary]){if ($Object.Contains($Name)){return $Object[$Name]};return $null}
    $p=$Object.PSObject.Properties[$Name];if ($null -eq $p){return $null};return $p.Value
}
function Get-Sha([string]$Path){
    Require (Test-Path -LiteralPath $Path -PathType Leaf) ('FILE_MISSING|' + $Path)
    $stream=[IO.File]::OpenRead($Path);$hash=[Security.Cryptography.SHA256]::Create()
    try {return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','')}
    finally {$hash.Dispose();$stream.Dispose()}
}
function Validate-AdapterBinding {
    Require (-not [string]::IsNullOrWhiteSpace($AdapterDir)) 'ADAPTER_DIRECTORY_REQUIRED'
    Require ($AdapterBindingSha -cmatch '^[0-9A-F]{64}$') 'ADAPTER_EXTERNAL_BINDING_SHA_REQUIRED'
    $bindingPath=Join-Path $AdapterDir 'RUNTIME_LOCATOR_ADAPTER_BINDING.json'
    Require ((Get-Sha $bindingPath) -ceq $AdapterBindingSha) 'ADAPTER_EXTERNAL_BINDING_SHA'
    $binding=Read-Json $bindingPath
    Require ([string](Get-Prop $binding 'schema') -ceq 'TICKSTORE_G_CA_RUNTIME_LOCATOR_ADAPTER_BINDING_V002') 'ADAPTER_BINDING_SCHEMA'
    foreach($pair in @(@('adapter_sha256','runtime_locator_adapter.py'),@('inline_entry_sha256','runtime_locator_inline_entry.py'),@('orchestrator_entry_sha256','runtime_locator_orchestrator_entry.py'),@('adapted_loader_sha256','INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1'),@('adapted_launch_sha256','Launch-TickstoreBundle-Adapter.ps1'))){
        Require ((Get-Sha (Join-Path $AdapterDir $pair[1])) -ceq [string](Get-Prop $binding $pair[0])) ('ADAPTER_COMPONENT_SHA|'+$pair[1])
    }
    Require ([string](Get-Prop $binding 'frozen_release_sha256') -ceq $ExpectedReleaseSha) 'ADAPTER_FROZEN_RELEASE'
    Require ([string](Get-Prop $binding 'frozen_orchestrator_sha256') -ceq $ExpectedOrchestratorSha) 'ADAPTER_FROZEN_ORCHESTRATOR'
    return $binding
}
function Assert-OrchestratorIdentity([string]$Path){Require ((Get-Sha $Path) -ceq $ExpectedOrchestratorSha) 'SUCCESSOR_ORCHESTRATOR_SHA'}
function Read-Json([string]$Path){return ([IO.File]::ReadAllText($Path,[Text.Encoding]::UTF8) | ConvertFrom-Json)}
function Is-Admin{$id=[Security.Principal.WindowsIdentity]::GetCurrent();$p=New-Object Security.Principal.WindowsPrincipal($id);return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)}
function Write-AtomicBytes([string]$Path,[byte[]]$Bytes){
    $dir=[IO.Path]::GetDirectoryName($Path);if (-not (Test-Path -LiteralPath $dir -PathType Container)){New-Item -ItemType Directory -Path $dir -Force|Out-Null}
    $tmp=$Path+'.tmp.'+$PID+'.'+[Guid]::NewGuid().ToString('N')
    try {
        $fs=New-Object IO.FileStream($tmp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {$fs.Write($Bytes,0,$Bytes.Length);$fs.Flush($true)}finally {$fs.Dispose()}
        if (Test-Path -LiteralPath $Path -PathType Leaf){[IO.File]::Replace($tmp,$Path,[System.Management.Automation.Language.NullString]::Value)}else {[IO.File]::Move($tmp,$Path)}
        $committed=New-Object IO.FileStream($Path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
        try {$committed.Flush($true)}finally {$committed.Dispose()}
    }finally {if (Test-Path -LiteralPath $tmp -PathType Leaf){Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue}}
}
function Write-AtomicJson([string]$Path,$Object){$json=($Object|ConvertTo-Json -Depth 32 -Compress)+"`n";$enc=New-Object Text.UTF8Encoding($false);Write-AtomicBytes $Path ($enc.GetBytes($json))}
function Write-ChildResult([string]$Status,[int]$ExitCode,[string]$PrimaryError){
    if ([string]::IsNullOrWhiteSpace($ChildResultPath)){return }
    $obj=[ordered]@{schema='TICKSTORE_D4_RESUME_EFFECTFUL_V002R22_CHILD_RESULT';status=$Status;exit_code=$ExitCode;primary_error=$PrimaryError;pid=$PID;written_at=[DateTimeOffset]::Now.ToString('o')}
    Write-AtomicJson $ChildResultPath $obj
}
function Quote-NativeArg([string]$Value){
    Require ($Value.IndexOf([char]34) -lt 0) ('NATIVE_ARG_CONTAINS_QUOTE|' + $Value)
    $trailing=([regex]::Match($Value,'\\+$')).Value
    return ([char]34 + $Value + $trailing + [char]34)
}
function Parse-Verdict([string]$Path){
    Require (Test-Path -LiteralPath $Path -PathType Leaf) 'REVIEW_VERDICT_MISSING'
    $map=@{};$headers=New-Object 'System.Collections.Generic.List[string]'
    foreach ($raw in Get-Content -LiteralPath $Path){
        $line=[string]$raw;$line=$line.Trim();if ([string]::IsNullOrWhiteSpace($line)){continue}
        if ($line -notmatch '='){[void]$headers.Add($line);continue}
        if ($line -notmatch '^([A-Z0-9_]+)=(.*)$'){throw 'BLOCKED|REVIEW_VERDICT_KEY_FORMAT'}
        $k=$Matches[1];$val=$Matches[2]
        Require (-not $map.ContainsKey($k)) ('REVIEW_VERDICT_DUPLICATE|' + $k)
        $map[$k]=$val
    }
    Require ($headers.Count -eq 1 -and [string]$headers[0] -ceq 'TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R22') 'REVIEW_VERDICT_HEADER'
    $required=@('VERDICT','INDEPENDENT_REVIEW','REVIEW_PACK_SHA256','BASE_RELEASE_SHA256','SUCCESSOR_RELEASE_SHA256','SUCCESSOR_CANDIDATE_SHA256','EFFECTFUL_WRAPPER_SHA256','TESTED_CODE_EQUALS_PACKAGED_CODE','CANDIDATE_RELEASE_FUSE_ONLY','CERTIFY_SCRATCH_FINAL_SEMANTICS_PRESERVED','RESUME_ATTESTATION_AUTHORITY','RUNTIME_IDENTITY_BINDING','CHECKPOINT_ATOMIC_DURABLE','CHECKPOINT_RECONCILIATION','COMMITTED_REVALIDATION','SAFE_STOP_COOPERATIVE','EFFECTFUL_WRAPPER_D4_ONLY','RESUME_CHUNK_UNIT','AUTO_KILL_DELTA','RUN_AUTHORITY_SINGLE_ATOMIC_FILE','CTRL_C_STOP_DURABLE','LONG_RUNNER_OBSERVABILITY','POLICY_ADMISSION_BINDING','SUPPORT_TOPOLOGY_REPRODUCIBLE','NESTED_EXIT_PROPAGATION','THREAD_ROUTING_IDENTITY','D4_RESUME_AUTHORIZED','D5_AUTHORIZED','FULL_AUTHORIZED','CRITICAL_FINDINGS','MAJOR_FINDINGS')
    Require ($map.Count -eq $required.Count) ('REVIEW_VERDICT_KEY_COUNT|' + $map.Count)
    foreach ($k in $required){Require ($map.ContainsKey($k)) ('REVIEW_VERDICT_KEY_MISSING|' + $k)}
    return $map
}
function Validate-ReviewVerdict([string]$Path){
    $v=Parse-Verdict $Path
    $values=[ordered]@{
        VERDICT='PASS';INDEPENDENT_REVIEW='YES';TESTED_CODE_EQUALS_PACKAGED_CODE='YES';CANDIDATE_RELEASE_FUSE_ONLY='PASS';CERTIFY_SCRATCH_FINAL_SEMANTICS_PRESERVED='YES';
        RESUME_ATTESTATION_AUTHORITY='PASS';RUNTIME_IDENTITY_BINDING='PASS';CHECKPOINT_ATOMIC_DURABLE='PASS';CHECKPOINT_RECONCILIATION='PASS';COMMITTED_REVALIDATION='PASS';
        SAFE_STOP_COOPERATIVE='PASS';EFFECTFUL_WRAPPER_D4_ONLY='PASS';RESUME_CHUNK_UNIT='DATE_KEY';AUTO_KILL_DELTA='NO';RUN_AUTHORITY_SINGLE_ATOMIC_FILE='PASS';
        CTRL_C_STOP_DURABLE='PASS';LONG_RUNNER_OBSERVABILITY='PASS';POLICY_ADMISSION_BINDING='PASS';SUPPORT_TOPOLOGY_REPRODUCIBLE='PASS';NESTED_EXIT_PROPAGATION='PASS';THREAD_ROUTING_IDENTITY='PASS';
        D4_RESUME_AUTHORIZED='YES';D5_AUTHORIZED='NO';FULL_AUTHORIZED='NO';CRITICAL_FINDINGS='0';MAJOR_FINDINGS='0'
    }
    foreach ($k in $values.Keys){Require ([string]$v[$k] -ceq [string]$values[$k]) ('REVIEW_VERDICT_FIELD|' + $k)}
    Require ([string]$v['REVIEW_PACK_SHA256'] -ceq (Get-Sha $ReviewPack)) 'REVIEW_PACK_SHA'
    Require ([string]$v['BASE_RELEASE_SHA256'] -ceq $ExpectedBaseReleaseSha) 'REVIEW_BASE_RELEASE_SHA'
    Require ([string]$v['SUCCESSOR_RELEASE_SHA256'] -ceq $ExpectedReleaseSha) 'REVIEW_RELEASE_SHA'
    Require ([string]$v['SUCCESSOR_CANDIDATE_SHA256'] -ceq $ExpectedCandidateSha) 'REVIEW_CANDIDATE_SHA'
    Require ([string]$v['EFFECTFUL_WRAPPER_SHA256'] -ceq (Get-Sha $PSCommandPath)) 'REVIEW_WRAPPER_SHA'
    return $v
}
function Validate-PolicyAdmission([string]$Path,[string]$ReviewVerdictSha){
    Require (Test-Path -LiteralPath $Path -PathType Leaf) 'POLICY_ADMISSION_RECEIPT_MISSING'
    $p=Read-Json $Path
    Require ([string](Get-Prop $p 'schema') -ceq 'TICKSTORE_D4_POLICY_ADMISSION_RECEIPT_V001') 'POLICY_ADMISSION_SCHEMA'
    Require ([string](Get-Prop $p 'status') -ceq 'PASS') 'POLICY_ADMISSION_STATUS'
    Require ([string](Get-Prop $p 'project') -ceq $Project -and [string](Get-Prop $p 'thread') -ceq $Thread) 'POLICY_ADMISSION_ROUTING'
    Require ([string](Get-Prop $p 'origin_policy_reconciliation_sha256') -cmatch '^[0-9A-F]{64}$') 'POLICY_ADMISSION_RECONCILIATION'
    Require ([string](Get-Prop $p 'effect_scope') -ceq 'D4_ONLY') 'POLICY_ADMISSION_SCOPE'
    Require ([string](Get-Prop $p 'policy_source_cardinality') -ceq 'PASS_1_MASTER_PLUS_1_HEAD') 'POLICY_SOURCE_CARDINALITY'
    Require ([string](Get-Prop $p 'policy_head_state') -ceq 'FROZEN') 'POLICY_HEAD_STATE'
    Require ([string](Get-Prop $p 'artifact_base_master_sha256') -ceq $ArtifactBaseMasterSha) 'POLICY_ARTIFACT_BASE'
    $am=[string](Get-Prop $p 'active_master_sha256');$ah=[string](Get-Prop $p 'active_head_sha256')
    Require ($am -match '^[0-9A-F]{64}$' -and $ah -match '^[0-9A-F]{64}$') 'POLICY_ACTIVE_HASH_FORMAT'
    Require (-not [string]::IsNullOrWhiteSpace([string](Get-Prop $p 'active_revision_id'))) 'POLICY_ACTIVE_REVISION'
    Require ([string](Get-Prop $p 'material_delta_reconciled') -ceq 'YES' -and [string](Get-Prop $p 'material_delta_blocks_execution') -ceq 'NO') 'POLICY_DELTA_RECONCILIATION'
    Require ([string](Get-Prop $p 'review_pack_sha256') -ceq (Get-Sha $ReviewPack)) 'POLICY_REVIEW_PACK_SHA'
    Require ([string](Get-Prop $p 'review_verdict_sha256') -ceq $ReviewVerdictSha) 'POLICY_REVIEW_VERDICT_SHA'
    Require ([string](Get-Prop $p 'effectful_wrapper_sha256') -ceq (Get-Sha $PSCommandPath)) 'POLICY_WRAPPER_SHA'
    return $p
}
function Invoke-FirstAdmissionBoundary {
    Require (Is-Admin) 'FIRST_ADMISSION_NATIVE_ELEVATION_REQUIRED'
    Require ($PreparationBindingSha -cmatch '^[0-9A-F]{64}$') 'FIRST_ADMISSION_CODE_BINDING_SHA_REQUIRED'
    Require ($FinalCodeManifestSha -cmatch '^[0-9A-F]{64}$') 'FINAL_CODE_MANIFEST_SHA_REQUIRED'
    Require ($OriginReconciliationSha256 -cmatch '^[0-9A-F]{64}$') 'ORIGIN_POLICY_RECONCILIATION_SHA_REQUIRED'
    foreach($p in @($PolicyRoot,$OriginCapturePath,$CompletenessReceiptPath,$B07ReceiptPath,$FinalCodeManifestPath,$FirstAdmissionReviewPackPath,$ReviewVerdictPath,$PolicyAdmissionReceiptPath,$AdapterDir,$PredecessorEvidenceDir)) {
        Require (-not [string]::IsNullOrWhiteSpace($p)) 'FIRST_ADMISSION_REQUIRED_INPUT_MISSING'
    }
    $bindPath=Join-Path $PSScriptRoot 'FIRST_ADMISSION_BINDING.json'
    $bindBytes=[IO.File]::ReadAllBytes($bindPath)
    $hash=[Security.Cryptography.SHA256]::Create()
    try {$actual=[BitConverter]::ToString($hash.ComputeHash($bindBytes)).Replace('-','')}finally{$hash.Dispose()}
    Require ($actual -ceq $PreparationBindingSha) 'FIRST_ADMISSION_CODE_BINDING_SHA'
    $sealed=[Text.Encoding]::UTF8.GetString($bindBytes)|ConvertFrom-Json
    $bootstrapPath=Join-Path $PSScriptRoot 'D4_FIRST_ADMISSION_BOOTSTRAP.py'
    $bootstrapBytes=[IO.File]::ReadAllBytes($bootstrapPath)
    $hash=[Security.Cryptography.SHA256]::Create()
    try {$actual=[BitConverter]::ToString($hash.ComputeHash($bootstrapBytes)).Replace('-','')}finally{$hash.Dispose()}
    Require ($actual -ceq $sealed.bootstrap_sha256) 'FIRST_ADMISSION_BOOTSTRAP_SHA'
    Require ((Get-Sha $PSCommandPath) -ceq $sealed.wrapper_sha256) 'FIRST_ADMISSION_WRAPPER_SHA'
    Require ((Get-Sha $Python) -ceq '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9') 'PYTHON_SHA'
    $bootstrap='import base64,sys;sys.argv=sys.argv[1:];__file__=sys.argv[0];exec(compile(base64.b64decode(sys.stdin.buffer.read().strip(),validate=True),__file__,"exec"))'
    $mode='--admit-first';if ($ResumeAdmittedRun) {$mode='--validate-existing'}
    $argsAdmission=@('-I','-S','-B','-c',$bootstrap,$bootstrapPath,$mode,
      '--package',$SuccessorRoot,'--package-zip',$SuccessorZip,'--adapter-dir',$AdapterDir,'--resume-root',$ResumeRoot,
      '--binding-sha',$PreparationBindingSha,'--policy-root',$PolicyRoot,'--policy-reconciliation',$OriginCapturePath,'--policy-reconciliation-sha256',$OriginReconciliationSha256,
      '--final-code-manifest',$FinalCodeManifestPath,'--final-code-sha',$FinalCodeManifestSha,
      '--review-pack',$FirstAdmissionReviewPackPath,'--review-verdict',$ReviewVerdictPath,
      '--policy-receipt',$PolicyAdmissionReceiptPath,'--b07',$B07ReceiptPath,'--completeness',$CompletenessReceiptPath,
      '--predecessor-evidence',$PredecessorEvidenceDir)
    $output=[Convert]::ToBase64String($bootstrapBytes)|& $Python @argsAdmission
    $nativeExit=$LASTEXITCODE
    $result=($output -join "`n")|ConvertFrom-Json
    Require ($null -ne $nativeExit -and $nativeExit -eq 0) ('FIRST_ADMISSION_BLOCKED|'+[string](Get-Prop $result 'reason'))
    Require ([string](Get-Prop $result 'schema') -ceq 'TICKSTORE_FIRST_ADMISSION_BOOTSTRAP_RESULT_V001') 'FIRST_ADMISSION_RESULT_SCHEMA'
    Require ([string](Get-Prop $result 'authority_path') -ceq $RunAuthorityPath) 'FIRST_ADMISSION_AUTHORITY_PATH'
    Require ((Get-Sha $RunAuthorityPath) -ceq [string](Get-Prop $result 'authority_sha256')) 'FIRST_ADMISSION_AUTHORITY_SHA'
    $ra=Read-Json $RunAuthorityPath
    $script:OwnerGatePath=[string](Get-Prop $ra 'owner_gate_path')
    $script:ExpectedOwnerGateSha=[string](Get-Prop $ra 'owner_gate_sha256')
    $script:AdmittedOwnerGatePath=$script:OwnerGatePath
    $script:AdmittedOwnerGateSha=$script:ExpectedOwnerGateSha
    $script:AdapterDir=[string](Get-Prop $result 'adapter_dir')
    $script:AdapterBindingSha=[string](Get-Prop $result 'binding_sha256')
    $script:GcaRecoveryReceiptPath=[string](Get-Prop $ra 'gca_recovery_receipt_path')
    $script:ReviewPack=$FirstAdmissionReviewPackPath
    Write-Host ('FIRST_ADMISSION_MODE='+[string](Get-Prop $result 'mode'))
}

function Write-StopRequest([string]$Reason,[string]$TargetPath=$StopFile){
    try {
        $targetDir=[IO.Path]::GetDirectoryName($TargetPath);if (-not (Test-Path -LiteralPath $targetDir -PathType Container)){New-Item -ItemType Directory -Path $targetDir -Force|Out-Null}
        $text='reason='+$Reason+"`nrequested_at="+[DateTimeOffset]::Now.ToString('o')+"`n"
        $enc=New-Object Text.UTF8Encoding($false);Write-AtomicBytes $TargetPath ($enc.GetBytes($text))
        $script:StopPersisted=$true;$script:StopWriteError='';return $true
    }catch {$script:StopPersisted=$false;$script:StopWriteError=$_.Exception.Message;return $false}
}
function Get-CheckpointTelemetry {
    $result=[ordered]@{committed=0;checkpoint='NONE';read_status='ABSENT'}
    $cp=Join-Path $CheckpointRoot 'CHECKPOINT.json'
    if (-not (Test-Path -LiteralPath $cp -PathType Leaf)){return $result}
    try {
        $obj=Read-Json $cp;$payload=Get-Prop $obj 'payload';$raw=Get-Prop $payload 'committed_count';if ($null -ne $raw){$result.committed=[int]$raw}
        $last=Get-Prop $payload 'last_committed';if (-not [string]::IsNullOrWhiteSpace([string]$last)){$result.checkpoint=[string]$last}else {$result.checkpoint='NONE'}
        $result.read_status='PASS'
    }catch {$result.read_status='UNREADABLE'}
    return [pscustomobject]$result
}
function Assert-D4ResumeState($State){
    $stateStatus=[string](Get-Prop $State 'status')
    $allowedStatus=($stateStatus -ceq 'FAIL') -or (($stateStatus -ceq 'SAFE_STOP') -and $ResumeAfterSafeStop)
    Require ($allowedStatus -and [string](Get-Prop $State 'next_node') -ceq 'D4') 'CURRENT_STATE_NOT_D4'
    Require ($null -eq (Get-Prop $State 'canary_scratch_cert')) 'CURRENT_STATE_CERT_PRESENT'
}
function Format-Duration([double]$Seconds){
    if ($Seconds -lt 0 -or [double]::IsNaN($Seconds) -or [double]::IsInfinity($Seconds)){return 'UNKNOWN'}
    $whole=[int64][math]::Ceiling($Seconds);$d=[math]::Floor($whole/86400);$r=$whole%86400;$h=[math]::Floor($r/3600);$r=$r%3600;$m=[math]::Floor($r/60);$sec=$r%60
    return ('{0}.{1:00}.{2:00}.{3:00}' -f $d,$h,$m,$sec)
}
function Emit-D4Status([Diagnostics.Stopwatch]$Watch,[int]$Committed,[string]$Checkpoint,[int]$Active,[string]$SafeStopState,[int]$ProcessId){
    $elapsed=[math]::Max(0.001,$Watch.Elapsed.TotalSeconds)
    $newCommitted=[math]::Max(0,$Committed-$script:ProgressBaselineCommitted)
    $rate=[double]$newCommitted/$elapsed
    $rateText='UNKNOWN';$eta='UNKNOWN';$finish='UNKNOWN'
    if ($rate -gt 0){$rateText=$rate.ToString('0.000',[Globalization.CultureInfo]::InvariantCulture);$etaSec=($ExpectedTotalChunks-$Committed)/$rate;$eta=Format-Duration $etaSec;$finish=[DateTimeOffset]::Now.AddSeconds($etaSec).ToString('o')}
    $progress=([string]$Committed)+'/'+([string]$ExpectedTotalChunks);$pct=[math]::Min(100.0,100.0*$Committed/$ExpectedTotalChunks)
    Write-Progress -Activity 'TICKSTORE D4 resumable' -Status ('COMMITTED '+$progress+' ETA '+$eta) -PercentComplete $pct
    $ready=0
    Write-Host ('HEARTBEAT|PHASE=D4_RESUME|PROGRESS='+$progress+'|COMMITTED='+$Committed+'|TOTAL='+$ExpectedTotalChunks+'|RATE='+$rateText+'|ETA='+$eta+'|FINISH='+$finish+'|ACTIVE='+$Active+'|READY_WAITING='+$ready+'|CHECKPOINT='+$Checkpoint+'|SAFE_STOP='+$SafeStopState+'|PID='+$ProcessId+'|ELAPSED_S='+[int]$Watch.Elapsed.TotalSeconds+'|AUTO_KILL=NO')
    $status=[ordered]@{schema='TICKSTORE_D4_STATUS_V001';phase='D4_RESUME';progress=$progress;committed=$Committed;total=$ExpectedTotalChunks;rate=$rateText;eta=$eta;finish=$finish;active=$Active;ready_waiting=$ready;checkpoint=$Checkpoint;safe_stop=$SafeStopState;pid=$ProcessId;elapsed_seconds=[int]$Watch.Elapsed.TotalSeconds;updated_at=[DateTimeOffset]::Now.ToString('o')}
    Write-AtomicJson $StatusPath $status
}
function Test-FreeSpace {
    $drive=New-Object -TypeName System.IO.DriveInfo -ArgumentList 'D:\'
    $free=[int64]$drive.AvailableFreeSpace;$required=[int64]$ExpectedOutputGrowthBytes+[int64]$FreeSpaceHeadroomBytes
    Write-Host ('D4_EXPECTED_OUTPUT_GROWTH_BYTES_MAX='+$ExpectedOutputGrowthBytes+'|D4_EXPECTED_SCRATCH_GROWTH_BYTES='+$ExpectedScratchGrowthBytes+'|D_FREE_BYTES='+$free+'|D_REQUIRED_BYTES='+$required)
    Require ($free -ge $required) ('D_FREE_SPACE_INSUFFICIENT|FREE='+$free+'|REQUIRED='+$required)
}
function Probe-ReviewParser([string]$Root){
    $valid=Join-Path $Root 'VERDICT_VALID.txt';$dup=Join-Path $Root 'VERDICT_DUP.txt';$missing=Join-Path $Root 'VERDICT_MISSING.txt'
    $lines=New-Object 'System.Collections.Generic.List[string]'
    [void]$lines.Add('TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R22')
    [void]$lines.Add('VERDICT=PASS')
    [void]$lines.Add('INDEPENDENT_REVIEW=YES')
    [void]$lines.Add(('REVIEW_PACK_SHA256=' + (Get-Sha $ReviewPack)))
    [void]$lines.Add(('BASE_RELEASE_SHA256=' + $ExpectedBaseReleaseSha))
    [void]$lines.Add(('SUCCESSOR_RELEASE_SHA256=' + $ExpectedReleaseSha))
    [void]$lines.Add(('SUCCESSOR_CANDIDATE_SHA256=' + $ExpectedCandidateSha))
    [void]$lines.Add(('EFFECTFUL_WRAPPER_SHA256=' + (Get-Sha $PSCommandPath)))
    foreach ($line in @(
        'TESTED_CODE_EQUALS_PACKAGED_CODE=YES','CANDIDATE_RELEASE_FUSE_ONLY=PASS','CERTIFY_SCRATCH_FINAL_SEMANTICS_PRESERVED=YES','RESUME_ATTESTATION_AUTHORITY=PASS','RUNTIME_IDENTITY_BINDING=PASS',
        'CHECKPOINT_ATOMIC_DURABLE=PASS','CHECKPOINT_RECONCILIATION=PASS','COMMITTED_REVALIDATION=PASS','SAFE_STOP_COOPERATIVE=PASS','EFFECTFUL_WRAPPER_D4_ONLY=PASS','RESUME_CHUNK_UNIT=DATE_KEY','AUTO_KILL_DELTA=NO',
        'RUN_AUTHORITY_SINGLE_ATOMIC_FILE=PASS','CTRL_C_STOP_DURABLE=PASS','LONG_RUNNER_OBSERVABILITY=PASS','POLICY_ADMISSION_BINDING=PASS','SUPPORT_TOPOLOGY_REPRODUCIBLE=PASS','NESTED_EXIT_PROPAGATION=PASS','THREAD_ROUTING_IDENTITY=PASS',
        'D4_RESUME_AUTHORIZED=YES','D5_AUTHORIZED=NO','FULL_AUTHORIZED=NO','CRITICAL_FINDINGS=0','MAJOR_FINDINGS=0')){[void]$lines.Add([string]$line)}
    Require ($lines.Count -eq 32) ('PROBE_VERDICT_LINE_COUNT|' + $lines.Count)
    [IO.File]::WriteAllLines($valid,$lines.ToArray(),(New-Object Text.UTF8Encoding($false)));[void](Validate-ReviewVerdict $valid)
    $dupLines=New-Object 'System.Collections.Generic.List[string]';foreach ($line in $lines){[void]$dupLines.Add([string]$line)};[void]$dupLines.Add('VERDICT=PASS')
    [IO.File]::WriteAllLines($dup,$dupLines.ToArray(),(New-Object Text.UTF8Encoding($false)));$blocked=$false;try {[void](Parse-Verdict $dup)}catch {$blocked=$true};Require $blocked 'PROBE_DUPLICATE_VERDICT_NOT_BLOCKED'
    $missingLines=New-Object 'System.Collections.Generic.List[string]';foreach ($line in $lines){if ($line -ne 'POLICY_ADMISSION_BINDING=PASS'){[void]$missingLines.Add([string]$line)}}
    [IO.File]::WriteAllLines($missing,$missingLines.ToArray(),(New-Object Text.UTF8Encoding($false)));$blocked=$false;try {[void](Parse-Verdict $missing)}catch {$blocked=$true};Require $blocked 'PROBE_MISSING_VERDICT_GATE_NOT_BLOCKED'
}
function Invoke-RuntimeProbe {
    $probeRoot=Join-Path $env:TEMP ('TICKSTORE V002R22 TARGET PROBE '+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $probeRoot -ErrorAction Stop|Out-Null
    try {
        if (-not [string]::IsNullOrWhiteSpace($RuntimeProbeReviewPackPath)){Require (Test-Path -LiteralPath $RuntimeProbeReviewPackPath -PathType Leaf) 'PROBE_REVIEW_PACK_OVERRIDE_MISSING';$script:ReviewPack=$RuntimeProbeReviewPackPath}
        Probe-ReviewParser $probeRoot
        $actualOrchestrator=Join-Path $SuccessorRoot 'modules\orchestrator.py';Assert-OrchestratorIdentity $actualOrchestrator
        $tampered=Join-Path $probeRoot 'orchestrator tampered.py';[IO.File]::WriteAllBytes($tampered,[IO.File]::ReadAllBytes($actualOrchestrator));[IO.File]::AppendAllText($tampered,'#tamper',(New-Object Text.UTF8Encoding($false)));$orchBlocked=$false;try {Assert-OrchestratorIdentity $tampered}catch {if ($_.Exception.Message -ceq 'BLOCKED|SUCCESSOR_ORCHESTRATOR_SHA'){$orchBlocked=$true}else {throw }};Require $orchBlocked 'PROBE_ORCHESTRATOR_DRIFT_NOT_BLOCKED'
        $json='{"items":[{"x":1},{"x":2}]}'|ConvertFrom-Json;$items=New-Object 'System.Collections.Generic.List[object]';foreach ($item in (Get-Prop $json 'items')){[void]$items.Add($item)};Require ($items.Count -eq 2) 'PS51_JSON_ARRAY_MATERIALIZATION'
        $probeStop=Join-Path $probeRoot 'durable stop request with spaces.request';$script:StopPersisted=$false;$script:StopWriteError='';Require (Write-StopRequest 'RUNTIME_PROBE' $probeStop) ('PROBE_DURABLE_STOP_WRITE|' + $script:StopWriteError);Require (Test-Path -LiteralPath $probeStop -PathType Leaf) 'PROBE_DURABLE_STOP_MISSING';$stopText=[IO.File]::ReadAllText($probeStop,[Text.Encoding]::UTF8);Require ($stopText -match '^reason=RUNTIME_PROBE') 'PROBE_DURABLE_STOP_CONTENT';Require (@(Get-ChildItem -LiteralPath $probeRoot -File -Filter 'durable stop request with spaces.request.tmp.*' -ErrorAction SilentlyContinue).Count -eq 0) 'PROBE_DURABLE_STOP_TEMP_LEFTOVER'
        $receipt=Join-Path $probeRoot 'child result with spaces.json'
        $argLine='-NoProfile -ExecutionPolicy Bypass -File '+(Quote-NativeArg $PSCommandPath)+' -RuntimeProbeChild -ProbeExitCode 7 -ChildResultPath '+(Quote-NativeArg $receipt)
        $pp=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Verb RunAs -ArgumentList $argLine -Wait -PassThru
        $pp.Refresh();$raw=$pp.ExitCode;Require ($null -ne $raw) 'PROBE_CHILD_NATIVE_EXIT_NULL';$native=[int]$raw
        Require (Test-Path -LiteralPath $receipt -PathType Leaf) 'PROBE_CHILD_RECEIPT_MISSING';$r=Read-Json $receipt;$rx=Get-Prop $r 'exit_code';Require ($null -ne $rx) 'PROBE_CHILD_RECEIPT_EXIT_NULL';$receiptExit=[int]$rx
        Require ([string](Get-Prop $r 'schema') -ceq 'TICKSTORE_D4_RESUME_EFFECTFUL_V002R22_PROBE_CHILD_RESULT') 'PROBE_CHILD_SCHEMA'
        Require ([string](Get-Prop $r 'status') -ceq 'PROBE') 'PROBE_CHILD_STATUS'
        Require ($native -eq 7 -and $receiptExit -eq 7 -and $native -eq $receiptExit) ('PROBE_NESTED_EXIT|NATIVE='+$native+'|RECEIPT='+$receiptExit)
        Write-Host 'RUNTIME_PROBE=PASS|PS51_JSON_ARRAY=PASS|GENERIC_LIST_CARDINALITY=PASS|VERDICT_EXACT_SCHEMA=PASS|DUPLICATE_VERDICT_BLOCKS=PASS|NESTED_EXIT_RUNAS=PASS|ARG_PATH_SPACES=PASS|CTRL_C_DURABLE_WRITER=PASS|CHILD_PS1_EXPLICIT_TARGET_PROCESS=PASS|ORCHESTRATOR_RUNTIME_SHA_BINDING=PASS|ORCHESTRATOR_DRIFT_BLOCKS=PASS'
    }finally {if (Test-Path -LiteralPath $probeRoot -PathType Container){Remove-Item -LiteralPath $probeRoot -Recurse -Force -ErrorAction SilentlyContinue}}
}

Write-Host ('RESULT_CONTEXT=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread)
Write-Host 'EFFECTFUL_WRAPPER=TICKSTORE_D4_RESUME_EFFECTFUL_V002R22'
Write-Host 'D5_EXECUTION=NO'
Write-Host 'FULL_EXECUTION=NO'
Write-Host 'AUTO_KILL=NO'

if ($RuntimeProbeChild){
    Require (-not [string]::IsNullOrWhiteSpace($ChildResultPath)) 'PROBE_CHILD_RESULT_PATH_EMPTY'
    $obj=[ordered]@{schema='TICKSTORE_D4_RESUME_EFFECTFUL_V002R22_PROBE_CHILD_RESULT';status='PROBE';exit_code=$ProbeExitCode;pid=$PID;written_at=[DateTimeOffset]::Now.ToString('o')};Write-AtomicJson $ChildResultPath $obj
    Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);exit $ProbeExitCode
}
if ($RuntimeProbe){
    try {Invoke-RuntimeProbe;Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);exit 0}catch {Write-Host ('RUNTIME_PROBE=BLOCKED|ERROR='+$_.Exception.Message);Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);exit 2}
}
if ($RequestSafeStop){
    Require ((Get-Sha $RunAuthorityPath) -ceq $RunAuthoritySha) 'SAFE_STOP_AUTHORITY_SHA'
    $stopAuthority=Read-Json $RunAuthorityPath
    Require ([string](Get-Prop $stopAuthority 'schema') -ceq 'TICKSTORE_D4_RUN_AUTHORITY_V005' -and [string](Get-Prop $stopAuthority 'status') -ceq 'ACTIVE') 'SAFE_STOP_AUTHORITY_SCHEMA'
    Require ([string](Get-Prop $stopAuthority 'effect_scope') -ceq 'D4_ONLY' -and [string](Get-Prop $stopAuthority 'stop_file') -ceq $StopFile) 'SAFE_STOP_AUTHORITY_SCOPE'
    $script:StopPersisted=$false;$script:StopWriteError='';Require (Write-StopRequest 'EXPLICIT_REQUEST') ('SAFE_STOP_REQUEST_WRITE_FAILED|' + $script:StopWriteError)
    Write-Host ('SAFE_STOP_REQUEST_FILE=' + $StopFile);Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);return
}
if (-not $ExecuteD4){Write-Host 'MODE=REVIEWED_ENTRYPOINT_DRY';Write-Host 'D4_EXECUTION=NO';Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);return }

# First admission materializes only after final-code gates and native observation.
try {
    if ($FirstAdmission -or $ResumeAdmittedRun) {Invoke-FirstAdmissionBoundary}
    Require (Test-Path -LiteralPath $RunAuthorityPath -PathType Leaf) 'ADMITTED_RUN_AUTHORITY_REQUIRED_NO_IMPLICIT_BOOTSTRAP'

    Require ($AdmittedOwnerGateSha -cmatch '^[0-9A-F]{64}$') 'EXTERNAL_OWNER_GATE_SHA_REQUIRED'
    $OwnerGatePath=$AdmittedOwnerGatePath;$ExpectedOwnerGateSha=$AdmittedOwnerGateSha
    Require ((Get-Sha $OwnerGatePath) -ceq $ExpectedOwnerGateSha) 'EXTERNAL_OWNER_GATE_SHA'
    $admittedOwner=Read-Json $OwnerGatePath
    Require ([string](Get-Prop $admittedOwner 'recovery_source_sha256') -ceq $ExpectedReleaseSha) 'OWNER_SOURCE_NOT_RECONCILED'
    $adapterBinding=Validate-AdapterBinding
    Require ([string](Get-Prop $adapterBinding 'owner_gate_sha256') -ceq $ExpectedOwnerGateSha) 'ADAPTER_OWNER_BINDING'
    Require ((Get-Sha $Python) -ceq '4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9') 'PYTHON_SHA'
}catch {Write-Host ('FINAL_ERROR='+$_.Exception.Message);Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT='+$ResultProject+' | THREAD='+$ResultThread);exit 2}

if (-not (Is-Admin)){
    # R45 G6: the former self-elevation relaunched a child that the mode guard always blocks; the
    # early elevation check above makes this unreachable, kept fail-closed as defense in depth.
    Write-Host 'FINAL_ERROR=ELEVATION_REQUIRED_USE_RUN_TICKSTORE_FULL_PS1';Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);exit 2
}
if ($ElevatedChild){Require (Is-Admin) 'ELEVATED_CHILD_NOT_ADMIN';if (-not [string]::IsNullOrWhiteSpace($OriginalCwd)){Set-Location -LiteralPath $OriginalCwd}}

try {
    Require (Test-Path -LiteralPath $SuccessorRoot -PathType Container) 'SUCCESSOR_ROOT_MISSING'
    $Release=Join-Path $SuccessorRoot 'engine\tickstore_publisher_recovery_v004_release.py';$Candidate=Join-Path $SuccessorRoot 'engine\tickstore_publisher_recovery_v004_candidate.py';$Config=Join-Path $SuccessorRoot 'config\STAGE_A_SEALED_VALUES_V001.json';$CodeManifest=Join-Path $SuccessorRoot 'CODE_MANIFEST.json';$MasterPath=Join-Path $SuccessorRoot 'TICKSTORE_V004R1_MASTER_ORCHESTRATOR.ps1';$Orchestrator=Join-Path $SuccessorRoot 'modules\orchestrator.py'
    Require ((Get-Sha $Release) -ceq $ExpectedReleaseSha) 'SUCCESSOR_RELEASE_SHA';Require ((Get-Sha $Candidate) -ceq $ExpectedCandidateSha) 'SUCCESSOR_CANDIDATE_SHA';Assert-OrchestratorIdentity $Orchestrator;Require ((Get-Sha $Config) -ceq $ExpectedConfigSha) 'SUCCESSOR_CONFIG_SHA';Require ((Get-Sha $CodeManifest) -ceq $ExpectedCodeManifestSha) 'SUCCESSOR_CODE_MANIFEST_SHA';Require ((Get-Sha $MasterPath) -ceq $ExpectedMasterScriptSha) 'MASTER_SCRIPT_SHA';Require ((Get-Sha $SuccessorZip) -ceq $ExpectedPackageZipSha) 'SUCCESSOR_PACKAGE_ZIP_SHA'
    $manifestHits=@(Get-ChildItem -LiteralPath $SuccessorRoot -Recurse -File -Filter '*.json'|Where-Object{try {(Get-Sha $_.FullName)-ceq $ExpectedPackageManifestSha}catch {$false}});Require ($manifestHits.Count -eq 1) ('PACKAGE_MANIFEST_CARDINALITY|' + $manifestHits.Count);$PackageManifestPath=$manifestHits[0].FullName
    Require ((Get-Sha $OwnerGatePath) -ceq $ExpectedOwnerGateSha) 'OWNER_GATE_SHA';Require (Test-Path -LiteralPath $ReviewPack -PathType Leaf) 'REVIEW_PACK_MISSING'

    $v=Validate-ReviewVerdict $ReviewVerdictPath;$reviewVerdictSha=Get-Sha $ReviewVerdictPath
    $policy=Validate-PolicyAdmission $PolicyAdmissionReceiptPath $reviewVerdictSha

    Require (Test-Path -LiteralPath $GcaRecoveryReceiptPath -PathType Leaf) 'G_CA_RECOVERY_RECEIPT_MISSING';$gca=Read-Json $GcaRecoveryReceiptPath
    Require ([string](Get-Prop $gca 'schema') -ceq 'TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT_V001') 'G_CA_RECEIPT_SCHEMA';Require ([string](Get-Prop $gca 'status') -ceq 'PASS') 'G_CA_RECEIPT_STATUS';Require ([string](Get-Prop $gca 'state_status') -ceq 'FAIL' -and [string](Get-Prop $gca 'state_next_node') -ceq 'D4') 'G_CA_RECEIPT_STATE';Require ([string](Get-Prop $gca 'canary_scratch_cert') -ceq 'ABSENT') 'G_CA_RECEIPT_CERT';Require ([string](Get-Prop $gca 'owner_gate_sha256') -ceq $ExpectedOwnerGateSha) 'G_CA_RECEIPT_OWNER'
    $locatorGeneration=Get-Prop $gca 'generation';$generation=Get-Prop $admittedOwner 'admission_generation';Require ($null -ne $generation -and $null -ne $locatorGeneration) 'G_CA_RECEIPT_GENERATION'
    foreach ($f in @('snapshot_id','snapshot_set_id','provider_id','volume_identity','purpose')){Require ([string](Get-Prop $generation $f) -ceq [string](Get-Prop $locatorGeneration $f)) ('G_CA_STABLE_IDENTITY|' + $f)}
    $state=Read-Json $StatePath;Assert-D4ResumeState $state;Require (@(Get-ChildItem -LiteralPath $RunsRoot -Recurse -File -Filter 'RESULT_D5.json' -ErrorAction SilentlyContinue).Count -eq 0) 'D5_RESULT_PRESENT'
    Test-FreeSpace

    New-Item -ItemType Directory -Path $AuthorityRoot -Force|Out-Null
    Require (@(Get-ChildItem -LiteralPath $AuthorityRoot -File -Filter 'RUN_AUTHORITY.json.tmp.*' -ErrorAction Stop).Count -eq 0) 'AUTHORITY_PENDING_FILES_REQUIRE_DIAGNOSIS'
    Require (Test-Path -LiteralPath $RunAuthorityPath -PathType Leaf) 'ADMITTED_RUN_AUTHORITY_REQUIRED'
    $auth=Read-Json $RunAuthorityPath
    $protected=[Convert]::FromBase64String([string](Get-Prop $auth 'protected_key_b64'))
    $key=[Security.Cryptography.ProtectedData]::Unprotect($protected,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    $keySha=([BitConverter]::ToString(([Security.Cryptography.SHA256]::Create().ComputeHash($key)))).Replace('-','')
    $auth=Read-Json $RunAuthorityPath;Require ([string](Get-Prop $auth 'schema') -ceq 'TICKSTORE_D4_RUN_AUTHORITY_V005' -and [string](Get-Prop $auth 'status') -ceq 'ACTIVE') 'RUN_AUTHORITY_SCHEMA';Require ([string](Get-Prop $auth 'key_sha256') -ceq $keySha) 'RUN_AUTHORITY_KEY'
    foreach ($pair in @(@('artifact_base_master_sha256',$ArtifactBaseMasterSha),@('base_release_sha256',$ExpectedBaseReleaseSha),@('successor_release_sha256',$ExpectedReleaseSha),@('engine_path',$Release),@('successor_candidate_sha256',$ExpectedCandidateSha),@('candidate_path',$Candidate),@('orchestrator_sha256',$ExpectedOrchestratorSha),@('orchestrator_path',$Orchestrator),@('config_sha256',$ExpectedConfigSha),@('config_path',$Config),@('code_manifest_sha256',$ExpectedCodeManifestSha),@('code_manifest_path',$CodeManifest),@('package_manifest_sha256',$ExpectedPackageManifestSha),@('package_manifest_path',$PackageManifestPath),@('package_zip_sha256',$ExpectedPackageZipSha),@('package_zip_path',$SuccessorZip),@('owner_gate_sha256',$ExpectedOwnerGateSha),@('owner_gate_path',$OwnerGatePath),@('review_pack_sha256',(Get-Sha $ReviewPack)),@('review_pack_path',$ReviewPack),@('review_verdict_sha256',$reviewVerdictSha),@('review_verdict_path',$ReviewVerdictPath),@('gca_recovery_receipt_sha256',(Get-Sha $GcaRecoveryReceiptPath)),@('gca_recovery_receipt_path',$GcaRecoveryReceiptPath),@('policy_admission_receipt_sha256',(Get-Sha $PolicyAdmissionReceiptPath)),@('policy_admission_receipt_path',$PolicyAdmissionReceiptPath),@('effectful_wrapper_sha256',(Get-Sha $PSCommandPath)),@('effectful_wrapper_path',$PSCommandPath))){Require ([string](Get-Prop $auth $pair[0]) -ceq [string]$pair[1]) ('RUN_AUTHORITY_DRIFT|' + $pair[0])}
    $authGeneration=Get-Prop $auth 'generation';Require ($null -ne $authGeneration) 'RUN_AUTHORITY_GENERATION_MISSING';foreach ($f in @('snapshot_id','snapshot_set_id','provider_id','device_object','volume_identity')){Require ([string](Get-Prop $authGeneration $f) -ceq [string](Get-Prop $generation $f)) ('RUN_AUTHORITY_GENERATION_DRIFT|' + $f)}
    $protected=[Convert]::FromBase64String([string](Get-Prop $auth 'protected_key_b64'));$key=[Security.Cryptography.ProtectedData]::Unprotect($protected,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser);$keyHex=[BitConverter]::ToString($key).Replace('-','');$authoritySha=Get-Sha $RunAuthorityPath

    if (Test-Path -LiteralPath $StopFile -PathType Leaf){Require $ResumeAfterSafeStop 'STOP_REQUEST_PRESENT_USE_RESUME_AFTER_SAFE_STOP';$consumed=Join-Path $ResumeRoot ('STOP.consumed.'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')+'.request');Move-Item -LiteralPath $StopFile -Destination $consumed -ErrorAction Stop;Write-Host ('SAFE_STOP_REQUEST_CONSUMED_FOR_EXPLICIT_RESUME='+$consumed)}

    $script:CancelRequested=$false;$script:StopPersisted=$false;$script:StopWriteError=''
    $cancelHandler=[ConsoleCancelEventHandler]{param ($sender,$e);$script:CancelRequested=$true;[void](Write-StopRequest 'CTRL_C');$e.Cancel=$true}
    [Console]::add_CancelKeyPress($cancelHandler)
    $old=@{ENABLE=$env:TICKSTORE_D4_RESUME_ENABLE;AUTH=$env:TICKSTORE_D4_RUN_AUTHORITY;AUTHSHA=$env:TICKSTORE_D4_RUN_AUTHORITY_SHA256;KEY=$env:TICKSTORE_D4_RUN_HMAC_KEY_HEX;ADAPTER=$env:TICKSTORE_RUNTIME_LOCATOR_ADAPTER_DIR;LOCATOR=$env:TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT}
    try {
        $env:TICKSTORE_D4_RESUME_ENABLE='1';$env:TICKSTORE_D4_RUN_AUTHORITY=$RunAuthorityPath;$env:TICKSTORE_D4_RUN_AUTHORITY_SHA256=$authoritySha;$env:TICKSTORE_D4_RUN_HMAC_KEY_HEX=$keyHex
        $env:TICKSTORE_RUNTIME_LOCATOR_ADAPTER_DIR=$AdapterDir;$env:TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT=$GcaRecoveryReceiptPath
        Require ((Get-Sha $Orchestrator) -ceq $ExpectedOrchestratorSha) 'SUCCESSOR_ORCHESTRATOR_SHA_PRELAUNCH'
        $adapterEntry=Join-Path $AdapterDir 'runtime_locator_orchestrator_entry.py'
        Require ((Get-Sha $adapterEntry) -ceq [string](Get-Prop $adapterBinding 'orchestrator_entry_sha256')) 'ADAPTER_ENTRY_PRELAUNCH_SHA'
        $psi=New-Object Diagnostics.ProcessStartInfo;$psi.FileName=$Python;$psi.WorkingDirectory='C:\Users\silvi';$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true;$psi.Arguments='-I -S -B '+(Quote-NativeArg $adapterEntry)+' run --until D4 --package '+(Quote-NativeArg $SuccessorRoot)+' --python '+(Quote-NativeArg $Python)
        $baselineTelemetry=Get-CheckpointTelemetry;$script:ProgressBaselineCommitted=[int]$baselineTelemetry.committed
        $p=New-Object Diagnostics.Process;$p.StartInfo=$psi;Require ($p.Start()) 'MASTER_START_FALSE';$ot=$p.StandardOutput.ReadToEndAsync();$et=$p.StandardError.ReadToEndAsync();$sw=[Diagnostics.Stopwatch]::StartNew();$next=$HeartbeatSeconds;$lastCommitted=-1
        while (-not $p.HasExited){
            Start-Sleep -Seconds 1;$p.Refresh()
            if ($script:CancelRequested -and -not $script:StopPersisted){if (Write-StopRequest 'CTRL_C_RETRY'){Write-Host 'SAFE_STOP_REQUEST_PERSIST=PASS_AFTER_RETRY'}else {Write-Host ('SAFE_STOP_REQUEST_PERSIST=RETRYING|ERROR='+$script:StopWriteError)}}
            if ($sw.Elapsed.TotalHours -ge 24 -and -not (Test-Path -LiteralPath $StopFile)){if (Write-StopRequest 'WATCHDOG_24H'){Write-Host 'WATCHDOG_ACTION=COOPERATIVE_SAFE_STOP_REQUESTED|AUTO_KILL=NO'}else {Write-Host ('WATCHDOG_SAFE_STOP_WRITE=RETRYING|ERROR='+$script:StopWriteError)}}
            $tele=Get-CheckpointTelemetry;$safe='NO';if ($script:CancelRequested -and -not $script:StopPersisted){$safe='PERSIST_RETRY'}elseif (Test-Path -LiteralPath $StopFile -PathType Leaf){$safe='REQUESTED'}
            if ($tele.committed -ne $lastCommitted -or $sw.Elapsed.TotalSeconds -ge $next){Emit-D4Status $sw ([int]$tele.committed) ([string]$tele.checkpoint) 1 $safe $p.Id;$lastCommitted=[int]$tele.committed;while ($sw.Elapsed.TotalSeconds -ge $next){$next+=$HeartbeatSeconds}}
        }
        $p.WaitForExit();$p.Refresh();$sw.Stop();$rawMasterExit=$p.ExitCode;Require ($null -ne $rawMasterExit) 'MASTER_EXIT_NULL';$masterExit=[int]$rawMasterExit
        $stdout=$ot.GetAwaiter().GetResult();$stderr=$et.GetAwaiter().GetResult();if (-not [string]::IsNullOrWhiteSpace($stdout)){Write-Host $stdout};if (-not [string]::IsNullOrWhiteSpace($stderr)){Write-Host $stderr};Write-Host ('D4_MASTER_EXIT_CODE='+$masterExit)
        $finalTele=Get-CheckpointTelemetry;$safeFinal='NO';if (Test-Path -LiteralPath $StopFile -PathType Leaf){$safeFinal='REQUESTED'};Emit-D4Status $sw ([int]$finalTele.committed) ([string]$finalTele.checkpoint) 0 $safeFinal $p.Id;Write-Progress -Activity 'TICKSTORE D4 resumable' -Completed
        if ($masterExit -eq 130 -and $stdout -match 'SAFE_STOP=YES'){Write-Host 'D4_SAFE_STOP=PASS_RESUMABLE';Write-ChildResult 'SAFE_STOP_PASS' 130 '';Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);exit 130}
        Require ($masterExit -eq 0) ('MASTER_NONZERO|' + $masterExit);$state2=Read-Json $StatePath;Require ([string](Get-Prop $state2 'status') -eq 'PASS' -and [string](Get-Prop $state2 'next_node') -eq 'D5') 'D4_FINAL_STATE';Write-Host 'D4_EXECUTION=PASS';Write-Host 'D5_EXECUTION=NO';Write-Host 'FULL_EXECUTION=NO'
    }finally {[Console]::remove_CancelKeyPress($cancelHandler);$env:TICKSTORE_D4_RESUME_ENABLE=$old.ENABLE;$env:TICKSTORE_D4_RUN_AUTHORITY=$old.AUTH;$env:TICKSTORE_D4_RUN_AUTHORITY_SHA256=$old.AUTHSHA;$env:TICKSTORE_D4_RUN_HMAC_KEY_HEX=$old.KEY;$env:TICKSTORE_RUNTIME_LOCATOR_ADAPTER_DIR=$old.ADAPTER;$env:TICKSTORE_G_CA_RUNTIME_LOCATOR_RECEIPT=$old.LOCATOR}
    Write-ChildResult 'PASS' 0 '';Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread)
} catch {
    $msg=$_.Exception.Message;Write-ChildResult 'BLOCKED_OR_FAIL' 2 $msg;Write-Host ('FINAL_ERROR=' + $msg);Write-Host ('RESULT_RETURN_TO=ChatGPT | PROJECT=' + $ResultProject + ' | THREAD=' + $ResultThread);exit 2
}

