import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import tickstore_publisher_recovery_v004 as r


def make_fixture():
    inventory={}
    observed=[]
    days={}
    months={"M":{}}
    for i in range(1399):
        key=f"{20000000+i:08d}"
        namespace=r.NAMESPACES[0]
        contract={"date_key":key,"month_id":"M","proof":"nested-invs0-regression"}
        entry={"namespace":namespace,"contract":contract}
        for kind,suffix in (("journal","journal.json"),("partial","pts2g.partial")):
            path=f"{namespace}/fixture/{key}/{key}.{suffix}"
            obj={
                "date_key":key,
                "kind":kind,
                "namespace":namespace,
                "path":path,
                "sha256":r.sha((key+kind).encode()),
                "bytes":32,
                "reparse":False,
                "links":1,
            }
            if kind=="journal":
                obj["contract"]=contract
            entry[kind]={field:obj[field] for field in ("path","sha256","bytes")}
            observed.append(obj)
        inventory[key]=entry
        days[key]=contract
    return inventory,observed,days,months


class S0CertPathAssociationMicrofix(unittest.TestCase):
    def test_nested_invs0_shape_passes_and_path_drift_still_blocks(self):
        inventory,observed,days,months=make_fixture()
        source_sha="A"*64
        generation={"snapshot_id":"fixture-snapshot"}

        with patch.object(r,"scan_s0",return_value=copy.deepcopy(observed)), \
             patch.object(r,"prep",return_value={}):
            result=r.certify_scratch(
                object(),Path("fixture-shadow"),copy.deepcopy(inventory),
                days,months,object(),generation,source_sha
            )

        self.assertEqual(result["schema"],"SCRATCH_ADMISSION_CERT_V004")
        self.assertEqual(result["result"],"PASS_1399_1399")
        self.assertEqual(len(result["days"]),1399)

        bad=copy.deepcopy(inventory)
        first=sorted(bad)[0]
        bad[first]["journal"]["path"]="BROKEN/JOURNAL/PATH"
        with patch.object(r,"scan_s0",return_value=copy.deepcopy(observed)), \
             patch.object(r,"prep",return_value={}):
            with self.assertRaisesRegex(r.Blocked,"S0_CERT_PATH_ASSOCIATION"):
                r.certify_scratch(
                    object(),Path("fixture-shadow"),bad,
                    days,months,object(),generation,source_sha
                )

        bad_partial=copy.deepcopy(inventory)
        bad_partial[first]["partial"]["path"]="BROKEN/PARTIAL/PATH"
        with patch.object(r,"scan_s0",return_value=copy.deepcopy(observed)), \
             patch.object(r,"prep",return_value={}):
            with self.assertRaisesRegex(r.Blocked,"S0_CERT_PATH_ASSOCIATION"):
                r.certify_scratch(
                    object(),Path("fixture-shadow"),bad_partial,
                    days,months,object(),generation,source_sha
                )


if __name__=="__main__":
    unittest.main(verbosity=2)
