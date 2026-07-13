import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-batch-integration"
REPORT = ROOT / "reports" / "single-cell-batch-integration-live-verification.json"


class SingleCellBatchIntegrationEvidenceTests(unittest.TestCase):
    def test_live_report_is_bound_to_template_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        template = MODULE_ROOT / "templates" / "benchmark_integration.py"

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["templates"]["benchmark_integration"]["sha256"], hashlib.sha256(template.read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions) - {"python"})
        self.assertTrue(all(version_is_allowed(version, row.dependency_versions[name]) for name, version in report["dependency_versions"].items()))

    def test_all_methods_execute_but_only_gate_eligible_methods_can_be_selected(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        candidates = report["candidate_results"]

        self.assertEqual(set(candidates), {"harmony", "scanorama", "bbknn"})
        self.assertEqual(set(report["decision"]["eligible_methods"]), {"scanorama", "bbknn"})
        self.assertEqual(report["decision"]["blocked_methods"], {"harmony": ["batch_mixing_gain"]})
        self.assertEqual(report["decision"]["selected_method"], "bbknn")
        self.assertFalse(candidates["harmony"]["quality_gates"]["batch_mixing_gain"])
        self.assertTrue(all(candidates[name]["quality_status"] == "passed" for name in ("scanorama", "bbknn")))
        self.assertTrue(all(candidates[name]["quality_gates"]["label_purity_preserved"] for name in candidates))
        self.assertTrue(all(candidates[name]["quality_gates"]["unknown_labels_retained"] for name in candidates))

    def test_report_proves_no_label_leakage_and_preserves_unknowns_and_counts(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        self.assertEqual(report["fixture"]["unknown_cells"], 40)
        self.assertTrue(summary["labels_used_only_for_posthoc_evaluation"])
        self.assertTrue(summary["one_frozen_baseline_used"])
        self.assertTrue(summary["unknown_cells_retained"])
        self.assertTrue(summary["raw_counts_preserved"])
        self.assertTrue(summary["eligible_method_selected_without_umap_scoring"])

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
