import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.public_execution import PublicExecutionError, execute_public_module
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis


class PublicExecutionStateTests(unittest.TestCase):
    def test_single_module_entry_cannot_bypass_upstream_review_contract(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        module_ids = (
            "flow-cytometry-summary",
            "cell-migration-metrics",
            "gene-ortholog-evidence",
            "flow-immunophenotype-summary",
        )
        with tempfile.TemporaryDirectory() as temporary:
            for module_id in module_ids:
                manifest = registry.get(module_id)
                bindings = {
                    "project_context": project_context().to_dict(),
                    "hypotheses": [hypothesis().to_dict()],
                    "artifacts": {port.name: {} for port in manifest.input_artifacts},
                }
                with self.subTest(module_id=module_id), self.assertRaises(PublicExecutionError) as raised:
                    execute_public_module(
                        module_id,
                        {},
                        project_root=Path(temporary),
                        artifact_bindings=bindings,
                        compatibility_row_id=manifest.compatibility_matrix[0].id,
                    )
                self.assertEqual(raised.exception.code, "UPSTREAM_REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
