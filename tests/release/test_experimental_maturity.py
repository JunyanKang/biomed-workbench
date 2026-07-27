import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from tools.build_experimental_maturity_report import build


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "experimental-module-maturity.json"


class ExperimentalMaturityReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_checked_report_is_deterministic(self):
        self.assertEqual(self.report, build())

    def test_every_experimental_module_has_foundational_execution_evidence(self):
        report = self.report
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        expected_count = sum(1 for module in registry.all() if module.maturity == "experimental")
        self.assertTrue(report["passed"])
        self.assertEqual(report["experimental_module_count"], expected_count)
        for key in (
            "contract_passed",
            "template_passed",
            "compatibility_passed",
            "representative_execution_passed",
        ):
            self.assertEqual(report[key], report["experimental_module_count"])

    def test_public_data_gaps_are_explicit_and_not_promoted_by_fixture_evidence(self):
        report = self.report
        self.assertEqual(
            report["public_data_accepted"] + report["public_data_gap_count"],
            report["experimental_module_count"],
        )
        for record in report["records"]:
            if record["evidence"]["live_public_data"]:
                self.assertTrue(record["public_case_ids"])
                self.assertNotIn("stable_public_dataset_acceptance", record["missing_evidence"])
            else:
                self.assertFalse(record["public_case_ids"])
                self.assertIn("stable_public_dataset_acceptance", record["missing_evidence"])
            self.assertFalse(record["evidence"]["project_validation"])


if __name__ == "__main__":
    unittest.main()
