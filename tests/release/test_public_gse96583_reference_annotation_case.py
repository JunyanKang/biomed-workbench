import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-reference-annotation.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-reference-annotation"
)


class PublicGSE96583ReferenceAnnotationCaseTests(unittest.TestCase):
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
            hashlib.sha256((MODULE_ROOT / "module.json").read_bytes()).hexdigest(),
        )
        for filename in ("annotate_reference.py", "run_singler.R"):
            self.assertEqual(
                report["module"]["template_sha256"][filename],
                hashlib.sha256(
                    (MODULE_ROOT / "templates" / filename).read_bytes()
                ).hexdigest(),
            )

    def test_query_labels_are_withheld_and_donors_are_disjoint(self):
        parameters = self.report["parameters"]
        source = self.report["source"]["source_validation"]
        self.assertTrue(parameters["donor_split_frozen_before_mapping"])
        self.assertFalse(parameters["publisher_labels_available_to_mapping"])
        self.assertFalse(parameters["publisher_labels_used_for_threshold_selection"])
        self.assertEqual(parameters["held_out_reference_label"], "Megakaryocytes")
        self.assertEqual(len(source["reference_donors"]), 6)
        self.assertEqual(len(source["query_donors"]), 2)
        self.assertTrue(
            set(source["reference_donors"]).isdisjoint(source["query_donors"])
        )
        self.assertEqual(source["reference_cells_after_balancing"], 840)
        self.assertEqual(source["query_cells"], 4139)
        self.assertEqual(source["genes"], 35635)

    def test_conservative_performance_and_unknown_boundary_are_preserved(self):
        execution = self.report["execution"]
        self.assertGreaterEqual(
            execution["known_label_accuracy_among_accepted"], 0.95
        )
        self.assertGreaterEqual(execution["known_label_coverage"], 0.80)
        self.assertGreaterEqual(
            execution["known_macro_f1_with_unknown_penalty"], 0.60
        )
        self.assertEqual(execution["held_out_class_cells"], 32)
        self.assertGreaterEqual(
            execution["held_out_class_unknown_retention"], 0.50
        )
        self.assertTrue(execution["all_query_cells_accounted"])
        self.assertTrue(execution["source_artifacts_immutable"])
        self.assertTrue(execution["output_reloaded"])
        self.assertTrue(execution["raw_counts_preserved"])
        self.assertTrue(execution["existing_labels_preserved"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )
        per_label = execution["per_publisher_label"]
        self.assertLess(per_label["NK cells"]["accepted_fraction"], 0.01)
        self.assertLess(per_label["CD8 T cells"]["accepted_fraction"], 0.10)

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "absent from the query h5ad",
            "removed from the reference",
            "label-independent query clusters",
            "only after the annotated h5ad",
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
