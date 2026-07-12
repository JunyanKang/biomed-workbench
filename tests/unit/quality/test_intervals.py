import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import IntervalReportError, parse_bedtools_intersect_report


class IntervalReportTests(unittest.TestCase):
    def parse(self, text, *, query_columns=4, reference_columns=4):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "overlaps.tsv"
            path.write_text(text, encoding="utf-8")
            return parse_bedtools_intersect_report(path, query_columns=query_columns, reference_columns=reference_columns)

    def test_summarizes_pairwise_zero_based_half_open_overlaps(self):
        result = self.parse("chr1\t10\t20\tq1\tchr1\t15\t18\tr1\nchr1\t10\t20\tq1\tchr1\t18\t25\tr2\n")
        self.assertEqual(result["overlap_pair_count"], 2)
        self.assertEqual(result["overlapping_query_interval_count"], 1)
        self.assertEqual(result["total_pairwise_overlap_bp"], 5)
        self.assertEqual(result["coordinate_system"], "zero-based-half-open")

    def test_empty_result_is_valid_but_malformed_or_nonoverlapping_rows_fail(self):
        self.assertTrue(self.parse("")["empty_result"])
        invalid = (
            "chr1\t10\t20\tq1\tchr2\t15\t18\tr1\n",
            "chr1\t20\t10\tq1\tchr1\t15\t18\tr1\n",
            "chr1\t10\t20\tq1\tchr1\t20\t25\tr1\n",
            "track name=x\n",
        )
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(IntervalReportError):
                self.parse(text)
