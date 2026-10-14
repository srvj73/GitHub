"""Physical verification of the CURRENT policy capture for technical producers (B07, B2D).

Shared by B07_TECHNICAL_PRODUCER and ORIGIN_DECISION_BINDER (R45 B07-PROVENANCE-01 and its
B2D analogue).  A producer never accepts a caller-supplied capture dictionary: the capture
folder and the origin reconciliation record are read through the sealed D4 reader
(D4_FIRST_ADMISSION_PREP.Reads: Win32 handles denying write/delete on Windows), the verifier
module POLICY_CAPTURE_BINDING is admitted only by its FIRST_ADMISSION_BINDING digest, and the
reconciliation SHA-256 is supplied separately by the operator.  Only WIN32_PROTECTED_HANDLES
reads are native evidence; anything else is reported as a finding.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NATIVE_MODE = 'WIN32_PROTECTED_HANDLES'
NOT_NATIVE = 'POLICY_CAPTURE_READ_NOT_NATIVE_PROTECTED'


def verify_policy(policy_root, reconciliation, reconciliation_sha256, now=None):
    """Return (capture | None, read_mode, findings); never raises for policy or reader failures."""
    findings, capture, mode = [], None, 'NOT_READ'
    try:
        spec = importlib.util.spec_from_file_location('policy_physical_verify_prep', HERE / 'D4_FIRST_ADMISSION_PREP.py')
        prep = importlib.util.module_from_spec(spec); spec.loader.exec_module(prep)
        manifest = json.loads((HERE / 'FIRST_ADMISSION_BINDING.json').read_bytes())
        with prep.Reads() as reads:
            mode = NATIVE_MODE if reads.store is not None else 'POSIX_OPTIMISTIC_NOT_NATIVE'
            binding = prep.load_policy_binding(reads, manifest)
            verified = binding.verify_capture(reads.read, Path(policy_root), Path(reconciliation),
                                              reconciliation_sha256, now=now)
            reads.revalidate()
        capture = dict(verified, binding_module_sha256=manifest['policy_capture_binding_sha256'], read_mode=mode)
    except Exception as exc:  # PolicyBlocked, reader Blocked, OSError: all fail closed
        findings.append('POLICY_CAPTURE_NOT_VERIFIED:%s:%s' % (type(exc).__name__, str(exc)[:200]))
    if mode != NATIVE_MODE:
        findings.append(NOT_NATIVE)
    return capture, mode, findings
