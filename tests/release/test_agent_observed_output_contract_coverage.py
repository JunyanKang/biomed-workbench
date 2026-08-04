import hashlib
import importlib
import unittest
from pathlib import Path

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
                    self.assertTrue(contract.container_reload_validator)
                    self.assertTrue(contract.semantic_validator)
                    module_name, _ = contract.semantic_validator.split(":", 1)
                    source = Path(importlib.import_module(module_name).__file__)
                    self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), contract.semantic_validator_sha256)
                    self.assertEqual(
                        {item.gate_id for item in contract.gate_evaluators},
                        set(contract.required_postflight_gate_ids),
                    )
                    self.assertIn("semantic-metadata", {item.role for item in contract.payloads if item.minimum > 0})


if __name__ == "__main__":
    unittest.main()
