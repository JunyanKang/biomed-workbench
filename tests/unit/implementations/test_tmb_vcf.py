import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.implementations.tmb_vcf import TMBError, calculate


VCF = """##fileformat=VCFv4.5
##contig=<ID=chr1,length=1000>
##contig=<ID=chr2,length=1000>
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
chr1\t100\tv1\tA\tG\t60\tPASS\tANN=G|missense_variant|MODERATE|GENE1
chr2\t100\tv2\tC\tT\t60\tPASS\tANN=T|stop_gained|HIGH|GENE2
"""


class TMBVCFImplementationTests(unittest.TestCase):
    def execute(self, bed_text: str):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vcf = root / "filtered.vcf"
            bed = root / "callable.bed"
            report = root / "report.json"
            vcf.write_text(VCF, encoding="utf-8")
            bed.write_text(bed_text, encoding="utf-8")
            calculate(vcf, bed, report)
            return json.loads(report.read_text(encoding="utf-8"))

    def test_counts_valid_vcf_contigs_without_callable_bed_territory_as_outside(self):
        result = self.execute("chr1\t0\t1000\n")

        self.assertEqual(result["input_variant_count"], 2)
        self.assertEqual(result["within_callable_variant_count"], 1)
        self.assertEqual(result["outside_callable_variant_count"], 1)
        self.assertEqual(result["eligible_variant_keys"], ["chr1:100:A:G:v1"])

    def test_rejects_callable_bed_chromosome_absent_from_vcf_dictionary(self):
        with self.assertRaises(TMBError):
            self.execute("chr3\t0\t1000\n")


if __name__ == "__main__":
    unittest.main()
