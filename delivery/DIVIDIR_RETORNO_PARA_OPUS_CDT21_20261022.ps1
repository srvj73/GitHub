#requires -Version 5.1
# TICKSTORE CDT21 - TRANSPORTE DO RETORNO NATIVO AO OPUS EM PARTES MENORES QUE O LIMITE DE ANEXO.
# Divide, byte a byte, o ZIP de retorno (ENVIAR_AO_OPUS_*.zip) em partes de no maximo -ParteMB megabytes (padrao 20).
# Cada parte e um ZIP valido com um pedaco exato do original (BYTEPART_kk_DE_nn.bin) e o mesmo TRANSPORTE_MANIFEST.json
# (SHA-256 e tamanho do original e de cada pedaco). O Opus remonta e confere o SHA-256 do original antes de usar.
# Somente leitura sobre o retorno original; nao executa codigo TICKSTORE; nao toca o D:.
# Execute a partir de PS C:\Users\silvi> (sem cd):
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\DIVIDIR_RETORNO_PARA_OPUS_CDT21_20261022.ps1"
# Sem -Retorno, escolhe o ENVIAR_AO_OPUS_CDT21_G5_V005_*.zip mais recente em C:\Users\silvi\Downloads\CDT21_G5_V005_RUNS.
# Para outro arquivo: -Retorno "<caminho completo do ZIP>".
# Log sempre em pasta absoluta fixa, nova a cada execucao, independente da pasta atual:
#   C:\Users\silvi\Downloads\CDT21_TRANSPORTE_RUNS\DIVIDIR_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt
# As partes ficam na mesma pasta do log. Anexe todas as partes ao Opus e cole o log.
[CmdletBinding()]
param(
    [string]$Retorno = '',
    [ValidateRange(1, 28)][int]$ParteMB = 20
)
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$RunsRoot = 'C:\Users\silvi\Downloads\CDT21_TRANSPORTE_RUNS'
$SearchRoot = 'C:\Users\silvi\Downloads\CDT21_G5_V005_RUNS'
$SearchFilter = 'ENVIAR_AO_OPUS_CDT21_G5_V005_*.zip'
$Schema = 'CDT21_OPUS_RETURN_TRANSPORT_V001'
$script:RunLog = ''

function Log([string]$Line) {
    Write-Output $Line
    if ($script:RunLog -ne '') { [IO.File]::AppendAllText($script:RunLog, $Line + "`r`n", (New-Object Text.UTF8Encoding($false))) }
}
function Require([bool]$Condition, [string]$Reason) { if (-not $Condition) { throw $Reason } }
function Hex([byte[]]$Bytes) { return ([BitConverter]::ToString($Bytes)).Replace('-', '') }
function NewSha { return [Security.Cryptography.SHA256]::Create() }
function Finish($Sha) { [void]$Sha.TransformFinalBlock([byte[]]::new(0), 0, 0); $h = Hex $Sha.Hash; $Sha.Dispose(); return $h }

$exit = 2
try {
    $stamp = (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID
    [void][IO.Directory]::CreateDirectory($RunsRoot)
    $runDir = Join-Path $RunsRoot ('DIVIDIR_' + $stamp)
    Require (-not ([IO.Directory]::Exists($runDir) -or [IO.File]::Exists($runDir))) 'RUN_DIR_COLLISION'
    [void][IO.Directory]::CreateDirectory($runDir)
    $script:RunLog = Join-Path $runDir 'RUN_LOG.txt'
    Log 'RESULT_CONTEXT=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressao De Ticks 21'
    Log ('RUN_LOG=' + $script:RunLog)
    Log ('SCRIPT=' + $PSCommandPath + ' SHA256=' + (Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash)
    Log 'MODO=TRANSPORTE_SOMENTE_LEITURA (nao executa TICKSTORE; nao toca o D:)'

    if ($Retorno -eq '') {
        Require ([IO.Directory]::Exists($SearchRoot)) ('PASTA_DE_RETORNOS_AUSENTE:' + $SearchRoot)
        $found = @(Get-ChildItem -LiteralPath $SearchRoot -Recurse -File -Filter $SearchFilter | Sort-Object LastWriteTimeUtc -Descending)
        Require ($found.Count -ge 1) 'NENHUM_RETORNO_ENCONTRADO'
        foreach ($f in $found) { Log ('CANDIDATO=' + $f.FullName + ' BYTES=' + $f.Length + ' MODIFICADO=' + $f.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')) }
        $Retorno = $found[0].FullName
    }
    $src = [IO.Path]::GetFullPath($Retorno)
    Require ([IO.File]::Exists($src)) ('RETORNO_AUSENTE:' + $src)
    Require ($src.EndsWith('.zip', [StringComparison]::OrdinalIgnoreCase)) 'RETORNO_NAO_E_ZIP'
    $size = (New-Object IO.FileInfo($src)).Length
    $partBytes = [long]$ParteMB * 1000000
    $count = [int][Math]::Ceiling($size / [double]$partBytes)
    Require ($count -ge 1 -and $count -le 99) 'NUMERO_DE_PARTES'
    Log ('RETORNO=' + $src + ' BYTES=' + $size + ' PARTES=' + $count + ' PARTE_MAX_BYTES=' + $partBytes)

    # Passo 1 (leitura): SHA-256 do original e de cada pedaco, sem escrever nada.
    $buf = New-Object byte[] 1048576
    $whole = NewSha
    $parts = @()
    $in = [IO.File]::Open($src, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        for ($i = 1; $i -le $count; $i++) {
            $want = [Math]::Min($partBytes, $size - ($i - 1) * $partBytes)
            $ps = NewSha; $left = $want
            while ($left -gt 0) {
                $n = $in.Read($buf, 0, [int][Math]::Min($buf.Length, $left))
                Require ($n -gt 0) 'LEITURA_CURTA'
                [void]$ps.TransformBlock($buf, 0, $n, $null, 0); [void]$whole.TransformBlock($buf, 0, $n, $null, 0)
                $left -= $n
            }
            $parts += [ordered]@{ index = $i; filename = ('BYTEPART_{0:D2}_DE_{1:D2}.bin' -f $i, $count); size_bytes = $want; sha256 = (Finish $ps) }
        }
        Require ($in.Read($buf, 0, 1) -eq 0) 'ARQUIVO_CRESCEU_DURANTE_A_LEITURA'
    } finally { $in.Dispose() }
    $origSha = Finish $whole
    $declared = (Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash
    Require ($declared -ceq $origSha) 'SHA_DO_ORIGINAL_INSTAVEL'
    Log ('ORIGINAL_SHA256=' + $origSha)

    $base = [IO.Path]::GetFileNameWithoutExtension($src)
    $manifest = [ordered]@{
        schema = $Schema; purpose = 'Transporte byte a byte do retorno nativo ao Opus; nao certifica nada.'
        original_filename = [IO.Path]::GetFileName($src); original_size_bytes = $size; original_sha256 = $origSha
        part_max_bytes = $partBytes; parts = $parts; created_local = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff')
        route = 'RESULT_RETURN_TO=Opus | ORIGIN=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressao De Ticks 21'
    }
    $mjson = ($manifest | ConvertTo-Json -Depth 5)
    $mbytes = (New-Object Text.UTF8Encoding($false)).GetBytes($mjson)
    [IO.File]::WriteAllBytes((Join-Path $runDir 'TRANSPORTE_MANIFEST.json'), $mbytes)

    # Passo 2: cada parte = ZIP novo com o pedaco exato + o manifesto (criacao exclusiva, nunca sobrescreve).
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $outs = @()
    $in = [IO.File]::Open($src, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        foreach ($p in $parts) {
            $out = Join-Path $runDir ('{0}_PARTE_{1:D2}_DE_{2:D2}.zip' -f $base, $p.index, $count)
            $fs = [IO.File]::Open($out, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            $zip = New-Object IO.Compression.ZipArchive($fs, [IO.Compression.ZipArchiveMode]::Create, $false)
            try {
                $e = $zip.CreateEntry('TRANSPORTE_MANIFEST.json', [IO.Compression.CompressionLevel]::Optimal)
                $s = $e.Open(); try { $s.Write($mbytes, 0, $mbytes.Length) } finally { $s.Dispose() }
                $e = $zip.CreateEntry($p.filename, [IO.Compression.CompressionLevel]::NoCompression)
                $s = $e.Open(); $left = $p.size_bytes
                try {
                    while ($left -gt 0) {
                        $n = $in.Read($buf, 0, [int][Math]::Min($buf.Length, $left))
                        Require ($n -gt 0) 'LEITURA_CURTA'
                        $s.Write($buf, 0, $n); $left -= $n
                    }
                } finally { $s.Dispose() }
            } finally { $zip.Dispose() }
            $outs += $out
        }
    } finally { $in.Dispose() }

    # Passo 3: releitura das partes gravadas; a concatenacao dos pedacos precisa reproduzir o SHA-256 do original.
    $whole = NewSha
    for ($k = 0; $k -lt $outs.Count; $k++) {
        $p = $parts[$k]
        $zip = [IO.Compression.ZipFile]::OpenRead($outs[$k])
        try {
            $names = @($zip.Entries | ForEach-Object { $_.FullName } | Sort-Object)
            Require (($names -join '|') -ceq ((@($p.filename, 'TRANSPORTE_MANIFEST.json') | Sort-Object) -join '|')) ('PARTE_MEMBROS:' + $p.index)
            $ps = NewSha; $got = 0
            $s = $zip.GetEntry($p.filename).Open()
            try {
                while (($n = $s.Read($buf, 0, $buf.Length)) -gt 0) {
                    [void]$ps.TransformBlock($buf, 0, $n, $null, 0); [void]$whole.TransformBlock($buf, 0, $n, $null, 0); $got += $n
                }
            } finally { $s.Dispose() }
            Require ($got -eq $p.size_bytes -and (Finish $ps) -ceq $p.sha256) ('PARTE_RELIDA_DIFERENTE:' + $p.index)
        } finally { $zip.Dispose() }
        $len = (New-Object IO.FileInfo($outs[$k])).Length
        Require ($len -lt 30000000) ('PARTE_ACIMA_DE_30MB:' + $p.index)
        Log ('ANEXE_PARTE_{0:D2}={1} BYTES={2} SHA256={3}' -f $p.index, $outs[$k], $len, (Get-FileHash -Algorithm SHA256 -LiteralPath $outs[$k]).Hash)
    }
    Require ((Finish $whole) -ceq $origSha) 'CONCATENACAO_DIFERENTE_DO_ORIGINAL'
    Log ('TRANSPORTE=PASS PARTES=' + $count + ' ORIGINAL_SHA256=' + $origSha)
    Log ('PASTA_DAS_PARTES=' + $runDir)
    Log 'Anexe TODAS as partes acima ao Opus (Claude Code), na mesma conversa de engenharia CDT21, e cole este log.'
    Log 'RESULT_RETURN_TO=Opus | ORIGIN=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressao De Ticks 21'
    $exit = 0
} catch {
    Log ('TRANSPORTE_BLOCKED=' + $_.Exception.Message)
    $exit = 2
}
Log ('EXIT_CODE=' + $exit)
exit $exit
