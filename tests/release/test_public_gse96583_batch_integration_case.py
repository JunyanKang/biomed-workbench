import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-batch-integration.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-batch-integration"
)


class PublicGSE96583BatchIntegrationCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["accession"], "GSE96583")
        self.assertEqual(report["module"]["version"], "1.1.0")
        self.assertEqual(
            report["module"]["manifest_sha256"],
            hashlib.sha256((MODULE_ROOT / "module.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "templates" / "benchmark_integration.py").read_bytes()
            ).hexdigest(),
        )

    def test_crossed_design_and_label_isolation_are_preserved(self):
        source = self.report["source"]["source_validation"]
        parameters = self.report["parameters"]
        execution = self.report["execution"]
        self.assertEqual(source["selected_cells"], 6400)
        self.assertEqual(source["genes"], 35635)
        self.assertEqual(source["donors"], 8)
        self.assertEqual(source["conditions"], 2)
        self.assertEqual(source["biological_samples"], 16)
        self.assertGreaterEqual(source["minimum_donors_per_stratum"], 2)
        self.assertEqual(parameters["batch_key"], "donor")
        self.assertEqual(parameters["biological_sample_key"], "donor:condition")
        self.assertTrue(execution["counterfactual_pca_exact"])
        self.assertEqual(execution["counterfactual_max_absolute_difference"], 0.0)
        self.assertTrue(
            all(
                result["source_immutable"]
                and result["identity_preserved"]
                and result["reload_validated"]
                for result in execution["method_results"].values()
            )
        )

    def test_selection_retains_blocked_method_and_biology_gates(self):
        execution = self.report["execution"]
        results = execution["method_results"]
        self.assertEqual(set(execution["eligible_methods"]), {"bbknn", "harmony"})
        self.assertEqual(
            set(execution["blocked_methods"]["scanorama"]),
            {"batch_mixing_gain", "label_purity_preserved"},
        )
        self.assertEqual(execution["selected_method"], "bbknn")
        self.assertGreaterEqual(
            results["bbknn"]["metric_deltas"]["batch_neighbor_entropy_gain"], 0.02
        )
        self.assertLessEqual(
            results["bbknn"]["metric_deltas"]["label_neighbor_purity_loss"], 0.10
        )
        self.assertLess(
            results["scanorama"]["metric_deltas"]["batch_neighbor_entropy_gain"], 0
        )
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "donor is treated as the integration batch",
            "only after each backend",
            "physically removes evaluation labels",
            "dataset- and parameter-specific",
        ):
            self.assertIn(phrase, boundaries)
        serialized = REPORT.read_text(encoding="utf-8")
        for forbidden in (
            "/Users/",
            "/private/",
            "/var/folders/",
            "ACCESS_TOKEN=",
            "SECRET=",
        ):
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
