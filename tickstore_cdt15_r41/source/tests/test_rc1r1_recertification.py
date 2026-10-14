"""RC1R1 recertification (R46 origin decision Option A). Source-only, disposable fixtures.

Proof layers
  1. structural delta: RC1 -> RC1R1 (core), BFC44DA9/E998 -> successor engines and B5E753C3 ->
     successor postfull verifier change only the declared top-level definitions (AST, comments ignored);
  2. the embedded core executed by both engines is byte-identical to the packaged RC1R1 core;
  3. provenance: oracles written by the historical RC1 core stay valid in the engine contract and in
     the independent post-FULL verifier, with the same reference check; unknown runners are refused;
  4. the legacy FULL_SERIAL and PILOT CLI routes refuse even a forged, binding-exact gate.
"""
import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
CAND = HERE.parent / 'candidate'
FIX = HERE / 'fixtures' / 'RC1R1_HISTORICAL'
FULL = CAND / 'full'
sys.path.insert(0, str(FULL))

RC1 = 'D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0'
HISTORICAL = {
    'core': ('tickstore_serial_runner.RC1_D3A15572.py.txt', RC1, FULL / 'tickstore_serial_runner.py'),
    'release': ('tickstore_publisher_recovery_v004_release.BFC44DA9.py.txt',
                'BFC44DA9A375ED565D8DA2DA7E34EC376C25DEAFE15ED2F3C063CE635CEBCD4C',
                CAND / 'recovery/engine/tickstore_publisher_recovery_v004_release.py'),
    'candidate': ('tickstore_publisher_recovery_v004_candidate.E9980324.py.txt',
                  'E998032478EA1FAB8BD69FF000D9622749B679058F457A927D5854963208E310',
                  CAND / 'recovery/engine/tickstore_publisher_recovery_v004_candidate.py'),
    'postfull': ('postfull_verifier.B5E753C3.py.txt',
                 'B5E753C3A0727B01B8DE65B44374F432D6F5B8AE1C52C02449CA50BFC558B7F0',
                 CAND / 'recovery/modules/postfull_verifier.py'),
}
EXPECTED_DELTA = {
    'core': ({'FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE', 'PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE',
              'reconcile_full_readonly'},
             {'RC1_HISTORICAL_RUNNER_SHA256', '_rc1_historical_rebuild', 'historical_rc1_oracle',
              'historical_rc1_scratch_oracle', 'reject_historical_rc1_transient'}),
    'release': ({'CORE_SHA', 'CORE_B64', 'oracle_contract'}, {'RC1_HISTORICAL_CORE_SHA'}),
    'candidate': ({'CORE_SHA', 'CORE_B64', 'oracle_contract'}, {'RC1_HISTORICAL_CORE_SHA'}),
    'postfull': ({'CORE_SHA', 'verify'}, {'RC1_HISTORICAL_CORE_SHA'}),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def top_level(raw):
    named, anonymous = {}, []
    for node in ast.parse(raw).body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name is None:
            anonymous.append(ast.dump(node))
        else:
            # The engines redefine some names (layered overrides); every occurrence is compared.
            occurrence = sum(1 for k in named if k[0] == name)
            named[(name, occurrence)] = ast.dump(node)
    return named, sorted(anonymous)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StructuralDeltaTest(unittest.TestCase):
    def test_historical_fixtures_are_the_preserved_originals(self):
        for key, (name, digest, _current) in HISTORICAL.items():
            with self.subTest(key=key):
                self.assertEqual(sha((FIX / name).read_bytes()), digest)

    def test_delta_is_exactly_the_declared_definitions(self):
        for key, (name, _digest, current) in HISTORICAL.items():
            with self.subTest(key=key):
                old, old_anon = top_level((FIX / name).read_bytes())
                new, new_anon = top_level(current.read_bytes())
                self.assertEqual(old_anon, new_anon)
                self.assertEqual(set(old) - set(new), set())
                changed = {n[0] for n in old if old[n] != new[n]}
                added = {n[0] for n in set(new) - set(old)}
                self.assertEqual((changed, added), EXPECTED_DELTA[key])

    def test_release_and_candidate_still_differ_only_by_the_fuse(self):
        rel = HISTORICAL['release'][2].read_bytes().decode().splitlines()
        cand = HISTORICAL['candidate'][2].read_bytes().decode().splitlines()
        diff = [(a, b) for a, b in zip(rel, cand) if a != b]
        self.assertEqual(len(rel), len(cand))
        self.assertEqual(diff, [('IMPLEMENTATION_READY = True', 'IMPLEMENTATION_READY = False')])


class EngineProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engines = {k: load(HISTORICAL[k][2], 'rc1r1_engine_' + k) for k in ('release', 'candidate')}

    def test_embedded_core_is_the_packaged_rc1r1_core(self):
        core = HISTORICAL['core'][2].read_bytes()
        for key, e in self.engines.items():
            with self.subTest(engine=key):
                self.assertEqual(sha(base64.b64decode(e.CORE_B64)), sha(core))
                self.assertEqual(e.CORE_SHA, sha(core))
                self.assertEqual(e.RC1_HISTORICAL_CORE_SHA, RC1)
                self.assertNotEqual(e.CORE_SHA, RC1)

    def test_embedded_core_executes_with_disabled_legacy_routes(self):
        e = self.engines['release']
        with mock.patch.object(e, '_core', None):
            core = e.frozen_core()
        self.assertIs(core.FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE, False)
        self.assertIs(core.PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE, False)
        self.assertEqual(core.RC1_HISTORICAL_RUNNER_SHA256, RC1)

    def _contract(self, e, runner, reference):
        oracle = {'source_identity': {'sha256': 'A' * 64, 'size': 123},
                  'runner_ids': {'runner_sha256': runner, 'reference_sha256': reference}}
        fake = types.SimpleNamespace(make_oracle=lambda contract, month, identity, ledger, ids: oracle)
        month = {'source_sha256': 'A' * 64, 'source_size': 123}
        with mock.patch.object(e, 'frozen_core', return_value=fake):
            return e.oracle_contract(oracle, {'date_key': '20260901'}, month)

    def test_oracle_contract_accepts_rc1r1_and_historical_rc1(self):
        for key, e in self.engines.items():
            for runner in (e.CORE_SHA, RC1):
                with self.subTest(engine=key, runner=runner):
                    self.assertEqual(self._contract(e, runner, e.REFERENCE_SHA)['runner_ids']['runner_sha256'], runner)

    def test_oracle_contract_rejects_wrong_reference_and_unknown_runner(self):
        for key, e in self.engines.items():
            with self.subTest(engine=key):
                for runner in (e.CORE_SHA, RC1):
                    with self.assertRaisesRegex(e.Blocked, 'ORACLE_REFERENCE_PROVENANCE'):
                        self._contract(e, runner, '0' * 64)
                with self.assertRaisesRegex(e.Blocked, 'ORACLE_FROZEN_RC1_OR_R8_PROVENANCE'):
                    self._contract(e, 'F' * 64, e.REFERENCE_SHA)


class PostfullProvenanceTest(unittest.TestCase):
    """The independent verifier reads published bytes produced by the real core (synthetic codec)."""

    def publish(self, ids):
        import test_full_serial_r9 as t9
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        source, dest, days, months, _contract, _ids, cert = t9.fixture(Path(self.temp.name))
        with mock.patch.object(t9.r, '_require_full_serial_windows'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t9.r._execute_full_serial(source, dest, days, months, t9.LEDGER_SHA, ids, cert,
                                                       t9.SyntheticCodec(), None), 0)
        return dest, {c['date_key']: c for c in days}, months, sum(int(c['rows']) for c in days)

    def verify(self, pf, dest, days, months, rows):
        with mock.patch.object(pf, 'load_ledger', return_value=(days, months)), \
             mock.patch.object(pf, 'TOTAL_DAYS', len(days)), mock.patch.object(pf, 'TOTAL_ROWS', rows):
            return pf.verify(dest, 'synthetic-ledger.zip')

    def test_rc1_and_rc1r1_provenance_verified_and_tamper_refused(self):
        pf = load(HISTORICAL['postfull'][2], 'rc1r1_postfull')
        self.assertEqual(pf.RC1_HISTORICAL_CORE_SHA, RC1)
        for runner in (RC1, pf.CORE_SHA):
            with self.subTest(runner=runner):
                ids = {'runner_sha256': runner, 'reference_sha256': pf.REFERENCE_SHA, 'spec_sha256': 'SYNTHETIC_SPEC'}
                dest, days, months, rows = self.publish(ids)
                self.assertEqual(self.verify(pf, dest, days, months, rows)['status'], 'PASS')
                commit = sorted(dest.glob('WIN@N/*/*.commit.json'))[0]
                raw = commit.read_bytes()
                for field, value in (('reference_sha256', '0' * 64), ('runner_sha256', 'F' * 64)):
                    obj = json.loads(raw); obj['oracle']['runner_ids'][field] = value
                    commit.write_text(json.dumps(obj))
                    with self.assertRaisesRegex(pf.Blocked, 'ORACLE_RUNNER_IDS'):
                        self.verify(pf, dest, days, months, rows)
                commit.write_bytes(raw)


class LegacyRoutesClosedTest(unittest.TestCase):
    def test_core_refuses_legacy_cli_routes_before_any_access(self):
        import tickstore_serial_runner as r
        self.assertEqual(sha(HISTORICAL['core'][2].read_bytes()), sha(Path(r.__file__).read_bytes()))
        cases = (
            (['runner', '--mode', 'FULL_SERIAL', '--full-gate-file', 'g.json', '--full-gate-sha256', 'A' * 64,
              '--source-root', 's', '--dest-root', 'd', '--scratch-root', 'x', '--ledger-zip', 'l'],
             'FULL_SERIAL_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE'),
            (['runner', '--ledger-zip', 'l', '--pilot-date', '20260731', '--source-root', 's', '--dest-root', 'd',
              '--scratch-root', 'x', '--windows-preflight-report', 'p', '--pilot-gate-file', 'g'],
             'PILOT_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE'),
            (['runner', '--ledger-zip', 'l', '--full-history', '--full-gate-file', 'g'],
             'FULL_HISTORY_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE'),
        )
        guards = [mock.patch.object(r, n, side_effect=AssertionError(n)) for n in
                  ('validate_full_gate_arguments', 'require_windows_pilot_runtime', 'load_ledgers',
                   '_execute_full_serial', 'run_one_day', 'require_gate')]
        with contextlib.ExitStack() as stack:
            for g in guards:
                stack.enter_context(g)
            for argv, reason in cases:
                with self.subTest(reason=reason), mock.patch('sys.argv', argv):
                    with self.assertRaisesRegex(r.Blocked, reason):
                        r.main()


if __name__ == '__main__':
    unittest.main(verbosity=2)
