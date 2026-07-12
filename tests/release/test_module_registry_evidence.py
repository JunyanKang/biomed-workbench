import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "module-registry-verification.json"
DOMAINS = {"evidence", "omics", "molecular_design", "imaging", "clinical", "wetlab", "publication"}


class ModuleRegistryEvidenceTests(unittest.TestCase):
    def test_source_and_installed_registries_have_identical_verified_indexes(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        source = report["source_checkout"]
        installed = report["installed_cache"]

        self.assertTrue(report["passed"])
        self.assertEqual(source["module_count"], 52)
        self.assertEqual(installed["module_count"], 52)
        self.assertEqual(source["registry_digest"], source["index_digest"])
        self.assertEqual(installed["registry_digest"], installed["index_digest"])
        self.assertEqual(source["registry_digest"], installed["registry_digest"])
        self.assertTrue(source["dynamic_fixture_discovery"])
        self.assertEqual(source["skill_count"], 1)
        self.assertEqual(installed["skill_count"], 1)
        self.assertTrue(installed["cache_snapshot_isolated"])
        self.assertTrue(installed["new_task_required"])

    def test_every_domain_routes_and_executes_from_installed_cache(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        installed = report["installed_cache"]

        self.assertEqual(set(installed["routed_modules"]), DOMAINS)
        self.assertEqual(set(installed["executed_modules"]), DOMAINS)
        self.assertTrue(all(installed["routed_modules"].values()))
        self.assertTrue(all(installed["executed_modules"].values()))

    def test_compatibility_evidence_counts_are_complete(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))

        self.assertEqual(
            report["compatibility_evidence"],
            {
                "tool_requirements": 13,
                "dependency_requirements": 60,
                "dependency_probes": 60,
                "structured_version_differences": 22,
                "input_format_contracts": 53,
                "output_format_contracts": 52,
                "compatibility_rows": 52,
                "regression_evidence_bindings": 52,
                "end_to_end_evidence_bindings": 52,
            },
        )
        self.assertEqual(report["credentials"], ["NCBI_API_KEY"])

    def test_report_contains_no_machine_path_or_secret(self):
        text = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/var/folders/", "nvapi-", "bf339"):
            self.assertNotIn(marker, text)

    def test_every_dependency_has_a_typed_probe_and_tool_differences_are_structured(self):
        modules = ModuleRegistry.discover(BUILTIN_ROOT).all()
        dependencies = [item for module in modules for item in module.dependencies]
        differences = [item for module in modules for tool in module.tool_requirements for item in tool.version_differences]

        self.assertEqual(len(dependencies), 60)
        self.assertTrue(all(item.identity and item.version_probe and item.version_pattern for item in dependencies))
        self.assertEqual({item.version_probe_kind for item in dependencies}, {"python_callable", "command"})
        self.assertEqual(len(differences), 22)
        self.assertTrue(all(item.category and item.compatibility_effect and item.required_action and item.source.startswith("https://") for item in differences))


if __name__ == "__main__":
    unittest.main()
