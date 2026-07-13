import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-trajectory-velocity"
REPORT = ROOT / "reports" / "single-cell-trajectory-velocity-live-verification.json"


class SingleCellTrajectoryVelocityEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_template_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        template = MODULE_ROOT / "templates" / "run_velocity.py"

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["templates"]["run_velocity"]["sha256"], hashlib.sha256(template.read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions) - {"python"})
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))

    def test_direction_is_supported_by_time_anchors_and_confidence(self):
        results = json.loads(REPORT.read_text(encoding="utf-8"))["results"]

        self.assertGreaterEqual(results["modeled_genes"], 20)
        self.assertGreaterEqual(results["latent_time_spearman"], 0.65)
        self.assertGreaterEqual(results["velocity_pseudotime_spearman"], 0.25)
        self.assertGreaterEqual(results["root_terminal_separation"], 0.05)
        self.assertGreaterEqual(results["median_velocity_confidence"], 0.7)

    def test_report_proves_real_execution_and_source_preservation(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        self.assertTrue(report["execution"]["dynamical_model_completed"])
        self.assertTrue(report["execution"]["velocity_graph_completed"])
        self.assertTrue(summary["experimental_time_withheld_from_model_fitting"])
        self.assertTrue(summary["latent_time_direction_validated_against_known_time"])
        self.assertTrue(summary["root_and_terminal_direction_validated"])
        self.assertTrue(summary["source_counts_and_identifiers_preserved"])
        self.assertTrue(summary["velocity_h5ad_reloaded"])
        self.assertTrue(summary["no_environment_or_compute_infrastructure_managed"])

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
