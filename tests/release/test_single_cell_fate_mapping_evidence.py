import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-fate-mapping"
REPORT = ROOT / "reports" / "single-cell-fate-mapping-live-verification.json"


class TestSingleCellFateMappingEvidence(unittest.TestCase):
    def test_single_cell_fate_mapping_evidence_bound_and_executable(self):
        module = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        row = module.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], module.id)
        self.assertEqual(report["module_version"], module.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        self.assertEqual(
            report["templates"]["cellrank"]["sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "run_cellrank_fate.py").read_bytes()).hexdigest(),
        )
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))
        self.assertTrue(report["scientific_summary"]["velocity_pseudotime_and_optimal_transport_kernels_executed"])
        self.assertTrue(report["scientific_summary"]["velocity_connectivity_weight_recorded"])
        self.assertEqual(report["scientific_summary"]["declared_terminal_states_recovered"], True)


if __name__ == "__main__":
    unittest.main()
