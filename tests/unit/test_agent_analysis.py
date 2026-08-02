import unittest

from biomed_workbench.modules.contract import parse_manifest
from biomed_workbench.modules.registry import ModuleRegistry
from tests.unit.test_module_contract import agent_manifest_payload


class AgentAnalysisTests(unittest.TestCase):
    def test_registry_emits_no_edit_parameterized_plan_without_claiming_execution(self):
        manifest = parse_manifest(agent_manifest_payload())
        entrypoint = ModuleRegistry((manifest,), "fixture").resolve_entrypoint(manifest.id)

        output = entrypoint(rows=[{"sample": "S1"}])

        self.assertEqual(output["handoff_type"], "packaged_parameterized_project_analysis")
        self.assertEqual(output["module"], {"id": "fixture-analysis", "version": "1.0.0"})
        self.assertTrue(output["execution_policy"]["observed_execution_required"])
        self.assertTrue(output["execution_policy"]["planned_output_is_not_evidence"])
        self.assertTrue(output["execution_policy"]["use_packaged_parameterized_templates"])
        self.assertFalse(output["execution_policy"]["manual_code_editing_required"])
        self.assertFalse(output["execution_policy"]["generate_project_specific_code"])
        self.assertFalse(output["execution_policy"]["manage_environment_or_compute_infrastructure"])
        self.assertEqual(output["request_fields"], ["rows"])


if __name__ == "__main__":
    unittest.main()
