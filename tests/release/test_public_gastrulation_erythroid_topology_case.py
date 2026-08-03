import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gastrulation-erythroid-topology.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-trajectory-topology"
)


class PublicGastrulationErythroidTopologyCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["module"]["version"], "1.1.0")
        assert_evidence_scope_current(self, report)
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (
                    MODULE_ROOT
                    / "templates"
                    / "run_slingshot_monocle_tradeseq.R"
                ).read_bytes()
            ).hexdigest(),
        )

    def test_public_sampling_and_orientation_contract(self):
        source = self.report["source"]["validation"]
        self.assertEqual(source["source_cells"], 9815)
        self.assertEqual(source["source_genes"], 53801)
        self.assertEqual(source["selected_cells"], 297)
        self.assertEqual(source["selected_genes"], 160)
        self.assertEqual(source["samples"], 27)
        self.assertEqual(source["external_stages"], 7)
        self.assertIn("label-blind", source["feature_selection"])

    def test_single_lineage_and_applicable_tests_pass(self):
        results = self.report["execution"]["results"]
        self.assertEqual(results["lineage_cell_support"], {"Lineage1": 297})
        self.assertGreater(results["slingshot_external_time_spearman"], 0.8)
        self.assertGreater(results["monocle3_external_time_spearman"], 0.8)
        self.assertGreater(results["slingshot_monocle3_spearman"], 0.95)
        self.assertEqual(results["association_rows"], 160)
        self.assertEqual(results["start_vs_end_rows"], 160)
        self.assertEqual(results["pattern_rows"], 0)
        self.assertEqual(results["differential_end_rows"], 0)
        self.assertEqual(
            results["test_applicability"]["pattern"],
            "not_applicable_single_lineage",
        )
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "only for postfit direction validation",
            "do not establish ancestry",
            "not donor-level condition inference",
            "deterministic bifurcation fixture",
        ):
            self.assertIn(phrase, boundaries)
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
