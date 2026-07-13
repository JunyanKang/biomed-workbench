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
        self.assertNotIn('"temporal-integrity-audit"', source)
        self.assertNotIn('"assertion-citation-coverage-audit"', source)
        self.assertIn("_select_ranked_modules", source)

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

    def test_exact_manifest_intent_suppresses_incidental_fuzzy_workflows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exact = valid_manifest_payload()
            exact["id"] = "contract-audit"
            exact["domains"] = ["evidence"]
            exact["title"] = "Audit research contracts"
            exact["intents"] = ["检查科研项目多份产物的一致性"]
            write_manifest(root, exact)
            fuzzy = valid_manifest_payload()
            fuzzy["id"] = "generic-data-check"
            fuzzy["domains"] = ["omics"]
            fuzzy["title"] = "Check scientific data"
            fuzzy["intents"] = ["检查科研数据"]
            write_manifest(root, fuzzy)

            plan = route("请检查科研项目多份产物的一致性", registry=ModuleRegistry.discover(root))

        self.assertEqual(plan["matched_workflows"], ["evidence"])
        self.assertEqual(plan["steps"][0]["candidates"][0]["id"], "contract-audit")

    def test_multi_domain_module_is_scheduled_once_without_a_central_special_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shared = valid_manifest_payload()
            shared["id"] = "shared-visual"
            shared["domains"] = ["imaging", "publication"]
            shared["title"] = "Create shared visual"
            shared["intents"] = ["create shared visual"]
            shared["questions"] = ["What shared visual should be created?"]
            write_manifest(root, shared)
            for identifier, domain in (("image-check", "imaging"), ("publication-check", "publication")):
                payload = valid_manifest_payload()
                payload["id"] = identifier
                payload["domains"] = [domain]
                payload["title"] = identifier.replace("-", " ")
                payload["intents"] = [identifier.replace("-", " ")]
                write_manifest(root, payload)

            plan = route("create shared visual for publication", registry=ModuleRegistry.discover(root))

        routed = [item["id"] for step in plan["steps"] for item in step["candidates"]]
        self.assertEqual(routed.count("shared-visual"), 1)
        self.assertIn("publication-check", routed)

    def test_artifact_contract_turns_independent_selection_into_serial_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            producer = valid_manifest_payload()
            producer["id"] = "neo-assay-preparation"
            producer["domains"] = ["evidence"]
            producer["title"] = "Prepare neo assay"
            producer["intents"] = ["prepare neo assay"]
            producer["output_artifacts"][0]["artifact_type"] = "neo_assay_result"
            write_manifest(root, producer)

            consumer = valid_manifest_payload()
            consumer["id"] = "neo-conclusion-review"
            consumer["domains"] = ["evidence"]
            consumer["title"] = "Review neo conclusion"
            consumer["intents"] = ["review neo conclusion"]
            consumer["input_artifacts"][0]["artifact_type"] = "neo_assay_result"
            write_manifest(root, consumer)

            plan = route(
                "prepare neo assay and review neo conclusion",
                registry=ModuleRegistry.discover(root),
            )

        self.assertEqual(plan["selected_module_ids"], ["neo-assay-preparation", "neo-conclusion-review"])
        self.assertEqual(plan["plan_type"], "serial")
        self.assertEqual(plan["steps"][0]["mode"], "serial")


if __name__ == "__main__":
    unittest.main()
