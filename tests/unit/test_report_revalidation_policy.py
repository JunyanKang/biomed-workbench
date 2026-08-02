import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.evidence_scope import module_evidence_scope
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from tools.assess_report_revalidation import ROOT, assess, sha256


class ReportRevalidationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        self.module_id = "bulk-ribosome-profiling"
        self.implementation = ROOT / "biomed_workbench/implementations/nfcore.py"

    def report(self, root: Path, *, digest: str, scope: dict) -> Path:
        path = root / "report.json"
        path.write_text(json.dumps({
            "passed": True,
            "module_id": self.module_id,
            "implementation": {
                "path": "biomed_workbench/implementations/nfcore.py",
                "sha256": digest,
            },
            "evidence_scope": scope,
        }))
        return path

    def test_current_implementation_and_scope_reuse_without_recompute(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.report(
                Path(temporary),
                digest=sha256(self.implementation),
                scope=module_evidence_scope(self.registry, [self.module_id]).to_dict(),
            )
            self.assertEqual(assess(path, self.registry)["decision"], "reuse_without_recomputation")

    def test_implementation_change_requires_scientific_rerun(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.report(
                Path(temporary),
                digest="0" * 64,
                scope=module_evidence_scope(self.registry, [self.module_id]).to_dict(),
            )
            self.assertEqual(assess(path, self.registry)["decision"], "scientific_rerun_required")

    def test_scope_only_change_requires_metadata_review_not_rerun(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.report(Path(temporary), digest=sha256(self.implementation), scope={
                "schema_version": 1,
                "module_ids": [self.module_id],
                "module_slice_digest": "0" * 64,
            })
            self.assertEqual(assess(path, self.registry)["decision"], "metadata_scope_review_required")


if __name__ == "__main__":
    unittest.main()
