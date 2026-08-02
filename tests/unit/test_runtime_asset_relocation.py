import hashlib
import unittest
from pathlib import Path

from tools.reissue_runtime_asset_relocation import RELOCATIONS, ROOT


class RuntimeAssetRelocationTests(unittest.TestCase):
    def test_current_assets_match_declared_checksums(self):
        for spec in RELOCATIONS.values():
            for asset in spec["assets"]:
                path = ROOT / asset["current_path"]
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["current_sha256"])

    def test_runtime_assets_are_not_scientific_templates(self):
        module_templates = ROOT / "biomed_workbench/modules/builtin/bulk-rbp-rna-binding/templates"
        self.assertFalse(any(path.name.startswith("Dockerfile") for path in module_templates.iterdir()))
        self.assertFalse(any(path.suffix == ".patch" for path in module_templates.iterdir()))

    def test_migrations_preserve_scientific_outputs(self):
        for spec in RELOCATIONS.values():
            for name in spec["reports"]:
                report = (ROOT / "reports" / name).read_text(encoding="utf-8")
                self.assertIn('"passed": true', report)


if __name__ == "__main__":
    unittest.main()
