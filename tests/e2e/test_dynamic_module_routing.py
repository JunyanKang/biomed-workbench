import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.router import route
from tests.unit.test_module_contract import valid_manifest_payload
from tests.unit.test_module_registry import write_manifest


class DynamicModuleRoutingTests(unittest.TestCase):
    def test_router_contains_no_module_specific_intent_table(self):
        source = (Path(__file__).resolve().parents[2] / "biomed_workbench" / "router.py").read_text(encoding="utf-8")

        self.assertNotIn("INTENT_BOOSTS", source)
        self.assertNotIn("WORKFLOW_KEYWORDS", source)
        self.assertNotIn('"crispr-design"', source)
        self.assertNotIn('"manuscript-audit"', source)

    def test_new_fixture_module_routes_from_manifest_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            payload["id"] = "neoenzyme-flux"
            payload["title"] = "Quantify neoenzyme flux"
            payload["intents"] = ["quantify neoenzyme flux", "量化新酶通量"]
            payload["questions"] = ["Does the new enzyme alter pathway flux?"]
            write_manifest(root, payload)
            registry = ModuleRegistry.discover(root)

            plan = route("请量化新酶通量", registry=registry)

        candidate = plan["steps"][0]["candidates"][0]
        self.assertEqual(candidate["id"], "neoenzyme-flux")
        self.assertTrue(candidate["selection_reasons"])

    def test_unknown_domain_is_discovered_without_router_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            payload["id"] = "ecology-flux"
            payload["domains"] = ["ecology"]
            payload["title"] = "Analyze ecosystem flux"
            payload["intents"] = ["ecosystem flux", "生态系统通量"]
            payload["questions"] = ["How does ecosystem flux change?"]
            write_manifest(root, payload)

            plan = route("分析生态系统通量", registry=ModuleRegistry.discover(root))

        self.assertEqual(plan["matched_workflows"], ["ecology"])
        self.assertEqual(plan["steps"][0]["candidates"][0]["id"], "ecology-flux")


if __name__ == "__main__":
    unittest.main()
