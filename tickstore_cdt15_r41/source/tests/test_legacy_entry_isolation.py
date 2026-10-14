"""R45: legacy FULL_SERIAL / pilot / full-history entries isolated without touching the frozen RC1 core.

Proof layers
  1. the RC1 core is byte-identical (CORE_RC1_FROZEN D3A15572...);
  2. packaging: the legacy launchers and their release audits are quarantined out of the package;
  3. static non-reachability: no launcher (.ps1/.bat/.cmd) and no non-test module of the package
     carries a legacy CLI route or calls a legacy entry function of the core;
  4. direct entry (native in R45): every legacy CLI form fails closed without the administrative
     owner gate that R40 revoked; the multiwork API rejects legacy gate arguments.
Residual (declared, not hidden): a human-forged FULL_SERIAL owner gate bound exactly to the
current bindings would still be accepted by the frozen core CLI; R40 forbids issuing it and the
core cannot be modified without re-certification.  That decision belongs to the origin.
"""
import ast
import hashlib
import os
import subprocess
import sys
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = R / 'candidate'
CORE = C / 'full/tickstore_serial_runner.py'
CORE_SHA = 'D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0'
QUARANTINED = ('run_tickstore_full_serial_r9.ps1', 'RUN_WINDOWS_GATE_B.ps1', 'run_tickstore_serial.ps1',
               'static_runner_preaudit_r3.py', 'static_runner_preaudit_r8.py', 'static_runner_preaudit_r9.py')
CLI_TOKENS = ('--mode FULL_SERIAL', "'FULL_SERIAL'", '"FULL_SERIAL"', '--pilot-date', '--pilot-gate-file',
              '--full-history', '--full-gate-file', '--full-gate-sha256', 'PILOT_LOW', 'PILOT_HIGH')
# Core-bound callee: hashed into every core binding (file_ids.preflight_sha256) and spawned only by the core's
# own pilot preflight; it cannot leave the package without changing RC1 bindings.  Pinned, and no other module
# may reference it.
CORE_BOUND = {C / 'full/WINDOWS_GATE_B_PREFLIGHT_V005.py': 'CDC49F5E6AC1A1A43954D36F900CC8BE82EC8FCD7EF4A903515CC92A462EAE0F'}
LEGACY_FUNCS = {'run_full_serial', 'run_one_day', 'require_pilot_owner_gate', 'validate_full_owner_gate',
                'validate_full_gate_arguments', 'run_fresh_windows_preflight'}


def is_test(p):
    return p.name.startswith(('test_', 'tests_')) or 'tests' in p.parts


def scan_cli_routes(root):
    offenders = []
    for p in sorted(Path(root).rglob('*')):
        if not p.is_file() or p == CORE or p in CORE_BOUND or '__pycache__' in p.parts or p.name == Path(__file__).name:
            continue
        if p.suffix.lower() in ('.ps1', '.bat', '.cmd', '.vbs') or (p.suffix == '.py' and not is_test(p)):
            hits = [t for t in CLI_TOKENS if t in p.read_text(encoding='utf-8', errors='replace')]
            if hits:
                offenders.append((str(p.relative_to(root)), hits))
    return offenders


class LegacyIsolation(unittest.TestCase):
    def test_01_rc1_core_byte_identical(self):
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(), CORE_SHA)

    def test_02_legacy_launchers_and_release_audits_not_packaged(self):
        for name in QUARANTINED:
            self.assertFalse(any(R.rglob(name)), name)

    def test_03_no_launcher_or_runtime_module_routes_to_legacy_cli(self):
        self.assertEqual(scan_cli_routes(R), [])

    def test_03b_core_bound_callee_pinned_and_referenced_only_by_core(self):
        for p, digest in CORE_BOUND.items():
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest().upper(), digest)
            refs = [str(q.relative_to(R)) for q in R.rglob('*') if q.is_file() and q.suffix.lower() in ('.py', '.ps1')
                    and q not in (CORE, p) and not is_test(q) and '__pycache__' not in q.parts
                    and p.name in q.read_text(encoding='utf-8', errors='replace')]
            self.assertEqual(refs, [])

    def test_04_no_runtime_module_calls_a_legacy_entry_function(self):
        offenders = []
        for p in sorted(R.rglob('*.py')):
            if p == CORE or p in CORE_BOUND or is_test(p) or '__pycache__' in p.parts or p.name == Path(__file__).name:
                continue
            try:
                tree = ast.parse(p.read_text(encoding='utf-8', errors='replace'))
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Call):
                    f = n.func
                    name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
                    owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
                    if name in LEGACY_FUNCS or (name == 'main' and owner in ('core', 'r', 'runner_core')):
                        offenders.append((str(p.relative_to(R)), name, n.lineno))
        self.assertEqual(offenders, [])

    def run_core(self, *args):
        r = subprocess.run([sys.executable, '-E', '-s', '-B', str(CORE)] + list(args), capture_output=True, text=True,
                           timeout=120, cwd=str(CORE.parent))
        return r.returncode, r.stdout + r.stderr

    def test_05_direct_full_serial_entry_fails_closed_without_revoked_gate(self):
        for args, reason in ((['--mode', 'FULL_SERIAL'], 'FULL_OWNER_GATE_REQUIRED'),
                             (['--mode', 'FULL_SERIAL', '--full-gate-file', 'gate.json'], 'FULL_OWNER_GATE_TRUSTED_SHA256_REQUIRED')):
            code, out = self.run_core(*args)
            self.assertNotEqual(code, 0); self.assertIn('TICKSTORE_RUNNER_STATUS=BLOCKED', out); self.assertIn(reason, out)

    def test_06_direct_full_history_and_pilot_entries_fail_closed(self):
        code, out = self.run_core('--full-history', '--ledger-zip', 'x.zip')
        self.assertNotEqual(code, 0); self.assertIn('FULL_HISTORY_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE', out)
        code, out = self.run_core('--pilot-date', '20990101', '--ledger-zip', 'x.zip')
        self.assertNotEqual(code, 0); self.assertIn('PILOT_DATE_NOT_FROZEN_GATE_B_CASE', out)
        code, out = self.run_core('--pilot-date', '20260731', '--ledger-zip', 'x.zip')
        self.assertNotEqual(code, 0); self.assertIn('TICKSTORE_RUNNER_STATUS=BLOCKED', out)

    def test_07_multiwork_api_rejects_legacy_gate_arguments(self):
        sys.path.insert(0, str(C / 'full'))
        import tickstore_full_multiwork as mw
        for kw in ({'core_gate_file': 'g'}, {'core_gate_sha256': 'A' * 64}, {'multiwork_gate_file': 'g'},
                   {'multiwork_gate_sha256': 'A' * 64}):
            with self.assertRaisesRegex(mw.MultiworkBlocked, 'LEGACY_ADMINISTRATIVE_OWNER_GATE_REVOKED'):
                mw.execute_multiwork(Path('S'), Path('D'), Path('X'), Path('L'), **kw)

    def test_08_mutation_planted_launchers_are_detected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            for i, body in enumerate(('python full\\tickstore_serial_runner.py --mode FULL_SERIAL\n',
                                      '& py runner.py --full-history --ledger-zip x\n', 'call r.py --pilot-date 20260731\n')):
                (t / ('L%d.%s' % (i, ('ps1', 'cmd', 'bat')[i]))).write_text(body)
            (t / 'mod.py').write_text("ARGS=['--mode','FULL_SERIAL']\n")
            self.assertEqual(len(scan_cli_routes(t)), 4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
