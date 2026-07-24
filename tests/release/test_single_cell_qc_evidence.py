import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-qc"
REPORT = ROOT / "reports" / "single-cell-qc-live-verification.json"


class SingleCellQCEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_template_and_compatibility_row(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(
            report["templates"]["run_single_cell_qc"]["sha256"],
            hashlib.sha256((MODULE_ROOT / "templates" / "run_single_cell_qc.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))

    def test_report_contains_expected_qc_coverage_gates_and_outputs(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))

        self.assertTrue(report["execution"]["fixture_matched_output"])
        self.assertTrue(report["execution"]["output_contains_flags"])
        self.assertTrue(report["execution"]["output_thresholds_serialized"])
        self.assertEqual(report["execution"]["input_cells"], 1)
        self.assertEqual(report["execution"]["input_features"], 2)
        self.assertEqual(report["execution"]["output_flagged_cells"], 1)
        self.assertTrue(report["scientific_summary"]["descriptive_thresholds_retained"])
        self.assertTrue(report["scientific_summary"]["source_output_roundtrip_checked"])

    def test_report_contains_no_private_path_or_credential_material(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/var/folders/", "API_KEY", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
