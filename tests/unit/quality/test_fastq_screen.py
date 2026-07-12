import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import FastQScreenReportError, parse_fastq_screen_report


REPORT = """#Fastq_screen version: 0.16.0\t#Aligner: bowtie2\t#Processing all reads in FASTQ files
Genome\t#Reads_processed\t#Unmapped\t%Unmapped\t#One_hit_one_genome\t%One_hit_one_genome\t#Multiple_hits_one_genome\t%Multiple_hits_one_genome\t#One_hit_multiple_genomes\t%One_hit_multiple_genomes\tMultiple_hits_multiple_genomes\t%Multiple_hits_multiple_genomes
target\t12\t6\t50.00\t0\t0.00\t6\t50.00\t0\t0.00\t0\t0.00
contaminant\t12\t12\t100.00\t0\t0.00\t0\t0.00\t0\t0.00\t0\t0.00

%Hit_no_genomes: 50.00
"""


class FastQScreenParserTests(unittest.TestCase):
    def test_parses_declared_reference_screen_and_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "screen.txt"
            path.write_text(REPORT, encoding="utf-8")
            result = parse_fastq_screen_report(path, expected_references=("target",), max_unexpected_percent=1.0)

        self.assertEqual(result["reads_processed"], 12)
        self.assertEqual(result["references"]["target"]["mapped_any_percent"], 50.0)
        self.assertEqual(result["contamination_screening"]["status"], "passed")
        self.assertEqual(result["flagged_unexpected_references"], [])

    def test_flags_unexpected_mapping_and_rejects_version_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            flagged = root / "flagged.txt"
            flagged.write_text(REPORT.replace("100.00\t0\t0.00\t0\t0.00", "90.00\t0\t0.00\t1\t10.00", 1), encoding="utf-8")
            result = parse_fastq_screen_report(flagged, expected_references=("target",), max_unexpected_percent=1.0)
            old = root / "old.txt"
            old.write_text(REPORT.replace("0.16.0", "0.15.3"), encoding="utf-8")

            self.assertEqual(result["flagged_unexpected_references"], ["contaminant"])
            with self.assertRaisesRegex(FastQScreenReportError, "version"):
                parse_fastq_screen_report(old, expected_references=("target",), max_unexpected_percent=1.0)


if __name__ == "__main__":
    unittest.main()
