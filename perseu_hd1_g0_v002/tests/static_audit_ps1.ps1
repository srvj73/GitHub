param([Parameter(Mandatory = $true)][string]$TargetPath)
# External static audit of the generated wrapper (parser tokens/AST, not raw substrings).
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($TargetPath, [ref]$tokens, [ref]$errors)
$automatic = @('args', 'input', 'pid', 'host', 'error', 'matches', '_', 'psitem', 'this', 'true', 'false', 'null',
    'home', 'psscriptroot', 'pscommandpath', 'myinvocation', 'lastexitcode', 'executioncontext', 'shellid',
    'psversiontable', 'foreach', 'switch', 'event', 'eventargs', 'eventsubscriber', 'sender', 'stacktrace',
    'consolefilename', 'nestedpromptlevel', 'profile', 'pwd', 'psboundparameters', 'pscmdlet', 'psculture',
    'psuiculture', 'psdebugcontext', 'pshome', 'psitem', 'ofs', 'iswindows', 'islinux', 'ismacos', 'iscoreclr')
$findings = New-Object System.Collections.Generic.List[string]
foreach ($e in $errors) { $findings.Add('PARSE_ERROR:' + $e.Extent.StartLineNumber + ':' + $e.Message) }
$params = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ParameterAst] }, $true)
foreach ($p in $params) {
    $name = $p.Name.VariablePath.UserPath.ToLowerInvariant()
    if ($automatic -contains $name) { $findings.Add('PARAM_AUTOMATIC_COLLISION:' + $name) }
}
$assigns = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] }, $true)
foreach ($a in $assigns) {
    $left = $a.Left
    if ($left -is [System.Management.Automation.Language.ConvertExpressionAst]) { $left = $left.Child }
    if ($left -is [System.Management.Automation.Language.VariableExpressionAst]) {
        $name = $left.VariablePath.UserPath.ToLowerInvariant()
        if ($name.StartsWith('script:')) { $name = $name.Substring(7) }
        if ($automatic -contains $name) { $findings.Add('ASSIGN_AUTOMATIC_COLLISION:' + $name + ':' + $a.Extent.StartLineNumber) }
    }
}
$loops = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ForEachStatementAst] }, $true)
foreach ($l in $loops) {
    $name = $l.Variable.VariablePath.UserPath.ToLowerInvariant()
    if ($automatic -contains $name) { $findings.Add('FOREACH_AUTOMATIC_COLLISION:' + $name) }
}
$functions = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true))
# PS 5.1 Desktop default aliases are a superset of pwsh ones on Linux; add the Windows-only set explicitly.
$aliasNames = @((Get-Alias).Name | ForEach-Object { $_.ToLowerInvariant() })
$aliasNames += @('curl', 'wget', 'ls', 'cp', 'mv', 'rm', 'cat', 'sort', 'diff', 'tee', 'ps', 'kill', 'sleep', 'write', 'start', 'man', 'mount', 'lp', 'compare', 'sc', 'gwmi', 'iwmi', 'rwmi', 'swmi')
foreach ($f in $functions) {
    $fname = $f.Name.ToLowerInvariant()
    if ($aliasNames -contains $fname) { $findings.Add('FUNCTION_ALIAS_COLLISION:' + $fname) }
    if ($fname.Length -le 1) { $findings.Add('FUNCTION_SINGLE_LETTER:' + $fname) }
    if ($null -ne (Get-Command -Name $f.Name -CommandType Cmdlet -ErrorAction SilentlyContinue)) { $findings.Add('FUNCTION_SHADOWS_CMDLET:' + $fname) }
}
for ($i = 0; $i -lt $tokens.Count - 1; $i++) {
    $t = $tokens[$i]
    if ($t.Kind -eq [System.Management.Automation.Language.TokenKind]::Return) {
        $next = $tokens[$i + 1]
        if ($next.Extent.StartOffset -eq $t.Extent.EndOffset -and $next.Kind -ne [System.Management.Automation.Language.TokenKind]::NewLine) {
            $findings.Add('RETURN_TOKEN_GLUE:' + $t.Extent.StartLineNumber)
        }
    }
}
$bytes = [System.IO.File]::ReadAllBytes($TargetPath)
$nonAscii = 0
$bareLf = 0
for ($i = 0; $i -lt $bytes.Length; $i++) {
    if ($bytes[$i] -gt 127) { $nonAscii++ }
    if ($bytes[$i] -eq 10 -and ($i -eq 0 -or $bytes[$i - 1] -ne 13)) { $bareLf++ }
}
if ($nonAscii -gt 0) { $findings.Add('NON_ASCII_BYTES:' + $nonAscii) }
if ($bareLf -gt 0) { $findings.Add('BARE_LF:' + $bareLf) }
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $findings.Add('BOM_PRESENT_UNEXPECTED_FOR_ASCII') }
$summary = [ordered]@{
    parser = 'pwsh ' + $PSVersionTable.PSVersion.ToString() + ' (external; NOT Windows PowerShell 5.1)'
    target = $TargetPath; bytes = $bytes.Length; parse_errors = @($errors).Count; tokens = $tokens.Count
    functions = $functions.Count; parameters = @($params).Count; assignments = @($assigns).Count
    findings = $findings.ToArray(); verdict = $(if ($findings.Count -eq 0) { 'PASS_SANDBOX_PARSER_SCOPE' } else { 'FAIL' })
}
ConvertTo-Json -InputObject $summary -Depth 4
if ($findings.Count -eq 0) { exit 0 } else { exit 1 }
