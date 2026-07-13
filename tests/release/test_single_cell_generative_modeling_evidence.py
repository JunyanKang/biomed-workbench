import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-generative-modeling"
REPORT = ROOT / "reports" / "single-cell-generative-modeling-live-verification.json"


class SingleCellGenerativeModelingEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_template_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        template = MODULE_ROOT / "templates" / "train_scvi_scanvi.py"

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["templates"]["train_scvi_scanvi"]["sha256"], hashlib.sha256(template.read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions) - {"python"})
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))

    def test_scvi_is_blocked_and_scanvi_is_independently_eligible(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))

        self.assertEqual(report["decision"]["eligible_modes"], ["scanvi"])
        self.assertEqual(report["decision"]["selected_mode"], "scanvi")
        self.assertEqual(set(report["decision"]["blocked_modes"]["scvi"]), {"batch_mixing_gain", "label_graph_connected"})
        self.assertEqual(report["results"]["scanvi"]["heldout_macro_f1"], 1.0)
        self.assertTrue(all(report["results"]["scanvi"]["quality_gates"].values()))
        self.assertFalse(report["results"]["scvi"]["quality_gates"]["batch_mixing_gain"])

    def test_artifacts_reload_and_unknown_labels_remain_reviewable(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        self.assertEqual(report["fixture"]["unknown_cells"], 48)
        self.assertTrue(summary["models_and_h5ad_reloaded"])
        self.assertTrue(summary["raw_counts_preserved"])
        self.assertTrue(summary["reviewed_and_unknown_labels_preserved"])
        self.assertTrue(summary["scanvi_evaluated_on_hidden_labels"])
        self.assertTrue(summary["scanvi_predictions_are_reviewable_suggestions"])
        self.assertTrue(summary["no_environment_or_compute_infrastructure_managed"])

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
