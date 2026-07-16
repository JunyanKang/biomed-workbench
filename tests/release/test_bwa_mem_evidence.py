import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "bwa-mem-live-verification.json"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "dna-align-bwa-mem-single" / "module.json"


class BwaMemEvidenceTests(unittest.TestCase):
    def test_live_report_binds_actual_versions_tested_baseline_and_policy(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertTrue(all(report["tested_version_baseline"]["tools"].values()))
        self.assertTrue(all(report["tested_version_baseline"]["dependencies"].values()))
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertTrue(all(version_is_allowed(report["dependency_versions"][name], rules) for name, rules in row.dependency_versions.items()))
        self.assertEqual(report["compatibility_policy"]["tools"], {name: list(rules) for name, rules in row.tool_versions.items()})

    def test_fixture_preserves_sample_reference_reads_and_portable_sam(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]
        self.assertEqual(report["fixture"]["read_count"], 2)
        self.assertEqual(summary["sample_id"], "bwa-fixture-01")
        self.assertEqual(summary["counts"]["mapped"], 1)
        self.assertEqual(summary["counts"]["unmapped"], 1)
        self.assertEqual(summary["primary_mapping_percent"], 50.0)
        self.assertTrue(report["portable_program_record_validated"])

    def test_report_contains_no_machine_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
