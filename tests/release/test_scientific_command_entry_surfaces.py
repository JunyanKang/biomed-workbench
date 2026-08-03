import unittest
import re

from biomed_workbench.modules.execution_readiness import assess_execution_readiness
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


class ScientificCommandEntrySurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        cls.commands = tuple(module for module in cls.registry.all() if module.execution.kind == "command")

    def test_all_command_contracts_dry_bind_every_port_parameter_and_output(self):
        self.assertEqual(len(self.commands), 14)
        for module in self.commands:
            with self.subTest(module=module.id):
                command = module.execution.command
                self.assertIsNotNone(command)
                self.assertEqual({item.port for item in command.inputs}, {item.name for item in module.input_artifacts})
                self.assertEqual({item.port for item in command.outputs}, {item.name for item in module.output_artifacts})
                placeholders = {
                    match.group(1)
                    for argument in command.arguments
                    for match in re.finditer(r"\{parameter:([^}]+)\}", argument)
                }
                self.assertEqual(placeholders, set(command.parameter_names))
                for row in module.compatibility_matrix:
                    self.assertEqual(set(row.input_formats), {item.name for item in module.input_artifacts})
                    self.assertEqual(set(row.output_formats), {item.name for item in module.output_artifacts})

    def test_all_command_modules_expose_only_strict_cli_and_controller_execution(self):
        for module in self.commands:
            with self.subTest(module=module.id):
                readiness = assess_execution_readiness(BUILTIN_ROOT / module.id, module)
                self.assertEqual(readiness.entry_surface_reachability["cli"]["mode"], "strict-project-artifact-execution")
                self.assertTrue(readiness.entry_surface_reachability["stateful_controller"]["reachable"])
                self.assertEqual(readiness.entry_surface_reachability["mcp"]["mode"], "explicitly-unsupported")


if __name__ == "__main__":
    unittest.main()
