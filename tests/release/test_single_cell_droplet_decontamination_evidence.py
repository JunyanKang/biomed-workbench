import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-droplet-decontamination"
REPORT = ROOT / "reports" / "single-cell-droplet-decontamination-live-verification.json"


class TestSingleCellDropletDecontaminationEvidence(unittest.TestCase):
    def test_single_cell_droplet_decontamination_evidence_binding_and_versions(self):
        module = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        row = module.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["module_id"], module.id)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        self.assertEqual(
            report["templates"]["cellbender"]["sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "run_cellbender.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["templates"]["r"]["sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "run_emptydrops_soupx.R").read_bytes()).hexdigest(),
        )
        self.assertTrue(
            all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items())
        )
        self.assertTrue(
            all(
                version_is_allowed(value, row.dependency_versions[name])
                for name, value in report["dependency_versions"].items()
            )
        )
        science = report["scientific_summary"]
        self.assertTrue(science["nonnegative_counts"])
        self.assertTrue(science["raw_counts_preserved"])
        self.assertTrue(science["methods_separated"])
        self.assertTrue(science["no_environment_or_compute_infrastructure_managed"])
        report_text = REPORT.read_text(encoding="utf-8")
        self.assertNotRegex(report_text, r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", re.IGNORECASE)
        self.assertNotIn("/Users/", report_text)


if __name__ == "__main__":
    unittest.main()
