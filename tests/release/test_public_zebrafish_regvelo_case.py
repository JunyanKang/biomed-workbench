import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-zebrafish-regvelo.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-regulatory-velocity"
)


class PublicZebrafishRegVeloCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_official_sources_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(
            report["source"]["sha256"],
            "eccab081c44cfe335b726aec8172bbcda072241b4f006f6420bb5d46d39611cb",
        )
        self.assertEqual(report["source"]["documented_shape"], [697, 8012])
        self.assertEqual(
            report["prior_grn"]["sha256"],
            "356bfde785af53e36f9334c4f5032c06f111d67d30b881b41e24a8ebde7a536a",
        )
        self.assertEqual(report["prior_grn"]["documented_shape"], [4508, 4508])
        assert_evidence_scope_current(self, report)
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "templates" / "run_regvelo.py").read_bytes()
            ).hexdigest(),
        )

    def test_case_executes_continuous_semantics_and_complete_regvelo_outputs(self):
        report = self.report
        derivation = report["derivation"]
        execution = report["execution"]
        self.assertEqual(derivation["cells"], 697)
        self.assertEqual(derivation["features"], 1008)
        self.assertEqual(derivation["regulators"], 81)
        self.assertEqual(derivation["edges"], 4309)
        self.assertFalse(derivation["labels_used_for_preprocessing"])
        self.assertTrue(
            derivation["labels_removed_before_preprocessing_and_restored_after"]
        )
        self.assertFalse(derivation["splicing_layers"]["Ms"]["integer_like"])
        self.assertFalse(derivation["splicing_layers"]["Mu"]["integer_like"])
        self.assertEqual(report["parameters"]["model_modes"], ["hard", "soft"])
        self.assertEqual(report["parameters"]["max_epochs"], 20)
        self.assertEqual(len(execution["runs"]), 2)
        self.assertTrue(execution["all_outputs_finite"])
        self.assertTrue(execution["models_saved_and_reloaded"])
        self.assertTrue(execution["source_layers_preserved"])
        self.assertTrue(execution["output_reloaded"])
        repeated = execution["deterministic_repeat_execution"]
        self.assertEqual(repeated["independent_template_runs"], 2)
        self.assertTrue(repeated["same_parameters_histories_and_mode_comparison"])
        self.assertTrue(all(item["exactly_equal"] for item in repeated["outputs"].values()))
        self.assertTrue(
            all(
                item["maximum_absolute_difference"] == 0
                for item in repeated["outputs"].values()
            )
        )

    def test_withheld_stage_direction_passes_without_hiding_mode_sensitivity(self):
        execution = self.report["execution"]
        direction = execution["withheld_stage_direction"]
        self.assertFalse(direction["used_for_fitting_or_preprocessing"])
        self.assertEqual(direction["included_cells"], 695)
        self.assertGreater(direction["spearman_rho"], 0.7)
        self.assertLess(direction["spearman_pvalue"], 1e-100)
        self.assertEqual(
            direction["excluded_stages"],
            [{"cells": 2, "reason": "fewer-than-20-cells", "stage": "3ss"}],
        )
        comparison = execution["mode_comparisons"][0]
        self.assertEqual({comparison["left"], comparison["right"]}, {"hard-seed-2026", "soft-seed-2026"})
        self.assertTrue(-1 <= comparison["velocity_pearson"] <= 1)
        self.assertEqual(
            execution["mode_sensitivity_status"],
            "warning-no-robustness-claim",
        )

    def test_case_records_unrun_methods_limits_and_contains_no_private_material(self):
        self.assertEqual(set(self.report["methods_not_run"].values()), {"not-run"})
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "does not establish portability",
            "withheld from preprocessing and model fitting",
            "does not claim mode-robust velocities",
            "no cellrank fate",
            "not treated as wholly independent causal evidence",
        ):
            self.assertIn(phrase, boundaries)
        serialized = REPORT.read_text(encoding="utf-8")
        for forbidden in ("/Users/", "/private/", "/var/folders/", "API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(forbidden, serialized)
        self.assertIsNone(
            re.search(
                r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}",
                serialized,
                re.IGNORECASE,
            )
        )


if __name__ == "__main__":
    unittest.main()
