import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.catalog import ModuleCatalogError, all_capabilities, load_module_capabilities
from biomed_workbench.modules.index import BUILTIN_ROOT
from tests.unit.test_module_contract import valid_manifest_payload


ROOT = Path(__file__).resolve().parents[2]
class RegistryLayoutTests(unittest.TestCase):
    def test_flat_builtin_modules_are_the_only_runtime_source(self):
        directories = sorted(path for path in BUILTIN_ROOT.iterdir() if path.is_dir())

        self.assertEqual(len(directories), 62)
        self.assertEqual(len(load_module_capabilities()), len(all_capabilities()))
        self.assertTrue(all((path / "module.json").is_file() for path in directories))

    def test_projection_rejects_duplicate_module_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = valid_manifest_payload()
            for parent in (root / "first" / payload["id"], root / "second" / payload["id"]):
                parent.mkdir(parents=True)
                (parent / "module.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ModuleCatalogError):
                load_module_capabilities(root)

    def test_central_registry_contains_no_builtin_capability_definitions(self):
        text = (ROOT / "biomed_workbench" / "catalog.py").read_text(encoding="utf-8")
        self.assertNotIn("def _register_builtins", text)
        self.assertNotIn("Capability(\n", text)
        self.assertNotIn("load_capabilities", text)


if __name__ == "__main__":
    unittest.main()
