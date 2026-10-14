"""R44D (R44-DROOT-01) delta bundle: audit driver + admission module only; R44 FINAL untouched."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'source'
REV, DATE = 'R44D', '20261014'
QUAL_NAME = 'TICKSTORE_CDT15_%s_DROOT_%s.zip' % (REV, DATE)
BOOTSTRAP = 'RUN_TICKSTORE_CDT15_%s_DROOT.ps1' % REV
WITNESS = 'WITNESS_TICKSTORE_CDT15_%s_DROOT_%s.json' % (REV, DATE)
FIXED = (2026, 10, 14, 0, 0, 0)
R44_FINAL_SHA = '0FBB6C36B840F2EF228DB3B160AA50D733FE5293C80BB4060AFFD4C074F8A48D'


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def canon(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    members = [(n, (SOURCE / n).read_bytes()) for n in ('qual/R44D_DROOT_AUDIT.py', 'qual/SANDBOX_ADMISSION.py')]
    qman = canon({'schema': 'TICKSTORE_CDT15_R41_QUAL_BUNDLE_MANIFEST_V001',
                  'files': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n, b in members]})
    zpath = out / QUAL_NAME
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, b in [('QUAL_MANIFEST.json', qman)] + members:
            i = zipfile.ZipInfo(n, FIXED); i.compress_type = zipfile.ZIP_DEFLATED; i.external_attr = 0o100644 << 16
            z.writestr(i, b)
    zraw = zpath.read_bytes()
    tpl = (HERE / 'RUN_TICKSTORE_CDT15_QUAL.ps1.template').read_text(encoding='ascii')
    ps = (tpl.replace('@@ZIP_NAME@@', QUAL_NAME).replace('@@ZIP_SHA@@', sha(zraw)).replace('@@ZIP_BYTES@@', str(len(zraw)))
          .replace('@@QUAL_MANIFEST_SHA@@', sha(qman)).replace('@@REV@@', REV).replace('@@BOOTSTRAP@@', BOOTSTRAP)
          .replace('@@DRIVER@@', 'qual\\R44D_DROOT_AUDIT.py').replace('@@ZIP_PATTERN@@', 'TICKSTORE_CDT15_%s_DROOT_*.zip' % REV))
    assert '@@' not in ps
    praw = ps.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii')
    (out / BOOTSTRAP).write_bytes(praw)
    w = canon({'schema': 'EXTERNAL_WITNESS_TICKSTORE_CDT15_QUAL_V002', 'revision': REV, 'role': 'ENGINEER_ONLY',
               'purpose': 'R44-DROOT-01 delta: read-only audit of R44 sandbox topology + native negative admission probes',
               'qual_zip': QUAL_NAME, 'qual_zip_sha256': sha(zraw), 'qual_zip_bytes': len(zraw),
               'qual_manifest_sha256': sha(qman), 'bootstrap': BOOTSTRAP, 'bootstrap_sha256': sha(praw),
               'bootstrap_bytes': len(praw), 'audited_r44_final_sha256': R44_FINAL_SHA, 'r44_126_rerun': False,
               'final_bytes_touched': False, 'elevation_required': True,
               'invocation': 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                             '"C:\\Users\\silvi\\OneDrive\\Downloads\\' + BOOTSTRAP + '"',
               'production_modified': False, 'full_started': False, 'gate_verdict_issued': False})
    (out / WITNESS).write_bytes(w)
    for n in (QUAL_NAME, BOOTSTRAP, WITNESS):
        print(sha((out / n).read_bytes()), n, (out / n).stat().st_size)


if __name__ == '__main__':
    main(sys.argv[1])
