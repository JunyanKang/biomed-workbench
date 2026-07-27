import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-qc"
REPORT = ROOT / "reports" / "single-cell-qc-live-verification.json"


class TestSingleCellQCEvidence(unittest.TestCase):
    def test_single_cell_qc_evidence_binding_and_runtime_constraints(self):
        module = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        row = module.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["module_version"], module.version)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        expected_template = (MODULE_ROOT / "templates" / "run_single_cell_qc.py").read_bytes()
        self.assertEqual(
            report["templates"]["single_cell_qc"]["sha256"],
            hashlib.sha256(expected_template).hexdigest(),
        )
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(
            all(
                version_is_allowed(value, row.dependency_versions[name])
                for name, value in report["dependency_versions"].items()
            )
        )
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertTrue(report["scientific_summary"]["qc_thresholds_applied"])
        self.assertTrue(report["scientific_summary"]["cell_level_qc_flags_retained"])
        self.assertTrue(report["execution"]["template_completed"])
        self.assertEqual(report["fixture"]["cells"], report["execution"]["result_cells_returned"])


if __name__ == "__main__":
    unittest.main()
