import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.evidence_scope import module_evidence_scope
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from tools.bind_report_evidence_scopes import bind


class BindReportEvidenceScopesTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        self.module_id = "data-profile"

    def _report(self, root: Path, payload: dict) -> Path:
        path = root / "report.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_current_registry_report_can_adopt_a_dependency_scope_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._report(
                Path(temporary),
                {
                    "passed": True,
                    "module_id": self.module_id,
                    "registry_digest": self.registry.digest,
                },
            )
            self.assertTrue(bind(path, self.registry))
            observed = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                observed["evidence_scope"],
                module_evidence_scope(self.registry, [self.module_id]).to_dict(),
            )
            self.assertFalse(bind(path, self.registry))

    def test_stale_dependency_scope_is_never_rebound(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._report(
                Path(temporary),
                {
                    "passed": True,
                    "module_id": self.module_id,
                    "registry_digest": self.registry.digest,
                    "evidence_scope": {
                        "schema_version": 1,
                        "module_ids": [self.module_id],
                        "module_slice_digest": "0" * 64,
                    },
                },
            )
            with self.assertRaisesRegex(RuntimeError, "requires fresh execution"):
                bind(path, self.registry)

    def test_old_global_digest_without_module_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._report(
                Path(temporary),
                {
                    "passed": True,
                    "module_id": self.module_id,
                    "registry_digest": "0" * 64,
                },
            )
            with self.assertRaisesRegex(RuntimeError, "cannot adopt"):
                bind(path, self.registry)


if __name__ == "__main__":
    unittest.main()
