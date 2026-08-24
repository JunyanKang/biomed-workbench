import json
import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.scientific_taxonomy import classify_module


class ScientificTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModuleRegistry.discover(BUILTIN_ROOT)

    def test_every_registered_module_has_exactly_one_primary_scale(self):
        rows = [classify_module(module) for module in self.registry.all()]
        self.assertEqual(len(rows), len(self.registry.all()))
        self.assertEqual(len({row["module_id"] for row in rows}), len(rows))
        self.assertTrue(
            all(row["primary_scale"] in {"bulk", "single-cell", "spatial", "universal"} for row in rows)
        )

    def test_representative_modules_land_in_the_correct_scale(self):
        expected = {
            "bulk-chromatin-peak-calling": "bulk",
            "bulk-ribosome-profiling": "bulk",
            "single-cell-batch-integration": "single-cell",
            "single-cell-spatial-analysis": "spatial",
            "differential-expression": "universal",
            "figure-specification": "universal",
            "publication-figure-package": "universal",
            "journal-targeting-and-compliance": "universal",
        }
        for module_id, scale in expected.items():
            self.assertEqual(classify_module(self.registry.get(module_id))["primary_scale"], scale)

    def test_quantitative_imaging_and_project_wide_figure_support_are_distinct(self):
        for module_id in (
            "image-profile",
            "image-segment",
            "image-colocalization",
            "point-tracking",
            "cell-migration-metrics",
            "image-translation-registration",
        ):
            row = classify_module(self.registry.get(module_id))
            self.assertEqual(row["capability_scope"], "image-derived-measurement")
            self.assertEqual(row["measurement_family"], "quantitative image measurement")
            self.assertEqual(row["method_role"], "measurement-specific")

        for module_id in ("figure-specification", "publication-figure-package"):
            row = classify_module(self.registry.get(module_id))
            self.assertEqual(row["primary_scale"], "universal")
            self.assertEqual(row["capability_scope"], "project-wide-figure-support")
            self.assertNotIn("imaging", row["domains"])

        communication = classify_module(self.registry.get("scientific-illustration-generation"))
        self.assertEqual(communication["capability_scope"], "scientific-communication-asset")
        self.assertEqual(communication["method_role"], "communication-support")

    def test_cuttag_target_normalization_and_specificity_are_not_assay_classes(self):
        path = BUILTIN_ROOT / "bulk-chromatin-peak-calling" / "module.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        properties = manifest["input_schema"]["properties"]
        self.assertEqual(properties["assay"]["enum"], ["chip-seq", "cutrun", "cuttag"])
        self.assertIn("target_or_antibody", properties)
        self.assertIn("specificity_control", properties)
        self.assertNotIn("s9.6", {value.lower() for value in properties["assay"]["enum"]})
        self.assertNotIn("spike-in", {value.lower() for value in properties["assay"]["enum"]})

    def test_generated_taxonomy_report_is_bound_to_current_registry(self):
        report_path = BUILTIN_ROOT.parents[2] / "reports" / "module-scientific-taxonomy.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["module_count"], len(self.registry.all()))
        self.assertEqual(report["registry_digest"], self.registry.digest)


if __name__ == "__main__":
    unittest.main()
