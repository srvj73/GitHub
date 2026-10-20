"""Build the sealed CDT20 PRE-G06 integrated successor (inner package + bindings).

Parent inner package: CDT20_PRE_G06_INTEGRATED_SOURCE_20261020.zip (6C952BD9..., native PASS 38 commits).
Only changed/new members are replaced; every other member keeps its bytes and ZipInfo.
"""
import difflib,hashlib,json,sys,zipfile,ast
from pathlib import Path
parent_zip,src,outer_src,dest=map(Path,sys.argv[1:5])
PARENT_SHA='6C952BD9D0C0B7E13D7B5AD01E1563DA8AFC2FB641262835A0AABBC49778C064'
NAME='CDT20_PRE_G06_INTEGRATED_SOURCE_V002_20261020.zip'
CORE='implementation_v001/candidate/full/tickstore_serial_runner.py'
CORE_SHA='749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00'
def sha(b):return hashlib.sha256(b).hexdigest().upper()
def enc(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode()
assert sha(parent_zip.read_bytes())==PARENT_SHA
with zipfile.ZipFile(parent_zip) as z:
    infos=z.infolist();original={i.filename:z.read(i) for i in infos}
members=dict(original)
manifests=('PACKAGE_MANIFEST.json','implementation_v001/SOURCE_MANIFEST.json','implementation_v001/RUNTIME_CODE_MANIFEST.json')
on_disk={p.relative_to(src).as_posix():p.read_bytes() for p in src.rglob('*') if p.is_file()}
changed=sorted(n for n in on_disk if n not in manifests and n in original and on_disk[n]!=original[n])
added=sorted(n for n in on_disk if n not in original)
missing=sorted(n for n in original if n not in on_disk)
assert not missing,missing
for n in changed+added:
    if n.endswith('.py'):ast.parse(on_disk[n])
    members[n]=on_disk[n]
assert sha(members[CORE])==CORE_SHA
def rows(prefix):
    return [{'path':n[len(prefix):],'sha256':sha(members[n]),'bytes':len(members[n])}
            for n in sorted(members) if n.startswith(prefix) and n not in manifests]
rt=json.loads(original['implementation_v001/RUNTIME_CODE_MANIFEST.json'])
rt['files']=rows('implementation_v001/candidate/')
members['implementation_v001/RUNTIME_CODE_MANIFEST.json']=enc(rt)
sm=json.loads(original['implementation_v001/SOURCE_MANIFEST.json'])
sm['files']=[r for r in rows('implementation_v001/')];sm['file_count']=len(sm['files'])
members['implementation_v001/SOURCE_MANIFEST.json']=enc(sm)
pm=json.loads(original['PACKAGE_MANIFEST.json'])
pm['files']=[{'path':n,'sha256':sha(members[n]),'bytes':len(members[n])} for n in sorted(members) if n!='PACKAGE_MANIFEST.json']
members['PACKAGE_MANIFEST.json']=enc(pm)
dest.mkdir(parents=True,exist_ok=True)
package=dest/NAME
template={i.filename:i for i in infos}
with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as out:
    for n in sorted(members):
        info=template.get(n)
        if info is None:
            info=zipfile.ZipInfo(n,date_time=(2026,10,20,12,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3;info.external_attr=template['implementation_v001/tests/test_state_cas_recovery.py'].external_attr
        out.writestr(info,members[n])
with zipfile.ZipFile(package) as z:
    assert z.testzip() is None and sorted(z.namelist())==sorted(members)
    for n in members:assert z.read(n)==members[n]
pack=sha(package.read_bytes());code=sha(members['implementation_v001/RUNTIME_CODE_MANIFEST.json'])
witness={'schema':'CDT19_R08Q1_ENGINEERING_WITNESS_V001','production_authorized':False,'package_name':NAME,
         'package_sha256':pack,'manifest_sha256':sha(members['PACKAGE_MANIFEST.json']),'code_manifest_sha256':code,
         'source_origin_sha256':PARENT_SHA,'correction':'CDT20_V002_G5_OWNER_BASIS_ANY_VALID_DECLARATION_DATE_OWNER_AUTHORIZED_20261020','b06':'NOT_STARTED'}
(dest/'CDT20_R08Q1_WITNESS.json').write_bytes(enc(witness))
delta=[{'path':n,'before_sha256':sha(original[n]) if n in original else None,'after_sha256':sha(members[n]),
        'before_bytes':len(original[n]) if n in original else 0,'after_bytes':len(members[n])} for n in changed+added]
patch=[]
for n in changed+added:
    old=original.get(n,b'').decode('utf8').splitlines(True);new=members[n].decode('utf8').splitlines(True)
    patch+=difflib.unified_diff(old,new,fromfile='parent/'+n,tofile='successor/'+n)
(dest/'INTEGRATED_DELTA_INNER.patch').write_text(''.join(patch),encoding='utf8')
for n in manifests:(dest/Path(n).name).write_bytes(members[n])
(dest/'BUILD_SUMMARY.json').write_bytes(enc({'package_name':NAME,'package_sha256':pack,'code_manifest_sha256':code,
    'parent_package_sha256':PARENT_SHA,'changed':changed,'added':added,'members':len(members),'core_frozen_sha256':CORE_SHA,'delta':delta}))
print(json.dumps({'package_sha256':pack,'code_manifest_sha256':code,'changed':changed,'added':added,'members':len(members)},indent=1))
