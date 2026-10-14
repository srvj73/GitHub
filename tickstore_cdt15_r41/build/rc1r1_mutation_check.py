"""R47 adversarial evidence: each RC1R1 / G11 / migration / scratch power-loss correction is guarded by a behavioural test.

Usage: python3 -I -B rc1r1_mutation_check.py <source_dir> <out_log>
Every mutant runs on a private copy of the source tree; the source tree itself is never modified.
The targeted tests are behavioural (no byte pin), so a kill proves the semantic guard, not a hash.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = 'candidate/full/tickstore_serial_runner.py'
MW = 'candidate/full/tickstore_full_multiwork.py'
REL = 'candidate/recovery/engine/tickstore_publisher_recovery_v004_release.py'
PF = 'candidate/recovery/modules/postfull_verifier.py'
ODB = 'candidate/control/ORIGIN_DECISION_BINDER.py'
MIG = 'candidate/control/RC1R1_SUCCESSOR_MIGRATION.py'
FULL_DIR, TEST_DIR = 'candidate/full', 'tests'
MUTANTS = {
    'CORE_FULL_SERIAL_CAPABILITY_TRUE': (CORE, 'FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False',
                                         'FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True',
                                         FULL_DIR, ['test_full_serial_r9.FullSerialTests.test_rc1r1_disabled_routes_refuse_even_a_forged_valid_gate']),
    'CORE_PILOT_CAPABILITY_TRUE': (CORE, 'PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False',
                                   'PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=True',
                                   FULL_DIR, ['test_full_serial_r9.FullSerialTests.test_rc1r1_disabled_routes_refuse_even_a_forged_valid_gate']),
    'CORE_RC1_REFERENCE_CHECK_REMOVED': (CORE, '    if ids.get("reference_sha256")!=FROZEN_REFERENCE_SHA256: raise Blocked("FULL_RC1_HISTORICAL_REFERENCE")\n',
                                         '', FULL_DIR, ['test_full_serial_r9.FullSerialTests.test_rc1_historical_provenance_rejects_tamper_and_foreign_runner']),
    'CORE_RC1_BUILDING_SCRATCH_ADOPTED': (CORE, '    if obj.get("state")!="VALIDATED_PENDING_PUBLISH":\n',
                                          '    if False:\n', FULL_DIR,
                                          ['test_full_multiwork.TestRc1HistoricalScratch.test_rc1_building_scratch_is_never_continued']),
    'CORE_READONLY_RECONCILE_HISTORICAL_REMOVED': (CORE, '            oracle=(historical_rc1_oracle(pp,c,months[c["month_id"]],src_id,ledger_sha)\n                    or ',
                                                   '            oracle=(None\n                    or ', FULL_DIR,
                                                   ['test_full_serial_r9.FullSerialTests.test_rc1r1_reuses_days_published_by_historical_rc1_with_their_provenance']),
    'MW_C0_HISTORICAL_REMOVED': (MW, '            oracle=(core.historical_rc1_oracle(pp,c,month,identity,ledger_sha)\n',
                                 '            oracle=(None\n', FULL_DIR, ['test_full_multiwork.TestRc1HistoricalProvenance']),
    'MW_S0_PUBLISH_HISTORICAL_REMOVED': (MW, '    oracle = (core.historical_rc1_scratch_oracle(Path(scratch_journal), c, month, identity, ledger_sha)\n',
                                         '    oracle = (None\n', FULL_DIR, ['test_full_multiwork.TestRc1HistoricalScratch']),
    'MW_RC1_TRANSIENT_GUARD_REMOVED': (MW, '    core.reject_historical_rc1_transient(core._full_day_paths(dest_root, c))\n', '',
                                       FULL_DIR, ['test_full_multiwork.TestRc1HistoricalProvenance']),
    'ENGINE_RC1_HISTORICAL_DROPPED': (REL, '    if runner in (CORE_SHA,RC1_HISTORICAL_CORE_SHA):\n', '    if runner==CORE_SHA:\n',
                                      TEST_DIR, ['test_rc1r1_recertification.EngineProvenanceTest']),
    'POSTFULL_RC1_HISTORICAL_DROPPED': (PF, 'if runner in (CORE_SHA,RC1_HISTORICAL_CORE_SHA):', 'if runner==CORE_SHA:',
                                        TEST_DIR, ['test_rc1r1_recertification.PostfullProvenanceTest']),
    'BINDER_G4_ENFORCEMENT_REMOVED': (ODB, '    _check_native_chain(stage, bodies, code_sha=code_sha, final_package_sha=final_package_sha)\n', '',
                                      TEST_DIR, ['test_b2d_origin_decision_binder']),
    'MW_SCRATCH_CRASH_DEBRIS_IGNORED': (MW, '        _discard_scratch_crash_debris(namespace,partial,journal)\n', '',
                                        FULL_DIR, ['test_full_multiwork.TestScratchCrashDebris']),
    'MIGRATION_APPLY_WITHOUT_CHAIN': (MIG, "        require(all((a.chain_file, a.chain_sha256, a.b06_sha256)), 'APPLY_REQUIRES_RELEASE_CHAIN_UNTIL_B07')\n", '',
                                      TEST_DIR, ['test_rc1r1_successor_migration.Apply']),
    'MIGRATION_SKIPS_FINAL_TREE_EQUALITY': (MIG, "        require(q.read_bytes() == members[p], 'SUCCESSOR_FINAL_BYTES:' + p)\n", '        pass\n',
                                            TEST_DIR, ['test_rc1r1_successor_migration.Blockers']),
    'MIGRATION_ADMITTED_AUTHORITY_IGNORED': (MIG, "    if admitted:\n        blockers.append('ADMITTED_RUN_AUTHORITY_PRESENT_REQUIRES_ORIGIN_DECISION')\n", '',
                                             TEST_DIR, ['test_rc1r1_successor_migration.Blockers']),
}


def run(tree, cwd, names):
    r = subprocess.run([sys.executable, '-B', '-m', 'unittest'] + names, cwd=str(tree / cwd),
                       capture_output=True, text=True, timeout=1800)
    tail = [l for l in r.stderr.splitlines() if l.startswith(('FAIL:', 'ERROR:', 'Ran ', 'OK', 'FAILED'))]
    return r.returncode, tail


def main(source, out):
    source, lines, ok = Path(source), [], True
    with tempfile.TemporaryDirectory() as t:
        base = Path(t) / 'clean'
        shutil.copytree(source, base, ignore=shutil.ignore_patterns('__pycache__'))
        for name, (rel, old, new, cwd, names) in MUTANTS.items():
            rc, tail = run(base, cwd, names)
            lines += ['BASELINE %s rc=%d' % (name, rc)] + tail[-2:]
            ok &= rc == 0
            tree = Path(t) / name
            shutil.copytree(base, tree, ignore=shutil.ignore_patterns('__pycache__'))
            p = tree / rel
            s = p.read_text(encoding='utf-8')
            assert s.count(old) == 1, name
            p.write_text(s.replace(old, new), encoding='utf-8')
            rc, tail = run(tree, cwd, names)
            killed = rc != 0
            ok &= killed
            lines += ['MUTANT %s rc=%d %s' % (name, rc, 'KILLED' if killed else 'SURVIVED')] + tail[-4:]
            shutil.rmtree(tree, ignore_errors=True)
    lines.append('RC1R1_MUTATION_CHECK=' + ('PASS' if ok else 'FAIL'))
    Path(out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:3]))
