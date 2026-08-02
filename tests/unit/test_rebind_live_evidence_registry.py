import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
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

    def test_migrates_to_dependency_scope_without_rewriting_historical_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._write(Path(temporary), scientific_summary={"passed": True})
            self.assertTrue(rebind(path, self.registry))
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["registry_digest"], "0" * 64)
            self.assertTrue(evidence_scope_is_current(report, self.registry))
            self.assertEqual(report["scientific_summary"], {"passed": True})
            self.assertFalse(rebind(path, self.registry))

    def test_rejects_stale_module_version_or_compatibility_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "module version is stale"):
                rebind(self._write(root, module_version="0.0.0"), self.registry)
            with self.assertRaisesRegex(RuntimeError, "compatibility row is stale"):
                rebind(self._write(root, compatibility_row_id="retired-row"), self.registry)

    def test_rejects_stale_template_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._write(
                Path(temporary),
                module_id="single-cell-doublet-detection",
                module_version="1.1.0",
                compatibility_row_id="agent-protocol-1-scrublet-023-scdblfinder-1160",
                templates={"scrublet": {"name": "run_scrublet.py", "sha256": "0" * 64}},
            )
            with self.assertRaisesRegex(RuntimeError, "template evidence is stale"):
                rebind(path, self.registry)


if __name__ == "__main__":
    unittest.main()
