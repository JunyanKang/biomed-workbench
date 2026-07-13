import copy
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.router import route
from tests.unit.test_module_contract import valid_manifest_payload
from tools.create_module import ModuleCreationError, create_module
from tools.validate_module import validate_module


def future_module_request():
    manifest = valid_manifest_payload()
    manifest.update(
        {
            "id": "future-table-profile",
            "title": "Profile future assay tables",
            "description": "Profile future assay tables with explicit structural and missingness quality controls.",
            "intents": ["profile future assay table", "检查未来实验数据表"],
            "questions": ["Does the future assay table satisfy its structural quality requirements?"],
        }
    )
    manifest["output_schema"] = {
        "type": "object",
        "properties": {
            "row_count": {"type": "integer"},
            "column_count": {"type": "integer"},
            "column_order": {"type": "array"},
            "columns": {"type": "object"},
        },
        "required": ["row_count", "column_count", "column_order", "columns"],
        "additionalProperties": False,
    }
    return {
        "manifest": manifest,
        "tests": [
            {
                "name": "profiles-two-assay-rows",
                "input": {"rows": [{"sample_id": "S1", "signal": 2.0}, {"sample_id": "S2", "signal": None}]},
                "expected_subset": {"row_count": 2, "column_count": 2},
            }
        ],
    }


class CreateModuleEndToEndTests(unittest.TestCase):
    def test_create_validate_discover_route_and_execute_without_builtin_changes(self):
        builtin_digest = ModuleRegistry.discover(BUILTIN_ROOT).digest
        with tempfile.TemporaryDirectory() as temporary:
            registry_root = Path(temporary) / "extensions"

            module_path = create_module(future_module_request(), registry_root)
            report = validate_module(module_path)
            registry = ModuleRegistry.discover(registry_root)
            plan = route("请检查未来实验数据表", registry=registry)
            output = registry.resolve_entrypoint("future-table-profile")(
                rows=[{"sample_id": "S1", "signal": 2.0}, {"sample_id": "S2", "signal": None}]
            )

            self.assertEqual(module_path.resolve(), (registry_root / "future-table-profile").resolve())
            self.assertTrue(report["valid"])
            self.assertEqual(report["executed_test_cases"], 1)
            self.assertEqual(registry.get("future-table-profile").version, "1.0.0")
            self.assertEqual(plan["steps"][0]["candidates"][0]["id"], "future-table-profile")
            self.assertEqual(output["row_count"], 2)
            self.assertEqual(
                {path.relative_to(module_path).as_posix() for path in module_path.rglob("*") if path.is_file()},
                {"module.json", "tests/cases.json", "templates/run_future_table_profile.py"},
            )
            self.assertEqual(registry.get("future-table-profile").code_templates[0].path, "templates/run_future_table_profile.py")

        self.assertEqual(ModuleRegistry.discover(BUILTIN_ROOT).digest, builtin_digest)

    def test_failed_creation_is_atomic_and_leaves_no_partial_directory(self):
        request = copy.deepcopy(future_module_request())
        request["manifest"]["kernel_compatibility"] = [">=9.0.0"]
        with tempfile.TemporaryDirectory() as temporary:
            registry_root = Path(temporary) / "extensions"

            with self.assertRaisesRegex(ModuleCreationError, "kernel"):
                create_module(request, registry_root)

            self.assertFalse((registry_root / "future-table-profile").exists())
            self.assertEqual(list(registry_root.glob(".*.creating-*")), [])

    def test_validator_rejects_a_symlinked_module_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module_path = create_module(future_module_request(), root / "real-registry")
            link = root / "linked-module"
            link.symlink_to(module_path, target_is_directory=True)

            report = validate_module(link)

        self.assertFalse(report["valid"])
        self.assertTrue(any("symbolic link" in error for error in report["errors"]))

    def test_creator_rejects_a_symlinked_registry_root_without_writing_through_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_registry = root / "real-registry"
            real_registry.mkdir()
            linked_registry = root / "linked-registry"
            linked_registry.symlink_to(real_registry, target_is_directory=True)

            with self.assertRaisesRegex(ModuleCreationError, "symbolic link"):
                create_module(future_module_request(), linked_registry)

            self.assertEqual(list(real_registry.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
