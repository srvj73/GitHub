"""Recompute candidate_overlay/control/FIRST_ADMISSION_BINDING.json from the merged B2C bytes (deterministic)."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OV = HERE / 'candidate_overlay/control'
SRC = HERE.parent / 'source/candidate/control'


def sha(name):
    p = OV / name if (OV / name).is_file() else SRC / name
    return hashlib.sha256(p.read_bytes()).hexdigest().upper()


b = json.loads((SRC / 'FIRST_ADMISSION_BINDING.json').read_bytes())
b.update(preparation_sha256=sha('D4_FIRST_ADMISSION_PREP.py'), wrapper_sha256=sha('60_EFFECTFUL_WRAPPER_RELEASE.ps1'),
         transaction_sha256=sha('D4_FIRST_ADMISSION_TRANSACTION.py'), bootstrap_sha256=sha('D4_FIRST_ADMISSION_BOOTSTRAP.py'),
         predecessor_reconciliation_sha256=sha('D4_PREDECESSOR_RECONCILIATION.py'),
         policy_capture_binding_sha256=sha('POLICY_CAPTURE_BINDING.py'),
         policy_binding='R44_B2C_CURRENT_CAPTURE_PLUS_ORIGIN_RECONCILIATION_NO_REVISION_LITERAL')
(OV / 'FIRST_ADMISSION_BINDING.json').write_text(json.dumps(b, indent=2) + '\n', encoding='utf-8')
print(json.dumps(b, indent=1))
