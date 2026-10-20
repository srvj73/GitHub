#requires -Version 5.1
<#
Corrige TEMP/TMP do usuario quando estao gravados como texto literal nao expandido
(ex.: '%USERPROFILE%\AppData\Local\Temp' em REG_SZ), causa comprovada da falha G0 de 20/10.

Uso a partir de PS C:\Users\silvi> (sem cd):
  Diagnostico (somente leitura):
    powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\FIX_TEMP_ENV_USUARIO_20261020.ps1"
  Aplicar a correcao (com backup .reg antes):
    powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\FIX_TEMP_ENV_USUARIO_20261020.ps1" -Apply

Altera somente HKCU\Environment (TEMP e TMP do proprio usuario). Nao requer administrador.
Nao apaga nenhuma pasta. Desfazer: reg import "<pasta do log>\HKCU_Environment_BACKUP.reg"
Codigos: 0 OK; 2 bloqueado sem alteracao; 3 falha apos tentativa de alteracao.
#>
[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'

# ---- Constantes fixas (regra do titular: log em pasta absoluta definida pelo script) ----
$DownloadsRoot = 'C:\Users\silvi\OneDrive\Downloads'
$RunsParent    = 'C:\Users\silvi\OneDrive\Downloads\WINDOWS_TEMP_ENV_RUNS'
$ExpectedUser  = 'silvi'
$Canonical     = '%USERPROFILE%\AppData\Local\Temp'
$Names         = @('TEMP', 'TMP')

$Mode = 'DIAGNOSE'; if ($Apply) { $Mode = 'APPLY' }
$ScriptExit = 2
$Changed = $false
$RunLog = $null

function Write-Run([string]$Line) {
    Write-Host $Line
    if ($script:RunLog) { [IO.File]::AppendAllText($script:RunLog, $Line + "`r`n", (New-Object System.Text.UTF8Encoding($false))) }
}

function Get-EnvEntry([Microsoft.Win32.RegistryKey]$Key, [string]$Name) {
    $raw = $Key.GetValue($Name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    if ($null -eq $raw) { return [ordered]@{ name = $Name; present = $false } }
    $kind = $Key.GetValueKind($Name).ToString()
    $expanded = [Environment]::ExpandEnvironmentVariables([string]$raw)
    $broken = ($kind -eq 'String' -and ([string]$raw).Contains('%'))
    return [ordered]@{ name = $Name; present = $true; raw = [string]$raw; kind = $kind; expanded = $expanded
                       literal_percent_not_expanded = $broken; expanded_is_absolute = [IO.Path]::IsPathRooted($expanded) }
}

try {
    if (-not [IO.Directory]::Exists($DownloadsRoot)) { throw ('DOWNLOADS_ROOT_ABSENT: ' + $DownloadsRoot) }
    if (-not [IO.Directory]::Exists($RunsParent)) { [void][IO.Directory]::CreateDirectory($RunsParent) }
    $RunDir = Join-Path $RunsParent ($Mode + '_' + (Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + $PID)
    if ([IO.Directory]::Exists($RunDir)) { throw ('RUN_DIR_COLLISION: ' + $RunDir) }
    [void][IO.Directory]::CreateDirectory($RunDir)
    $RunLog = Join-Path $RunDir 'RUN_LOG.txt'
    Write-Run ('MODE=' + $Mode)
    Write-Run ('RUN_LOG=' + $RunLog)
    Write-Run ('SCRIPT=' + $PSCommandPath + ' SHA256=' + (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash)

    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'REQUIRED_WINDOWS_POWERSHELL_5_1' }
    if ([Environment]::UserName -ne $ExpectedUser) { throw ('WRONG_USER: ' + [Environment]::UserName + ' (HKCU seria de outro usuario)') }
    $profileDir = [Environment]::GetFolderPath('UserProfile')
    $target = Join-Path $profileDir 'AppData\Local\Temp'
    if (-not [IO.Directory]::Exists($target)) { throw ('CANONICAL_TEMP_DIR_ABSENT: ' + $target) }
    $item = Get-Item -LiteralPath $target -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw ('CANONICAL_TEMP_IS_REPARSE_POINT: ' + $target) }
    Write-Run ('CANONICAL_TEMP_TARGET=' + $target)

    # Estado atual: usuario (HKCU) e maquina (HKLM, somente leitura) e o processo corrente.
    $user = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $false)
    $machine = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey('SYSTEM\CurrentControlSet\Control\Session Manager\Environment', $false)
    $before = @()
    foreach ($n in $Names) {
        $u = Get-EnvEntry $user $n
        $m = Get-EnvEntry $machine $n
        $before += [ordered]@{ name = $n; user = $u; machine_readonly = $m; this_process = [Environment]::GetEnvironmentVariable($n, 'Process') }
        Write-Run ('USER_' + $n + ' RAW=' + $u.raw + ' KIND=' + $u.kind + ' EXPANDED=' + $u.expanded + ' LITERAL_PERCENT_NOT_EXPANDED=' + $u.literal_percent_not_expanded)
        Write-Run ('PROCESS_' + $n + '=' + [Environment]::GetEnvironmentVariable($n, 'Process'))
    }
    $user.Close(); $machine.Close()
    $stray = Join-Path $profileDir '%USERPROFILE%'
    if ([IO.Directory]::Exists($stray)) { Write-Run ('STRAY_FOLDER_PRESENT_NOT_DELETED=' + $stray) }

    $needs = @($before | Where-Object { -not $_.user.present -or $_.user.literal_percent_not_expanded -or -not $_.user.expanded_is_absolute })
    Write-Run ('NEEDS_FIX=' + ((@($needs | ForEach-Object { $_.name })) -join ','))
    if ($needs.Count -eq 0) {
        Write-Run 'RESULT=NO_CHANGE_NEEDED'
        $ScriptExit = 0
    } elseif (-not $Apply) {
        Write-Run 'RESULT=PROBLEM_FOUND_NO_CHANGE_MADE (rode novamente com -Apply)'
        $ScriptExit = 0
    } else {
        $running = $null
        if ([System.Threading.Mutex]::TryOpenExisting('Local\CDT20_PRE_G06_INTEGRATED_LAUNCHER', [ref]$running)) {
            $running.Dispose(); throw 'CDT20_LAUNCHER_STILL_RUNNING: aguarde o termino antes de alterar o ambiente'
        }
        $backup = Join-Path $RunDir 'HKCU_Environment_BACKUP.reg'
        $reg = Join-Path $env:SystemRoot 'System32\reg.exe'
        & $reg export 'HKCU\Environment' $backup /y | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not [IO.File]::Exists($backup)) { throw 'REGISTRY_BACKUP_FAILED' }
        Write-Run ('BACKUP=' + $backup + ' SHA256=' + (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash)
        $w = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
        try {
            foreach ($row in $needs) {
                $Changed = $true
                $w.SetValue($row.name, $Canonical, [Microsoft.Win32.RegistryValueKind]::ExpandString)
                Write-Run ('SET USER_' + $row.name + '=' + $Canonical + ' KIND=ExpandString')
            }
        } finally { $w.Close() }
        # Avisa o Explorer para que novas janelas recebam o ambiente corrigido.
        Add-Type -Namespace Cdt20 -Name Native -MemberDefinition @'
[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
public static extern System.IntPtr SendMessageTimeout(System.IntPtr hWnd, uint Msg, System.UIntPtr wParam, string lParam, uint flags, uint timeout, out System.UIntPtr result);
'@
        $res = [UIntPtr]::Zero
        [void][Cdt20.Native]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$res)
        Write-Run 'BROADCAST=WM_SETTINGCHANGE_ENVIRONMENT'
        # Leitura de volta.
        $check = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $false)
        try {
            foreach ($n in @($needs | ForEach-Object { $_.name })) {
                $e = Get-EnvEntry $check $n
                Write-Run ('AFTER_USER_' + $n + ' RAW=' + $e.raw + ' KIND=' + $e.kind + ' EXPANDED=' + $e.expanded)
                if ($e.kind -ne 'ExpandString' -or $e.expanded -ne $target) { throw ('READBACK_MISMATCH: ' + $n) }
            }
        } finally { $check.Close() }
        Write-Run 'RESULT=FIXED (abra uma NOVA janela do PowerShell para usar o TEMP corrigido)'
        $ScriptExit = 0
    }
} catch {
    Write-Run ('BLOCKED=' + $_.Exception.Message)
    if ($Changed) { $ScriptExit = 3 } else { $ScriptExit = 2 }
} finally {
    Write-Run ('EXIT_CODE=' + $ScriptExit)
}
exit $ScriptExit
