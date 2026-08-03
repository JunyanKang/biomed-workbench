import json
import unittest
from pathlib import Path

from biomed_workbench.research_plan import compile_research_plan
from biomed_workbench.router import route


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "tests" / "fixtures" / "routing" / "objective-gold.json"


class ObjectiveRoutingGoldTests(unittest.TestCase):
    def test_bilingual_positive_negative_gold_and_plan_projection(self):
        fixture = json.loads(GOLD.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema_version"], 1)
        self.assertGreaterEqual(len(fixture["cases"]), 5)
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                routed = route(case["query"], per_workflow=case["per_workflow"])
                planned = compile_research_plan(case["query"], per_workflow=case["per_workflow"])
                selected = routed["selected_module_ids"]
                for module_id in case["required_module_ids"]:
                    self.assertIn(module_id, selected)
                for module_id in case["forbidden_module_ids"]:
                    self.assertNotIn(module_id, selected)
                self.assertEqual(routed["plan_type"], case["expected_plan_type"])

                graph = routed["objective_graph"]
                self.assertEqual(planned["selected_module_ids"], selected)
                self.assertEqual(planned["plan_type"], graph["plan_type"])
                self.assertEqual(planned["execution_layers"], graph["execution_layers"])
                self.assertEqual(
                    {row["id"]: row["depends_on"] for row in planned["modules"]},
                    graph["dependencies"],
                )


if __name__ == "__main__":
    unittest.main()
