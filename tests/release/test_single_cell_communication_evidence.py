import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-communication"
REPORT = ROOT / "reports" / "single-cell-communication-live-verification.json"


class TestSingleCellCommunicationEvidence(unittest.TestCase):
    def test_single_cell_communication_evidence_covers_python_and_r_protocols(self):
        module = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], module.id)
        self.assertEqual(report["module_version"], module.version)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        self.assertEqual(
            report["templates"]["run_liana_cellphonedb"]["sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "run_liana_cellphonedb.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["templates"]["run_cellchat_nichenet"]["sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "run_cellchat_nichenet.R").read_bytes()).hexdigest(),
        )
        reported_row_ids = {row["id"] for row in report["compatibility_rows"]}
        manifest_row_ids = {row.id for row in module.compatibility_matrix}
        self.assertTrue(reported_row_ids <= manifest_row_ids)
        self.assertEqual(set(report["python_backends"]["methods"]), {"liana-cellphonedb", "cellphonedb-statistical"})
        self.assertEqual(set(report["r_backends"]["methods"]), {"cellchat", "nichenet"})
        self.assertTrue(report["scientific_summary"]["all_four_backends_executed"])
        self.assertTrue(report["scientific_summary"]["outputs_reloaded"])
        for name, value in report["tool_versions"].items():
            lowered = name.lower()
            allowed_rules = [
                row.tool_versions[row_name]
                for row in module.compatibility_matrix
                for row_name in row.tool_versions
                if row_name.lower() == lowered
            ]
            if not allowed_rules:
                continue
            self.assertTrue(
                any(version_is_allowed(value, rules) for rules in allowed_rules),
                f"{name} version {value} not in compatibility rules",
            )
        report_text = REPORT.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", report_text)
        self.assertNotIn("/private/", report_text)
        self.assertNotIn("file://", report_text)
        self.assertNotRegex(report_text, r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", re.IGNORECASE)


if __name__ == "__main__":
    unittest.main()
