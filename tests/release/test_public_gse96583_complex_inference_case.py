import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-complex-inference.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-complex-inference"
)


class PublicGSE96583ComplexInferenceCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_templates(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["accession"], "GSE96583")
        self.assertEqual(report["module"]["version"], "1.1.0")
        self.assertEqual(
            report["module"]["manifest_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "module.json").read_bytes()
            ).hexdigest(),
        )
        for name, digest in report["module"]["template_sha256"].items():
            self.assertEqual(
                digest,
                hashlib.sha256(
                    (MODULE_ROOT / "templates" / name).read_bytes()
                ).hexdigest(),
            )

    def test_paired_design_and_label_blind_features_are_preserved(self):
        source = self.report["source"]["validation"]
        selection = source["feature_selection"]
        self.assertEqual(source["subjects"], 8)
        self.assertEqual(source["biological_samples"], 16)
        self.assertEqual(len(source["cell_types"]), 6)
        self.assertEqual(source["minimum_cells_per_sample_cell_type"], 15)
        self.assertEqual(selection["selected_features"], 1200)
        self.assertLessEqual(
            selection["maximum_predeclared_ifn_control_rank"], 1200
        )
        self.assertTrue(selection["all_predeclared_ifn_controls_retained"])
        self.assertIn("label-blind", selection["method"])

    def test_sample_level_models_and_statistical_outputs_pass(self):
        execution = self.report["execution"]
        self.assertEqual(execution["pseudobulks"], 96)
        self.assertEqual(execution["eligible_pseudobulks"], 96)
        self.assertGreater(execution["expression_result_rows"], 0)
        self.assertGreater(execution["variance_result_rows"], 0)
        self.assertGreater(execution["composition_result_rows"], 0)
        self.assertGreater(execution["alr_result_rows"], 0)
        self.assertEqual(len(execution["ifn_response_by_cell_type"]), 6)
        self.assertTrue(execution["source_artifacts_immutable"])
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "not a multi-timepoint longitudinal trajectory",
            "biological samples rather than cells are model rows",
            "predeclared external direction sanity check",
            "discordance is preserved",
            "rather than causal effects",
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
