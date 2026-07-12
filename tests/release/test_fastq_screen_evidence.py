import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.kernel.identity import digest_value
from biomed_workbench.modules.contract import parse_manifest


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "fastq-screen-live-verification.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "read-contamination-screen" / "module.json"


class FastQScreenEvidenceTests(unittest.TestCase):
    def test_live_report_binds_tool_dependencies_reference_manifest_and_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["tool_versions"], {"fastq-screen": "0.16.0"})
        self.assertEqual(report["dependency_versions"], {name: versions[0] for name, versions in row.dependency_versions.items()})
        self.assertEqual(report["runtime_lock"]["bowtie2"], "2.5.5-h9e91881_0")
        self.assertEqual(report["reference_manifest_digest"], digest_value(report["reference_manifest"]))
        self.assertEqual(report["fixture"]["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())

    def test_screening_summary_uses_declared_reference_scope_and_denominator(self):
        summary = json.loads(REPORT.read_text(encoding="utf-8"))["scientific_summary"]

        self.assertEqual(summary["reads_processed"], 12)
        self.assertEqual(summary["expected_references"], ["target"])
        self.assertEqual(summary["contamination_screening"], {"status": "passed", "reference_count": 2})
        self.assertEqual(summary["flagged_unexpected_references"], [])
        self.assertIn("unrepresented contaminants", summary["interpretation_policy"])

    def test_report_contains_no_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
