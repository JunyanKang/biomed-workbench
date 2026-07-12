import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "vcf-region-query-live-verification.json"
VCF = ROOT / "tests" / "fixtures" / "variants" / "region-query.vcf.gz"
TBI = ROOT / "tests" / "fixtures" / "variants" / "region-query.vcf.gz.tbi"


class VCFRegionQueryEvidenceTests(unittest.TestCase):
    def test_live_report_binds_module_versions_fixture_index_and_scientific_result(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("variant-region-query-tabix")
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["tool_versions"], {"tabix": "1.23"})
        self.assertEqual(report["dependency_versions"], {"htslib": "1.23"})
        self.assertEqual(report["fixture"]["vcf_sha256"], hashlib.sha256(VCF.read_bytes()).hexdigest())
        self.assertEqual(report["fixture"]["index_sha256"], hashlib.sha256(TBI.read_bytes()).hexdigest())
        self.assertTrue(all(report["bundle_integrity"].values()))
        self.assertEqual(report["scientific_summary"]["record_count"], 2)
        self.assertEqual(report["scientific_summary"]["samples"], ["SAMPLE_A"])

    def test_public_evidence_has_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "nvapi-"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
