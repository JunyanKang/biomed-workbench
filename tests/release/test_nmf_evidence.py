import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "nmf-live-verification.json"
FIXTURE = ROOT / "tests" / "fixtures" / "omics"
IMPLEMENTATION = ROOT / "biomed_workbench" / "implementations" / "nmf_metagenes.py"


class NMFEvidenceTests(unittest.TestCase):
    def test_live_report_binds_runtime_fixture_factors_and_selection(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("metagene-factorization-nmf")
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["fixture"]["matrix_sha256"], hashlib.sha256((FIXTURE / "nmf-matrix.tsv").read_bytes()).hexdigest())
        self.assertEqual(report["fixture"]["features_sha256"], hashlib.sha256((FIXTURE / "nmf-features.txt").read_bytes()).hexdigest())
        self.assertEqual(report["fixture"]["samples_sha256"], hashlib.sha256((FIXTURE / "nmf-samples.txt").read_bytes()).hexdigest())
        self.assertEqual(report["implementation"]["sha256"], hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest())
        self.assertEqual(report["scientific_summary"]["selected_rank"], 2)
        self.assertEqual(report["scientific_summary"]["removed_features"], ["GENE_ZERO", "GENE_CONSTANT"])
        self.assertEqual(report["scientific_summary"]["quality_status"], "passed")
        self.assertGreater(report["scientific_summary"]["rank_metrics"][0]["component_stability"], 0.99)
        self.assertLess(report["scientific_summary"]["selected_relative_error"], 0.001)

    def test_public_evidence_has_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "nvapi-"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
