import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import build_compatibility_catalog, build_index, write_generated_indexes
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"


class ModuleIndexTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry.discover(BUILTIN_ROOT)

    def test_index_is_deterministic_and_contains_scientific_search_fields(self):
        first = build_index(self.registry)
        second = build_index(self.registry)

        self.assertEqual(first, second)
        self.assertEqual(first["module_count"], 62)
        self.assertEqual(first["registry_digest"], self.registry.digest)
        self.assertTrue(first["modules"][0]["intents"])
        self.assertTrue(first["modules"][0]["questions"])
        self.assertTrue(first["modules"][0]["input_artifacts"])
        self.assertIn("compatibility_matrix", first["modules"][0])

    def test_compatibility_catalog_preserves_v02_surface(self):
        catalog = build_compatibility_catalog(self.registry)
        ids = [row["id"] for row in catalog["entries"]]

        self.assertEqual(catalog["entry_count"], 62)
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(
            set(catalog["entries"][0]),
            {"id", "workflow", "kind", "title", "description", "entrypoint", "input_schema", "requirements", "access", "mutability"},
        )

    def test_generated_files_are_stable_across_rebuilds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module_index = root / "index.json"
            catalog = root / "catalog.json"

            write_generated_indexes(self.registry, module_index, catalog)
            first = (module_index.read_bytes(), catalog.read_bytes())
            write_generated_indexes(self.registry, module_index, catalog)
            second = (module_index.read_bytes(), catalog.read_bytes())

        self.assertEqual(first, second)
        self.assertEqual(json.loads(first[0])["module_count"], 62)


if __name__ == "__main__":
    unittest.main()
