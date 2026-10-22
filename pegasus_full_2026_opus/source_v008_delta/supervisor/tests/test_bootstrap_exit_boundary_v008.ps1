# PEGASUS V008R2 - qualificacao da fronteira de exit/stdio do bootstrap.
# Extrai por AST as funcoes EMBARCADAS do template (bytes reais do bootstrap) e as executa
# contra processos filhos reais. Uso:
#   pwsh -NoProfile -File test_bootstrap_exit_boundary_v008.ps1 -Template <template.ps1> -Python <python> -Out <dir>
param([Parameter(Mandatory)][string]$Template, [Parameter(Mandatory)][string]$Python, [Parameter(Mandatory)][string]$Out)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Tokens = $null; $Errs = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile($Template, [ref]$Tokens, [ref]$Errs)
if ($Errs.Count -gt 0) { throw 'TEMPLATE_PARSE_FAILED' }
$Wanted = @('Write-Log','Write-Utf8NoBom','ConvertTo-PegasusNativeArgument','Get-PegasusExitCode','Resolve-PegasusRelayExit','Invoke-Native','Invoke-NativeExpect')
$Defs = $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
foreach ($W in $Wanted) {
    $D = @($Defs | Where-Object { $_.Name -eq $W })
    if ($D.Count -ne 1) { throw ('FUNCTION_NOT_FOUND_EXACTLY_ONCE ' + $W) }
    . ([ScriptBlock]::Create($D[0].Extent.Text))
}

[void][System.IO.Directory]::CreateDirectory($Out)
$RunRoot = $Out
$Log = Join-Path $Out 'RUN_LOG.txt'
$Facts = [ordered]@{ steps = [ordered]@{} }
$Results = [System.Collections.ArrayList]::new()
function Check([string]$Name, [bool]$Ok, $Detail) {
    [void]$Results.Add([ordered]@{ case = $Name; result = $(if ($Ok) { 'PASS' } else { 'FAIL' }); detail = $Detail })
    Write-Host ($Name + '=' + $(if ($Ok) { 'PASS' } else { 'FAIL' }))
}

# 1) Saida RAPIDA com cada codigo relevante: o defeito R1 lia 0 quando o filho saia rapido.
foreach ($C in @(0, 1, 2, 3, 7, 19, 37, 87, 130, 255)) {
    $Got = Invoke-Native $Python @('-I','-c',('import sys; sys.exit(' + $C + ')')) ('FAST_' + $C) @($C) 60
    Check ('FAST_EXIT_' + $C) ($Got -is [int] -and $Got -eq $C -and $Facts.steps['FAST_' + $C].classification -eq 'MATCH') @{ observed = $Got }
}

# 2) Saida rapida inesperada: classificada MISMATCH (nunca falso PASS) e Expect lanca a tag.
$Got = Invoke-Native $Python @('-I','-c','import sys; sys.exit(3)') 'MISMATCH_3_VS_0' @(0) 60
Check 'MISMATCH_RECORDED' ($Got -eq 3 -and $Facts.steps['MISMATCH_3_VS_0'].classification -eq 'MISMATCH') @{ observed = $Got }
$Threw = $false
try { [void](Invoke-NativeExpect $Python @('-I','-c','import sys; sys.exit(3)') 'EXPECT_THROWS' @(0) 'STEP_FAILED_TAG' 60) } catch { $Threw = $_.Exception.Message.StartsWith('STEP_FAILED_TAG observed=3') }
Check 'EXPECT_MISMATCH_THROWS_TAG' $Threw $null

# 3) Excecao Python nao tratada (exit 1) no filho e propagada como 1.
$Got = Invoke-Native $Python @('-I','-c','raise RuntimeError("boom")') 'UNCAUGHT_EXCEPTION' @(1) 60
$ErrTxt = Get-Content -LiteralPath (Join-Path $Out 'UNCAUGHT_EXCEPTION.stderr.txt') -Raw
Check 'CHILD_EXCEPTION_EXIT_1_AND_STDERR' ($Got -eq 1 -and $ErrTxt -match 'RuntimeError: boom') @{ observed = $Got }

# 4) Saidas grandes simultaneas (2 MB + 2 MB): sem deadlock, bytes integrais, codigo exato.
$Big = "import sys; sys.stdout.write('o'*2097152); sys.stderr.write('e'*2097152); sys.stdout.flush(); sys.stderr.flush(); sys.exit(5)"
$Got = Invoke-Native $Python @('-I','-c',$Big) 'STREAMS_2MB' @(5) 120
$St = $Facts.steps['STREAMS_2MB']
Check 'STREAMS_2MB_NO_DEADLOCK_EXACT_BYTES' ($Got -eq 5 -and $St.stdout_bytes -eq 2097152 -and $St.stderr_bytes -eq 2097152 -and (Get-Item (Join-Path $Out 'STREAMS_2MB.stdout.txt')).Length -eq 2097152) @{ out = $St.stdout_bytes; err = $St.stderr_bytes }

# 5) Filho lento (>10 s): heartbeat registrado e codigo exato.
$Got = Invoke-Native $Python @('-I','-c','import time,sys; time.sleep(12); sys.exit(4)') 'SLOW_12S' @(4) 60
$Hb = @(Select-String -LiteralPath $Log -Pattern 'BOOTSTRAP_HEARTBEAT label=SLOW_12S').Count
Check 'SLOW_CHILD_HEARTBEAT_AND_EXIT' ($Got -eq 4 -and $Hb -ge 1) @{ observed = $Got; heartbeats = $Hb }

# 6) Watchdog: estoura o prazo, NAO mata, grava recibo de reconciliacao e lanca.
$Marker = Join-Path $Out 'WATCHDOG_CHILD_FINISHED.txt'
$Code = "import time,sys; time.sleep(25); open(sys.argv[1],'w').write('done'); sys.exit(0)"
$Msg = ''
try { [void](Invoke-Native $Python @('-I','-c',$Code,$Marker) 'WATCHDOG' @(0) 3) } catch { $Msg = $_.Exception.Message }
$RecPath = Join-Path $Out 'TIMEOUT_RECONCILE_WATCHDOG.json'
$Rec = if (Test-Path $RecPath) { Get-Content $RecPath -Raw | ConvertFrom-Json } else { $null }
Start-Sleep -Seconds 20
Check 'WATCHDOG_THROWS_NO_KILL_RECONCILE_RECEIPT' ($Msg.StartsWith('NATIVE_TIMEOUT_NO_KILL_RECONCILE label=WATCHDOG') -and $null -ne $Rec -and $Rec.kill_performed -eq $false -and $Rec.pid -gt 0 -and (Test-Path $Marker)) @{ message = $Msg; child_finished_naturally = (Test-Path $Marker) }

# 7) argv: serializacao V003 preserva espacos, aspas e barra final.
$ArgvOut = Join-Path $Out 'ARGV.json'
$Got = Invoke-Native $Python @('-I','-c',"import sys,json; open(sys.argv[1],'w').write(json.dumps(sys.argv[2:])); sys.exit(37)",$ArgvOut,'space value','literal"quote','tail\') 'ARGV' @(37) 60
$Argv = Get-Content $ArgvOut -Raw | ConvertFrom-Json
Check 'ARGV_EXACT_AND_EXIT_37' ($Got -eq 37 -and $Argv.Count -eq 3 -and $Argv[0] -eq 'space value' -and $Argv[1] -eq 'literal"quote' -and $Argv[2] -eq 'tail\') @{ argv = $Argv }

# 8) Higiene de ambiente: PYTHONPATH removido mesmo se definido no pai; flags definidas.
$env:PYTHONPATH = '/should/not/leak'
$EnvOut = Join-Path $Out 'ENV.json'
$Got = Invoke-Native $Python @('-I','-c',"import os,sys,json; open(sys.argv[1],'w').write(json.dumps({k:os.environ.get(k) for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','PYTHONIOENCODING']}))",$EnvOut) 'ENV' @(0) 60
Remove-Item Env:\PYTHONPATH
$EnvDoc = Get-Content $EnvOut -Raw | ConvertFrom-Json
Check 'ENV_HYGIENE' ($Got -eq 0 -and $null -eq $EnvDoc.PYTHONPATH -and $EnvDoc.PYTHONDONTWRITEBYTECODE -eq '1' -and $EnvDoc.PYTHONNOUSERSITE -eq '1' -and $EnvDoc.PYTHONIOENCODING -eq 'utf-8') @{ env = $EnvDoc }

# 9) Get-PegasusExitCode: exit ausente/nao encerrado e FAIL-CLOSED (nunca 0).
$T1 = ''; try { [void](Get-PegasusExitCode ([pscustomobject]@{ HasExited = $true; ExitCode = $null })) } catch { $T1 = $_.Exception.Message }
$T2 = ''; try { [void](Get-PegasusExitCode ([pscustomobject]@{ HasExited = $false; ExitCode = 0 })) } catch { $T2 = $_.Exception.Message }
$T3 = ''; try { [void](Get-PegasusExitCode $null) } catch { $T3 = $_.Exception.Message }
Check 'NULL_EXIT_FAIL_CLOSED' ($T1 -eq 'NATIVE_EXIT_NULL' -and $T2 -eq 'NATIVE_EXIT_READ_BEFORE_EXIT' -and $T3 -eq 'NATIVE_PROCESS_OBJECT_NULL') @{ t1 = $T1; t2 = $T2; t3 = $T3 }

# 10) Relay UAC: exit do processo elevado x exit gravado pelo elevado.
$R = @((Resolve-PegasusRelayExit 0 0), (Resolve-PegasusRelayExit 3 3), (Resolve-PegasusRelayExit 2 2),
       (Resolve-PegasusRelayExit $null 0), (Resolve-PegasusRelayExit 0 $null), (Resolve-PegasusRelayExit 0 3), (Resolve-PegasusRelayExit 3 0))
Check 'UAC_RELAY_RULES' (($R -join ',') -eq '0,3,2,3,3,3,3') @{ results = ($R -join ',') }

$Fail = @($Results | Where-Object { $_.result -ne 'PASS' }).Count
$Doc = [ordered]@{ schema = 'PEGASUS_FULL_2026_V008R2_BOOTSTRAP_EXIT_BOUNDARY_TEST'; template_sha256 = (Get-FileHash -LiteralPath $Template -Algorithm SHA256).Hash;
    runtime = $PSVersionTable.PSVersion.ToString(); edition = $PSVersionTable.PSEdition; cases = $Results;
    passed = $Results.Count - $Fail; failed = $Fail; result = $(if ($Fail -eq 0) { 'PASS_ALL' } else { 'FAIL' }) }
[System.IO.File]::WriteAllText((Join-Path $Out 'BOOTSTRAP_EXIT_BOUNDARY_RESULT.json'), ($Doc | ConvertTo-Json -Depth 8))
Write-Host ('BOOTSTRAP_EXIT_BOUNDARY=' + $Doc.result + ' passed=' + $Doc.passed + ' failed=' + $Fail)
exit $(if ($Fail -eq 0) { 0 } else { 1 })
