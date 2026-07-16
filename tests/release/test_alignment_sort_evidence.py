import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "alignment-sort-live-verification.json"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "alignment-sort-index-samtools" / "module.json"


class AlignmentSortEvidenceTests(unittest.TestCase):
    def test_live_report_binds_actual_versions_policy_and_tested_baseline(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertTrue(all(report["tested_version_baseline"]["tools"].values()))
        self.assertTrue(all(report["tested_version_baseline"]["dependencies"].values()))
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertTrue(all(version_is_allowed(report["dependency_versions"][name], rules) for name, rules in row.dependency_versions.items()))

    def test_sorted_bam_csi_and_read_accounting_are_reconciled(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertTrue(all(report["bundle_integrity"].values()))
        self.assertEqual(report["output_manifest"]["format"], "bam@1.6")
        self.assertEqual(report["output_manifest"]["index_type"], "csi")
        self.assertEqual(report["output_manifest"]["sort_order"], "coordinate")
        self.assertEqual(report["scientific_summary"]["counts"]["total"], 3)
        self.assertEqual(report["scientific_summary"]["counts"]["mapped"], 2)

    def test_report_contains_no_machine_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
