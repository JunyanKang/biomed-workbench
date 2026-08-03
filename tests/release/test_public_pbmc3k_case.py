import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-pbmc3k-foundation.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-foundation-workflow"
)


class PublicPBMC3KCaseReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_public_source_module_and_template(self):
        report = self.report

        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(
            report["source"]["sha256"],
            "847d6ebd9a1ec9a768f2be7e40ca42cbfe75ebeb6d76a4c24167041699dc28b5",
        )
        self.assertEqual(report["source"]["documented_shape"], [2700, 32738])
        assert_evidence_scope_current(self, report)
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "templates" / "scanpy_foundation.py").read_bytes()
            ).hexdigest(),
        )

    def test_execution_preserves_counts_accounts_for_cells_and_reloads(self):
        execution = self.report["execution"]

        self.assertEqual(execution["input_cells"], 2700)
        self.assertEqual(
            execution["retained_cells"] + execution["excluded_cells"],
            execution["input_cells"],
        )
        self.assertGreater(execution["retained_cells"], 2000)
        self.assertGreater(execution["retained_features"], 10000)
        self.assertTrue(
            all(
                value
                for key, value in execution["reload_validation"].items()
                if key != "ephemeral_output_sha256"
            )
        )
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_does_not_overclaim_filtered_single_donor_data(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()

        self.assertEqual(
            self.report["methods_not_run"],
            {
                "ambient_rna": "not-run",
                "doublet": "not-run",
                "empty_droplet": "not-run",
            },
        )
        for phrase in (
            "filtered matrix",
            "one healthy donor",
            "cannot support donor-aware condition inference",
            "not universal defaults",
        ):
            self.assertIn(phrase, boundaries)

    def test_public_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for forbidden in ("/Users/", "/private/", "/var/folders/", "ACCESS_TOKEN=", "SECRET="):
            self.assertNotIn(forbidden, serialized)
        self.assertIsNone(
            re.search(
                r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}",
                serialized,
                re.IGNORECASE,
            )
        )


if __name__ == "__main__":
    unittest.main()
