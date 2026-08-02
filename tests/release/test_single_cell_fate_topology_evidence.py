import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]


class SingleCellFateTopologyEvidenceTests(unittest.TestCase):
    def check_binding(self, module_id, report_name, templates):
        module_root = ROOT / "biomed_workbench" / "modules" / "builtin" / module_id
        report = json.loads((ROOT / "reports" / report_name).read_text())
        manifest = parse_manifest(json.loads((module_root / "module.json").read_text()))
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertTrue(evidence_scope_is_current(report, ModuleRegistry.discover(BUILTIN_ROOT)))
        self.assertEqual(report["module_id"], module_id); self.assertEqual(report["compatibility_row_id"], row.id)
        for key, filename in templates.items(): self.assertEqual(report["templates"][key]["sha256"], hashlib.sha256((module_root / "templates" / filename).read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))

    def test_reports_are_bound(self):
        self.check_binding("single-cell-fate-mapping", "single-cell-fate-mapping-live-verification.json", {"cellrank": "run_cellrank_fate.py"})
        self.check_binding("single-cell-trajectory-topology", "single-cell-trajectory-topology-live-verification.json", {"trajectory": "run_slingshot_monocle_tradeseq.R"})

    def test_fate_backends_and_topology_gene_tests_pass(self):
        fate = json.loads((ROOT / "reports" / "single-cell-fate-mapping-live-verification.json").read_text())
        topology = json.loads((ROOT / "reports" / "single-cell-trajectory-topology-live-verification.json").read_text())
        self.assertTrue(fate["scientific_summary"]["velocity_pseudotime_and_optimal_transport_kernels_executed"])
        self.assertTrue(fate["scientific_summary"]["velocity_connectivity_weight_recorded"])
        self.assertEqual(fate["backend_summaries"]["optimal_transport"]["terminal_own_fate"], {"A": 1.0, "B": 1.0})
        self.assertGreater(topology["results"]["slingshot_external_time_spearman"], 0.9)
        self.assertGreater(topology["results"]["monocle3_external_time_spearman"], 0.9)
        self.assertGreaterEqual(topology["results"]["association_branch_hits"], 18)
        self.assertGreaterEqual(topology["results"]["differential_end_branch_hits"], 18)
        self.assertTrue(topology["results"]["all_four_test_prefixes"])

    def test_reports_have_no_local_paths_or_credentials(self):
        text = (ROOT / "reports" / "single-cell-fate-mapping-live-verification.json").read_text() + (ROOT / "reports" / "single-cell-trajectory-topology-live-verification.json").read_text()
        self.assertNotIn("/Users/", text); self.assertNotIn("/private/", text); self.assertNotIn("file://", text); self.assertNotIn("ACCESS_TOKEN=", text)


if __name__ == "__main__": unittest.main()
