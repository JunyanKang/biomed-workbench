import json
import unittest
from pathlib import Path

from biomed_workbench.modules.evidence_scope import (
    evidence_scope_is_current,
    report_module_ids,
)
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]


class ReportEvidenceScopeTests(unittest.TestCase):
    def test_every_module_specific_report_has_a_current_dependency_scope(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        failures = []
        checked = 0
        for path in sorted((ROOT / "reports").glob("*.json")):
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict) or not report_module_ids(report):
                continue
            checked += 1
            if not evidence_scope_is_current(report, registry):
                failures.append(path.name)
        self.assertGreaterEqual(checked, 1)
        self.assertEqual(failures, [])

    def test_metadata_only_scope_reissues_are_explicit_and_bounded(self):
        allowed = {
            "maturity",
            "description",
            "limitations",
            "module-registration",
            "additive-unexecuted-adapter",
            "additive-independently-validated-assay-arm",
            "independent-backend-change",
            "compatibility-policy",
            "application-lifecycle",
        }
        checked = 0
        for path in sorted((ROOT / "reports").glob("*.json")):
            report = json.loads(path.read_text(encoding="utf-8"))
            migration = report.get("evidence_scope_migration")
            if migration is None:
                continue
            checked += 1
            self.assertEqual(migration["schema_version"], 1, path.name)
            self.assertEqual(
                migration["migration_type"],
                "reviewed-metadata-only-scope-reissue",
                path.name,
            )
            self.assertEqual(migration["current_evidence_scope"], report["evidence_scope"], path.name)
            self.assertNotEqual(migration["prior_evidence_scope"], report["evidence_scope"], path.name)
            self.assertTrue(set(migration["changed_fields"]) <= allowed, path.name)
            self.assertGreaterEqual(len(migration["reason"]), 40, path.name)
            self.assertFalse(migration["scientific_outputs_recomputed"], path.name)
            self.assertEqual(len(migration["report_sha256_before_reissue"]), 64, path.name)
        self.assertGreaterEqual(checked, 1)


if __name__ == "__main__":
    unittest.main()
