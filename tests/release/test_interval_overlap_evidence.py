import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "interval-overlap-live-verification.json"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "interval-overlap-bedtools" / "module.json"


class IntervalOverlapEvidenceTests(unittest.TestCase):
    def test_live_report_binds_exact_bedtools_row_and_bed_contract(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["tool_versions"], {"bedtools": "2.31.1"})
        self.assertEqual(report["dependency_versions"], {"xz": "5.8.3"})
        self.assertEqual(report["fixture"]["format"], "bed@1.0")
        self.assertEqual(report["fixture"]["coordinate_system"], "zero-based-half-open")
        self.assertTrue(report["source_reconciliation_passed"])

    def test_overlap_summary_is_geometrically_consistent_and_scope_limited(self):
        summary = json.loads(REPORT.read_text(encoding="utf-8"))["scientific_summary"]
        self.assertEqual(summary["overlap_pair_count"], 3)
        self.assertEqual(summary["overlapping_query_interval_count"], 2)
        self.assertEqual(summary["overlapping_reference_interval_count"], 2)
        self.assertEqual(summary["total_pairwise_overlap_bp"], 10)
        self.assertIn("null models", summary["interpretation_policy"])

    def test_report_contains_no_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
