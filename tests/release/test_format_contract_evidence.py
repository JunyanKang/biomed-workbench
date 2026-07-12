import json
import unittest
from pathlib import Path

from biomed_workbench.formats import FormatRegistry
from tools.build_format_contract_report import build


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "format-contract-registry.json"


class FormatContractEvidenceTests(unittest.TestCase):
    def test_report_is_exactly_rebuildable_from_builtin_registry(self):
        self.assertEqual(json.loads(REPORT.read_text(encoding="utf-8")), build())

    def test_report_covers_every_required_foundational_format(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        expected = {
            "fastq", "fasta", "sam", "bam", "cram", "vcf", "bcf", "bed", "gtf", "gff3",
            "count-matrix", "h5ad", "loom", "matrix-market", "fragments", "bigwig", "tabular",
        }

        self.assertEqual(set(report["format_names"]), expected)
        self.assertEqual(report["profile_count"], 17)
        self.assertEqual(report["registry_digest"], FormatRegistry.builtin().digest)
        self.assertTrue(all(profile["specification_version"] for profile in report["profiles"]))

    def test_report_contains_no_machine_path_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/var/folders/", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
