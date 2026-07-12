import copy
import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError
from tests.unit.test_module_contract import valid_manifest_payload


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "modules"


def write_manifest(root: Path, payload: dict) -> Path:
    directory = root / payload["id"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "module.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


class ModuleRegistryTests(unittest.TestCase):
    def test_registry_discovers_fixture_without_registration_code(self):
        registry = ModuleRegistry.discover(FIXTURE_ROOT)

        self.assertEqual([module.id for module in registry.all()], ["fixture-analysis"])
        self.assertIn("analyze fixture", registry.search_terms("fixture-analysis"))
        self.assertRegex(registry.digest, r"^[0-9a-f]{64}$")
        self.assertTrue(callable(registry.resolve_entrypoint("fixture-analysis")))

    def test_registry_rejects_duplicate_ids_across_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            write_manifest(root / "first", payload)
            duplicate = root / "second" / payload["id"] / "module.json"
            duplicate.parent.mkdir(parents=True)
            duplicate.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ModuleRegistryError, "duplicate module id"):
                ModuleRegistry.discover(root)

    def test_filesystem_addition_changes_registry_without_code_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = valid_manifest_payload()
            write_manifest(root, first)
            before = ModuleRegistry.discover(root)

            second = copy.deepcopy(first)
            second["id"] = "second-analysis"
            second["title"] = "Analyze a second fixture"
            second["intents"] = ["analyze second fixture"]
            second["questions"] = ["Does the second fixture contain a signal?"]
            write_manifest(root, second)
            after = ModuleRegistry.discover(root)

            self.assertEqual([module.id for module in before.all()], ["fixture-analysis"])
            self.assertEqual([module.id for module in after.all()], ["fixture-analysis", "second-analysis"])
            self.assertNotEqual(before.digest, after.digest)

    def test_registry_validates_alternative_and_complement_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            payload["alternatives"] = ["missing-analysis"]
            write_manifest(root, payload)

            with self.assertRaisesRegex(ModuleRegistryError, "unknown alternative"):
                ModuleRegistry.discover(root)

    def test_registry_rejects_directory_and_manifest_id_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "wrong-directory" / "module.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(valid_manifest_payload()), encoding="utf-8")

            with self.assertRaisesRegex(ModuleRegistryError, "directory must match"):
                ModuleRegistry.discover(root)

    def test_registry_reports_safe_manifest_and_entrypoint_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            payload["entrypoint"] = "missing.module:call"
            write_manifest(root, payload)
            registry = ModuleRegistry.discover(root)

            with self.assertRaisesRegex(ModuleRegistryError, "entrypoint cannot be resolved"):
                registry.resolve_entrypoint("fixture-analysis")
            with self.assertRaisesRegex(ModuleRegistryError, "unknown module"):
                registry.get("not-installed")


if __name__ == "__main__":
    unittest.main()
