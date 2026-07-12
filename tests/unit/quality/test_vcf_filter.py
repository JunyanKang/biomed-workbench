import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import VCFReportError, parse_vcf_filter_outputs


PARAMETERS = {
    "minimum_quality": 30.0,
    "minimum_depth": 10,
    "minimum_allele_fraction": 0.05,
    "genes": ["GENE1"],
    "require_pass": True,
    "missing_metric_policy": "exclude",
}
VCF = """##fileformat=VCFv4.5
##contig=<ID=chr1,length=1000>
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_A
chr1\t100\tv1\tA\tG\t60\tPASS\tDP=30;AF=0.25;ANN=G|missense_variant|MODERATE|GENE1\tGT\t0/1
"""


class VCFFilterOutputTests(unittest.TestCase):
    def outputs(self, root: Path, *, vcf: str = VCF, accepted: int = 1, exclusions=None):
        exclusions = {"depth": 1} if exclusions is None else exclusions
        vcf_path = root / "filtered.vcf"
        report_path = root / "report.json"
        vcf_path.write_text(vcf, encoding="utf-8")
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "fileformat": "VCFv4.5",
                    "method": "strict-biallelic-vcf-filter-v1",
                    "parameters": PARAMETERS,
                    "input_record_count": 2,
                    "accepted_record_count": accepted,
                    "excluded_record_count": 2 - accepted,
                    "exclusion_counts": exclusions,
                    "accepted_record_keys": ["chr1:100:A:G:v1"] if accepted else [],
                    "sample_count": 1,
                    "quality_status": "passed",
                }
            ),
            encoding="utf-8",
        )
        return vcf_path, report_path

    def test_reconciles_filtered_records_parameters_and_exclusion_accounting(self):
        with tempfile.TemporaryDirectory() as temporary:
            vcf, report = self.outputs(Path(temporary))
            result = parse_vcf_filter_outputs(vcf, report, expected_parameters=PARAMETERS, expected_samples=("SAMPLE_A",), expected_input_count=2)

        self.assertEqual(result["accepted_record_count"], 1)
        self.assertEqual(result["exclusion_counts"], {"depth": 1})
        self.assertEqual(result["quality_status"], "passed")

    def test_rejects_failing_output_record_or_inconsistent_accounting(self):
        invalid_vcf = VCF.replace("\t60\t", "\t10\t")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vcf, report = self.outputs(root, vcf=invalid_vcf)
            with self.assertRaises(VCFReportError):
                parse_vcf_filter_outputs(vcf, report, expected_parameters=PARAMETERS, expected_samples=("SAMPLE_A",), expected_input_count=2)
            vcf, report = self.outputs(root, exclusions={})
            with self.assertRaises(VCFReportError):
                parse_vcf_filter_outputs(vcf, report, expected_parameters=PARAMETERS, expected_samples=("SAMPLE_A",), expected_input_count=2)
