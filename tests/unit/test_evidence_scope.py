import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.evidence_scope import (
    evidence_scope_is_current,
    module_evidence_scope,
)
from biomed_workbench.modules.registry import ModuleRegistry
from tests.unit.test_module_contract import valid_manifest_payload


def write_module(root: Path, payload: dict[str, object], template_text: str = "") -> None:
    path = root / payload["id"]
    path.mkdir()
    (path / "module.json").write_text(json.dumps(payload), encoding="utf-8")
    if template_text:
        template = path / "templates" / "run.py"
        template.parent.mkdir()
        template.write_text(template_text, encoding="utf-8")


class EvidenceScopeTests(unittest.TestCase):
    def test_unrelated_module_addition_does_not_invalidate_scoped_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = valid_manifest_payload()
            first["id"] = "first-analysis"
            write_module(root, first)
            registry = ModuleRegistry.discover(root)
            report = {
                "module_id": "first-analysis",
                "evidence_scope": module_evidence_scope(
                    registry, ["first-analysis"], module_root=root
                ).to_dict(),
            }

            second = valid_manifest_payload()
            second["id"] = "second-analysis"
            write_module(root, second)
            expanded = ModuleRegistry.discover(root)

            self.assertNotEqual(registry.digest, expanded.digest)
            self.assertTrue(
                evidence_scope_is_current(report, expanded, module_root=root)
            )

    def test_manifest_change_invalidates_only_the_affected_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            payload["id"] = "first-analysis"
            write_module(root, payload)
            registry = ModuleRegistry.discover(root)
            report = {
                "module_id": "first-analysis",
                "evidence_scope": module_evidence_scope(
                    registry, ["first-analysis"], module_root=root
                ).to_dict(),
            }
            payload["version"] = "1.1.0"
            payload["compatibility_matrix"][0]["module_version"] = "1.1.0"
            (root / "first-analysis" / "module.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            self.assertFalse(
                evidence_scope_is_current(
                    report, ModuleRegistry.discover(root), module_root=root
                )
            )


if __name__ == "__main__":
    unittest.main()
