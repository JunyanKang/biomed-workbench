import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "alignment-quality-live-verification.json"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "alignment-quality-samtools" / "module.json"


class AlignmentQualityEvidenceTests(unittest.TestCase):
    def test_live_report_binds_exact_toolchain_row_and_bam_bundle(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["tool_versions"], {"samtools": "1.23"})
        self.assertEqual(report["dependency_versions"], {"htslib": "1.23"})
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["fixture_manifest"]["sample_id"], "alignment-qc-fixture")
        self.assertEqual(report["fixture_manifest"]["format"], "bam@1.6")
        self.assertTrue(all(report["bundle_integrity"].values()))

    def test_scientific_summary_is_consistent_and_scope_limited(self):
        summary = json.loads(REPORT.read_text(encoding="utf-8"))["scientific_summary"]
        self.assertEqual(summary["counts"]["total"], 4)
        self.assertEqual(summary["counts"]["mapped"], 2)
        self.assertEqual(summary["metrics"]["mapped_percent"], 50.0)
        self.assertEqual(summary["metrics"]["properly_paired_percent"], 50.0)
        self.assertIn("biological adequacy", summary["interpretation_policy"])

    def test_report_contains_no_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
