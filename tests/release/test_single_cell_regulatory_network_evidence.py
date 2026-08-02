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
MODULE_ROOT = BUILTIN_ROOT / "single-cell-regulatory-network"
REPORT = ROOT / "reports" / "single-cell-regulatory-network-live-verification.json"


class SingleCellRegulatoryNetworkEvidenceTests(unittest.TestCase):
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
        for key, filename in {"pyscenic": "run_pyscenic.py", "scenicplus": "score_scenicplus_eregulons.py"}.items():
            template = MODULE_ROOT / "templates" / filename
            self.assertEqual(self.report["templates"][key]["sha256"], hashlib.sha256(template.read_bytes()).hexdigest())
        self.assertEqual(set(self.report["tool_versions"]), set(row.tool_versions))
        self.assertTrue(all(version_is_allowed(self.report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(self.report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in self.report["dependency_versions"].items()))

    def test_pyscenic_recovers_motif_pruned_programs_and_activity(self):
        evaluation = self.report["independent_evaluation"]["pyscenic"]
        self.assertEqual(evaluation["planted_targets_recovered"], {"TF1": 10, "TF2": 10})
        self.assertTrue(all(value >= 0.3 for value in evaluation["activity_contrasts"].values()))
        result = self.report["backend_summaries"]["pyscenic"]
        self.assertEqual(result["regulons"], 2)
        self.assertEqual(result["auc_shape"], [120, 2])

    def test_scenicplus_recovers_paired_gene_and_region_programs(self):
        evaluation = self.report["independent_evaluation"]["scenicplus"]
        self.assertGreaterEqual(evaluation["minimum_gene_region_pearson"], 0.95)
        for pair in evaluation["activity_contrasts"].values():
            self.assertGreaterEqual(pair["gene"], 0.3)
            self.assertGreaterEqual(pair["region"], 0.3)
        result = self.report["backend_summaries"]["scenicplus"]
        self.assertEqual(result["gene_auc_shape"], [120, 2])
        self.assertEqual(result["region_auc_shape"], [120, 2])

    def test_execution_source_preservation_reload_and_claim_boundaries(self):
        summary = self.report["scientific_summary"]
        for key in (
            "grnboost2_executed", "cistarget_motif_pruning_executed", "regulons_constructed",
            "aucell_executed_for_every_cell", "scenicplus_gene_and_region_auc_executed",
            "planted_tf_target_programs_recovered", "paired_rna_atac_programs_recovered",
            "coexpression_motif_and_region_gene_evidence_separated", "resources_hashed",
            "paired_cells_and_source_inputs_preserved", "outputs_reloaded",
            "causal_claims_prohibited_without_independent_evidence",
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
