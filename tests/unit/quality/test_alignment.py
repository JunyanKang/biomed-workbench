import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import AlignmentQualityReportError, parse_bwa_mem_sam, parse_samtools_flagstat_report


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

    def test_bwa_sam_preserves_reference_sample_program_and_read_accounting(self):
        sam = """@HD\tVN:1.5\tSO:unsorted\tGO:query
@SQ\tSN:chr1\tLN:1000
@RG\tID:sample-01\tSM:sample-01\tPL:ILLUMINA
@PG\tID:bwa\tPN:bwa\tVN:0.7.19-r1273\tCL:bwa mem inputs/reference/reference.fa inputs/reads.fastq
mapped\t0\tchr1\t101\t60\t50M\t*\t0\t0\tACGT\tIIII\tRG:Z:sample-01
unmapped\t4\t*\t0\t0\t*\t*\t0\t0\tTTTT\tIIII\tRG:Z:sample-01
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "alignments.sam"
            path.write_text(sam, encoding="utf-8")
            result = parse_bwa_mem_sam(
                path,
                expected_version="0.7.19-r1273",
                expected_sample_id="sample-01",
                reference_sequences={"chr1": 1000},
                expected_read_count=2,
            )
        self.assertEqual(result["counts"]["mapped"], 1)
        self.assertEqual(result["primary_mapping_percent"], 50.0)
        self.assertEqual(result["program_record_paths"], "workdir-relative")

    def test_bwa_sam_rejects_absolute_program_paths_and_sample_drift(self):
        template = """@HD\tVN:1.5\tSO:unsorted\tGO:query
@SQ\tSN:chr1\tLN:1000
@RG\tID:sample-01\tSM:sample-01
@PG\tID:bwa\tPN:bwa\tVN:0.7.19-r1273\tCL:{command}
read1\t4\t*\t0\t0\t*\t*\t0\t0\tTTTT\tIIII\tRG:Z:{record_sample}
"""
        cases = (("bwa mem /tmp/reference.fa reads.fastq", "sample-01"), ("bwa mem reference.fa reads.fastq", "other"))
        for command, record_sample in cases:
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "alignments.sam"
                path.write_text(template.format(command=command, record_sample=record_sample), encoding="utf-8")
                with self.subTest(command=command, sample=record_sample), self.assertRaises(AlignmentQualityReportError):
                    parse_bwa_mem_sam(path, expected_version="0.7.19-r1273", expected_sample_id="sample-01", reference_sequences={"chr1": 1000}, expected_read_count=1)
