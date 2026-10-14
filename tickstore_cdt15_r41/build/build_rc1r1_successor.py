"""RC1R1 recertification: deterministic V002R23 successor package and the D4 identity cascade.

Usage: python3 -I -B build_rc1r1_successor.py <repo_root>

Source-only and idempotent. Reads the recertified core, checks that both engines embed it, then
regenerates, in dependency order:
  CODE_MANIFEST -> STAGE_A config -> 99_MANIFEST -> successor ZIP (stored, fixed metadata) ->
  code-delta review pack -> adapter binding -> D4 PREP/BOOTSTRAP/wrapper pins -> FIRST_ADMISSION_BINDING.
The historical V002R22 identities are read from history/RC1_V002R22 and never rewritten.
"""
import base64
import difflib
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SUCCESSOR_ZIP = 'TICKSTORE_V004R1_D4_RESUMABLE_V002R23_PACKAGE.zip'
REVIEW_PACK = 'TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R23.zip'
OLD = {'core': 'D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0',
       'release': 'BFC44DA9A375ED565D8DA2DA7E34EC376C25DEAFE15ED2F3C063CE635CEBCD4C',
       'candidate': 'E998032478EA1FAB8BD69FF000D9622749B679058F457A927D5854963208E310',
       'postfull': 'B5E753C3A0727B01B8DE65B44374F432D6F5B8AE1C52C02449CA50BFC558B7F0',
       'config': 'B67527C0E78E896BF4F4128BF02CC3968CA1AE00F2A8449DB7DBD1E583785515',
       'code_manifest': '60FE88C92BDBD95884DF3258C739855AF870F4A4D58B40301BF8E5E1786C579D',
       'package_manifest': '5199C7B03A442F0D33C1250E3E2A68A5A213377E012A902336502453CAAA18D6',
       'package_zip': '4BC28843012A059F65237E07780B79D158190A661B16FFD520861A3F092C3062'}
SCHEMA_99 = 'TICKSTORE_V004R1_ORCHESTRATOR_V002R23_RC1R1_RECERTIFICATION_SUCCESSOR_MANIFEST_20261014'


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def compact(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def stored_zip(path, members):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED; info.create_system = 0; info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert {n: z.read(n) for n in z.namelist()} == members
    return sha(path.read_bytes())


def replace_once(path, pattern, repl):
    raw = path.read_bytes()
    new, n = re.subn(pattern.encode(), repl.encode(), raw, flags=re.M)
    assert n == 1, (path.name, pattern)
    path.write_bytes(new)


def main(repo):
    repo = Path(repo); cand = repo / 'source/candidate'; rec = cand / 'recovery'; hist = repo / 'history/RC1_V002R22'
    for rel, key in (('full/tickstore_serial_runner.py', 'core'), ('recovery/engine/tickstore_publisher_recovery_v004_release.py', 'release'),
                     ('recovery/engine/tickstore_publisher_recovery_v004_candidate.py', 'candidate'),
                     ('recovery/modules/postfull_verifier.py', 'postfull'), ('recovery/config/STAGE_A_SEALED_VALUES_V001.json', 'config'),
                     ('recovery/CODE_MANIFEST.json', 'code_manifest'), ('recovery/99_MANIFEST_SHA256.json', 'package_manifest')):
        assert sha((hist / rel).read_bytes()) == OLD[key], 'HISTORY_' + key

    core = (cand / 'full/tickstore_serial_runner.py').read_bytes(); core_sha = sha(core)
    assert core_sha != OLD['core']
    for name in ('release', 'candidate'):
        text = (rec / ('engine/tickstore_publisher_recovery_v004_%s.py' % name)).read_text(encoding='utf-8')
        assert 'CORE_SHA = "%s"' % core_sha in text, 'ENGINE_CORE_SHA_' + name
        b64 = re.search(r'^CORE_B64 = "([A-Za-z0-9+/=]+)"$', text, re.M).group(1)
        assert base64.b64decode(b64) == core, 'ENGINE_CORE_B64_' + name
        assert 'RC1_HISTORICAL_CORE_SHA = "%s"' % OLD['core'] in text
    assert 'CORE_SHA="%s"' % core_sha in (rec / 'modules/postfull_verifier.py').read_text(encoding='utf-8')

    # Preserved parent manifest inside the successor (different SHA, so the wrapper cardinality check holds).
    keep = rec / 'history/V002R22/99_MANIFEST_SHA256.json'; keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_bytes((hist / 'recovery/99_MANIFEST_SHA256.json').read_bytes())

    cm_path = rec / 'CODE_MANIFEST.json'; cm = json.loads((hist / 'recovery/CODE_MANIFEST.json').read_bytes())
    for row in cm['files']:
        raw = (rec / row['path']).read_bytes(); row['sha256'] = sha(raw); row['bytes'] = len(raw)
    cm_raw = compact(cm); cm_path.write_bytes(cm_raw)

    cfg_path = rec / 'config/STAGE_A_SEALED_VALUES_V001.json'; cfg = json.loads((hist / 'recovery/config/STAGE_A_SEALED_VALUES_V001.json').read_bytes())
    release = (rec / 'engine/tickstore_publisher_recovery_v004_release.py').read_bytes()
    candidate = (rec / 'engine/tickstore_publisher_recovery_v004_candidate.py').read_bytes()
    postfull = (rec / 'modules/postfull_verifier.py').read_bytes()
    changes = {'core_sha256': core_sha, 'delta_release_source_sha256': sha(release), 'delta_candidate_source_sha256': sha(candidate),
               'postfull_verifier_sha256': sha(postfull), 'code_manifest_sha256': sha(cm_raw)}
    for k, v in changes.items():
        assert k in cfg; cfg[k] = v
    cfg_raw = compact(cfg); cfg_path.write_bytes(cfg_raw)

    pm_path = rec / '99_MANIFEST_SHA256.json'; old_pm = json.loads((hist / 'recovery/99_MANIFEST_SHA256.json').read_bytes())
    files = sorted((p for p in rec.rglob('*') if p.is_file() and p != pm_path and '__pycache__' not in p.parts),
                   key=lambda p: p.relative_to(rec).as_posix())
    present = {p.relative_to(rec).as_posix() for p in files}
    pm = {k: old_pm[k] for k in ('base_head_sha256', 'base_master_sha256')}
    pm.update({'schema': SCHEMA_99, 'd4_rerun_authorized': False, 'd5_authorized': False, 'full_authorized': False,
               'promotion_effect': False, 'parent_manifest_sha256': OLD['package_manifest'], 'parent_package_sha256': OLD['package_zip'],
               'superseded_manifest_path': 'history/V002R22/99_MANIFEST_SHA256.json',
               'not_carried_from_parent': sorted(r['path'] for r in old_pm['files'] if r['path'] not in present),
               'files': [{'bytes': p.stat().st_size, 'path': p.relative_to(rec).as_posix(), 'sha256': sha(p.read_bytes())} for p in files]})
    pm_raw = compact(pm); pm_path.write_bytes(pm_raw)

    dist = repo / 'dist'; dist.mkdir(exist_ok=True)
    members = {p.relative_to(rec).as_posix(): p.read_bytes() for p in files}; members['99_MANIFEST_SHA256.json'] = pm_raw
    zip_sha = stored_zip(dist / SUCCESSOR_ZIP, members)

    def diff(a, b, la, lb):
        return ''.join(difflib.unified_diff(a.decode().splitlines(True), b.decode().splitlines(True), la, lb)).encode()
    old_rel = (hist / 'recovery/engine/tickstore_publisher_recovery_v004_release.py').read_bytes()
    old_cand = (hist / 'recovery/engine/tickstore_publisher_recovery_v004_candidate.py').read_bytes()
    # The embedded CORE_B64 line is replaced by its identity in the engine diffs; the core diff is shown in full.
    strip = lambda raw: re.sub(rb'^CORE_B64 = "[A-Za-z0-9+/=]+"$', lambda m: b'CORE_B64 = "<sha256 ' + sha(base64.b64decode(m.group(0)[12:-1])).encode() + b'>"', raw, flags=re.M)
    review = {
        'V002R23_RC1R1_CORE_RECERTIFICATION_SUPERSESSION.md': (rec / 'docs/V002R23_RC1R1_CORE_RECERTIFICATION_SUPERSESSION.md').read_bytes(),
        'CORE_RC1_TO_RC1R1.diff': diff((hist / 'full/tickstore_serial_runner.py').read_bytes(), core, 'RC1/tickstore_serial_runner.py', 'RC1R1/tickstore_serial_runner.py'),
        'ENGINE_RELEASE_V002R22_TO_V002R23.diff': diff(strip(old_rel), strip(release), 'V002R22/engine/release.py', 'V002R23/engine/release.py'),
        'ENGINE_CANDIDATE_V002R22_TO_V002R23.diff': diff(strip(old_cand), strip(candidate), 'V002R22/engine/candidate.py', 'V002R23/engine/candidate.py'),
        'POSTFULL_VERIFIER_V002R22_TO_V002R23.diff': diff((hist / 'recovery/modules/postfull_verifier.py').read_bytes(), postfull, 'V002R22/postfull_verifier.py', 'V002R23/postfull_verifier.py'),
        'CONFIG_DELTA.json': (json.dumps({k: {'V002R22': json.loads((hist / 'recovery/config/STAGE_A_SEALED_VALUES_V001.json').read_bytes())[k], 'V002R23': v}
                                          for k, v in changes.items()}, indent=1, sort_keys=True) + '\n').encode(),
        'V002R23/99_MANIFEST_SHA256.json': pm_raw, 'V002R23/CODE_MANIFEST.json': cm_raw,
        'V002R23/config/STAGE_A_SEALED_VALUES_V001.json': cfg_raw,
        'IDENTITIES.json': (json.dumps({'schema': 'TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_PACK_V002R23', 'base_release_sha256': OLD['release'],
                                        'successor_release_sha256': sha(release), 'successor_candidate_sha256': sha(candidate),
                                        'core_rc1r1_sha256': core_sha, 'core_rc1_historical_sha256': OLD['core'],
                                        'postfull_verifier_sha256': sha(postfull), 'config_sha256': sha(cfg_raw),
                                        'code_manifest_sha256': sha(cm_raw), 'package_manifest_sha256': sha(pm_raw),
                                        'package_zip_sha256': zip_sha, 'verdict_schema_header': 'TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R22'},
                                       indent=1, sort_keys=True) + '\n').encode()}
    review_sha = stored_zip(dist / REVIEW_PACK, review)

    ad_path = cand / 'adapter/RUNTIME_LOCATOR_ADAPTER_BINDING.json'; ad = json.loads(ad_path.read_bytes())
    ad['frozen_release_sha256'] = sha(release)
    ad_raw = (json.dumps(ad, indent=2, sort_keys=True) + '\n').encode(); ad_path.write_bytes(ad_raw)

    ctl = cand / 'control'
    replace_once(ctl / 'D4_FIRST_ADMISSION_PREP.py', r"^RELEASE_SHA = '[0-9A-F]{64}'$", "RELEASE_SHA = '%s'" % sha(release))
    replace_once(ctl / 'D4_FIRST_ADMISSION_PREP.py', r"^CONFIG_SHA = '[0-9A-F]{64}'$", "CONFIG_SHA = '%s'" % sha(cfg_raw))
    boot = ctl / 'D4_FIRST_ADMISSION_BOOTSTRAP.py'
    replace_once(boot, r"^RELEASE_SHA='[0-9A-F]{64}'$", "RELEASE_SHA='%s'" % sha(release))
    for name, digest in (('engine/tickstore_publisher_recovery_v004_candidate.py', sha(candidate)), ('CODE_MANIFEST.json', sha(cm_raw)),
                         ('99_MANIFEST_SHA256.json', sha(pm_raw))):
        replace_once(boot, r"'%s':'[0-9A-F]{64}'" % re.escape(name), "'%s':'%s'" % (name, digest))
    replace_once(boot, r"reads\.read\(a\.package_zip,'[0-9A-F]{64}'\)", "reads.read(a.package_zip,'%s')" % zip_sha)
    wrapper = ctl / '60_EFFECTFUL_WRAPPER_RELEASE.ps1'
    for var, value in (('ExpectedReleaseSha', sha(release)), ('ExpectedCandidateSha', sha(candidate)), ('ExpectedConfigSha', sha(cfg_raw)),
                       ('ExpectedCodeManifestSha', sha(cm_raw)), ('ExpectedPackageManifestSha', sha(pm_raw)), ('ExpectedPackageZipSha', zip_sha)):
        replace_once(wrapper, r"^\$%s = '[0-9A-F]{64}'\r$" % var, "$%s = '%s'\r" % (var, value))
    replace_once(wrapper, r"'TICKSTORE_V004R1_D4_RESUMABLE_V002R2[23]_PACKAGE\.zip'", "'%s'" % SUCCESSOR_ZIP)
    replace_once(wrapper, r"'TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R2[23]\.zip'", "'%s'" % REVIEW_PACK)

    mig = ctl / 'RC1R1_SUCCESSOR_MIGRATION.py'
    replace_once(mig, r"^SUCCESSOR_ZIP_SHA256 = '[0-9A-F]{64}'$", "SUCCESSOR_ZIP_SHA256 = '%s'" % zip_sha)
    replace_once(mig, r"^REVIEW_PACK_SHA256 = '[0-9A-F]{64}'$", "REVIEW_PACK_SHA256 = '%s'" % review_sha)

    fb_path = ctl / 'FIRST_ADMISSION_BINDING.json'; fb = json.loads(fb_path.read_bytes())
    for key, rel in (('preparation_sha256', 'D4_FIRST_ADMISSION_PREP.py'), ('wrapper_sha256', '60_EFFECTFUL_WRAPPER_RELEASE.ps1'),
                     ('transaction_sha256', 'D4_FIRST_ADMISSION_TRANSACTION.py'), ('bootstrap_sha256', 'D4_FIRST_ADMISSION_BOOTSTRAP.py'),
                     ('predecessor_reconciliation_sha256', 'D4_PREDECESSOR_RECONCILIATION.py'),
                     ('policy_capture_binding_sha256', 'POLICY_CAPTURE_BINDING.py')):
        fb[key] = sha((ctl / rel).read_bytes())
    fb['adapter_sha256'] = sha((cand / 'adapter/runtime_locator_adapter.py').read_bytes())
    fb['runtime_binding_sha256'] = sha(ad_raw)
    fb_raw = (json.dumps(fb, indent=2) + '\n').encode(); fb_path.write_bytes(fb_raw)

    out = {'schema': 'TICKSTORE_V002R23_RC1R1_SUCCESSOR_IDENTITIES_V001', 'core_rc1r1_sha256': core_sha,
           'core_rc1_historical_sha256': OLD['core'], 'successor_release_sha256': sha(release),
           'successor_candidate_sha256': sha(candidate), 'postfull_verifier_sha256': sha(postfull), 'config_sha256': sha(cfg_raw),
           'code_manifest_sha256': sha(cm_raw), 'package_manifest_sha256': sha(pm_raw), 'package_zip': SUCCESSOR_ZIP,
           'package_zip_sha256': zip_sha, 'package_zip_bytes': (dist / SUCCESSOR_ZIP).stat().st_size, 'review_pack': REVIEW_PACK,
           'review_pack_sha256': review_sha, 'adapter_binding_sha256': sha(ad_raw), 'first_admission_binding_sha256': sha(fb_raw),
           'wrapper_sha256': fb['wrapper_sha256'], 'preparation_sha256': fb['preparation_sha256'], 'bootstrap_sha256': fb['bootstrap_sha256'],
           'not_carried_from_parent': len(pm['not_carried_from_parent']), 'parent': {k: OLD[k] for k in ('release', 'candidate', 'postfull', 'config', 'code_manifest', 'package_manifest', 'package_zip')}}
    (dist / 'V002R23_RC1R1_SUCCESSOR_IDENTITIES.json').write_bytes((json.dumps(out, indent=1, sort_keys=True) + '\n').encode())
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == '__main__':
    main(sys.argv[1])
