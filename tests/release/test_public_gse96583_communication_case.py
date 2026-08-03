import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-communication.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-communication"
)


class PublicGSE96583CommunicationCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["accession"], "GSE96583")
        self.assertEqual(report["module"]["version"], "1.1.0")
        assert_evidence_scope_current(self, report)
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (
                    MODULE_ROOT
                    / "templates"
                    / "run_liana_cellphonedb.py"
                ).read_bytes()
            ).hexdigest(),
        )

    def test_public_design_and_true_permutation_evidence_are_preserved(self):
        source = self.report["source"]["validation"]
        execution = self.report["execution"]
        self.assertEqual(source["selected_cells"], 5857)
        self.assertEqual(source["selected_genes"], 9471)
        self.assertEqual(source["donors"], 8)
        self.assertEqual(source["biological_samples"], 16)
        self.assertEqual(execution["observed_sample_runs"], 16)
        self.assertEqual(execution["method"], "liana-cellphonedb")
        self.assertEqual(execution["p_value_unique_count"], 101)
        self.assertEqual(execution["p_value_minimum"], 0.0)
        self.assertEqual(execution["p_value_maximum"], 1.0)

    def test_replicated_calls_require_independent_sample_significance(self):
        execution = self.report["execution"]
        self.assertEqual(execution["replicated_interactions"], 185)
        self.assertEqual(
            execution["replicated_by_condition"],
            {"ctrl": 87, "stim": 98},
        )
        self.assertGreaterEqual(
            execution["minimum_significant_sample_support"], 6
        )
        self.assertTrue(execution["source_artifacts_immutable"])
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "cells are never used as condition-level replicates",
            "conservatively floored at 1/(permutations+1)",
            "does not perform a formal between-condition interaction test",
            "does not establish physical contact",
        ):
            self.assertIn(phrase, boundaries)
        sanity = self.report["execution"]["posthoc_biological_sanity"]
        self.assertTrue(sanity["stimulated_cxcl10_cxcr3_observed"])
        self.assertFalse(sanity["used_for_threshold_selection"])
        self.assertFalse(sanity["used_as_quality_gate"])
        serialized = REPORT.read_text(encoding="utf-8")
        for forbidden in (
            "/Users/",
            "/private/",
            "/var/folders/",
            "ACCESS_TOKEN=",
            "SECRET=",
        ):
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
