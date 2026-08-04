import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


class AgentObservedOutputContractCoverageTests(unittest.TestCase):
    def test_every_agent_workflow_has_port_complete_gate_bound_result_contracts(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        agent_modules = tuple(item for item in registry.all() if item.access == "agent_generated")
        self.assertEqual(len(agent_modules), 54)
        for manifest in agent_modules:
            with self.subTest(module=manifest.id):
                contracts = {item.port: item for item in manifest.observed_output_contracts}
                self.assertEqual(set(contracts), {item.name for item in manifest.output_artifacts})
                blocking = {item.id for item in manifest.quality_gates if item.blocks_interpretation}
                for contract in contracts.values():
                    self.assertTrue(blocking <= set(contract.required_postflight_gate_ids))
                    self.assertTrue(any(item.minimum > 0 for item in contract.payloads))
                    self.assertFalse(contract.content_schema.get("additionalProperties", True))
                    self.assertIsNotNone(contract.reload_validator)


if __name__ == "__main__":
    unittest.main()
