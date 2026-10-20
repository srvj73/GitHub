param([string]$Path)
$t=$null;$e=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Path,[ref]$t,[ref]$e)
$bad=@()
if($e.Count){$bad+='PARSE_ERRORS='+$e.Count}
$ps7=@('TernaryExpressionAst','PipelineChainAst')
foreach($n in $ast.FindAll({param($x) $true},$true)){
  if($ps7 -contains $n.GetType().Name){$bad+='PS7_ONLY_AST:'+$n.GetType().Name+':'+$n.Extent.StartLineNumber}
  if($n -is [System.Management.Automation.Language.BinaryExpressionAst] -and $n.Operator -eq 'QuestionQuestion'){$bad+='PS7_NULL_COALESCE:'+$n.Extent.StartLineNumber}
  if($n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Operator -eq 'QuestionQuestionEquals'){$bad+='PS7_NULL_ASSIGN:'+$n.Extent.StartLineNumber}
  if($n -is [System.Management.Automation.Language.MemberExpressionAst] -and $n.NullConditional){$bad+='PS7_NULL_CONDITIONAL:'+$n.Extent.StartLineNumber}
  if($n -is [System.Management.Automation.Language.AssignmentStatementAst]){
    $l=$n.Left.Extent.Text
    if($l -match '^\$(PID|args|input|_|PSItem|this|true|false|null|Host|PSScriptRoot|PSCommandPath|LASTEXITCODE|Error|matches)$'){$bad+='RESERVED_ASSIGN:'+$l+':'+$n.Extent.StartLineNumber}
  }
  if($n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Join-Path' -and $n.CommandElements.Count -gt 3){$bad+='JOINPATH_3ARGS:'+$n.Extent.StartLineNumber}
}
$raw=[IO.File]::ReadAllBytes($Path)
$bom=($raw.Length -ge 3 -and $raw[0] -eq 0xEF -and $raw[1] -eq 0xBB -and $raw[2] -eq 0xBF)
$nonascii=($raw | Where-Object { $_ -gt 127 }).Count
"BOM=$bom NONASCII_BYTES=$nonascii"
if(-not $bom -and $nonascii){$bad+='NON_ASCII_WITHOUT_BOM'}
if($bad.Count){'PS51_LINT=FAIL';$bad}else{'PS51_LINT=PASS'}
