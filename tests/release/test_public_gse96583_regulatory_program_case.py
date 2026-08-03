import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-regulatory-program.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-regulatory-network"
)


class PublicGSE96583RegulatoryProgramCaseTests(unittest.TestCase):
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
                    / "run_grnboost2_programs.py"
                ).read_bytes()
            ).hexdigest(),
        )

    def test_paired_design_programs_and_ifn_controls_are_preserved(self):
        source = self.report["source"]["validation"]
        execution = self.report["execution"]
        self.assertEqual(source["selected_cells"], 480)
        self.assertEqual(source["donors"], 8)
        self.assertEqual(source["biological_samples"], 16)
        self.assertGreaterEqual(execution["scored_programs"], 20)
        self.assertEqual(execution["auc_shape"], [480, execution["scored_programs"]])
        for tf in ("IRF1", "IRF7", "STAT1"):
            effect = execution["independent_ifn_control_programs"][tf]
            self.assertEqual(effect["positive_donors"], 8)
            self.assertGreater(effect["median_stim_minus_ctrl"], 0)
        self.assertGreaterEqual(
            execution["independent_ifn_control_programs"]["STAT2"][
                "positive_donors"
            ],
            7,
        )
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(execution["source_artifacts_immutable"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "does not call them motif-pruned regulons",
            "complete executable fixture separately validates",
            "does not establish direct tf binding",
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
