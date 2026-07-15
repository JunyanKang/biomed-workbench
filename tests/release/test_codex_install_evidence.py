import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]


class CodexInstallEvidenceTests(unittest.TestCase):
    def test_isolated_codex_install_completed_every_step(self):
        report = json.loads((ROOT / "reports" / "codex-install-verification.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        registry = ModuleRegistry.discover(BUILTIN_ROOT)

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
                "installed_cache_module_index",
                "installed_cache_routing",
                "installed_cache_execution",
                "installed_skill_metadata",
                "cache_snapshot_isolation",
                "new_task_reload_required",
            },
        )
        self.assertEqual(report["codex_cli_version"], "0.144.0-alpha.4")
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["installed_module_count"], len(registry.all()))
        self.assertEqual(report["installed_registry_digest"], registry.digest)
        self.assertEqual(report["installed_skill_count"], 1)
        self.assertRegex(report["installed_skill_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("data-profile", report["route_selected_module_ids"])
        self.assertEqual(report["executed_module_id"], "data-profile")
        self.assertEqual(report["executed_row_count"], 2)
        self.assertTrue(report["new_task_required"])
        self.assertEqual(report["credentials"], ["NCBI_API_KEY"])

    def test_install_report_is_path_and_secret_free(self):
        text = (ROOT / "reports" / "codex-install-verification.json").read_text(encoding="utf-8")

        self.assertNotIn("/Users/", text)
        self.assertNotIn("/private/", text)
        self.assertNotIn("/var/folders/", text)
        self.assertNotIn("nvapi-", text)
        self.assertNotIn("bf339", text)


if __name__ == "__main__":
    unittest.main()
