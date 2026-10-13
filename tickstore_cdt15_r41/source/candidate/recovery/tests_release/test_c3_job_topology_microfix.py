"""C3 Job topology microfix tests. No production paths or C3 orchestration."""
import os
import unittest
from unittest.mock import patch
import tickstore_publisher_recovery_v004 as r

class JobTopologyMicrofixTests(unittest.TestCase):
    def test_self_only_is_accepted(self):
        with patch.object(r,"job_members",return_value={os.getpid()}):
            self.assertEqual(r.require_quiescent_root_job("GATE"),{os.getpid()})

    def test_verified_direct_system_conhost_is_accepted(self):
        extra=424242
        identity={"pid":extra,"parent_pid":os.getpid(),"exe":"conhost.exe",
                  "image":r"C:\\Windows\\System32\\conhost.exe","process_creation_time":1}
        with patch.object(r,"job_members",return_value={os.getpid(),extra}), \
             patch.object(r,"_system_conhost_image",return_value=r.norm(r"C:\\Windows\\System32\\conhost.exe")), \
             patch.object(r,"_job_member_identity",return_value=identity):
            self.assertEqual(r.require_quiescent_root_job("GATE"),{os.getpid(),extra})

    def test_conhost_wrong_parent_is_rejected(self):
        extra=424242
        identity={"pid":extra,"parent_pid":999,"exe":"conhost.exe",
                  "image":r"C:\\Windows\\System32\\conhost.exe","process_creation_time":1}
        with patch.object(r,"job_members",return_value={os.getpid(),extra}), \
             patch.object(r,"_system_conhost_image",return_value=r.norm(r"C:\\Windows\\System32\\conhost.exe")), \
             patch.object(r,"_job_member_identity",return_value=identity):
            with self.assertRaisesRegex(r.Blocked,"GATE:UNEXPECTED_JOB_MEMBER"):
                r.require_quiescent_root_job("GATE")

    def test_conhost_wrong_image_is_rejected(self):
        extra=424242
        identity={"pid":extra,"parent_pid":os.getpid(),"exe":"conhost.exe",
                  "image":r"C:\\Temp\\conhost.exe","process_creation_time":1}
        with patch.object(r,"job_members",return_value={os.getpid(),extra}), \
             patch.object(r,"_system_conhost_image",return_value=r.norm(r"C:\\Windows\\System32\\conhost.exe")), \
             patch.object(r,"_job_member_identity",return_value=identity):
            with self.assertRaisesRegex(r.Blocked,"GATE:UNEXPECTED_JOB_MEMBER"):
                r.require_quiescent_root_job("GATE")

    def test_arbitrary_direct_child_is_rejected(self):
        extra=424242
        identity={"pid":extra,"parent_pid":os.getpid(),"exe":"python.exe",
                  "image":r"C:\\Python\\python.exe","process_creation_time":1}
        with patch.object(r,"job_members",return_value={os.getpid(),extra}), \
             patch.object(r,"_system_conhost_image",return_value=r.norm(r"C:\\Windows\\System32\\conhost.exe")), \
             patch.object(r,"_job_member_identity",return_value=identity):
            with self.assertRaisesRegex(r.Blocked,"GATE:UNEXPECTED_JOB_MEMBER"):
                r.require_quiescent_root_job("GATE")

    def test_self_absent_is_rejected_before_identity_lookup(self):
        with patch.object(r,"job_members",return_value=set()), \
             patch.object(r,"_job_member_identity",side_effect=AssertionError("identity lookup not expected")):
            with self.assertRaisesRegex(r.Blocked,"GATE:SELF_ABSENT"):
                r.require_quiescent_root_job("GATE")

    def test_all_four_quiescent_gates_use_topology_helper(self):
        import inspect
        text=inspect.getsource(r)
        self.assertNotIn('job_members()=={os.getpid()}',text)
        for reason in ("JOB_ASSIGNMENT_REQUIRED_BEFORE_STARTUP","RECOVERY_JOB_MEMBERSHIP",
                       "RESIDUAL_CHILDREN","STALE_LOCK_RESIDUAL_JOB_PROCESSES"):
            self.assertIn('require_quiescent_root_job("'+reason+'")',text)

    def test_more_than_one_extra_member_is_rejected(self):
        extras={424242,424243}
        with patch.object(r,"job_members",return_value={os.getpid(),*extras}):
            with self.assertRaisesRegex(r.Blocked,"GATE:UNEXPECTED_MEMBER_COUNT:2"):
                r.require_quiescent_root_job("GATE")

if __name__=="__main__":
    unittest.main(verbosity=2)
