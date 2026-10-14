"""Read-only preparation. Never creates a gate, authority, key, checkpoint or bundle.

Output is a proposal/evidence envelope, NOT a runtime locator receipt. The legacy
OWNER_GATE member remains a frozen-engine serialization constraint, not approval.
The O constructor, bundle, cert, launch, n_d4 and all VSS mutators are never called.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
import uuid

# R44-B2C: no policy revision literal; see POLICY_CAPTURE_BINDING.verify_capture.
RELEASE_SHA = '0DF4DDEB2FDD29850168A345A30100D5D13A806694AF6332C96C781404365FBC'
ORCH_SHA = '9EB509A2A82C0BE6D4C7AEF315AAF6B41348CECE64AB502061116DFC74419DDA'
CONFIG_SHA = '77B638CCC4B3B07D37E09D2EF40225023E2102E4C664AF96F4F599B99CC4557F'
GATES = ['ORIGIN_CURRENT_POLICY_RECONCILIATION', 'B06_INDEPENDENT_FINAL_BYTES',
         'B07_WINDOWS_FINAL_BYTES', 'FRESH_PREDECESSOR_PROCESS_LOCK_LEASE_EVIDENCE', 'FRESH_INSTANCE_ADMISSION_AND_EXECUTION_BINDINGS']

class Blocked(RuntimeError):
    pass

def require(ok, reason):
    if not ok:
        raise Blocked(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()

def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True)+'\n').encode('ascii')

def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'DUPLICATE_JSON_KEY:'+k)
            out[k] = v
        return out
    def invalid(value):
        raise Blocked('NONFINITE_JSON:'+value)
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid)

def ident(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def chain(path):
    p = Path(os.path.abspath(path))
    out = []
    for q in (p, *p.parents):
        s = os.lstat(q)
        require(not stat.S_ISLNK(s.st_mode) and not getattr(s, 'st_file_attributes', 0) & 0x400,
                'LINK_OR_REPARSE:'+str(q))
        out.append((str(q), s.st_dev, s.st_ino))
    return out

def native_identity(f):
    """Win32 identity plus creation/write/change times, all from the same handle.

    Access time is deliberately excluded: reads can update it. Change time is
    retained exactly, without rounding or tolerance. ProtectedFile.info rejects
    reparses, multiple hardlinks, delete-pending objects and final-path drift.
    """
    import ctypes
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [('creation',ctypes.c_int64),('access',ctypes.c_int64),
                    ('write',ctypes.c_int64),('change',ctypes.c_int64),('attributes',w.DWORD)]
    info = f.info()
    basic = Basic()
    f.store.check(f.store.k.GetFileInformationByHandleEx(f.handle,0,ctypes.byref(basic),ctypes.sizeof(basic)), 'BASIC_FILE_INFORMATION')
    return dict(info, creation=basic.creation, write=basic.write, change=basic.change, attributes=basic.attributes)

class Reads(contextlib.ExitStack):
    """Retain admitted buffers, fd identity and (on NTFS) protected read handles.

    POSIX revalidation is optimistic, not a Windows sharing/ACL qualification.
    Native Win32Store.open retains parents and denies file write/delete sharing.
    """
    def __init__(self, store=None):
        super().__init__()
        if store is None and os.name == 'nt':
            # Bootstrap only exact, frozen engine bytes; no execution entrypoint.
            # Windows must never fall back to unprotected CRT descriptor reads.
            engine_path = Path(__file__).parent.parent / 'recovery/engine/tickstore_publisher_recovery_v004_release.py'
            raw = engine_path.read_bytes()
            require(sha(raw) == RELEASE_SHA, 'NATIVE_READER_ENGINE_SHA')
            store = library(raw, 'first_admission_native_reader').Win32Store()
        self.store = store
        self.items = {}

    def read(self, path, expected=None):
        p = Path(os.path.abspath(path)); key = str(p)
        if key in self.items:
            raw = self.items[key]['raw']
        else:
            parents = chain(p)
            before = os.lstat(p)
            require(stat.S_ISREG(before.st_mode), 'NOT_REGULAR:'+key)
            if self.store is not None:
                f = self.enter_context(self.store.open(p))
                native = native_identity(f)
                # Compare two Win32 handles, never lstat creation time against
                # fstat metadata change time (observed on CPython 3.14.7/NTFS).
                with self.store.open(p) as by_path:
                    require(native_identity(by_path) == native, 'OPEN_IDENTITY_DRIFT:'+key)
                raw = f.read()
                require(native_identity(f) == native, 'READ_IDENTITY_DRIFT:'+key)
            else:
                fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
                f = self.enter_context(os.fdopen(fd, 'rb'))
                require(ident(os.fstat(f.fileno())) == ident(before), 'OPEN_IDENTITY_DRIFT:'+key)
                raw = f.read()
                require(ident(os.fstat(f.fileno())) == ident(before), 'READ_IDENTITY_DRIFT:'+key)
            require(ident(os.lstat(p)) == ident(before) and chain(p) == parents and len(raw) == before.st_size,
                    'READ_DRIFT:'+key)
            self.items[key] = {'raw': raw, 'identity': ident(before), 'chain': parents,
                               'handle': f if self.store is not None else None,
                               'native': native if self.store is not None else None}
        if expected is not None:
            require(sha(raw) == expected, 'SHA_MISMATCH:'+key)
        return raw

    def revalidate(self):
        for name, item in self.items.items():
            require(chain(name) == item['chain'] and ident(os.lstat(name)) == item['identity'], 'INPUT_DRIFT:'+name)
            if item['handle'] is not None:
                require(native_identity(item['handle']) == item['native'], 'HANDLE_DRIFT:'+name)
                with self.store.open(name) as current:
                    require(native_identity(current) == item['native'], 'NATIVE_PATH_DRIFT:'+name)
                    require(current.read() == item['raw'], 'CONTENT_DRIFT:'+name)
            else:
                # POSIX qualification is optimistic; never a native Windows claim.
                require(Path(name).read_bytes() == item['raw'], 'CONTENT_DRIFT:'+name)

    def evidence(self):
        return {name: {'sha256': sha(v['raw']), 'bytes': len(v['raw']), 'physical_identity': v['identity'], 'native_identity': v['native']}
                for name, v in sorted(self.items.items())}

def load_policy_binding(reads, manifest):
    """POLICY_CAPTURE_BINDING bytes admitted by the sealed first-admission code binding."""
    path = Path(__file__).with_name('POLICY_CAPTURE_BINDING.py')
    raw = reads.read(path, manifest['policy_capture_binding_sha256'])
    return library(raw, 'first_admission_policy_capture_binding')


def validate_policy(reads, root, reconciliation, reconciliation_sha, binding_module):
    chain(Path(root))
    capture = binding_module.verify_capture(reads.read, root, reconciliation, reconciliation_sha)
    return dict(capture, status='CAPTURE_VERIFIED_AND_ORIGIN_RECONCILED_NOT_LIVE',
                additional_issuer_required=False, windows_immutability='PENDING_B07')

def validate_state(state):
    require(isinstance(state, dict) and state.get('schema') == 'TICKSTORE_ORCH_STATE_V001' and
            state.get('status') == 'FAIL' and state.get('next_node') == 'D4' and
            isinstance(state.get('completed'), list) and 'D4' not in state['completed'] and
            state.get('canary_scratch_cert') is None, 'FIRST_ADMISSION_STATE_NOT_FAIL_D4')
    require(isinstance(state.get('G_CA'), dict) and isinstance(state.get('cprof'), dict), 'STATE_GENERATION_PROFILE')
    require(set(state.get('canary', {})) >= {'dest','scratch','recovery'}, 'STATE_CANARY_ROOTS')

def validate_journal(raw):
    previous = ''; count = 0
    for line in raw.splitlines():
        record = strict_json(line)
        require(isinstance(record, dict) and record.get('prev_line_sha256') == previous, 'JOURNAL_CHAIN')
        previous = sha(line); count += 1
    require(count > 0, 'JOURNAL_EMPTY')
    return {'sha256':sha(raw), 'lines':count, 'last_line_sha256':previous, 'historical_completion_inferred':False}

def library(raw, name):
    ns = {'__name__': name, '__file__': '<'+name+'>'}
    exec(compile(raw, ns['__file__'], 'exec'), ns)
    return types.SimpleNamespace(**ns)

def technical_descriptor(orch, config, roots, root_bindings, profile, generation, inventory, instance_id):
    """Reuse the actual O.gate implementation with observed immutable inputs.

    No O.__init__/STATE, Win32 mutator, gate file or authority is instantiated.
    The envelope keeps this format specimen out of legacy runtime consumers.
    """
    require(str(uuid.UUID(instance_id)) == instance_id.lower(), 'INSTANCE_UUID')
    require(len(inventory) == 1399 and all({'namespace','journal','partial','contract'} <= set(v)
            for v in inventory.values()), 'S0_1399')
    obj = object.__new__(orch.O)
    obj.cfg = dict(config)
    obj.eng = types.SimpleNamespace(Win32Store=lambda: None)
    obj.bind = lambda unused, p: dict(root_bindings[next(k for k,v in roots.items() if str(v)==str(p))])
    obj.vprof = lambda unused: dict(profile)
    gate = obj.gate('CERTIFY_SCRATCH', roots, 'FIRST_ADMISSION_'+instance_id, False, False)
    gate['admission_generation'] = dict(generation)
    gate['s0_inventory'] = inventory
    raw = canonical(gate)
    return {'schema':'TICKSTORE_D4_TECHNICAL_DESCRIPTOR_PROPOSAL_V001', 'instance_id':instance_id,
            'role':'TECHNICAL_DATA_NOT_OWNER_APPROVAL', 'production_authorized':False,
            'legacy_format_sha256':sha(raw), 'legacy_format':gate}

def no_first_admission_artifacts(resume_root, recovery_root, state_path):
    """Conservative, complete bounded scan of exact execution roots; no disk search.

    Existing authority/checkpoint/debris/certificate => stop, never repair or delete.
    Unknown files under checkpoint/authority also block (including partial receipts).
    """
    rr = Path(resume_root); sp = Path(state_path); rec = Path(recovery_root)
    checked = []
    for path in [rr, rr/'authority', rr/'checkpoint', rec, sp.parent]:
        if not os.path.lexists(path):
            nearest = path.parent
            while not os.path.lexists(nearest): nearest = nearest.parent
            chain(nearest)
            checked.append({'path':str(path), 'present':False})
            continue
        chain(path); require(path.is_dir(), 'SCOPE_NOT_DIRECTORY')
        names = sorted(p.name for p in path.iterdir())
        if path in (rr/'authority', rr/'checkpoint'):
            require(not names, 'FIRST_ADMISSION_EXISTING_AUTHORITY_OR_CHECKPOINT')
        if path == rec:
            require(not names, 'FIRST_ADMISSION_RECOVERY_NOT_EMPTY')
        if path == sp.parent:
            require(not any(n.startswith(sp.name) and '.cas-' in n for n in names), 'STATE_CAS_RECOVERY_REQUIRED')
            # Archived partial finalizations also need explicit diagnosis.
            archive = path/'cas_recovery'
            if archive.exists():
                require(not any(archive.iterdir()), 'CAS_ARCHIVE_REQUIRES_DIAGNOSIS')
        checked.append({'path':str(path), 'present':True, 'names':names})
    require(rec.is_dir(), 'RECOVERY_ROOT_MISSING')
    return checked

def observe_native(reads, engine, orch, adapter, binding, cfg, state, instance):
    require(os.name == 'nt' and reads.store is not None, 'NATIVE_WINDOWS_REQUIRED')
    roots = {k:Path(state['canary'][k]) for k in ('dest','scratch','recovery')}
    require(len({os.path.normcase(os.path.abspath(v)) for v in roots.values()}) == 3, 'ROOT_ALIAS')
    native = reads.store
    root_handles = {k:reads.enter_context(native.open(p, directory=True)) for k,p in roots.items()}
    bindings = {k:h.info() for k,h in root_handles.items()}
    profile = state['cprof']; historical = state['G_CA']
    require(profile['volume_identity'] == binding['expected_volume_identity'], 'PROFILE_VOLUME_IDENTITY')
    require(adapter.normalize_path(profile['volume_guid']) == adapter.normalize_path(binding['expected_volume_guid']), 'PROFILE_VOLUME_GUID')
    require(all(v['volume'] == profile['volume_identity'] for v in bindings.values()), 'ROOT_VOLUME_IDENTITY')
    require(len({(v['volume'], str(v['file_id'])) for v in bindings.values()}) == 3, 'ROOT_PHYSICAL_ALIAS')
    vss = engine.NativeVSS(native, profile)
    try:
        generation = adapter.reconcile_generation(vss, historical, binding)
        current = vss.properties(historical['snapshot_id'])
        require(not current['attributes'] & 4, 'G_CA_CLIENT_ACCESSIBLE')
        shadow_root = Path(generation['device_object']+'\\')
        shadow_scratch = vss.shadow_root(generation, roots['scratch'])
        with native.open(shadow_root, directory=True): pass
        with native.open(shadow_scratch, directory=True): pass
        obj = object.__new__(orch.O); obj.eng = engine
        inventory = obj.invs0(shadow_scratch)
        require(adapter.reconcile_generation(vss, historical, binding) == generation, 'G_CA_CHANGED_DURING_SCAN')
    finally:
        vss.close()
    descriptor = technical_descriptor(orch, cfg, roots, bindings, profile, historical, inventory, instance)
    locator = {'schema':'TICKSTORE_G_CA_OBSERVATION_V002', 'status':'OBSERVED_NOT_ADMITTED',
               'instance_id':instance, 'generation':generation, 'historical_generation':historical,
               'snapshot_state':12, 'attributes':current['attributes'], 'original_volume_guid':current['volume_guid'],
               'shadow_root_open':True, 'shadow_scratch_open':True, 'snapshot_recreation_required':False,
               'technical_descriptor_sha256':descriptor['legacy_format_sha256'],
               'root_bindings':bindings, 'inventory_sha256':sha(canonical(inventory))}
    return locator, descriptor

def prepare(policy_root, reconciliation, reconciliation_sha, package, adapter_dir, resume_root, instance_id, observe=False, binding_sha=None):
    require(isinstance(binding_sha, str) and re.fullmatch(r"[0-9A-F]{64}", binding_sha), "EXTERNAL_PREPARATION_BINDING_SHA_REQUIRED")
    require(str(uuid.UUID(instance_id)) == instance_id.lower(), 'INSTANCE_UUID')
    package = Path(package); adapter_dir = Path(adapter_dir)
    # Code admitted by exact digests; the native library has no __main__ dispatch.
    with Reads() as initial:
        eraw = initial.read(package/'engine/tickstore_publisher_recovery_v004_release.py', RELEASE_SHA)
        oraw = initial.read(package/'modules/orchestrator.py', ORCH_SHA)
        manifest = strict_json(initial.read(Path(__file__).with_name('FIRST_ADMISSION_BINDING.json'), binding_sha))
        require(manifest['schema'] == 'TICKSTORE_FIRST_ADMISSION_CODE_BINDING_V001', 'PREP_BINDING_SCHEMA')
        ar = initial.read(adapter_dir/'runtime_locator_adapter.py', manifest['adapter_sha256'])
        br = initial.read(adapter_dir/'RUNTIME_LOCATOR_ADAPTER_BINDING.json', manifest['runtime_binding_sha256'])
        initial.read(__file__, manifest['preparation_sha256'])
        initial.read(Path(__file__).with_name('60_EFFECTFUL_WRAPPER_RELEASE.ps1'), manifest['wrapper_sha256'])
        policy_binding = load_policy_binding(initial, manifest)
        initial.revalidate()
    engine = library(eraw, 'first_admission_frozen_engine') if observe else None
    if observe: require(os.name == 'nt', 'NATIVE_WINDOWS_REQUIRED')
    store = engine.Win32Store() if observe else None
    with Reads(store) as reads:
        # Retain code handles with the same sharing discipline as inputs.
        for p, data in [(package/'engine/tickstore_publisher_recovery_v004_release.py',eraw),
                        (package/'modules/orchestrator.py',oraw), (adapter_dir/'runtime_locator_adapter.py',ar),
                        (adapter_dir/'RUNTIME_LOCATOR_ADAPTER_BINDING.json',br)]:
            reads.read(p, sha(data))
        policy = validate_policy(reads, policy_root, reconciliation, reconciliation_sha, policy_binding)
        report = {'schema':'TICKSTORE_D4_FIRST_ADMISSION_PREPARATION_V001', 'role':'EXTERNAL_ISOLATED_IMPLEMENTER',
                  'instance_id':instance_id, 'observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                  'status':'PREPARED_NOT_ADMITTED', 'production_authorized':False, 'execution_allowed':False,
                  'B06_independent':'PENDING', 'gates_pending':GATES, 'policy':policy,
                  'native_observation_executed':observe, 'descriptor':None, 'locator':None,
                  'code_binding_sha256':binding_sha}
        if observe:
            cfg = strict_json(reads.read(package/'config/STAGE_A_SEALED_VALUES_V001.json', CONFIG_SHA))
            reads.read(sys.executable, cfg['python_exe_sha256'])
            state_path = Path(cfg['control_root'])/'state/STATE.json'
            state = strict_json(reads.read(state_path)); validate_state(state)
            report['journal'] = validate_journal(reads.read(state_path.with_name('STATE_JOURNAL.jsonl')))
            before = no_first_admission_artifacts(resume_root, state['canary']['recovery'], state_path)
            adapter = library(ar, 'first_admission_adapter'); binding = strict_json(br)
            adapter.validate_binding(binding)
            report['locator'], report['descriptor'] = observe_native(reads, engine, library(oraw, 'first_admission_orchestrator'),
                                                                     adapter, binding, cfg, state, instance_id)
            after = no_first_admission_artifacts(resume_root, state['canary']['recovery'], state_path)
            require(before == after, 'EXECUTION_SCOPE_CHANGED')
            report['absence_scope'] = after
            report['policy']['windows_immutability'] = 'READ_HANDLES_HELD_DURING_OBSERVATION_NOT_B07_PASS'
        else:
            report['gates_pending'] = ['WINDOWS_G_CA_POLICYROOT_ROOTS_PREDECESSOR_OBSERVATION'] + GATES
        # Also detect cardinality changes, not just changes to existing policy files.
        require(validate_policy(reads, policy_root, reconciliation, reconciliation_sha, policy_binding) == policy,
                'POLICY_DRIFT_DURING_PREPARATION')
        reads.revalidate()
        report['inputs'] = reads.evidence()
        report['input_binding_sha256'] = sha(canonical(report['inputs']))
        return report

def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    for arg in ('policy-root','policy-reconciliation','policy-reconciliation-sha256','package','adapter-dir','resume-root','instance-id','binding-sha'):
        ap.add_argument('--'+arg, required=True)
    ap.add_argument('--observe-native', action='store_true')
    a = ap.parse_args(argv)
    try:
        r = prepare(a.policy_root, a.policy_reconciliation, a.policy_reconciliation_sha256, a.package, a.adapter_dir, a.resume_root, a.instance_id, a.observe_native, a.binding_sha)
        print(json.dumps(r, indent=2)); return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({'schema':'TICKSTORE_D4_FIRST_ADMISSION_PREPARATION_V001', 'status':'BLOCKED',
                          'execution_allowed':False, 'production_authorized':False, 'reason':str(e),
                          'instance_id':a.instance_id, 'B06_independent':'PENDING'})); return 2

if __name__ == '__main__':
    raise SystemExit(main())
