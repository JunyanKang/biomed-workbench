import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from tools.rebind_live_evidence_registry import rebind


class RebindLiveEvidenceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        self.manifest = self.registry.get("image-chroma-key-remove")

    def _write(self, root: Path, **overrides: object) -> Path:
        report = {
            "passed": True,
            "module_id": self.manifest.id,
            "module_version": self.manifest.version,
            "compatibility_row_id": self.manifest.compatibility_matrix[0].id,
            "registry_digest": "0" * 64,
            **overrides,
        }
        path = root / "live.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_rebinds_only_the_registry_digest_for_current_module_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._write(Path(temporary), scientific_summary={"passed": True})
            self.assertTrue(rebind(path, self.registry))
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["registry_digest"], self.registry.digest)
            self.assertEqual(report["scientific_summary"], {"passed": True})
            self.assertFalse(rebind(path, self.registry))

    def test_rejects_stale_module_version_or_compatibility_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "module version is stale"):
                rebind(self._write(root, module_version="0.0.0"), self.registry)
            with self.assertRaisesRegex(RuntimeError, "compatibility row is stale"):
                rebind(self._write(root, compatibility_row_id="retired-row"), self.registry)


if __name__ == "__main__":
    unittest.main()
