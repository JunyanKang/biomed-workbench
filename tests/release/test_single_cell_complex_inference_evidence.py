import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-complex-inference"
REPORT = ROOT / "reports" / "single-cell-complex-inference-live-verification.json"


class SingleCellComplexInferenceEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_templates_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        templates = {"prepare": "prepare_inference_inputs.py", "dream": "fit_dream_longitudinal.R", "composition": "fit_composition_models.R"}

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        for key, filename in templates.items():
            path = MODULE_ROOT / "templates" / filename
            self.assertEqual(report["templates"][key]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))

    def test_linear_and_spline_models_recover_planted_program(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        expected = {f"GENE{index:03d}" for index in range(5)}
        models = report["model_summaries"]

        self.assertEqual(set(models["linear"]["planted_top_five"]), expected)
        self.assertEqual(set(models["spline"]["planted_joint_top_five"]), expected)
        self.assertEqual(models["spline"]["basis_coefficients_per_cell_type"], 2)

    def test_composition_primary_and_reference_sensitivity_are_distinct(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        composition = report["model_summaries"]["composition"]
        observations = report["compatibility_observations"]

        self.assertGreater(composition["primary_effects"]["TypeA"], 0)
        self.assertLess(composition["primary_effects"]["TypeB"], 0)
        self.assertTrue(composition["reference_stability"]["TypeA"]["admitted_reference_stable"])
        self.assertTrue(composition["reference_stability"]["TypeB"]["admitted_reference_stable"])
        self.assertEqual(composition["reference_stability"]["TypeC"]["direction"], "discordant")
        self.assertFalse(composition["reference_stability"]["TypeC"]["admitted_reference_stable"])
        self.assertEqual(observations["primary_repeated_measure_backend"], "variancePartition-dream")
        self.assertIn("fixed-only-sensitivity", observations["propeller_backend_used"])

    def test_report_proves_experimental_unit_accounting_and_reload(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        for key in (
            "biological_samples_used_as_replicates", "cells_not_used_as_replicates", "all_cells_and_counts_accounted",
            "subject_random_effect_enforced", "linear_longitudinal_effect_recovered", "nonlinear_spline_joint_test_executed",
            "variance_components_extracted", "complete_composition_grid_and_closure_checked",
            "repeated_measure_composition_effects_recovered", "propeller_fixed_only_sensitivity_explicit",
            "multi_reference_alr_sensitivity_completed", "reference_discordance_preserved", "outputs_reloaded",
        ):
            self.assertTrue(summary[key], key)

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
