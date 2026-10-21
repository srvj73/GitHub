#requires -Version 5.1
# TICKSTORE CDT21 - COLETA SOMENTE LEITURA das evidencias da ultima execucao G5 V003 (filho elevado PID 5076).
# Execute a partir de PS C:\Users\silvi> em PowerShell 5.1 COMUM (sem Administrador, sem UAC):
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V003_COLLECT_READONLY_20261021.ps1"
# Log sempre em pasta absoluta fixa, nova a cada execucao, independente da pasta atual:
#   C:\Users\silvi\Downloads\CDT21_G5_V003_COLLECT_RUNS\COLLECT_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt
# Le somente (C:, perfil silvi):
#   Downloads\CDT21_G5_V003_RUNS\G5_*                  (logs do pai e do filho, SUPERVISOR_RESULT, retornos)
#   AppData\Local\CDT21_G5_V003\STAGE_*                (console do supervisor)
#   AppData\Local\CDT20_R08\R08_Q1_* com CDT21_SUPERVISOR_BOOTSTRAP.json ou citadas em SUPERVISOR_RESULT
#   Downloads\TICKSTORE_RUNS e OneDrive\Downloads\TICKSTORE_RUNS apenas na janela temporal dessas raizes
# Nunca executa, move, apaga ou altera arquivos de origem; nunca acessa D:; nao segue links/junctions.
[CmdletBinding()]
param(
    [string]$TestRoot = '',
    [long]$MaxFileBytes = 262144000,
    [long]$MaxTotalBytes = 629145600,
    [int]$MaxListEntries = 20000
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function J([string[]]$Parts) { $p = $Parts[0]; for ($i = 1; $i -lt $Parts.Count; $i++) { $p = [IO.Path]::Combine($p, $Parts[$i]) }; return $p }

$Profile0 = 'C:\Users\silvi'
if ($TestRoot) { $Profile0 = [IO.Path]::GetFullPath($TestRoot) }
$Downloads = J @($Profile0, 'Downloads')
$Local = J @($Profile0, 'AppData', 'Local')
$RunsDir = J @($Downloads, 'CDT21_G5_V003_RUNS')
$StageParent = J @($Local, 'CDT21_G5_V003')
$R08Parent = J @($Local, 'CDT20_R08')
$TickDirs = @((J @($Downloads, 'TICKSTORE_RUNS')), (J @($Profile0, 'OneDrive', 'Downloads', 'TICKSTORE_RUNS')))
$Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
$OutDir = J @($Downloads, 'CDT21_G5_V003_COLLECT_RUNS', ('COLLECT_' + $Stamp))
$FilesDir = J @($OutDir, 'FILES')
if (-not $TestRoot -and -not $OutDir.StartsWith('C:\Users\silvi\Downloads\', [StringComparison]::OrdinalIgnoreCase)) { throw 'OUTDIR_NOT_CANONICAL' }
[void][IO.Directory]::CreateDirectory($FilesDir)
$Log = J @($OutDir, 'RUN_LOG.txt')
$Utf8 = New-Object Text.UTF8Encoding($false)
$Share = [IO.FileShare]'ReadWrite, Delete'
$Entries = New-Object Collections.Generic.List[object]
$Aliases = New-Object Collections.Generic.List[object]
$script:Total = [long]0
$script:Listed = 0
$script:Errors = 0

function Log([string]$Line) {
    Write-Host $Line
    [IO.File]::AppendAllText($Log, $Line + "`r`n", $Utf8)
}
function HashStream([IO.Stream]$S) {
    $h = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($h.ComputeHash($S)).Replace('-', '') } finally { $h.Dispose() }
}
function HashFile([string]$Path) {
    $s = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $Share)
    try { return HashStream $s } finally { $s.Dispose() }
}
function Add-Entry([string]$Alias, [string]$Rel, [string]$Source, [string]$Kind, $Bytes, [string]$Sha, [string]$Mtime, [string]$Err) {
    $Entries.Add([pscustomobject][ordered]@{ alias = $Alias; rel = $Rel; source = $Source; kind = $Kind; bytes = $Bytes;
        sha256 = $Sha; mtime_utc = $Mtime; error = $Err })
}
function Under([string]$Path, [string]$Root) {
    $p = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/'); $r = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    return ($p.Equals($r, [StringComparison]::OrdinalIgnoreCase) -or
            $p.StartsWith($r + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))
}
function Is-Reparse($Info) { return (($Info.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) }
function Rel([string]$Base, [string]$Full) { return $Full.Substring($Base.TrimEnd('\', '/').Length).TrimStart('\', '/') }

function Walk([string]$Base, [int]$MaxDepth, [string]$Alias) {
    # Own walker: never follows reparse points (links/junctions), records them instead.
    $files = New-Object Collections.Generic.List[object]
    $stack = New-Object Collections.Generic.Stack[object]
    $stack.Push(@{ d = $Base; n = 0 })
    while ($stack.Count -gt 0) {
        $item = $stack.Pop()
        try { $infos = (New-Object IO.DirectoryInfo($item.d)).GetFileSystemInfos() }
        catch { $script:Errors++; Add-Entry $Alias (Rel $Base $item.d) $item.d 'ERROR_DIR' $null '' '' $_.Exception.Message; continue }
        foreach ($e in $infos) {
            try {
                if (Is-Reparse $e) { Add-Entry $Alias (Rel $Base $e.FullName) $e.FullName 'SKIPPED_REPARSE' $null '' '' ''; continue }
                if ($e -is [IO.DirectoryInfo]) {
                    if ($item.n + 1 -le $MaxDepth) { $stack.Push(@{ d = $e.FullName; n = $item.n + 1 }) }
                } else { [void]$e.Length; $files.Add($e) }
            } catch { $script:Errors++; Add-Entry $Alias '' ([string]$item.d) 'ERROR_ENTRY' $null '' '' $_.Exception.Message }
        }
    }
    $arr = @($files.ToArray() | Sort-Object FullName)
    return ,$arr
}

function Copy-One([string]$Alias, [string]$Base, $Info) {
    $rel = Rel $Base $Info.FullName
    $mt = $Info.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
    try {
        if ($Info.Length -gt $MaxFileBytes) { Add-Entry $Alias $rel $Info.FullName 'HASH_ONLY_SIZE_CAP' $Info.Length (HashFile $Info.FullName) $mt ''; return }
        if ($script:Total + $Info.Length -gt $MaxTotalBytes) { Add-Entry $Alias $rel $Info.FullName 'HASH_ONLY_TOTAL_CAP' $Info.Length (HashFile $Info.FullName) $mt ''; return }
        $src = [IO.File]::Open($Info.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, $Share)
        try {
            $buf = New-Object byte[] ([int]$src.Length); $off = 0
            while ($off -lt $buf.Length) { $n = $src.Read($buf, $off, $buf.Length - $off); if ($n -le 0) { break }; $off += $n }
        } finally { $src.Dispose() }
        if ($off -ne $buf.Length) { throw 'SHORT_READ' }
        $h = [Security.Cryptography.SHA256]::Create()
        try { $sha = [BitConverter]::ToString($h.ComputeHash($buf)).Replace('-', '') } finally { $h.Dispose() }
        $dest = J @($FilesDir, $Alias, $rel)
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dest))
        $out = [IO.File]::Open($dest, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $out.Write($buf, 0, $buf.Length); $out.Flush($true) } finally { $out.Dispose() }
        if ((HashFile $dest) -cne $sha) { throw 'COPY_READBACK_MISMATCH' }
        $script:Total += $buf.Length
        Add-Entry $Alias $rel $Info.FullName 'COLLECTED' $buf.Length $sha $mt ''
    } catch { $script:Errors++; Add-Entry $Alias $rel $Info.FullName 'ERROR' $Info.Length '' $mt $_.Exception.Message }
}
function Hash-One([string]$Alias, [string]$Base, $Info, [string]$Kind) {
    $rel = Rel $Base $Info.FullName
    try { Add-Entry $Alias $rel $Info.FullName $Kind $Info.Length (HashFile $Info.FullName) $Info.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ') '' }
    catch { $script:Errors++; Add-Entry $Alias $rel $Info.FullName 'ERROR' $Info.Length '' '' $_.Exception.Message }
}
function List-Only([string]$Alias, [string]$Base, [string]$Sub, [int]$Depth) {
    $p = J @($Base, $Sub)
    if (-not [IO.Directory]::Exists($p)) { return }
    foreach ($f in (Walk $p $Depth $Alias)) {
        if ($script:Listed -ge $MaxListEntries) { Add-Entry $Alias $Sub $p 'LIST_CAP_REACHED' $null '' '' ''; return }
        $script:Listed++
        Add-Entry $Alias (Rel $Base $f.FullName) $f.FullName 'LISTED_ONLY' $f.Length '' $f.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ') ''
    }
}
function Make-Alias([string]$Prefix, [string]$Source, [string]$Why) {
    $n = 1 + @($Aliases | Where-Object { $_.alias -like ($Prefix + '_*') }).Count
    $a = $Prefix + '_' + $n
    $Aliases.Add([pscustomobject][ordered]@{ alias = $a; source = $Source; selected_because = $Why })
    return $a
}
function Dirs([string]$Parent, [string]$Pattern) {
    if (-not [IO.Directory]::Exists($Parent)) { return @() }
    return @((New-Object IO.DirectoryInfo($Parent)).GetDirectories($Pattern) | Where-Object { -not (Is-Reparse $_) } | Sort-Object Name)
}
function Prop($Obj, [string]$Name) { $p = $Obj.PSObject.Properties[$Name]; if ($p) { return $p.Value } else { return $null } }

$code = 2
try {
    Log ('RESULT_CONTEXT=Opus | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compress' + [char]0x00E3 + 'o De Ticks 21')
    Log ('RUN_LOG=' + $Log)
    if ($PSCommandPath) { Log ('COLLECTOR=' + $PSCommandPath + ' SHA256=' + (HashFile $PSCommandPath)) }
    Log 'MODO=SOMENTE_LEITURA; SEM_UAC; SEM_EXECUCAO_DE_ARQUIVOS_COLETADOS; SEM_ACESSO_A_D; SEM_MOVER_APAGAR_ALTERAR'
    Log ('LIMITES=arquivo<=' + $MaxFileBytes + ' total<=' + $MaxTotalBytes + ' listagem<=' + $MaxListEntries)
    foreach ($root in @($RunsDir, $StageParent, $R08Parent) + $TickDirs) {
        if ($root.StartsWith('D:', [StringComparison]::OrdinalIgnoreCase)) { throw 'D_DRIVE_FORBIDDEN' }
        if (Under $OutDir $root) { throw 'OUTDIR_INSIDE_SOURCE' }
    }

    # 1. Execucoes G5 (pai e filho): ultimas 20, todos os arquivos; ENVIAR_* (duplicata) so hash.
    $runRoots = New-Object Collections.Generic.List[string]
    $runDirs = @(Dirs $RunsDir 'G5_*' | Select-Object -Last 20)
    Log ('G5_RUN_DIRS=' + $runDirs.Count)
    foreach ($d in $runDirs) {
        $a = Make-Alias 'G5RUN' $d.FullName 'Downloads\CDT21_G5_V003_RUNS\G5_*'
        Log ('  ' + $a + ' = ' + $d.FullName)
        foreach ($f in (Walk $d.FullName 2 $a)) {
            if ($f.Name -like 'ENVIAR_AO_CHATGPT_*.zip') { Hash-One $a $d.FullName $f 'HASH_ONLY_DUPLICATE_BUNDLE' } else { Copy-One $a $d.FullName $f }
            if ($f.Name -eq 'SUPERVISOR_RESULT.json') {
                try {
                    $sr = [IO.File]::ReadAllText($f.FullName) | ConvertFrom-Json
                    foreach ($k in @('status', 'phase', 'exit_code', 'campaign_exit_code', 'campaign_status', 'run_root', 'owned_processes_at_end', 'return_sha256', 'native_return_sha256')) { Log ('    ' + $k + '=' + (Prop $sr $k)) }
                    foreach ($b in @(Prop $sr 'blockers')) { if ($b) { Log ('    blocker=' + $b) } }
                    $rr = [string](Prop $sr 'run_root')
                    if ($rr -and (Under $rr $Local) -and -not $runRoots.Contains($rr)) { $runRoots.Add($rr) }
                } catch { Log ('    SUPERVISOR_RESULT_PARSE_ERROR=' + $_.Exception.Message) }
            }
        }
    }

    # 2. Estagios do supervisor: arquivos de primeiro nivel; TEMP so listado.
    $stages = @(Dirs $StageParent 'STAGE_*' | Select-Object -Last 20)
    Log ('STAGE_DIRS=' + $stages.Count)
    foreach ($d in $stages) {
        $a = Make-Alias 'STAGE' $d.FullName 'AppData\Local\CDT21_G5_V003\STAGE_*'
        Log ('  ' + $a + ' = ' + $d.FullName)
        foreach ($f in (Walk $d.FullName 0 $a)) { Copy-One $a $d.FullName $f }
        List-Only $a $d.FullName 'TEMP' 3
    }

    # 3. Raizes de campanha V003: com CDT21_SUPERVISOR_BOOTSTRAP.json ou citadas por SUPERVISOR_RESULT.
    foreach ($d in (Dirs $R08Parent 'R08_Q1_*')) {
        if ([IO.File]::Exists((J @($d.FullName, 'CDT21_SUPERVISOR_BOOTSTRAP.json'))) -and -not $runRoots.Contains($d.FullName)) { $runRoots.Add($d.FullName) }
    }
    $roots = @($runRoots | Where-Object { [IO.Directory]::Exists($_) -and -not (Is-Reparse (New-Object IO.DirectoryInfo($_))) } | Sort-Object | Select-Object -Last 10)
    Log ('V003_RUN_ROOTS=' + $roots.Count)
    $windows = New-Object Collections.Generic.List[object]
    foreach ($r in $roots) {
        $a = Make-Alias 'ROOT' $r 'CDT21_SUPERVISOR_BOOTSTRAP.json or SUPERVISOR_RESULT.run_root'
        Log ('  ' + $a + ' = ' + $r)
        foreach ($f in (Walk $r 0 $a)) {
            if ($f.Name -like '*.zip.partial') { Hash-One $a $r $f 'HASH_ONLY_PARTIAL' } else { Copy-One $a $r $f }
        }
        foreach ($sub in @('COMMITS', 'LOGS', 'UNITS', 'EVIDENCE', 'INTERRUPTED_ATTEMPTS', 'SOURCE_REVIEW', 'FINAL_G5')) {
            $p = J @($r, $sub)
            if (-not [IO.Directory]::Exists($p)) { continue }
            foreach ($f in (Walk $p 12 $a)) {
                if ($sub -eq 'FINAL_G5' -and $f.Name -like '*.zip') { Hash-One $a $r $f 'HASH_ONLY_DUPLICATE_INPUT' } else { Copy-One $a $r $f }
            }
        }
        foreach ($g in (Dirs $r 'G5_ASSEMBLY_INPUTS_*')) { foreach ($f in (Walk $g.FullName 4 $a)) { Copy-One $a $r $f } }
        $inp = J @($r, 'INPUTS')
        if ([IO.Directory]::Exists($inp)) {
            foreach ($f in (Walk $inp 0 $a)) { if ($f.Extension -ieq '.json') { Copy-One $a $r $f } else { Hash-One $a $r $f 'HASH_ONLY_INPUT' } }
        }
        foreach ($sub in @('WORK', 'TEMP', 'QUAL_C')) { List-Only $a $r $sub 4 }
        List-Only $a $r 'PACKAGED' 1
        $er = J @($r, 'ENGINEERING_RESULT.json')
        $start = (New-Object IO.DirectoryInfo($r)).CreationTimeUtc
        $bs = J @($r, 'CDT21_SUPERVISOR_BOOTSTRAP.json'); if ([IO.File]::Exists($bs)) { $start = [IO.File]::GetLastWriteTimeUtc($bs) }
        $end = [DateTime]::UtcNow; if ([IO.File]::Exists($er)) { $end = [IO.File]::GetLastWriteTimeUtc($er) }
        $windows.Add(@{ from = $start.AddMinutes(-2); to = $end.AddMinutes(5) })
        if ([IO.File]::Exists($er)) {
            try {
                $eo = [IO.File]::ReadAllText($er) | ConvertFrom-Json
                Log ('    ENGINEERING_RESULT.status=' + (Prop $eo 'status'))
                foreach ($b in @(Prop $eo 'blockers')) { if ($b) { Log ('    ENGINEERING_RESULT.blocker=' + $b) } }
                $t = Prop $eo 'tests'; if ($t) { Log ('    ENGINEERING_RESULT.tests=' + @($t.PSObject.Properties).Count) }
            } catch { Log ('    ENGINEERING_RESULT_PARSE_ERROR=' + $_.Exception.Message) }
        } else { Log '    ENGINEERING_RESULT=AUSENTE' }
        $cm = J @($r, 'COMMITS'); $nc = 0; if ([IO.Directory]::Exists($cm)) { $nc = @([IO.Directory]::GetFiles($cm, '*.json')).Count }
        Log ('    COMMITS_JSON=' + $nc)
    }

    # 4. TICKSTORE_RUNS somente dentro da janela temporal das raizes coletadas.
    foreach ($t in $TickDirs) {
        foreach ($d in (Dirs $t '*')) {
            $mt = $d.LastWriteTimeUtc; $hit = $false
            foreach ($w in $windows) { if ($mt -ge $w.from -and $mt -le $w.to) { $hit = $true } }
            if (-not $hit) { continue }
            $a = Make-Alias 'TICK' $d.FullName 'TICKSTORE_RUNS within run-root time window'
            foreach ($f in (Walk $d.FullName 3 $a)) { Copy-One $a $d.FullName $f }
        }
    }

    $found = $runDirs.Count + $stages.Count + $roots.Count
    $code = 0; if ($found -eq 0) { $code = 1 }
    if ($script:Errors -gt 0) { Log ('ERROS_DE_LEITURA=' + $script:Errors + ' (ver COLLECT_MANIFEST.json; se forem ACCESS_DENIED em arquivos do filho elevado, informe)') }
} catch {
    Log ('COLLECT_BLOCKED=' + $_.Exception.Message)
    $code = 2
} finally {
    $kinds = @{}; foreach ($e in $Entries) { if ($kinds.ContainsKey($e.kind)) { $kinds[$e.kind]++ } else { $kinds[$e.kind] = 1 } }
    $manifest = [pscustomobject][ordered]@{
        schema = 'CDT21_G5_V003_READONLY_COLLECT_MANIFEST_V001'; exit_code = $code; stamp = $Stamp; test_mode = [bool]$TestRoot
        candidate_sha256 = '69DA2D5964BABA95D8B90D5BC17E12683B5F5E91D1C7D7ABD01938A7AE014A50'
        read_only = $true; d_drive_accessed = $false; executed_collected_files = $false
        limits = [pscustomobject][ordered]@{ max_file_bytes = $MaxFileBytes; max_total_bytes = $MaxTotalBytes; max_list_entries = $MaxListEntries }
        collected_bytes = $script:Total; errors = $script:Errors
        counts = [pscustomobject]$kinds; aliases = $Aliases.ToArray(); entries = $Entries.ToArray() }
    $mpath = J @($OutDir, 'COLLECT_MANIFEST.json')
    [IO.File]::WriteAllText($mpath, ($manifest | ConvertTo-Json -Depth 6), $Utf8)
    foreach ($k in ($kinds.Keys | Sort-Object)) { Log ('CONTAGEM ' + $k + '=' + $kinds[$k]) }
    Log ('COLLECT_MANIFEST=' + $mpath + ' SHA256=' + (HashFile $mpath))
    Log ('EXIT_CODE=' + $code)
    $Send = J @($OutDir, ('ENVIAR_AO_OPUS_CDT21_G5_V003_COLLECT_' + $Stamp + '.zip'))
    try {
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::Open($Send, [IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($f in (Walk $OutDir 20 'OUT')) {
                if ($f.FullName -eq $Send) { continue }
                $name = (Rel $OutDir $f.FullName).Replace('\', '/')
                [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $name, [IO.Compression.CompressionLevel]::Optimal)
            }
        } finally { $zip.Dispose() }
        Log ('ENVIE_AO_OPUS=' + $Send)
        Log ('ENVIE_AO_OPUS_SHA256=' + (HashFile $Send))
    } catch { Log ('ZIP_FALHOU=' + $_.Exception.Message + ' (envie a pasta ' + $OutDir + ')') }
    Log 'Envie o ZIP acima ao Opus na conversa de engenharia (Compressao De Ticks 21).'
}
exit $code
