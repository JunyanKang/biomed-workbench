import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "tmb-vcf-live-verification.json"
VCF = ROOT / "tests" / "fixtures" / "variants" / "region-query.vcf"
BED = ROOT / "tests" / "fixtures" / "variants" / "callable-targets.bed"
IMPLEMENTATION = ROOT / "biomed_workbench" / "implementations" / "tmb_vcf.py"


class TMBVCFEvidenceTests(unittest.TestCase):
    def test_live_report_binds_serial_filter_ann_bed_union_and_tmb_arithmetic(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("tumor-mutation-burden-vcf")
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["fixture"]["vcf_sha256"], hashlib.sha256(VCF.read_bytes()).hexdigest())
        self.assertEqual(report["fixture"]["bed_sha256"], hashlib.sha256(BED.read_bytes()).hexdigest())
        self.assertEqual(report["implementation"]["sha256"], hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest())
        self.assertEqual(report["serial_execution"]["plan"], ["variant-filter-vcf", "tumor-mutation-burden-vcf"])
        self.assertEqual(report["scientific_summary"]["category_counts"], {"missense": 2})
        self.assertEqual(report["scientific_summary"]["gene_counts"], {"GENE1": 1, "GENE3": 1})
        self.assertAlmostEqual(report["scientific_summary"]["tmb_mutations_per_mb"], 4 / 3)
        self.assertTrue(report["scientific_summary"]["classification_policy"].startswith("none"))

    def test_public_evidence_has_no_machine_path_credential_or_clinical_label(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "ACCESS_TOKEN=", '"classification": "High"'):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
