import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-zebrafish-cellrank.json"
UPSTREAM = ROOT / "reports" / "public-case-zebrafish-regvelo.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-fate-mapping"
)


class PublicZebrafishCellRankCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_upstream_public_evidence_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(
            report["case_id"],
            "zebrafish-regvelo-cellrank-fate-public-data-v1",
        )
        self.assertEqual(
            report["source"]["official_h5ad_sha256"],
            "eccab081c44cfe335b726aec8172bbcda072241b4f006f6420bb5d46d39611cb",
        )
        self.assertEqual(
            report["source"]["upstream_report_sha256"],
            hashlib.sha256(UPSTREAM.read_bytes()).hexdigest(),
        )
        self.assertEqual(report["module"]["id"], "single-cell-fate-mapping")
        self.assertEqual(report["module"]["version"], "1.1.0")
        assert_evidence_scope_current(self, report)
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "templates" / "run_cellrank_fate.py").read_bytes()
            ).hexdigest(),
        )

    def test_velocity_kernel_executes_with_exact_repeat_and_reload(self):
        report = self.report
        self.assertEqual(report["runtime"]["cellrank"], "2.3.2")
        self.assertEqual(report["runtime"]["moscot"], "0.5.1")
        self.assertEqual(report["source"]["validation"]["cells"], 697)
        self.assertEqual(report["source"]["validation"]["features"], 1008)
        self.assertEqual(
            report["source"]["validation"]["expression_semantics"],
            "log-normalized-continuous",
        )
        self.assertTrue(
            report["source"]["validation"]["velocity_finite_signed"]
        )
        execution = report["execution"]
        self.assertEqual(execution["independent_template_runs"], 3)
        self.assertEqual(execution["pure_velocity_runs"], 2)
        self.assertEqual(execution["velocity_connectivity_runs"], 1)
        self.assertTrue(execution["source_expression_preserved"])
        self.assertTrue(execution["outputs_reloaded"])
        self.assertEqual(execution["lineage_driver_rows"], 1008)
        self.assertTrue(
            all(
                item["exactly_equal"]
                and item["maximum_absolute_difference"] == 0
                for item in execution["deterministic_repeat"].values()
            )
        )

    def test_withheld_stage_and_connectivity_sensitivity_pass_frozen_gates(self):
        execution = self.report["execution"]
        direction = execution["withheld_stage_direction"]
        self.assertFalse(direction["stage_used_for_fitting"])
        self.assertGreater(direction["expected_deltas"]["pure_velocity"], 0)
        self.assertGreater(
            direction["expected_deltas"]["velocity_connectivity"],
            0,
        )
        sensitivity = execution["connectivity_sensitivity"]
        self.assertEqual(sensitivity["blended_connectivity_weight"], 0.2)
        self.assertGreaterEqual(
            sensitivity["flattened_fate_pearson"],
            sensitivity["thresholds"]["minimum_flattened_fate_pearson"],
        )
        self.assertLessEqual(
            sensitivity["maximum_absolute_fate_difference"],
            sensitivity["thresholds"][
                "maximum_absolute_fate_difference"
            ],
        )
        self.assertGreater(sensitivity["maximum_fate_assignment_agreement"], 0.95)
        self.assertEqual(
            set(execution["terminal_state_consistency"].values()),
            {1.0},
        )
        self.assertEqual(
            self.report["quality_gates"]["terminal_state_consistency"],
            "pass-not-independent",
        )

    def test_case_preserves_claim_boundaries_and_contains_no_private_material(self):
        self.assertEqual(
            set(self.report["methods_not_run"].values()),
            {"not-run"},
        )
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "does not establish portability",
            "annotation-defined rather than discovered independently",
            "not independent biological validation",
            "hard-versus-soft fate robustness is not claimed",
            "no donor or experimental replicate field",
            "not treated as validated regulators or causal mechanisms",
        ):
            self.assertIn(phrase, boundaries)
        serialized = REPORT.read_text(encoding="utf-8")
        for forbidden in (
            "/Users/",
            "/private/",
            "/var/folders/",
            "API_KEY",
            "ACCESS_TOKEN=",
            "SECRET=",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertIsNone(
            re.search(
                r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*"
                r"['\"]?[A-Za-z0-9_-]{16,}",
                serialized,
                re.IGNORECASE,
            )
        )


if __name__ == "__main__":
    unittest.main()
