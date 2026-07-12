import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import TMBReportError, parse_tmb_report


def report():
    return {
        "schema_version": 1,
        "method": "ann-nonsynonymous-variants-per-callable-bed-union-mb-v1",
        "input_variant_count": 2,
        "within_callable_variant_count": 2,
        "outside_callable_variant_count": 0,
        "non_nonsynonymous_variant_count": 0,
        "nonsynonymous_variant_count": 2,
        "eligible_variant_keys": ["chr1:100:A:G:v1", "chr1:215:G:T:v6"],
        "category_counts": {"missense": 2},
        "gene_counts": {"GENE1": 1, "GENE3": 1},
        "input_interval_count": 3,
        "merged_interval_count": 2,
        "callable_bases": 1500000,
        "callable_megabases": 1.5,
        "tmb_mutations_per_mb": 4 / 3,
        "quality_status": "passed",
        "classification_policy": "none-without-assay-indication-and-validated-cutoffs",
    }


class TMBReportTests(unittest.TestCase):
    def parse(self, payload):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tmb.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return parse_tmb_report(path, expected_input_variants=2, expected_input_intervals=3)

    def test_validates_variant_interval_and_denominator_accounting(self):
        result = self.parse(report())

        self.assertEqual(result["merged_interval_count"], 2)
        self.assertEqual(result["nonsynonymous_variant_count"], 2)
        self.assertAlmostEqual(result["tmb_mutations_per_mb"], 4 / 3)
        self.assertTrue(result["classification_policy"].startswith("none"))

    def test_rejects_inconsistent_counts_or_tmb_arithmetic(self):
        for key, value in (("within_callable_variant_count", 1), ("callable_megabases", 2.0), ("tmb_mutations_per_mb", 2.0)):
            payload = report()
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(TMBReportError):
                self.parse(payload)
