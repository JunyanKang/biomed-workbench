import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry

ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-communication"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
REPORT = ROOT / "reports" / "single-cell-communication-live-verification.json"


class SingleCellCommunicationEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_manifest_registry_and_backends(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        compatibility_rows = {row.id: row for row in manifest.compatibility_matrix}

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], MODULE_ID)
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        self.assertEqual({row["id"] for row in report["compatibility_rows"]}, set(compatibility_rows))

        for key, filename in {"run_liana_cellphonedb": "run_liana_cellphonedb.py", "run_cellchat_nichenet": "run_cellchat_nichenet.R"}.items():
            self.assertEqual(report["templates"][key]["sha256"], hashlib.sha256((MODULE_ROOT / "templates" / filename).read_bytes()).hexdigest())

        # Both protocol profiles should report expected execution completion.
        self.assertTrue(report["execution"]["cellphonedb_completed"])
        self.assertTrue(report["execution"]["liana_completed"])
        self.assertTrue(report["execution"]["cellchat_completed"])
        self.assertTrue(report["execution"]["nichenet_completed"])

        self.assertIn("cellphonedb-statistical", report["python_backends"]["methods"])
        self.assertIn("liana-rank-aggregate", report["python_backends"]["methods"])
        self.assertIn("cellchat", report["r_backends"]["methods"])
        self.assertIn("cellchat", report["r_backends"]["methods"])
        self.assertIn("nichenet", report["r_backends"]["methods"])

    def test_communication_versions_and_compatibility_boundaries(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        versions = report["versions"]
        self.assertGreaterEqual(int(versions["python"].split(".")[0]), 3)

        for row in manifest.compatibility_matrix:
            for name, rules in row.tool_versions.items():
                reported_version = versions.get(name)
                if reported_version is None and name in {"cellchat", "liana", "cellphonedb", "nichenetr"}:
                    # row-specific packages are only available via lowercase/legacy keys.
                    if name == "cellchat":
                        reported_version = versions.get("cellchat") or versions.get("CellChat")
                    elif name == "liana":
                        reported_version = versions.get("liana")
                    elif name == "cellphonedb":
                        reported_version = versions.get("cellphonedb")
                    elif name == "nichenetr":
                        reported_version = versions.get("nichenetr")
                if reported_version is None:
                    continue
                self.assertTrue(version_is_allowed(reported_version, rules), f"{MODULE_ID}:{name}")

    def test_report_is_clean_of_path_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/private/", text)
        self.assertNotIn("file://", text)
        self.assertIsNone(re.search(r"(?:api[_-]?key|access[_-]?token|secret)[\\\"' ]*[:=]", text, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
