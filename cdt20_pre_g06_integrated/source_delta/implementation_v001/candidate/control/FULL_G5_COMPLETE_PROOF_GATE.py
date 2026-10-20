"""Fail-closed G5-to-FULL admission: a scoped G5 receipt is not a FULL release.

This module is consumed by FULL_RELEASE_CHAIN under native pinned read handles.
It does not mint a receipt, issue owner authority, or substitute for independent B06.
"""
from __future__ import annotations
import hashlib
import json
import re
import io
import zipfile

class G5Incomplete(RuntimeError):
    pass

HEX = re.compile(r"[0-9A-F]{64}\Z")
ROLES = ("ENGINEERING_COMPLETENESS", "G5_STAGE_COMPLETENESS", "G5_EVIDENCE_PACK",
         "ORIGIN_DECISION", "G5_INTEGRATION_MANIFEST", "G5_INTEGRATION_SOURCE", "NATIVE_RETURN_ZIP",
         "FINAL_PACKAGE_ZIP")
FIVE = ("all_implementations_integrated", "all_known_fixable_blockers_closed",
        "tested_equals_packaged_new_final_code", "adversarial_false_completeness_check",
        "frozen_for_independent_audit")

def inspect_pre_b06_eleven_consumer_evidence(dossier, candidate_root, evidence_root, *, native_required=True):
    """Pre-audit technical evidence; NEVER returns a FINAL G5 or D4 PASS.

    V001 eleven-effect chain is reserved for operational/post-audit proof.
    Separate V002 contract does not waive B06/B07 or downstream admission.
    """
    from pathlib import Path
    import importlib.util
    target=Path(__file__).with_name('PRE_B06_ENGINEERING_GATE.py')
    spec=importlib.util.spec_from_file_location('_cdt19_pre_b06_gate',str(target))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_dossier(dossier,candidate_root,evidence_root,native_required=native_required)


def req(value, message):
    if not value:
        raise G5Incomplete("G5_FINAL_" + message)

def strict(raw):
    def hook(pairs):
        ret = {}
        for key, value in pairs:
            req(key not in ret, "JSON_DUPLICATE_KEY")
            ret[key] = value
        return ret
    return json.loads(raw.decode("utf-8"), object_pairs_hook=hook)

def digest(raw):
    return hashlib.sha256(raw).hexdigest().upper()

def validate_g5_complete_proof(stage_receipt, code_manifest_sha, instance_sha, pinned_read):
    """Evidence-only gate, cannot be passed by a scoped owner/G5 legacy receipt.

    The independent Windows producer of a FINAL candidate must supply physically
    pinned, hash-bound proof of each of the canonical five completeness parts.
    A field merely saying PASS without its sealed final-byte evidence is blocked.
    """
    req(isinstance(stage_receipt, dict) and stage_receipt.get("stage") == "G5", "RECEIPT_STAGE")
    req(stage_receipt.get("status") == "PASS" and
        stage_receipt.get("environment") == "WINDOWS_PRODUCTION", "NOT_NATIVE_PASS")
    req(stage_receipt.get("code_manifest_sha256") == code_manifest_sha and
        stage_receipt.get("instance_sha256") == instance_sha, "RUNTIME_INSTANCE_BINDING")
    # A historical G5 scoped owner decision is not re-issued for the final package.
    # This field is deliberately absent on those receipts and prevents migration by copy.
    req(stage_receipt.get("full_candidate_completeness") == "PASS", "SCOPED_RECEIPT_NOT_FULL")
    evs = stage_receipt.get("evidence")
    req(isinstance(evs, list), "EVIDENCE_LIST")
    roles = {}
    for item in evs:
        req(isinstance(item,dict), "EVIDENCE_RECORD")
        role=item.get("role")
        req(isinstance(role,str) and role and role not in roles, "EVIDENCE_DUPLICATE_OR_ROLE")
        path=item.get("path"); sha=item.get("sha256")
        req(isinstance(path,str) and path and isinstance(sha,str) and HEX.fullmatch(sha), "EVIDENCE_FIELDS")
        roles[role]=(path,sha)
    req(set(ROLES) <= set(roles), "REQUIRED_EVIDENCE_MISSING")
    bodies = {role: pinned_read(*roles[role]) for role in ROLES}
    for role in ROLES:
        req(digest(bodies[role]) == roles[role][1], "EVIDENCE_SHA:"+role)
    comp = strict(bodies["ENGINEERING_COMPLETENESS"])
    req(comp.get("schema") == "TICKSTORE_ENGINEERING_COMPLETENESS_V003" and
        comp.get("status") == "COMPLETE", "ENGINEERING_NOT_COMPLETE")
    req(comp.get("code_manifest_sha256") == code_manifest_sha and
        comp.get("instance_sha256") == instance_sha, "COMPLETENESS_BINDING")
    req(comp.get("known_blockers") == [] and comp.get("full_started") is False and
        comp.get("formal_audit_started") is False, "OPEN_BLOCKERS_OR_PREMATURE_STAGE")
    parts=comp.get("five_part_completeness")
    req(isinstance(parts,dict) and set(parts) == set(FIVE), "FIVE_PART_SET")
    native_preview=native_zip_members(bodies['NATIVE_RETURN_ZIP'])
    preview_result=strict(native_preview['ENGINEERING_RESULT.json'])
    v002=(preview_result.get('schema')=='CDT19_PRE_B06_NATIVE_ENGINEERING_V002')
    chain_role='PRE_B06_11_CHAIN' if v002 else 'LEGACY_11_CHAIN'
    # Each PASS requires an independently readable evidence object tied to the
    # code and instance, not an unqualified boolean in G5 or in a summary report.
    for part in FIVE:
        entry = parts[part]
        req(isinstance(entry,dict) and entry.get("status") == "PASS", "FIVE_PART_NOT_PASS:"+part)
        req(entry.get("code_manifest_sha256") == code_manifest_sha and
            entry.get("instance_sha256") == instance_sha, "FIVE_PART_CODE_DRIFT:"+part)
        path, sh = entry.get("path"), entry.get("sha256")
        req(isinstance(path,str) and path and isinstance(sh,str) and HEX.fullmatch(sh), "FIVE_PART_PROOF_MISSING:"+part)
        raw = pinned_read(path, sh)
        req(digest(raw) == sh, "FIVE_PART_PROOF_SHA:"+part)
        proof = strict(raw)
        req(proof.get("schema") == "TICKSTORE_FINAL_COMPLETENESS_PROOF_V001" and
            proof.get("part") == part and proof.get("status") == "PASS" and
            proof.get("code_manifest_sha256") == code_manifest_sha and
            proof.get("instance_sha256") == instance_sha, "FIVE_PART_PROOF_SEMANTICS:"+part)
        elements = proof.get("evidence")
        req(isinstance(elements,list) and len(elements)>0, "FIVE_PART_NO_SUBSTANTIVE_EVIDENCE:"+part)
        seen = set()
        for elem in elements:
            req(isinstance(elem,dict) and isinstance(elem.get("role"),str) and elem["role"] not in seen,
                "FIVE_PART_EVIDENCE_ROLE:"+part)
            seen.add(elem["role"])
            ep, es = elem.get("path"), elem.get("sha256")
            req(isinstance(ep,str) and ep and isinstance(es,str) and HEX.fullmatch(es),
                "FIVE_PART_EVIDENCE_FIELDS:"+part)
            req(digest(pinned_read(ep, es)) == es, "FIVE_PART_EVIDENCE_NOT_PINNED:"+part)
        req({'FINAL_PACKAGE_ZIP', 'ADVERSARIAL_CLOSURE', chain_role} <= seen,
            'FIVE_PART_REQUIRED_ROLES:' + part)
    # Require an ACTUAL packaged FINAL archive, not the older owner-scoped FULL.
    raw_zip=bodies["FINAL_PACKAGE_ZIP"]
    req(digest(raw_zip)==stage_receipt.get("final_package_sha256"), "FINAL_PACKAGE_ZIP_BINDING")
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as arc:
            infos=arc.infolist(); names=[r.filename for r in infos]
            req(all(not r.is_dir() and not r.filename.startswith('/') and '\\' not in r.filename
                    and ':' not in r.filename and '..' not in r.filename.split('/') for r in infos),
                "FINAL_PACKAGE_UNSAFE_ENTRY")
            req(len(names)==len(set(n.casefold() for n in names)), "FINAL_PACKAGE_DUPLICATE_ENTRY")
            req(arc.testzip() is None, "FINAL_PACKAGE_CRC")
            manifest=strict(arc.read("PACKAGE_MANIFEST.json"))
            req(manifest.get("schema")=="TICKSTORE_FINAL_PACKAGE_MANIFEST_V001", "FINAL_PACKAGE_MANIFEST_SCHEMA")
            declared={r["path"]:r for r in manifest["files"]}
            req(len(declared) == len(manifest['files']), 'FINAL_PACKAGE_MANIFEST_DUPLICATE')
            req(set(declared)==set(names)-{"PACKAGE_MANIFEST.json"}, "FINAL_PACKAGE_MANIFEST_EXACT_SET")
            for path, entry in declared.items():
                raw=arc.read(path)
                req(len(raw)==entry.get("bytes") and digest(raw)==entry.get("sha256"),
                    "FINAL_PACKAGE_MEMBER_SHA:"+path)
            req(digest(arc.read("implementation_v001/RUNTIME_CODE_MANIFEST.json"))==code_manifest_sha,
                "FINAL_PACKAGE_CODE_MANIFEST_DRIFT")
    except (KeyError, ValueError, zipfile.BadZipFile, TypeError) as error:
        raise G5Incomplete("G5_FINAL_PACKAGE_FORMAT:"+type(error).__name__) from error
    decision = strict(bodies["ORIGIN_DECISION"])
    req(decision.get("stage") == "G5" and decision.get("decision") == "PASS" and
        decision.get("code_manifest_sha256") == code_manifest_sha and
        decision.get("instance_sha256") == instance_sha and
        decision.get("final_package_sha256") == digest(raw_zip), "ORIGIN_DECISION_OLD_OR_WRONG_CODE")
    req(stage_receipt.get("origin_decision_sha256") == roles["ORIGIN_DECISION"][1], "ORIGIN_DECISION_RECEIPT_DRIFT")
    # The externally supplied decision must bind the observations as well as the
    # package. Otherwise a different, self-consistent campaign could be substituted.
    decision_evidence = decision.get('evidence')
    req(isinstance(decision_evidence, list), 'ORIGIN_DECISION_EVIDENCE_MISSING')
    native_decisions = [e for e in decision_evidence if isinstance(e, dict)
                        and e.get('role') == 'NATIVE_RETURN_ZIP']
    req(len(native_decisions) == 1 and native_decisions[0].get('sha256') ==
        digest(bodies['NATIVE_RETURN_ZIP']), 'ORIGIN_DECISION_NATIVE_RETURN_BINDING')
    # Hashing an opaque native attachment is not validation of its contents.
    # The same verifier is used by the evidence producer and this consumer.
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as arc:
        final_members={name:arc.read(name) for name in arc.namelist()}
        runtime = strict(arc.read('implementation_v001/RUNTIME_CODE_MANIFEST.json'))
        req(runtime.get('schema') == 'TICKSTORE_FINAL_RUNTIME_CODE_MANIFEST_V001', 'RUNTIME_SCHEMA')
        rows = runtime.get('files')
        req(isinstance(rows, list), 'RUNTIME_FILES')
        index = {r['path']: r for r in rows}
        req(len(index) == len(rows), 'RUNTIME_DUPLICATE_PATH')
        prefix = 'implementation_v001/candidate/'
        req(set(index) == {n[len(prefix):] for n in arc.namelist() if n.startswith(prefix)}, 'RUNTIME_EXACT_SET')
        for path, record in index.items():
            data = arc.read(prefix + path)
            req(len(data) == record.get('bytes') and digest(data) == record.get('sha256'), 'RUNTIME_MEMBER:' + path)
    native, units, native_members = verify_native_campaign(bodies['NATIVE_RETURN_ZIP'], code_manifest_sha, digest(raw_zip), index, final_members=final_members)
    req(comp.get('native_g5_return_sha256') == digest(bodies['NATIVE_RETURN_ZIP']), 'NATIVE_COMPLETENESS_BINDING')
    integration = strict(bodies['G5_INTEGRATION_MANIFEST'])
    required_integration = ('control/FULL_RELEASE_CHAIN.py', 'control/FULL_G5_COMPLETE_PROOF_GATE.py',
                           'control/ORIGIN_DECISION_BINDER.py', 'control/G5_C6_FORMAL_CONTRACT.py',
                           'control/G5_C6_FORMAL_STAGE_BUILDER.py', 'control/FULL_QUALIFICATION_CONTRACT.py',
                           'control/G5_FINAL_COMPLETENESS_PRODUCER.py')
    if v002:
        required_integration += ('control/PRE_B06_ENGINEERING_GATE.py',
                                 'g5proof/NATIVE_EXECUTION_OBSERVER.py')
    req(integration.get('schema') == 'CDT17_G5_FINAL_INTEGRATED_CODE_MANIFEST_V001'
        and integration.get('binding_mode') == 'FINAL_CANDIDATE'
        and integration.get('code_manifest_sha256') == code_manifest_sha
        and integration.get('final_package_sha256') == digest(raw_zip), 'INTEGRATION_MANIFEST_BINDING')
    integration_rows = integration.get('files')
    req(isinstance(integration_rows, list) and len(integration_rows) == len(required_integration)
        and {r.get('path') for r in integration_rows} == set(required_integration), 'INTEGRATION_FILE_SET')
    req(all(r['path'] in index and r['sha256'] == index[r['path']]['sha256']
            and r['bytes'] == index[r['path']]['bytes'] for r in integration_rows), 'INTEGRATION_FILE_BYTES')
    req(digest(bodies['G5_INTEGRATION_SOURCE']) == index['control/G5_C6_FORMAL_CONTRACT.py']['sha256'],
        'INTEGRATION_SOURCE_BYTES')
    for part in FIVE:
        proof = strict(pinned_read(parts[part]['path'], parts[part]['sha256']))
        part_roles = {r['role']: r for r in proof['evidence']}
        req(part_roles['FINAL_PACKAGE_ZIP']['sha256'] == digest(raw_zip), 'FIVE_PART_OTHER_PACKAGE')
        req(part_roles[chain_role]['sha256'] == units[chain_role][1], 'FIVE_PART_OTHER_CHAIN')
        adversarial = strict(pinned_read(part_roles['ADVERSARIAL_CLOSURE']['path'], part_roles['ADVERSARIAL_CLOSURE']['sha256']))
        req(adversarial.get('schema') == 'TICKSTORE_FINAL_ADVERSARIAL_ENGINEERING_ATTESTATION_V001'
            and adversarial.get('status') == 'PASS' and adversarial.get('known_blockers') == []
            and adversarial.get('candidate_sha256') == digest(raw_zip)
            and adversarial.get('code_manifest_sha256') == code_manifest_sha
            and adversarial.get('native_g5_return_sha256') == digest(bodies['NATIVE_RETURN_ZIP'])
            and adversarial.get('legacy_technical_consumer_count') == 11
            and adversarial.get('false_completeness_search') == 'PASS'
            and adversarial.get('state_toctou_receipt_checkpoint_negative_controls') == 'PASS'
            and adversarial.get('final_bytes_freeze') == 'PASS', 'ADVERSARIAL_CLOSURE_NOT_PROVEN')
        for role, ref in part_roles.items():
            if role in units:
                req(ref['sha256'] == units[role][1], 'FIVE_PART_OTHER_NATIVE_UNIT:' + role)
    pack = strict(bodies["G5_EVIDENCE_PACK"])
    req(pack.get("code_manifest_sha256") == code_manifest_sha, "G5_PACK_CODE_DRIFT")
    stage = strict(bodies["G5_STAGE_COMPLETENESS"])
    req(stage.get("full_candidate_completeness") == "PASS" and
        stage.get("original_full_sha256") == decision.get("final_package_sha256"), "G5_STAGE_NOT_FINAL_PACKAGE")
    return {"status":"PASS", "five_parts_verified":5, "code_manifest_sha256":code_manifest_sha}


LEGACY11 = (
    'adapter/INLINE_ROOT_LOADER_V004_R1R1_ADAPTER.ps1',
    'adapter/runtime_locator_adapter.py', 'adapter/runtime_locator_inline_entry.py',
    'adapter/runtime_locator_orchestrator_entry.py', 'control/60_EFFECTFUL_WRAPPER_RELEASE.ps1',
    'control/D4_FIRST_ADMISSION_TRANSACTION.py', 'control/D4_ROOTS_EVIDENCE.py',
    'recovery/engine/tickstore_publisher_recovery_v004_candidate.py',
    'recovery/engine/tickstore_publisher_recovery_v004_release.py',
    'recovery/loader/INLINE_ROOT_LOADER_V004_R1R1.ps1', 'recovery/modules/orchestrator.py')
NEGATIVE_CONTROLS = ('STATE_RECREATION', 'CONFIG_TOCTOU', 'CONCURRENT_RECEIPT_OVERWRITE',
                     'FAILURE_AFTER_CHECKPOINT')


# Resource bound against decompression bombs, not an evidence criterion. A real
# PRE-G06 return carries the full G3/G6 physical namespace (~197 MB in the 12:19
# native run) plus every other unit, so the earlier 512 MiB bound was untested
# against a complete successful campaign and could block a valid readback.
NATIVE_ZIP_MAX_MEMBERS = 20000
NATIVE_ZIP_MAX_UNCOMPRESSED = 1536 * 1024**2


def native_zip_members(raw):
    """Bounded, exact-name ZIP read; no extraction and no execution of evidence."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as arc:
            infos = arc.infolist()
            names = [r.filename for r in infos]
            req(len(names) <= NATIVE_ZIP_MAX_MEMBERS and sum(r.file_size for r in infos) <= NATIVE_ZIP_MAX_UNCOMPRESSED,
                'NATIVE_ZIP_BOUNDS')
            req(len(names) == len({n.casefold() for n in names}), 'NATIVE_ZIP_DUPLICATE')
            req(all(not r.is_dir() and r.filename and not r.filename.startswith('/')
                    and '\\' not in r.filename and ':' not in r.filename
                    and all(p not in ('', '.', '..') for p in r.filename.split('/'))
                    and (r.external_attr >> 16) & 0xF000 != 0xA000 for r in infos), 'NATIVE_ZIP_UNSAFE')
            req(arc.testzip() is None, 'NATIVE_ZIP_CRC')
            return {n: arc.read(n) for n in names}
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise G5Incomplete('G5_FINAL_NATIVE_ZIP_INVALID:' + type(error).__name__) from error


def _physical_ref(ref, members, label):
    req(isinstance(ref, dict), label + '_REF')
    name = ref.get('member')
    req(isinstance(name, str) and name in members, label + '_MISSING')
    raw = members[name]
    req(type(ref.get('bytes')) is int and len(raw) == ref['bytes'] and
        digest(raw) == ref.get('sha256'), label + '_BYTES')
    return raw


ENTRYPOINTS = dict(zip(LEGACY11, (
    ('Invoke-TickstoreInlineRootV004R1Adapter',),
    ('install_engine_namespace', 'install_orchestrator_namespace'), ('main',), ('main',),
    ('<script>',), ('materialize',), ('main',), ('dispatch_bootstrap',),
    ('dispatch_bootstrap',), ('Invoke-TickstoreInlineRootV004R1',), ('execute',))))


def verify_execution_observation(event, members, runtime_index):
    """Check physical call/return, runner, source and output bindings.

    These consistency checks cannot authenticate arbitrary bytes authored by an
    untrusted issuer. Operational admission additionally requires the externally
    supplied origin decision to bind the exact native-return archive digest.
    """
    obs = strict(_physical_ref(event.get('observation'), members, 'LEGACY_11_OBSERVATION'))
    path = event['source_path']
    req(obs.get('schema') == 'TICKSTORE_EXECUTION_OBSERVATION_V001'
        and obs.get('run_id') == event['run_id'] and obs.get('pid') == event['pid']
        and obs.get('process_creation_filetime') == event['process_creation_filetime']
        and obs.get('exit_code') == 0 and obs.get('native_windows') is True,
        'LEGACY_11_OBSERVATION_PROCESS')
    source = _physical_ref(obs.get('source'), members, 'LEGACY_11_OBSERVED_SOURCE')
    req(digest(source) == event['source_sha256'] == runtime_index[path]['sha256']
        and len(source) == runtime_index[path]['bytes'], 'LEGACY_11_OBSERVED_SOURCE_DRIFT')
    runner = obs.get('runner')
    req(isinstance(runner, dict) and runner.get('path') in runtime_index, 'LEGACY_11_RUNNER_REQUIRED')
    runner_raw = _physical_ref(runner.get('source'), members, 'LEGACY_11_RUNNER_SOURCE')
    req(digest(runner_raw) == runtime_index[runner['path']]['sha256']
        and len(runner_raw) == runtime_index[runner['path']]['bytes'], 'LEGACY_11_RUNNER_DRIFT')
    trace_raw = _physical_ref(obs.get('trace'), members, 'LEGACY_11_CALL_TRACE')
    trace = [strict(line) for line in trace_raw.splitlines()]
    req(trace and len(trace) <= 1000000, 'LEGACY_11_CALL_TRACE_EMPTY')
    previous = ''; calls = {}; completed = set()
    for n, (record, raw) in enumerate(zip(trace, trace_raw.splitlines())):
        req(record.get('sequence') == n and record.get('previous_sha256') == previous
            and record.get('pid') == event['pid'] and record.get('run_id') == event['run_id'],
            'LEGACY_11_CALL_TRACE_CHAIN')
        previous = digest(raw)
        call_id = record.get('call_id')
        req(isinstance(call_id, int) and call_id >= 0, 'LEGACY_11_CALL_ID')
        if record.get('phase') == 'CALL':
            req(call_id not in calls, 'LEGACY_11_CALL_DUPLICATE')
            calls[call_id] = record
        elif record.get('phase') == 'RETURN':
            req(call_id in calls and call_id not in completed, 'LEGACY_11_RETURN_WITHOUT_CALL')
            first = calls[call_id]
            req(all(record.get(k) == first.get(k) for k in ('source_path','source_sha256','function')),
                'LEGACY_11_RETURN_SOURCE')
            completed.add(call_id)
        else: req(False, 'LEGACY_11_TRACE_PHASE')
    req(set(calls) == completed, 'LEGACY_11_UNCLOSED_CALL')
    entrypoint = event.get('entrypoint')
    req(entrypoint in ENTRYPOINTS[path], 'LEGACY_11_ENTRYPOINT')
    req(any(r.get('source_path') == path and r.get('source_sha256') == event['source_sha256']
            and r.get('function') == entrypoint for r in calls.values()), 'LEGACY_11_ENTRY_NOT_CALLED')
    effects = obs.get('effects')
    req(isinstance(effects, list) and effects, 'LEGACY_11_OBSERVED_EFFECTS')
    req({e.get('sha256') for e in effects if isinstance(e, dict)} ==
        {e['sha256'] for e in event['outputs']}, 'LEGACY_11_OBSERVED_EFFECT_SET')
    for effect in effects:
        _physical_ref(effect, members, 'LEGACY_11_OBSERVED_EFFECT')
        req(effect.get('before_sha256') != effect['sha256'], 'LEGACY_11_NO_EFFECT')
    return obs


def verify_legacy11(members, result, code_sha, package_sha, runtime_index=None):
    """Require actual linked effect receipts, not 11 hashes or a PASS label.

    This verifies evidence consistency. It does not authenticate a human issuer,
    issue the origin's decision, or turn test fixtures into native observation.
    """
    req(isinstance(runtime_index, dict) and set(LEGACY11) <= set(runtime_index),
        'LEGACY_11_RUNTIME_INDEX_REQUIRED')
    body = _physical_ref(result.get('legacy_11_effectful_receipt'), members, 'LEGACY_11_CHAIN_REQUIRED')
    chain = strict(body)
    req(chain.get('schema') == 'TICKSTORE_LEGACY_11_EFFECTFUL_INTEGRATION_V001'
        and chain.get('status') == 'PASS_EFFECTFUL_INTEGRATED'
        and chain.get('native_windows') is True and chain.get('scope') == 'OWNED_SCRATCH'
        and chain.get('synthetic_substitute') is False
        and chain.get('production_modified') is False, 'LEGACY_11_CHAIN_NOT_PROVEN')
    req(chain.get('code_manifest_sha256') == code_sha and chain.get('final_zip_sha256') == package_sha,
        'LEGACY_11_SOURCE_BINDING')
    req(isinstance(chain.get('run_id'), str) and re.fullmatch('[0-9A-F]{32}', chain['run_id']), 'LEGACY_11_RUN_ID')
    run_id = chain['run_id']
    rows = chain.get('executions')
    req(isinstance(rows, list) and len(rows) == len(LEGACY11), 'LEGACY_11_EXECUTIONS_REQUIRED')
    req({r.get('source_path') for r in rows if isinstance(r, dict)} == set(LEGACY11), 'LEGACY_11_EXACT_SET')
    ids, artifact_hashes = set(), set()
    for item in rows:
        event = strict(_physical_ref(item.get('receipt'), members, 'LEGACY_11_EXECUTION'))
        path, source_sha = item['source_path'], item.get('source_sha256')
        req(isinstance(source_sha, str) and HEX.fullmatch(source_sha), 'LEGACY_11_SOURCE_HASH')
        req(path in runtime_index and source_sha == runtime_index[path]['sha256'], 'LEGACY_11_PACKAGED_SOURCE:' + path)
        req(event.get('schema') == 'TICKSTORE_NATIVE_CONSUMER_EFFECT_V001'
            and event.get('source_path') == path and event.get('source_sha256') == source_sha
            and event.get('run_id') == run_id and event.get('native_windows') is True
            and event.get('status') == 'COMMITTED' and event.get('test_only_branch') is False,
            'LEGACY_11_EFFECT_NOT_PROVEN:' + path)
        eid = event.get('event_id')
        req(isinstance(eid, str) and eid and eid not in ids, 'LEGACY_11_EVENT_ID')
        parents = event.get('predecessor_event_ids')
        req(isinstance(parents, list) and len(parents) == len(set(parents))
            and set(parents) <= ids and (bool(parents) or not ids), 'LEGACY_11_CAUSAL_CHAIN')
        req(type(event.get('pid')) is int and event['pid'] > 0
            and type(event.get('process_creation_filetime')) is int and event['process_creation_filetime'] > 0,
            'LEGACY_11_PROCESS_IDENTITY')
        outputs = event.get('outputs')
        req(isinstance(outputs, list) and outputs, 'LEGACY_11_EFFECT_ARTIFACTS_REQUIRED')
        for ref in outputs:
            _physical_ref(ref, members, 'LEGACY_11_EFFECT_ARTIFACT')
            artifact_hashes.add(ref['sha256'])
        verify_execution_observation(event, members, runtime_index)
        ids.add(eid)
    terminal = strict(_physical_ref(chain.get('terminal_readback'), members, 'LEGACY_11_TERMINAL'))
    req(terminal.get('schema') == 'TICKSTORE_NATIVE_CHAIN_TERMINAL_V001'
        and terminal.get('run_id') == run_id and terminal.get('source_event_ids') == sorted(ids)
        and terminal.get('effect_artifact_sha256') == sorted(artifact_hashes)
        and terminal.get('tree_members_after_exit') == []
        and terminal.get('state_journal_checkpoint_consistent') is True, 'LEGACY_11_TERMINAL_RECONCILIATION')
    controls = chain.get('negative_controls')
    req(isinstance(controls, dict) and set(controls) == set(NEGATIVE_CONTROLS), 'LEGACY_11_NEGATIVE_CONTROLS_REQUIRED')
    for name in NEGATIVE_CONTROLS:
        probe = strict(_physical_ref(controls[name], members, 'LEGACY_11_NEGATIVE_' + name))
        req(probe.get('schema') == 'TICKSTORE_NATIVE_NEGATIVE_CONTROL_V001'
            and probe.get('probe') == name and probe.get('native_windows') is True
            and probe.get('run_id') == run_id and probe.get('status') == 'PASS'
            and probe.get('reproduction_observed') is True and probe.get('fixed_probe_rejected') is True
            and probe.get('positive_control_committed') is True,
            'LEGACY_11_NEGATIVE_NOT_PROVEN:' + name)
        refs = probe.get('artifacts')
        req(isinstance(refs, list) and len(refs) >= 2, 'LEGACY_11_NEGATIVE_ARTIFACTS:' + name)
        for ref in refs:
            _physical_ref(ref, members, 'LEGACY_11_NEGATIVE_ARTIFACT')
    return chain


def verify_pre_b06_v002(members, result, code_sha, package_sha, runtime_index, final_members):
    """V002 is engineering readiness, not protected operational effect authority.

    Never accepts an opaque 11-entry list of PASS values: every witness is
    read and verified against the exact packaged code plus native-return bytes.
    """
    req(isinstance(final_members,dict) and isinstance(runtime_index,dict),
        'PRE_B06_FINAL_SOURCE_REQUIRED')
    record=result.get('pre_b06_11_receipt')
    dossier=strict(_physical_ref(record,members,'PRE_B06_11_RECEIPT'))
    req(dossier.get('schema')=='TICKSTORE_PRE_B06_11_CONSUMER_EVIDENCE_V002',
        'PRE_B06_EVIDENCE_SCHEMA')
    req(dossier.get('code_manifest_sha256')==code_sha,
        'PRE_B06_CODE_BINDING')
    # The local consumer schema requires a 32-hex run ID, whereas the native
    # campaign owner has an R08_Q1_* run root. Bind the projection explicitly;
    # an arbitrary but syntactically valid 32-hex ID is not acceptable.
    native_run=result.get('run_id')
    req(isinstance(native_run,str) and re.fullmatch(r'R08_Q1_[0-9]{14}_[0-9a-f]{12}',native_run)
        and dossier.get('run_id')==hashlib.sha256(native_run.encode('ascii')).hexdigest()[:32],
        'PRE_B06_CONSUMER_RUN_BINDING')
    # The bundled validator is obtained from the same final code tree. This
    # function exists only in that package's gated source: no bypass flag.
    import importlib.util
    from pathlib import Path
    module_path=Path(__file__).with_name('PRE_B06_ENGINEERING_GATE.py')
    spec=importlib.util.spec_from_file_location('_g5_pre_b06_archive',str(module_path))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        checked=mod.verify_archive_dossier(dossier,final_members,members,code_sha)
    except (mod.NotProven,OSError,ValueError) as error:
        raise G5Incomplete('G5_FINAL_PRE_B06_NOT_PROVEN:'+str(error)) from error
    req(checked['consumers_verified']==11 and checked['five_part_completeness']=='NOT_EVALUATED',
        'PRE_B06_EVIDENCE_INVALID_SCOPE')
    req(result.get('pre_b06_11_evidence_class')=='ENGINEERING_READINESS_NOT_PRODUCTION',
        'PRE_B06_MISREPRESENTED_AS_OPERATIONAL')
    return record


def verify_native_isolated_boundary(proof, name, *, pre_b06=False):
    """Isolated technical transitions only; NEVER production authorization.

    For the V002 engineering contract, strong provenance is derived from
    separately pinned physical artifact refs in verify_native_campaign.
    """
    if pre_b06:
        req(proof.get('boundary_scope') == 'OWNED_ISOLATED_NTFS_PRE_B06'
            and proof.get('operational_authority') is False
            and proof.get('protected_effects') is False,
            'NATIVE_PRE_B06_BOUNDARY_SCOPE:' + name)
        req(proof.get('real_packaged_code_invoked') is True
            and proof.get('isolated_physical_readback') is True
            and proof.get('protected_inventory_unchanged') is True,
            'NATIVE_PRE_B06_BOUNDARY_PROOF:' + name)
    else:
        req(proof.get('boundary_scope') == 'NATIVE_FULL_INTEGRATED_REAL_EFFECTS',
            'NATIVE_BOUNDED_PROOF_NOT_FINAL_G5:' + name)


def verify_native_campaign(raw, code_sha, package_sha, runtime_index=None, *, final_members=None):
    members = native_zip_members(raw)
    req({'ENGINEERING_RESULT.json', 'LIVE_STATUS.json'} <= set(members), 'NATIVE_RESULT_MISSING')
    result, live = (strict(members[n]) for n in ('ENGINEERING_RESULT.json', 'LIVE_STATUS.json'))
    v002=result.get('schema')=='CDT19_PRE_B06_NATIVE_ENGINEERING_V002'
    req((result.get('status')=='PASS_NATIVE_INTEGRATED_PRE_B06' if v002 else
         result.get('schema')=='CDT18_ONE_SINGLE_FULL_ENGINEERING_QUAL_V001' and
         result.get('status')=='PASS_NATIVE_INTEGRATED_PRE_G5_DECISION'), 'NATIVE_G5_RUN_NOT_PASS')
    req(result.get('code_manifest_sha256') == code_sha and result.get('final_zip_sha256') == package_sha,
        'NATIVE_G5_SOURCE_BINDING')
    chain_role='PRE_B06_11_CHAIN' if v002 else 'LEGACY_11_CHAIN'
    if v002:
        record=verify_pre_b06_v002(members,result,code_sha,package_sha,runtime_index,final_members)
        verify_causal_projection(members,code_sha,package_sha)
    else:
        verify_legacy11(members, result, code_sha, package_sha, runtime_index)
        req(result.get('legacy_11_effectful_windows') == 'PASS_EFFECTFUL_INTEGRATED'
            and result.get('legacy_11_effectful_receipt_schema') == 'TICKSTORE_LEGACY_11_EFFECTFUL_INTEGRATION_V001',
            'NATIVE_LEGACY_11_SUMMARY_MISMATCH')
        record=result['legacy_11_effectful_receipt']
    req(result.get('native_proofs_are_sandbox_experiments') is False
        and result.get('synthetic_d4_stage_b_substitute') is False, 'NATIVE_SYNTHETIC_SUBSTITUTION')
    req(result.get('production_modified') is False and result.get('full_started') is False
        and result.get('blockers') == [] and result.get('b06') == 'NOT_STARTED'
        and result.get('g5_final') == 'NOT_ISSUED', 'NATIVE_PREMATURE_GATE_OR_EFFECT')
    required = {'SUITE_' + n for n in SUITES} | {'G5_' + n for n in PROOFS} | {chain_role}
    tests = result.get('tests')
    req(isinstance(tests, dict) and set(tests) == required, 'NATIVE_UNIT_SET')
    req(live.get('status') == result['status'] and type(live.get('committed_units')) is int
        and live['committed_units'] == len(required), 'NATIVE_TERMINAL_COMMITTED')
    roles = {chain_role: (record['member'],record['sha256'])}
    chain_unit = tests[chain_role]
    expected_status='PASS_PRE_B06_ENGINEERING' if v002 else 'PASS_EFFECTFUL_INTEGRATED'
    req(chain_unit.get('status') == expected_status and chain_unit.get('exit_code') == 0
        and chain_unit.get('receipt') == record, 'NATIVE_CHAIN_UNIT_NOT_COMMITTED')
    for name in SUITES:
        key = 'SUITE_' + name
        record = tests[key]
        req(record.get('status') == 'PASS_NATIVE_SCOPED' and record.get('exit_code') == 0
            and record.get('skipped') is False and type(record.get('test_count')) is int
            and record['test_count'] > 0, 'NATIVE_SUITE_NOT_PASS:' + name)
        logname = 'LOGS/' + record.get('log', '').replace('\\', '/').split('/')[-1]
        log = members.get(logname)
        req(log is not None and digest(log) == record.get('sha256'), 'NATIVE_SUITE_LOG:' + name)
        counts = re.findall(rb'(?m)^Ran (\d+) tests? in [^\r\n]+\r?$', log)
        req(len(counts) == 1 and int(counts[0]) == record['test_count']
            and re.search(rb'(?m)^OK\r?$', log) is not None
            and b'FAILED (' not in log and b'skipped=' not in log and b'expected failures=' not in log,
            'NATIVE_SUITE_RESULT:' + name)
        roles[key] = (logname, digest(log))
    for name in PROOFS:
        key = 'G5_' + name
        record = tests[key]
        req(record.get('status') == 'PASS_NATIVE_SCOPED' and record.get('exit_code') == 0, 'NATIVE_PROOF_EXIT:' + name)
        member = 'EVIDENCE/PROOFS/' + name + '/PROOF_RECEIPT.json'
        req(member in members, 'NATIVE_PROOF_MISSING:' + name)
        proof = strict(members[member])
        req(proof.get('schema') == 'TICKSTORE_G5_TARGET_PROOF_RECEIPT_V001'
            and proof.get('proof') == name and proof.get('native_windows') is True
            and proof.get('code_manifest_sha256') == code_sha and proof.get('final_zip_sha256') == package_sha
            and proof.get('status') == ('EMULATED_PASS' if name == 'POWERLOSS_EMULATED' else 'PASS')
            and proof.get('production_execution') is False and proof.get('gate_verdict_issued') is False
            and proof.get('error') is None, 'NATIVE_PROOF_CONTRACT:' + name)
        req(isinstance(proof.get('kind'), str) and 'SYNTHETIC' not in proof['kind'], 'NATIVE_PROOF_SYNTHETIC:' + name)
        if name in ('D4_REAL_ISOLATED_PATH_NATIVE', 'STAGE_B_REAL_ISOLATED_PATH_NATIVE'):
            # Real packaged code exercised on artificial qualification roots is
            # valid engineering evidence, but never FULL/operational provenance.
            # The pre-B06 isolated receipt explicitly advertises its limited scope.
            verify_native_isolated_boundary(proof, name, pre_b06=v002)
        checks = proof.get('checks')
        req(isinstance(checks, dict) and checks and all(v == 'PASS' for v in checks.values()), 'NATIVE_PROOF_CHECKS:' + name)
        artifacts = proof.get('artifacts')
        req(isinstance(artifacts, list) and artifacts, 'NATIVE_PROOF_ARTIFACTS_REQUIRED:' + name)
        seen = set()
        for ref in artifacts:
            _physical_ref(ref, members, 'NATIVE_PROOF_ARTIFACT')
            req(ref['member'] != member and ref['member'] not in seen, 'NATIVE_PROOF_DUPLICATE_OR_SELF_REFERENCE')
            seen.add(ref['member'])
        if name == 'POWERLOSS_EMULATED':
            req(proof.get('counts_as') == 'NOT_CHECKPOINT_POWERLOSS_RECOVERY', 'NATIVE_PHYSICAL_POWERLOSS_FALSE_CLAIM')
        roles[key] = (member, digest(members[member]))
    return result, roles, members


def verify_causal_projection(members, code_sha, package_sha):
    """Read all native causal bytes; a rehashed summary alone cannot close G3/G6."""
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'g5proof/PRE_G06_PROOF_PROJECTION.py'
    spec=importlib.util.spec_from_file_location('_g5_causal_projection',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    summary_name='WORK/G3_G6_NATIVE/G3_G6_NATIVE_SCENARIOS.json'
    req(summary_name in members,'NATIVE_CAUSAL_SUMMARY_MISSING')
    summary=strict(members[summary_name])
    try:module.validate(summary)
    except (RuntimeError,KeyError,TypeError,ValueError) as exc:
        raise G5Incomplete('NATIVE_CAUSAL_INVALID:'+str(exc)) from exc
    expected={n for n in members if n.startswith('WORK/G3_G6_NATIVE/')}
    for name in ('PROCESS_TREE_CRASH_CONTAINMENT','SAFE_STOP_RESUME_ROW_GROUP','POWERLOSS_EMULATED'):
        member='EVIDENCE/PROOFS/'+name+'/NATIVE_CAUSAL_EVIDENCE.json'
        req(member in members,'NATIVE_CAUSAL_PROJECTION_MISSING:'+name)
        obj=strict(members[member])
        req(obj.get('schema')=='CDT19_SCOPED_NATIVE_PROOF_PROJECTION_V002'
            and obj.get('proof')==name and obj.get('summary')==summary
            and obj.get('code_manifest_sha256')==code_sha
            and obj.get('final_zip_sha256')==package_sha
            and obj.get('operational_authority') is False,'NATIVE_CAUSAL_BINDING')
        refs=obj.get('physical_files')
        req(isinstance(refs,list) and len(refs)==len(expected)
            and {r.get('member') for r in refs}==expected,'NATIVE_CAUSAL_PHYSICAL_SET')
        for ref in refs:_physical_ref(ref,members,'NATIVE_CAUSAL_ARTIFACT')
    return summary


PROOFS=('PROCESS_TREE_CRASH_CONTAINMENT','SAFE_STOP_RESUME_ROW_GROUP',
        'D4_REAL_ISOLATED_PATH_NATIVE','STAGE_B_REAL_ISOLATED_PATH_NATIVE','PS51_INSTALL_MENU','POWERLOSS_EMULATED')
SUITES=('test_cdt17_final_g5_complete_proof_gate.py','test_cdt18_stage_proof_integrated_reconcile.py','test_b2d_origin_decision_binder.py',
        'test_operator_entry_points.py','test_state_cas_recovery.py','test_native_process_control_r41.py',
        'test_full_runner_observability_r41.py','test_official_writer_effectful.py','test_menu_tx_interprocess.py',
        'test_stageb_full_physical_closure.py','test_stage_canary_physical_publication.py',
        'test_full_postverify_readback.py','test_canary_receipt_readback.py','test_scratch_powerloss_debris.py',
        'test_cdt16_held_rename_failure.py','test_cdt16_delete_share_denial.py','test_cdt16_native_pin_contract.py',
        'test_g5_proof_runner_contract.py','test_installer_legacy_activation_prune.py',
        'test_official_target_readonly_admission.py','adapter_tests.py','test_full_multiwork.py',
        'test_full_serial_r9.py','test_publisher_recovery_v004.py')
