import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/public-case-uniprot-cytochrome-c-phylogeny.json"


class PublicUniProtCytochromeCPhylogenyCaseTests(unittest.TestCase):
    def test_public_case_preserves_real_records_and_method_boundary(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], "comparative-sequence-phylogeny")
        self.assertEqual(report["module_version"], "0.1.0")
        self.assertEqual(len(report["source_records"]), 4)
        self.assertEqual(report["analysis"]["alignment"]["record_count"], 4)
        self.assertEqual(report["analysis"]["tree"]["tip_count"], 4)
        self.assertEqual(report["analysis"]["tree"]["outgroups_present"], ["yeast_cyc1"])
        self.assertEqual(report["analysis"]["parameters"]["support_replicates"], 1000)
        self.assertTrue(any("not orthology" in item for item in report["scientific_boundary"]))


if __name__ == "__main__":
    unittest.main()
