import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from tools.bind_public_case_compatibility import bind, cited_rows


class PublicCaseCompatibilityBindingTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        self.citations = cited_rows(self.registry)

    def test_multivi_case_has_one_current_citing_row(self):
        matches = self.citations["pbmc-multiome-multivi-150-public-e2e-v1"]
        self.assertEqual(matches, [("single-cell-mosaic-integration", "1.0.0", "scvi15-scglue041-mosaic-v1")])

    def test_binding_is_metadata_only_and_idempotent(self):
        payload = {
            "passed": True,
            "case_id": "pbmc-multiome-multivi-150-public-e2e-v1",
            "module": {"id": "single-cell-mosaic-integration", "version": "1.0.0"},
            "execution": {"native_training": True},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "case.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(bind(path, self.registry, self.citations))
            migrated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(migrated["execution"], payload["execution"])
            self.assertFalse(migrated["compatibility_binding_migration"]["scientific_outputs_recomputed"])
            self.assertFalse(bind(path, self.registry, self.citations))


if __name__ == "__main__":
    unittest.main()
