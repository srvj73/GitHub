"""Single menu/PowerShell entry into qualified D4, continuation and MULTIWORK."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from D4_FIRST_ADMISSION_PREP import require, strict_json
from FULL_RELEASE_CHAIN import ReleaseChain, STAGES

REQUIRED_PREFIX = {'D4': 'B07', 'D4Close': 'B07', 'D5': 'D4', 'CANARY': 'D5',
                   'FULL_PREP': 'CANARY', 'FULL_ADMIT': 'FULL_PREP', 'FULL': 'FULL_ADMISSION', 'FULL_READMIT': 'FULL_ADMISSION', 'Stop': 'FULL_ADMISSION'}
D4_PARAMETERS = {
    'FinalCodeManifestPath', 'FinalCodeManifestSha', 'CompletenessReceiptPath',
    'B07ReceiptPath', 'FirstAdmissionReviewPackPath', 'PredecessorEvidenceDir',
    'PolicyRoot', 'OriginCapturePath', 'PreparationBindingSha',
    'ReviewVerdictPath', 'PolicyAdmissionReceiptPath', 'AdapterDir',
}


def d4_command(instance, candidate, *, resume=False):
    params = instance.get('d4_parameters')
    require(isinstance(params, dict) and set(params) == D4_PARAMETERS, 'D4_PARAMETER_SET')
    command = [str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),
               '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
               str(candidate/'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1'),
               '-ResumeAdmittedRun' if resume else '-FirstAdmission', '-ExecuteD4']
    if resume: command.append('-ResumeAfterSafeStop')
    for name in sorted(params):
        value = params[name]
        require(isinstance(value, str) and bool(value) and '\x00' not in value, 'D4_PARAMETER:' + name)
        command.extend(['-' + name, value])
    return command


def run(a):
    root = Path(__file__).resolve().parent.parent
    if a.stage in ('D5', 'CANARY', 'FULL_PREP', 'FULL_ADMIT', 'FULL', 'FULL_READMIT'):
        import FULL_STAGE_CONTINUATION as continuation
        return continuation.run(a)
    until = REQUIRED_PREFIX.get(a.stage)
    if a.stage == 'Check':
        # Discovery is bounded to the descriptor whose digest is supplied separately.
        from D4_FIRST_ADMISSION_PREP import Reads, sha
        with Reads() as reads:
            d = strict_json(reads.read(a.chain_file, a.chain_sha256))
            present = tuple(k for k in STAGES if k in d.get('receipts', {}))
            require(present and present == STAGES[:len(present)], 'CHAIN_PREFIX_GAP')
            until = present[-1]
    require(until is not None, 'RUNNER_STAGE')
    with ReleaseChain(a.chain_file, a.chain_sha256, a.b06_sha256, root, until=until) as admission:
        i = admission.instance
        if a.stage == 'Check':
            print(json.dumps({'schema': 'TICKSTORE_FULL_CHECK_V001', 'status': 'PASS_READ_ONLY',
                  'last_proven_stage': until, 'production_started': False,
                  'code_manifest_sha256': admission.descriptor['code_manifest_sha256']}))
            return 0
        if a.stage in ('D4', 'D4Close'):
            from FULL_D4_CLOSURE import close_d4
            if a.stage == 'D4Close':
                close_d4(admission)
                return 0
            command = d4_command(i, root, resume=a.resume)
            admission.revalidate()
            # Existing qualified wrapper owns DPAPI/HMAC, first admission and D4_ONLY dispatch.
            code = subprocess.call(command)
            if code == 0:
                close_d4(admission)
            return code
        sys.path.insert(0, str(root/'full'))
        if a.stage == 'Stop':
            from FULL_PROCESS_CONTROL import StopEvent
            event = StopEvent(i['run_id'], request=True)
            event.close()
            print('SAFE_STOP_REQUESTED=YES; COMPLETION_REQUIRES_RUNNER_RECEIPT', flush=True)
            return 0
        require(False, 'RUNNER_UNDISPATCHED_STAGE')


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--stage', required=True, choices=('Check', *REQUIRED_PREFIX))
    for name in ('chain-file', 'chain-sha256', 'b06-sha256'): ap.add_argument('--' + name, required=True)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--close-only', action='store_true')
    ap.add_argument('--workers', default='AUTO')
    a = ap.parse_args(argv)
    try:
        require(not a.close_only or a.stage in ('D5','CANARY','FULL_PREP','FULL_ADMIT','FULL'), 'CLOSE_ONLY_STAGE')
        require(not a.resume or a.stage == 'D4', 'RESUME_SWITCH_D4_ONLY')
        return run(a)
    except KeyboardInterrupt:
        print('FULL_RUNNER_INTERRUPTED=YES', flush=True); return 130
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print('FULL_RUNNER_BLOCKED=' + str(exc), flush=True); return 2


if __name__ == '__main__':
    raise SystemExit(main())
