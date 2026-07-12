import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import VCFReportError, parse_tabix_vcf_query


HEADER = """##fileformat=VCFv4.5
##contig=<ID=chr1,length=1000>
##FORMAT=<ID=GT,Number=1,Type=String,Description=Genotype>
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_A
"""


class VCFQueryReportTests(unittest.TestCase):
    def parse(self, records: str, *, region: str = "chr1:90-220"):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "subset.vcf"
            path.write_text(HEADER + records, encoding="utf-8")
            return parse_tabix_vcf_query(path, region=region, expected_samples=("SAMPLE_A",))

    def test_validates_header_region_samples_and_variant_counts(self):
        result = self.parse("chr1\t100\tv1\tA\tG\t60\tPASS\t.\tGT\t0/1\nchr1\t200\tv2\tAT\tA\t50\tPASS\t.\tGT\t0/1\n")

        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["type_counts"], {"indel_or_mnv": 1, "snv": 1})
        self.assertEqual(result["samples"], ["SAMPLE_A"])
        self.assertEqual(result["coordinate_system"], "one-based-inclusive")

    def test_empty_region_is_valid_but_out_of_region_unsorted_or_sample_drift_fails(self):
        self.assertTrue(self.parse("")["empty_result"])
        invalid = (
            "chr2\t100\tv1\tA\tG\t60\tPASS\t.\tGT\t0/1\n",
            "chr1\t200\tv2\tA\tG\t60\tPASS\t.\tGT\t0/1\nchr1\t100\tv1\tC\tT\t60\tPASS\t.\tGT\t0/1\n",
            "chr1\t221\tv3\tA\tG\t60\tPASS\t.\tGT\t0/1\n",
        )
        for records in invalid:
            with self.subTest(records=records), self.assertRaises(VCFReportError):
                self.parse(records)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "subset.vcf"
            path.write_text(HEADER.replace("SAMPLE_A", "SAMPLE_B") + "chr1\t100\tv1\tA\tG\t60\tPASS\t.\tGT\t0/1\n", encoding="utf-8")
            with self.assertRaises(VCFReportError):
                parse_tabix_vcf_query(path, region="chr1:90-220", expected_samples=("SAMPLE_A",))
