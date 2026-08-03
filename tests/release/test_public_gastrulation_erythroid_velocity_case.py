import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gastrulation-erythroid-velocity.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-trajectory-velocity"
)


class PublicGastrulationErythroidVelocityCaseTests(unittest.TestCase):
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
                (MODULE_ROOT / "templates" / "run_velocity.py").read_bytes()
            ).hexdigest(),
        )

    def test_public_design_and_direction_gates_are_preserved(self):
        source = self.report["source"]["validation"]
        execution = self.report["execution"]
        self.assertEqual(source["selected_cells"], 1234)
        self.assertEqual(source["source_genes"], 53801)
        self.assertEqual(source["samples"], 27)
        self.assertEqual(len(source["embryonic_stages"]), 7)
        self.assertTrue(source["spliced_integer_like"])
        self.assertTrue(source["unspliced_integer_like"])
        self.assertGreaterEqual(execution["model"]["modeled_genes"], 80)
        self.assertGreaterEqual(execution["model"]["finite_fit_genes"], 80)
        self.assertGreaterEqual(
            execution["direction_validation"]["latent_time_spearman"], 0.15
        )
        self.assertGreaterEqual(
            execution["direction_validation"]["velocity_pseudotime_spearman"],
            0.10,
        )
        self.assertGreaterEqual(
            execution["direction_validation"]["root_terminal_separation"], 0.15
        )
        self.assertGreaterEqual(
            execution["confidence"]["median_velocity_confidence"], 0.40
        )

    def test_repeat_and_source_preservation_are_exact(self):
        execution = self.report["execution"]
        self.assertEqual(execution["independent_template_runs"], 2)
        self.assertTrue(execution["source_artifact_immutable"])
        self.assertTrue(execution["all_outputs_reloaded"])
        for field in execution["exact_repeat_fields"].values():
            self.assertTrue(field["exactly_equal"])
            self.assertTrue(field["missing_value_mask_equal"])
            self.assertEqual(field["maximum_absolute_difference"], 0.0)
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "physically absent",
            "independent root and terminal anchors",
            "not treated as independent condition-level replicates",
            "does not establish lineage causality",
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
