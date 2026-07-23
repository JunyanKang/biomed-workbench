import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-pbmc3k-atlas-annotation.json"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-atlas-annotation"


class PublicPBMC3kAtlasAnnotationReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_public_query_model_and_packaged_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["sha256"], "847d6ebd9a1ec9a768f2be7e40ca42cbfe75ebeb6d76a4c24167041699dc28b5")
        self.assertEqual(report["reference"]["model"], "Immune_All_Low.pkl")
        self.assertEqual(report["reference"]["version"], "v2")
        self.assertEqual(report["reference"]["classes"], 98)
        self.assertEqual(
            report["module"]["manifest_sha256"],
            hashlib.sha256((MODULE_ROOT / "module.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "annotate_celltypist.py").read_bytes()).hexdigest(),
        )

    def test_case_preserves_counts_unknowns_and_complete_probability_evidence(self):
        execution = self.report["execution"]
        validation = execution["output_validation"]
        self.assertEqual(execution["cells"], 2700)
        self.assertEqual(execution["features"], 32738)
        self.assertEqual(execution["prediction_label_count"], 98)
        self.assertGreater(execution["model_feature_overlap"], 1000)
        self.assertGreater(execution["unknown_cells"], 0)
        self.assertTrue(validation["raw_counts_preserved"])
        self.assertTrue(validation["all_cells_accounted"])
        self.assertTrue(validation["complete_probability_matrix"])
        self.assertTrue(validation["unknown_policy_exact"])
        self.assertEqual(validation["probability_matrix_shape"], [2700, 98])
        self.assertTrue(all(value == "pass" for value in self.report["quality_gates"].values()))

    def test_marker_review_is_posthoc_broad_and_directionally_coherent(self):
        review = self.report["execution"]["posthoc_marker_review"]
        self.assertIn("after", review["timing"])
        self.assertIn("not tuning", review["purpose"])
        self.assertGreaterEqual(len(review["families"]), 3)
        self.assertTrue(review["all_evaluable_families_enriched"])
        for evidence in review["families"].values():
            self.assertEqual(evidence["direction"], "enriched")
            self.assertGreater(evidence["difference"], 0)
        self.assertIn("T", review["not_evaluable_families"])
        self.assertIn(
            "fewer-than-3-declared-markers-present",
            review["not_evaluable_families"]["T"]["reasons"],
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "not biological ground truth",
            "markers did not tune",
            "does not establish generalization",
            "cannot validate all 98",
            "future model updates require",
        ):
            self.assertIn(phrase, boundaries)
        serialized = REPORT.read_text(encoding="utf-8")
        for forbidden in ("/Users/", "/private/", "/var/folders/", "ACCESS_TOKEN=", "SECRET="):
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
