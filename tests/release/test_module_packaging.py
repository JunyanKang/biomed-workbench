import json
import subprocess
import sys
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT, MODULE_INDEX, build_index
from biomed_workbench.modules.registry import ModuleRegistry
from tools.validate_module import validate_module


ROOT = Path(__file__).resolve().parents[2]


class ModulePackagingTests(unittest.TestCase):
    def test_checked_module_index_exactly_matches_all_builtin_manifests(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)

        self.assertEqual(len(registry.all()), 56)
        self.assertEqual(json.loads(MODULE_INDEX.read_text(encoding="utf-8")), build_index(registry))

    def test_every_builtin_module_passes_strict_packaging_validation(self):
        reports = [validate_module(path.parent, require_tests=False) for path in sorted(BUILTIN_ROOT.glob("*/module.json"))]

        self.assertEqual(len(reports), 56)
        self.assertTrue(all(report["valid"] for report in reports))
        self.assertTrue(all(report["entrypoint_resolved"] for report in reports))
        self.assertTrue(all(report["compatibility_rows"] >= 1 for report in reports))
        self.assertTrue(all(report["dependency_evidence_complete"] for report in reports))
        self.assertTrue(all(report["format_evidence_complete"] for report in reports))
        self.assertTrue(all(report["compatibility_evidence_complete"] for report in reports))

    def test_release_validator_enforces_module_registry_and_no_central_intent_tables(self):
        source = (ROOT / "biomed_workbench" / "router.py").read_text(encoding="utf-8")
        self.assertNotIn("INTENT_BOOSTS", source)
        self.assertNotIn("WORKFLOW_KEYWORDS", source)

        result = subprocess.run(
            [sys.executable, "tools/validate_workbench.py", "--release"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("modules=56", result.stdout)
        self.assertIn("registry_digest=", result.stdout)


if __name__ == "__main__":
    unittest.main()
