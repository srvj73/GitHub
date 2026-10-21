#requires -Version 5.1
# DIAGNOSTICO V2 SOMENTE LEITURA do volume D: apos perda de dados. NAO grava nada em D:.
# Execute em PowerShell 5.1 ABERTO COMO ADMINISTRADOR, a partir de PS C:\Users\silvi>:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_DIAG_D_PERDA_READONLY_V2_20261021.ps1"
# Log sempre em pasta absoluta fixa, nova a cada execucao, independente da pasta atual:
#   C:\Users\silvi\Downloads\DIAG_D_RUNS\DIAGV2_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt
# Diario USN bruto (grande) fica em C:\Users\silvi\AppData\Local\DIAG_D\<carimbo>\ e pode ser apagado depois.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Continue'

$Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
$LogDir = 'C:\Users\silvi\Downloads\DIAG_D_RUNS\DIAGV2_' + $Stamp
$WorkDir = 'C:\Users\silvi\AppData\Local\DIAG_D\V2_' + $Stamp
foreach ($d in @($LogDir, $WorkDir)) {
    if ($d.Substring(0, 2) -ne 'C:') { throw 'DESTINO_FORA_DE_C' }
    New-Item -ItemType Directory -Path $d -ErrorAction Stop | Out-Null
}
$Log = Join-Path $LogDir 'RUN_LOG.txt'
$Utf8 = New-Object Text.UTF8Encoding($false)
$Downloads = @('C:\Users\silvi\Downloads', 'C:\Users\silvi\OneDrive\Downloads')

function Log([string]$Line) {
    Write-Host $Line
    [IO.File]::AppendAllText($Log, $Line + "`r`n", $Utf8)
}
function Section([string]$Title) { Log ''; Log ('==== ' + $Title + ' ====') }
function Run([string]$Title, [scriptblock]$Block) {
    Section $Title
    try {
        $text = (& $Block 2>&1 | Out-String -Width 400)
        foreach ($line in ($text -split "`r?`n")) { if ($line.Trim()) { Log $line.TrimEnd() } }
    } catch { Log ('ERRO=' + $_.Exception.Message) }
}
function SizeOf([string]$Path) {
    $sum = [double]0; $n = 0
    Get-ChildItem -LiteralPath $Path -Force -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { $sum += $_.Length; $n++ }
    return ('{0,10:N2} GB  {1,9} arquivos' -f ($sum / 1GB), $n)
}

Log 'DIAGNOSTICO_D_PERDA_V2=SOMENTE_LEITURA; NENHUMA_GRAVACAO_EM_D'
Log ('RUN_LOG=' + $Log)
Log ('INICIO=' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Log 'ELEVACAO_NECESSARIA: feche, abra o PowerShell com "Executar como administrador" e rode de novo.'
    exit 2
}
Log 'ELEVADO=True'

Run 'PROCESSOS EM EXECUCAO QUE PODEM APAGAR ARQUIVOS' {
    Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|powershell|pwsh|cmd|robocopy|node|codex|claude)(\.exe)?$' } |
        Select-Object ProcessId, Name, @{n='Inicio';e={$_.CreationDate}}, CommandLine | Format-List
}

Run 'VOLUME D: E PASTA D:\Base CSV' {
    Get-Volume -DriveLetter D | Format-List DriveLetter, FileSystemLabel, FileSystem, HealthStatus, @{n='TamanhoGB';e={[math]::Round($_.Size/1GB,2)}}, @{n='LivreGB';e={[math]::Round($_.SizeRemaining/1GB,2)}}
    $b = Get-Item -LiteralPath 'D:\Base CSV' -Force -ErrorAction SilentlyContinue
    if ($b) { 'D:\Base CSV  criada={0}  ultima_alteracao_da_pasta={1}  atributos={2}' -f $b.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'), $b.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $b.Attributes }
    else { 'D:\Base CSV AUSENTE' }
}

Run 'COPIAS DE SOMBRA (VSS) DE D:' {
    vssadmin list shadows /for=D:
    vssadmin list shadowstorage /for=D:
    Get-CimInstance Win32_ShadowCopy | Select-Object ID, VolumeName, InstallDate, DeviceObject | Format-List
}

Run 'LIXEIRA DE D:' {
    $rb = 'D:\$Recycle.Bin'
    if (Test-Path -LiteralPath $rb) {
        Get-ChildItem -LiteralPath $rb -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object { '{0}  {1}' -f (SizeOf $_.FullName), $_.Name }
    } else { 'SEM_LIXEIRA_EM_D' }
}

Run 'PASTAS DE PRIMEIRO NIVEL DE D:\ (procura dados movidos em vez de apagados)' {
    Get-ChildItem -LiteralPath 'D:\' -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        '{0}  {1}  criada={2}  alterada={3}' -f (SizeOf $_.FullName), $_.FullName, $_.CreationTime.ToString('yyyy-MM-dd HH:mm'), $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')
    }
}

Section 'DIARIO USN DE D: (quais arquivos foram apagados e quando)'
try {
    $raw = Join-Path $WorkDir 'USN_D_RAW.csv'
    foreach ($line in ((fsutil usn queryjournal D: 2>&1 | Out-String) -split "`r?`n")) { if ($line.Trim()) { Log $line.TrimEnd() } }
    cmd /c ('fsutil usn readjournal D: csv > "' + $raw + '" 2>&1') | Out-Null
    $rawLen = (Get-Item -LiteralPath $raw).Length
    Log ('USN_BRUTO=' + $raw + ' BYTES=' + $rawLen)
    if ($rawLen -lt 4096) { foreach ($l in (Get-Content -LiteralPath $raw)) { Log ('USN_SAIDA: ' + $l) } }
    $deletes = Join-Path $LogDir 'USN_D_DELECOES.csv'
    $writer = New-Object IO.StreamWriter($deletes, $false, $Utf8)
    $count = 0; $csv = 0; $headerSeen = $false
    $byHour = @{}; $byExt = @{}
    $first = New-Object Collections.Generic.List[string]; $last = New-Object Collections.Generic.Queue[string]
    try {
        $reader = New-Object IO.StreamReader($raw)
        try {
            while ($null -ne ($line = $reader.ReadLine())) {
                if (-not $headerSeen -and $line -match '^Usn,') { $writer.WriteLine($line); $headerSeen = $true; continue }
                # Reason = primeiro hexadecimal de 8 digitos; bit 0x200 = USN_REASON_FILE_DELETE (independe do idioma).
                $isDelete = $line.IndexOf('File delete', [StringComparison]::OrdinalIgnoreCase) -ge 0
                $mm = [regex]::Match($line, '\b0x([0-9a-fA-F]{8})\b')
                if ($mm.Success -and (([Convert]::ToUInt32($mm.Groups[1].Value, 16) -band 0x200) -ne 0)) { $isDelete = $true }
                if (-not $isDelete) { continue }
                $writer.WriteLine($line); $count++
                if ($line -match '\.csv') { $csv++ }
                $t = [regex]::Match($line, '\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}[ T]\d{1,2}')
                $hk = if ($t.Success) { $t.Value } else { '?' }
                if ($byHour.ContainsKey($hk)) { $byHour[$hk]++ } else { $byHour[$hk] = 1 }
                $e = [regex]::Match($line, '\.([A-Za-z0-9]{1,8})"?,')
                $ek = if ($e.Success) { $e.Groups[1].Value.ToLower() } else { '(sem extensao/pasta)' }
                if ($byExt.ContainsKey($ek)) { $byExt[$ek]++ } else { $byExt[$ek] = 1 }
                if ($first.Count -lt 20) { $first.Add($line) }
                $last.Enqueue($line); if ($last.Count -gt 20) { [void]$last.Dequeue() }
            }
        } finally { $reader.Dispose() }
    } finally { $writer.Dispose() }
    Log ('USN_REGISTROS_DE_DELECAO=' + $count + ' ; COM_.csv=' + $csv)
    Log ('USN_DELECOES_ARQUIVO=' + $deletes)
    Log '-- delecoes por data/hora (dd/mm/aaaa hh) --'
    foreach ($k in ($byHour.Keys | Sort-Object)) { Log ('  ' + $k + 'h  ' + $byHour[$k]) }
    Log '-- delecoes por extensao (top 15) --'
    foreach ($kv in ($byExt.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 15)) { Log ('  ' + $kv.Key + '  ' + $kv.Value) }
    Log '-- primeiras delecoes registradas --'; foreach ($l in $first) { Log $l }
    Log '-- ultimas delecoes registradas --'; foreach ($l in $last) { Log $l }
} catch { Log ('ERRO_USN=' + $_.Exception.Message) }

Run 'HISTORICO DO POWERSHELL QUE MENCIONA D:, Base CSV OU EXCLUSAO' {
    $h = Join-Path $env:APPDATA 'Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt'
    if (Test-Path -LiteralPath $h) {
        $n = 0
        Get-Content -LiteralPath $h -ErrorAction SilentlyContinue | ForEach-Object {
            $n++
            if ($_ -match 'Base CSV|Remove-Item|\brmdir\b|\brd\b|\bdel\b|\brm\b|rmtree|Format-Volume|robocopy .*/(MIR|PURGE)|D:\\') { 'linha {0}: {1}' -f $n, $_ }
        } | Select-Object -Last 200
    } else { 'SEM_HISTORICO ' + $h }
}

Run 'SESSOES DE AGENTES LOCAIS (Codex/Claude) QUE MENCIONAM Base CSV (ultimos 7 dias)' {
    $limit = (Get-Date).AddDays(-7)
    foreach ($root in @('C:\Users\silvi\.codex\sessions', 'C:\Users\silvi\.codex\history.jsonl', 'C:\Users\silvi\.claude\projects')) {
        if (-not (Test-Path -LiteralPath $root)) { 'AUSENTE ' + $root; continue }
        Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $limit } | ForEach-Object {
            $hits = @(Select-String -LiteralPath $_.FullName -Pattern 'Base CSV' -SimpleMatch -ErrorAction SilentlyContinue)
            if ($hits.Count) {
                $del = @($hits | Where-Object { $_.Line -match 'Remove-Item|rmtree|rmdir|\brm -|\bdel |Delete\(|unlink|-Recurse' })
                '{0}  mencoes={1}  com_exclusao={2}  {3}' -f $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $hits.Count, $del.Count, $_.FullName
                $del | Select-Object -First 5 | ForEach-Object { '    ' + $(if ($_.Line.Length -gt 300) { $_.Line.Substring(0, 300) } else { $_.Line }) }
            }
        }
    }
}

Run 'SCRIPTS RECENTES (14 dias) EM Downloads QUE MENCIONAM Base CSV E EXCLUSAO' {
    $limit = (Get-Date).AddDays(-14)
    foreach ($dl in $Downloads) {
        if (-not (Test-Path -LiteralPath $dl)) { continue }
        Get-ChildItem -LiteralPath $dl -Recurse -File -Include *.ps1, *.py, *.bat, *.cmd -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $limit } | ForEach-Object {
            $txt = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
            if ($txt -and $txt -match 'Base CSV' -and $txt -match 'Remove-Item|rmtree|rmdir|os\.remove|unlink|\bdel /|\brd /s') {
                '{0}  {1}' -f $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $_.FullName
            }
        }
    }
}

Run 'EXECUCOES RECENTES (7 dias) EM Downloads\*_RUNS' {
    $limit = (Get-Date).AddDays(-7)
    foreach ($dl in $Downloads) {
        Get-ChildItem -LiteralPath $dl -Directory -Filter '*_RUNS' -ErrorAction SilentlyContinue | ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Directory -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $limit } |
                ForEach-Object { '{0}  {1}' -f $_.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'), $_.FullName }
        }
    }
}

Log ''
Log ('FIM=' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
Log ('ENVIE=' + $LogDir + ' (RUN_LOG.txt e USN_D_DELECOES.csv)')
Log 'Nao grave nada em D: ate decidir a recuperacao.'
exit 0
