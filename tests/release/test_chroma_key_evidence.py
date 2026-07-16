import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "chroma-key-live-verification.json"
IMPLEMENTATION = ROOT / "biomed_workbench" / "implementations" / "chroma_key.py"


class ChromaKeyEvidenceTests(unittest.TestCase):
    def test_report_binds_runtime_fixture_output_and_scientific_boundary(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("image-chroma-key-remove")
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["implementation"]["sha256"], hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest())
        self.assertEqual(report["scientific_summary"]["quality_status"], "passed")
        self.assertEqual(report["scientific_summary"]["scientific_use"], "communication-asset-only")
        self.assertFalse(report["scientific_summary"]["quantitative_interpretation_allowed"])
        self.assertGreater(report["scientific_summary"]["alpha_counts"]["transparent"], 0)
        self.assertGreater(report["scientific_summary"]["alpha_counts"]["partial"], 0)
        self.assertGreater(report["scientific_summary"]["alpha_counts"]["opaque"], 0)

    def test_public_evidence_has_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "ACCESS_TOKEN="):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
