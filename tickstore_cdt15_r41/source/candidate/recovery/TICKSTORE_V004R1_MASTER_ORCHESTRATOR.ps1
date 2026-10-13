#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Position=0)][ValidateSet('plan','run','status','stop','resume','reconcile','confirm-stale-lock','ingest-stage-b','postfull','attach')][string]$Command='plan',[string]$Until,[string]$LockSha)
$ErrorActionPreference='Stop';Set-StrictMode -Version 2.0
if($PSVersionTable.PSEdition-ne'Desktop'-or$PSVersionTable.PSVersion.Major-ne5-or$PSVersionTable.PSVersion.Minor-ne1){throw 'WINDOWS_POWERSHELL_5_1_REQUIRED'}
if((Get-Location).Path-cne'C:\Users\silvi'){throw ('LAUNCH_CWD_REQUIRED=C:\Users\silvi actual='+(Get-Location).Path)}
$Python='C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe';$PythonSha='4942B86A6597E5AEE0128DAA00050ED79BC21F6E709A78EB19CBFEB0C2F39AC9'
if((Get-FileHash -LiteralPath $Python -Algorithm SHA256).Hash.ToUpperInvariant()-cne$PythonSha){throw 'PYTHON_HASH_MISMATCH'}
$tok=$null;$err=$null;[void][Management.Automation.Language.Parser]::ParseFile($PSCommandPath,[ref]$tok,[ref]$err);if(@($err).Count-ne0){throw ('TARGET_SHELL_PARSE_FAIL='+@($err).Count)}
Write-Host 'TARGET_SHELL_PARSE=PASS'
$M=[IO.Path]::Combine($PSScriptRoot,'modules','orchestrator.py');$A=@('-I','-S','-B',$M,$Command,'--package',$PSScriptRoot,'--python',$Python);if($Until){$A+=@('--until',$Until)};if($LockSha){$A+=@('--lock-sha',$LockSha)}
$old=$ErrorActionPreference;try{$ErrorActionPreference='Continue';& $Python @A;$c=$LASTEXITCODE}finally{$ErrorActionPreference=$old};exit $c
