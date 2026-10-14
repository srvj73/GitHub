"""R45 completeness (audit G9): STATE_CAS_RECOVERY decision table and apply boundary.

Synthetic STATE directories only.  The D4 entry boundary is a stub that records acquisition
and release; directory fsync is a no-op off Windows.  Every BLOCKED_MANUAL branch must leave the
directory byte-identical.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'candidate/control'))
import STATE_CAS_RECOVERY as cas  # noqa: E402

TAG = '1700000000.' + 'a' * 32


def h(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def state(next_node='D4', completed=(), status='PASS'):
    return json.dumps({'schema': 'TICKSTORE_ORCH_STATE_V001', 'next_node': next_node, 'completed': list(completed),
                       'status': status}, sort_keys=True).encode()


class Entry:
    def __init__(self):
        self.events = []

    def acquire_state_boundary(self, path):
        self.events.append('acquire')
        return lambda: self.events.append('release')

    def _fsync_directory(self, path):
        pass


class Recovery(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.sd = Path(t.name) / 'state'; self.sd.mkdir()
        self.sp = self.sd / 'STATE.json'
        self.prev, self.new = state('D4'), state('D4', status='SAFE_STOP')
        self.journal([{'node': 'D4', 'phase': 'STARTED', 'run_id': 'R1'}])

    def journal(self, records, broken=False):
        lines, prev = [], ''
        for r in records:
            line = json.dumps(dict(r, prev_line_sha256='X' if broken else prev), sort_keys=True).encode()
            lines.append(line); prev = h(line)
        (self.sd / 'STATE_JOURNAL.jsonl').write_bytes(b'\n'.join(lines) + b'\n')

    def debris(self, kinds, tag=TAG, prev=None, new=None):
        prev, new = prev or self.prev, new or self.new
        if 'intent' in kinds:
            (self.sd / ('STATE.json.cas-intent.' + tag)).write_bytes(json.dumps(
                {'schema': 'TICKSTORE_D4_STATE_CAS_INTENT_V001', 'tag': tag, 'prev_sha256': h(prev),
                 'new_sha256': h(new)}).encode('ascii'))
        if 'old' in kinds:
            (self.sd / ('STATE.json.cas-old.' + tag)).write_bytes(prev)
        if 'new' in kinds:
            (self.sd / ('STATE.json.cas-new.' + tag)).write_bytes(new)

    def tree(self):
        return {p.relative_to(self.sd).as_posix(): p.read_bytes() for p in sorted(self.sd.rglob('*')) if p.is_file()}

    def blocked(self, reason, checkpoint=None):
        before = self.tree()
        rep, parts = cas.diagnose(self.sp, checkpoint)
        self.assertEqual(rep['decision'], 'BLOCKED_MANUAL'); self.assertIn(reason, rep['reasons']); self.assertIsNone(parts)
        self.assertEqual(self.tree(), before)

    def apply(self):
        rep, parts = cas.diagnose(self.sp)
        entry = Entry()
        result = cas.apply(self.sp, rep, parts, entry)
        self.assertEqual(entry.events, ['acquire', 'release'])
        return rep, result

    def test_01_nothing_to_recover(self):
        self.sp.write_bytes(self.prev)
        self.assertEqual(cas.diagnose(self.sp)[0]['decision'], 'NOTHING_TO_RECOVER')

    def test_02_r1_restores_the_confirmed_previous_state(self):
        self.debris(('intent', 'old', 'new'))
        rep, result = self.apply()
        self.assertEqual(rep['decision'], 'R1_RESTORE_CONFIRMED')
        self.assertEqual(self.sp.read_bytes(), self.prev)  # the unconfirmed target is never promoted
        self.assertTrue(result['applied'])
        archive = self.sd / 'cas_recovery' / TAG
        self.assertTrue((archive / 'RECOVERY_RECEIPT.json').is_file())
        self.assertFalse(any(n.startswith('STATE.json.cas-') for n in os.listdir(self.sd)))
        self.assertEqual(cas.diagnose(self.sp)[0]['decision'], 'NOTHING_TO_RECOVER')

    def test_03_r2_completed_commit_archives_debris(self):
        self.sp.write_bytes(self.new); self.debris(('intent', 'old'))
        rep, result = self.apply()
        self.assertEqual(rep['decision'], 'R2_COMMIT_COMPLETED_ARCHIVE_DEBRIS')
        self.assertEqual(self.sp.read_bytes(), self.new)

    def test_04_r3_commit_not_started(self):
        self.sp.write_bytes(self.prev); self.debris(('intent', 'new'))
        rep, _ = self.apply()
        self.assertEqual(rep['decision'], 'R3_COMMIT_NOT_STARTED_ARCHIVE_DEBRIS')
        self.assertEqual(self.sp.read_bytes(), self.prev)

    def test_05_blocked_branches_change_nothing(self):
        self.debris(('intent', 'old')); self.debris(('intent',), tag='1700000001.' + 'b' * 32)
        self.blocked('DEBRIS_NOT_SINGLE_TAG')

    def test_06_intent_missing_or_target_mismatch(self):
        self.debris(('old',)); self.blocked('INTENT_MISSING')
        for p in list(self.sd.glob('STATE.json.cas-*')):
            p.unlink()
        self.debris(('intent', 'old')); (self.sd / ('STATE.json.cas-new.' + TAG)).write_bytes(b'other')
        self.blocked('CAS_NEW_NOT_INTENT_TARGET')

    def test_07_broken_journal_blocks(self):
        self.journal([{'node': 'D4', 'phase': 'STARTED', 'run_id': 'R1'}], broken=True)
        self.debris(('intent', 'old')); self.blocked('JOURNAL_CHAIN_BROKEN')

    def test_08_state_matching_neither_blocks(self):
        self.sp.write_bytes(state('D5')); self.debris(('intent', 'old')); self.blocked('STATE_PRESENT_MATCHES_NEITHER_PREV_NOR_NEW')

    def test_09_state_ahead_of_checkpoint_blocks(self):
        ahead = state('D5', completed=('D4',))
        self.sp.write_bytes(ahead); self.debris(('intent', 'old'), new=ahead)
        cp = self.sd.parent / 'CHECKPOINT.json'; cp.write_bytes(json.dumps({'payload': {'status': 'IN_PROGRESS'}}).encode())
        self.blocked('STATE_AHEAD_OF_CHECKPOINT', checkpoint=cp)

    def test_10_apply_requires_unchanged_evidence_and_a_diagnosis(self):
        self.debris(('intent', 'old'))
        rep, parts = cas.diagnose(self.sp)
        (self.sd / 'STATE_JOURNAL.jsonl').write_bytes((self.sd / 'STATE_JOURNAL.jsonl').read_bytes() + b'')
        os.utime(self.sd / 'STATE_JOURNAL.jsonl', ns=(1, 1))
        entry = Entry()
        with self.assertRaisesRegex(RuntimeError, 'CAS_RECOVERY_EVIDENCE_CHANGED'):
            cas.apply(self.sp, rep, parts, entry)
        self.assertEqual(entry.events, ['acquire', 'release'])
        self.assertFalse(self.sp.exists())
        with self.assertRaisesRegex(RuntimeError, 'CAS_RECOVERY_DIAGNOSIS_REQUIRED'):
            cas.apply(self.sp, {'decision': 'BLOCKED_MANUAL'}, None, Entry())

    def test_11_partial_archive_stays_blocked(self):
        self.debris(('intent', 'old'))
        (self.sd / 'cas_recovery' / TAG).mkdir(parents=True)
        self.blocked('RECOVERY_ARCHIVE_FINALIZATION_PENDING')


if __name__ == '__main__':
    unittest.main(verbosity=2)
