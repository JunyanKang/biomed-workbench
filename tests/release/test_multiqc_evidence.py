import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "multiqc-live-verification.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "quality-report-multiqc" / "module.json"


class MultiQCEvidenceTests(unittest.TestCase):
    def test_live_report_binds_tested_baselines_compatibility_policy_and_fixture(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["tool_versions"], {item.name: item.tested_versions[0] for item in manifest.tool_requirements})
        self.assertEqual(report["dependency_versions"], {item.name: item.tested_versions[0] for item in manifest.dependencies})
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertTrue(all(version_is_allowed(report["dependency_versions"][name], rules) for name, rules in row.dependency_versions.items()))
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["fixture"]["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        self.assertGreaterEqual(len(report["runtime_lock"]), 50)

    def test_aggregate_summary_reconciles_both_samples_and_versions(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(set(summary["samples"]), {"sample-a", "sample-b"})
        self.assertEqual(summary["fastqc_versions"], ["0.12.1"])
        self.assertEqual(summary["downstream_readiness"], "requires-assay-aware-review")
        self.assertTrue(report["html_report_validated"])
        self.assertTrue(report["source_fastqc_completed"])

    def test_report_contains_no_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
