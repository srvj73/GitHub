#requires -Version 5.1
# DIAGNOSTICO SOMENTE LEITURA do volume D: apos perda de dados. NAO grava nada em D:.
# Execute a partir de PS C:\Users\silvi> em PowerShell 5.1 ELEVADO (Administrador):
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_DIAG_D_PERDA_READONLY_20261021.ps1"
# Log sempre em pasta absoluta fixa, nova a cada execucao, independente da pasta atual:
#   C:\Users\silvi\OneDrive\Downloads\DIAG_D_RUNS\DIAG_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt
# Dados volumosos temporarios (diario USN bruto) ficam em C:\Users\silvi\AppData\Local\DIAG_D\<carimbo>\ (C:, fora do OneDrive).
[CmdletBinding()]
param()
$ErrorActionPreference = 'Continue'
Set-StrictMode -Version 2.0

$Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
$LogDir = 'C:\Users\silvi\OneDrive\Downloads\DIAG_D_RUNS\DIAG_' + $Stamp
$WorkDir = 'C:\Users\silvi\AppData\Local\DIAG_D\' + $Stamp
foreach ($d in @($LogDir, $WorkDir)) {
    if ($d.Substring(0, 2) -ne 'C:') { throw 'DESTINO_FORA_DE_C' }
    New-Item -ItemType Directory -Path $d -ErrorAction Stop | Out-Null
}
$Log = Join-Path $LogDir 'RUN_LOG.txt'
$Utf8 = New-Object Text.UTF8Encoding($false)

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
    $m = Get-ChildItem -LiteralPath $Path -Force -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum
    $sum = 0; if ($m.Sum) { $sum = [double]$m.Sum }
    return ('{0,10:N2} GB  {1,9} arquivos' -f ($sum / 1GB), $m.Count)
}

Log 'DIAGNOSTICO_D_PERDA=SOMENTE_LEITURA; NENHUMA_GRAVACAO_EM_D'
Log ('RUN_LOG=' + $Log)
Log ('INICIO=' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Log ('ELEVADO=' + $admin + $(if (-not $admin) { ' (sem elevacao, VSS/USN/Lixeira ficam incompletos; reabra como Administrador)' } else { '' }))

Run 'PROCESSOS PYTHON/POWERSHELL/CMD EM EXECUCAO (algo ainda pode estar apagando)' {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='powershell.exe' OR Name='pwsh.exe' OR Name='cmd.exe' OR Name='robocopy.exe'" |
        Select-Object ProcessId, Name, @{n='Inicio';e={$_.CreationDate}}, CommandLine | Format-List
}

Run 'VOLUME D:' {
    Get-Volume -DriveLetter D | Format-List DriveLetter, FileSystemLabel, FileSystem, HealthStatus, @{n='TamanhoGB';e={[math]::Round($_.Size/1GB,2)}}, @{n='LivreGB';e={[math]::Round($_.SizeRemaining/1GB,2)}}
}

Run 'DISCO FISICO DE D: (SSD com TRIM reduz as chances de recuperacao por varredura)' {
    $disk = Get-Partition -DriveLetter D | Get-Disk
    $disk | Format-List Number, FriendlyName, BusType, PartitionStyle, @{n='TamanhoGB';e={[math]::Round($_.Size/1GB,2)}}
    Get-PhysicalDisk | Format-Table DeviceId, FriendlyName, MediaType, BusType, @{n='TamanhoGB';e={[math]::Round($_.Size/1GB,2)}} -AutoSize
    fsutil behavior query DisableDeleteNotify
}

Run 'COPIAS DE SOMBRA (VSS) DE D: (principal via de recuperacao se existirem)' {
    vssadmin list shadows /for=D:
    vssadmin list shadowstorage /for=D:
}

Run 'LIXEIRA DE D:' {
    $rb = 'D:\$Recycle.Bin'
    if (Test-Path -LiteralPath $rb) {
        Get-ChildItem -LiteralPath $rb -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object { '{0}  {1}' -f $_.Name, (SizeOf $_.FullName) }
    } else { 'SEM_LIXEIRA_EM_D' }
}

Run 'PASTAS DE PRIMEIRO NIVEL DE D:\ (procura dados movidos em vez de apagados)' {
    Get-ChildItem -LiteralPath 'D:\' -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        '{0}  {1}  modificada={2}' -f (SizeOf $_.FullName), $_.FullName, $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')
    }
}

Run 'D:\Base CSV - PRIMEIRO NIVEL' {
    $base = 'D:\Base CSV'
    if (Test-Path -LiteralPath $base) {
        Get-ChildItem -LiteralPath $base -Force -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.PSIsContainer) { '{0}  {1}  modificada={2}' -f (SizeOf $_.FullName), $_.Name, $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm') }
            else { '{0,10:N2} GB  arquivo    {1}  modificado={2}' -f ($_.Length / 1GB), $_.Name, $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm') }
        }
    } else { 'PASTA_D_BASE_CSV_NAO_EXISTE' }
}

Section 'DIARIO USN DE D: (quais arquivos foram apagados e quando)'
try {
    $raw = Join-Path $WorkDir 'USN_D_RAW.csv'
    $q = (fsutil usn queryjournal D: 2>&1 | Out-String)
    foreach ($line in ($q -split "`r?`n")) { if ($line.Trim()) { Log $line.TrimEnd() } }
    cmd /c ('fsutil usn readjournal D: csv > "' + $raw + '"') | Out-Null
    if (Test-Path -LiteralPath $raw) {
        Log ('USN_BRUTO=' + $raw + ' BYTES=' + (Get-Item -LiteralPath $raw).Length)
        $deletes = Join-Path $LogDir 'USN_D_DELECOES.csv'
        $header = Get-Content -LiteralPath $raw -TotalCount 40 | Where-Object { $_ -match '^Usn,' } | Select-Object -First 1
        $writer = New-Object IO.StreamWriter($deletes, $false, $Utf8)
        $count = 0; $csv = 0; $first = New-Object Collections.Generic.List[string]; $last = New-Object Collections.Generic.Queue[string]
        try {
            if ($header) { $writer.WriteLine($header) }
            $reader = New-Object IO.StreamReader($raw)
            try {
                while ($null -ne ($line = $reader.ReadLine())) {
                    # Reason = primeiro hexadecimal de 8 digitos da linha; bit 0x200 = USN_REASON_FILE_DELETE (independe do idioma).
                    $isDelete = $line.IndexOf('File delete', [StringComparison]::OrdinalIgnoreCase) -ge 0
                    $mm = [regex]::Match($line, '\b0x([0-9a-fA-F]{8})\b')
                    if ($mm.Success -and (([Convert]::ToUInt32($mm.Groups[1].Value, 16) -band 0x200) -ne 0)) { $isDelete = $true }
                    if ($isDelete) {
                        $writer.WriteLine($line); $count++
                        if ($line -match '\.csv') { $csv++ }
                        if ($first.Count -lt 15) { $first.Add($line) }
                        $last.Enqueue($line); if ($last.Count -gt 15) { [void]$last.Dequeue() }
                    }
                }
            } finally { $reader.Dispose() }
        } finally { $writer.Dispose() }
        Log ('USN_REGISTROS_DE_DELECAO=' + $count + ' ; DELES_COM_.csv=' + $csv)
        Log ('USN_DELECOES_ARQUIVO=' + $deletes)
        if ($header) { Log ('CABECALHO=' + $header) }
        Log '-- primeiras delecoes registradas --'; foreach ($l in $first) { Log $l }
        Log '-- ultimas delecoes registradas --'; foreach ($l in $last) { Log $l }
    } else { Log 'USN_BRUTO_NAO_GERADO' }
} catch { Log ('ERRO_USN=' + $_.Exception.Message) }

Run 'EXECUCOES RECENTES (7 dias) EM Downloads\*_RUNS' {
    $limit = (Get-Date).AddDays(-7)
    Get-ChildItem -LiteralPath 'C:\Users\silvi\OneDrive\Downloads' -Directory -Filter '*_RUNS' -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -Directory -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $limit } |
            ForEach-Object { '{0}  {1}' -f $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $_.FullName }
    }
}

Run 'RUN_LOGs RECENTES QUE MENCIONAM D:\Base CSV' {
    $limit = (Get-Date).AddDays(-7)
    Get-ChildItem -LiteralPath 'C:\Users\silvi\OneDrive\Downloads' -Recurse -File -Filter 'RUN_LOG.txt' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $limit } | ForEach-Object {
            $hits = @(Select-String -LiteralPath $_.FullName -Pattern 'Base CSV' -SimpleMatch -ErrorAction SilentlyContinue)
            if ($hits.Count) { '{0}  ocorrencias={1}  {2}' -f $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $hits.Count, $_.FullName
                               $hits | Select-Object -First 5 | ForEach-Object { '    ' + $_.Line.Trim() } }
        }
}

Run 'LABORATORIOS TICKSTORE (somente listagem)' {
    foreach ($p in @('C:\Users\silvi\AppData\Local\CDT20_R08', 'C:\Users\silvi\AppData\Local\CDT21_F01_G0', 'C:\Users\silvi\AppData\Local\CDT21_G5_V003', 'D:\TICKSTORE_CDT19_PRE_G06_LABS')) {
        if (Test-Path -LiteralPath $p) {
            Get-ChildItem -LiteralPath $p -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object { '{0}  {1}' -f $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $_.FullName }
        } else { 'AUSENTE ' + $p }
    }
}

Log ''
Log ('FIM=' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
Log ('ENVIE_A_PASTA=' + $LogDir + ' (RUN_LOG.txt e USN_D_DELECOES.csv)')
Log 'Nao grave nada em D: ate decidir a recuperacao.'
exit 0
