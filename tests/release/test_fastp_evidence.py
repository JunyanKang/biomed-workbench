import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "fastp-live-verification.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / "read-quality-fastp" / "module.json"


class FastPEvidenceTests(unittest.TestCase):
    def test_live_report_binds_exact_bioconda_build_row_and_fixture(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads(MODULE.read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["tool_versions"], {"fastp": "1.3.6"})
        self.assertEqual(report["dependency_versions"], {"fastp-bioconda-build": "1.3.6-ha1d0559_0"})
        self.assertEqual(report["runtime_lock"]["fastp"], "1.3.6-ha1d0559_0")
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["fixture"]["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())

    def test_qc_only_summary_preserves_reads_and_states_screening_limit(self):
        summary = json.loads(REPORT.read_text(encoding="utf-8"))["scientific_summary"]

        self.assertTrue(summary["qc_only_read_accounting_passed"])
        self.assertEqual(summary["metrics"]["total_reads"], 12)
        self.assertEqual(summary["contamination_screening"]["status"], "not-assessed")
        self.assertEqual(summary["downstream_readiness"], "requires-assay-aware-review")

    def test_report_contains_no_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/", "NCBI_API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
