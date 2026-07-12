import json
import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.execution import execute_node
from tests.unit.orchestration.test_execution import environment, execution_node, execution_plan, execution_state


class ExecutionProvenanceContractTests(unittest.TestCase):
    def test_execution_provenance_is_complete_secret_free_and_path_free(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        node = execution_node()
        result = execute_node(execution_state(), execution_plan(node), node, registry, environment_provider=lambda _manifest: environment())
        serialized = json.dumps(result.to_dict(), sort_keys=True)

        self.assertEqual(result.provenance["module_id"], "data-profile")
        self.assertEqual(result.provenance["module_version"], "1.0.0")
        self.assertEqual(result.provenance["input_formats"], {"records": "inline-json@1"})
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("/private/", serialized)
        self.assertNotIn("NCBI_API_KEY", serialized)
        self.assertNotIn("rows", result.provenance)


if __name__ == "__main__":
    unittest.main()
