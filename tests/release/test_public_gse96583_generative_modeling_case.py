import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current

from biomed_workbench.modules.contract import parse_manifest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-generative-modeling.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-generative-modeling"
)
MODULE_VERSION = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8"))).version


class PublicGSE96583GenerativeModelingCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["accession"], "GSE96583")
        self.assertEqual(report["module"]["version"], MODULE_VERSION)
        assert_evidence_scope_current(self, report)
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "templates" / "train_scvi_scanvi.py").read_bytes()
            ).hexdigest(),
        )

    def test_donor_holdout_and_prediction_metrics_are_preserved(self):
        source = self.report["source"]["validation"]
        query = self.report["execution"]["heldout_query_donor_evaluation"]
        self.assertEqual(source["selected_cells"], 1600)
        self.assertEqual(source["selected_genes"], 2500)
        self.assertEqual(source["donors"], 8)
        self.assertEqual(source["biological_samples"], 16)
        self.assertEqual(source["query_donors"], ["1256", "1488"])
        self.assertEqual(query["cells"], 400)
        self.assertGreaterEqual(query["accuracy"], 0.90)
        self.assertGreaterEqual(query["macro_f1"], 0.70)
        self.assertGreaterEqual(
            self.report["execution"]["mode_results"]["scanvi"][
                "heldout_annotation_metrics"
            ]["macro_f1"],
            0.70,
        )

    def test_failed_mixing_gate_forces_no_selection(self):
        execution = self.report["execution"]
        self.assertEqual(execution["eligible_modes"], [])
        self.assertIsNone(execution["selected_mode"])
        self.assertEqual(
            execution["blocked_modes"],
            {"scanvi": ["batch_mixing_gain"], "scvi": ["batch_mixing_gain"]},
        )
        for mode in ("scvi", "scanvi"):
            result = execution["mode_results"][mode]
            self.assertLess(
                result["metric_deltas"]["batch_neighbor_entropy_gain"], 0
            )
            self.assertTrue(result["source_immutable"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "absent from the input h5ad",
            "physically removed",
            "no model is selected",
            "raw counts and donor identities remain authoritative",
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
