import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "fastqc-live-verification.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "read-quality-fastqc" / "module.json"


class FastQCEvidenceTests(unittest.TestCase):
    def test_live_report_is_bound_to_module_row_fixture_and_exact_versions(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["tool_versions"], {"fastqc": "0.12.1"})
        self.assertEqual(report["dependency_versions"], {"java": "22"})
        self.assertEqual(report["fixture"]["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        self.assertEqual(report["fixture"]["record_count"], 12)

    def test_report_contains_complete_scientific_interpretation_surface(self):
        summary = json.loads(REPORT.read_text(encoding="utf-8"))["scientific_summary"]

        self.assertEqual(summary["fastqc_version"], "0.12.1")
        self.assertEqual(summary["basic_statistics"]["total_sequences"], 12)
        self.assertEqual(sum(summary["status_counts"].values()), 10)
        self.assertEqual(summary["downstream_readiness"], "requires-assay-aware-review")
        self.assertTrue(summary["flagged_modules"])

    def test_report_contains_no_machine_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
