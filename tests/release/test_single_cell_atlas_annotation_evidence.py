import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-atlas-annotation"
REPORT = ROOT / "reports" / "single-cell-atlas-annotation-live-verification.json"


class SingleCellAtlasAnnotationEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_every_template_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        templates = {
            "celltypist": "annotate_celltypist.py",
            "azimuth": "annotate_azimuth.R",
            "popv": "annotate_popv.py",
        }

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

    def test_known_classes_and_absent_reference_population_are_both_handled(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summaries = report["backend_summaries"]

        self.assertEqual(set(summaries), {"celltypist", "azimuth", "popv"})
        for summary in summaries.values():
            self.assertEqual(summary["cells"], 150)
            self.assertGreaterEqual(summary["known_accuracy"], 0.95)
            self.assertGreater(summary["novel_unknown"], 0)
            self.assertTrue(summary["counts_present"])

    def test_report_proves_method_evidence_cell_accounting_and_source_preservation(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        self.assertTrue(report["execution"]["celltypist_completed"])
        self.assertTrue(report["execution"]["azimuth_completed"])
        self.assertTrue(report["execution"]["popv_completed"])
        self.assertTrue(report["execution"]["outputs_reloaded"])
        self.assertTrue(summary["method_specific_probabilities_and_scores_retained"])
        self.assertTrue(summary["absent_reference_population_retained_as_unknown"])
        self.assertTrue(summary["popv_expert_disagreement_preserved"])
        self.assertTrue(summary["all_query_cells_accounted"])
        self.assertTrue(summary["source_counts_and_identifiers_preserved"])
        self.assertTrue(summary["evaluation_labels_posthoc_only"])

    def test_observed_popv_xgboost_conflict_is_not_hidden(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        observation = report["compatibility_observations"]

        self.assertEqual(observation["popv_validated_experts"], ["Support_Vector", "Random_Forest", "CELLTYPIST"])
        self.assertIn("segmentation-fault", observation["popv_xgboost_status"])

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
