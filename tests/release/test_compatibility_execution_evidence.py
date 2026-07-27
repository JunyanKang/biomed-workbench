import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from tools.capture_compatibility_evidence import capture


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "compatibility-execution-evidence.json"


def _first_difference(actual, expected, path="report"):
    if type(actual) is not type(expected):
        return f"{path}: type {type(actual).__name__} != {type(expected).__name__}"
    if isinstance(actual, dict):
        actual_keys = set(actual)
        expected_keys = set(expected)
        if actual_keys != expected_keys:
            return f"{path}: keys {sorted(actual_keys ^ expected_keys)} differ"
        for key in sorted(actual):
            difference = _first_difference(actual[key], expected[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(actual, list):
        if len(actual) != len(expected):
            return f"{path}: length {len(actual)} != {len(expected)}"
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
            difference = _first_difference(actual_item, expected_item, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if actual != expected:
        return f"{path}: {actual!r} != {expected!r}"
    return None


class CompatibilityExecutionEvidenceTests(unittest.TestCase):
    def test_every_compatibility_row_binds_passing_regression_and_e2e_evidence(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        expected = {
            (module.id, row.id, row.regression_evidence_ids[0], row.end_to_end_evidence_ids[0])
            for module in registry.all()
            for row in module.compatibility_matrix
        }
        observed = {
            (record["module_id"], record["row_id"], record["regression"]["id"], record["end_to_end"]["id"])
            for record in report["records"]
        }

        self.assertTrue(report["passed"])
        self.assertEqual(report["registry_digest"], registry.digest)
        self.assertEqual(report["regression_passed"], len(expected))
        self.assertEqual(report["end_to_end_passed"], len(expected))
        self.assertEqual(observed, expected)

    def test_report_is_reproducible_from_real_execution(self):
        actual = capture()
        expected = json.loads(REPORT.read_text(encoding="utf-8"))
        difference = _first_difference(actual, expected)
        self.assertIsNone(difference, difference)

    def test_report_contains_no_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "api_key=", "ACCESS_TOKEN="):
            self.assertNotIn(marker, serialized)

    def test_every_record_is_bound_to_current_project_implementation_bytes(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))

        self.assertTrue(all(len(record["implementation_sha256"]) == 64 for record in report["records"]))
        self.assertTrue(all(set(record["implementation_sha256"]) <= set("0123456789abcdef") for record in report["records"]))


if __name__ == "__main__":
    unittest.main()
