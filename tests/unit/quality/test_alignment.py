import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import AlignmentQualityReportError, parse_samtools_flagstat_report


def section(*, total=4, primary=4, mapped=2, paired=4, properly_paired=2):
    return {
        "total": total, "primary": primary, "secondary": 0, "supplementary": total - primary,
        "duplicates": 0, "primary duplicates": 0, "mapped": mapped, "mapped %": 50.0 if total else None,
        "primary mapped": mapped, "primary mapped %": 50.0 if primary else None, "paired in sequencing": paired,
        "read1": paired // 2, "read2": paired // 2, "properly paired": properly_paired,
        "properly paired %": 50.0 if paired else None, "with itself and mate mapped": properly_paired,
        "singletons": 0, "singletons %": 0.0 if paired else None, "with mate mapped to a different chr": 0,
        "with mate mapped to a different chr (mapQ >= 5)": 0,
    }


class AlignmentQualityTests(unittest.TestCase):
    def parse(self, payload):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "flagstat.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return parse_samtools_flagstat_report(path)

    def test_summarizes_qc_strata_and_preserves_interpretation_scope(self):
        empty = section(total=0, primary=0, mapped=0, paired=0, properly_paired=0)
        result = self.parse({"QC-passed reads": section(), "QC-failed reads": empty})
        self.assertEqual(result["counts"]["total"], 4)
        self.assertEqual(result["metrics"]["mapped_percent"], 50.0)
        self.assertEqual(result["metrics"]["properly_paired_percent"], 50.0)
        self.assertTrue(result["paired_end_observed"])
        self.assertIn("reference choice", result["interpretation_policy"])

    def test_rejects_missing_sections_count_violations_and_empty_reports(self):
        empty = section(total=0, primary=0, mapped=0, paired=0, properly_paired=0)
        invalid = [
            {"QC-passed reads": section()},
            {"QC-passed reads": {**section(), "primary": 3}, "QC-failed reads": empty},
            {"QC-passed reads": {**section(), "mapped %": 75.0}, "QC-failed reads": empty},
            {"QC-passed reads": empty, "QC-failed reads": empty},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(AlignmentQualityReportError):
                self.parse(payload)
