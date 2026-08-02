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
MODULE_ROOT = BUILTIN_ROOT / "single-cell-spatial-analysis"
REPORT = ROOT / "reports" / "single-cell-spatial-analysis-live-verification.json"


class SingleCellSpatialAnalysisEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))

    def test_report_is_bound_to_template_registry_and_versions(self):
        row = self.manifest.compatibility_matrix[0]
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["module_id"], self.manifest.id)
        self.assertEqual(self.report["module_version"], self.manifest.version)
        self.assertEqual(self.report["compatibility_row_id"], row.id)
        self.assertTrue(evidence_scope_is_current(self.report, ModuleRegistry.discover(BUILTIN_ROOT)))
        self.assertEqual(self.report["templates"]["spatial"]["sha256"], hashlib.sha256((MODULE_ROOT / "templates" / "run_spatial_analysis.py").read_bytes()).hexdigest())
        self.assertEqual(set(self.report["tool_versions"]), set(row.tool_versions))
        self.assertTrue(all(version_is_allowed(self.report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(self.report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in self.report["dependency_versions"].items()))

    def test_both_input_formats_preserve_spatialdata_provenance_and_counts(self):
        h5ad = self.report["backend_summaries"]["h5ad"]
        spatialdata = self.report["backend_summaries"]["spatialdata"]
        self.assertEqual(h5ad["input"]["kind"], "h5ad")
        self.assertEqual(spatialdata["input"]["kind"], "spatialdata-zarr")
        self.assertEqual(spatialdata["input"]["spatial_elements"]["images"], ["histology"])
        self.assertEqual(spatialdata["input"]["spatial_elements"]["tables"], ["spots"])
        self.assertEqual(h5ad["input"]["source_count_digest"], spatialdata["input"]["source_count_digest"])
        self.assertEqual(h5ad["results"]["cross_sample_edges"], 0)
        self.assertEqual(spatialdata["results"]["cross_sample_edges"], 0)

    def test_spatial_statistics_recover_replicated_zones_and_reject_controls(self):
        for evaluation in self.report["independent_evaluation"].values():
            self.assertGreaterEqual(evaluation["domain_ari"], 0.95)
            self.assertGreater(evaluation["neighborhood_diagonal_gap"], 10)
            self.assertGreater(evaluation["nearest_cooccurrence_diagonal_gap"], 1)
            self.assertEqual(evaluation["admitted_spatial_genes"], ["SVG_A", "SVG_B", "SVG_C"])
            self.assertEqual(evaluation["spatial_gene_support"], {"SVG_A": 2, "SVG_B": 2, "SVG_C": 2})

    def test_execution_replication_reload_and_inferential_boundaries(self):
        summary = self.report["scientific_summary"]
        for key in (
            "h5ad_and_spatialdata_zarr_executed", "spatialdata_image_and_table_provenance_retained",
            "sample_isolated_spatial_graph_executed", "zero_cross_sample_spatial_edges",
            "sample_restricted_neighborhood_permutations_executed", "sample_level_cooccurrence_executed",
            "global_and_sample_level_moran_executed", "multiplicity_and_sample_replication_gates_applied",
            "all_planted_spatial_genes_and_no_controls_admitted", "three_planted_domains_recovered_without_label_leakage",
            "source_counts_cells_genes_coordinates_and_elements_preserved", "outputs_reloaded",
            "spots_not_used_as_condition_replicates", "no_environment_or_compute_infrastructure_managed",
        ):
            self.assertTrue(summary[key], key)

    def test_report_contains_no_machine_paths_or_credentials(self):
        serialized = REPORT.read_text(encoding="utf-8")
        self.assertNotRegex(serialized, r"/(?:Users|private|home)/")
        self.assertNotIn("file://", serialized)
        self.assertIsNone(re.search(r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", serialized, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
