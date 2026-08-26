import json
import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.runner import run


class AgentHandoffSemanticsTests(unittest.TestCase):
    def test_every_agent_generated_module_stops_at_handoff_without_artifact_or_evidence(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        manifests = tuple(manifest for manifest in registry.all() if manifest.access == "agent_generated")
        self.assertTrue(manifests)
        self.assertIn("rna-processing-alternative-splicing", {manifest.id for manifest in manifests})
        for manifest in manifests:
            case_path = BUILTIN_ROOT / manifest.id / "tests" / "cases.json"
            cases = json.loads(case_path.read_text(encoding="utf-8"))["cases"]
            with self.subTest(module_id=manifest.id):
                result = run(manifest.id, cases[0]["input"])
                self.assertEqual(result.status, "awaiting_observed_execution")
                self.assertEqual(result.output["result_kind"], "execution_handoff")
                self.assertEqual(result.output["execution_state"], "prepared-not-run")
                self.assertTrue(result.output["execution_policy"]["planned_output_is_not_evidence"])
                self.assertEqual(result.artifacts, ())
                self.assertEqual(result.evidence, ())


if __name__ == "__main__":
    unittest.main()
