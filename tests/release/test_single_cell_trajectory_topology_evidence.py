import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-trajectory-topology"
REPORT = ROOT / "reports" / "single-cell-trajectory-topology-live-verification.json"


class TestSingleCellTrajectoryTopologyEvidence(unittest.TestCase):
    def test_single_cell_trajectory_topology_evidence_bound_and_directionally_valid(self):
        module = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        row = module.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], module.id)
        self.assertEqual(report["module_version"], module.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        self.assertEqual(
            report["templates"]["trajectory"]["sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "run_slingshot_monocle_tradeseq.R").read_bytes()).hexdigest(),
        )
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))
        results = report["results"]
        self.assertGreater(results["slingshot_external_time_spearman"], 0.9)
        self.assertGreater(results["monocle3_external_time_spearman"], 0.9)
        self.assertGreaterEqual(results["association_branch_hits"], 18)
        self.assertGreaterEqual(results["differential_end_branch_hits"], 18)
        self.assertTrue(results["all_four_test_prefixes"])


if __name__ == "__main__":
    unittest.main()
