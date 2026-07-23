import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-doublet-detection"
)
REPORT = ROOT / "reports" / "single-cell-doublet-detection-live-verification.json"


class SingleCellDoubletDetectionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.manifest = parse_manifest(
            json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8"))
        )

    def test_report_is_bound_to_both_templates_and_versions(self):
        row = self.manifest.compatibility_matrix[0]
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["module_id"], self.manifest.id)
        self.assertEqual(self.report["module_version"], self.manifest.version)
        self.assertEqual(self.report["compatibility_row_id"], row.id)
        for method, filename in (
            ("scrublet", "run_scrublet.py"),
            ("scDblFinder", "run_scdblfinder.R"),
        ):
            self.assertEqual(
                self.report["templates"][method]["sha256"],
                hashlib.sha256(
                    (MODULE_ROOT / "templates" / filename).read_bytes()
                ).hexdigest(),
            )
        self.assertTrue(
            all(
                version_is_allowed(value, row.dependency_versions[name])
                for name, value in self.report["dependency_versions"].items()
            )
        )

    def test_execution_preserves_sources_and_disagreement(self):
        execution = self.report["execution"]
        summary = self.report["scientific_summary"]
        self.assertTrue(execution["scrublet_completed"])
        self.assertTrue(execution["scdblfinder_completed"])
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(execution["sparse_reload_validation_completed"])
        self.assertTrue(execution["source_immutability_verified"])
        self.assertTrue(summary["raw_counts_preserved"])
        self.assertTrue(summary["cell_and_feature_identity_preserved"])
        self.assertTrue(summary["score_distributions_retained"])
        self.assertTrue(summary["method_disagreement_preserved"])
        self.assertTrue(summary["no_automatic_cell_removal"])

    def test_report_contains_no_private_material(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/var/folders/", "API_KEY", "SECRET="):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
