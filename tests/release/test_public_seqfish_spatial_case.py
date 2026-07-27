import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-seqfish-spatial.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-spatial-analysis"
)


class PublicSeqFISHSpatialCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["module"]["version"], "1.1.0")
        self.assertEqual(
            report["module"]["manifest_sha256"],
            hashlib.sha256((MODULE_ROOT / "module.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (
                    MODULE_ROOT
                    / "templates"
                    / "run_spatial_analysis.py"
                ).read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            report["source"]["sha256"],
            "7e544c0ede7538067537da69c52748ad01522ef7fc8691e077fd73c9434019f7",
        )

    def test_spatial_execution_and_single_sample_boundary_are_preserved(self):
        source = self.report["source"]["validation"]
        execution = self.report["execution"]
        self.assertEqual(source["selected_observations"], 2000)
        self.assertEqual(source["selected_genes"], 351)
        self.assertEqual(execution["cross_sample_edges"], 0)
        self.assertGreater(execution["spatial_edges"], 1000)
        self.assertEqual(execution["moran_genes"], 20)
        self.assertGreaterEqual(execution["domains"], 2)
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(execution["source_artifact_immutable"])
        self.assertEqual(
            set(execution["spatial_gene_support"].values()),
            {1},
        )
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "one embryo",
            "rather than biological replication",
            "not replicated spatial genes",
            "do not establish lineage",
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
