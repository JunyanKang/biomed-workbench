import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-doublet-detection.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-doublet-detection"
)


class PublicGSE96583DoubletCaseReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_templates(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["accession"], "GSE96583")
        self.assertEqual(report["module"]["version"], "1.1.0")
        assert_evidence_scope_current(self, report)
        for filename in ("run_scrublet.py", "run_scdblfinder.R"):
            self.assertEqual(
                report["module"]["template_sha256"][filename],
                hashlib.sha256((MODULE_ROOT / "templates" / filename).read_bytes()).hexdigest(),
            )

    def test_frozen_label_withheld_design_and_results(self):
        parameters = self.report["parameters"]
        execution = self.report["execution"]
        self.assertFalse(parameters["labels_available_to_methods"])
        self.assertFalse(parameters["labels_used_for_threshold_selection"])
        self.assertEqual(parameters["expected_doublet_rate"], 0.10)
        self.assertEqual(execution["input_cells"], 29065)
        self.assertEqual(execution["ambiguous_cells_excluded_from_metrics"], 1217)
        self.assertGreaterEqual(
            execution["method_metrics"]["scrublet"]["overall"]["auroc"], 0.85
        )
        self.assertGreaterEqual(
            execution["method_metrics"]["scDblFinder"]["overall"]["auroc"], 0.90
        )
        self.assertGreater(
            execution["method_agreement"][
                "published_doublet_prevalence_among_both_called"
            ],
            execution["method_agreement"]["published_doublet_prevalence"],
        )
        self.assertTrue(all(value == "pass" for value in self.report["quality_gates"].values()))

    def test_case_records_incomplete_label_boundary_and_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "withheld from fitting",
            "ambiguous publisher labels",
            "miss same-donor doublets",
            "no cell was automatically removed",
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
