import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = BUILTIN_ROOT / "single-cell-multimodal-integration"
REPORT = ROOT / "reports" / "single-cell-multimodal-integration-live-verification.json"


class SingleCellMultimodalIntegrationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))

    def test_report_is_bound_to_templates_registry_and_versions(self):
        row = self.manifest.compatibility_matrix[0]
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["module_id"], self.manifest.id)
        self.assertEqual(self.report["module_version"], self.manifest.version)
        self.assertEqual(self.report["compatibility_row_id"], row.id)
        self.assertTrue(evidence_scope_is_current(self.report, ModuleRegistry.discover(BUILTIN_ROOT)))
        for key, filename in {"wnn": "run_wnn.R", "mofaplus": "fit_mofaplus.py"}.items():
            template = MODULE_ROOT / "templates" / filename
            self.assertEqual(self.report["templates"][key]["sha256"], hashlib.sha256(template.read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(self.report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(self.report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in self.report["dependency_versions"].items()))

    def test_both_wnn_paths_recover_structure_and_retain_weights_and_graphs(self):
        evaluation = self.report["independent_evaluation"]
        self.assertGreaterEqual(evaluation["rna_atac_ari"], 0.95)
        self.assertGreaterEqual(evaluation["rna_adt_ari"], 0.95)
        for key in ("rna_atac_wnn", "rna_adt_wnn"):
            result = self.report["backend_summaries"][key]
            self.assertEqual(result["clusters"], 3)
            self.assertGreater(result["wknn_nonzero"], 0)
            self.assertGreater(result["wsnn_nonzero"], 0)
            self.assertAlmostEqual(result["RNA_weight"]["mean"] + result["secondary_weight"]["mean"], 1.0, places=3)
            self.assertGreater(result["RNA_weight"]["maximum"], result["RNA_weight"]["minimum"])
            self.assertGreater(result["secondary_weight"]["maximum"], result["secondary_weight"]["minimum"])

    def test_mofaplus_recovers_shared_factor_and_retains_view_evidence(self):
        evaluation = self.report["independent_evaluation"]
        result = self.report["backend_summaries"]["mofaplus"]
        self.assertGreaterEqual(evaluation["maximum_absolute_mofa_truth_correlation"], 0.95)
        self.assertEqual(result["weight_rows"], 150)
        self.assertEqual(result["variance_explained_rows"], 3)
        self.assertEqual(set(result["factor_variance"]), {f"Factor{i}" for i in range(1, 7)})

    def test_execution_preservation_reload_and_posthoc_evaluation_are_explicit(self):
        summary = self.report["scientific_summary"]
        for key in (
            "rna_atac_wnn_executed", "rna_adt_wnn_executed", "cell_specific_modality_weights_retained",
            "wknn_wsnn_neighbor_umap_and_clusters_retained", "mofaplus_three_view_model_converged",
            "mofaplus_factors_weights_and_variance_retained", "planted_shared_factor_recovered",
            "paired_cells_and_source_counts_preserved", "outputs_reloaded", "evaluation_labels_posthoc_only",
            "no_environment_or_compute_infrastructure_managed",
        ):
            self.assertTrue(summary[key], key)

    def test_report_contains_no_machine_paths_or_credentials(self):
        serialized = REPORT.read_text(encoding="utf-8")
        self.assertNotRegex(serialized, r"/(?:Users|private|home)/")
        self.assertNotIn("file://", serialized)
        self.assertIsNone(re.search(r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", serialized, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
