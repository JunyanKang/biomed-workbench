import re
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]


class ModuleManifestCoverageTests(unittest.TestCase):
    def test_only_explicit_typed_relations_are_revision_compatible(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        relations = {
            (manifest.id, relation.target_module_id)
            for manifest in registry.all()
            for relation in manifest.revision_alternatives
        }
        self.assertEqual(relations, {
            ("read-quality-fastqc", "read-quality-fastp"),
            ("read-quality-fastp", "read-quality-fastqc"),
        })
        ordinary_alternatives = {
            (manifest.id, alternative)
            for manifest in registry.all()
            for alternative in manifest.alternatives
        }
        self.assertGreater(len(ordinary_alternatives), len(relations))


def _sanitize(module_id: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]", "_", module_id)


def _module_contract_assertions(module_id: str):
    module_path = ROOT / "biomed_workbench" / "modules" / "builtin" / module_id / "module.json"

    def test(self: unittest.TestCase) -> None:
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get(module_id)
        self.assertEqual(manifest.id, module_id)
        self.assertEqual(module_path.name, "module.json")
        self.assertEqual(module_path.parent.name, module_id)
        self.assertGreaterEqual(len(manifest.compatibility_matrix), 1)
        for row in manifest.compatibility_matrix:
            self.assertEqual(row.module_version, manifest.version)
            self.assertTrue(row.id)
            self.assertGreaterEqual(len(row.regression_evidence_ids), 1)
            self.assertGreaterEqual(len(row.end_to_end_evidence_ids), 1)

    return test


for manifest in ModuleRegistry.discover(BUILTIN_ROOT).all():
    name = f"test_module_{_sanitize(manifest.id)}_contract"
    setattr(ModuleManifestCoverageTests, name, _module_contract_assertions(manifest.id))


if __name__ == "__main__":
    unittest.main()
