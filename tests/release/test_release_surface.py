import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]


class IndependentModuleReleaseSurfaceTests(unittest.TestCase):
    def test_domain_owned_migration_surfaces_are_absent(self):
        self.assertFalse((ROOT / "biomed_workbench" / "capability_specs").exists())
        self.assertFalse((ROOT / "tools" / "add_capability.py").exists())

        catalog_source = (ROOT / "biomed_workbench" / "catalog.py").read_text(encoding="utf-8")
        for legacy_name in ("SPECIFICATION_ROOT", "_read_specification", "load_capabilities"):
            self.assertNotIn(legacy_name, catalog_source)

    def test_every_builtin_is_one_independent_flat_module_directory(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        directories = sorted(path for path in BUILTIN_ROOT.iterdir() if path.is_dir())

        self.assertEqual(len(directories), 48)
        self.assertEqual({path.name for path in directories}, {module.id for module in registry.all()})
        for path in directories:
            self.assertEqual({item.name for item in path.iterdir()}, {"module.json"})
            self.assertEqual(path.name, path.name.lower())
            self.assertNotIn(path.name, {"evidence", "omics", "molecular-design", "imaging", "clinical", "wetlab", "publication"})

    def test_single_skill_and_module_creator_are_the_only_extension_surface(self):
        skill_files = sorted((ROOT / "skills").glob("*/SKILL.md"))

        self.assertEqual([path.parent.name for path in skill_files], ["biomed-workbench"])
        self.assertTrue((ROOT / "tools" / "create_module.py").is_file())
        self.assertTrue((ROOT / "tools" / "validate_module.py").is_file())


if __name__ == "__main__":
    unittest.main()
