import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-regulatory-velocity"
REPORT = ROOT / "reports" / "single-cell-regulatory-velocity-live-verification.json"


class SingleCellRegulatoryVelocityEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_template_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        template = MODULE_ROOT / "templates" / "run_regvelo.py"
        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["templates"]["run_regvelo"]["sha256"], hashlib.sha256(template.read_bytes()).hexdigest())
        self.assertTrue(version_is_allowed(report["tool_versions"]["RegVelo"], row.tool_versions["RegVelo"]))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(
            version_is_allowed(version, row.dependency_versions[name])
            for name, version in report["dependency_versions"].items()
        ))

    def test_observed_execution_covers_core_regvelo_outputs_and_model_modes(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        execution = report["execution"]
        results = report["results"]
        self.assertTrue(execution["hard_constraint_completed"])
        self.assertTrue(execution["soft_constraint_completed"])
        self.assertTrue(execution["velocity_completed"])
        self.assertTrue(execution["latent_time_completed"])
        self.assertTrue(execution["models_reloaded"])
        self.assertTrue(execution["outputs_reloaded"])
        self.assertEqual(results["velocity_shape"], [96, 24])
        self.assertEqual(results["latent_time_shape"], [96, 24])
        self.assertEqual(results["latent_shape"], [96, 10])
        self.assertTrue(results["velocity_finite"])
        self.assertTrue(results["latent_time_finite"])

    def test_scientific_and_compatibility_boundaries_are_explicit(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]
        observations = report["compatibility_observations"]
        self.assertTrue(summary["grn_namespace_orientation_and_edges_validated"])
        self.assertTrue(summary["dense_memory_budget_enforced"])
        self.assertTrue(summary["model_mode_comparison_retained"])
        self.assertTrue(summary["source_counts_grn_and_identifiers_preserved"])
        self.assertTrue(summary["integer_count_semantics_executed"])
        self.assertTrue(summary["perturbation_predictions_limited_to_hypotheses"])
        self.assertEqual(observations["integer_count_layer_semantics"], "integer-counts")
        self.assertIn("blocked", observations["sparse_working_layers"])
        self.assertIn("square", observations["rectangular_model_grn"])
        self.assertIn("excluded", observations["numpy_2_profile"])
        self.assertIn("excluded", observations["modern_jax_profile"])
        self.assertIn("blocked", observations["custom_n_latent_or_n_hidden"])

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
