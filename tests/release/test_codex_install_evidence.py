import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CodexInstallEvidenceTests(unittest.TestCase):
    def test_isolated_codex_install_completed_every_step(self):
        report = json.loads((ROOT / "reports" / "codex-install-verification.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

        self.assertTrue(report["passed"])
        self.assertTrue(report["isolated_home"])
        self.assertEqual(report["plugin"], manifest["name"])
        self.assertEqual(report["version"], manifest["version"])
        self.assertTrue(all(check["passed"] for check in report["checks"]))
        self.assertEqual(
            {check["operation"] for check in report["checks"]},
            {
                "marketplace_add",
                "plugin_list_discovery",
                "plugin_add",
                "manifest_version_resolution",
                "installed_cache_routing",
                "installed_cache_execution",
                "installed_skill_metadata",
            },
        )


if __name__ == "__main__":
    unittest.main()
