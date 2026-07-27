import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = (
    ROOT
    / "reports"
    / "public-case-pbmc3k-droplet-decontamination.json"
)
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-droplet-decontamination"
)


class PublicPBMC3kDropletDecontaminationCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_sources_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["dataset"], "3k PBMCs from a healthy donor")
        self.assertEqual(report["module"]["version"], "1.1.0")
        self.assertEqual(
            report["module"]["manifest_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "module.json").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (
                    MODULE_ROOT
                    / "templates"
                    / "run_emptydrops_soupx.R"
                ).read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            report["source"]["files"]["raw"]["sha256"],
            "6a8f903aa87d196f66f9b24414bf5ab3e875cf554be2613eb0409a7afd668f01",
        )

    def test_raw_filtered_and_emptydrops_accounting_are_preserved(self):
        source = self.report["source"]["validation"]
        execution = self.report["execution"]
        self.assertEqual(source["raw_droplets"], 737280)
        self.assertEqual(source["filtered_cells"], 2700)
        self.assertEqual(source["features"], 32738)
        self.assertEqual(execution["raw_barcodes_accounted"], 737280)
        self.assertEqual(execution["emptydrops_tested"], 2962)
        self.assertEqual(execution["emptydrops_called"], 2182)
        self.assertEqual(
            execution["filtered_cells_not_supported_by_emptydrops"], 518
        )
        self.assertEqual(
            execution["emptydrops_calls_outside_cellranger_filtered_set"], 0
        )

    def test_soupx_correction_and_marker_sanity_are_gated(self):
        execution = self.report["execution"]
        self.assertAlmostEqual(
            execution["contamination_fraction"]["median"], 0.057
        )
        self.assertEqual(execution["removed_counts"], 364355)
        self.assertGreaterEqual(execution["minimum_marker_retention"], 0.80)
        self.assertTrue(execution["source_archives_immutable"])
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "not automatically removed",
            "dataset- and clustering-specific",
            "not proof that every cell type",
            "corrected counts remain an alternative representation",
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
