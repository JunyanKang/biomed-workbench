import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-pbmc-multiome-integration.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-multimodal-integration"
)


class PublicPBMCMultiomeIntegrationCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_templates(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["module"]["version"], "1.1.0")
        self.assertEqual(
            report["module"]["manifest_sha256"],
            hashlib.sha256((MODULE_ROOT / "module.json").read_bytes()).hexdigest(),
        )
        for name, digest in report["module"]["template_sha256"].items():
            self.assertEqual(
                digest,
                hashlib.sha256((MODULE_ROOT / "templates" / name).read_bytes()).hexdigest(),
            )
        self.assertEqual(
            report["source"]["sha256"],
            "03f946fc11984e6d4e8bf9a5d5904654c3d8b6b5776e08b7962796a9cb81c48d",
        )

    def test_paired_inputs_and_backend_outputs_are_preserved(self):
        source = self.report["source"]["validation"]
        execution = self.report["execution"]
        self.assertEqual(source["selected_cells"], 600)
        self.assertEqual(source["selected_rna_features"], 800)
        self.assertEqual(source["selected_atac_features"], 1000)
        self.assertGreater(execution["wnn"]["wknn_nonzero"], 0)
        self.assertGreater(execution["wnn"]["wsnn_nonzero"], 0)
        self.assertGreaterEqual(execution["wnn"]["clusters"], 2)
        self.assertEqual(execution["mofaplus"]["variance_explained_rows"], 2)
        self.assertEqual(execution["mofaplus"]["weight_rows"], 240)
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(execution["source_artifact_immutable"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "not biological annotation",
            "selected without cluster labels",
            "does not infer missing modalities",
            "not causal cross-modal regulation",
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
