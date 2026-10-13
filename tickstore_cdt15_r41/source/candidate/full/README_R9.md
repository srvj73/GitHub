# TICKSTORE R9 — FULL_SERIAL RELEASE CANDIDATE RC1 handoff

FULL_SERIAL_CAPABILITY_IN_RELEASE_CANDIDATE=YES
OWNER_AUTHORIZATION_REQUIRED=YES
AUTHORIZED_GATE_INCLUDED=NO
FULL_HISTORY_EXECUTION_AUTHORIZED=NO
AUTOCPU_AUTHORIZED=NO
CSV_DELETION_AUTHORIZED=NO

RC1 enables the FULL_SERIAL code path only after complete validation of an external owner
gate and its independently supplied trusted SHA256. The package includes neither an
authorized gate nor a trusted gate digest and performs no automatic discovery, generation
or fallback. The historical --full-history route remains blocked. This is a release
candidate for independent audit; package capability does not authorize real history execution.
All commands below are for the owner to run later; none was run by Codex.
Use Windows PowerShell and Python 3.14 for the Windows checks. Run without Python -O,
because the inherited R8 regression scripts use assert statements.

## Files

Created: SPEC_FULL_SERIAL_R9.md, CHANGELOG_R9_FULL_SERIAL.md,
run_tickstore_full_serial_r9.ps1, test_full_serial_r9.py,
static_runner_preaudit_r9.py, README_R9.md and FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json.

RC1 modifies tickstore_serial_runner.py, test_full_serial_r9.py,
static_runner_preaudit_r9.py, SPEC_FULL_SERIAL_R9.md, README_R9.md,
CHANGELOG_R9_FULL_SERIAL.md, run_tickstore_full_serial_r9.ps1 and
FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json.

Frozen seed files, existing tests, BASELINE_R8 and Gate B staging remain unchanged.
The transaction-core routines retain their behavior. The only R8 call-site refactor is
extraction of verify_full / reconcile_or_build / verify_full into _run_day_already_locked.
The new full source view is used only in the R9 full-serial engine.

## Directed preaudit remediation V001

- MAJOR-01: FULL_SOURCE_FINAL_SEAL adds a third whole-source hash after monthly processing.
  It verifies the captured path/size/mtime/file identity and retains lightweight Windows
  source-pin descriptors through reconciliation and successful unlock. V003 below requires
  final verification and successful close before terminal PASS. Residual cleanup covers
  failure and Ctrl+C cases.
- MAJOR-02: terminal reconciliation now performs two complete artifact inventories, three
  exact-equality manifest reads and a final global-manifest partial-file check under the lock.
- MINOR-01: use FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json, which has the exact R9 fields,
  authorized=false and null release/machine placeholders. The frozen original template
  FULL_OWNER_GATE_TEMPLATE_DO_NOT_USE.json is preserved. No authorized gate is included.
- MINOR-02: the whitespace commands below check the complete R9 text files even if untracked,
  using no-index comparisons against an empty temporary file, without staging or committing.

## Directed final remediation V003

- NEW_MAJOR_03: terminal success now requires reconciliation, successful writer-lock
  release, final source-binding verification and successful final-seal close, in that order.
  The PASS marker and return 0 occur only afterward. A descriptor that fails to close is
  retained for residual cleanup in finally; cleanup is attempted without replacing the
  original FULL_SOURCE_FINAL_SEAL_CLOSE_FAILED or KeyboardInterrupt cause.
- The permanent close-failure test injects os.close failure only for a final-seal descriptor
  and requires no PASS, no remaining writer lock, residual cleanup and no return 0.
- The descriptor-lifetime test now requires descriptors live through lock release and final
  verification, then all closed before the terminal PASS marker.

No validation command was executed for this remediation.

## Release candidate RC1

- The active runner identity is TICKSTORE_SERIAL_RUNNER_V001R9_FULL_SERIAL_RELEASE_RC1.
- FULL_SERIAL capability is enabled only for --mode FULL_SERIAL. The legacy full-history
  capability remains false and its route remains blocked.
- Gate path and independently trusted gate SHA256 are mandatory launcher parameters. Their
  pure syntax validation occurs before source, destination or ledger access; complete gate
  validation occurs before dispatch to the unchanged FULL_SERIAL engine.
- The template remains authorized=false, with null release-dependent and machine-specific
  fields. This package contains no authorized gate, embedded digest or gate generator.

Real history execution remains prohibited until independent audit of this RC, calculation
of the final runner/spec hashes, capture of the real paths and volume identities, owner-local
creation of an authorized gate outside the package, separate transmission of that gate's
SHA256 and a final pre-execution audit are all complete.

The new tests reproduce a source mutation after clean month closure, same-content file
replacement, size/mtime/SHA mismatch, final-seal open failure/interrupt and descriptor cleanup.
They also inject late artifacts and a manifest partial exactly after the first inventory.
These tests and the updated scanner have not been executed in this remediation session.

## Local commands, in order

Set the exact working directory. py_compile writes __pycache__ locally.

```powershell
Set-Location -LiteralPath 'D:\Base CSV\Scripts\TICKSTORE_R9_DEV\WORK_R9_FULL_RELEASE_RC1'
$tickstorePythonFiles = Get-ChildItem -LiteralPath . -File -Filter '*.py' | Select-Object -ExpandProperty FullName
& py -3.14 -m py_compile @tickstorePythonFiles
if ($LASTEXITCODE -ne 0) { throw 'TICKSTORE py_compile failed' }
```

Affected R9 tests (tiny synthetic CSVs in temporary directories; no historical source access).
The canonical-plan test reads only the small sealed ledger ZIP and release metadata.
Authorized gate objects and synthetic legacy certificates exist only in memory in tests.

```powershell
& py -3.14 -m unittest -v test_full_serial_r9
if ($LASTEXITCODE -ne 0) { throw 'TICKSTORE R9 tests failed' }
```

R8 regressions that exercise the Windows-compatible subset:

```powershell
$tickstoreWindowsRegression = @(
    'test_runner_logic.py',
    'test_gate_b_r8.py',
    'test_windows_create_new_mapping_r7.py',
    'test_enospc_matrix_r4.py',
    'test_filesystem_alias_r3.py'
)
foreach ($tickstoreTest in $tickstoreWindowsRegression) {
    & py -3.14 $tickstoreTest
    if ($LASTEXITCODE -ne 0) { throw "TICKSTORE regression failed: $tickstoreTest" }
}
```

The inherited test_runner_adversarial_r3.py and test_r3_additional_regressions.py inject
source writes/replacements while a pin is open and expect POSIX success followed by
detection. Windows deliberately denies those writes. Run these unchanged regressions
in WSL/Linux with Python 3.10+; do not weaken Windows sharing denial to make them pass.
This command uses the same WORK_R9_FULL_RELEASE_RC1 directory through WSL. WSL and its filesystem must
support the existing alias/symlink tests; environmental failures require review.

```powershell
& wsl.exe --cd '/mnt/d/Base CSV/Scripts/TICKSTORE_R9_DEV/WORK_R9_FULL_RELEASE_RC1' python3 test_runner_adversarial_r3.py
if ($LASTEXITCODE -ne 0) { throw 'TICKSTORE adversarial regression failed' }
& wsl.exe --cd '/mnt/d/Base CSV/Scripts/TICKSTORE_R9_DEV/WORK_R9_FULL_RELEASE_RC1' python3 test_r3_additional_regressions.py
if ($LASTEXITCODE -ne 0) { throw 'TICKSTORE additional regression failed' }
```

Integral suite means all seven inherited test scripts (their main/top-level assertions,
not only test collection) plus the R9 unittest suite. Run Windows R9 above as well, since
the actual sharing-denial test is explicitly skipped on POSIX. This integral command
uses WSL and aborts on the first failed script:

```powershell
$tickstoreAllTests = @(
    'test_runner_logic.py',
    'test_runner_adversarial_r3.py',
    'test_r3_additional_regressions.py',
    'test_filesystem_alias_r3.py',
    'test_enospc_matrix_r4.py',
    'test_windows_create_new_mapping_r7.py',
    'test_gate_b_r8.py',
    'test_full_serial_r9.py'
)
foreach ($tickstoreTest in $tickstoreAllTests) {
    & wsl.exe --cd '/mnt/d/Base CSV/Scripts/TICKSTORE_R9_DEV/WORK_R9_FULL_RELEASE_RC1' python3 $tickstoreTest
    if ($LASTEXITCODE -ne 0) { throw "TICKSTORE integral suite failed: $tickstoreTest" }
}
```

Whitespace check from the canonical Git root, followed by complete-file checks of every R9
text file. The explicit list covers newly created/untracked files independently of Git's
index and ignore rules. The empty temporary file is created only inside WORK_R9_FULL_RELEASE_RC1:

```powershell
& git -C 'D:\Base CSV\Scripts' diff --check -- 'TICKSTORE_R9_DEV/WORK_R9_FULL_RELEASE_RC1'
if ($LASTEXITCODE -ne 0) { throw 'TICKSTORE diff check failed' }

$tickstoreWhitespaceFiles = @(
    'tickstore_serial_runner.py',
    'test_full_serial_r9.py',
    'static_runner_preaudit_r9.py',
    'SPEC_FULL_SERIAL_R9.md',
    'README_R9.md',
    'CHANGELOG_R9_FULL_SERIAL.md',
    'run_tickstore_full_serial_r9.ps1',
    'FULL_OWNER_GATE_R9_TEMPLATE_DO_NOT_USE.json'
)
$tickstoreEmptyFile = Join-Path 'D:\Base CSV\Scripts\TICKSTORE_R9_DEV\WORK_R9_FULL_RELEASE_RC1' (
    'TICKSTORE_WHITESPACE_EMPTY_' + [guid]::NewGuid().ToString('N') + '.tmp'
)
[System.IO.File]::WriteAllBytes($tickstoreEmptyFile, [byte[]]@())
try {
    foreach ($tickstoreFile in $tickstoreWhitespaceFiles) {
        $tickstoreTextPath = Join-Path 'D:\Base CSV\Scripts\TICKSTORE_R9_DEV\WORK_R9_FULL_RELEASE_RC1' $tickstoreFile
        $tickstoreCheckOutput = @(& git diff --no-index --no-ext-diff --check -- $tickstoreEmptyFile $tickstoreTextPath 2>&1)
        $tickstoreCheckExit = $LASTEXITCODE
        if ($tickstoreCheckOutput.Count -ne 0 -or $tickstoreCheckExit -notin @(0,1)) {
            $tickstoreCheckOutput | Write-Output
            throw "TICKSTORE complete-file whitespace check failed: $tickstoreFile"
        }
    }
}
finally {
    Remove-Item -LiteralPath $tickstoreEmptyFile -Force
}
```

The no-index check accepts only a clean, empty diagnostic stream and exit code 0 or 1;
code 1 can mean ordinary differences from the empty file. Whitespace diagnostics or other
errors fail the check. No git add/commit/push command is used.

Static prohibition scanner (AST/text checks only; no runner import, source access or execution):

```powershell
& py -3.14 static_runner_preaudit_r9.py
if ($LASTEXITCODE -ne 0) { throw 'TICKSTORE R9 static checks failed' }
```

The inherited static_runner_preaudit_r3.py/static_runner_preaudit_r8.py are historical
package scanners. They assume historical release names and some files not included in
this curated WORK_R9_FULL_RELEASE_RC1 seed. They are preserved, not repurposed as R9 acceptance commands.

Generate hashes of the package files only (no recursive hashing, no CSV base hashing):

```powershell
$tickstorePackageFiles = Get-ChildItem -LiteralPath . -File |
    Where-Object { $_.Extension -in '.py','.ps1','.md','.json','.zip','.txt' } |
    Sort-Object Name
$tickstoreHashRows = foreach ($tickstoreFile in $tickstorePackageFiles) {
    $tickstoreDigest = Get-FileHash -LiteralPath $tickstoreFile.FullName -Algorithm SHA256
    [pscustomobject]@{ name=$tickstoreFile.Name; sha256=$tickstoreDigest.Hash; bytes=$tickstoreFile.Length }
}
$tickstoreHashRows | Export-Csv -LiteralPath '.\MANIFEST_R9_LOCAL_SHA256.csv' -NoTypeInformation -Encoding utf8
```

Tests and scanners reporting success do not constitute a release PASS or FULL authorization.
Keep the historical full-history flag false. Do not run the full launcher as part of these checks.
After successful local checks, submit source, test outputs and package hash manifest for
independent audit. Any authorized owner gate and its trusted digest must come from an
independent owner-controlled handoff; neither is included in RC1.

FULL_SERIAL_CAPABILITY_IN_RELEASE_CANDIDATE=YES
OWNER_AUTHORIZATION_REQUIRED=YES
AUTHORIZED_GATE_INCLUDED=NO
FULL_HISTORY_EXECUTION_AUTHORIZED=NO
AUTOCPU_AUTHORIZED=NO
CSV_DELETION_AUTHORIZED=NO


RC2R3 (25/09/2026): fecha `JOURNAL_ORACLE_MISMATCH` na ponte de recuperação de transação canônica interrompida pelo FULL_SERIAL RC1. A recuperação passa a usar os `full_release_materials()` ids exatos que criaram o journal; `run_one_day()` genérico é proibido nessa ponte. Core RC1 permanece byte a byte congelado.

RC3 (25/09/2026): productive multiwork redesign. The ordinary parallel phase now performs one forward source pass per month with inline SHA-256 + scan/parse/build, removes the per-day ACK barrier, defers canonical publication until monthly SHA verification, retains continuous parent source pins through final reconciliation, reuses compatible RC2R3 scratch, and reports BUILDING/SCANNING plus SOURCE_MIB_S instead of treating process count as proof of work.

RC4 (26/09/2026): removes the RC3 publication-starvation bottleneck observed in production. Canonical validation/publication moves to one dedicated single-writer process; the parent keeps consuming worker events, seals verified month pins, prequeues START only after a parent pin is open, and immediately admits replacement month workers. Build/hash and publication therefore overlap. Scratch resume extends fail-closed compatibility to RC4 + RC3 + RC2R3. Production remains unauthorized until RC4 Windows preflight and a bounded real-source productivity canary pass.
