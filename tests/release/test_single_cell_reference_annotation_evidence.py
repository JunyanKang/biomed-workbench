import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-reference-annotation"
REPORT = ROOT / "reports" / "single-cell-reference-annotation-live-verification.json"


class SingleCellReferenceAnnotationEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_templates_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        templates = {"annotate_reference": "annotate_reference.py", "run_singler": "run_singler.R"}

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        for key, filename in templates.items():
            path = MODULE_ROOT / "templates" / filename
            self.assertEqual(report["templates"][key]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions) - {"python"})
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))

    def test_known_cells_are_accepted_and_unknown_population_is_retained(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        results = report["results"]

        self.assertEqual(results["accepted_cells"], 240)
        self.assertEqual(results["unknown_cells"], 40)
        self.assertEqual(results["known_cell_accuracy"], 1.0)
        self.assertEqual(results["macro_f1"], 1.0)
        self.assertEqual(results["unknown_retention_fraction"], 1.0)
        self.assertIn("ontology_allowed", results["unknown_group_blocking_gates"])
        self.assertIn("positive_marker_support", results["unknown_group_blocking_gates"])

    def test_report_proves_execution_source_preservation_and_posthoc_evaluation(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        self.assertTrue(report["execution"]["singler_completed"])
        self.assertTrue(summary["marker_contracts_applied"])
        self.assertTrue(summary["ontology_ancestor_constraints_applied"])
        self.assertTrue(summary["unknown_population_retained"])
        self.assertTrue(summary["existing_labels_and_raw_counts_preserved"])
        self.assertTrue(summary["evaluation_labels_posthoc_only"])
        self.assertTrue(summary["annotated_h5ad_reloaded"])
        self.assertTrue(summary["no_environment_or_compute_infrastructure_managed"])

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
