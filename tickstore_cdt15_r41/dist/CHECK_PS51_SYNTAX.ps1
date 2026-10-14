# TICKSTORE CDT15 - read-only PowerShell 5.1 syntax proof of the delivered bootstraps.
# Run (no cd needed):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\CHECK_PS51_SYNTAX.ps1"
# Parses (never executes) every RUN_TICKSTORE_CDT15_*.ps1 in Downloads with the PS 5.1 parser and
# prints PARSE_OK / PARSE_ERROR with the file SHA-256.  Log: TICKSTORE_RUNS\PS51_SYNTAX_<ts>_<PID>\RUN_LOG.txt
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$Downloads = 'C:\Users\silvi\OneDrive\Downloads'
$LogRoot = 'C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS'
$runDir = Join-Path $LogRoot ('PS51_SYNTAX_' + (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID)
[IO.Directory]::CreateDirectory($runDir) | Out-Null
$log = Join-Path $runDir 'RUN_LOG.txt'
$utf8 = New-Object Text.UTF8Encoding($false)
function Log([string]$l) { Write-Host $l; [IO.File]::AppendAllText($log, $l + "`r`n", $utf8) }
Log ('RESULT_CONTEXT=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compress' + [char]0x00E3 + 'o De Ticks 15')
Log ('POWERSHELL=' + $PSVersionTable.PSVersion.ToString())
$bad = 0; $n = 0
foreach ($f in @(Get-ChildItem -LiteralPath $Downloads -File -Filter 'RUN_TICKSTORE_CDT15_*.ps1')) {
    $n++
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors)
    $sha = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
    if ($errors.Count -eq 0) { Log ('PARSE_OK ' + $f.Name + ' SHA256=' + $sha) }
    else { $bad++; foreach ($e in $errors) { Log ('PARSE_ERROR ' + $f.Name + ' SHA256=' + $sha + ' LINE=' + $e.Extent.StartLineNumber + ' ' + $e.Message) } }
}
Log ('FILES_PARSED=' + $n + ' PARSE_ERRORS=' + $bad)
Log ('RUN_LOG=' + $log)
if ($bad -eq 0 -and $n -gt 0) { exit 0 } else { exit 2 }
