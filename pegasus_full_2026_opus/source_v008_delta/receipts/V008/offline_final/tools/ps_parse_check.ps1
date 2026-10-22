param([string[]]$Paths)
$fail = 0
foreach ($p in $Paths) {
  $t = $null; $e = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$t, [ref]$e)
  if ($e.Count -gt 0) { $fail++; Write-Output ("PARSE_FAIL " + $p); $e | ForEach-Object { Write-Output ("  " + $_.Extent.StartLineNumber + ": " + $_.Message) } }
  else { Write-Output ("PARSE_OK tokens=" + $t.Count + " " + (Split-Path $p -Leaf)) }
}
exit $fail
